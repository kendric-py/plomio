from typing import Tuple

from pydantic_settings import BaseSettings
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine


class BaseSQLModel(DeclarativeBase):
    pass


def get_database_connection(config: BaseSettings) -> Tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    async_engine = create_async_engine(
        str(config.POSTGRES.DSN),
        echo=False,
        future=True,
        pool_pre_ping=True,
        pool_recycle=1800,
    )
    async_session_maker = async_sessionmaker(
        async_engine,
        expire_on_commit=False,
    )
    return (async_engine, async_session_maker,)
