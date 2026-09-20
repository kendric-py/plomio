from datetime import datetime

from pydantic import BaseModel, Field

from core.enums import Marketplace


class MarketplaceSessionPool(BaseModel):
    marketplace: Marketplace = Field(description='Маркетплейс')
    live_count: int = Field(description='Количество живых (не просроченных) сессий в пуле')
    nearest_expires_at: datetime | None = Field(
        description='Момент истечения самой "старой" из живых сессий пула; '
        '`null`, если живых сессий нет',
    )


class SessionPoolResponse(BaseModel):
    marketplaces: list[MarketplaceSessionPool] = Field(
        description='Состояние пула сессий по каждому маркетплейсу',
    )
