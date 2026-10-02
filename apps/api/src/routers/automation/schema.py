from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.src.routers.schema import PaginationMeta
from core.enums import Marketplace
from packages.automation.src.enums import AutomationStatus, TrackedField


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
    article: str | None = Field(
        description='Артикул товара, извлечённый из input_value; None, если формат не распознан',
    )
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
    in_stock: bool | None = Field(
        description='Наличие товара по последней завершённой проверке; None — проверок ещё не было',
    )
    name: str | None = Field(
        description='Название товара по последней успешной проверке; None — успешных проверок не было',
    )
    price_kopecks: int | None = Field(
        description='Текущая цена без скидки в копейках (последняя успешная проверка)',
    )
    discounted_price_kopecks: int | None = Field(
        description='Текущая цена со скидкой в копейках (последняя успешная проверка)',
    )
    original_price_kopecks: int | None = Field(
        description='Текущая перечёркнутая цена в копейках (последняя успешная проверка)',
    )
    next_check_at: datetime = Field(description='Момент следующей плановой проверки')
    last_checked_at: datetime | None = Field(description='Момент последней завершённой проверки')
    last_check_error: str | None = Field(description='Причина провала последней проверки')
    created_at: datetime = Field(description='Время создания автоматизации')


class AutomationDetailResponse(AutomationResponse):
    """GET /api/automations/{id} — та же форма, что AutomationResponse, плюс last_info (не входит
    в остальные ручки, где отдаётся AutomationResponse: create/list/pause/resume/update_baseline
    не делают лишний запрос за снимком ради поля, которое там никто не читает)."""

    last_info: dict | None = Field(
        description='Снимок всех восьми отслеживаемых полей карточки на момент последней '
        'успешной проверки; null, если ни одна проверка ещё не завершилась успехом',
    )


class AutomationListResponse(BaseModel):
    items: list[AutomationResponse] = Field(
        description='Автоматизации пользователя на текущей странице',
    )
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class TrackedFieldChangeItem(BaseModel):
    field: TrackedField = Field(description='Какое из отслеживаемых полей карточки изменилось')
    old_value: int | bool | str | float | None = Field(
        description='Предыдущее значение (по снимку предыдущего успешного тика)',
    )
    new_value: int | bool | str | float | None = Field(description='Новое значение')
    threshold_breached: bool = Field(
        description='Достигнут порог падения цены относительно базовой (для IN_STOCK — товар '
        'снова появился в наличии)',
    )


class AutomationHistoryResponse(BaseModel):
    """Один тик проверки автоматизации — успешный, неуспешный или без изменений
    (GET /api/automations/{id}/history)."""

    id: int = Field(description='Идентификатор строки лога проверки')
    succeeded: bool = Field(description='Проверка завершилась успешно')
    error_message: str | None = Field(description='Причина провала проверки; null при успехе')
    changes: list[TrackedFieldChangeItem] = Field(
        description='Поля, изменившиеся относительно предыдущего успешного тика',
    )
    has_changes: bool = Field(
        description='Хотя бы одно поле изменилось относительно предыдущего тика',
    )
    threshold_breached: bool = Field(
        description='Достигнут порог падения цены относительно базовой хотя бы по одному изменению',
    )
    checked_at: datetime = Field(description='Момент проверки')


class PricePointResponse(BaseModel):
    at: datetime = Field(description='Момент, на который верно состояние карточки в точке (UTC)')
    price_kopecks: int | None = Field(description='Цена без скидки в копейках')
    discounted_price_kopecks: int | None = Field(description='Цена со скидкой в копейках')
    original_price_kopecks: int | None = Field(description='Перечёркнутая цена в копейках')
    in_stock: bool | None = Field(description='Наличие товара на этот момент')
    changed: bool = Field(description='Цена в этой точке отличается от предыдущей точки')


class PriceDynamicsResponse(BaseModel):
    date_from: datetime = Field(description='Начало применённого диапазона (UTC)')
    date_to: datetime = Field(description='Конец применённого диапазона (UTC)')
    step_seconds: int = Field(description='Шаг сетки точек в секундах (зависит от периода)')
    items: list[PricePointResponse] = Field(
        description='Регулярный ряд по возрастанию времени: цена на конец каждого шага сетки '
        '(держится до следующего изменения, без пропусков)',
    )


class PriceChangeFrequencyPointResponse(BaseModel):
    bucket_start: datetime = Field(description='Начало корзины времени (UTC)')
    changes_count: int = Field(description='Сколько раз за корзину изменилась цена')


class PriceChangeFrequencyResponse(BaseModel):
    date_from: datetime = Field(description='Начало применённого диапазона (UTC)')
    date_to: datetime = Field(description='Конец применённого диапазона (UTC)')
    step_seconds: int = Field(
        description='Ширина корзины в секундах — тот же шаг, что у динамики на этом диапазоне',
    )
    items: list[PriceChangeFrequencyPointResponse] = Field(
        description='Корзины по возрастанию времени без пропусков; без изменений — 0',
    )


class AutomationHistoryListResponse(BaseModel):
    items: list[AutomationHistoryResponse] = Field(description='Тики проверок на текущей странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class AutomationRecentCheckResponse(AutomationHistoryResponse):
    """Тик проверки в составе GET /api/automations/with-history — тот же набор полей, что
    AutomationHistoryResponse, плюс snapshot (не отдаётся в GET /{id}/history)."""

    snapshot: dict | None = Field(
        description='Снимок всех восьми отслеживаемых полей карточки на момент этого тика; null '
        'при неуспешном тике',
    )


class AutomationWithHistoryResponse(AutomationResponse):
    recent_checks: list[AutomationRecentCheckResponse] = Field(
        description='Последние (не более 5) тики проверок этой автоматизации, новые сначала',
    )


class AutomationWithHistoryListResponse(BaseModel):
    items: list[AutomationWithHistoryResponse] = Field(
        description='Автоматизации пользователя на текущей странице, каждая — с последними '
        'проверками',
    )
    meta: PaginationMeta = Field(description='Метаданные пагинации')
