from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from apps.api.src.routers.dependencies import get_date_range

UTC = timezone.utc


def test_no_bounds():
    date_range = get_date_range(date_from=None, date_to=None)
    assert date_range.date_from is None
    assert date_range.date_to is None


def test_only_from():
    date_from = datetime(2026, 1, 1, tzinfo=UTC)
    date_range = get_date_range(date_from=date_from, date_to=None)
    assert date_range.date_from == date_from
    assert date_range.date_to is None


def test_only_to():
    date_to = datetime(2026, 1, 1, tzinfo=UTC)
    date_range = get_date_range(date_from=None, date_to=date_to)
    assert date_range.date_from is None
    assert date_range.date_to == date_to


def test_naive_is_treated_as_utc():
    date_range = get_date_range(date_from=datetime(2026, 1, 1), date_to=None)
    assert date_range.date_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert date_range.date_from.utcoffset() == timedelta(0)


def test_aware_is_converted_to_utc():
    moscow = timezone(timedelta(hours=3))
    date_range = get_date_range(date_from=datetime(2026, 1, 1, 3, tzinfo=moscow), date_to=None)
    assert date_range.date_from == datetime(2026, 1, 1, tzinfo=UTC)
    assert date_range.date_from.utcoffset() == timedelta(0)


def test_equal_bounds_are_allowed():
    point = datetime(2026, 1, 1, tzinfo=UTC)
    date_range = get_date_range(date_from=point, date_to=point)
    assert date_range.date_from == date_range.date_to == point


def test_from_after_to_is_rejected():
    with pytest.raises(HTTPException) as error:
        get_date_range(
            date_from=datetime(2026, 2, 1, tzinfo=UTC), date_to=datetime(2026, 1, 1, tzinfo=UTC),
        )
    assert error.value.status_code == 422
