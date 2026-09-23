import asyncio
import logging
from datetime import timedelta
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import (
    OzonPaginationCursor,
    OzonReviewCursor,
    SessionMessage,
    WildberriesPaginationCursor,
)
from apps.worker_parser.src.enums import WorkerParserStatus
from apps.worker_parser.src.exceptions import ParserError
from apps.worker_parser.src.marketplaces.ozon import fetchers as ozon_fetchers
from apps.worker_parser.src.marketplaces.ozon.utils import create_ozon_http_session
from apps.worker_parser.src.marketplaces.wb import fetchers as wb_fetchers
from apps.worker_parser.src.marketplaces.wb.utils import create_wb_http_session
from apps.worker_parser.src.retry_policy import SessionAction, resolve_retry_policy
from core.database import get_database_connection
from core.enums import Marketplace
from core.transaction_manager import AsyncTransactionManager
from packages.result.src.service import ResultService
from packages.sessions.src.redis_store import SessionPoolStore
from packages.task.src.entities import TaskEntity, TaskItemEntity
from packages.task.src.enums import ParseType, TaskItemStatus, TaskStatus
from packages.task.src.service import TERMINAL_ITEM_STATUSES, TaskService
from packages.worker_health.src.liveness_reporter import LivenessReporter

logger = logging.getLogger(__name__)


def build_services(
    session_factory: async_sessionmaker[AsyncSession],
) -> tuple[TaskService, ResultService]:
    """Fresh `TaskService`/`ResultService`, each backed by its own `AsyncTransactionManager`.

    `AsyncTransactionManager` keeps the active session/repositories as mutable attributes on
    itself (set in `__aenter__`), not per-call-local state — safe to reuse *sequentially*, but
    two coroutines entering the same instance's `async with` block concurrently race on that
    shared state (one can `commit()` while another is still mid-query on the same
    `AsyncSession`), surfacing as `InvalidRequestError`/`IllegalStateChangeError` from
    SQLAlchemy and crashing the whole process. `apps/worker_parser` runs several `Task`s and,
    within a `Task`, several `TaskItem`s concurrently (see AGENTS.md, "Модель конкурентности"),
    so every independently-scheduled coroutine (each claimed task, its heartbeat loop, each
    concurrently processed item) must call this to get its own instances rather than share ones
    handed down by its caller. `apps/api` doesn't need this helper — its DI container already
    hands out a fresh `AsyncTransactionManager` per request (`providers.Factory`)."""

    return (
        TaskService(transaction_manager=AsyncTransactionManager(session_factory=session_factory)),
        ResultService(transaction_manager=AsyncTransactionManager(session_factory=session_factory)),
    )

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
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> SessionMessage:
    while True:
        session_message = await session_client.acquire_session(
            marketplace=marketplace,
            max_pop_attempts=config.SESSION_POOL.MAX_POP_ATTEMPTS,
            min_ttl_margin_seconds=config.SESSION_POOL.MIN_TTL_MARGIN_SECONDS,
        )
        if session_message is not None:
            return session_message
        liveness_reporter.set_status(WorkerParserStatus.WAITING_FOR_SESSION.value)
        await asyncio.sleep(config.SESSION_POOL.EMPTY_POOL_BACKOFF_SECONDS)


async def _release_session(
    session_message: SessionMessage | None,
    session_client: SessionPoolStore,
) -> None:
    """Hands a still-trusted session back to the pool for the next item/task to pick up, instead
    of letting whatever request budget it has left go to waste. Callers must only pass a session
    that didn't just fail with a block/error whose retry policy is `REINIT_SESSION` — this
    doesn't re-validate anything itself, it trusts the caller's judgment (see
    `SessionPoolStore.release`)."""
    if session_message is None:
        return
    await session_client.release(
        session_message, min_ttl_margin_seconds=config.SESSION_POOL.MIN_TTL_MARGIN_SECONDS,
    )


async def handle_product_page_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    fetch_product_page = _PRODUCT_PAGE_FETCHERS[task.marketplace]
    create_http_session = _HTTP_SESSION_FACTORY_BY_MARKETPLACE[task.marketplace]

    session_message: SessionMessage | None = None
    attempt_count = 0
    payload: BaseModel | None = None

    while payload is None:
        if session_message is None:
            session_message = await acquire_session_or_wait(
                task.marketplace, session_client, liveness_reporter,
            )
        liveness_reporter.set_status(WorkerParserStatus.WORKING.value)
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
                if policy.session_action == SessionAction.KEEP:
                    await _release_session(session_message, session_client)
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
    await _release_session(session_message, session_client)


