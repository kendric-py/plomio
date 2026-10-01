import pytest

from packages.notifications.src import telegram_polling
from packages.notifications.src.telegram_client import build_bot, build_telegram_notifier

TOKEN = '123456:TEST-token'
PROXY = 'socks5://user:pass@127.0.0.1:1080'


def test_bot_without_proxy_uses_default_session():
    bot = build_bot(bot_token=TOKEN)
    assert bot.session.proxy is None


def test_bot_with_proxy_passes_it_to_session():
    bot = build_bot(bot_token=TOKEN, proxy_url=PROXY)
    assert bot.session.proxy == PROXY


def test_notifier_is_disabled_without_token_even_with_proxy():
    assert build_telegram_notifier(bot_token='', proxy_url=PROXY) is None


def test_notifier_uses_proxy_when_configured():
    notifier = build_telegram_notifier(bot_token=TOKEN, proxy_url=PROXY)
    assert notifier._bot.session.proxy == PROXY
    assert build_telegram_notifier(bot_token=TOKEN)._bot.session.proxy is None


@pytest.mark.asyncio
async def test_polling_is_restarted_after_a_crash(monkeypatch):
    calls: list[str] = []

    async def flaky_start_polling(bot, **_kwargs):
        calls.append(bot.session.proxy)
        if len(calls) == 1:
            raise RuntimeError('network is down')

    monkeypatch.setattr(telegram_polling.dispatcher, 'start_polling', flaky_start_polling)
    monkeypatch.setattr(telegram_polling, 'RESTART_DELAY_SECONDS', 0.0)

    await telegram_polling.run_telegram_polling(
        bot_token=TOKEN, notification_service=None, proxy_url=PROXY,
    )

    assert calls == [PROXY, PROXY]
