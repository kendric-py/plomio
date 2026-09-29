from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from packages.notifications.src.enums import TelegramLinkOutcome
from packages.notifications.src.service import NotificationService

OUTCOME_TEXT = {
    TelegramLinkOutcome.LINKED: '✅ Telegram привязан к вашему аккаунту',
    TelegramLinkOutcome.ALREADY_LINKED_SAME: 'Этот Telegram уже привязан к вашему аккаунту.',
    TelegramLinkOutcome.ALREADY_LINKED_OTHER: (
        '⚠️ Этот Telegram уже привязан к другому аккаунту'
    ),
    TelegramLinkOutcome.INVALID_CODE: (
        '❌ Код недействителен или устарел — сгенерируйте новую ссылку в личном кабинете.'
    ),
}

dispatcher = Dispatcher()


@dispatcher.message(CommandStart(deep_link=True))
async def handle_start_with_code(
    message: Message,
    command: CommandObject,
    notification_service: NotificationService,
) -> None:
    outcome = await notification_service.confirm_telegram_link(
        code=command.args,
        telegram_user_id=message.from_user.id,
    )
    await message.answer(text=OUTCOME_TEXT[outcome])


@dispatcher.message(CommandStart())
async def handle_start_without_code(message: Message) -> None:
    await message.answer(
        text='Чтобы привязать Telegram, сгенерируйте ссылку в личном кабинете plomio.pro '
        '(POST /api/notifications/telegram/link) и перейдите по ней.',
    )


async def run_telegram_polling(bot_token: str, notification_service: NotificationService) -> None:
    """Long polling — временное решение этой итерации, безопасно только для одной реплики
    `apps/api` (см. `packages/notifications/AGENTS.md`, "Привязка Telegram"): несколько реплик,
    поллящих один и тот же `bot_token`, конфликтуют на `getUpdates` (Telegram отвечает `409
    Conflict` всем, кроме одной). Заменить на webhook (`config.REST.PUBLIC_BASE_URL` уже
    зарезервирован под это) — отдельная будущая работа, не в этой итерации."""

    # handle_signals=False — this loop runs as one asyncio task inside apps/api's own process;
    # letting aiogram install its own SIGINT/SIGTERM handlers would fight uvicorn's, which already
    # owns process-level shutdown (the lifespan cancels this task instead, see
    # apps/api/src/server.py).
    # parse_mode=HTML — same bot-wide default as TelegramNotifier (telegram_client.py), so the
    # link-confirmation replies below are parsed the same way; they're static strings with no
    # `<`/`&`, so no escaping is needed for them specifically.
    bot = Bot(
        token=bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    await dispatcher.start_polling(
        bot, notification_service=notification_service, handle_signals=False,
    )
