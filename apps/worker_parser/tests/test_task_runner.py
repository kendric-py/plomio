from dataclasses import dataclass, field
from types import SimpleNamespace
from uuid import uuid4

import pytest

from apps.worker_parser.src import task_runner
from apps.worker_parser.src.entities import Page, WildberriesPaginationCursor
from apps.worker_parser.src.exceptions import InputResolutionError
from apps.worker_parser.src.execution import ExecutionOptions, PageExecutor
from apps.worker_parser.src.registry import PageOperation
from apps.worker_parser.src.session_provider import SessionHandle
from core.enums import Marketplace
from packages.result.src.entities import ProductPayload
from packages.task.src.enums import ParseType, TaskItemStatus, TaskStatus


class StubProvider:
    async def acquire(self, deadline):
        return SessionHandle(session_message=None, http_session=None)

    async def release(self, handle):
        return None

    async def discard(self, handle):
        return None


@dataclass
class FakeTaskService:
    task_status: TaskStatus = TaskStatus.RUNNING
    progress: list[tuple[dict | None, int]] = field(default_factory=list)
    completions: list[tuple[TaskItemStatus, str | None]] = field(default_factory=list)

    async def record_item_progress(self, item_id, cursor, result_count):
        self.progress.append((cursor, result_count))

    async def complete_item(self, item_id, status, error_reason=None):
        self.completions.append((status, error_reason))

    async def get_task_by_id(self, task_id):
        return SimpleNamespace(status=self.task_status)


@dataclass
class FakeResultService:
    recorded: list[int] = field(default_factory=list)

    async def record_results(self, task_item_id, marketplace, parse_type, payloads):
        self.recorded.append(len(payloads))


def product(index: int) -> ProductPayload:
    return ProductPayload(external_id=str(index), title='t', product_url='u')


def cursor(page_num: int) -> WildberriesPaginationCursor:
    return WildberriesPaginationCursor(marketplace=Marketplace.WILDBERRIES, page_num=page_num)


def make_task(result_limit=None, parse_type=ParseType.SEARCH_QUERY):
    return SimpleNamespace(
        id=uuid4(), marketplace=Marketplace.WILDBERRIES, parse_type=parse_type,
        result_limit=result_limit,
    )


def make_item():
    return SimpleNamespace(id=uuid4(), input_value='q', cursor=None, result_count=0)


def install_operation(monkeypatch, fetch_page, parse_type=ParseType.SEARCH_QUERY):
    operation = PageOperation(fetch_page=fetch_page, cursor_model=WildberriesPaginationCursor)
    monkeypatch.setattr(
        task_runner, 'OPERATIONS', {(Marketplace.WILDBERRIES, parse_type): operation},
    )


@pytest.mark.asyncio
async def test_progress_recorded_after_every_page_and_item_succeeds(monkeypatch):
    pages = [Page(items=[product(1), product(2)], next_cursor=cursor(1)), Page(items=[product(3)])]

    async def fetch_page(input_value, cursor_value, ctx):
        return pages.pop(0)

    install_operation(monkeypatch, fetch_page)
    task_service, result_service = FakeTaskService(), FakeResultService()
    executor = PageExecutor(StubProvider(), ExecutionOptions())

    await task_runner.process_item_pages(
        make_task(), make_item(), executor, task_service, result_service,
    )

    assert task_service.progress == [({'marketplace': 'wildberries', 'page_num': 1,
                                       'total_on_site': None, 'collected_so_far': None}, 2),
                                     (None, 3)]
    assert result_service.recorded == [2, 1]
    assert task_service.completions == [(TaskItemStatus.SUCCEEDED, None)]


@pytest.mark.asyncio
async def test_result_limit_stops_pagination(monkeypatch):
    seen_limits = []

    async def fetch_page(input_value, cursor_value, ctx):
        seen_limits.append(ctx.limit)
        return Page(items=[product(1), product(2)], next_cursor=cursor(1))

    install_operation(monkeypatch, fetch_page)
    task_service = FakeTaskService()
    executor = PageExecutor(StubProvider(), ExecutionOptions())

    await task_runner.process_item_pages(
        make_task(result_limit=2), make_item(), executor, task_service, FakeResultService(),
    )

    assert seen_limits == [2]
    assert task_service.completions == [(TaskItemStatus.SUCCEEDED, None)]


