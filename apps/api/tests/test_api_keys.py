from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import ValidationError
from sqlalchemy.dialects import postgresql

from apps.api.src.routers.api_keys import endpoints
from apps.api.src.routers.api_keys.dependencies import build_api_key_response
from apps.api.src.routers.api_keys.schema import CreateApiKeyRequest, UpdateApiKeyRequest
from apps.api.src.routers.auth.dependencies import (
    AuthContext,
    get_auth_context,
    get_session_user,
)
from packages.api_keys.src.entities import (
    ApiKeyEntity,
    ApiKeyUpdateData,
    ApiKeyWithSpendingEntity,
)
from packages.api_keys.src.enums import ApiKeyBlockReason, ApiKeyStatus
from packages.api_keys.src.exceptions import (
    ApiKeyCreditLimitExceededError,
    ApiKeyExpiredError,
    ApiKeyInactiveError,
    ApiKeyRevokedError,
    InvalidApiKeyError,
    InvalidApiKeyExpiryError,
)
from packages.api_keys.src.security import (
    API_KEY_PREFIX,
    display_prefix,
    generate_api_key,
    hash_api_key,
    looks_like_api_key,
)
from packages.api_keys.src.service import (
    ApiKeyService,
    resolve_api_key_status,
    resolve_block_reason,
)
from packages.auth.src.security import create_access_token
from packages.billing.src.exceptions import InsufficientCreditsError
from packages.billing.src.repository import CreditTransactionRepository
from packages.task.src.entities import TaskEntity, TaskItemEntity
from packages.task.src.enums import ParseType, TaskStatus
from packages.task.src.service import TaskService
from packages.user.src.entities import UserEntity

NOW = datetime.now(tz=timezone.utc)


def _key(**fields) -> ApiKeyEntity:
    return ApiKeyEntity(**{'id': 1, 'user_id': 7, 'name': 'n', 'prefix': 'plm_x', **fields})


def _transaction_manager(transaction: MagicMock) -> MagicMock:
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=transaction)
    context.__aexit__ = AsyncMock(return_value=False)
    manager = MagicMock(return_value=context)
    manager.commit = AsyncMock()
    return manager


def _service(transaction: MagicMock, spent: dict | None = None) -> ApiKeyService:
    billing = MagicMock()
    billing.get_spent_by_api_keys = AsyncMock(return_value=spent or {})
    return ApiKeyService(
        transaction_manager=_transaction_manager(transaction=transaction),
        billing_service=billing,
    )


# --- значение ключа


def test_generated_key_has_prefix_and_is_hashed_deterministically():
    raw_key = generate_api_key()
    assert raw_key.startswith(API_KEY_PREFIX)
    assert len(raw_key) > 40
    assert hash_api_key(raw_key=raw_key) == hash_api_key(raw_key=raw_key)
    assert hash_api_key(raw_key=raw_key) != hash_api_key(raw_key=generate_api_key())
    assert display_prefix(raw_key=raw_key) == raw_key[:12]


def test_jwt_is_not_mistaken_for_api_key():
    assert looks_like_api_key(value=generate_api_key())
    assert not looks_like_api_key(value=create_access_token(user_id=1))


# --- статус и блокировка


def test_status_revoked_wins_over_expired():
    expired = NOW - timedelta(days=1)
    assert resolve_api_key_status(api_key=_key(), now=NOW) == ApiKeyStatus.ACTIVE
    assert resolve_api_key_status(api_key=_key(expires_at=expired), now=NOW) == ApiKeyStatus.EXPIRED
    revoked = _key(expires_at=expired, revoked_at=NOW)
    assert resolve_api_key_status(api_key=revoked, now=NOW) == ApiKeyStatus.REVOKED


def test_block_reason_by_limit_and_activity():
    assert resolve_block_reason(api_key=_key(credit_limit=100), spent_credits=99, now=NOW) is None
    assert (
        resolve_block_reason(api_key=_key(credit_limit=100), spent_credits=100, now=NOW)
        == ApiKeyBlockReason.CREDIT_LIMIT
    )
    assert resolve_block_reason(api_key=_key(), spent_credits=10**9, now=NOW) is None
    assert (
        resolve_block_reason(api_key=_key(revoked_at=NOW), spent_credits=0, now=NOW)
        == ApiKeyBlockReason.INACTIVE
    )


def test_api_key_spend_errors_are_402_errors():
    # Все обработчики 402 ловят InsufficientCreditsError — ошибки ключа должны под них подходить.
    assert issubclass(ApiKeyCreditLimitExceededError, InsufficientCreditsError)
    assert issubclass(ApiKeyInactiveError, InsufficientCreditsError)


