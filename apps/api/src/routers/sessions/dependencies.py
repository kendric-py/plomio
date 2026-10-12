from apps.api.src.routers.sessions.schema import MarketplaceSessionPool
from core.enums import Marketplace
from packages.sessions.src.errors import group_errors
from packages.sessions.src.redis_store import SessionPoolStore


async def build_marketplace_pool(
    store: SessionPoolStore, marketplace: Marketplace,
) -> MarketplaceSessionPool:
    """Состояние пула по маркетплейсу + последние ошибки генерации, сгруппированные по типу."""
    live_count, nearest_expires_at = await store.get_pool_stats(marketplace)
    recent_errors = await store.get_recent_errors(marketplace=marketplace)
    return MarketplaceSessionPool(
        marketplace=marketplace,
        live_count=live_count,
        nearest_expires_at=nearest_expires_at,
        recent_errors_total=len(recent_errors),
        recent_errors=group_errors(kinds=recent_errors),
    )
