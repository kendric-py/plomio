from unittest.mock import MagicMock
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from core.enums import Marketplace
from packages.automation.src.entities import AdminAutomationFilters
from packages.automation.src.enums import AutomationStatus
from packages.automation.src.models import Automation
from packages.automation.src.repository import AutomationRepository


def _sql(filters: AdminAutomationFilters) -> str:
    repository = AutomationRepository(session=MagicMock())
    statement = repository._apply_admin_filters(statement=select(Automation.id), filters=filters)
    return str(
        statement.compile(dialect=postgresql.dialect(), compile_kwargs={'literal_binds': True}),
    )


def test_no_filters_adds_no_where():
    assert 'WHERE' not in _sql(AdminAutomationFilters())


def test_overdue_filter_uses_dispatch_condition():
    sql = _sql(AdminAutomationFilters(overdue=True))
    assert "status = 'ACTIVE'" in sql
    assert 'next_check_at <=' in sql
    assert 'pending_task_id IS NULL' in sql


def test_overdue_false_is_not_a_filter():
    assert 'WHERE' not in _sql(AdminAutomationFilters(overdue=False))


def test_has_error_filter():
    assert 'last_check_error IS NOT NULL' in _sql(AdminAutomationFilters(has_error=True))


def test_search_matches_name_article_and_link_case_insensitively():
    sql = _sql(AdminAutomationFilters(search='iphone'))
    assert sql.count('ILIKE') == 3
    assert '%iphone%' in sql


def test_filters_combine_with_and():
    sql = _sql(
        AdminAutomationFilters(
            automation_id=uuid4(),
            user_id=3,
            marketplace=Marketplace.OZON,
            status=AutomationStatus.PAUSED,
        ),
    )
    assert sql.count(' AND ') == 3


def test_admin_routes_registered():
    from fastapi import FastAPI

    from apps.api.src.routers.router import api_router

    app = FastAPI()
    app.include_router(api_router)
    paths = app.openapi()['paths']
    assert 'get' in paths['/api/admin/automations/']
    assert 'get' in paths['/api/admin/automations/summary']
    assert 'post' in paths['/api/admin/automations/{automation_id}/pause']
    assert 'post' in paths['/api/admin/automations/{automation_id}/resume']
    assert 'delete' in paths['/api/admin/automations/{automation_id}']
