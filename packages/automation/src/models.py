import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String, text
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from core.enums import Marketplace
from packages.automation.src.enums import AutomationStatus


class Automation(BaseSQLModel):
    __tablename__ = 'automations'
    __table_args__ = (
        CheckConstraint(
            'price_drop_threshold_percent BETWEEN 1 AND 100',
            name='ck_automations_price_drop_threshold_range',
        ),
        # Partial (article IS NOT NULL only) — a user can still have several automations whose
        # article couldn't be extracted (see core.marketplace_article.extract_article); those are
        # de-duplicated by input_value at the application level instead (AutomationRepository.
        # find_duplicate), not enforceable as a plain column constraint without normalizing it.
        Index(
            'ux_automations_user_marketplace_article',
            'user_id', 'marketplace', 'article',
            unique=True,
            postgresql_where=text('article IS NOT NULL'),
        ),
    )
    # eager_defaults: updated_at is server-computed (onupdate=func.now()) — without this,
    # reading it back right after an async UPDATE fails with MissingGreenlet, since SQLAlchemy
    # would otherwise lazily re-fetch it outside the async context.
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    marketplace: Mapped[Marketplace] = mapped_column(SqlEnum(Marketplace), nullable=False)
    input_value: Mapped[str] = mapped_column(String, nullable=False)
    # Extracted from input_value at creation time (core.marketplace_article.extract_article) —
    # NULL when the format wasn't recognized. Exists purely for duplicate detection: two
    # differently-formatted links to the same product should still be caught as the same
    # automation, which comparing input_value as a raw string can't do.
    article: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[AutomationStatus] = mapped_column(
        SqlEnum(AutomationStatus),
        nullable=False,
        server_default=AutomationStatus.ACTIVE.value,
    )
    price_drop_threshold_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    check_frequency_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    history_retention_days: Mapped[int] = mapped_column(Integer, nullable=False)
    baseline_price_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_discounted_price_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    baseline_original_price_kopecks: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Наличие товара по последней завершённой проверке; NULL — проверок ещё не было. Управляет
    # частотой следующей проверки в claim_due_for_dispatch (AUTOMATION_OUT_OF_STOCK_CHECK_
    # FREQUENCY_MINUTES вместо check_frequency_minutes, пока False) и служит baseline для
    # обнаружения возврата в наличие в AutomationService._diff_stock.
    in_stock: Mapped[bool | None] = mapped_column(nullable=True)
    next_check_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pending_task_id: Mapped[uuid.UUID | None] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('tasks.id', ondelete='SET NULL'),
        nullable=True,
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_check_error: Mapped[str | None] = mapped_column(String, nullable=True)
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


class AutomationHistory(BaseSQLModel):
    __tablename__ = 'automation_history'

    id: Mapped[int] = mapped_column(primary_key=True)
    automation_id: Mapped[uuid.UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey('automations.id', ondelete='CASCADE'),
        nullable=False,
    )
    # Одна строка = одна проверка: все поля, изменившиеся за эту проверку (может быть и цена, и
    # в будущем другие типы изменений), а не одна строка на каждое изменившееся поле — список
    # {field, old_value, new_value, threshold_breached} на верхнем уровне не даёт единообразно
    # запросить конкретное поле без JSONB-операторов, зато это осознанный компромисс ради "одна
    # проверка — одна запись".
    changes: Mapped[list[dict]] = mapped_column(JSONB, nullable=False)
    threshold_breached: Mapped[bool] = mapped_column(nullable=False)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
