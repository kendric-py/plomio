from apps.api.src.routers.sessions.schema import MarketplaceSessionPool
from core.enums import Marketplace
from packages.proxy.src.service import ProxyService
from packages.sessions.src.errors import group_generations, success_percent
from packages.sessions.src.redis_store import SessionPoolStore


async def build_marketplace_pool(
    store: SessionPoolStore, proxy_service: ProxyService, marketplace: Marketplace,
) -> MarketplaceSessionPool:
    """Состояние пула (Redis) + последние 50 генераций сессий (БД), сгруппированные по итогу."""
    live_count, nearest_expires_at = await store.get_pool_stats(marketplace)
    recent_generations = await proxy_service.get_recent_generations(marketplace=marketplace)
    return MarketplaceSessionPool(
        marketplace=marketplace,
        live_count=live_count,
        nearest_expires_at=nearest_expires_at,
        recent_generations_total=len(recent_generations),
        success_percent=success_percent(outcomes=recent_generations),
        recent_generations=group_generations(outcomes=recent_generations),
    )
