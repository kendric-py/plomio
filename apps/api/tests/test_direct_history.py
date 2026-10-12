import time

from fastapi import status

from apps.api.src.routers.direct.dependencies import DirectCall, build_history_record
from core.enums import Marketplace
from packages.direct.src.entities import DirectReply, DirectRequest
from packages.direct.src.enums import DirectOutcome, DirectRequestType, DirectStatus


def make_call(reply: DirectReply | None = None, **overrides) -> DirectCall:
    request = DirectRequest(
        request_id='abc',
        request_type=DirectRequestType.SEARCH,
        marketplace=Marketplace.OZON,
        input_value='кроссовки',
        page_cursor=None,
        created_at=time.time(),
        deadline_at=time.time() + 20,
    )
    call = DirectCall(request=request, user_id=7, started=time.monotonic(), reply=reply)
    for name, value in overrides.items():
        setattr(call, name, value)
    return call


def test_ok_reply_keeps_worker_diagnostics():
    reply = DirectReply(
        request_id='abc', status=DirectStatus.OK, next_cursor={'page': 2},
        attempts=1, queue_ms=5, session_ms=2, fetch_ms=300, worker_ms=320, proxy_id=4,
    )
    record = build_history_record(
        make_call(reply, items_count=12, credits_charged=12), status.HTTP_200_OK,
    )
    assert record.outcome == DirectOutcome.OK
    assert (record.items_count, record.has_next_page, record.credits_charged) == (12, True, 12)
    assert (record.proxy_id, record.fetch_ms, record.worker_ms) == (4, 300, 320)
    assert record.error_detail is None


def test_worker_failure_keeps_internal_reason():
    reply = DirectReply(request_id='abc', status=DirectStatus.NOT_FOUND, error='404 from market')
    record = build_history_record(make_call(reply), status.HTTP_404_NOT_FOUND)
    assert record.outcome == DirectOutcome.NOT_FOUND
    assert record.error_detail == '404 from market'
    assert record.http_status == 404


def test_no_reply_is_timeout_on_504_and_unavailable_otherwise():
    assert build_history_record(make_call(), status.HTTP_504_GATEWAY_TIMEOUT).outcome == DirectOutcome.TIMEOUT
    assert build_history_record(make_call(), status.HTTP_503_SERVICE_UNAVAILABLE).outcome == DirectOutcome.UNAVAILABLE


def test_billing_failure_and_bad_reply_override_worker_status():
    reply = DirectReply(request_id='abc', status=DirectStatus.OK)
    billing = build_history_record(make_call(reply, billing_failed=True), status.HTTP_503_SERVICE_UNAVAILABLE)
    assert billing.outcome == DirectOutcome.BILLING_FAILED
    bad = build_history_record(make_call(reply, bad_reply=True), status.HTTP_503_SERVICE_UNAVAILABLE)
    assert bad.outcome == DirectOutcome.ERROR
    assert bad.error_detail == 'unparsable worker reply'
