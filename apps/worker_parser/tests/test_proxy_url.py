import pytest

from apps.worker_parser.src.marketplaces.ozon.utils import create_ozon_http_session
from apps.worker_parser.src.marketplaces.wb.utils import create_wb_http_session
from core.enums import Marketplace
from packages.sessions.src.entities import ProxyConfig, SessionMessage


def socks5_proxy(**overrides) -> ProxyConfig:
    return ProxyConfig(type='socks5', host='1.2.3.4', port=1080, username='u', password='p',
                       **overrides)


def test_curl_url_resolves_dns_on_the_proxy_for_socks5():
    # `socks5://` => libcurl резолвит DNS локально и отдаёт прокси IPv6 хостов с AAAA (WB), который
    # прокси не маршрутизирует (`curl: (97) cannot complete SOCKS5 connection ... (3)`).
    assert socks5_proxy().to_curl_url() == 'socks5h://u:p@1.2.3.4:1080'


def test_curl_url_keeps_http_proxies_and_no_auth():
    http_proxy = ProxyConfig(type='http', host='h', port=3128)
    assert http_proxy.to_curl_url() == 'http://h:3128'
    assert ProxyConfig(type='socks5', host='h', port=1).to_curl_url() == 'socks5h://h:1'


def test_browser_url_is_unchanged():
    # Браузерная сторона (Camoufox + локальный туннель) разбирает именно `socks5://`.
    assert socks5_proxy().to_url() == 'socks5://u:p@1.2.3.4:1080'


@pytest.mark.parametrize('marketplace, factory, extra', [
    (Marketplace.WILDBERRIES, create_wb_http_session, {'device_id': 'd'}),
    (Marketplace.OZON, create_ozon_http_session, {'xcid': 'x', 'ab_group': '1'}),
])
@pytest.mark.asyncio
async def test_parser_http_sessions_use_remote_dns_proxy(marketplace, factory, extra):
    message = SessionMessage(
        marketplace=marketplace, proxy=socks5_proxy(), cookies={}, user_agent='ua',
        sec_ch_ua='', sec_ch_ua_platform='', extra=extra,
    )
    session = factory(message)
    try:
        assert session.proxies['https'] == 'socks5h://u:p@1.2.3.4:1080'
        assert session.proxies['http'] == 'socks5h://u:p@1.2.3.4:1080'
    finally:
        await session.close()