# --- сервис


@pytest.mark.asyncio
async def test_blocked_ids_batch_uses_spending_and_marks_missing_keys_inactive():
    transaction = MagicMock()
    transaction.api_key_repository.get_by_ids = AsyncMock(
        return_value=[_key(id=1, credit_limit=50), _key(id=2), _key(id=3, credit_limit=50)],
    )
    service = _service(transaction=transaction, spent={1: 50, 3: 10})

    blocked = await service.get_blocked_api_key_ids(api_key_ids=[1, 2, 3, 4, 1])

    assert blocked == {1: ApiKeyBlockReason.CREDIT_LIMIT, 4: ApiKeyBlockReason.INACTIVE}
    # Потраченное запрашивается только для ключей с лимитом.
    requested = service.billing_service.get_spent_by_api_keys.call_args.kwargs['api_key_ids']
    assert sorted(requested) == [1, 3]


@pytest.mark.asyncio
async def test_ensure_can_spend_raises_error_matching_reason():
    transaction = MagicMock()
    transaction.api_key_repository.get_by_ids = AsyncMock(return_value=[_key(credit_limit=5)])
    with pytest.raises(ApiKeyCreditLimitExceededError):
        await _service(transaction=transaction, spent={1: 7}).ensure_can_spend(api_key_id=1)

    transaction.api_key_repository.get_by_ids = AsyncMock(return_value=[_key(revoked_at=NOW)])
    with pytest.raises(ApiKeyInactiveError):
        await _service(transaction=transaction).ensure_can_spend(api_key_id=1)


@pytest.mark.parametrize(
    ('stored', 'error'),
    [
        (None, InvalidApiKeyError),
        (_key(revoked_at=NOW), ApiKeyRevokedError),
        (_key(expires_at=NOW - timedelta(seconds=1)), ApiKeyExpiredError),
    ],
)
@pytest.mark.asyncio
async def test_authenticate_rejects_unknown_revoked_and_expired(stored, error):
    transaction = MagicMock()
    transaction.api_key_repository.get_by_hash = AsyncMock(return_value=stored)
    with pytest.raises(error):
        await _service(transaction=transaction).authenticate(raw_key=generate_api_key())


@pytest.mark.asyncio
async def test_authenticate_touches_last_used_at_most_once_a_minute():
    transaction = MagicMock()
    transaction.api_key_repository.touch_last_used = AsyncMock()
    transaction.api_key_repository.get_by_hash = AsyncMock(
        return_value=_key(last_used_at=NOW - timedelta(seconds=10)),
    )
    service = _service(transaction=transaction)
    await service.authenticate(raw_key=generate_api_key())
    transaction.api_key_repository.touch_last_used.assert_not_called()

    transaction.api_key_repository.get_by_hash = AsyncMock(
        return_value=_key(last_used_at=NOW - timedelta(minutes=5)),
    )
    await service.authenticate(raw_key=generate_api_key())
    transaction.api_key_repository.touch_last_used.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_applies_only_explicit_fields_including_null():
    transaction = MagicMock()
    transaction.api_key_repository.get_by_id = AsyncMock(return_value=_key(credit_limit=10))
    transaction.api_key_repository.apply_changes = AsyncMock(return_value=_key())
    service = _service(transaction=transaction)

    await service.update_api_key(
        api_key_id=1, user_id=7, changes=ApiKeyUpdateData(credit_limit=None),
    )

    values = transaction.api_key_repository.apply_changes.call_args.kwargs['values']
    assert values == {'credit_limit': None}


@pytest.mark.asyncio
async def test_update_rejects_revoked_key_and_past_expiry():
    transaction = MagicMock()
    transaction.api_key_repository.get_by_id = AsyncMock(return_value=_key(revoked_at=NOW))
    with pytest.raises(ApiKeyRevokedError):
        await _service(transaction=transaction).update_api_key(
            api_key_id=1, user_id=7, changes=ApiKeyUpdateData(name='x'),
        )
    with pytest.raises(InvalidApiKeyExpiryError):
        await _service(transaction=transaction).update_api_key(
            api_key_id=1, user_id=7,
            changes=ApiKeyUpdateData(expires_at=NOW - timedelta(days=1)),
        )


