import logging
from typing import Callable

from worker_sessions.entities import ProxyConfig, SessionMessage
from worker_sessions.enums import Marketplace
from worker_sessions.generation.marketplaces.ozon.session import build_session_message as build_ozon
from worker_sessions.generation.marketplaces.wb.session import build_session_message as build_wb

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
