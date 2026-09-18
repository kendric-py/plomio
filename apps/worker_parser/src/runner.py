import asyncio
import logging
from datetime import timedelta
from uuid import UUID

from pydantic import BaseModel

from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import (
    OzonPaginationCursor,
    OzonReviewCursor,
    SessionMessage,
    WildberriesPaginationCursor,
)
from apps.worker_parser.src.enums import WorkerParserStatus
from apps.worker_parser.src.exceptions import ParserError
from apps.worker_parser.src.liveness import LivenessReporter
from apps.worker_parser.src.marketplaces.ozon import fetchers as ozon_fetchers
from apps.worker_parser.src.marketplaces.ozon.utils import create_ozon_http_session
from apps.worker_parser.src.marketplaces.wb import fetchers as wb_fetchers
from apps.worker_parser.src.marketplaces.wb.utils import create_wb_http_session
from apps.worker_parser.src.redis_session_client import RedisSessionClient
from apps.worker_parser.src.retry_policy import SessionAction, resolve_retry_policy
from core.database import get_database_connection
from core.enums import Marketplace
from core.transaction_manager import AsyncTransactionManager
from packages.result.src.service import ResultService
from packages.task.src.entities import TaskEntity, TaskItemEntity
from packages.task.src.enums import ParseType, TaskItemStatus, TaskStatus
from packages.task.src.service import TERMINAL_ITEM_STATUSES, TaskService

logger = logging.getLogger(__name__)

_LISTING_FETCHERS = {
    (Marketplace.OZON, ParseType.SEARCH_QUERY): ozon_fetchers.fetch_ozon_search_page,
    (Marketplace.OZON, ParseType.CATEGORY): ozon_fetchers.fetch_ozon_category_page,
    (Marketplace.OZON, ParseType.SELLER): ozon_fetchers.fetch_ozon_seller_page,
    (Marketplace.WILDBERRIES, ParseType.SEARCH_QUERY): wb_fetchers.fetch_wb_search_page,
    (Marketplace.WILDBERRIES, ParseType.CATEGORY): wb_fetchers.fetch_wb_category_page,
    (Marketplace.WILDBERRIES, ParseType.SELLER): wb_fetchers.fetch_wb_seller_page,
}

_CURSOR_MODEL_BY_MARKETPLACE = {
    Marketplace.OZON: OzonPaginationCursor,
    Marketplace.WILDBERRIES: WildberriesPaginationCursor,
}

_HTTP_SESSION_FACTORY_BY_MARKETPLACE = {
    Marketplace.OZON: create_ozon_http_session,
    Marketplace.WILDBERRIES: create_wb_http_session,
}

_PRODUCT_PAGE_FETCHERS = {
    Marketplace.OZON: ozon_fetchers.fetch_ozon_product_page,
    Marketplace.WILDBERRIES: wb_fetchers.fetch_wb_product_page,
}

_SELLER_PROFILE_FETCHERS = {
    Marketplace.OZON: ozon_fetchers.fetch_ozon_seller_profile,
    Marketplace.WILDBERRIES: wb_fetchers.fetch_wb_seller_profile,
}


