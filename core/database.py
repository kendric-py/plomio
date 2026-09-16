from typing import Tuple

from pydantic_settings import BaseSettings
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine, AsyncSession


class BaseSQLModel(DeclarativeBase):
    pass


def _get_database_connection(config: BaseSettings) -> Tuple[AsyncEngine, sessionmaker]:
    async_engine = create_async_engine(
        str(config.POSTGRES.DSN),
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    async_session = sessionmaker(
        async_engine,
        expire_on_commit=False,
        class_=AsyncSession,
    )
    return (async_engine, async_session,)
