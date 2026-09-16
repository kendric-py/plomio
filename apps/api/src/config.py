from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from core.configs import PostgresConfig

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


class Config(BaseSettings):
    REST: RestConfig = Field(default_factory=RestConfig)
    POSTGRES: PostgresConfig = Field(default_factory=PostgresConfig)

    class Config:
        env_file = ENV_FILE
        env_file_encoding = 'utf-8'
        extra = 'ignore'


config = Config()
