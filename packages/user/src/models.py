from datetime import datetime

from sqlalchemy import BigInteger, DateTime, String
from sqlalchemy import Enum as SqlEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from core.database import BaseSQLModel
from packages.api_keys.src.models import ApiKey
from packages.membership.src.models import Membership
from packages.user.src.enums import UserRole


class User(BaseSQLModel):
    __tablename__ = 'users'

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(String, nullable=False)
    role: Mapped[UserRole] = mapped_column(SqlEnum(UserRole), nullable=False, default=UserRole.CLIENT)
    telegram_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    last_active_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    memberships: Mapped[list[Membership]] = relationship(back_populates='user')
    api_keys: Mapped[list[ApiKey]] = relationship(back_populates='user')
