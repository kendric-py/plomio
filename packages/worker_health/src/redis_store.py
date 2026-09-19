import time

from core.configs import RedisConfig
from core.redis import get_redis_client
from packages.worker_health.src.enums import WorkerType

_HEARTBEATS_KEY = 'worker_health:heartbeats'
_MISSED_KEY = 'worker_health:missed'
_STATUS_KEY = 'worker_health:status'


def _member(worker_type: WorkerType, worker_name: str) -> str:
    return f'{worker_type.value}:{worker_name}'


def parse_member(member: str) -> tuple[WorkerType, str]:
    worker_type_value, worker_name = member.split(':', 1)
    return WorkerType(worker_type_value), worker_name


class WorkerHeartbeatStore:
    """Redis-backed last-seen tracking for worker heartbeats.

    `touch()` is called on every incoming heartbeat request (cheap, no Postgres write) and also
    records the worker-reported status string (`worker_health:status` HASH) so it can be surfaced
    by the status-reading endpoint — it's transit telemetry, not validated against a domain enum
    (see packages/worker_health/AGENTS.md for why).
    `try_claim_missed`/`try_claim_recovered` use atomic Redis SET operations (SADD/SREM) as the
    dedup mechanism for state-transition logging: with several `apps/api` replicas each running
    their own periodic check, only the replica whose SADD/SREM actually mutates the set is allowed
    to write the transition to Postgres — the others observe `False` and skip.
    """

    def __init__(self, redis_config: RedisConfig) -> None:
        self._client = get_redis_client(redis_config)

    async def touch(self, worker_type: WorkerType, worker_name: str, status: str) -> None:
        member = _member(worker_type, worker_name)
        async with self._client.pipeline() as pipeline:
            pipeline.zadd(_HEARTBEATS_KEY, {member: time.time()})
            pipeline.hset(_STATUS_KEY, member, status)
            await pipeline.execute()

    async def get_last_seen_map(self) -> dict[str, float]:
        raw = await self._client.zrange(_HEARTBEATS_KEY, 0, -1, withscores=True)
        return {
            (member.decode() if isinstance(member, bytes) else member): score
            for member, score in raw
        }

    async def get_status_map(self) -> dict[str, str]:
        raw = await self._client.hgetall(_STATUS_KEY)
        return {
            (member.decode() if isinstance(member, bytes) else member):
                (status.decode() if isinstance(status, bytes) else status)
            for member, status in raw.items()
        }

    async def try_claim_missed(self, member: str) -> bool:
        added = await self._client.sadd(_MISSED_KEY, member)
        return added == 1

    async def try_claim_recovered(self, member: str) -> bool:
        removed = await self._client.srem(_MISSED_KEY, member)
        return removed == 1

    async def get_missed_members(self) -> set[str]:
        raw = await self._client.smembers(_MISSED_KEY)
        return {member.decode() if isinstance(member, bytes) else member for member in raw}

    async def close(self) -> None:
        await self._client.aclose()