def test_spent_by_api_keys_counts_only_debits_grouped_by_key():
    repository = CreditTransactionRepository(session=MagicMock())
    repository.session.execute = AsyncMock(return_value=[])
    statement_holder = {}

    async def capture(statement):
        statement_holder['sql'] = str(
            statement.compile(
                dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True},
            ),
        )
        return []

    repository.session.execute = capture
    import asyncio

    assert asyncio.run(repository.get_spent_by_api_keys(api_key_ids=[3, 4])) == {}
    assert 'api_key_id IN (3, 4)' in statement_holder['sql']
    assert 'amount < 0' in statement_holder['sql']
    assert 'GROUP BY credit_transactions.api_key_id' in statement_holder['sql']


# --- REST


def test_api_keys_router_builds_openapi_schema():
    app = FastAPI()
    app.include_router(endpoints.router, prefix='/api')
    paths = app.openapi()['paths']
    assert '/api/api-keys/' in paths
    assert '/api/api-keys/{api_key_id}/revoke' in paths


def test_create_request_validation():
    assert CreateApiKeyRequest(name='  CI  ').name == 'CI'
    with pytest.raises(ValidationError):
        CreateApiKeyRequest(name='   ')
    with pytest.raises(ValidationError):
        CreateApiKeyRequest(name='x', credit_limit=0)
    naive = CreateApiKeyRequest(name='x', expires_at=datetime(2030, 1, 1))
    assert naive.expires_at.tzinfo == timezone.utc


def test_update_request_tracks_explicit_nulls():
    body = UpdateApiKeyRequest.model_validate({'credit_limit': None})
    assert body.model_fields_set == {'credit_limit'}
    with pytest.raises(ValidationError):
        UpdateApiKeyRequest.model_validate({'name': None})


def test_response_computes_status_and_remaining():
    response = build_api_key_response(
        api_key=ApiKeyWithSpendingEntity(
            **_key(credit_limit=100, created_at=NOW).model_dump(), spent_credits=130,
        ),
    )
    assert response['status'] == ApiKeyStatus.ACTIVE
    assert response['remaining_credits'] == 0
    unlimited = build_api_key_response(
        api_key=ApiKeyWithSpendingEntity(**_key(created_at=NOW).model_dump(), spent_credits=5),
    )
    assert unlimited['remaining_credits'] is None


# --- авторизация


def _auth_services(api_key: ApiKeyEntity | None = None, error: Exception | None = None):
    user_service = MagicMock()
    user_service.get_by_id = AsyncMock(return_value=UserEntity(id=7, email='a@b.c'))
    api_key_service = MagicMock()
    api_key_service.authenticate = AsyncMock(return_value=api_key, side_effect=error)
    return user_service, api_key_service


@pytest.mark.asyncio
async def test_auth_accepts_api_key_header_and_bearer_with_prefix():
    user_service, api_key_service = _auth_services(api_key=_key())
    raw_key = generate_api_key()

    via_header = await get_auth_context(
        credentials=None, header_api_key=raw_key,
        user_service=user_service, api_key_service=api_key_service,
    )
    via_bearer = await get_auth_context(
        credentials=HTTPAuthorizationCredentials(scheme='Bearer', credentials=raw_key),
        header_api_key=None, user_service=user_service, api_key_service=api_key_service,
    )

    assert via_header.api_key.id == via_bearer.api_key.id == 1
    assert via_header.user.id == 7


@pytest.mark.asyncio
async def test_auth_jwt_has_no_api_key_and_missing_credentials_is_401():
    user_service, api_key_service = _auth_services()
    context = await get_auth_context(
        credentials=HTTPAuthorizationCredentials(
            scheme='Bearer', credentials=create_access_token(user_id=7),
        ),
        header_api_key=None, user_service=user_service, api_key_service=api_key_service,
    )
    assert context.api_key is None
    api_key_service.authenticate.assert_not_called()

    with pytest.raises(HTTPException) as missing:
        await get_auth_context(
            credentials=None, header_api_key=None,
            user_service=user_service, api_key_service=api_key_service,
        )
    assert missing.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_revoked_key_is_401_with_reason():
    user_service, api_key_service = _auth_services(error=ApiKeyRevokedError())
    with pytest.raises(HTTPException) as error:
        await get_auth_context(
            credentials=None, header_api_key=generate_api_key(),
            user_service=user_service, api_key_service=api_key_service,
        )
    assert error.value.status_code == 401
    assert error.value.detail == ApiKeyRevokedError.detail


@pytest.mark.asyncio
async def test_session_only_endpoints_reject_api_key():
    user = UserEntity(id=7, email='a@b.c')
    assert await get_session_user(context=AuthContext(user=user)) == user
    with pytest.raises(HTTPException) as error:
        await get_session_user(context=AuthContext(user=user, api_key=_key()))
    assert error.value.status_code == 403


