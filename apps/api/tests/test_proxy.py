import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from apps.api.src.config import config
from apps.api.src.routers.proxy.dependencies import verify_worker_token
from apps.api.src.routers.proxy.dependencies import build_proxy_response
from apps.api.src.routers.proxy.schema import CreateProxyRequest, UpdateProxyRequest
from packages.proxy.src.entities import ProxyEntity
from packages.proxy.src.enums import ProxyType
from packages.proxy.src.service import ProxyService


@pytest.fixture
def worker_token(monkeypatch):
    def _set(value: str) -> None:
        monkeypatch.setattr(config.PROXY, 'WORKER_TOKEN', value)

    return _set


@pytest.mark.asyncio
async def test_issue_is_disabled_without_configured_token(worker_token):
    worker_token('')
    with pytest.raises(HTTPException) as error:
        await verify_worker_token(x_worker_token='anything')
    assert error.value.status_code == 503


@pytest.mark.asyncio
@pytest.mark.parametrize('header', [None, '', 'wrong'])
async def test_issue_rejects_missing_or_wrong_token(worker_token, header):
    worker_token('secret')
    with pytest.raises(HTTPException) as error:
        await verify_worker_token(x_worker_token=header)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_issue_accepts_correct_token(worker_token):
    worker_token('secret')
    assert await verify_worker_token(x_worker_token='secret') is None


def test_create_request_validates_port_and_host():
    request = CreateProxyRequest(proxy_type='socks5', host='  1.2.3.4 ', port=1080)
    assert request.host == '1.2.3.4'
    assert request.is_active is True
    with pytest.raises(ValidationError):
        CreateProxyRequest(proxy_type='socks5', host='1.2.3.4', port=0)
    with pytest.raises(ValidationError):
        CreateProxyRequest(proxy_type='socks5', host='   ', port=1080)
    with pytest.raises(ValidationError):
        CreateProxyRequest(proxy_type='ftp', host='1.2.3.4', port=1080)


def test_update_request_only_reports_passed_fields():
    assert UpdateProxyRequest().changed_fields() == {}
    request = UpdateProxyRequest.model_validate({'port': 8080, 'username': None})
    assert request.changed_fields() == {'port': 8080, 'username': None}


@pytest.mark.parametrize('field', ['proxy_type', 'host', 'port', 'is_active'])
def test_update_request_rejects_null_for_required_columns(field):
    with pytest.raises(ValidationError):
        UpdateProxyRequest.model_validate({field: None})


def test_admin_response_never_exposes_password():
    entity = ProxyEntity(
        id=1,
        proxy_type=ProxyType.HTTP,
        host='h',
        port=3128,
        username='u',
        password='p@ss',
        is_active=True,
        note=None,
        created_at='2026-10-01T00:00:00Z',
        updated_at='2026-10-01T00:00:00Z',
    )
    dumped = build_proxy_response(proxy=entity).model_dump()
    assert dumped['has_password'] is True
    assert 'password' not in dumped


class FakeProxyRepository:
    def __init__(self, proxies: list[ProxyEntity]):
        self.proxies = proxies
        self.requested_type = 'unset'

    async def get_random_active(self, proxy_type=None):
        self.requested_type = proxy_type
        candidates = [
            proxy for proxy in self.proxies
            if proxy.is_active and (proxy_type is None or proxy.proxy_type == proxy_type)
        ]
        return candidates[0] if candidates else None


class FakeTransactionManager:
    def __init__(self, repository: FakeProxyRepository):
        self.proxy_repository = repository

    def __call__(self, **_kwargs):
        return self

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_exc):
        return None


@pytest.mark.asyncio
async def test_issue_random_passes_type_filter_and_returns_none_when_empty():
    repository = FakeProxyRepository(proxies=[])
    service = ProxyService(transaction_manager=FakeTransactionManager(repository))
    assert await service.issue_random(proxy_type=ProxyType.SOCKS5) is None
    assert repository.requested_type == ProxyType.SOCKS5


def test_generation_stats_shares_include_success():
    from datetime import date

    from apps.api.src.routers.proxy.dependencies import build_generation_stats
    from packages.proxy.src.entities import OutcomeCount, OutcomeDayCount
    from packages.sessions.src.enums import SessionGenerationOutcome

    stats = build_generation_stats(
        proxy_id=5,
        include_antibot=False,
        outcome_counts=[
            OutcomeCount(outcome=SessionGenerationOutcome.SUCCESS, count=6),
            OutcomeCount(outcome=SessionGenerationOutcome.VALIDATION, count=3),
            OutcomeCount(outcome=SessionGenerationOutcome.OTHER, count=1),
        ],
        day_counts=[
            OutcomeDayCount(
                day=date(2026, 10, 12), outcome=SessionGenerationOutcome.SUCCESS, count=6,
            ),
        ],
    )

    assert stats.total == 10
    assert stats.success_percent == 60
    assert [(share.outcome, share.percent) for share in stats.by_outcome] == [
        (SessionGenerationOutcome.SUCCESS, 60),
        (SessionGenerationOutcome.VALIDATION, 30),
        (SessionGenerationOutcome.OTHER, 10),
    ]
    assert stats.by_outcome[0].label == 'Успешно'
    assert stats.by_day[0].count == 6


def test_generation_stats_empty():
    from apps.api.src.routers.proxy.dependencies import build_generation_stats

    stats = build_generation_stats(
        proxy_id=1, include_antibot=True, outcome_counts=[], day_counts=[],
    )

    assert stats.total == 0 and stats.success_percent == 0
    assert stats.by_outcome == [] and stats.by_day == []


def test_record_generation_request_allows_missing_proxy():
    from apps.api.src.routers.proxy.schema import RecordGenerationRequest

    request = RecordGenerationRequest.model_validate(
        {'marketplace': 'ozon', 'outcome': 'success'},
    )

    assert request.proxy_id is None and request.traceback is None
