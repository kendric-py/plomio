from uuid import UUID

from pydantic import BaseModel, Field

from apps.api.src.routers.automation.schema import AutomationDetailResponse, AutomationResponse
from apps.api.src.routers.schema import PaginationMeta
from apps.api.src.routers.task_admin.schema import AdminTaskNotificationResponse, TaskStatusCounts


class AdminAutomationItemResponse(AutomationResponse):
    """Строка админского списка: автоматизация + владелец, текущая проверка и признак просрочки."""

    user_id: int = Field(description='Владелец автоматизации')
    pending_task_id: UUID | None = Field(
        description='Проверочная задача, выполняемая сейчас; null — проверка не идёт',
    )
    is_overdue: bool = Field(
        description='Просрочена: активна, срок проверки наступил, а диспетчер ещё не взял её',
    )


class AdminAutomationListResponse(BaseModel):
    """Ответ `GET /api/admin/automations/` — автоматизации всех пользователей."""

    items: list[AdminAutomationItemResponse] = Field(description='Автоматизации на странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')


class AdminAutomationResponse(AutomationDetailResponse):
    """Автоматизация для админа: форма пользовательской детали + владелец и текущая проверка."""

    user_id: int = Field(description='Владелец автоматизации')
    pending_task_id: UUID | None = Field(
        description='Проверочная задача, выполняемая сейчас; null — проверка не идёт',
    )
    is_overdue: bool = Field(description='Просрочена: активна, срок проверки наступил')


class AutomationsStateSummary(BaseModel):
    active: int = Field(description='Активные автоматизации (на сейчас)')
    paused: int = Field(description='Приостановленные автоматизации (на сейчас)')
    overdue: int = Field(
        description='Просроченные: активные, у которых срок проверки наступил, а диспетчер ещё не '
        'поставил проверку (на сейчас)',
    )
    with_error: int = Field(description='С ошибкой последней проверки (на сейчас)')
    checks: int = Field(description='Тиков проверок за период')
    failed_checks: int = Field(description='Неудачных тиков проверок за период')


class AdminAutomationSummaryResponse(BaseModel):
    """Сводка раздела «Автоматизации»: состояние автоматизаций и их проверочные задачи за период."""

    automations: AutomationsStateSummary = Field(description='Автоматизации')
    check_tasks: TaskStatusCounts = Field(description='Проверочные задачи автоматизаций за период')


class AdminAutomationNotificationListResponse(BaseModel):
    """Вся история уведомлений автоматизации, новые сверху."""

    items: list[AdminTaskNotificationResponse] = Field(description='Уведомления на странице')
    meta: PaginationMeta = Field(description='Метаданные пагинации')