async def handle_listing_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: SessionPoolStore,
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
            session_message = await acquire_session_or_wait(
                task.marketplace, session_client, liveness_reporter,
            )
        liveness_reporter.set_status(WorkerParserStatus.WORKING.value)
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
                if policy.session_action == SessionAction.KEEP:
                    await _release_session(session_message, session_client)
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
                await _release_session(session_message, session_client)
                return

    session_still_trusted = True
    if task.parse_type == ParseType.SELLER:
        session_still_trusted = await _record_seller_profile(
            task, item, session_message, result_service, session_client, liveness_reporter,
        )

    await task_service.complete_item(item_id=item.id, status=TaskItemStatus.SUCCEEDED)
    if session_still_trusted:
        await _release_session(session_message, session_client)


async def _record_seller_profile(
    task: TaskEntity,
    item: TaskItemEntity,
    session_message: SessionMessage | None,
    result_service: ResultService,
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> bool:
    """Returns whether `session_message` is still trustworthy enough to hand back to the pool
    afterward — this function doesn't retry on failure (unlike the retry-policy-driven handlers),
    so a `ParserError` here means we don't actually know whether the session died or the data was
    just off; treated as untrusted either way, matching the conservative default elsewhere."""
    fetch_seller_profile = _SELLER_PROFILE_FETCHERS[task.marketplace]
    create_http_session = _HTTP_SESSION_FACTORY_BY_MARKETPLACE[task.marketplace]
    if session_message is None:
        session_message = await acquire_session_or_wait(
            task.marketplace, session_client, liveness_reporter,
        )
    http_session = create_http_session(session_message)
    try:
        profile = await fetch_seller_profile(item.input_value, http_session, session_message)
    except ParserError as error:
        logger.warning(
            '[seller_profile] failed to fetch profile for %s: %s', item.input_value, error,
        )
        return False
    await result_service.record_results(
        task_item_id=item.id,
        marketplace=task.marketplace,
        parse_type=task.parse_type,
        payloads=[profile],
    )
    return True


async def handle_reviews_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    if task.marketplace == Marketplace.OZON:
        await _handle_ozon_reviews(
            task, item, task_service, result_service, session_client, liveness_reporter,
        )
    else:
        await _handle_wb_reviews(
            task, item, task_service, result_service, session_client, liveness_reporter,
        )


async def _handle_ozon_reviews(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    cursor = OzonReviewCursor.model_validate(item.cursor) if item.cursor else None
    seen_uuids: set[str] = set(cursor.seen_uuids) if cursor else set()
    result_count = item.result_count or 0
    session_message: SessionMessage | None = None
    attempt_count = 0

    while True:
        if session_message is None:
            session_message = await acquire_session_or_wait(
                task.marketplace, session_client, liveness_reporter,
            )
        liveness_reporter.set_status(WorkerParserStatus.WORKING.value)
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
                if policy.session_action == SessionAction.KEEP:
                    await _release_session(session_message, session_client)
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
    await _release_session(session_message, session_client)


async def _handle_wb_reviews(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    session_message: SessionMessage | None = None
    attempt_count = 0
    reviews: list[BaseModel] | None = None

    while reviews is None:
        if session_message is None:
            session_message = await acquire_session_or_wait(
                task.marketplace, session_client, liveness_reporter,
            )
        liveness_reporter.set_status(WorkerParserStatus.WORKING.value)
        http_session = create_wb_http_session(session_message)
        try:
            reviews = await wb_fetchers.fetch_wb_review_page(
                item.input_value, http_session, session_message,
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
                if policy.session_action == SessionAction.KEEP:
                    await _release_session(session_message, session_client)
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
    await task_service.record_item_progress(
        item_id=item.id, cursor=None, result_count=len(reviews),
    )
    await task_service.complete_item(item_id=item.id, status=TaskItemStatus.SUCCEEDED)
    await _release_session(session_message, session_client)


async def process_task_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    if task.parse_type == ParseType.PRODUCT_PAGE:
        await handle_product_page_item(
            task, item, task_service, result_service, session_client, liveness_reporter,
        )
    elif task.parse_type == ParseType.REVIEWS:
        await handle_reviews_item(
            task, item, task_service, result_service, session_client, liveness_reporter,
        )
    else:
        await handle_listing_item(
            task, item, task_service, result_service, session_client, liveness_reporter,
        )


async def process_claimed_task(
    task: TaskEntity,
    session_factory: async_sessionmaker[AsyncSession],
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    """Pending `TaskItem`s of this task run concurrently, up to
    `POLL_MAX_CONCURRENT_ITEMS_PER_TASK`. Each item re-checks the task's status itself right
    before starting (not just once up front) — a pause/cancel that lands mid-run stops items that
    haven't started yet, while ones already in flight are left to finish rather than aborted
    mid-page. `TaskService.complete_item` locks the parent Task row to serialize concurrently
    completing siblings (see there) — required for the parent Task to reliably reach its terminal
    status once every item is done."""

    own_task_service, _ = build_services(session_factory)
    items = await own_task_service.get_task_items(task_id=task.id)
    pending_items = [item for item in items if item.status not in TERMINAL_ITEM_STATUSES]
    semaphore = asyncio.Semaphore(config.POLL.MAX_CONCURRENT_ITEMS_PER_TASK)

    async def run_item(item: TaskItemEntity) -> None:
        # Own TaskService/ResultService per concurrently-gathered item — sharing one across
        # gathered coroutines races on AsyncTransactionManager's shared session state (see
        # build_services docstring) and crashes the process.
        item_task_service, item_result_service = build_services(session_factory)
        async with semaphore:
            refreshed_task = await item_task_service.get_task_by_id(task_id=task.id)
            if refreshed_task.status != TaskStatus.RUNNING:
                return
            await process_task_item(
                task, item, item_task_service, item_result_service,
                session_client, liveness_reporter,
            )

    await asyncio.gather(*(run_item(item) for item in pending_items))


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
            await task_service.heartbeat(
                task_id=task_id, worker_id=worker_id, lease_duration=lease_duration,
            )


async def run_claimed_task(
    task: TaskEntity,
    lease_duration: timedelta,
    session_factory: async_sessionmaker[AsyncSession],
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    # Own TaskService for the heartbeat loop — it runs concurrently with process_claimed_task
    # below for the whole lifetime of this task, so it can't share build_services() output with
    # it (see build_services docstring).
    heartbeat_task_service, _ = build_services(session_factory)
    stop_event = asyncio.Event()
    heartbeat_task = asyncio.create_task(
        run_lease_heartbeat_loop(
            task_id=task.id,
            worker_id=config.POLL.WORKER_ID,
            lease_duration=lease_duration,
            interval_seconds=config.POLL.HEARTBEAT_INTERVAL_SECONDS,
            task_service=heartbeat_task_service,
            stop_event=stop_event,
        ),
    )
    try:
        await process_claimed_task(
            task, session_factory, session_client, liveness_reporter,
        )
    except Exception:
        logger.exception('[task_processing_failed] task_id=%s', task.id)
    finally:
        stop_event.set()
        await heartbeat_task


async def run_poll_loop(
    session_factory: async_sessionmaker[AsyncSession],
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    """Up to `POLL_MAX_CONCURRENT_TASKS` claimed tasks run as independent asyncio tasks in this
    single process. `claim_next`/`acquire_session` are safe to call concurrently (row-level
    locking / atomic Redis ops respectively — see AGENTS.md), so this is plain fan-out, not a
    worker pool with its own scheduling. `liveness_reporter`'s status is process-wide, not
    per-task: WORKING means "at least one task is running", not "N of M slots busy".

    `task_service` here is this loop's own instance, used only for its own sequential
    `claim_next` calls — each spawned `run_claimed_task` gets a fresh one via `session_factory`
    instead of sharing this one (see `build_services` docstring)."""

    task_service, _ = build_services(session_factory)
    lease_duration = timedelta(seconds=config.POLL.LEASE_DURATION_SECONDS)
    running_tasks: set[asyncio.Task] = set()

    while True:
        if len(running_tasks) < config.POLL.MAX_CONCURRENT_TASKS:
            task = await task_service.claim_next(
                worker_id=config.POLL.WORKER_ID, lease_duration=lease_duration,
            )
            if task is not None:
                liveness_reporter.set_status(WorkerParserStatus.WORKING.value)
                worker_task = asyncio.create_task(
                    run_claimed_task(
                        task, lease_duration, session_factory,
                        session_client, liveness_reporter,
                    ),
                )
                running_tasks.add(worker_task)
                worker_task.add_done_callback(running_tasks.discard)
                continue

        if not running_tasks:
            liveness_reporter.set_status(WorkerParserStatus.READY.value)
            await asyncio.sleep(config.POLL.INTERVAL_SECONDS)
        elif len(running_tasks) >= config.POLL.MAX_CONCURRENT_TASKS:
            await asyncio.wait(running_tasks, return_when=asyncio.FIRST_COMPLETED)
        else:
            await asyncio.sleep(config.POLL.INTERVAL_SECONDS)


async def run_main() -> None:
    _, session_factory = get_database_connection(config=config)
    session_client = SessionPoolStore(redis_config=config.REDIS)
    liveness_reporter = LivenessReporter(config=config.LIVENESS)

    try:
        await asyncio.gather(
            run_poll_loop(session_factory, session_client, liveness_reporter),
            liveness_reporter.run(),
        )
    finally:
        await session_client.close()
