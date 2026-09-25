from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field

from packages.billing.src.enums import ReferenceType


class BillingActionEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор строки каталога действий')
    action_code: Optional[str] = Field(default=None, description='Код тарифицируемого действия')
    description: Optional[str] = Field(default=None, description='Описание действия для админки')
    base_cost: Optional[int] = Field(
        default=None,
        description='Базовая цена за единицу в кредитах; 0 — действие бесплатно',
    )
    unit_label: Optional[str] = Field(
        default=None,
        description='Что считается единицей действия (для UI, не участвует в расчётах)',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания строки')
    updated_at: Optional[datetime] = Field(default=None, description='Время последнего изменения')


class PricingMultiplierRuleEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор правила множителя')
    dimension_code: Optional[str] = Field(
        default=None,
        description='Код измерения (например, task_priority, automation_check_frequency)',
    )
    value_min: Optional[int] = Field(
        default=None,
        description='Нижняя граница диапазона значения измерения (включительно)',
    )
    value_max: Optional[int] = Field(
        default=None,
        description='Верхняя граница диапазона значения измерения (включительно)',
    )
    multiplier: Optional[Decimal] = Field(
        default=None,
        description='На что умножается базовая цена действия в этом диапазоне',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания правила')


class CreditWalletEntity(BaseModel):
    user_id: Optional[int] = Field(default=None, description='Идентификатор пользователя')
    balance: Optional[int] = Field(
        default=None,
        description='Текущий баланс кредитов пользователя; может быть отрицательным',
    )
    updated_at: Optional[datetime] = Field(
        default=None,
        description='Время последнего изменения баланса',
    )


class CreditTransactionEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор строки журнала')
    user_id: Optional[int] = Field(default=None, description='Идентификатор пользователя')
    amount: Optional[int] = Field(
        default=None,
        description='Сумма транзакции: отрицательная — списание, положительная — начисление',
    )
    balance_after: Optional[int] = Field(
        default=None,
        description='Баланс пользователя сразу после этой транзакции',
    )
    action_code: Optional[str] = Field(
        default=None,
        description='Код тарифицированного действия; None для ручного начисления админом',
    )
    reference_type: Optional[ReferenceType] = Field(
        default=None,
        description='Тип сущности, породившей списание (task/automation)',
    )
    reference_id: Optional[str] = Field(
        default=None,
        description='Идентификатор сущности-источника списания',
    )
    transaction_metadata: Optional[dict] = Field(
        default=None,
        description='Расшифровка расчёта: quantity/unit_cost/multiplier/dimension_code/'
        'dimension_value, либо комментарий администратора для ручного начисления',
    )
    granted_by_admin_id: Optional[int] = Field(
        default=None,
        description='Идентификатор администратора, выдавшего начисление вручную',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания транзакции')
