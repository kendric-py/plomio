import asyncio
import time
from dataclasses import dataclass, field

import pytest

from apps.worker_parser.src.entities import Page
from apps.worker_parser.src.enums import ErrorOutcome
from apps.worker_parser.src.exceptions import (
    BlockedError,
    InputResolutionError,
    RequestError,
    UpstreamDataError,
)
from apps.worker_parser.src.execution import ExecutionOptions, FetchFailedError, PageExecutor
from apps.worker_parser.src.session_provider import SessionHandle


@dataclass
class FakeProvider:
    events: list[str] = field(default_factory=list)

    async def acquire(self, deadline):
        self.events.append('acquire')
        return SessionHandle(session_message=None, http_session=None)

    async def release(self, handle):
        self.events.append('release')

    async def discard(self, handle):
        self.events.append('discard')


class ScriptedCall:
    """Вызов, который по очереди бросает заготовленные ошибки, а затем возвращает страницу."""

    def __init__(self, *errors: Exception) -> None:
        self.errors = list(errors)
        self.calls = 0

    async def __call__(self, context) -> Page:
        self.calls += 1
        if self.errors:
            raise self.errors.pop(0)
        return Page(items=[])


@pytest.mark.asyncio
async def test_success_keeps_session_until_close():
    provider = FakeProvider()
    executor = PageExecutor(provider, ExecutionOptions())
    await executor.run(ScriptedCall())
    assert provider.events == ['acquire']
    await executor.close()
    assert provider.events == ['acquire', 'release']


@pytest.mark.asyncio
async def test_reinit_policy_discards_session_and_retries_with_new_one():
    provider = FakeProvider()
    executor = PageExecutor(provider, ExecutionOptions())
    call = ScriptedCall(BlockedError('blocked'))
    await executor.run(call)
    assert call.calls == 2
    assert provider.events == ['acquire', 'discard', 'acquire']


@pytest.mark.asyncio
async def test_exhaustion_after_policy_attempts_discards_session():
    provider = FakeProvider()
    executor = PageExecutor(provider, ExecutionOptions())
    call = ScriptedCall(*[BlockedError('blocked') for _ in range(4)])
    with pytest.raises(FetchFailedError) as failure:
        await executor.run(call)
    assert call.calls == 4
    assert failure.value.classification.outcome == ErrorOutcome.ERROR
    assert provider.events[-1] == 'discard'
    await executor.close()
    assert 'release' not in provider.events


@pytest.mark.asyncio
async def test_keep_policy_exhaustion_leaves_session_releasable():
    provider = FakeProvider()
    executor = PageExecutor(provider, ExecutionOptions())
    call = ScriptedCall(UpstreamDataError('a'), UpstreamDataError('b'))
    with pytest.raises(FetchFailedError):
        await executor.run(call)
    assert call.calls == 2
    await executor.close()
    assert provider.events == ['acquire', 'release']


@pytest.mark.asyncio
async def test_attempt_cap_limits_total_attempts():
    executor = PageExecutor(FakeProvider(), ExecutionOptions(max_attempts=2))
    call = ScriptedCall(*[BlockedError('blocked') for _ in range(4)])
    with pytest.raises(FetchFailedError):
        await executor.run(call)
    assert call.calls == 2


@pytest.mark.asyncio
async def test_invalid_input_is_not_retried():
    executor = PageExecutor(FakeProvider(), ExecutionOptions())
    call = ScriptedCall(InputResolutionError('bad'))
    with pytest.raises(FetchFailedError) as failure:
        await executor.run(call)
    assert call.calls == 1
    assert failure.value.classification.outcome == ErrorOutcome.INVALID_INPUT


@pytest.mark.asyncio
async def test_404_maps_to_not_found():
    executor = PageExecutor(FakeProvider(), ExecutionOptions(max_attempts=1))
    with pytest.raises(FetchFailedError) as failure:
        await executor.run(ScriptedCall(RequestError('nope', status_code=404)))
    assert failure.value.classification.outcome == ErrorOutcome.NOT_FOUND


@pytest.mark.asyncio
async def test_deadline_maps_to_unavailable():
    async def slow(context):
        await asyncio.sleep(5)

    executor = PageExecutor(
        FakeProvider(), ExecutionOptions(deadline=time.monotonic() + 0.05),
    )
    with pytest.raises(FetchFailedError) as failure:
        await executor.run(slow)
    assert failure.value.classification.outcome == ErrorOutcome.UNAVAILABLE


@pytest.mark.asyncio
async def test_no_retry_mode_raises_raw_error_and_discards_session():
    provider = FakeProvider()
    executor = PageExecutor(provider, ExecutionOptions())
    with pytest.raises(UpstreamDataError):
        await executor.run(ScriptedCall(UpstreamDataError('x')), retry=False)
    assert provider.events == ['acquire', 'discard']


@pytest.mark.asyncio
async def test_404_is_not_retried_and_keeps_session():
    provider = FakeProvider()
    executor = PageExecutor(provider, ExecutionOptions())
    call = ScriptedCall(RequestError('nope', status_code=404))
    with pytest.raises(FetchFailedError) as failure:
        await executor.run(call)
    assert call.calls == 1
    assert failure.value.classification.outcome == ErrorOutcome.NOT_FOUND
    await executor.close()
    assert provider.events == ['acquire', 'release']
