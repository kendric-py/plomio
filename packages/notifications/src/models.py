from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from packages.notifications.src.enums import NotificationChannel, NotificationDeliveryStatus


class NotificationEvent(BaseSQLModel):
    """Каталог типов событий — по образцу packages.billing.src.models.BillingAction. Новый тип
    события = новая строка здесь + один вызов NotificationService.notify(...) в коде домена, без
    изменения схемы (см. AGENTS.md)."""

    __tablename__ = 'notification_events'
    __mapper_args__ = {'eager_defaults': True}

    event_code: Mapped[str] = mapped_column(String, primary_key=True)
    description: Mapped[str] = mapped_column(String, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default='true')
    # Список имён полей, по которым можно фильтровать подписку на это событие (например,
    # TrackedField-значения PRICE/RATING/... у automation.change_detected) — только хранится,
    # домен их не интерпретирует, не знает про TrackedField. NULL/пустой список — у события нет
    # понятия "поле", фильтр неприменим (task.* события).
    available_fields: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)


class NotificationSetting(BaseSQLModel):
    """Настройки уведомлений — одна строка на пользователя (PK = user_id, по образцу
    packages.billing.src.models.CreditWallet), полностью глобальные: без привязки к конкретным
    объектам (automation/task и т.п.). `preferences` — карта {event_code: {"channels": [...],
    "fields": [...] | null}}; отсутствие ключа для event_code или пустой список каналов =
    уведомления по этому событию выключены — безопасный дефолт для нового пользователя. `fields`
    (подмножество NotificationEvent.available_fields этого события) — необязательный фильтр:
    null/пусто = уведомлять по любому изменению, непустой список = только если событие затронуло
    хотя бы одно из перечисленных полей."""

    __tablename__ = 'notification_settings'
    # eager_defaults: updated_at is server-computed (onupdate=func.now()) — without this, reading
    # it back right after an async UPDATE fails with MissingGreenlet (same reasoning as
    # packages.automation.src.models.Automation).
    __mapper_args__ = {'eager_defaults': True}

    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
        primary_key=True,
    )
    preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default='{}')
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


class NotificationDelivery(BaseSQLModel):
    """Append-only журнал "это уведомление нужно отправить" — тот же принцип, что
    automation_check_log/credit_transactions. Никогда не обновляется этим доменом в этой итерации
    (только будущий отправитель будет переводить status в SENT/FAILED)."""

    __tablename__ = 'notification_deliveries'
    __table_args__ = (
        Index('ix_notification_deliveries_status_created_at', 'status', 'created_at'),
        Index('ix_notification_deliveries_user_id', 'user_id'),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    event_code: Mapped[str] = mapped_column(
        ForeignKey('notification_events.event_code', ondelete='CASCADE'), nullable=False,
    )
    channel: Mapped[NotificationChannel] = mapped_column(SqlEnum(NotificationChannel), nullable=False)
    status: Mapped[NotificationDeliveryStatus] = mapped_column(
        SqlEnum(NotificationDeliveryStatus),
        nullable=False,
        server_default=NotificationDeliveryStatus.PENDING.value,
    )
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
