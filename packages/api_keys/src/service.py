from datetime import datetime, timedelta, timezone

from core.exceptions import ObjectNotFoundError
from core.transaction_manager import AsyncTransactionManager
from packages.api_keys.src.entities import (
    ApiKeyEntity,
    ApiKeyUpdateData,
    ApiKeyWithSpendingEntity,
)
from packages.api_keys.src.enums import ApiKeyBlockReason, ApiKeyStatus
from packages.api_keys.src.exceptions import (
    ApiKeyCreditLimitExceededError,
    ApiKeyExpiredError,
    ApiKeyInactiveError,
    ApiKeyQuotaExceededError,
    ApiKeyRevokedError,
    InvalidApiKeyError,
    InvalidApiKeyExpiryError,
)
from packages.api_keys.src.security import display_prefix, generate_api_key, hash_api_key
from packages.billing.src.service import BillingService

# Сколько действующих (не отозванных) ключей может быть у пользователя одновременно.
MAX_ACTIVE_KEYS_PER_USER = 20
# `last_used_at` обновляется не чаще раза в минуту — иначе каждый запрос по ключу писал бы в БД.
LAST_USED_RESOLUTION = timedelta(minutes=1)

_ERROR_BY_REASON = {
    ApiKeyBlockReason.INACTIVE: ApiKeyInactiveError,
    ApiKeyBlockReason.CREDIT_LIMIT: ApiKeyCreditLimitExceededError,
}


def resolve_api_key_status(api_key: ApiKeyEntity, now: datetime) -> ApiKeyStatus:
    if api_key.revoked_at is not None:
        return ApiKeyStatus.REVOKED
    if api_key.expires_at is not None and api_key.expires_at <= now:
        return ApiKeyStatus.EXPIRED
    return ApiKeyStatus.ACTIVE


def resolve_block_reason(
    api_key: ApiKeyEntity, spent_credits: int, now: datetime,
) -> ApiKeyBlockReason | None:
    """Лимит «мягкий», как и у баланса: последнее списание может его перешагнуть, но после этого
    новые траты по ключу запрещены."""
    if resolve_api_key_status(api_key=api_key, now=now) != ApiKeyStatus.ACTIVE:
        return ApiKeyBlockReason.INACTIVE
    if api_key.credit_limit is not None and spent_credits >= api_key.credit_limit:
        return ApiKeyBlockReason.CREDIT_LIMIT
    return None


