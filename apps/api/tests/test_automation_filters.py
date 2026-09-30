from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from apps.api.src.routers.automation.dependencies import get_automation_filters
from apps.api.src.routers.schema import DateRange
from packages.automation.src.enums import AutomationStatus


def _filters(**overrides):
    params = {
        'automation_status': None,
        'in_stock': None,
        'price_from': None,
        'price_to': None,
        'date_range': DateRange(),
    }
    return get_automation_filters(**{**params, **overrides})


def test_defaults_are_all_none():
    filters = _filters()
    assert filters.model_dump() == {
        'status': None,
        'in_stock': None,
        'price_from': None,
        'price_to': None,
        'date_from': None,
        'date_to': None,
    }


def test_values_are_passed_through():
    date_from = datetime(2026, 1, 1, tzinfo=timezone.utc)
    filters = _filters(
        automation_status=AutomationStatus.PAUSED,
        in_stock=False,
        price_from=100,
        price_to=500,
        date_range=DateRange(date_from=date_from),
    )
    assert filters.status == AutomationStatus.PAUSED
    assert filters.in_stock is False
    assert (filters.price_from, filters.price_to) == (100, 500)
    assert filters.date_from == date_from


def test_price_from_greater_than_price_to_is_rejected():
    with pytest.raises(HTTPException) as error:
        _filters(price_from=500, price_to=100)
    assert error.value.status_code == 422
