from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode


class TelegramNotifier:
    """Thin wrapper around `aiogram.Bot` — the only Telegram-specific code in
    `packages/notifications`. A new channel implementation follows the same shape (a class with an
    async `send`), selected by `NotificationChannel` in `NotificationService.dispatch_pending`.

    `parse_mode=HTML` is set once here as a bot-wide default (`DefaultBotProperties`), not passed
    per `send_message` call — every message this bot sends is parsed as HTML, letting a user's own
    template contain `<b>`/`<i>`/`<a href=...>` markup. `formatting.py::render_template` HTML-escapes
    every substituted value for exactly this reason — a product title containing `<`/`&` must not
    be interpreted as markup or break the message's HTML structure."""

    def __init__(self, bot_token: str):
        self._bot = Bot(
            token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        )

    async def send(self, chat_id: int, text: str) -> None:
        await self._bot.send_message(chat_id=chat_id, text=text)


def build_telegram_notifier(bot_token: str) -> TelegramNotifier | None:
    """Empty `bot_token` (see `core.configs.TelegramConfig`) means Telegram sending is disabled —
    `None` here, `NotificationService.dispatch_pending` leaves TELEGRAM deliveries PENDING when
    there's no notifier configured, the same convention as `packages.worker_health`'s
    `LivenessReporter` no-op on an empty endpoint URL."""

    return TelegramNotifier(bot_token=bot_token) if bot_token else None
