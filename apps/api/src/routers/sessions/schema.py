from datetime import datetime

from pydantic import BaseModel, Field

from core.enums import Marketplace


class SessionInfo(BaseModel):
    session_id: str = Field(description='Идентификатор сессии в пуле')
    expires_at: datetime = Field(description='Момент, до которого сессия действительна')


class MarketplaceSessionPool(BaseModel):
    marketplace: Marketplace = Field(description='Маркетплейс')
    live_count: int = Field(description='Количество живых (не просроченных) сессий в пуле')
    sessions: list[SessionInfo] = Field(description='Живые сессии этого маркетплейса')


class SessionPoolResponse(BaseModel):
    marketplaces: list[MarketplaceSessionPool] = Field(
        description='Состояние пула сессий по каждому маркетплейсу',
    )