# --- задачи: учёт и остановка по ключу


def _task_service(api_key_can_spend: bool) -> tuple[TaskService, MagicMock, MagicMock]:
    task = TaskEntity(
        id=uuid4(), user_id=7, parse_type=ParseType.SEARCH_QUERY, status=TaskStatus.RUNNING,
        api_key_id=3,
    )
    transaction = MagicMock()
    transaction.task_item_repository.get_by_id = AsyncMock(
        return_value=TaskItemEntity(id=uuid4(), task_id=task.id, result_count=0),
    )
    transaction.task_item_repository.update = AsyncMock(
        return_value=TaskItemEntity(id=uuid4(), task_id=task.id, result_count=5),
    )
    transaction.task_repository.get_by_id = AsyncMock(return_value=task)
    transaction.task_repository.update = AsyncMock(return_value=task)
    billing = MagicMock()
    billing.charge = AsyncMock()
    billing.can_spend = AsyncMock(return_value=True)
    api_keys = MagicMock()
    api_keys.can_spend = AsyncMock(return_value=api_key_can_spend)
    service = TaskService(
        transaction_manager=_transaction_manager(transaction=transaction),
        billing_service=billing,
        notification_service=MagicMock(),
        api_key_service=api_keys,
    )
    return service, billing, transaction


@pytest.mark.asyncio
async def test_result_charge_carries_task_api_key():
    service, billing, transaction = _task_service(api_key_can_spend=True)
    await service.record_item_progress(item_id=uuid4(), cursor=None, result_count=5)
    assert billing.charge.call_args.kwargs['api_key_id'] == 3
    transaction.task_repository.update.assert_not_called()


@pytest.mark.asyncio
async def test_task_pauses_when_its_api_key_is_exhausted():
    service, _, transaction = _task_service(api_key_can_spend=False)
    await service.record_item_progress(item_id=uuid4(), cursor=None, result_count=5)
    paused = transaction.task_repository.update.call_args.kwargs['entity']
    assert paused.status == TaskStatus.PAUSED


# --- автоматизации: проверка пропускается, если ключ автоматизации исчерпан


@pytest.mark.asyncio
async def test_dispatch_skips_automation_whose_api_key_is_blocked():
    from core.enums import Marketplace
    from packages.automation.src.entities import AutomationEntity
    from packages.automation.src.service import AutomationService

    blocked = AutomationEntity(
        id=uuid4(), user_id=7, marketplace=Marketplace.OZON, input_value='1',
        check_frequency_minutes=30, api_key_id=3,
    )
    allowed = AutomationEntity(
        id=uuid4(), user_id=7, marketplace=Marketplace.OZON, input_value='2',
        check_frequency_minutes=30, api_key_id=4,
    )
    transaction = MagicMock()
    transaction.automation_repository.claim_due_for_dispatch = AsyncMock(
        return_value=[blocked, allowed],
    )
    transaction.automation_repository.finalize_check = AsyncMock()
    transaction.automation_repository.set_pending_task = AsyncMock()
    billing = MagicMock()
    billing.get_blocked_user_ids = AsyncMock(return_value={})
    api_keys = MagicMock()
    api_keys.get_blocked_api_key_ids = AsyncMock(
        return_value={3: ApiKeyBlockReason.CREDIT_LIMIT},
    )
    task_service = MagicMock()
    task_service.create_task = AsyncMock(return_value=TaskEntity(id=uuid4()))
    service = AutomationService(
        transaction_manager=_transaction_manager(transaction=transaction),
        task_service=task_service,
        result_service=MagicMock(),
        billing_service=billing,
        notification_service=MagicMock(),
        api_key_service=api_keys,
    )

    result = await service.dispatch_due_checks(
        batch_size=10, out_of_stock_check_frequency_minutes=5,
    )

    assert result == {'dispatched': 1}
    skipped = transaction.automation_repository.finalize_check.call_args.kwargs
    assert skipped['automation_id'] == blocked.id
    assert skipped['last_check_error'] == 'api_key_credit_limit'
    assert task_service.create_task.call_args.kwargs['api_key_id'] == 4


def test_transaction_journal_filters_by_api_key():
    from sqlalchemy import select

    from packages.billing.src.entities import TransactionFilters
    from packages.billing.src.models import CreditTransaction

    repository = CreditTransactionRepository(session=MagicMock())
    statement = repository._apply_filters(
        statement=select(CreditTransaction.id), user_id=7,
        filters=TransactionFilters(api_key_id=3),
    )
    sql = str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}),
    )
    assert 'credit_transactions.api_key_id = 3' in sql
