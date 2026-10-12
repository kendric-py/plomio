from datetime import datetime

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.sessions.src.errors import SessionErrorShare


class MarketplaceSessionPool(BaseModel):
    marketplace: Marketplace = Field(description='Маркетплейс')
    live_count: int = Field(description='Количество живых (не просроченных) сессий в пуле')
    nearest_expires_at: datetime | None = Field(
        description='Момент истечения самой "старой" из живых сессий пула; '
        '`null`, если живых сессий нет',
    )
    recent_errors_total: int = Field(
        description='Сколько последних ошибок генерации сессий учтено (до 10)',
    )
    recent_errors: list[SessionErrorShare] = Field(
        description='Последние ошибки генерации сессий, сгруппированные по типу: '
        'самые частые первыми, `percent` — доля от `recent_errors_total`',
    )


class SessionPoolResponse(BaseModel):
    marketplaces: list[MarketplaceSessionPool] = Field(
        description='Состояние пула сессий по каждому маркетплейсу',
    )
