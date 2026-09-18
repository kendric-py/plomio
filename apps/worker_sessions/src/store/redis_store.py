import logging
import time

import redis.asyncio as redis

from apps.worker_sessions.src.config import config
from apps.worker_sessions.src.entities import SessionMessage
from core.enums import Marketplace

logger = logging.getLogger(__name__)


def _session_key(marketplace: Marketplace, session_id: str) -> str:
    return f'session:{marketplace.value}:{session_id}'


def _pool_key(marketplace: Marketplace) -> str:
    return f'sessions:pool:{marketplace.value}'


def _stream_key(marketplace: Marketplace) -> str:
    return f'{config.SESSIONS_STREAM.PREFIX}:{marketplace.value}'


class RedisSessionStore:
    """Session pool backed by Redis: `HSET session:{marketplace}:{id}` holds the serialized
    session with a matching `PEXPIRE`, so a session simply disappears on its own TTL — no
    separate reaping step, unlike a broker that only discards an expired message once it's
    actually delivered. `ZADD sessions:pool:{marketplace}` (scored by expire_at) tracks the
    pool for depth accounting; `live_count` reads that score range directly instead of
    trusting a broker's own queue-depth reporting, which can go stale while idle.

    `save` additionally publishes to a per-marketplace Redis Stream (`{PREFIX}:{marketplace}`,
    see `SessionsStreamConfig`) — a separate, explicitly-named channel so a future consumer
    (e.g. worker_parser) can react to new sessions without polling, and so this doesn't share
    a key namespace with whatever else ends up on the same Redis instance. The stream is
    additive: it does not replace the TTL'd HSET/ZSET pool above, which stays the source of
    truth for whether a session is actually still valid (stream entries carry no TTL of their
    own — see MAXLEN capping in SessionsStreamConfig)."""

    def __init__(self) -> None:
        self._client = redis.Redis(
            host=config.REDIS.HOST,
            port=config.REDIS.PORT,
            db=config.REDIS.DB,
            password=config.REDIS.PASSWORD,
        )

    async def save(self, session_message: SessionMessage) -> None:
        ttl_ms = config.GENERATION.TTL_MS
        expire_at = session_message.created_at + ttl_ms / 1000
        session_key = _session_key(
            marketplace=session_message.marketplace, session_id=session_message.session_id,
        )
        pool_key = _pool_key(marketplace=session_message.marketplace)
        stream_key = _stream_key(marketplace=session_message.marketplace)
        async with self._client.pipeline() as pipeline:
            pipeline.set(session_key, session_message.model_dump_json(), px=ttl_ms)
            pipeline.zadd(pool_key, {session_message.session_id: expire_at})
            pipeline.xadd(
                stream_key,
                {'session_id': session_message.session_id, 'expire_at': expire_at},
                maxlen=config.SESSIONS_STREAM.MAXLEN,
                approximate=True,
            )
            await pipeline.execute()
        logger.info(
            '[session_saved] marketplace=%s session_id=%s ttl_ms=%d',
            session_message.marketplace, session_message.session_id, ttl_ms,
        )

    async def live_count(self, marketplace: Marketplace) -> int:
        return await self._client.zcount(
            _pool_key(marketplace=marketplace), min=time.time(), max='+inf',
        )

    async def close(self) -> None:
        await self._client.aclose()
