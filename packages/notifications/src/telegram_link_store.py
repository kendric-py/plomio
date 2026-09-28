import secrets

from core.configs import RedisConfig
from core.redis import get_redis_client


def _link_code_key(code: str) -> str:
    return f'telegram_link:{code}'


class TelegramLinkStore:
    """One-time code → user_id mapping backing the Telegram account-linking flow (see
    `packages/notifications/AGENTS.md`, "Привязка Telegram"). `telegram_link:{code}` — `SET ... EX
    <ttl_seconds>` holding the raw `user_id`; the key disappears on its own TTL, same convention as
    `packages.sessions.SessionPoolStore`'s `session:{marketplace}:{id}`. A code is single-use —
    `consume_link_code` deletes it atomically (`GETDEL`) as part of resolving it, so a stale
    `/start <code>` retried after a successful link — or two concurrent `/start` clicks racing on
    the same leaked/replayed code — can't both read the code before either delete fires and
    silently re-link a different account (a plain GET-then-DEL would be a TOCTOU race here)."""

    def __init__(self, redis_config: RedisConfig) -> None:
        self._client = get_redis_client(redis_config)

    async def create_link_code(self, user_id: int, ttl_seconds: int) -> str:
        code = secrets.token_urlsafe(16)
        await self._client.set(_link_code_key(code=code), user_id, ex=ttl_seconds)
        return code

    async def consume_link_code(self, code: str) -> int | None:
        key = _link_code_key(code=code)
        # GETDEL — single atomic Redis command (not GET followed by a separate DEL): two concurrent
        # calls for the same code can't both observe it as present, so only one ever resolves to a
        # user_id.
        raw_user_id = await self._client.getdel(key)
        return int(raw_user_id) if raw_user_id is not None else None
