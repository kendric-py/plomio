from typing import Optional

from pydantic_core.core_schema import FieldValidationInfo
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, field_validator


class PostgresConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_prefix='POSTGRES_',
        extra='ignore',
    )

    HOST: str = Field(default=None)
    PORT: int = Field(default=None)
    DB: str = Field(default=None)
    USER: str = Field(default=None)
    PASSWORD: str = Field(default=None)
    DSN: Optional[PostgresDsn] = Field(default=None)

    @field_validator('DSN')
    def validate_postgres_dsn(
        cls,
        field: Optional[PostgresDsn],
        fields: FieldValidationInfo,
    ) -> PostgresDsn:
        if field:
            return field
        return PostgresDsn(
            f'postgresql+asyncpg://{fields.data.get("USER")}:'
            f'{fields.data.get("PASSWORD")}@'
            f'{fields.data.get("HOST")}:'
            f'{fields.data.get("PORT")}/'
            f'{fields.data.get("DB")}',
        )


class AuthConfig(BaseSettings):
    model_config = SettingsConfigDict(
        env_file='.env',
        env_file_encoding='utf-8',
        env_prefix='AUTH_',
        extra='ignore',
    )

    SECRET_KEY: str = Field(default=None)
    ALGORITHM: str = Field(default='HS256')
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(default=60)
