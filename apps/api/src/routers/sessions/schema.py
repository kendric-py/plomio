from datetime import datetime

from pydantic import BaseModel, Field

from core.enums import Marketplace
from packages.sessions.src.errors import SessionGenerationShare


class MarketplaceSessionPool(BaseModel):
    marketplace: Marketplace = Field(description='Маркетплейс')
    live_count: int = Field(description='Количество живых (не просроченных) сессий в пуле')
    nearest_expires_at: datetime | None = Field(
        description='Момент истечения самой "старой" из живых сессий пула; '
        '`null`, если живых сессий нет',
    )
    recent_generations_total: int = Field(
        description='Сколько последних генераций сессий (успехов и ошибок) учтено (до 50)',
    )
    success_percent: int = Field(
        description='Доля успешных генераций среди последних, %; 0, если генераций ещё не было',
    )
    recent_generations: list[SessionGenerationShare] = Field(
        description='Последние генерации сессий, сгруппированные по итогу (`success` или тип '
        'ошибки): самые частые первыми, `percent` — доля от `recent_generations_total`',
    )


class SessionPoolResponse(BaseModel):
    marketplaces: list[MarketplaceSessionPool] = Field(
        description='Состояние пула сессий по каждому маркетплейсу',
    )
