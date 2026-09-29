import asyncio
import logging
import time
from urllib.parse import urlparse

from pydantic import ValidationError

from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import Cursor, Page
from apps.worker_parser.src.enums import ErrorOutcome, WorkerParserStatus
from apps.worker_parser.src.exceptions import InputResolutionError
from apps.worker_parser.src.execution import (
    ExecutionOptions,
    ExecutionStats,
    FetchFailedError,
    PageExecutor,
)
from apps.worker_parser.src.hot_session import HotSessionSlot
from apps.worker_parser.src.marketplaces.ozon.utils import extract_ozon_product_id_from_path
from apps.worker_parser.src.registry import OPERATIONS, PageOperation
from core.enums import Marketplace
from packages.direct.src.entities import DirectReply, DirectRequest
from packages.direct.src.enums import DirectRequestType, DirectStatus
from packages.direct.src.redis_bus import DirectBus
from packages.sessions.src.redis_store import SessionPoolStore
from packages.task.src.enums import ParseType
from packages.worker_health.src.liveness_reporter import LivenessReporter

logger = logging.getLogger(__name__)

PARSE_TYPE_BY_REQUEST_TYPE = {
    DirectRequestType.PRODUCT_PAGE: ParseType.PRODUCT_PAGE,
    DirectRequestType.REVIEWS: ParseType.REVIEWS,
    DirectRequestType.SEARCH: ParseType.SEARCH_QUERY,
    DirectRequestType.CATEGORY: ParseType.CATEGORY,
    DirectRequestType.SELLER: ParseType.SELLER,
}

# Числовой артикул → ссылка на карточку. Ozon принимает путь только с артикулом (проверено).
PRODUCT_URL_BY_MARKETPLACE = {
    Marketplace.WILDBERRIES: 'https://www.wildberries.ru/catalog/{article}/detail.aspx',
    Marketplace.OZON: 'https://www.ozon.ru/product/{article}/',
}

# Ссылку воркер запрашивает своей сессией (куки маркетплейса), поэтому принимаются только ссылки
# самого маркетплейса: иначе клиент мог бы направить запрос с чужой сессией на произвольный хост.
HOSTS_BY_MARKETPLACE = {
    Marketplace.WILDBERRIES: frozenset({'www.wildberries.ru', 'wildberries.ru'}),
    Marketplace.OZON: frozenset({'www.ozon.ru', 'ozon.ru'}),
}

# Числовой id продавца → ссылка на его витрину; у Ozon ссылка требует «слаг», по одному id её не
# построить — там принимается только ссылка.
SELLER_URL_BY_MARKETPLACE = {
    Marketplace.WILDBERRIES: 'https://www.wildberries.ru/seller/{seller_id}',
}

STATUS_BY_OUTCOME = {
    ErrorOutcome.INVALID_INPUT: DirectStatus.INVALID_INPUT,
    ErrorOutcome.NOT_FOUND: DirectStatus.NOT_FOUND,
    ErrorOutcome.UNAVAILABLE: DirectStatus.UNAVAILABLE,
    ErrorOutcome.ERROR: DirectStatus.ERROR,
}

REASON_LOG_LIMIT = 300


