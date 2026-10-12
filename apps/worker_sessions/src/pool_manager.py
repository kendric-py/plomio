import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from apps.worker_sessions.src.config import config
from apps.worker_sessions.src.entities import ProxyConfig, SessionMessage
from apps.worker_sessions.src.enums import WorkerSessionsStatus
from apps.worker_sessions.src.exceptions import BrowserInitError, JsRuntimeError
from apps.worker_sessions.src.generation.marketplaces.registry import build_session
from apps.worker_sessions.src.generation.process_reaper import run_process_reaper
from apps.worker_sessions.src.generation.validation import find_validation_error
from apps.worker_sessions.src.proxy.client import ProxyRotator
from core.enums import Marketplace
from packages.sessions.src.errors import SessionErrorKind
from packages.sessions.src.redis_store import SessionPoolStore
from packages.worker_health.src.liveness_reporter import LivenessReporter

logger = logging.getLogger(__name__)


def _build_and_validate(
    marketplace: Marketplace, proxy: ProxyConfig | None,
) -> tuple[SessionErrorKind | None, SessionMessage]:
    """Runs on a worker thread: blocking Camoufox init + blocking curl_cffi validation
    request. Returns why the session failed validation (`None` — it passed), and the session."""
    session_message = build_session(marketplace=marketplace, proxy=proxy)
    return find_validation_error(session_message=session_message), session_message


async def _record_error(
    store: SessionPoolStore, marketplace: Marketplace, kind: SessionErrorKind,
) -> None:
    """Статистика ошибок — вспомогательная: её сбой не должен ломать цикл генерации."""
    try:
        await store.record_error(marketplace=marketplace, kind=kind)
    except Exception:
        logger.exception('[record_error_failed] marketplace=%s kind=%s', marketplace, kind)


async def _generator_worker(
    marketplace: Marketplace,
    executor: ThreadPoolExecutor,
    store: SessionPoolStore,
    liveness: LivenessReporter,
    worker_tag: str,
) -> None:
    loop = asyncio.get_running_loop()
    rotator = ProxyRotator(max_sessions=config.GENERATION.MAX_SESSIONS_PER_PROXY)

    while True:
        try:
            depth = await store.live_count(marketplace=marketplace)
            if depth >= config.GENERATION.TARGET_POOL_DEPTH:
                await asyncio.sleep(config.GENERATION.POOL_FULL_RECHECK_DELAY_SECONDS)
                continue

            proxy: ProxyConfig | None = None
            if config.GENERATION.REQUIRE_PROXY:
                liveness.set_status(status=WorkerSessionsStatus.WAITING_FOR_PROXY.value)
                proxy = await rotator.acquire()
                if proxy is None:
                    await _record_error(
                        store=store, marketplace=marketplace,
                        kind=SessionErrorKind.PROXY_UNAVAILABLE,
                    )
                    logger.warning(
                        '[proxy_unavailable] %s no proxy available, retrying soon', worker_tag,
                    )
                    await asyncio.sleep(config.GENERATION.NO_PROXY_RETRY_DELAY_SECONDS)
                    continue

            liveness.set_status(status=WorkerSessionsStatus.GENERATING.value)
            validation_error, session_message = await loop.run_in_executor(
                executor, _build_and_validate, marketplace, proxy,
            )
            if validation_error is None:
                await store.save(
                    session_message=session_message,
                    ttl_ms=config.GENERATION.TTL_MS,
                    stream_prefix=config.SESSIONS_STREAM.PREFIX,
                    stream_maxlen=config.SESSIONS_STREAM.MAXLEN,
                )
            else:
                await _record_error(
                    store=store, marketplace=marketplace, kind=validation_error,
                )
                logger.warning(
                    '[session_dropped] %s marketplace=%s session_id=%s — failed validation',
                    worker_tag, marketplace, session_message.session_id,
                )
            liveness.set_status(status=WorkerSessionsStatus.READY.value)
        except BrowserInitError as exc:
            await _record_error(
                store=store, marketplace=marketplace, kind=SessionErrorKind.ANTIBOT_INIT,
            )
            logger.error('[browser_init_failed] %s error=%s', worker_tag, exc)
            liveness.set_status(status=WorkerSessionsStatus.READY.value)
        except Exception as exc:
            kind = (
                SessionErrorKind.ANTIBOT_INIT
                if isinstance(exc, JsRuntimeError) else SessionErrorKind.OTHER
            )
            await _record_error(store=store, marketplace=marketplace, kind=kind)
            logger.exception('[generator_worker_error] %s', worker_tag)
            liveness.set_status(status=WorkerSessionsStatus.READY.value)
            await asyncio.sleep(5)


async def run_pool_manager() -> None:
    if not config.GENERATION.REQUIRE_PROXY:
        logger.warning(
            '[dev_mode] GENERATION_REQUIRE_PROXY=false — generating sessions over a direct '
            'connection, no proxy. Marketplaces will ban this IP quickly; never use in prod.',
        )
    store = SessionPoolStore(redis_config=config.REDIS)
    liveness = LivenessReporter(config=config.LIVENESS)
    executor = ThreadPoolExecutor(
        max_workers=config.GENERATION.CONCURRENCY_PER_MARKETPLACE * len(Marketplace),
    )

    workers = [
        _generator_worker(
            marketplace=marketplace,
            executor=executor,
            store=store,
            liveness=liveness,
            worker_tag=f'{marketplace.value}-{index}',
        )
        for marketplace in Marketplace
        for index in range(config.GENERATION.CONCURRENCY_PER_MARKETPLACE)
    ]
    workers.append(run_process_reaper())
    workers.append(liveness.run())
    logger.info(
        '[service_ready] %d generator workers across %d marketplaces',
        len(workers) - 2, len(Marketplace),
    )
    try:
        await asyncio.gather(*workers)
    finally:
        await store.close()
