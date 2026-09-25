from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from packages.billing.src.enums import ReferenceType

# --- Переиспользуемые сущности ---


class BillingActionResponse(BaseModel):
    """Строка каталога тарифицируемых действий (`GET`/`PATCH /api/admin/billing/actions`)."""

    id: int = Field(description='Идентификатор строки каталога действий')
    action_code: str = Field(description='Код тарифицируемого действия')
    description: str = Field(description='Описание действия для админки')
    base_cost: int = Field(description='Базовая цена за единицу в кредитах; 0 — действие бесплатно')
    unit_label: str = Field(description='Что считается единицей действия')


class PricingMultiplierRuleResponse(BaseModel):
    """Правило множителя стоимости по диапазону значения измерения
    (`GET`/`POST /api/admin/billing/pricing-rules`)."""

    id: int = Field(description='Идентификатор правила множителя')
    dimension_code: str = Field(description='Код измерения (например, task_priority)')
    value_min: int = Field(description='Нижняя граница диапазона (включительно)')
    value_max: int = Field(description='Верхняя граница диапазона (включительно)')
    multiplier: Decimal = Field(description='На что умножается базовая цена в этом диапазоне')


class CreditTransactionResponse(BaseModel):
    """Одна строка журнала списаний/начислений. Вложен в `CreditTransactionListResponse.items`
    (`GET /api/billing/transactions`)."""

    id: int = Field(description='Идентификатор строки журнала')
    amount: int = Field(
        description='Сумма транзакции: отрицательная — списание, положительная — начисление',
    )
    balance_after: int = Field(description='Баланс пользователя сразу после этой транзакции')
    action_code: str | None = Field(
        description='Код тарифицированного действия; null для ручного начисления админом',
    )
    reference_type: ReferenceType | None = Field(
        description='Тип сущности, породившей списание (task/automation)',
    )
    reference_id: str | None = Field(description='Идентификатор сущности-источника')
    transaction_metadata: dict | None = Field(description='Расшифровка расчёта либо комментарий')
    created_at: datetime = Field(description='Время создания транзакции')


# --- Запросы ---


class UpdateActionCostRequest(BaseModel):
    """Тело запроса `PATCH /api/admin/billing/actions/{action_code}`."""

    base_cost: int = Field(description='Новая базовая цена за единицу в кредитах', ge=0)


class CreatePricingRuleRequest(BaseModel):
    """Тело запроса `POST /api/admin/billing/pricing-rules`."""

    dimension_code: str = Field(description='Код измерения (например, task_priority)')
    value_min: int = Field(description='Нижняя граница диапазона (включительно)')
    value_max: int = Field(description='Верхняя граница диапазона (включительно)')
    multiplier: Decimal = Field(description='На что умножается базовая цена в этом диапазоне', gt=0)


class GrantCreditsRequest(BaseModel):
    """Тело запроса `POST /api/admin/billing/users/{user_id}/grant`."""

    amount: int = Field(description='Сколько кредитов начислить пользователю', gt=0)
    comment: str | None = Field(default=None, description='Комментарий администратора')


# --- Ответы ---


class BillingActionListResponse(BaseModel):
    """Ответ `GET /api/admin/billing/actions`."""

    items: list[BillingActionResponse] = Field(description='Каталог тарифицируемых действий')


class PricingMultiplierRuleListResponse(BaseModel):
    """Ответ `GET /api/admin/billing/pricing-rules`."""

    items: list[PricingMultiplierRuleResponse] = Field(description='Правила множителей стоимости')


class BalanceResponse(BaseModel):
    """Ответ `GET /api/billing/balance`."""

    balance: int = Field(description='Текущий баланс кредитов пользователя')


class CreditTransactionListResponse(BaseModel):
    """Ответ `GET /api/billing/transactions` — постраничный журнал трат пользователя."""

    items: list[CreditTransactionResponse] = Field(description='Транзакции на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')
