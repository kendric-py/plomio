import math
from decimal import Decimal

from core.exceptions import ObjectNotFoundError
from core.transaction_manager import AsyncTransactionManager
from packages.billing.src.entities import (
    BillingActionEntity,
    CreditTransactionEntity,
    CreditTransactionGroupEntity,
    PricingMultiplierRuleEntity,
)
from packages.billing.src.enums import ReferenceType
from packages.billing.src.exceptions import OverlappingPricingRuleError


class BillingService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def charge(
        self,
        user_id: int,
        action_code: str,
        quantity: int = 1,
        dimension_code: str | None = None,
        dimension_value: int | None = None,
        reference_type: ReferenceType | None = None,
        reference_id: str | None = None,
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
                    },
                ),
            )
            await self.transaction_manager.commit()
        return created_transaction

    async def grant(
        self, user_id: int, amount: int, admin_id: int, comment: str | None,
    ) -> CreditTransactionEntity:
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

    async def get_balance(self, user_id: int) -> int:
        async with self.transaction_manager(use_credit_wallet_repository=True) as transaction:
            try:
                wallet = await transaction.credit_wallet_repository.get_by_id(entity_id=user_id)
            except ObjectNotFoundError:
                return 0
        return wallet.balance

    async def has_positive_balance(self, user_id: int) -> bool:
        return await self.get_balance(user_id=user_id) > 0

    async def get_balances(self, user_ids: list[int]) -> dict[int, int]:
        """Batched counterpart of `get_balance` — see `CreditWalletRepository.get_balances`. A
        `user_id` absent from the returned dict has no wallet yet, i.e. balance 0 (same convention
        as `get_balance`); callers should read via `.get(user_id, 0)`."""

        async with self.transaction_manager(use_credit_wallet_repository=True) as transaction:
            return await transaction.credit_wallet_repository.get_balances(user_ids=user_ids)

    async def list_transactions_grouped_by_reference(
        self, user_id: int, limit: int, offset: int,
    ) -> tuple[list[CreditTransactionGroupEntity], int]:
        async with self.transaction_manager(use_credit_transaction_repository=True) as transaction:
            items = await transaction.credit_transaction_repository.get_grouped_by_reference(
                user_id=user_id, limit=limit, offset=offset,
            )
            total = await transaction.credit_transaction_repository.count_reference_groups(
                user_id=user_id,
            )
        return items, total
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
