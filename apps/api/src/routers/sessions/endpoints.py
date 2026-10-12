from dependency_injector.wiring import Provide, inject
from fastapi import APIRouter, Depends

from apps.api.src.container import DependencyContainer
from apps.api.src.routers.sessions.dependencies import build_marketplace_pool
from apps.api.src.routers.sessions.schema import SessionPoolResponse
from core.enums import Marketplace
from packages.sessions.src.redis_store import SessionPoolStore

router = APIRouter(prefix='/sessions', tags=['Sessions'])


@router.get('/pool')
@inject
async def get_session_pool(
    store: SessionPoolStore = Depends(Provide[DependencyContainer.session_pool_store]),
) -> SessionPoolResponse:
    pools = [
        await build_marketplace_pool(store=store, marketplace=marketplace)
        for marketplace in Marketplace
    ]
    return SessionPoolResponse(marketplaces=pools)
