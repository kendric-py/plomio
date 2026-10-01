from enum import Enum


class ProxyType(str, Enum):
    """Тип прокси. Значения (`http`, `socks5`) — тот же контракт, что у
    `packages.sessions.src.entities.ProxyConfig.type`, который читает `worker_sessions`."""

    HTTP = 'http'
    SOCKS5 = 'socks5'
