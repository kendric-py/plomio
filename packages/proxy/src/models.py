from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from core.enums import Marketplace
from packages.proxy.src.enums import ProxyType
from packages.sessions.src.enums import SessionGenerationOutcome


class Proxy(BaseSQLModel):
    """Прокси из пула, который раздаёт `worker_sessions` ручка `GET /api/proxy/issue` (случайный
    активный — см. AGENTS.md). Уникальность — по (тип, хост, порт, логин); `NULLS NOT DISTINCT`,
    чтобы два прокси без логина с одним адресом тоже считались дублем."""

    __tablename__ = 'proxies'
    __table_args__ = (
        UniqueConstraint(
            'proxy_type', 'host', 'port', 'username',
            name='uq_proxies_endpoint',
            postgresql_nulls_not_distinct=True,
        ),
    )
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proxy_type: Mapped[ProxyType] = mapped_column(SqlEnum(ProxyType), nullable=False)
    host: Mapped[str] = mapped_column(String, nullable=False)
    port: Mapped[int] = mapped_column(Integer, nullable=False)
    username: Mapped[str | None] = mapped_column(String, nullable=True)
    password: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default='true')
    note: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class SessionGeneration(BaseSQLModel):
    """Итог одной попытки генерации сессии (пишет `worker_sessions` через api): успех или тип
    ошибки, маркетплейс и прокси. Из последних 50 по маркетплейсу считается процент успеха в
    пуле сессий, по `proxy_id` — статистика конкретного прокси. `proxy_id` пуст, если прокси не
    использовался или был удалён. Строки старше срока хранения удаляет cron-чистка."""

    __tablename__ = 'session_generations'
    __table_args__ = (
        Index('ix_session_generations_proxy_created', 'proxy_id', 'created_at'),
        Index('ix_session_generations_marketplace_created', 'marketplace', 'created_at'),
    )
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    proxy_id: Mapped[int | None] = mapped_column(
        ForeignKey('proxies.id', ondelete='SET NULL'), nullable=True,
    )
    marketplace: Mapped[Marketplace] = mapped_column(SqlEnum(Marketplace), nullable=False)
    outcome: Mapped[SessionGenerationOutcome] = mapped_column(
        SqlEnum(SessionGenerationOutcome), nullable=False,
    )
    # Оригинальная ошибка (трейсбек или текст) для разбора причин; у успеха и части ошибок её нет.
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
