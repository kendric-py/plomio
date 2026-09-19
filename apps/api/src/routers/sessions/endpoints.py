from datetime import datetime, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.sessions.schema import (
    MarketplaceSessionPool,
    SessionInfo,
    SessionPoolResponse,
)
from core.enums import Marketplace
from packages.sessions.src.redis_store import SessionPoolStore

router = APIRouter(prefix='/sessions', tags=['Sessions'])


@router.get('/pool')
@inject
async def get_session_pool(
    store: SessionPoolStore = Depends(Provide[DependencyContainer.session_pool_store]),
) -> SessionPoolResponse:
    pools = []
    for marketplace in Marketplace:
        live_sessions = await store.get_live_sessions(marketplace)
        pools.append(
            MarketplaceSessionPool(
                marketplace=marketplace,
                live_count=len(live_sessions),
                sessions=[
                    SessionInfo(
                        session_id=session_id,
                        expires_at=datetime.fromtimestamp(expires_at, tz=timezone.utc),
                    )
                    for session_id, expires_at in live_sessions
                ],
            ),
        )
    return SessionPoolResponse(marketplaces=pools)
