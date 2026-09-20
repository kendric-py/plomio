from datetime import datetime, timezone

from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.sessions.schema import MarketplaceSessionPool, SessionPoolResponse
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
        live_count, nearest_expires_at = await store.get_pool_stats(marketplace)
        pools.append(
            MarketplaceSessionPool(
                marketplace=marketplace,
                live_count=live_count,
                nearest_expires_at=(
                    datetime.fromtimestamp(nearest_expires_at, tz=timezone.utc)
                    if nearest_expires_at is not None
                    else None
                ),
            ),
        )
    return SessionPoolResponse(marketplaces=pools)
