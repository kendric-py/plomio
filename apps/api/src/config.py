from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from core.configs import PostgresConfig, RedisConfig

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


class Config(BaseSettings):
    REST: RestConfig = Field(default_factory=RestConfig)
    POSTGRES: PostgresConfig = Field(default_factory=PostgresConfig)
    REDIS: RedisConfig = Field(default_factory=RedisConfig)
    WORKER_HEALTH: WorkerHealthConfig = Field(default_factory=WorkerHealthConfig)

    class Config:
        env_file = ENV_FILE
        env_file_encoding = 'utf-8'
        extra = 'ignore'


config = Config()
