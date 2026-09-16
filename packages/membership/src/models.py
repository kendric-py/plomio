from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import BaseSQLModel

if TYPE_CHECKING:
    from packages.user.src.models import User


class Membership(BaseSQLModel):
    """Заглушка доменной области `membership` (подписки/тарифы пользователя)."""

    __tablename__ = 'memberships'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)

    user: Mapped['User'] = relationship(back_populates='memberships')
