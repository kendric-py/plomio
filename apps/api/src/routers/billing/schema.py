from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, Field, model_validator

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


class PricingResponse(BaseModel):
    """Публичный прайс (`GET /api/billing/pricing`): каталог действий и множители — всё, что нужно
    клиенту, чтобы прикинуть стоимость до отправки. Те же сущности, что в админском CRUD."""

    actions: list[BillingActionResponse] = Field(description='Каталог тарифицируемых действий')
    rules: list[PricingMultiplierRuleResponse] = Field(description='Правила множителей стоимости')


class CreditTransactionResponse(BaseModel):
    """Строка журнала списаний/начислений — ответ `POST /api/admin/billing/users/{user_id}/grant`."""

    id: int = Field(description='Идентификатор строки журнала')
    amount: int = Field(
        description='Сумма транзакции: отрицательная — списание, положительная — начисление',
    )
    balance_after: int = Field(description='Баланс пользователя сразу после этой транзакции')
    action_code: str | None = Field(
        description='Код тарифицированного действия; null для ручного начисления админом',
    )
    reference_type: ReferenceType | None = Field(
        description='Тип сущности, породившей списание (task/automation/direct)',
    )
    reference_id: str | None = Field(description='Идентификатор сущности-источника')
    transaction_metadata: dict | None = Field(description='Расшифровка расчёта либо комментарий')
    created_at: datetime = Field(description='Время создания транзакции')


class DailySpendingResponse(BaseModel):
    """Траты за один день (UTC), в кредитах, положительные числа."""

    day: date = Field(description='День (UTC), YYYY-MM-DD')
    total_spent: int = Field(description='Всего за день')
    tasks_spent: int = Field(description='Задачи (без проверок автоматизаций)')
    automations_spent: int = Field(description='Автоматизации: создание и проверки')
    direct_spent: int = Field(description='Прямые запросы')


class CreditTransactionGroupResponse(BaseModel):
    """Списания по одной сущности-источнику. Вложен в `CreditTransactionGroupListResponse.items`
    (`GET /api/billing/transactions/by-reference`)."""

    reference_type: ReferenceType = Field(
        description='Тип сущности, породившей списания (task/automation/direct)',
    )
    reference_id: str = Field(description='Идентификатор сущности-источника')
    total_amount: int = Field(description='Сумма транзакций группы; списания — отрицательные')
    transactions_count: int = Field(description='Число транзакций в группе')
    first_at: datetime = Field(description='Время первой транзакции группы')
    last_at: datetime = Field(description='Время последней транзакции группы')


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


class SpendingStatsResponse(BaseModel):
    """Ответ `GET /api/admin/billing/stats` — траты всех пользователей за период, в кредитах."""

    total_spent: int = Field(description='Всего потрачено (включая direct-запросы)')
    tasks_spent: int = Field(description='Потрачено на задачи')
    automations_spent: int = Field(description='Потрачено на автоматизации')
    direct_spent: int = Field(description='Потрачено на direct-запросы')
    date_from: datetime | None = Field(description='Начало периода (включительно), UTC')
    date_to: datetime | None = Field(description='Конец периода (включительно), UTC')


class CreditTransactionGroupListResponse(BaseModel):
    """Ответ `GET /api/billing/transactions/by-reference` — постраничные траты пользователя,
    сгруппированные по сущности-источнику."""

    items: list[CreditTransactionGroupResponse] = Field(description='Группы на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class CreditTransactionListResponse(BaseModel):
    """Ответ `GET /api/billing/transactions` — плоский журнал: списания и начисления."""

    items: list[CreditTransactionResponse] = Field(description='Транзакции текущей страницы')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class DailySpendingListResponse(BaseModel):
    """Ответ `GET /api/billing/stats/daily` — траты по дням, без пустых дней."""

    items: list[DailySpendingResponse] = Field(description='Дни со списаниями, по возрастанию')
    date_from: datetime | None = Field(description='Начало периода (включительно), UTC')
    date_to: datetime | None = Field(description='Конец периода (включительно), UTC')


class ReferenceSpendingResponse(BaseModel):
    """Ответ `GET /api/billing/spending/{reference_type}/{reference_id}`."""

    total_spent: int = Field(description='Потрачено на сущность, в кредитах (положительное число)')
    transactions_count: int = Field(description='Число списаний')


class SpendingLimitsResponse(BaseModel):
    """Лимиты расходов пользователя и сколько уже потрачено в текущих периодах (UTC)."""

    daily_limit: int | None = Field(description='Лимит за сутки, кредитов; null — не задан')
    monthly_limit: int | None = Field(description='Лимит за календарный месяц; null — не задан')
    spent_today: int = Field(description='Потрачено с начала текущих суток')
    spent_this_month: int = Field(description='Потрачено с начала текущего месяца')
    is_limit_reached: bool = Field(
        description='Лимит исчерпан: новые задачи, автоматизации и прямые запросы заблокированы',
    )


class UpdateSpendingLimitsRequest(BaseModel):
    """Тело `PUT /api/billing/limits` — оба лимита заменяются целиком; `null` снимает лимит."""

    daily_limit: int | None = Field(default=None, ge=1, description='Лимит за сутки, кредитов')
    monthly_limit: int | None = Field(default=None, ge=1, description='Лимит за месяц, кредитов')

    @model_validator(mode='after')
    def _daily_not_above_monthly(self) -> 'UpdateSpendingLimitsRequest':
        if (
            self.daily_limit is not None
            and self.monthly_limit is not None
            and self.daily_limit > self.monthly_limit
        ):
            raise ValueError('daily_limit must not exceed monthly_limit')
        return self
