import asyncio
import logging
from datetime import timedelta
from functools import partial
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import OzonReviewCursor
from apps.worker_parser.src.enums import WorkerParserStatus
from apps.worker_parser.src.exceptions import ParserError
from apps.worker_parser.src.execution import ExecutionOptions, FetchFailedError, PageExecutor
from apps.worker_parser.src.registry import OPERATIONS, SELLER_PROFILE_FETCHERS, PageOperation
from apps.worker_parser.src.services import build_services
from apps.worker_parser.src.session_provider import PoolSessionProvider
from packages.result.src.service import ResultService
from packages.sessions.src.redis_store import SessionPoolStore
from packages.task.src.entities import TaskEntity, TaskItemEntity
from packages.task.src.enums import ParseType, TaskItemStatus, TaskStatus
from packages.task.src.service import TERMINAL_ITEM_STATUSES, TaskService
from packages.worker_health.src.liveness_reporter import LivenessReporter

logger = logging.getLogger(__name__)

# Лимит результатов задачи (`result_limit`) применяется к спискам и отзывам; карточка товара всегда
# одна, лимит к ней не относится.
LIMITED_PARSE_TYPES = frozenset({
    ParseType.SEARCH_QUERY, ParseType.CATEGORY, ParseType.SELLER, ParseType.REVIEWS,
})


def restore_cursor(operation: PageOperation, raw_cursor: dict | None) -> BaseModel | None:
    if operation.cursor_model is None or not raw_cursor:
        return None
    return operation.cursor_model.model_validate(raw_cursor)


def initial_seen_keys(cursor: BaseModel | None) -> set[str]:
    """Дедупликация страниц одного элемента живёт в памяти; у отзывов Ozon она ещё и в курсоре —
    без неё дедуп между сортировками потерялся бы при возобновлении."""
    if isinstance(cursor, OzonReviewCursor):
        return set(cursor.seen_uuids)
    return set()


async def record_seller_profile(
    task: TaskEntity,
    item: TaskItemEntity,
    executor: PageExecutor,
    result_service: ResultService,
) -> None:
    """Без ретраев: `ParserError` здесь только логируется (элемент всё равно завершится успешно),
    а executor при этом выбрасывает сессию как ненадёжную."""
    fetch_seller_profile = SELLER_PROFILE_FETCHERS[task.marketplace]
    try:
        profile = await executor.run(partial(fetch_seller_profile, item.input_value), retry=False)
    except ParserError as error:
        logger.warning(
            '[seller_profile] failed to fetch profile for %s: %s', item.input_value, error,
        )
        return
    await result_service.record_results(
        task_item_id=item.id,
        marketplace=task.marketplace,
        parse_type=task.parse_type,
        payloads=[profile],
    )


async def process_item_pages(
    task: TaskEntity,
    item: TaskItemEntity,
    executor: PageExecutor,
    task_service: TaskService,
    result_service: ResultService,
) -> None:
    operation = OPERATIONS[(task.marketplace, task.parse_type)]
    limit_applies = task.parse_type in LIMITED_PARSE_TYPES

    cursor = restore_cursor(operation, item.cursor)
    seen_keys = initial_seen_keys(cursor)
    result_count = item.result_count or 0
    pages_since_status_check = 0

    while True:
        remaining_limit = (
            task.result_limit - result_count
            if limit_applies and task.result_limit is not None
            else None
        )
        try:
            page = await executor.fetch_page(
                operation, item.input_value, cursor, seen_keys, remaining_limit,
            )
        except FetchFailedError as failure:
            await task_service.complete_item(
                item_id=item.id,
                status=failure.classification.policy.resulting_item_status_on_exhaustion,
                error_reason=str(failure.cause),
            )
            return

        # Списочные fetcher'ы режут страницу по `ctx.limit` сами, отзывные (Ozon/WB) отдают её
        # целиком — поэтому обрезаем здесь, чтобы лимит держался для любого типа.
        items = page.items if remaining_limit is None else page.items[:remaining_limit]
        if items:
            await result_service.record_results(
                task_item_id=item.id,
                marketplace=task.marketplace,
                parse_type=task.parse_type,
                payloads=list(items),
            )
        result_count += len(items)
        cursor = page.next_cursor
        await task_service.record_item_progress(
            item_id=item.id,
            cursor=cursor.model_dump(mode='json') if cursor else None,
            result_count=result_count,
        )

        if cursor is None:
            break
        if remaining_limit is not None and remaining_limit - len(items) <= 0:
            break

        pages_since_status_check += 1
        if pages_since_status_check >= config.POLL.STATUS_CHECK_INTERVAL_PAGES:
            pages_since_status_check = 0
            refreshed_task = await task_service.get_task_by_id(task_id=task.id)
            if refreshed_task.status != TaskStatus.RUNNING:
                return

    if task.parse_type == ParseType.SELLER:
        await record_seller_profile(task, item, executor, result_service)
    await task_service.complete_item(item_id=item.id, status=TaskItemStatus.SUCCEEDED)


async def handle_task_item(
    task: TaskEntity,
    item: TaskItemEntity,
    task_service: TaskService,
    result_service: ResultService,
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
) -> None:
    provider = PoolSessionProvider(
        marketplace=task.marketplace,
        session_client=session_client,
        liveness_reporter=liveness_reporter,
    )
    executor = PageExecutor(provider, ExecutionOptions(walk_all_review_sorts=True))
    try:
        await process_item_pages(task, item, executor, task_service, result_service)
    except BaseException:
        # Неожиданный сбой (БД, баг) — не знаем, в порядке ли сессия, поэтому в пул не
        # возвращаем: консервативно, как и было.
        await executor.discard_session()
        raise
    await executor.close()


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

    await asyncio.gather(*(
        run_item(task, item, session_factory, session_client, liveness_reporter, semaphore)
        for item in pending_items
    ))


async def run_item(
    task: TaskEntity,
    item: TaskItemEntity,
    session_factory: async_sessionmaker[AsyncSession],
    session_client: SessionPoolStore,
    liveness_reporter: LivenessReporter,
    semaphore: asyncio.Semaphore,
) -> None:
    # Own TaskService/ResultService per concurrently-gathered item — sharing one across
    # gathered coroutines races on AsyncTransactionManager's shared session state (see
    # build_services docstring) and crashes the process.
    item_task_service, item_result_service = build_services(session_factory)
    async with semaphore:
        refreshed_task = await item_task_service.get_task_by_id(task_id=task.id)
        if refreshed_task.status != TaskStatus.RUNNING:
            return
        await handle_task_item(
            task, item, item_task_service, item_result_service, session_client, liveness_reporter,
        )


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
        await process_claimed_task(task, session_factory, session_client, liveness_reporter)
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
                        task, lease_duration, session_factory, session_client, liveness_reporter,
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
