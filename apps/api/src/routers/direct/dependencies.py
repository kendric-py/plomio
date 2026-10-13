import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass

from dependency_injector.wiring import Provide, inject
from fastapi import Depends, HTTPException, status
from pydantic import BaseModel, ValidationError

from apps.api.src.config import config
from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_api_key_id, get_current_user
from apps.api.src.routers.direct.errors import (
    error_for_status,
    insufficient_credits_error,
    invalid_page_key_error,
    timeout_error,
    unavailable_error,
)
from core.enums import Marketplace
from packages.api_keys.src.service import ApiKeyService
from packages.auth.src.security import auth_config
from packages.billing.src.enums import ReferenceType
from packages.billing.src.exceptions import InsufficientCreditsError
from packages.billing.src.service import BillingService
from packages.direct.src.entities import DirectReply, DirectRequest, DirectRequestRecordEntity
from packages.direct.src.enums import DirectOutcome, DirectRequestType, DirectStatus
from packages.direct.src.page_key import (
    InvalidPageKeyError,
    decode_page_key,
    derive_page_key_secret,
    encode_page_key,
)
from packages.direct.src.redis_bus import DirectBus
from packages.direct.src.service import DirectService
from packages.user.src.entities import UserEntity

logger = logging.getLogger(__name__)

_PAGE_KEY_SECRET = derive_page_key_secret(auth_config.SECRET_KEY)
_SUBJECT_LOG_LIMIT = 50

OUTCOME_BY_STATUS = {
    DirectStatus.OK: DirectOutcome.OK,
    DirectStatus.INVALID_INPUT: DirectOutcome.INVALID_INPUT,
    DirectStatus.NOT_FOUND: DirectOutcome.NOT_FOUND,
    DirectStatus.UNAVAILABLE: DirectOutcome.UNAVAILABLE,
    DirectStatus.ERROR: DirectOutcome.ERROR,
}

# Ссылки на фоновые задачи записи истории: без них задачу может собрать сборщик мусора до конца.
_history_tasks: set[asyncio.Task] = set()


@dataclass
class DirectCall:
    """Что известно о запросе по ходу обработки; из этого собирается строка истории."""

    request: DirectRequest
    user_id: int
    started: float
    reply: DirectReply | None = None
    items_count: int | None = None
    credits_charged: int = 0
    billing_failed: bool = False
    bad_reply: bool = False


@inject
async def require_positive_balance(
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
    api_key_service: ApiKeyService = Depends(Provide[DependencyContainer.api_key_service]),
    current_user: UserEntity = Depends(get_current_user),
    api_key_id: int | None = Depends(get_current_api_key_id),
) -> None:
    """Проверка до обращения к воркеру: при балансе <= 0, исчерпанном лимите расходов или лимите
    API-ключа запрос к маркетплейсу не уходит вовсе."""
    try:
        await billing_service.ensure_can_spend(user_id=current_user.id)
        if api_key_id is not None:
            await api_key_service.ensure_can_spend(api_key_id=api_key_id)
    except InsufficientCreditsError as error:
        raise insufficient_credits_error(detail=error.detail) from error
    except Exception as error:
        logger.exception('[direct_billing_failed] stage=check user_id=%s', current_user.id)
        raise unavailable_error() from error


async def charge_direct_request(
    billing_service: BillingService,
    user_id: int,
    request: DirectRequest,
    quantity: int,
    call: DirectCall | None = None,
    api_key_id: int | None = None,
) -> None:
    """Списание только за успешный ответ (вызывается после разбора `reply`). Сбой списания →
    503: данные клиенту не отдаются, чтобы не раздавать их бесплатно."""
    try:
        await billing_service.charge(
            user_id=user_id,
            action_code=f'direct.{request.request_type.name}',
            quantity=quantity,
            reference_type=ReferenceType.DIRECT,
            reference_id=request.request_id,
            api_key_id=api_key_id,
        )
    except Exception as error:
        logger.exception(
            '[direct_billing_failed] stage=charge request_id=%s user_id=%s',
            request.request_id, user_id,
        )
        if call is not None:
            call.billing_failed = True
        raise unavailable_error() from error
    if call is not None:
        call.credits_charged = quantity


def decode_cursor(page_key: str | None, marketplace: Marketplace, subject: str) -> dict | None:
    if page_key is None:
        return None
    try:
        return decode_page_key(
            secret=_PAGE_KEY_SECRET, page_key=page_key, marketplace=marketplace, subject=subject,
        )
    except InvalidPageKeyError as error:
        raise invalid_page_key_error() from error


def encode_next_page_key(
    reply: DirectReply, marketplace: Marketplace, subject: str,
) -> str | None:
    if reply.next_cursor is None:
        return None
    return encode_page_key(
        secret=_PAGE_KEY_SECRET,
        marketplace=marketplace,
        subject=subject,
        cursor=reply.next_cursor,
        ttl_seconds=config.DIRECT.PAGE_KEY_TTL_SECONDS,
    )


