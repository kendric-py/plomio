from pathlib import Path

from dotenv import load_dotenv
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.configs import PostgresConfig, RedisConfig

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


class SessionPoolConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='SESSION_POOL_',
        extra='ignore',
    )

    MAX_POP_ATTEMPTS: int = Field(default=5)
    MIN_TTL_MARGIN_SECONDS: float = Field(default=300.0)
    EMPTY_POOL_BACKOFF_SECONDS: float = Field(default=5.0)


class RetryConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='RETRY_',
        extra='ignore',
    )

    MAX_ATTEMPTS_SAME_SESSION: int = Field(default=3)


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


class LivenessConfig(BaseSettings):
    """Process-level HTTP heartbeat, independent of task-lease progress — see
    apps/worker_parser/AGENTS.md for the open questions around the receiving endpoint."""

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        env_prefix='LIVENESS_',
        extra='ignore',
    )

    WORKER_NAME: str = Field(default='')
    ENDPOINT_URL: str = Field(default='')
    INTERVAL_SECONDS: float = Field(default=15.0)
    REQUEST_TIMEOUT_SECONDS: float = Field(default=5.0)


class Config(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding='utf-8',
        extra='ignore',
    )

    DEBUG: bool = Field(default=False)

    REDIS: RedisConfig = Field(default_factory=RedisConfig)
    POSTGRES: PostgresConfig = Field(default_factory=PostgresConfig)
    POLL: PollConfig = Field(default_factory=PollConfig)
    SESSION_POOL: SessionPoolConfig = Field(default_factory=SessionPoolConfig)
    RETRY: RetryConfig = Field(default_factory=RetryConfig)
    HTTP: HttpConfig = Field(default_factory=HttpConfig)
    LIVENESS: LivenessConfig = Field(default_factory=LivenessConfig)


config = Config()
