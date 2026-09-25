from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.automation.src.enums import AutomationStatus


class AutomationEntity(BaseModel):
    id: Optional[UUID] = Field(default=None, description='Идентификатор автоматизации')
    user_id: Optional[int] = Field(
        default=None,
        description='Идентификатор пользователя, создавшего автоматизацию',
    )
    marketplace: Optional[Marketplace] = Field(default=None, description='Маркетплейс товара')
    input_value: Optional[str] = Field(default=None, description='Ссылка или артикул товара')
    article: Optional[str] = Field(
        default=None,
        description='Артикул товара, извлечённый из input_value для проверки дублей; None, если '
        'формат ссылки не распознан',
    )
    status: Optional[AutomationStatus] = Field(default=None, description='Статус автоматизации')
    price_drop_threshold_percent: Optional[int] = Field(
        default=None,
        description='Порог падения цены в процентах от базовой, при котором фиксируется '
        'достижение порога уведомления',
    )
    check_frequency_minutes: Optional[int] = Field(
        default=None,
        description='Периодичность проверки в минутах',
    )
    history_retention_days: Optional[int] = Field(
        default=None,
        description='Срок хранения истории проверок в днях',
    )
    baseline_price_kopecks: Optional[int] = Field(
        default=None,
        description='Базовая цена без скидки в копейках, точка отсчёта для сравнения',
    )
    baseline_discounted_price_kopecks: Optional[int] = Field(
        default=None,
        description='Базовая цена со скидкой (по карте) в копейках, точка отсчёта для сравнения',
    )
    baseline_original_price_kopecks: Optional[int] = Field(
        default=None,
        description='Базовая перечёркнутая цена в копейках, точка отсчёта для сравнения',
    )
    in_stock: Optional[bool] = Field(
        default=None,
        description='Наличие товара по последней завершённой проверке; None — проверок ещё не было',
    )
    next_check_at: Optional[datetime] = Field(
        default=None,
        description='Момент следующей плановой проверки',
    )
    pending_task_id: Optional[UUID] = Field(
        default=None,
        description='Идентификатор задачи текущей проверки, ещё не завершённой',
    )
    last_checked_at: Optional[datetime] = Field(
        default=None,
        description='Момент последней завершённой проверки',
    )
    last_check_error: Optional[str] = Field(
        default=None,
        description='Причина провала последней проверки (проверка, не автоматизация в целом)',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания автоматизации')
    updated_at: Optional[datetime] = Field(
        default=None,
        description='Время последнего изменения автоматизации',
    )


class AutomationCheckLogEntity(BaseModel):
    id: Optional[int] = Field(default=None, description='Идентификатор строки лога проверки')
    automation_id: Optional[UUID] = Field(
        default=None,
        description='Идентификатор родительской автоматизации',
    )
    succeeded: Optional[bool] = Field(default=None, description='Проверка завершилась успешно')
    error_message: Optional[str] = Field(
        default=None,
        description='Причина провала проверки; None при успехе',
    )
    snapshot: Optional[dict] = Field(
        default=None,
        description='Снимок всех отслеживаемых полей карточки на момент тика (только при успехе)',
    )
    changes: Optional[list[dict]] = Field(
        default=None,
        description='Поля, изменившиеся относительно предыдущего успешного тика: список '
        '{field, old_value, new_value, threshold_breached}',
    )
    has_changes: Optional[bool] = Field(
        default=None,
        description='Хотя бы одно поле изменилось относительно предыдущего тика',
    )
    threshold_breached: Optional[bool] = Field(
        default=None,
        description='Хотя бы одно из изменений в changes упало относительно базовой цены не менее '
        'чем на price_drop_threshold_percent',
    )
    checked_at: Optional[datetime] = Field(default=None, description='Момент проверки')
