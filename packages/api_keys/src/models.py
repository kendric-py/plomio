from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from core.database import BaseSQLModel

if TYPE_CHECKING:
    from packages.user.src.models import User


class ApiKey(BaseSQLModel):
    """Заглушка доменной области `api_keys` (API-ключи пользователя)."""

    __tablename__ = 'api_keys'

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey('users.id'), nullable=False)

    user: Mapped['User'] = relationship(back_populates='api_keys')
