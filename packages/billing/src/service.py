import logging
import math
from datetime import datetime, timezone
from decimal import Decimal

from core.exceptions import ObjectNotFoundError
from core.transaction_manager import AsyncTransactionManager
from packages.billing.src.entities import (
    BillingActionEntity,
    CreditTransactionEntity,
    CreditTransactionGroupEntity,
    DailySpendingEntity,
    PricingMultiplierRuleEntity,
    ReferenceSpendingEntity,
    SpendingLimitEntity,
    SpendingStatsEntity,
    SpendingStatusEntity,
    TransactionFilters,
)
from packages.billing.src.enums import ReferenceType
from packages.billing.src.exceptions import (
    InsufficientCreditsError,
    OverlappingPricingRuleError,
    SpendingLimitExceededError,
)

logger = logging.getLogger(__name__)

EVENT_BALANCE_DEPLETED = 'billing.balance_depleted'
EVENT_BALANCE_LOW = 'billing.balance_low'

# Размер страницы, которой выгрузка забирает журнал из БД (в память целиком, но не одним запросом).
EXPORT_PAGE_SIZE = 500


class BillingService:
    def __init__(
        self,
        transaction_manager: AsyncTransactionManager,
        notification_service=None,
        frontend_base_url: str = '',
        low_balance_threshold: int = 0,
    ):
        """`notification_service` необязателен: без него списание работает как раньше, просто не
        шлёт уведомлений о балансе. Зависимость однонаправленная (billing -> notifications),
        `packages/notifications` про billing не знает."""

        self.transaction_manager = transaction_manager
        self.notification_service = notification_service
        self.frontend_base_url = frontend_base_url
        self.low_balance_threshold = low_balance_threshold

    async def charge(
        self,
        user_id: int,
        action_code: str,
        quantity: int = 1,
        dimension_code: str | None = None,
        dimension_value: int | None = None,
        reference_type: ReferenceType | None = None,
        reference_id: str | None = None,
        extra_metadata: dict | None = None,
    ) -> CreditTransactionEntity | None:
        """No-op (returns None, no transaction/row written) when the action isn't in the catalog,
        its `base_cost` is 0, `quantity` is 0, or rounding brings the charge to 0 — a still
        unpriced action must never block or mutate anything. Otherwise atomically (one transaction,
        row lock on the wallet) debits `credits = ceil(base_cost * multiplier * quantity)` and
        writes one `credit_transactions` row. Never raises on going negative — that's allowed by
        design, callers that need to block on balance use `has_positive_balance` as a guard
        *before* calling this."""

        if quantity <= 0:
            return None

        async with self.transaction_manager(
            use_billing_action_repository=True,
            use_pricing_multiplier_rule_repository=True,
            use_credit_wallet_repository=True,
            use_credit_transaction_repository=True,
        ) as transaction:
            action = await transaction.billing_action_repository.get_by_action_code(
                action_code=action_code,
            )
            if action is None or not action.base_cost:
                return None

            multiplier = Decimal('1.00')
            if dimension_code is not None and dimension_value is not None:
                rule = await transaction.pricing_multiplier_rule_repository.find_matching(
                    dimension_code=dimension_code, value=dimension_value,
                )
                if rule is not None:
                    multiplier = rule.multiplier

            unit_cost = Decimal(action.base_cost) * multiplier
            credits = math.ceil(unit_cost * quantity)
            if credits <= 0:
                return None

            await transaction.credit_wallet_repository.lock_or_create(user_id=user_id)
            new_balance = await transaction.credit_wallet_repository.adjust_balance(
                user_id=user_id, delta=-credits,
            )
            created_transaction = await transaction.credit_transaction_repository.create(
                entity=CreditTransactionEntity(
                    user_id=user_id,
                    amount=-credits,
                    balance_after=new_balance,
                    action_code=action_code,
                    reference_type=reference_type,
                    reference_id=reference_id,
                    transaction_metadata={
                        'quantity': quantity,
                        'unit_cost': str(unit_cost),
                        'multiplier': str(multiplier),
                        'dimension_code': dimension_code,
                        'dimension_value': dimension_value,
                        **(extra_metadata or {}),
                    },
                ),
            )
            await self.transaction_manager.commit()
        await self._notify_balance_crossing(
            user_id=user_id, balance_before=new_balance + credits, balance_after=new_balance,
        )
        return created_transaction

    async def _notify_balance_crossing(
        self, user_id: int, balance_before: int, balance_after: int,
    ) -> None:
        """Уведомляет только в момент пересечения порога (раз, а не на каждом списании):
        баланс исчерпан (был > 0, стал <= 0) либо упал ниже порога «мало кредитов». Сбой уведомления
        никогда не ломает списание — оно уже закоммичено."""

        if self.notification_service is None:
            return
        payload = {
            'balance': balance_after,
            'billing_link': f'{self.frontend_base_url}/billing' if self.frontend_base_url else None,
        }
        if balance_before > 0 >= balance_after:
            event_code = EVENT_BALANCE_DEPLETED
        elif (
            self.low_balance_threshold > 0
            and balance_before > self.low_balance_threshold >= balance_after > 0
        ):
            event_code = EVENT_BALANCE_LOW
            payload['threshold'] = self.low_balance_threshold
        else:
            return
        try:
            await self.notification_service.notify(
                user_id=user_id, event_code=event_code, payload=payload,
            )
        except Exception:
            logger.exception('[billing_notify_failed] user_id=%s event=%s', user_id, event_code)

    async def grant(
        self, user_id: int, amount: int, admin_id: int | None, comment: str | None,
    ) -> CreditTransactionEntity:
        """`admin_id=None` — начисление не администратором (например, бонус при регистрации)."""

        async with self.transaction_manager(
            use_credit_wallet_repository=True,
            use_credit_transaction_repository=True,
        ) as transaction:
            await transaction.credit_wallet_repository.lock_or_create(user_id=user_id)
            new_balance = await transaction.credit_wallet_repository.adjust_balance(
                user_id=user_id, delta=amount,
            )
            created_transaction = await transaction.credit_transaction_repository.create(
                entity=CreditTransactionEntity(
                    user_id=user_id,
                    amount=amount,
                    balance_after=new_balance,
                    granted_by_admin_id=admin_id,
                    transaction_metadata={'comment': comment} if comment else None,
                ),
            )
            await self.transaction_manager.commit()
        return created_transaction

    async def get_spending_stats(
        self, date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> SpendingStatsEntity:
        """Суммарные траты всех пользователей за период (админская статистика)."""

        async with self.transaction_manager(use_credit_transaction_repository=True) as transaction:
            return await transaction.credit_transaction_repository.get_spending_stats(
                date_from=date_from, date_to=date_to,
            )

    async def get_balance(self, user_id: int) -> int:
        async with self.transaction_manager(use_credit_wallet_repository=True) as transaction:
            try:
                wallet = await transaction.credit_wallet_repository.get_by_id(entity_id=user_id)
            except ObjectNotFoundError:
                return 0
        return wallet.balance

    async def has_positive_balance(self, user_id: int) -> bool:
        return await self.get_balance(user_id=user_id) > 0

    async def can_spend(self, user_id: int) -> bool:
        """Можно ли начинать новую работу: баланс положительный и лимиты расходов не исчерпаны."""

        return await self._get_block_error(user_id=user_id) is None

    async def ensure_can_spend(self, user_id: int) -> None:
        """Guard перед созданием задач/автоматизаций. `InsufficientCreditsError` — баланс <= 0,
        `SpendingLimitExceededError` (его подкласс) — исчерпан собственный лимит пользователя."""

        error = await self._get_block_error(user_id=user_id)
        if error is not None:
            raise error

    async def _get_block_error(self, user_id: int) -> InsufficientCreditsError | None:
        if not await self.has_positive_balance(user_id=user_id):
            return InsufficientCreditsError()
        status = await self.get_spending_status(user_id=user_id)
        if status.is_limit_reached:
            return SpendingLimitExceededError()
        return None

    async def get_blocked_user_ids(self, user_ids: list[int]) -> dict[int, str]:
        """Батч-версия `can_spend` для диспатча автоматизаций: `{user_id: причина}` только для
        тех, кому тратить нельзя (`insufficient_credits` / `spending_limit`). Пользователь с лимитом
        стоит одного-двух лёгких запросов, без лимита — ни одного лишнего."""

        if not user_ids:
            return {}
        balances = await self.get_balances(user_ids=user_ids)
        blocked = {
            user_id: 'insufficient_credits'
            for user_id in user_ids
            if balances.get(user_id, 0) <= 0
        }
        async with self.transaction_manager(use_spending_limit_repository=True) as transaction:
            limits = await transaction.spending_limit_repository.get_for_users(user_ids=user_ids)
        for user_id in limits:
            if user_id in blocked:
                continue
            if (await self.get_spending_status(user_id=user_id)).is_limit_reached:
                blocked[user_id] = 'spending_limit'
        return blocked

    async def get_spending_status(self, user_id: int) -> SpendingStatusEntity:
        """Лимиты пользователя и сколько потрачено в текущих сутках/месяце (UTC)."""

        now = datetime.now(tz=timezone.utc)
        day_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        month_start = day_start.replace(day=1)
        async with self.transaction_manager(
            use_spending_limit_repository=True, use_credit_transaction_repository=True,
        ) as transaction:
            limit = await transaction.spending_limit_repository.get_for_user(user_id=user_id)
            daily_limit = limit.daily_limit if limit else None
            monthly_limit = limit.monthly_limit if limit else None
            # Суммы нужны всегда: интерфейс показывает «потрачено» и без лимита.
            spent_today = await transaction.credit_transaction_repository.get_spent_since(
                user_id=user_id, since=day_start,
            )
            spent_this_month = await transaction.credit_transaction_repository.get_spent_since(
                user_id=user_id, since=month_start,
            )
        return SpendingStatusEntity(
            daily_limit=daily_limit,
            monthly_limit=monthly_limit,
            spent_today=spent_today,
            spent_this_month=spent_this_month,
            is_limit_reached=(
                (daily_limit is not None and spent_today >= daily_limit)
                or (monthly_limit is not None and spent_this_month >= monthly_limit)
            ),
        )

    async def set_spending_limits(
        self, user_id: int, daily_limit: int | None, monthly_limit: int | None,
    ) -> SpendingLimitEntity | None:
        async with self.transaction_manager(use_spending_limit_repository=True) as transaction:
            limit = await transaction.spending_limit_repository.set_limits(
                user_id=user_id, daily_limit=daily_limit, monthly_limit=monthly_limit,
            )
            await self.transaction_manager.commit()
        return limit

    async def get_balances(self, user_ids: list[int]) -> dict[int, int]:
        """Batched counterpart of `get_balance` — see `CreditWalletRepository.get_balances`. A
        `user_id` absent from the returned dict has no wallet yet, i.e. balance 0 (same convention
        as `get_balance`); callers should read via `.get(user_id, 0)`."""

        async with self.transaction_manager(use_credit_wallet_repository=True) as transaction:
            return await transaction.credit_wallet_repository.get_balances(user_ids=user_ids)

    async def list_transactions_grouped_by_reference(
        self,
        user_id: int,
        limit: int,
        offset: int,
        filters: TransactionFilters | None = None,
    ) -> tuple[list[CreditTransactionGroupEntity], int]:
        async with self.transaction_manager(use_credit_transaction_repository=True) as transaction:
            items = await transaction.credit_transaction_repository.get_grouped_by_reference(
                user_id=user_id, limit=limit, offset=offset, filters=filters,
            )
            total = await transaction.credit_transaction_repository.count_reference_groups(
                user_id=user_id, filters=filters,
            )
        return items, total

    async def list_transactions(
        self, user_id: int, limit: int, offset: int, filters: TransactionFilters | None = None,
    ) -> tuple[list[CreditTransactionEntity], int]:
        """Плоский журнал пользователя: списания и начисления, новые сверху."""

        async with self.transaction_manager(use_credit_transaction_repository=True) as transaction:
            items = await transaction.credit_transaction_repository.list_for_user(
                user_id=user_id, limit=limit, offset=offset, filters=filters,
            )
            total = await transaction.credit_transaction_repository.count_for_user(
                user_id=user_id, filters=filters,
            )
        return items, total

    async def list_all_transactions(
        self, user_id: int, filters: TransactionFilters | None = None,
    ) -> list[CreditTransactionEntity]:
        """Весь журнал пользователя по фильтрам (для выгрузки): страницами по `EXPORT_PAGE_SIZE`."""

        transactions: list[CreditTransactionEntity] = []
        offset = 0
        while True:
            page, total = await self.list_transactions(
                user_id=user_id, limit=EXPORT_PAGE_SIZE, offset=offset, filters=filters,
            )
            transactions.extend(page)
            offset += EXPORT_PAGE_SIZE
            if offset >= total or not page:
                return transactions

    async def get_user_spending_stats(
        self, user_id: int, date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> SpendingStatsEntity:
        async with self.transaction_manager(use_credit_transaction_repository=True) as transaction:
            return await transaction.credit_transaction_repository.get_spending_stats(
                date_from=date_from, date_to=date_to, user_id=user_id,
            )

    async def get_daily_spending(
        self, user_id: int, date_from: datetime | None = None, date_to: datetime | None = None,
    ) -> list[DailySpendingEntity]:
        async with self.transaction_manager(use_credit_transaction_repository=True) as transaction:
            return await transaction.credit_transaction_repository.get_daily_spending(
                user_id=user_id, date_from=date_from, date_to=date_to,
            )

    async def get_reference_spending(
        self, user_id: int, reference_type: ReferenceType, reference_id: str,
    ) -> ReferenceSpendingEntity:
        async with self.transaction_manager(use_credit_transaction_repository=True) as transaction:
            return await transaction.credit_transaction_repository.get_reference_spending(
                user_id=user_id, reference_type=reference_type, reference_id=reference_id,
            )

    async def list_actions(self) -> list[BillingActionEntity]:
        async with self.transaction_manager(use_billing_action_repository=True) as transaction:
            return await transaction.billing_action_repository.retrieve_all()

    async def update_action_cost(self, action_code: str, base_cost: int) -> BillingActionEntity:
        async with self.transaction_manager(use_billing_action_repository=True) as transaction:
            updated_action = await transaction.billing_action_repository.update_base_cost(
                action_code=action_code, base_cost=base_cost,
            )
            await self.transaction_manager.commit()
        return updated_action

    async def list_pricing_rules(
        self, dimension_code: str | None = None,
    ) -> list[PricingMultiplierRuleEntity]:
        async with self.transaction_manager(
            use_pricing_multiplier_rule_repository=True,
        ) as transaction:
            if dimension_code is not None:
                return await transaction.pricing_multiplier_rule_repository.get_by_dimension_code(
                    dimension_code=dimension_code,
                )
            return await transaction.pricing_multiplier_rule_repository.retrieve_all()

    async def create_pricing_rule(
        self, dimension_code: str, value_min: int, value_max: int, multiplier: Decimal,
    ) -> PricingMultiplierRuleEntity:
        async with self.transaction_manager(
            use_pricing_multiplier_rule_repository=True,
        ) as transaction:
            has_overlap = await transaction.pricing_multiplier_rule_repository.has_overlap(
                dimension_code=dimension_code, value_min=value_min, value_max=value_max,
            )
            if has_overlap:
                raise OverlappingPricingRuleError

            created_rule = await transaction.pricing_multiplier_rule_repository.create(
                entity=PricingMultiplierRuleEntity(
                    dimension_code=dimension_code,
                    value_min=value_min,
                    value_max=value_max,
                    multiplier=multiplier,
                ),
            )
            await self.transaction_manager.commit()
        return created_rule

    async def delete_pricing_rule(self, rule_id: int) -> None:
        async with self.transaction_manager(
            use_pricing_multiplier_rule_repository=True,
        ) as transaction:
            await transaction.pricing_multiplier_rule_repository.delete(entity_id=rule_id)
            await self.transaction_manager.commit()