def resolve_marketplace_url(request: DirectRequest, value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {'http', 'https'} or parsed.hostname not in (
        HOSTS_BY_MARKETPLACE[request.marketplace]
    ):
        raise InputResolutionError(f'not a {request.marketplace.value} link: {value[:80]!r}')
    return value


def resolve_input_value(request: DirectRequest) -> str:
    """Поиск принимает текст как есть; остальные типы — артикул/id или ссылку самого маркетплейса.
    Всё, что не разбирается, — `invalid_input`."""
    value = request.input_value.strip()
    if request.request_type == DirectRequestType.SEARCH:
        return value
    if request.request_type == DirectRequestType.CATEGORY:
        return resolve_marketplace_url(request, value)
    if request.request_type == DirectRequestType.SELLER:
        return resolve_seller_input(request, value)
    if value.isdigit():
        return PRODUCT_URL_BY_MARKETPLACE[request.marketplace].format(article=value)
    value = resolve_marketplace_url(request, value)
    if (
        request.marketplace == Marketplace.OZON
        and extract_ozon_product_id_from_path(urlparse(value).path.rstrip('/') + '/') == 'unknown'
    ):
        raise InputResolutionError('cannot extract article from the link')
    return value


def resolve_seller_input(request: DirectRequest, value: str) -> str:
    if value.isdigit():
        template = SELLER_URL_BY_MARKETPLACE.get(request.marketplace)
        if template is None:
            raise InputResolutionError('seller id alone is not enough, a link is required')
        return template.format(seller_id=value)
    return resolve_marketplace_url(request, value)


def restore_cursor(operation: PageOperation, raw_cursor: dict | None) -> Cursor | None:
    if operation.cursor_model is None or not raw_cursor:
        return None
    try:
        return operation.cursor_model.model_validate(raw_cursor)
    except ValidationError as error:
        raise InputResolutionError('cursor does not match the request type') from error


def build_ok_reply(request: DirectRequest, page: Page) -> DirectReply:
    items = [item.model_dump(mode='json') for item in page.items]
    if request.request_type == DirectRequestType.PRODUCT_PAGE:
        payload = items[0] if items else None
    else:
        payload = {'items': items}
    # Пустая страница — всегда конец выдачи, даже если маркетплейс отдал ссылку дальше (обход
    # сортировок отзывов Ozon, «полная» последняя страница WB): иначе клиент листал бы пустоту.
    has_next = page.next_cursor is not None and bool(page.items)
    return DirectReply(
        request_id=request.request_id,
        status=DirectStatus.OK,
        payload=payload,
        next_cursor=page.next_cursor.model_dump(mode='json') if has_next else None,
    )


async def execute_direct_request(request: DirectRequest, executor: PageExecutor) -> DirectReply:
    """Разбор входа и курсора → общий цикл ядра → ответ. Все исходы, кроме неожиданных
    исключений, — статусы; неожиданные ловит вызывающий."""
    operation = OPERATIONS[(request.marketplace, PARSE_TYPE_BY_REQUEST_TYPE[request.request_type])]
    try:
        input_value = resolve_input_value(request)
        cursor = restore_cursor(operation, request.page_cursor)
        page = await executor.fetch_page(operation, input_value, cursor, set(), None)
    except InputResolutionError as error:
        return DirectReply(
            request_id=request.request_id, status=DirectStatus.INVALID_INPUT, error=str(error),
        )
    except FetchFailedError as failure:
        return DirectReply(
            request_id=request.request_id,
            status=STATUS_BY_OUTCOME[failure.classification.outcome],
            error=str(failure.cause),
        )
    except BaseException:
        # Неожиданный сбой — не знаем, в порядке ли сессия, в слот её не возвращаем.
        await executor.discard_session()
        raise
    await executor.close()
    return build_ok_reply(request, page)


async def handle_direct_request(
    request: DirectRequest,
    bus: DirectBus,
    hot_slot: HotSessionSlot,
) -> None:
    taken_at = time.time()
    worker_started = time.monotonic()
    remaining = request.deadline_at - taken_at
    if remaining <= 0:
        logger.info('[direct_expired] request_id=%s', request.request_id)
        return

    executor = PageExecutor(
        hot_slot,
        ExecutionOptions(
            max_attempts=config.DIRECT.MAX_ATTEMPTS,
            deadline=worker_started + remaining,
            review_page_size=config.DIRECT.REVIEWS_WB_PAGE_SIZE,
        ),
    )
    try:
        reply = await execute_direct_request(request, executor)
    except Exception as error:
        logger.exception('[direct_internal_error] request_id=%s', request.request_id)
        reply = DirectReply(
            request_id=request.request_id,
            status=DirectStatus.ERROR,
            error=f'internal error: {type(error).__name__}',
        )
    await bus.publish_reply(reply)
    log_request_done(request, reply, executor.stats, taken_at, worker_started)


def log_request_done(
    request: DirectRequest,
    reply: DirectReply,
    stats: ExecutionStats,
    taken_at: float,
    worker_started: float,
) -> None:
    logger.info(
        '[direct_done] request_id=%s marketplace=%s status=%s attempts=%d queue_ms=%d '
        'session_ms=%d fetch_ms=%d worker_ms=%d since_created_ms=%d',
        request.request_id,
        request.marketplace.value,
        reply.status.value,
        stats.attempts,
        (taken_at - request.created_at) * 1000,
        stats.session_seconds * 1000,
        stats.fetch_seconds * 1000,
        (time.monotonic() - worker_started) * 1000,
        (time.time() - request.created_at) * 1000,
    )
    if reply.status != DirectStatus.OK:
        logger.warning(
            '[direct_failed] request_id=%s marketplace=%s status=%s reason=%s',
            request.request_id,
            request.marketplace.value,
            reply.status.value,
            (reply.error or '')[:REASON_LOG_LIMIT],
        )


def resolve_marketplaces() -> list[Marketplace]:
    names = [name.strip() for name in config.DIRECT.MARKETPLACES.split(',') if name.strip()]
    return [Marketplace(name) for name in names] if names else list(Marketplace)


async def run_direct_loop(
    bus: DirectBus,
    hot_slots: dict[Marketplace, HotSessionSlot],
    liveness_reporter: LivenessReporter,
) -> None:
    """Свободных слотов = `MAX_CONCURRENT_REQUESTS - running`: если ноль — ждём завершения хотя бы
    одного запроса, иначе читаем ровно столько, сколько можем взять (`XREADGROUP BLOCK`, без
    поллинга). Каждый запрос — отдельная `asyncio.Task`."""
    marketplaces = list(hot_slots)
    await bus.ensure_groups(marketplaces)
    await asyncio.gather(*(slot.warm_up() for slot in hot_slots.values()))
    running: set[asyncio.Task] = set()

    while True:
        free_slots = config.DIRECT.MAX_CONCURRENT_REQUESTS - len(running)
        if free_slots <= 0:
            await asyncio.wait(running, return_when=asyncio.FIRST_COMPLETED)
            continue
        requests = await bus.consume(
            marketplaces,
            consumer_name=config.DIRECT.CONSUMER_NAME,
            count=free_slots,
            block_ms=config.DIRECT.BLOCK_MS,
        )
        for request in requests:
            task = asyncio.create_task(
                handle_direct_request(request, bus, hot_slots[request.marketplace]),
            )
            running.add(task)
            task.add_done_callback(running.discard)
        status = WorkerParserStatus.WORKING if running else WorkerParserStatus.READY
        liveness_reporter.set_status(status.value)


async def run_direct_main(liveness_reporter: LivenessReporter) -> None:
    session_client = SessionPoolStore(redis_config=config.REDIS)
    bus = DirectBus(redis_config=config.REDIS)
    hot_slots = {
        marketplace: HotSessionSlot(marketplace, session_client)
        for marketplace in resolve_marketplaces()
    }
    try:
        await asyncio.gather(
            run_direct_loop(bus, hot_slots, liveness_reporter),
            liveness_reporter.run(),
        )
    finally:
        for slot in hot_slots.values():
            await slot.close()
        await bus.close()
        await session_client.close()
