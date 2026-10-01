import asyncio
import logging

from aiogram import Dispatcher
from aiogram.filters import CommandObject, CommandStart
from aiogram.types import Message

from packages.notifications.src.enums import TelegramLinkOutcome
from packages.notifications.src.service import NotificationService
from packages.notifications.src.telegram_client import build_bot

logger = logging.getLogger(__name__)

RESTART_DELAY_SECONDS = 10.0

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


async def run_telegram_polling(
    bot_token: str, notification_service: NotificationService, proxy_url: str = '',
) -> None:
    """Long polling — временное решение этой итерации, безопасно только для одной реплики
    `apps/api` (см. `packages/notifications/AGENTS.md`, "Привязка Telegram"): несколько реплик,
    поллящих один и тот же `bot_token`, конфликтуют на `getUpdates` (Telegram отвечает `409
    Conflict` всем, кроме одной). Заменить на webhook (`config.REST.PUBLIC_BASE_URL` уже
    зарезервирован под это) — отдельная будущая работа, не в этой итерации."""

    # handle_signals=False — this loop runs as one asyncio task inside apps/api's own process;
    # letting aiogram install its own SIGINT/SIGTERM handlers would fight uvicorn's, which already
    # owns process-level shutdown (the lifespan cancels this task instead, see
    # apps/api/src/server.py).
    # Bot собирается через `telegram_client.build_bot` — тот же дефолтный parse_mode=HTML и
    # тот же прокси, что у TelegramNotifier; ответы ниже — статичные строки без `<`/`&`.
    # Фоновая задача, упавшая с исключением, иначе умирает молча (его увидит только gather при
    # остановке) — поэтому падение логируется, а polling перезапускается.
    while True:
        bot = build_bot(bot_token=bot_token, proxy_url=proxy_url)
        try:
            await dispatcher.start_polling(
                bot, notification_service=notification_service, handle_signals=False,
            )
            return
        except Exception:
            logger.exception(
                '[telegram_polling] polling crashed, restarting in %.0fs', RESTART_DELAY_SECONDS,
            )
        finally:
            await bot.session.close()
        await asyncio.sleep(RESTART_DELAY_SECONDS)
