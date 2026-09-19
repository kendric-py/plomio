import logging
import time

from core.configs import RedisConfig
from core.enums import Marketplace
from core.redis import get_redis_client
from packages.sessions.src.entities import SessionMessage

logger = logging.getLogger(__name__)


def _session_key(marketplace: Marketplace, session_id: str) -> str:
    return f'session:{marketplace.value}:{session_id}'


def _pool_key(marketplace: Marketplace) -> str:
    return f'sessions:pool:{marketplace.value}'


def _stream_key(marketplace: Marketplace, stream_prefix: str) -> str:
    return f'{stream_prefix}:{marketplace.value}'


class SessionPoolStore:
    """Single source of truth for the session pool's Redis wire contract — key formats,
    TTL/scoring, and the pipeline of writes that make up one saved session. Used by all three
    processes touching this pool: `apps/worker_sessions` (writer, `save`), `apps/worker_parser`
    (consumer, `acquire_session`), `apps/api` (read-only stats, `get_live_sessions`).

    Previously this logic was independently reimplemented in each of those three places
    (`RedisSessionStore`, `RedisSessionClient`, `SessionPoolReader`), including the key-format
    helpers below — a change to one had to be copied by hand into the others. Consolidating here
    removes that duplication; `apps/worker_parser`'s `SessionMessage`/`ProxyConfig` used to be an
    intentional hand-synced copy of `apps/worker_sessions`'s for the same reason (apps don't import
    each other's src/) — moving the entities into this package (see `entities.py`) removes that
    duplication too, without breaking the "apps only depend on core/packages" rule: both apps still
    only ever import from `packages.sessions`, never from one another.

    `session:{marketplace}:{id}` — `SET ... PX <ttl_ms>` holding the serialized `SessionMessage`;
    the key disappears on its own TTL, no separate reaping step. `sessions:pool:{marketplace}` —
    `ZSET` scored by `expire_at`, used both to pop the next session (`ZPOPMIN`) and to report pool
    depth (`ZCOUNT`/`ZRANGEBYSCORE`). `{stream_prefix}:{marketplace}` — a Redis Stream, additive to
    the TTL'd pool above, not a replacement (see `apps/worker_sessions/AGENTS.md`)."""

    def __init__(self, redis_config: RedisConfig) -> None:
        self._client = get_redis_client(redis_config)

    async def save(
        self,
        session_message: SessionMessage,
        ttl_ms: int,
        stream_prefix: str,
        stream_maxlen: int,
    ) -> None:
        expire_at = session_message.created_at + ttl_ms / 1000
        session_key = _session_key(
            marketplace=session_message.marketplace, session_id=session_message.session_id,
        )
        pool_key = _pool_key(marketplace=session_message.marketplace)
        stream_key = _stream_key(
            marketplace=session_message.marketplace, stream_prefix=stream_prefix,
        )
        async with self._client.pipeline() as pipeline:
            pipeline.set(session_key, session_message.model_dump_json(), px=ttl_ms)
            pipeline.zadd(pool_key, {session_message.session_id: expire_at})
            pipeline.xadd(
                stream_key,
                {'session_id': session_message.session_id, 'expire_at': expire_at},
                maxlen=stream_maxlen,
                approximate=True,
            )
            await pipeline.execute()
        logger.info(
            '[session_saved] marketplace=%s session_id=%s ttl_ms=%d',
            session_message.marketplace, session_message.session_id, ttl_ms,
        )

    async def acquire_session(
        self,
        marketplace: Marketplace,
        max_pop_attempts: int,
        min_ttl_margin_seconds: float,
    ) -> SessionMessage | None:
        pool_key = _pool_key(marketplace=marketplace)
        for _ in range(max_pop_attempts):
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
            if remaining_ttl_ms / 1000 < min_ttl_margin_seconds:
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

    async def live_count(self, marketplace: Marketplace) -> int:
        return await self._client.zcount(
            _pool_key(marketplace=marketplace), min=time.time(), max='+inf',
        )

    async def get_live_sessions(self, marketplace: Marketplace) -> list[tuple[str, float]]:
        now = time.time()
        raw = await self._client.zrangebyscore(
            _pool_key(marketplace=marketplace), min=now, max='+inf', withscores=True,
        )
        return [
            (session_id.decode() if isinstance(session_id, bytes) else session_id, expires_at)
            for session_id, expires_at in raw
        ]

    async def close(self) -> None:
        await self._client.aclose()
