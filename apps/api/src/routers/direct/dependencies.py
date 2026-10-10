import logging
import time
import uuid

from dependency_injector.wiring import Provide, inject
from fastapi import Depends
from pydantic import BaseModel, ValidationError

from apps.api.src.config import config
from apps.api.src.container import DependencyContainer
from apps.api.src.routers.auth.dependencies import get_current_user
from apps.api.src.routers.direct.errors import (
    error_for_status,
    insufficient_credits_error,
    invalid_page_key_error,
    timeout_error,
    unavailable_error,
)
from core.enums import Marketplace
from packages.auth.src.security import auth_config
from packages.billing.src.enums import ReferenceType
from packages.billing.src.exceptions import InsufficientCreditsError
from packages.billing.src.service import BillingService
from packages.direct.src.entities import DirectReply, DirectRequest
from packages.direct.src.enums import DirectRequestType, DirectStatus
from packages.direct.src.page_key import (
    InvalidPageKeyError,
    decode_page_key,
    derive_page_key_secret,
    encode_page_key,
)
from packages.direct.src.redis_bus import DirectBus
from packages.user.src.entities import UserEntity

logger = logging.getLogger(__name__)

_PAGE_KEY_SECRET = derive_page_key_secret(auth_config.SECRET_KEY)
_SUBJECT_LOG_LIMIT = 50


@inject
async def require_positive_balance(
    billing_service: BillingService = Depends(Provide[DependencyContainer.billing_service]),
    current_user: UserEntity = Depends(get_current_user),
) -> None:
    """Проверка до обращения к воркеру: при балансе <= 0 или исчерпанном лимите расходов запрос
    к маркетплейсу не уходит вовсе."""
    try:
        await billing_service.ensure_can_spend(user_id=current_user.id)
    except InsufficientCreditsError as error:
        raise insufficient_credits_error(detail=error.detail) from error
    except Exception as error:
        logger.exception('[direct_billing_failed] stage=check user_id=%s', current_user.id)
        raise unavailable_error() from error


async def charge_direct_request(
    billing_service: BillingService, user_id: int, request: DirectRequest, quantity: int,
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
        )
    except Exception as error:
        logger.exception(
            '[direct_billing_failed] stage=charge request_id=%s user_id=%s',
            request.request_id, user_id,
        )
        raise unavailable_error() from error


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


async def dispatch_request(bus: DirectBus, request: DirectRequest) -> DirectReply:
    """Единственная точка обмена с воркером: возвращает только успешный ответ, всё остальное —
    обобщённая ошибка из `errors.py` (см. там правило про то, что клиенту не отдаётся)."""
    started = time.monotonic()
    reply: DirectReply | None = None
    try:
        reply = await _wait_for_reply(bus, request)
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


def parse_reply_items(reply: DirectReply, item_model: type[BaseModel]) -> list:
    """Ответ воркера, не разбирающийся в модель, — сбой внутри системы, а не вина клиента."""
    try:
        return [item_model.model_validate(item) for item in (reply.payload or {})['items']]
    except (ValidationError, KeyError, TypeError) as error:
        logger.exception('[direct_api_bad_reply] request_id=%s', reply.request_id)
        raise unavailable_error() from error
