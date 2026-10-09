from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from apps.api.src.routers.schema import DateRange
from apps.api.src.routers.task_admin.dependencies import get_admin_task_filters
from apps.api.src.routers.task_admin.schema import AdminTaskSummaryResponse
from core.enums import Marketplace
from packages.task.src.entities import AdminTaskFilters, TaskEntity
from packages.task.src.enums import ParseType, TaskPurpose, TaskStatus
from packages.task.src.exceptions import InvalidTaskTransitionError
from packages.task.src.models import Task
from packages.task.src.repository import TaskRepository
from packages.task.src.service import TaskService


def _filters(**overrides) -> AdminTaskFilters:
    params = {
        'task_id': None,
        'item_id': None,
        'automation_id': None,
        'purpose': None,
        'user_id': None,
        'marketplace': None,
        'task_status': None,
        'parse_type': None,
        'date_range': DateRange(),
    }
    return get_admin_task_filters(**{**params, **overrides})


def _sql(filters: AdminTaskFilters) -> str:
    repository = TaskRepository(session=MagicMock())
    statement = repository._apply_admin_filters(statement=select(Task.id), filters=filters)
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}),
    )


def test_filters_default_to_none():
    assert all(value is None for value in _filters().model_dump().values())


def test_filters_pass_values_through():
    task_id = uuid4()
    date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
    filters = _filters(
        task_id=task_id,
        purpose=TaskPurpose.AUTOMATION,
        user_id=7,
        marketplace=Marketplace.WILDBERRIES,
        task_status=TaskStatus.EXPIRED,
        parse_type=ParseType.PRODUCT_PAGE,
        date_range=DateRange(date_from=date_from),
    )
    assert filters.task_id == task_id
    assert filters.status == TaskStatus.EXPIRED
    assert filters.date_from == date_from


def test_no_filters_adds_no_where():
    assert 'WHERE' not in _sql(AdminTaskFilters())


def test_purpose_maps_to_automation_id_null_check():
    assert 'automation_id IS NULL' in _sql(AdminTaskFilters(purpose=TaskPurpose.TASK))
    assert 'automation_id IS NOT NULL' in _sql(AdminTaskFilters(purpose=TaskPurpose.AUTOMATION))


def test_item_id_filter_looks_up_parent_task_through_task_items():
    item_id = uuid4()
    sql = _sql(AdminTaskFilters(item_id=item_id))
    assert 'FROM task_items' in sql
    assert str(item_id) in sql


def test_automation_id_filter_matches_check_tasks_of_that_automation():
    automation_id = uuid4()
    sql = _sql(AdminTaskFilters(automation_id=automation_id))
    assert f"automation_id = '{automation_id}'" in sql


def test_filters_combine_with_and():
    sql = _sql(AdminTaskFilters(user_id=5, status=TaskStatus.FAILED, marketplace=Marketplace.OZON))
    assert sql.count(' AND ') == 2


def _service(rows) -> TaskService:
    transaction = MagicMock()
    transaction.task_repository.count_grouped_by_status = AsyncMock(return_value=rows)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=transaction)
    context.__aexit__ = AsyncMock(return_value=False)
    transaction_manager = MagicMock(return_value=context)
    return TaskService(
        transaction_manager=transaction_manager,
        billing_service=MagicMock(),
        notification_service=MagicMock(),
    )


@pytest.mark.asyncio
async def test_summary_splits_tasks_and_automation_tasks_and_fills_zeros():
    service = _service(
        [
            (TaskStatus.SUCCEEDED, False, 5),
            (TaskStatus.FAILED, False, 2),
            (TaskStatus.EXPIRED, False, 1),
            (TaskStatus.FAILED, True, 4),
        ],
    )
    summary = await service.get_summary()

    assert summary['tasks']['total'] == 8
    assert summary['tasks']['SUCCEEDED'] == 5
    assert summary['tasks']['EXPIRED'] == 1
    assert summary['tasks']['QUEUED'] == 0
    assert summary['automations']['total'] == 4
    assert summary['automations']['FAILED'] == 4
    # Форма совпадает с REST-схемой.
    AdminTaskSummaryResponse.model_validate(obj={'tasks': summary['tasks']})


