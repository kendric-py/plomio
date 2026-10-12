from datetime import datetime

from pydantic import BaseModel, Field

from apps.api.src.routers.automation_admin.schema import AutomationsStateSummary
from apps.api.src.routers.overview.enums import OverviewWindow
from apps.api.src.routers.sessions.schema import MarketplaceSessionPool
from core.enums import BucketUnit


# --- Переиспользуемые сущности


class OverviewPoint(BaseModel):
    """Одна точка временного ряда; `values` содержит все ключи ряда (нули для пустых интервалов)."""

    bucket: datetime = Field(description='Начало интервала (UTC)')
    values: dict[str, int] = Field(description='Значения по ключам ряда в этом интервале')


class WorkerGroupHealth(BaseModel):
    online: int = Field(description='Воркеры, присылающие heartbeat вовремя')
    missed: int = Field(description='Воркеры, пропустившие heartbeat')


# --- Блоки сводки


class OverviewWorkers(BaseModel):
    parser: WorkerGroupHealth = Field(description='Воркеры-парсеры')
    sessions: WorkerGroupHealth = Field(description='Воркеры генерации сессий')


class OverviewTasks(BaseModel):
    queued: int = Field(description='В очереди сейчас (пользовательские и проверочные задачи)')
    running: int = Field(description='Выполняются сейчас')
    succeeded: int = Field(description='Успешно завершены за окно')
    failed: int = Field(description='Завершены с ошибкой за окно')
    expired: int = Field(description='Просрочены за окно (не взяты в работу до конца TTL очереди)')
    series: list[OverviewPoint] = Field(
        description='Завершённые задачи по интервалам: ключи `SUCCEEDED`, `FAILED`, `EXPIRED`',
    )


class OverviewGenerations(BaseModel):
    total: int = Field(description='Генераций сессий за окно')
    success_percent: int = Field(description='Доля успешных за окно, % (антибот не исключается)')
    by_outcome: dict[str, int] = Field(description='Число генераций за окно по итогам')
    series: list[OverviewPoint] = Field(
        description='Генерации по интервалам: ключи — итоги (`success`, `validation`, ...)',
    )
    pools: list[MarketplaceSessionPool] = Field(
        description='Пул сессий и последние 50 генераций по маркетплейсам',
    )


class OverviewWorstProxy(BaseModel):
    proxy_id: int = Field(description='Идентификатор прокси')
    host: str = Field(description='Хост прокси')
    port: int = Field(description='Порт прокси')
    success: int = Field(description='Успешных генераций за окно')
    total: int = Field(description='Всего генераций за окно (без антибот-ошибок)')
    success_percent: int = Field(description='Доля успеха, %')


class OverviewProxies(BaseModel):
    active: int = Field(description='Активных прокси')
    total: int = Field(description='Всего прокси')
    worst: list[OverviewWorstProxy] = Field(
        description='Прокси с наименьшей долей успеха за окно (от 5 генераций)',
    )


class OverviewNotifications(BaseModel):
    pending: int = Field(description='Ожидают отправки сейчас')
    sent: int = Field(description='Отправлено за окно')
    failed: int = Field(description='Не доставлено за окно')
    series: list[OverviewPoint] = Field(
        description='Уведомления по интервалам: ключи `SENT`, `FAILED`, `PENDING`',
    )


class OverviewCredits(BaseModel):
    spent: int = Field(description='Потрачено за окно, кредитов')
    tasks_spent: int = Field(description='Из них на задачи')
    automations_spent: int = Field(description='Из них на автоматизации')
    direct_spent: int = Field(description='Из них на direct-запросы')
    zero_balance_users: int = Field(description='Пользователей с нулевым или отрицательным балансом')
    low_balance_users: int = Field(description='Пользователей с балансом ниже порога')
    low_balance_threshold: int = Field(description='Порог «мало кредитов»')
    series: list[OverviewPoint] = Field(description='Траты по интервалам: ключ `spent`')


class OverviewUsers(BaseModel):
    total: int = Field(description='Всего пользователей')
    new: int = Field(description='Зарегистрировались за окно')
    active: int = Field(description='Были активны за окно')


# --- Ответ


class OverviewResponse(BaseModel):
    """Ответ `GET /api/admin/overview` — сводка по всему сайту за окно."""

    window: OverviewWindow = Field(description='Окно сводки')
    bucket_unit: BucketUnit = Field(description='Шаг точек временных рядов')
    date_from: datetime = Field(description='Начало окна (UTC)')
    generated_at: datetime = Field(description='Момент расчёта сводки (UTC)')
    workers: OverviewWorkers = Field(description='Состояние воркеров')
    tasks: OverviewTasks = Field(description='Задачи')
    generations: OverviewGenerations = Field(description='Генерации сессий')
    proxies: OverviewProxies = Field(description='Прокси')
    notifications: OverviewNotifications = Field(description='Уведомления')
    credits: OverviewCredits = Field(description='Кредиты')
    automations: AutomationsStateSummary = Field(description='Автоматизации')
    users: OverviewUsers = Field(description='Пользователи')
