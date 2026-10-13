from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import BaseSQLModel

if TYPE_CHECKING:
    from packages.user.src.models import User


class ApiKey(BaseSQLModel):
    """API-ключ пользователя для доступа к API в обход фронтенда. Сам ключ не хранится — только
    SHA-256-хэш (`key_hash`, по нему ищется ключ при авторизации) и префикс для отображения
    (`prefix`). Ключ не удаляется, а отзывается (`revoked_at`): по нему остаётся статистика трат
    (`credit_transactions.api_key_id`)."""

    __tablename__ = 'api_keys'
    __table_args__ = (UniqueConstraint('key_hash', name='uq_api_keys_key_hash'),)
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'), nullable=False, index=True,
    )
    name: Mapped[str] = mapped_column(String, nullable=False)
    prefix: Mapped[str] = mapped_column(String, nullable=False)
    key_hash: Mapped[str] = mapped_column(String, nullable=False)
    # Лимит трат по ключу за всё время его жизни, в кредитах; NULL — без лимита.
    credit_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # NULL — бессрочный ключ.
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
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

    user: Mapped['User'] = relationship(back_populates='api_keys')