@pytest.mark.asyncio
async def test_restart_rejects_non_restartable_status():
    task = TaskEntity(id=uuid4(), user_id=1, status=TaskStatus.RUNNING)
    transaction = MagicMock()
    transaction.task_repository.lock_by_id = AsyncMock(return_value=task)
    context = MagicMock()
    context.__aenter__ = AsyncMock(return_value=transaction)
    context.__aexit__ = AsyncMock(return_value=False)
    service = TaskService(
        transaction_manager=MagicMock(return_value=context),
        billing_service=MagicMock(),
        notification_service=MagicMock(),
    )
    with pytest.raises(InvalidTaskTransitionError):
        await service.restart_task(task_id=task.id, ttl=timedelta(seconds=60))


def test_notification_response_is_built_from_delivery_entity():
    from apps.api.src.routers.task_admin.schema import AdminTaskNotificationResponse
    from packages.notifications.src.entities import NotificationDeliveryEntity
    from packages.notifications.src.enums import NotificationChannel, NotificationDeliveryStatus

    delivery = NotificationDeliveryEntity(
        id=1,
        user_id=7,
        event_code='automation.change_detected',
        channel=NotificationChannel.TELEGRAM,
        status=NotificationDeliveryStatus.SENT,
        payload={'task_id': str(uuid4()), 'changes_text': 'Цена: 100 → 90'},
        sent_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    response = AdminTaskNotificationResponse.model_validate(obj=delivery, from_attributes=True)
    assert response.channel == NotificationChannel.TELEGRAM
    assert response.status == NotificationDeliveryStatus.SENT
    assert response.payload['changes_text'] == 'Цена: 100 → 90'


def test_delivery_lookup_includes_legacy_deliveries_for_automation_check_tasks():
    from packages.notifications.src.repository import NotificationDeliveryRepository

    repository = NotificationDeliveryRepository(session=MagicMock())
    captured = []
    repository.session.scalars = AsyncMock(return_value=[])
    repository.session.scalars.side_effect = lambda statement: captured.append(statement) or []

    import asyncio
    automation_id = uuid4()
    asyncio.run(
        repository.get_by_task_id(
            task_id=uuid4(),
            automation_id=automation_id,
            finished_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    )
    sql = str(
        captured[0].compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}),
    )
    assert 'IS NULL' in sql
    assert str(automation_id) in sql
    assert 'automation.change_detected' in sql

    # Без automation_id — только точное совпадение по task_id.
    captured.clear()
    asyncio.run(repository.get_by_task_id(task_id=uuid4()))
    assert 'IS NULL' not in str(captured[0].compile(dialect=postgresql.dialect()))


def test_automation_admin_routes_are_registered():
    from fastapi import FastAPI

    from apps.api.src.routers.router import api_router

    app = FastAPI()
    app.include_router(api_router)
    paths = app.openapi()["paths"]
    assert "get" in paths["/api/admin/automations/{automation_id}"]
    assert "get" in paths["/api/admin/automations/{automation_id}/notifications"]


def test_list_item_carries_failed_items_with_original_errors():
    from apps.api.src.routers.task_admin.schema import AdminTaskListItemResponse

    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    response = AdminTaskListItemResponse.model_validate(
        obj={
            'id': uuid4(), 'parse_type': 'PRODUCT_PAGE', 'marketplace': 'wildberries',
            'status': 'FAILED', 'priority': 5, 'queue_expires_at': now, 'result_limit': 1,
            'error_reason': 'item_failed', 'user_id': 1, 'automation_id': uuid4(),
            'pricing_dimension_code': None, 'pricing_dimension_value': None,
            'started_at': now, 'finished_at': now, 'created_at': now, 'updated_at': now,
            'total_items': 1, 'processed_items': 1, 'result_count': 0,
            'failed_items': [
                {'id': uuid4(), 'input_value': 'https://wb/1', 'error_reason': 'blocked 498'},
            ],
        },
    )
    assert response.error_reason == 'item_failed'
    assert response.failed_items[0].error_reason == 'blocked 498'
