from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from apps.worker_parser.src.enums import WorkerMode
from core.configs import LivenessConfig, PostgresConfig, RedisConfig

# Load this app's .env into the real process environment, independent of cwd — mirrors
# apps/worker_sessions/src/config.py, needed because this worker can be launched from outside its
# own directory (e.g. by an orchestrator) and every *Config class below builds itself at import
# time.
ENV_FILE = Path(__file__).resolve().parent.parent / '.env'
load_dotenv(dotenv_path=ENV_FILE)


class PollConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='POLL_',
        extra='ignore',
    )

    WORKER_ID: str = Field(default='')
    INTERVAL_SECONDS: float = Field(default=5.0)
    LEASE_DURATION_SECONDS: float = Field(default=120.0)
    HEARTBEAT_INTERVAL_SECONDS: float = Field(default=30.0)
    STATUS_CHECK_INTERVAL_PAGES: int = Field(default=1)
    MAX_CONCURRENT_TASKS: int = Field(default=3)
    MAX_CONCURRENT_ITEMS_PER_TASK: int = Field(default=5)


class SessionPoolConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='SESSION_POOL_',
        extra='ignore',
    )

    MAX_POP_ATTEMPTS: int = Field(default=5)
    MIN_TTL_MARGIN_SECONDS: float = Field(default=30.0)
    EMPTY_POOL_BACKOFF_SECONDS: float = Field(default=5.0)


class HttpConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='HTTP_',
        extra='ignore',
    )

    TIMEOUT_SECONDS: float = Field(default=20.0)
    RETRIES: int = Field(default=3)
    BASE_DELAY_SECONDS: float = Field(default=1.5)


class DirectConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='DIRECT_',
        extra='ignore',
    )

    CONSUMER_NAME: str = Field(default='direct-1')
    MAX_CONCURRENT_REQUESTS: int = Field(default=20)
    BLOCK_MS: int = Field(default=2000)
    # Общее число попыток на один запрос (смена сессии между ними), в пределах его дедлайна.
    MAX_ATTEMPTS: int = Field(default=2)
    # Возраст горячей сессии, после которого она возвращается в пул и берётся новая. Не добавляется
    # к SESSION_POOL_MIN_TTL_MARGIN_SECONDS: TTL сессий у worker_sessions — 7 минут, и большой порог
    # заставил бы acquire_session выбрасывать из пула все живые сессии.
    HOT_SESSION_MAX_AGE_SECONDS: float = Field(default=120.0)
    SESSION_WAIT_SECONDS: float = Field(default=3.0)
    # Через запятую; пусто — все маркетплейсы.
    MARKETPLACES: str = Field(default='')
    REVIEWS_WB_PAGE_SIZE: int = Field(default=30)


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra='ignore',
    )

    WORKER_MODE: WorkerMode = Field(default=WorkerMode.TASKS)
    # Базовый URL фронтенда (без завершающего /) — используется TaskService.complete_item, чтобы
    # положить ссылку на страницу завершённой задачи в payload уведомления (см.
    # packages/notifications/AGENTS.md, "Базовый URL фронтенда"). Тот же смысл, что
    # apps.api.src.config.RestConfig.FRONTEND_BASE_URL — раздельные настройки, так как это отдельный
    # процесс/деплоймент со своим .env, не общий конфиг с apps/api.
    FRONTEND_BASE_URL: str = Field(default_factory=str)

    REDIS: RedisConfig = Field(default_factory=RedisConfig)
    POSTGRES: PostgresConfig = Field(default_factory=PostgresConfig)
    POLL: PollConfig = Field(default_factory=PollConfig)
    SESSION_POOL: SessionPoolConfig = Field(default_factory=SessionPoolConfig)
    HTTP: HttpConfig = Field(default_factory=HttpConfig)
    DIRECT: DirectConfig = Field(default_factory=DirectConfig)
    LIVENESS: LivenessConfig = Field(default_factory=LivenessConfig)


config = Config()
