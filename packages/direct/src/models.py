from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, SmallInteger, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from core.enums import Marketplace
from packages.direct.src.enums import DirectOutcome, DirectRequestType


class DirectRequestRecord(BaseSQLModel):
    """История direct-запросов — append-only журнал: по строке на каждый запрос, дошедший до
    воркера (или не дождавшийся его). Результата (товары, отзывы), `page_key` и курсоров здесь нет —
    только метаданные для мониторинга и разбора сбоев. Срок хранения не ограничен."""

    __tablename__ = 'direct_requests'
    __mapper_args__ = {'eager_defaults': True}
    __table_args__ = (
        Index('ix_direct_requests_created_at', 'created_at'),
        Index('ix_direct_requests_user_created', 'user_id', 'created_at'),
        Index('ix_direct_requests_marketplace_created', 'marketplace', 'created_at'),
        Index('ix_direct_requests_outcome_created', 'outcome', 'created_at'),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    # Тот же id, что в логах `[direct_api]` и `credit_transactions.reference_id`.
    request_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    # SET NULL: история остаётся для статистики, даже если пользователя удалили.
    user_id: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL'), nullable=True,
    )
    marketplace: Mapped[Marketplace] = mapped_column(SqlEnum(Marketplace), nullable=False)
    request_type: Mapped[DirectRequestType] = mapped_column(
        SqlEnum(DirectRequestType), nullable=False,
    )
    outcome: Mapped[DirectOutcome] = mapped_column(SqlEnum(DirectOutcome), nullable=False)
    http_status: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    input_value: Mapped[str] = mapped_column(String, nullable=False)
    is_next_page: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default='false')
    items_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_next_page: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    credits_charged: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    # Прокси, через который шла сессия воркера; None — сессия без прокси или id неизвестен.
    proxy_id: Mapped[int | None] = mapped_column(
        ForeignKey('proxies.id', ondelete='SET NULL'), nullable=True,
    )
    total_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    attempts: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    queue_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    session_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fetch_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    worker_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Внутренняя причина сбоя из `DirectReply.error` (до 300 символов) — только для админа.
    error_detail: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(),
    )
