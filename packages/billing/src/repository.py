from datetime import datetime

from sqlalchemy import Date, Select, and_, case, cast, func, literal, not_, or_, select, true, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.exceptions import ObjectNotFoundError
from core.repository import BaseRepository
from packages.billing.src.entities import (
    BillingActionEntity,
    CreditTransactionEntity,
    CreditTransactionGroupEntity,
    CreditWalletEntity,
    DailySpendingEntity,
    PricingMultiplierRuleEntity,
    ReferenceSpendingEntity,
    SpendingLimitEntity,
    SpendingStatsEntity,
    TransactionFilters,
)
from packages.billing.src.enums import PricingDimension, ReferenceType, TransactionKind
from packages.billing.src.models import (
    BillingAction,
    CreditTransaction,
    CreditWallet,
    PricingMultiplierRule,
    SpendingLimit,
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

    def _source_type(self):
        """Источник списания для отчётов. Проверочная задача автоматизации пишется как `TASK`, но
        пользователю это расход на автоматизацию — по `automation_id` в метаданных."""

        return case(
            (
                self.model.transaction_metadata['automation_id'].astext.is_not(None),
                literal(ReferenceType.AUTOMATION, type_=self.model.reference_type.type),
            ),
            else_=self.model.reference_type,
        )

    def _source_id(self):
        return func.coalesce(
            self.model.transaction_metadata['automation_id'].astext, self.model.reference_id,
        )

    def _apply_filters(self, statement: Select, user_id: int, filters: TransactionFilters | None):
        statement = statement.where(self.model.user_id == user_id)
        if filters is None:
            return statement
        if filters.reference_type is not None:
            statement = statement.where(self._source_type() == filters.reference_type)
        if filters.reference_id is not None:
            statement = statement.where(self._source_id() == filters.reference_id)
        if filters.kind == TransactionKind.SPEND:
            statement = statement.where(self.model.amount < 0)
        elif filters.kind == TransactionKind.GRANT:
            statement = statement.where(self.model.amount > 0)
        if filters.date_from is not None:
            statement = statement.where(self.model.created_at >= filters.date_from)
        if filters.date_to is not None:
            statement = statement.where(self.model.created_at <= filters.date_to)
        return statement

    def _grouped_source(self, user_id: int, filters: TransactionFilters | None):
        """Подзапрос «строка журнала + её источник» — группировка идёт по готовым колонкам, а не по
        выражению с параметрами (иначе Postgres не сопоставит SELECT и GROUP BY)."""

        statement = self._apply_filters(
            select(
                self.model.id,
                self.model.amount,
                self.model.created_at,
                self._source_type().label('source_type'),
                self._source_id().label('source_id'),
            ),
            user_id,
            filters,
        ).where(self.model.reference_id.is_not(None))
        return statement.subquery()

    async def get_grouped_by_reference(
        self, user_id: int, limit: int, offset: int, filters: TransactionFilters | None = None,
    ) -> list[CreditTransactionGroupEntity]:
        """Списания пользователя, сгруппированные по источнику; строки без источника (ручное
        начисление админом) не входят. Расход проверочной задачи автоматизации относится к самой
        автоматизации, а не к задаче. Порядок — по последней транзакции группы."""

        source = self._grouped_source(user_id, filters)
        last_at = func.max(source.c.created_at)
        statement = (
            select(
                source.c.source_type,
                source.c.source_id,
                func.sum(source.c.amount).label('total_amount'),
                func.count(source.c.id).label('transactions_count'),
                func.min(source.c.created_at).label('first_at'),
                last_at.label('last_at'),
            )
            .group_by(source.c.source_type, source.c.source_id)
            .order_by(last_at.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.execute(statement)
        return [
            CreditTransactionGroupEntity(
                reference_type=row.source_type,
                reference_id=row.source_id,
                total_amount=row.total_amount,
                transactions_count=row.transactions_count,
                first_at=row.first_at,
                last_at=row.last_at,
            )
            for row in rows
        ]

    async def list_for_user(
        self, user_id: int, limit: int, offset: int, filters: TransactionFilters | None = None,
    ) -> list[CreditTransactionEntity]:
        """Плоский журнал пользователя (списания и начисления), новые сверху."""

        statement = (
            self._apply_filters(select(self.model), user_id, filters)
            .order_by(self.model.created_at.desc(), self.model.id.desc())
            .limit(limit)
            .offset(offset)
        )
        rows = await self.session.scalars(statement)
        return [self._to_entity(database_object=row) for row in rows]

    async def count_for_user(self, user_id: int, filters: TransactionFilters | None = None) -> int:
        statement = self._apply_filters(select(func.count(self.model.id)), user_id, filters)
        return await self.session.scalar(statement)

    async def get_spending_stats(
        self,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        user_id: int | None = None,
    ) -> SpendingStatsEntity:
        """Суммы списаний (`amount < 0`, возвращаются положительными) по всем пользователям за
        период (`created_at`, границы включительные).

        Проверочные задачи автоматизаций списываются с `reference_type=TASK` (reference — id
        задачи), поэтому «автоматизация» определяется по снэпшоту измерения в метаданных
        транзакции (`dimension_code == automation_check_frequency`) либо по
        `reference_type=AUTOMATION` (создание) — так billing не обращается к таблицам
        `packages/task`/`packages/automation`."""

        is_automation = or_(
            self.model.reference_type == ReferenceType.AUTOMATION,
            func.coalesce(self.model.transaction_metadata['dimension_code'].astext, '')
            == PricingDimension.AUTOMATION_CHECK_FREQUENCY.value,
        )
        spent = -self.model.amount

        def sum_where(*conditions) -> Select:
            return func.coalesce(func.sum(spent).filter(and_(*conditions)), 0)

        statement = select(
            sum_where(true()).label('total_spent'),
            sum_where(
                self.model.reference_type == ReferenceType.TASK, not_(is_automation),
            ).label('tasks_spent'),
            sum_where(is_automation).label('automations_spent'),
            sum_where(self.model.reference_type == ReferenceType.DIRECT).label('direct_spent'),
        ).where(self.model.amount < 0)
        if user_id is not None:
            statement = statement.where(self.model.user_id == user_id)
        if date_from is not None:
            statement = statement.where(self.model.created_at >= date_from)
        if date_to is not None:
            statement = statement.where(self.model.created_at <= date_to)

        row = (await self.session.execute(statement)).one()
        return SpendingStatsEntity(
            total_spent=row.total_spent,
            tasks_spent=row.tasks_spent,
            automations_spent=row.automations_spent,
            direct_spent=row.direct_spent,
        )

    async def count_reference_groups(
        self, user_id: int, filters: TransactionFilters | None = None,
    ) -> int:
        source = self._grouped_source(user_id, filters)
        groups = (
            select(source.c.source_type, source.c.source_id)
            .group_by(source.c.source_type, source.c.source_id)
            .subquery()
        )
        return await self.session.scalar(select(func.count()).select_from(groups))

    async def get_spent_since(self, user_id: int, since: datetime) -> int:
        """Сколько пользователь потратил с момента `since` (положительное число)."""

        statement = select(func.coalesce(func.sum(-self.model.amount), 0)).where(
            self.model.user_id == user_id,
            self.model.amount < 0,
            self.model.created_at >= since,
        )
        return await self.session.scalar(statement)

    async def get_daily_spending(
        self, user_id: int, date_from: datetime | None, date_to: datetime | None,
    ) -> list[DailySpendingEntity]:
        """Траты пользователя по дням (UTC) с той же классификацией, что в `get_spending_stats`.
        Дни без списаний в выдачу не входят — пустые дни добавляет клиент."""

        is_automation = self._is_automation_condition()
        spent = -self.model.amount
        day = cast(func.timezone('UTC', self.model.created_at), Date).label('day')

        def sum_where(*conditions):
            return func.coalesce(func.sum(spent).filter(and_(*conditions)), 0)

        statement = (
            select(
                day,
                sum_where(true()).label('total_spent'),
                sum_where(
                    self.model.reference_type == ReferenceType.TASK, not_(is_automation),
                ).label('tasks_spent'),
                sum_where(is_automation).label('automations_spent'),
                sum_where(self.model.reference_type == ReferenceType.DIRECT).label('direct_spent'),
            )
            .where(self.model.user_id == user_id, self.model.amount < 0)
            .group_by(day)
            .order_by(day)
        )
        if date_from is not None:
            statement = statement.where(self.model.created_at >= date_from)
        if date_to is not None:
            statement = statement.where(self.model.created_at <= date_to)
        rows = await self.session.execute(statement)
        return [
            DailySpendingEntity(
                day=row.day,
                total_spent=row.total_spent,
                tasks_spent=row.tasks_spent,
                automations_spent=row.automations_spent,
                direct_spent=row.direct_spent,
            )
            for row in rows
        ]

    async def get_reference_spending(
        self, user_id: int, reference_type: ReferenceType, reference_id: str,
    ) -> ReferenceSpendingEntity:
        """Расход на одну сущность. Для автоматизации сюда входят и проверочные задачи: их
        списания идут с `reference_type=TASK`, но в метаданных несут `automation_id`."""

        is_own = and_(
            self.model.reference_type == reference_type, self.model.reference_id == reference_id,
        )
        condition = is_own
        if reference_type == ReferenceType.AUTOMATION:
            condition = or_(
                is_own,
                self.model.transaction_metadata['automation_id'].astext == reference_id,
            )
        statement = select(
            func.coalesce(func.sum(-self.model.amount), 0).label('total_spent'),
            func.count(self.model.id).label('transactions_count'),
        ).where(self.model.user_id == user_id, self.model.amount < 0, condition)
        row = (await self.session.execute(statement)).one()
        return ReferenceSpendingEntity(
            total_spent=row.total_spent, transactions_count=row.transactions_count,
        )

    def _is_automation_condition(self):
        return or_(
            self.model.reference_type == ReferenceType.AUTOMATION,
            func.coalesce(self.model.transaction_metadata['dimension_code'].astext, '')
            == PricingDimension.AUTOMATION_CHECK_FREQUENCY.value,
        )


class SpendingLimitRepository(BaseRepository[SpendingLimit, SpendingLimitEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=SpendingLimit, entity_object=SpendingLimitEntity, session=session)

    async def get_for_user(self, user_id: int) -> SpendingLimitEntity | None:
        database_object = await self.session.get(entity=self.model, ident=user_id)
        return self._to_entity(database_object=database_object) if database_object else None

    async def get_for_users(self, user_ids: list[int]) -> dict[int, SpendingLimitEntity]:
        """Батч для диспатча автоматизаций: у большинства пользователей лимита нет, поэтому в
        результате только те, у кого он задан."""

        if not user_ids:
            return {}
        rows = await self.session.scalars(select(self.model).where(self.model.user_id.in_(user_ids)))
        return {row.user_id: self._to_entity(database_object=row) for row in rows}

    async def set_limits(
        self, user_id: int, daily_limit: int | None, monthly_limit: int | None,
    ) -> SpendingLimitEntity | None:
        """Задаёт оба лимита целиком (`None` — снять). Если не осталось ни одного — строка
        удаляется и возвращается `None`."""

        database_object = await self.session.get(entity=self.model, ident=user_id)
        if daily_limit is None and monthly_limit is None:
            if database_object is not None:
                await self.session.delete(database_object)
                await self.session.flush()
            return None
        if database_object is None:
            database_object = self.model(
                user_id=user_id, daily_limit=daily_limit, monthly_limit=monthly_limit,
            )
            self.session.add(database_object)
        else:
            database_object.daily_limit = daily_limit
            database_object.monthly_limit = monthly_limit
        await self.session.flush()
        return self._to_entity(database_object=database_object)
