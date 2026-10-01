from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from core.configs import PostgresConfig, RedisConfig, TelegramConfig

# Load this app's .env into the real process environment (not just this module's own
# settings) — independent of cwd, and before any other module (e.g. packages.auth,
# which builds its own AuthConfig() at import time) reads settings from the environment.
# Without this, `.env` resolution falls back to cwd-relative lookups, which breaks
# whenever a command isn't launched from inside apps/api (e.g. alembic from the repo root).
ENV_FILE = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=ENV_FILE)


class RestConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='REST_',
        extra='ignore',
    )

    APP_HOST: str = Field(default=None)
    APP_PORT: int = Field(default=None)
    APP_TITLE: str = Field(default=None)
    PUBLIC_BASE_URL: str = Field(default_factory=str)
    FRONTEND_BASE_URL: str = Field(default_factory=str)


class WorkerHealthConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='WORKER_HEALTH_',
        extra='ignore',
    )

    # M — как часто проверяем; должно быть заметно меньше MISSED_THRESHOLD_SECONDS.
    SWEEP_INTERVAL_SECONDS: float = Field(default=10.0)
    # N — порог "пропущен heartbeat"; должно быть заметно больше LIVENESS_INTERVAL_SECONDS
    # воркеров (по умолчанию 15с), чтобы не ловить ложные срабатывания на единичной задержке сети.
    MISSED_THRESHOLD_SECONDS: float = Field(default=60.0)


class TaskConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='TASK_',
        extra='ignore',
    )

    # Как часто сканируем QUEUED-задачи с истёкшим queue_expires_at и переводим их в EXPIRED.
    EXPIRY_SWEEP_INTERVAL_SECONDS: float = Field(default=30.0)
    # Как часто сканируем RUNNING-задачи с истёкшей арендой (lease_expires_at) и возвращаем их в
    # QUEUED — детект упавшего/зависшего воркера (см. packages/task/AGENTS.md, "Lease/heartbeat").
    LEASE_RECLAIM_SWEEP_INTERVAL_SECONDS: float = Field(default=30.0)
    # queue_expires_at пересчитывается на now() + этот TTL при реклейме, тем же приёмом, что
    # resume_task — задача могла проработать в RUNNING дольше своего исходного queue_expires_at
    # (выставленного один раз в create_task), и без пересчёта claim_next (WHERE queue_expires_at >
    # now) никогда не подхватил бы её обратно — ближайший expire_stale_queued() тихо перевёл бы её
    # в EXPIRED вместо повторной попытки.
    LEASE_RECLAIM_REQUEUE_TTL_SECONDS: float = Field(default=3600.0)


class AutomationConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='AUTOMATION_',
        extra='ignore',
    )

    # Минимальная частота проверки, которую разрешено задать автоматизации (нижний предел из
    # конфига, см. требование "частота проверки в минутах, минимальное задаётся в конфиге").
    MIN_CHECK_FREQUENCY_MINUTES: int = Field(default=15)
    # Как часто сканируем ACTIVE-автоматизации с истёкшим next_check_at и ставим им задачу проверки.
    DISPATCH_INTERVAL_SECONDS: float = Field(default=30.0)
    # Сколько автоматизаций диспатчим/забираем результат за один проход job'а.
    DISPATCH_BATCH_SIZE: int = Field(default=50)
    # Как часто сканируем автоматизации с незавершённой проверкой (pending_task_id) и, если задача
    # проверки завершилась, сравниваем цены и пишем историю.
    RESULT_SWEEP_INTERVAL_SECONDS: float = Field(default=15.0)
    # Как часто удаляем строки истории старше history_retention_days каждой автоматизации.
    HISTORY_RETENTION_SWEEP_INTERVAL_SECONDS: float = Field(default=3600.0)
    # Частота проверки товара, у которого последняя проверка зафиксировала "нет в наличии" — не
    # зависит от пользовательского check_frequency_minutes, задаётся только конфигом (см.
    # AutomationRepository.claim_due_for_dispatch).
    OUT_OF_STOCK_CHECK_FREQUENCY_MINUTES: int = Field(default=5)


class NotificationsConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='NOTIFICATIONS_',
        extra='ignore',
    )

    # Как часто сканируем PENDING notification_deliveries и пытаемся их отправить.
    DELIVERY_SWEEP_INTERVAL_SECONDS: float = Field(default=10.0)
    # Сколько доставок забираем за один проход job'а
    # (см. NotificationDeliveryRepository.claim_pending).
    DELIVERY_SWEEP_BATCH_SIZE: int = Field(default=50)


class DirectConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='DIRECT_',
        extra='ignore',
    )

    # Сколько api ждёт ответ воркера; он же `deadline_at` запроса — по его истечении воркер
    # запрос отбрасывает.
    REQUEST_TIMEOUT_SECONDS: float = Field(default=20.0)
    # Срок годности `page_key`, которым клиент листает страницы.
    PAGE_KEY_TTL_SECONDS: float = Field(default=900.0)


class BillingConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='BILLING_',
        extra='ignore',
    )

    # Сколько кредитов начисляется новому пользователю при регистрации; 0 — не начислять.
    SIGNUP_BONUS_CREDITS: int = Field(default=10000, ge=0)


class ProxyConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='PROXY_',
        extra='ignore',
    )

    # Общий секрет, который `worker_sessions` шлёт в заголовке `X-Worker-Token` на
    # `GET /api/proxy/issue` (тот же, что `PROXY_API_TOKEN` в `.env` воркера). Пусто — выдача
    # прокси выключена (ручка отвечает 503).
    WORKER_TOKEN: str = Field(default_factory=str)


class Config(BaseSettings):
    REST: RestConfig = Field(default_factory=RestConfig)
    POSTGRES: PostgresConfig = Field(default_factory=PostgresConfig)
    REDIS: RedisConfig = Field(default_factory=RedisConfig)
    TELEGRAM: TelegramConfig = Field(default_factory=TelegramConfig)
    WORKER_HEALTH: WorkerHealthConfig = Field(default_factory=WorkerHealthConfig)
    TASK: TaskConfig = Field(default_factory=TaskConfig)
    AUTOMATION: AutomationConfig = Field(default_factory=AutomationConfig)
    NOTIFICATIONS: NotificationsConfig = Field(default_factory=NotificationsConfig)
    DIRECT: DirectConfig = Field(default_factory=DirectConfig)
    BILLING: BillingConfig = Field(default_factory=BillingConfig)
    PROXY: ProxyConfig = Field(default_factory=ProxyConfig)

    class Config:
        env_file = ENV_FILE
        env_file_encoding = 'utf-8'
        extra = 'ignore'


config = Config()