@pytest.mark.asyncio
async def test_result_limit_truncates_reviews_page_and_stops(monkeypatch):
    # Отзывные fetcher'ы отдают страницу целиком и ctx.limit не учитывают — лимит держит runner.
    fetch_calls = []

    async def fetch_page(input_value, cursor_value, ctx):
        fetch_calls.append(ctx.limit)
        return Page(items=[product(index) for index in range(5)], next_cursor=cursor(1))

    install_operation(monkeypatch, fetch_page, parse_type=ParseType.REVIEWS)
    task_service, result_service = FakeTaskService(), FakeResultService()
    executor = PageExecutor(StubProvider(), ExecutionOptions())

    await task_runner.process_item_pages(
        make_task(result_limit=3, parse_type=ParseType.REVIEWS),
        make_item(), executor, task_service, result_service,
    )

    assert len(fetch_calls) == 1
    assert result_service.recorded == [3]
    assert task_service.progress[-1][1] == 3
    assert task_service.completions == [(TaskItemStatus.SUCCEEDED, None)]


@pytest.mark.asyncio
async def test_result_limit_spans_review_pages(monkeypatch):
    pages = [
        Page(items=[product(1), product(2)], next_cursor=cursor(1)),
        Page(items=[product(3), product(4)], next_cursor=cursor(2)),
    ]

    async def fetch_page(input_value, cursor_value, ctx):
        return pages.pop(0)

    install_operation(monkeypatch, fetch_page, parse_type=ParseType.REVIEWS)
    result_service = FakeResultService()
    executor = PageExecutor(StubProvider(), ExecutionOptions())

    await task_runner.process_item_pages(
        make_task(result_limit=3, parse_type=ParseType.REVIEWS),
        make_item(), executor, FakeTaskService(), result_service,
    )

    assert result_service.recorded == [2, 1]


@pytest.mark.asyncio
async def test_result_limit_does_not_apply_to_product_page(monkeypatch):
    seen_limits = []

    async def fetch_page(input_value, cursor_value, ctx):
        seen_limits.append(ctx.limit)
        return Page(items=[product(1)])

    install_operation(monkeypatch, fetch_page, parse_type=ParseType.PRODUCT_PAGE)
    result_service = FakeResultService()
    executor = PageExecutor(StubProvider(), ExecutionOptions())

    await task_runner.process_item_pages(
        make_task(result_limit=1, parse_type=ParseType.PRODUCT_PAGE),
        make_item(), executor, FakeTaskService(), result_service,
    )

    assert seen_limits == [None]
    assert result_service.recorded == [1]


@pytest.mark.asyncio
async def test_paused_task_stops_without_completing_item(monkeypatch):
    async def fetch_page(input_value, cursor_value, ctx):
        return Page(items=[product(1)], next_cursor=cursor(1))

    install_operation(monkeypatch, fetch_page)
    task_service = FakeTaskService(task_status=TaskStatus.PAUSED)
    executor = PageExecutor(StubProvider(), ExecutionOptions())

    await task_runner.process_item_pages(
        make_task(), make_item(), executor, task_service, FakeResultService(),
    )

    assert len(task_service.progress) == 1
    assert task_service.completions == []


@pytest.mark.asyncio
async def test_failure_completes_item_with_policy_status(monkeypatch):
    async def fetch_page(input_value, cursor_value, ctx):
        raise InputResolutionError('bad input')

    install_operation(monkeypatch, fetch_page)
    task_service = FakeTaskService()
    executor = PageExecutor(StubProvider(), ExecutionOptions())

    await task_runner.process_item_pages(
        make_task(), make_item(), executor, task_service, FakeResultService(),
    )

    assert task_service.completions == [(TaskItemStatus.FAILED, 'bad input')]
