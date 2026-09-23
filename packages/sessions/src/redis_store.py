import logging
from datetime import datetime, timedelta, timezone

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
    (consumer, `acquire_session`), `apps/api` (read-only stats, `get_pool_stats`).

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
    the TTL'd pool above, not a replacement (see `apps/worker_sessions/AGENTS.md`).

    Redis TTL only ever expires a key wholesale — it has no notion of expiring one member of a
    `ZSET`, so a `session:{marketplace}:{id}` dying by TTL leaves its `session_id` sitting dead in
    `sessions:pool:{marketplace}` until something removes it. `acquire_session` used to rely purely
    on lazy cleanup (`ZPOPMIN` one candidate at a time, discard if `PTTL` says it's gone) — fine
    when dead entries are rare, but if the pool ever accumulates a large backlog of already-expired
    members (e.g. `worker_sessions` outpacing consumption while `worker_parser` was down), that
    backlog only drained `max_pop_attempts` at a time per call, with an `EMPTY_POOL_BACKOFF_SECONDS`
    sleep between calls whenever a whole batch came back dead — multi-minute stalls before a caller
    ever reached a live session. `acquire_session` now opens with one `ZREMRANGEBYSCORE` sweep that
    bulk-drops every already-expired member in a single round trip before attempting any `ZPOPMIN`,
    so a stale backlog is cleared in one shot instead of trickling out in pop-sized batches."""

    def __init__(self, redis_config: RedisConfig) -> None:
        self._client = get_redis_client(redis_config)

    async def save(
        self,
        session_message: SessionMessage,
        ttl_ms: int,
        stream_prefix: str,
        stream_maxlen: int,
    ) -> None:
        expire_at_dt = session_message.created_at + timedelta(milliseconds=ttl_ms)
        session_key = _session_key(
            marketplace=session_message.marketplace, session_id=session_message.session_id,
        )
        pool_key = _pool_key(marketplace=session_message.marketplace)
        stream_key = _stream_key(
            marketplace=session_message.marketplace, stream_prefix=stream_prefix,
        )
        async with self._client.pipeline() as pipeline:
            pipeline.set(session_key, session_message.model_dump_json(), px=ttl_ms)
            pipeline.zadd(pool_key, {session_message.session_id: expire_at_dt.timestamp()})
            pipeline.xadd(
                stream_key,
                {'session_id': session_message.session_id, 'expire_at': expire_at_dt.isoformat()},
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
        expired_removed = await self._client.zremrangebyscore(
            pool_key, min='-inf', max=datetime.now(timezone.utc).timestamp(),
        )
        if expired_removed:
            logger.info(
                '[session_pool_swept] marketplace=%s removed=%d',
                marketplace.value, expired_removed,
            )
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

    async def release(
        self,
        session_message: SessionMessage,
        min_ttl_margin_seconds: float,
    ) -> bool:
        """Returns a still-usable session back into the pool instead of letting it go to waste
        after one caller's worth of use — `acquire_session` above `ZPOPMIN`s a session out of
        `sessions:pool:{marketplace}` exclusively, and without this there was no way back in, so
        a session that died of TTL/idle time rather than getting blocked (or one whose consumer
        simply finished before exhausting it) was silently thrown away instead of serving another
        caller. Only re-adds the pool-membership `ZSET` entry — the `session:{marketplace}:{id}`
        body/TTL from the original `save` is untouched, since nothing about the session itself
        changed. Callers are responsible for only releasing a session they still trust (e.g. not
        one that just failed with a block) — this method has no way to verify that itself.

        Re-checks remaining TTL first: a session already below `min_ttl_margin_seconds` would
        just get filtered straight back out by `acquire_session`'s own margin check, so adding it
        back would only pollute `live_count`/pool-depth stats with a session that's functionally
        already dead. Returns whether the session was actually re-added."""
        session_key = _session_key(
            marketplace=session_message.marketplace, session_id=session_message.session_id,
        )
        remaining_ttl_ms = await self._client.pttl(session_key)
        if remaining_ttl_ms is None or remaining_ttl_ms / 1000 < min_ttl_margin_seconds:
            logger.info(
                '[session_release_skipped] marketplace=%s session_id=%s remaining_ms=%s',
                session_message.marketplace.value, session_message.session_id, remaining_ttl_ms,
            )
            return False

        pool_key = _pool_key(marketplace=session_message.marketplace)
        expire_at = datetime.now(timezone.utc).timestamp() + remaining_ttl_ms / 1000
        await self._client.zadd(pool_key, {session_message.session_id: expire_at})
        logger.info(
            '[session_released] marketplace=%s session_id=%s remaining_ms=%d',
            session_message.marketplace.value, session_message.session_id, remaining_ttl_ms,
        )
        return True

    async def live_count(self, marketplace: Marketplace) -> int:
        return await self._client.zcount(
            _pool_key(marketplace=marketplace),
            min=datetime.now(timezone.utc).timestamp(),
            max='+inf',
        )

    async def get_pool_stats(self, marketplace: Marketplace) -> tuple[int, datetime | None]:
        """Aggregate pool info without exposing session ids: live count plus the nearest
        `expires_at` among live sessions (`None` if the pool is empty)."""

        pool_key = _pool_key(marketplace=marketplace)
        now = datetime.now(timezone.utc).timestamp()
        live_count = await self._client.zcount(pool_key, min=now, max='+inf')
        nearest = await self._client.zrangebyscore(
            pool_key, min=now, max='+inf', start=0, num=1, withscores=True,
        )
        nearest_expires_at = (
            datetime.fromtimestamp(nearest[0][1], tz=timezone.utc) if nearest else None
        )
        return live_count, nearest_expires_at

    async def close(self) -> None:
        await self._client.aclose()