class ApiKeyService:
    def __init__(
        self,
        transaction_manager: AsyncTransactionManager,
        billing_service: BillingService,
    ):
        """Потраченное по ключу считает `BillingService` (журнал `credit_transactions`), сам ключ
        хранит только лимит — зависимость однонаправленная, api_keys -> billing."""
        self.transaction_manager = transaction_manager
        self.billing_service = billing_service

    async def create_api_key(
        self,
        user_id: int,
        name: str,
        credit_limit: int | None,
        expires_at: datetime | None,
    ) -> tuple[ApiKeyEntity, str]:
        """Возвращает ключ и его значение — единственный момент, когда значение известно:
        хранится только хэш."""
        _ensure_future(expires_at=expires_at)
        raw_key = generate_api_key()
        async with self.transaction_manager(use_api_key_repository=True) as transaction:
            active_count = await transaction.api_key_repository.count_not_revoked(user_id=user_id)
            if active_count >= MAX_ACTIVE_KEYS_PER_USER:
                raise ApiKeyQuotaExceededError
            api_key = await transaction.api_key_repository.create(
                entity=ApiKeyEntity(
                    user_id=user_id,
                    name=name,
                    prefix=display_prefix(raw_key=raw_key),
                    key_hash=hash_api_key(raw_key=raw_key),
                    credit_limit=credit_limit,
                    expires_at=expires_at,
                ),
            )
            await self.transaction_manager.commit()
        return api_key, raw_key

    async def list_api_keys(self, user_id: int) -> list[ApiKeyWithSpendingEntity]:
        async with self.transaction_manager(use_api_key_repository=True) as transaction:
            api_keys = await transaction.api_key_repository.get_by_user_id(user_id=user_id)
        return await self._with_spending(api_keys=api_keys)

    async def get_api_key(self, api_key_id: int, user_id: int) -> ApiKeyWithSpendingEntity:
        api_key = await self._get_owned(api_key_id=api_key_id, user_id=user_id)
        return (await self._with_spending(api_keys=[api_key]))[0]

    async def update_api_key(
        self, api_key_id: int, user_id: int, changes: ApiKeyUpdateData,
    ) -> ApiKeyWithSpendingEntity:
        values = changes.model_dump(include=changes.model_fields_set)
        if 'expires_at' in values:
            _ensure_future(expires_at=values['expires_at'])
        async with self.transaction_manager(use_api_key_repository=True) as transaction:
            api_key = await transaction.api_key_repository.get_by_id(entity_id=api_key_id)
            if api_key.user_id != user_id:
                raise ObjectNotFoundError
            if api_key.revoked_at is not None:
                raise ApiKeyRevokedError
            if values:
                api_key = await transaction.api_key_repository.apply_changes(
                    api_key_id=api_key_id, values=values,
                )
            await self.transaction_manager.commit()
        return (await self._with_spending(api_keys=[api_key]))[0]

    async def revoke_api_key(self, api_key_id: int, user_id: int) -> ApiKeyWithSpendingEntity:
        """Повторный отзыв — no-op (возвращает ключ как есть), не ошибка."""
        async with self.transaction_manager(use_api_key_repository=True) as transaction:
            api_key = await transaction.api_key_repository.get_by_id(entity_id=api_key_id)
            if api_key.user_id != user_id:
                raise ObjectNotFoundError
            if api_key.revoked_at is None:
                api_key = await transaction.api_key_repository.apply_changes(
                    api_key_id=api_key_id,
                    values={'revoked_at': datetime.now(tz=timezone.utc)},
                )
            await self.transaction_manager.commit()
        return (await self._with_spending(api_keys=[api_key]))[0]

    async def authenticate(self, raw_key: str) -> ApiKeyEntity:
        """Ключ по его значению. Лимит кредитов здесь не проверяется: исчерпанный ключ по-прежнему
        читает данные, запрещены только новые траты (`ensure_can_spend`)."""
        now = datetime.now(tz=timezone.utc)
        async with self.transaction_manager(use_api_key_repository=True) as transaction:
            api_key = await transaction.api_key_repository.get_by_hash(
                key_hash=hash_api_key(raw_key=raw_key),
            )
            if api_key is None:
                raise InvalidApiKeyError
            status = resolve_api_key_status(api_key=api_key, now=now)
            if status == ApiKeyStatus.REVOKED:
                raise ApiKeyRevokedError
            if status == ApiKeyStatus.EXPIRED:
                raise ApiKeyExpiredError
            if api_key.last_used_at is None or now - api_key.last_used_at >= LAST_USED_RESOLUTION:
                await transaction.api_key_repository.touch_last_used(
                    api_key_id=api_key.id, used_at=now,
                )
                await self.transaction_manager.commit()
        return api_key

    async def can_spend(self, api_key_id: int) -> bool:
        blocked = await self.get_blocked_api_key_ids(api_key_ids=[api_key_id])
        return api_key_id not in blocked

    async def ensure_can_spend(self, api_key_id: int) -> None:
        """Guard перед новой тратой по ключу (вместе с `BillingService.ensure_can_spend` по
        пользователю). `ApiKeyCreditLimitExceededError`/`ApiKeyInactiveError` — оба подклассы
        `InsufficientCreditsError` (402)."""
        blocked = await self.get_blocked_api_key_ids(api_key_ids=[api_key_id])
        if api_key_id in blocked:
            raise _ERROR_BY_REASON[blocked[api_key_id]]()

    async def get_blocked_api_key_ids(
        self, api_key_ids: list[int],
    ) -> dict[int, ApiKeyBlockReason]:
        """Батч для диспатча автоматизаций: `{api_key_id: причина}` только для ключей, по которым
        тратить нельзя. Ключ, которого уже нет (удалён вместе с пользователем), — неактивен."""
        unique_ids = list(set(api_key_ids))
        if not unique_ids:
            return {}
        async with self.transaction_manager(use_api_key_repository=True) as transaction:
            api_keys = await transaction.api_key_repository.get_by_ids(api_key_ids=unique_ids)
        spent = await self.billing_service.get_spent_by_api_keys(
            api_key_ids=[api_key.id for api_key in api_keys if api_key.credit_limit is not None],
        )
        now = datetime.now(tz=timezone.utc)
        found = {api_key.id: api_key for api_key in api_keys}
        blocked: dict[int, ApiKeyBlockReason] = {}
        for api_key_id in unique_ids:
            api_key = found.get(api_key_id)
            if api_key is None:
                blocked[api_key_id] = ApiKeyBlockReason.INACTIVE
                continue
            reason = resolve_block_reason(
                api_key=api_key, spent_credits=spent.get(api_key_id, 0), now=now,
            )
            if reason is not None:
                blocked[api_key_id] = reason
        return blocked

    async def _get_owned(self, api_key_id: int, user_id: int) -> ApiKeyEntity:
        async with self.transaction_manager(use_api_key_repository=True) as transaction:
            api_key = await transaction.api_key_repository.get_by_id(entity_id=api_key_id)
        if api_key.user_id != user_id:
            raise ObjectNotFoundError
        return api_key

    async def _with_spending(
        self, api_keys: list[ApiKeyEntity],
    ) -> list[ApiKeyWithSpendingEntity]:
        spent = await self.billing_service.get_spent_by_api_keys(
            api_key_ids=[api_key.id for api_key in api_keys],
        )
        return [
            ApiKeyWithSpendingEntity(**api_key.model_dump(), spent_credits=spent.get(api_key.id, 0))
            for api_key in api_keys
        ]


def _ensure_future(expires_at: datetime | None) -> None:
    if expires_at is not None and expires_at <= datetime.now(tz=timezone.utc):
        raise InvalidApiKeyExpiryError