async def acquire_session_or_wait(
    marketplace: Marketplace,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> SessionMessage:
    while True:
        session_message = await session_client.acquire_session(marketplace=marketplace)
        if session_message is not None:
            return session_message
        liveness_reporter.set_status(WorkerParserStatus.WAITING_FOR_SESSION)
        await asyncio.sleep(config.SESSION_POOL.EMPTY_POOL_BACKOFF_SECONDS)


async def handle_product_page_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    fetch_product_page = _PRODUCT_PAGE_FETCHERS[task.marketplace]
    create_http_session = _HTTP_SESSION_FACTORY_BY_MARKETPLACE[task.marketplace]

    session_message: SessionMessage | None = None
    attempt_count = 0
    payload: BaseModel | None = None

    while payload is None:
        if session_message is None:
            session_message = await acquire_session_or_wait(task.marketplace, session_client, liveness_reporter)
        liveness_reporter.set_status(WorkerParserStatus.WORKING)
        http_session = create_http_session(session_message)
        try:
            payload = await fetch_product_page(item.input_value, http_session, session_message)
        except ParserError as error:
            policy = resolve_retry_policy(error)
            attempt_count += 1
            if attempt_count > policy.max_attempts:
                await task_service.complete_item(
                    item_id=item.id,
                    status=policy.resulting_item_status_on_exhaustion,
                    error_reason=str(error),
                )
                return
            if policy.session_action == SessionAction.REINIT_SESSION:
                session_message = None

    await result_service.record_results(
        task_item_id=item.id,
        marketplace=task.marketplace,
        parse_type=task.parse_type,
        payloads=[payload],
    )
    await task_service.record_item_progress(item_id=item.id, cursor=None, result_count=1)
    await task_service.complete_item(item_id=item.id, status=TaskItemStatus.SUCCEEDED)


async def handle_listing_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    fetch_page = _LISTING_FETCHERS[(task.marketplace, task.parse_type)]
    cursor_model = _CURSOR_MODEL_BY_MARKETPLACE[task.marketplace]
    create_http_session = _HTTP_SESSION_FACTORY_BY_MARKETPLACE[task.marketplace]

    cursor = cursor_model.model_validate(item.cursor) if item.cursor else None
    seen_keys: set[str] = set()
    result_count = item.result_count or 0
    session_message: SessionMessage | None = None
    attempt_count = 0
    pages_since_status_check = 0

    while True:
        if session_message is None:
            session_message = await acquire_session_or_wait(task.marketplace, session_client, liveness_reporter)
        liveness_reporter.set_status(WorkerParserStatus.WORKING)
        http_session = create_http_session(session_message)
        remaining_limit = None if task.result_limit is None else task.result_limit - result_count

        try:
            products, next_cursor = await fetch_page(
                item.input_value, cursor, remaining_limit, seen_keys, http_session, session_message,
            )
        except ParserError as error:
            policy = resolve_retry_policy(error)
            attempt_count += 1
            if attempt_count > policy.max_attempts:
                await task_service.complete_item(
                    item_id=item.id,
                    status=policy.resulting_item_status_on_exhaustion,
                    error_reason=str(error),
                )
                return
            if policy.session_action == SessionAction.REINIT_SESSION:
                session_message = None
            continue

        attempt_count = 0
        if products:
            await result_service.record_results(
                task_item_id=item.id,
                marketplace=task.marketplace,
                parse_type=task.parse_type,
                payloads=list(products),
            )
        result_count += len(products)
        cursor = next_cursor
        await task_service.record_item_progress(
            item_id=item.id,
            cursor=cursor.model_dump(mode='json') if cursor else None,
            result_count=result_count,
        )

        if cursor is None:
            break
        if remaining_limit is not None and remaining_limit - len(products) <= 0:
            break

        pages_since_status_check += 1
        if pages_since_status_check >= config.POLL.STATUS_CHECK_INTERVAL_PAGES:
            pages_since_status_check = 0
            refreshed_task = await task_service.get_task_by_id(task_id=task.id)
            if refreshed_task.status != TaskStatus.RUNNING:
                return

    if task.parse_type == ParseType.SELLER:
        await _record_seller_profile(task, item, session_message, result_service, session_client, liveness_reporter)

    await task_service.complete_item(item_id=item.id, status=TaskItemStatus.SUCCEEDED)


async def _record_seller_profile(
    task: TaskEntity,
    item: TaskItemEntity,
    session_message: SessionMessage | None,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    fetch_seller_profile = _SELLER_PROFILE_FETCHERS[task.marketplace]
    create_http_session = _HTTP_SESSION_FACTORY_BY_MARKETPLACE[task.marketplace]
    if session_message is None:
        session_message = await acquire_session_or_wait(task.marketplace, session_client, liveness_reporter)
    http_session = create_http_session(session_message)
    try:
        profile = await fetch_seller_profile(item.input_value, http_session, session_message)
    except ParserError as error:
        logger.warning('[seller_profile] failed to fetch profile for %s: %s', item.input_value, error)
        return
    await result_service.record_results(
        task_item_id=item.id,
        marketplace=task.marketplace,
        parse_type=task.parse_type,
        payloads=[profile],
    )


async def handle_reviews_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    if task.marketplace == Marketplace.OZON:
        await _handle_ozon_reviews(task, item, task_service, result_service, session_client, liveness_reporter)
    else:
        await _handle_wb_reviews(task, item, task_service, result_service, session_client, liveness_reporter)


async def _handle_ozon_reviews(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    cursor = OzonReviewCursor.model_validate(item.cursor) if item.cursor else None
    seen_uuids: set[str] = set(cursor.seen_uuids) if cursor else set()
    result_count = item.result_count or 0
    session_message: SessionMessage | None = None
    attempt_count = 0

    while True:
        if session_message is None:
            session_message = await acquire_session_or_wait(task.marketplace, session_client, liveness_reporter)
        liveness_reporter.set_status(WorkerParserStatus.WORKING)
        http_session = create_ozon_http_session(session_message)

        try:
            reviews, next_cursor = await ozon_fetchers.fetch_ozon_review_page(
                item.input_value, cursor, seen_uuids, http_session, session_message,
            )
        except ParserError as error:
            policy = resolve_retry_policy(error)
            attempt_count += 1
            if attempt_count > policy.max_attempts:
                await task_service.complete_item(
                    item_id=item.id,
                    status=policy.resulting_item_status_on_exhaustion,
                    error_reason=str(error),
                )
                return
            if policy.session_action == SessionAction.REINIT_SESSION:
                session_message = None
            continue

        attempt_count = 0
        if reviews:
            await result_service.record_results(
                task_item_id=item.id,
                marketplace=task.marketplace,
                parse_type=task.parse_type,
                payloads=list(reviews),
            )
        result_count += len(reviews)
        cursor = next_cursor
        await task_service.record_item_progress(
            item_id=item.id,
            cursor=cursor.model_dump(mode='json') if cursor else None,
            result_count=result_count,
        )
        if cursor is None:
            break

    await task_service.complete_item(item_id=item.id, status=TaskItemStatus.SUCCEEDED)


async def _handle_wb_reviews(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    session_message: SessionMessage | None = None
    attempt_count = 0
    reviews: list[BaseModel] | None = None

    while reviews is None:
        if session_message is None:
            session_message = await acquire_session_or_wait(task.marketplace, session_client, liveness_reporter)
        liveness_reporter.set_status(WorkerParserStatus.WORKING)
        http_session = create_wb_http_session(session_message)
        try:
            reviews = await wb_fetchers.fetch_wb_review_page(item.input_value, http_session, session_message)
        except ParserError as error:
            policy = resolve_retry_policy(error)
            attempt_count += 1
            if attempt_count > policy.max_attempts:
                await task_service.complete_item(
                    item_id=item.id,
                    status=policy.resulting_item_status_on_exhaustion,
                    error_reason=str(error),
                )
                return
            if policy.session_action == SessionAction.REINIT_SESSION:
                session_message = None

    if reviews:
        await result_service.record_results(
            task_item_id=item.id,
            marketplace=task.marketplace,
            parse_type=task.parse_type,
            payloads=list(reviews),
        )
    await task_service.record_item_progress(item_id=item.id, cursor=None, result_count=len(reviews))
    await task_service.complete_item(item_id=item.id, status=TaskItemStatus.SUCCEEDED)


async def process_task_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    if task.parse_type == ParseType.PRODUCT_PAGE:
        await handle_product_page_item(task, item, task_service, result_service, session_client, liveness_reporter)
    elif task.parse_type == ParseType.REVIEWS:
        await handle_reviews_item(task, item, task_service, result_service, session_client, liveness_reporter)
    else:
        await handle_listing_item(task, item, task_service, result_service, session_client, liveness_reporter)


async def process_claimed_task(
    task: TaskEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    items = await task_service.get_task_items(task_id=task.id)
    pending_items = [item for item in items if item.status not in TERMINAL_ITEM_STATUSES]

    for item in pending_items:
        refreshed_task = await task_service.get_task_by_id(task_id=task.id)
        if refreshed_task.status != TaskStatus.RUNNING:
            return
        await process_task_item(task, item, task_service, result_service, session_client, liveness_reporter)


async def run_lease_heartbeat_loop(
    task_id: UUID,
    worker_id: str,
    lease_duration: timedelta,
    interval_seconds: float,
    task_service: TaskService,
    stop_event: asyncio.Event,
) -> None:
    while not stop_event.is_set():
        try:
            await asyncio.wait_for(stop_event.wait(), timeout=interval_seconds)
        except asyncio.TimeoutError:
            await task_service.heartbeat(task_id=task_id, worker_id=worker_id, lease_duration=lease_duration)


async def run_poll_loop(
    task_service: TaskService,
    result_service: ResultService,
    session_client: RedisSessionClient,
    liveness_reporter: LivenessReporter,
) -> None:
    lease_duration = timedelta(seconds=config.POLL.LEASE_DURATION_SECONDS)

    while True:
        liveness_reporter.set_status(WorkerParserStatus.READY)
        task = await task_service.claim_next(worker_id=config.POLL.WORKER_ID, lease_duration=lease_duration)
        if task is None:
            await asyncio.sleep(config.POLL.INTERVAL_SECONDS)
            continue

        liveness_reporter.set_status(WorkerParserStatus.WORKING)
        stop_event = asyncio.Event()
        heartbeat_task = asyncio.create_task(
            run_lease_heartbeat_loop(
                task_id=task.id,
                worker_id=config.POLL.WORKER_ID,
                lease_duration=lease_duration,
                interval_seconds=config.POLL.HEARTBEAT_INTERVAL_SECONDS,
                task_service=task_service,
                stop_event=stop_event,
            ),
        )
        try:
            await process_claimed_task(task, task_service, result_service, session_client, liveness_reporter)
        except Exception:
            logger.exception('[task_processing_failed] task_id=%s', task.id)
        finally:
            stop_event.set()
            await heartbeat_task


async def run_main() -> None:
    _, session_factory = get_database_connection(config=config)
    transaction_manager = AsyncTransactionManager(session_factory=session_factory)
    task_service = TaskService(transaction_manager=transaction_manager)
    result_service = ResultService(transaction_manager=transaction_manager)
    session_client = RedisSessionClient()
    liveness_reporter = LivenessReporter()

    try:
        await asyncio.gather(
            run_poll_loop(task_service, result_service, session_client, liveness_reporter),
            liveness_reporter.run(),
        )
    finally:
        await session_client.close()
