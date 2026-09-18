import logging

import redis.asyncio as redis

from apps.worker_parser.src.config import config
from apps.worker_parser.src.entities import SessionMessage
from core.enums import Marketplace

logger = logging.getLogger(__name__)


def _session_key(marketplace: Marketplace, session_id: str) -> str:
    return f'session:{marketplace.value}:{session_id}'


def _pool_key(marketplace: Marketplace) -> str:
    return f'sessions:pool:{marketplace.value}'


class RedisSessionClient:
    """Consumes sessions written by apps/worker_sessions' RedisSessionStore, via
    `ZPOPMIN sessions:pool:{marketplace}` — chosen over `XREADGROUP` on the sessions stream
    because ZPOPMIN gives atomic single-consumer semantics for free (no consumer-group
    bookkeeping), and the stream carries no TTL of its own, so a stream-based consumer would
    still need the same GET-based freshness check this client already does. See
    apps/worker_parser/AGENTS.md for the full comparison."""

    def __init__(self) -> None:
        self._client = redis.Redis(
            host=config.REDIS.HOST,
            port=config.REDIS.PORT,
            db=config.REDIS.DB,
            password=config.REDIS.PASSWORD,
        )

    async def acquire_session(self, marketplace: Marketplace) -> SessionMessage | None:
        pool_key = _pool_key(marketplace=marketplace)
        for _ in range(config.SESSION_POOL.MAX_POP_ATTEMPTS):
            popped = await self._client.zpopmin(pool_key, count=1)
            if not popped:
                return None

            session_id = popped[0][0].decode('utf-8')
            session_key = _session_key(marketplace=marketplace, session_id=session_id)
            remaining_ttl_ms = await self._client.pttl(session_key)
            if remaining_ttl_ms is None or remaining_ttl_ms < 0:
                logger.warning(
                    '[session_expired] marketplace=%s session_id=%s',
                    marketplace.value, session_id,
                )
                continue
            if remaining_ttl_ms / 1000 < config.SESSION_POOL.MIN_TTL_MARGIN_SECONDS:
                logger.warning(
                    '[session_ttl_too_thin] marketplace=%s session_id=%s remaining_ms=%d',
                    marketplace.value, session_id, remaining_ttl_ms,
                )
                continue

            raw_session = await self._client.get(session_key)
            if raw_session is None:
                logger.warning(
                    '[session_missing] marketplace=%s session_id=%s',
                    marketplace.value, session_id,
                )
                continue
            return SessionMessage.model_validate_json(raw_session)
        return None

    async def close(self) -> None:
        await self._client.aclose()
