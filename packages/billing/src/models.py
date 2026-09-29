from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, UniqueConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from packages.billing.src.enums import ReferenceType


class BillingAction(BaseSQLModel):
    """Каталог тарифицируемых действий — базовая цена за единицу. Новое тарифицируемое действие =
    новая строка здесь + один вызов `BillingService.charge(...)` в коде домена, без изменения схемы
    (см. AGENTS.md)."""

    __tablename__ = 'billing_actions'
    __table_args__ = (
        UniqueConstraint('action_code', name='uq_billing_actions_action_code'),
    )
    __mapper_args__ = {'eager_defaults': True}

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action_code: Mapped[str] = mapped_column(String, nullable=False)
    description: Mapped[str] = mapped_column(String, nullable=False)
    base_cost: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    unit_label: Mapped[str] = mapped_column(String, nullable=False)
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


class PricingMultiplierRule(BaseSQLModel):
    """Множитель базовой цены по диапазону значений произвольного измерения (`dimension_code`) —
    одна универсальная таблица для всех измерений, текущих и будущих (см. AGENTS.md,
    "Конструктор"). Непересечение диапазонов в рамках одного `dimension_code` проверяется в
    `BillingService`, не БД-констрейнтом."""

    __tablename__ = 'pricing_multiplier_rules'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    dimension_code: Mapped[str] = mapped_column(String, nullable=False)
    value_min: Mapped[int] = mapped_column(Integer, nullable=False)
    value_max: Mapped[int] = mapped_column(Integer, nullable=False)
    multiplier: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )


class CreditWallet(BaseSQLModel):
    """Текущий баланс кредитов пользователя — один кошелёк на пользователя (PK = `user_id`).
    Баланс может уйти в минус — списание не блокируется на уровне кошелька, только на уровне guard'а
    перед созданием новых задач/автоматизаций (см. AGENTS.md)."""

    __tablename__ = 'credit_wallets'

    user_id: Mapped[int] = mapped_column(
        ForeignKey('users.id', ondelete='CASCADE'),
        primary_key=True,
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, server_default='0')
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


class CreditTransaction(BaseSQLModel):
    """Append-only журнал списаний/начислений — источник правды для анализа расходов, тот же
    принцип, что `automation_check_log` для истории проверок. Никогда не обновляется/не
    удаляется."""

    __tablename__ = 'credit_transactions'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)
    action_code: Mapped[str | None] = mapped_column(
        ForeignKey('billing_actions.action_code', ondelete='SET NULL'),
        nullable=True,
    )
    reference_type: Mapped[ReferenceType | None] = mapped_column(
        SqlEnum(ReferenceType), nullable=True,
    )
    reference_id: Mapped[str | None] = mapped_column(String, nullable=True)
    # Named transaction_metadata, not metadata — `metadata` is reserved on SQLAlchemy declarative
    # models (Base.metadata).
    transaction_metadata: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    granted_by_admin_id: Mapped[int | None] = mapped_column(
        ForeignKey('users.id', ondelete='SET NULL'),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
