from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.task.src.enums import ParseType, TaskItemStatus, TaskPurpose, TaskStatus


class TaskEntity(BaseModel):
    id: Optional[UUID] = Field(default=None, description='Идентификатор задачи')
    parse_type: Optional[ParseType] = Field(default=None, description='Тип парсинга')
    marketplace: Optional[Marketplace] = Field(default=None, description='Маркетплейс задачи')
    status: Optional[TaskStatus] = Field(default=None, description='Статус задачи')
    priority: Optional[int] = Field(default=None, description='Приоритет от 1 (высший) до 10')
    queue_expires_at: Optional[datetime] = Field(
        default=None,
        description='Момент, до которого задача должна быть взята в работу (TTL)',
    )
    result_limit: Optional[int] = Field(
        default=None,
        description='Общий лимит результатов по задаче',
    )
    claimed_by: Optional[str] = Field(
        default=None,
        description='Идентификатор воркера, держащего lease',
    )
    claimed_at: Optional[datetime] = Field(
        default=None,
        description='Момент захвата задачи воркером',
    )
    lease_expires_at: Optional[datetime] = Field(
        default=None,
        description='Момент истечения аренды задачи воркером',
    )
    started_at: Optional[datetime] = Field(
        default=None,
        description='Момент первого захвата задачи воркером (начало парсинга); в отличие от '
        'claimed_at не сбрасывается при потере лизы и повторном захвате',
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        description='Момент, когда задача пришла к терминальному статусу (успех/провал/отмена)',
    )
    error_reason: Optional[str] = Field(default=None, description='Причина общего провала задачи')
    user_id: Optional[int] = Field(
        default=None,
        description='Идентификатор пользователя, поставившего задачу',
    )
    automation_id: Optional[UUID] = Field(
        default=None,
        description='Идентификатор автоматизации, создавшей эту задачу (проверочная задача, не '
        'пользовательская); не выставляется при обычном создании задачи',
    )
    pricing_dimension_code: Optional[str] = Field(
        default=None,
        description='Код измерения billing-множителя, применённого к результатам этой задачи '
        '(например, task_priority или automation_check_frequency); снэпшот на момент создания',
    )
    pricing_dimension_value: Optional[int] = Field(
        default=None,
        description='Значение измерения billing-множителя на момент создания задачи (приоритет '
        'или частота проверки автоматизации)',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания задачи')
    updated_at: Optional[datetime] = Field(
        default=None,
        description='Время последнего изменения задачи',
    )


class AdminTaskFilters(BaseModel):
    """Фильтры админского списка задач; комбинируются через AND, `None` — не задан. Период —
    по `created_at`, границы включительные."""

    task_id: Optional[UUID] = Field(default=None, description='Точное совпадение ID задачи')
    item_id: Optional[UUID] = Field(
        default=None, description='ID элемента задачи — находит задачу-родителя',
    )
    automation_id: Optional[UUID] = Field(
        default=None, description='ID автоматизации — её проверочные задачи',
    )
    purpose: Optional[TaskPurpose] = Field(
        default=None, description='Пользовательская задача или проверка автоматизации',
    )
    user_id: Optional[int] = Field(default=None, description='Автор задачи')
    marketplace: Optional[Marketplace] = Field(default=None, description='Маркетплейс')
    status: Optional[TaskStatus] = Field(default=None, description='Статус задачи')
    parse_type: Optional[ParseType] = Field(default=None, description='Тип парсинга')
    date_from: Optional[datetime] = Field(default=None, description='Начало периода')
    date_to: Optional[datetime] = Field(default=None, description='Конец периода')


class TaskItemEntity(BaseModel):
    id: Optional[UUID] = Field(default=None, description='Идентификатор элемента задачи')
    task_id: Optional[UUID] = Field(
        default=None,
        description='Идентификатор родительской задачи',
    )
    position: Optional[int] = Field(default=None, description='Порядковый номер входа в задаче')
    input_value: Optional[str] = Field(default=None, description='Ссылка или поисковый запрос')
    status: Optional[TaskItemStatus] = Field(default=None, description='Статус элемента задачи')
    cursor: Optional[dict] = Field(
        default=None,
        description='Непрозрачное для домена состояние возобновления пагинации',
    )
    result_count: Optional[int] = Field(
        default=None,
        description='Количество спарсенных результатов',
    )
    error_reason: Optional[str] = Field(default=None, description='Причина провала элемента задачи')
    created_at: Optional[datetime] = Field(default=None, description='Время создания элемента')
    updated_at: Optional[datetime] = Field(
        default=None,
        description='Время последнего изменения элемента',
    )
