from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.automation.src.enums import AutomationStatus, PriceField


class CreateAutomationRequest(BaseModel):
    marketplace: Marketplace = Field(description='Маркетплейс товара')
    input_value: str = Field(description='Ссылка или артикул товара')
    price_drop_threshold_percent: int = Field(
        description='Порог падения цены в процентах от базовой, при котором фиксируется '
        'достижение порога уведомления',
        ge=1,
        le=100,
    )
    check_frequency_minutes: int = Field(description='Периодичность проверки в минутах', gt=0)
    history_retention_days: int = Field(description='Срок хранения истории проверок в днях', gt=0)


class UpdateBaselineRequest(BaseModel):
    price_kopecks: int | None = Field(
        default=None,
        description='Новая базовая цена без скидки в копейках',
        ge=0,
    )
    discounted_price_kopecks: int | None = Field(
        default=None,
        description='Новая базовая цена со скидкой (по карте) в копейках',
        ge=0,
    )
    original_price_kopecks: int | None = Field(
        default=None,
        description='Новая базовая перечёркнутая цена в копейках',
        ge=0,
    )


class AutomationResponse(BaseModel):
    id: UUID = Field(description='Идентификатор автоматизации')
    marketplace: Marketplace = Field(description='Маркетплейс товара')
    input_value: str = Field(description='Ссылка или артикул товара')
    status: AutomationStatus = Field(description='Статус автоматизации')
    price_drop_threshold_percent: int = Field(description='Порог падения цены в процентах')
    check_frequency_minutes: int = Field(description='Периодичность проверки в минутах')
    history_retention_days: int = Field(description='Срок хранения истории проверок в днях')
    baseline_price_kopecks: int | None = Field(description='Базовая цена без скидки в копейках')
    baseline_discounted_price_kopecks: int | None = Field(
        description='Базовая цена со скидкой в копейках',
    )
    baseline_original_price_kopecks: int | None = Field(
        description='Базовая перечёркнутая цена в копейках',
    )
    next_check_at: datetime = Field(description='Момент следующей плановой проверки')
    last_checked_at: datetime | None = Field(description='Момент последней завершённой проверки')
    last_check_error: str | None = Field(description='Причина провала последней проверки')
    created_at: datetime = Field(description='Время создания автоматизации')


class PaginationMeta(BaseModel):
    total: int = Field(description='Общее количество элементов')
    limit: int = Field(description='Размер страницы')
    offset: int = Field(description='Смещение страницы')


class AutomationListResponse(BaseModel):
    items: list[AutomationResponse] = Field(description='Автоматизации пользователя на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class PriceChangeItem(BaseModel):
    field: PriceField = Field(description='Какое из трёх ценовых полей изменилось')
    old_value: int = Field(description='Предыдущее значение в копейках')
    new_value: int = Field(description='Новое значение в копейках')
    threshold_breached: bool = Field(description='Достигнут порог для уведомления по этому полю')


class AutomationHistoryResponse(BaseModel):
    id: int = Field(description='Идентификатор строки истории')
    changes: list[PriceChangeItem] = Field(
        description='Все поля, изменившиеся за эту проверку',
    )
    threshold_breached: bool = Field(
        description='Достигнут порог для уведомления хотя бы по одному из изменений',
    )
    detected_at: datetime = Field(description='Момент фиксации изменения')


class AutomationHistoryListResponse(BaseModel):
    items: list[AutomationHistoryResponse] = Field(description='История изменений на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')
