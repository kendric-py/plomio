import logging
from typing import Callable

from apps.worker_sessions.src.config import config
from apps.worker_sessions.src.entities import ProxyConfig, SessionMessage
from apps.worker_sessions.src.generation.marketplaces.ozon.session_js import (
    build_session_message as build_ozon_js,
)
from apps.worker_sessions.src.generation.marketplaces.ozon.session import (
    build_session_message as build_ozon,
)
from apps.worker_sessions.src.generation.marketplaces.wb.session import (
    build_session_message as build_wb,
)
from apps.worker_sessions.src.generation.marketplaces.wb.session_js import (
    build_session_message as build_wb_js,
)
from core.enums import Marketplace

logger = logging.getLogger(__name__)

_BUILDERS: dict[Marketplace, Callable[[ProxyConfig | None], SessionMessage]] = {
    Marketplace.OZON: build_ozon,
    Marketplace.WILDBERRIES: build_wb,
}

_JS_BUILDERS: dict[Marketplace, Callable[[ProxyConfig | None], SessionMessage]] = {
    Marketplace.OZON: build_ozon_js,
    Marketplace.WILDBERRIES: build_wb_js,
}

_MODE_BY_MARKETPLACE: dict[Marketplace, Callable[[], str]] = {
    Marketplace.OZON: lambda: config.GENERATION.OZON_MODE,
    Marketplace.WILDBERRIES: lambda: config.GENERATION.WB_MODE,
}


def build_session(marketplace: Marketplace, proxy: ProxyConfig | None) -> SessionMessage:
    if marketplace not in _BUILDERS:
        logger.error('[unsupported_marketplace] marketplace=%s', marketplace)
        raise ValueError(f'unsupported marketplace: {marketplace}')
    if _MODE_BY_MARKETPLACE[marketplace]() != 'js_runtime':
        return _BUILDERS[marketplace](proxy)
    return _JS_BUILDERS[marketplace](proxy)
