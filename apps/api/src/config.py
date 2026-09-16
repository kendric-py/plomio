from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

from core.configs import PostgresConfig


class RestConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
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
    # POSTGRES: PostgresConfig = Field(default_factory=PostgresConfig)

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'


config = Config()