async def _wait_for_reply(bus: DirectBus, request: DirectRequest) -> DirectReply | None:
    try:
        await bus.enqueue(request)
        return await bus.wait_reply(
            request.request_id, timeout_seconds=config.DIRECT.REQUEST_TIMEOUT_SECONDS,
        )
    except Exception as error:
        logger.exception(
            '[direct_api_failed] request_id=%s error=%s', request.request_id, type(error).__name__,
        )
        raise unavailable_error() from error


async def dispatch_request(
    bus: DirectBus, request: DirectRequest, call: DirectCall | None = None,
) -> DirectReply:
    """Единственная точка обмена с воркером: возвращает только успешный ответ, всё остальное —
    обобщённая ошибка из `errors.py` (см. там правило про то, что клиенту не отдаётся)."""
    started = time.monotonic()
    reply: DirectReply | None = None
    try:
        reply = await _wait_for_reply(bus, request)
        if call is not None:
            call.reply = reply
        if reply is None:
            raise timeout_error()
        if reply.status != DirectStatus.OK:
            raise error_for_status(
                reply.status, request.request_type, request.page_cursor is not None,
            )
        return reply
    finally:
        logger.info(
            '[direct_api] request_id=%s type=%s marketplace=%s article=%s status=%s total_ms=%d',
            request.request_id,
            request.request_type.value,
            request.marketplace.value,
            request.input_value[:_SUBJECT_LOG_LIMIT],
            reply.status.value if reply else 'timeout',
            (time.monotonic() - started) * 1000,
        )


def build_request(
    request_type: DirectRequestType,
    marketplace: Marketplace,
    input_value: str,
    page_cursor: dict | None,
) -> DirectRequest:
    now = time.time()
    return DirectRequest(
        request_id=uuid.uuid4().hex,
        request_type=request_type,
        marketplace=marketplace,
        input_value=input_value,
        page_cursor=page_cursor,
        created_at=now,
        deadline_at=now + config.DIRECT.REQUEST_TIMEOUT_SECONDS,
    )


def parse_reply_items(
    reply: DirectReply, item_model: type[BaseModel], call: DirectCall | None = None,
) -> list:
    """Ответ воркера, не разбирающийся в модель, — сбой внутри системы, а не вина клиента."""
    try:
        items = [item_model.model_validate(item) for item in (reply.payload or {})['items']]
    except (ValidationError, KeyError, TypeError) as error:
        logger.exception('[direct_api_bad_reply] request_id=%s', reply.request_id)
        if call is not None:
            call.bad_reply = True
        raise unavailable_error() from error
    if call is not None:
        call.items_count = len(items)
    return items


def build_history_record(call: DirectCall, http_status: int) -> DirectRequestRecordEntity:
    """Строка истории по итогам обработки. Итог: статус ответа воркера, а если ответа нет — таймаут
    (504) или недоступность; сбой списания и неразбираемый ответ различаются отдельно."""
    reply = call.reply
    if call.billing_failed:
        outcome = DirectOutcome.BILLING_FAILED
    elif call.bad_reply:
        outcome = DirectOutcome.ERROR
    elif reply is not None:
        outcome = OUTCOME_BY_STATUS[reply.status]
    elif http_status == status.HTTP_504_GATEWAY_TIMEOUT:
        outcome = DirectOutcome.TIMEOUT
    else:
        outcome = DirectOutcome.UNAVAILABLE
    request = call.request
    return DirectRequestRecordEntity(
        request_id=request.request_id,
        user_id=call.user_id,
        marketplace=request.marketplace,
        request_type=request.request_type,
        outcome=outcome,
        http_status=http_status,
        input_value=request.input_value,
        is_next_page=request.page_cursor is not None,
        items_count=call.items_count,
        has_next_page=(reply.next_cursor is not None) if call.items_count is not None and reply else None,
        credits_charged=call.credits_charged,
        proxy_id=reply.proxy_id if reply else None,
        total_ms=round((time.monotonic() - call.started) * 1000),
        attempts=reply.attempts if reply else None,
        queue_ms=reply.queue_ms if reply else None,
        session_ms=reply.session_ms if reply else None,
        fetch_ms=reply.fetch_ms if reply else None,
        worker_ms=reply.worker_ms if reply else None,
        error_detail=(reply.error if reply and reply.status != DirectStatus.OK else None)
        or ('unparsable worker reply' if call.bad_reply else None),
    )


async def _save_history(direct_service: DirectService, record: DirectRequestRecordEntity) -> None:
    try:
        await direct_service.record_request(record=record)
    except Exception:
        logger.exception('[direct_history_failed] request_id=%s', record.request_id)


@asynccontextmanager
async def track_direct_request(
    direct_service: DirectService, request: DirectRequest, user_id: int,
):
    """Оборачивает обработку direct-запроса и пишет строку в историю (`direct_requests`) в фоне,
    после ответа клиенту: задержку не добавляет, сбой записи только логируется."""
    call = DirectCall(request=request, user_id=user_id, started=time.monotonic())
    http_status = status.HTTP_200_OK
    try:
        yield call
    except HTTPException as error:
        http_status = error.status_code
        raise
    except BaseException:
        http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
        raise
    finally:
        record = build_history_record(call, http_status)
        task = asyncio.create_task(_save_history(direct_service, record))
        _history_tasks.add(task)
        task.add_done_callback(_history_tasks.discard)
