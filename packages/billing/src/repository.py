from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ObjectNotFoundError
from core.repository import BaseRepository
from packages.billing.src.entities import (
    BillingActionEntity,
    CreditTransactionEntity,
    CreditTransactionGroupEntity,
    CreditWalletEntity,
    PricingMultiplierRuleEntity,
)
from packages.billing.src.models import (
    BillingAction,
    CreditTransaction,
    CreditWallet,
    PricingMultiplierRule,
)


class BillingActionRepository(BaseRepository[BillingAction, BillingActionEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=BillingAction, entity_object=BillingActionEntity, session=session)

    async def get_by_action_code(self, action_code: str) -> BillingActionEntity | None:
        statement = select(self.model).where(self.model.action_code == action_code)
        database_object = await self.session.scalar(statement)
        return self._to_entity(database_object=database_object) if database_object else None

    async def update_base_cost(self, action_code: str, base_cost: int) -> BillingActionEntity:
        statement = select(self.model).where(self.model.action_code == action_code)
        database_object = await self.session.scalar(statement)
        if database_object is None:
            raise ObjectNotFoundError
        database_object.base_cost = base_cost
        await self.session.flush()
        return self._to_entity(database_object=database_object)


class PricingMultiplierRuleRepository(
    BaseRepository[PricingMultiplierRule, PricingMultiplierRuleEntity],
):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=PricingMultiplierRule,
            entity_object=PricingMultiplierRuleEntity,
            session=session,
        )

    async def find_matching(
        self, dimension_code: str, value: int,
    ) -> PricingMultiplierRuleEntity | None:
        statement = (
            select(self.model)
            .where(
                self.model.dimension_code == dimension_code,
                self.model.value_min <= value,
                self.model.value_max >= value,
            )
            .limit(1)
        )
        database_object = await self.session.scalar(statement)
        return self._to_entity(database_object=database_object) if database_object else None

    async def get_by_dimension_code(self, dimension_code: str) -> list[PricingMultiplierRuleEntity]:
        statement = (
            select(self.model)
            .where(self.model.dimension_code == dimension_code)
            .order_by(self.model.value_min.asc())
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def has_overlap(self, dimension_code: str, value_min: int, value_max: int) -> bool:
        statement = (
            select(self.model.id)
            .where(
                self.model.dimension_code == dimension_code,
                self.model.value_min <= value_max,
                self.model.value_max >= value_min,
            )
            .limit(1)
        )
        return await self.session.scalar(statement) is not None


class CreditWalletRepository(BaseRepository[CreditWallet, CreditWalletEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=CreditWallet, entity_object=CreditWalletEntity, session=session)

    async def lock_or_create(self, user_id: int) -> CreditWalletEntity:
        """Row-level lock (`SELECT ... FOR UPDATE`), creating the wallet with `balance=0` on first
        use. Held until the caller's transaction commits — serializes concurrent `charge()`/
        `grant()` calls for the same user, same pattern as `TaskRepository.lock_by_id`."""

        statement = select(self.model).where(self.model.user_id == user_id).with_for_update()
        database_object = await self.session.scalar(statement)
        if database_object is None:
            database_object = self.model(user_id=user_id, balance=0)
            self.session.add(database_object)
            await self.session.flush()
        return self._to_entity(database_object=database_object)

    async def get_balances(self, user_ids: list[int]) -> dict[int, int]:
        """Batched counterpart of `get_by_id`/`BillingService.get_balance` — one query for a whole
        set of users instead of one `SELECT` per user (used by `AutomationService.
        dispatch_due_checks` to avoid an N+1 balance check per claimed automation in the same
        dispatch batch). A `user_id` with no wallet row yet is simply absent from the returned
        dict — same "no wallet = balance 0" semantics as `get_balance`, left to the caller via
        `.get(user_id, 0)`."""

        if not user_ids:
            return {}

        statement = select(self.model.user_id, self.model.balance).where(
            self.model.user_id.in_(user_ids),
        )
        rows = await self.session.execute(statement)
        return {row.user_id: row.balance for row in rows}

    async def adjust_balance(self, user_id: int, delta: int) -> int:
        """Applies `delta` to the wallet balance and returns the new balance. Caller must already
        hold the row lock from `lock_or_create` in the same transaction — this only applies the
        delta, it doesn't lock or create the wallet on its own."""

        statement = (
            update(self.model)
            .where(self.model.user_id == user_id)
            .values(balance=self.model.balance + delta)
            .returning(self.model.balance)
        )
        result = await self.session.execute(statement)
        return result.scalar_one()


class CreditTransactionRepository(BaseRepository[CreditTransaction, CreditTransactionEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=CreditTransaction,
            entity_object=CreditTransactionEntity,
            session=session,
        )

    async def get_grouped_by_reference(
        self, user_id: int, limit: int, offset: int,
    ) -> list[CreditTransactionGroupEntity]:
        """Списания пользователя, сгруппированные по (`reference_type`, `reference_id`); строки без
        источника (ручное начисление админом) не входят. Порядок — по последней транзакции группы."""

        last_at = func.max(self.model.created_at)
        statement = (
            select(
                self.model.reference_type,
                self.model.reference_id,
                func.sum(self.model.amount).label('total_amount'),
                func.count(self.model.id).label('transactions_count'),
                func.min(self.model.created_at).label('first_at'),
                last_at.label('last_at'),
            )
            .where(self.model.user_id == user_id, self.model.reference_id.is_not(None))
            .group_by(self.model.reference_type, self.model.reference_id)
            .order_by(last_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(statement)
        return [
            CreditTransactionGroupEntity(
                reference_type=row.reference_type,
                reference_id=row.reference_id,
                total_amount=row.total_amount,
                transactions_count=row.transactions_count,
                first_at=row.first_at,
                last_at=row.last_at,
            )
            for row in rows
        ]

    async def count_reference_groups(self, user_id: int) -> int:
        groups = (
            select(self.model.reference_type, self.model.reference_id)
            .where(self.model.user_id == user_id, self.model.reference_id.is_not(None))
            .group_by(self.model.reference_type, self.model.reference_id)
            .subquery()
        )
        return await self.session.scalar(select(func.count()).select_from(groups))