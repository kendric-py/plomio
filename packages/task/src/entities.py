from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.task.src.enums import ParseType, TaskItemStatus, TaskStatus


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
    error_reason: Optional[str] = Field(default=None, description='Причина общего провала задачи')
    user_id: Optional[int] = Field(
        default=None,
        description='Идентификатор пользователя, поставившего задачу',
    )
    created_at: Optional[datetime] = Field(default=None, description='Время создания задачи')
    updated_at: Optional[datetime] = Field(
        default=None,
        description='Время последнего изменения задачи',
    )


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
