import logging
from typing import Callable

from apps.worker_sessions.src.entities import ProxyConfig, SessionMessage
from apps.worker_sessions.src.generation.marketplaces.ozon.session import (
    build_session_message as build_ozon,
)
from apps.worker_sessions.src.generation.marketplaces.wb.session import (
    build_session_message as build_wb,
)
from core.enums import Marketplace

logger = logging.getLogger(__name__)

_BUILDERS: dict[Marketplace, Callable[[ProxyConfig | None], SessionMessage]] = {
    Marketplace.OZON: build_ozon,
    Marketplace.WILDBERRIES: build_wb,
}


def build_session(marketplace: Marketplace, proxy: ProxyConfig | None) -> SessionMessage:
    if marketplace not in _BUILDERS:
        logger.error('[unsupported_marketplace] marketplace=%s', marketplace)
        raise ValueError(f'unsupported marketplace: {marketplace}')
    return _BUILDERS[marketplace](proxy)
