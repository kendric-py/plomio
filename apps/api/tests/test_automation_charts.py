from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from apps.api.src.routers.automation.dependencies import get_chart_period
from apps.api.src.routers.schema import DateRange
from packages.automation.src.entities import AutomationPriceChangeBucketEntity
from packages.automation.src.service import (
    PRICE_CHART_MAX_POINTS,
    align_to_step,
    fill_empty_buckets,
    price_chart_step_seconds,
)

UTC = timezone.utc


@pytest.mark.parametrize(
    ('span', 'expected'),
    [
        (timedelta(hours=1), 300),
        (timedelta(days=1), 3600),
        (timedelta(days=7), 21600),
        (timedelta(days=30), 86400),
        (timedelta(days=90), 259200),
        (timedelta(days=365), 1209600),
    ],
)
def test_step_depends_on_span(span, expected):
    assert price_chart_step_seconds(span=span) == expected


@pytest.mark.parametrize('minutes', [1, 10, 60, 600, 5000, 40000, 525600])
def test_points_count_is_bounded(minutes):
    span = timedelta(minutes=minutes)
    step = price_chart_step_seconds(span=span)
    assert span.total_seconds() / step <= PRICE_CHART_MAX_POINTS


def test_zoom_gives_finer_step_than_full_period():
    full = price_chart_step_seconds(span=timedelta(days=30))
    zoomed = price_chart_step_seconds(span=timedelta(days=2))
    assert zoomed < full


def test_align_to_step_is_multiple_of_step():
    moment = datetime(2026, 10, 2, 13, 47, 21, tzinfo=UTC)
    aligned = align_to_step(moment=moment, step_seconds=3600)
    assert aligned == datetime(2026, 10, 2, 13, tzinfo=UTC)


def test_fill_empty_buckets_adds_zeros():
    points = [
        AutomationPriceChangeBucketEntity(
            bucket_start=datetime(2026, 10, 2, tzinfo=UTC), changes_count=3,
        ),
    ]
    filled = fill_empty_buckets(
        points=points,
        since=datetime(2026, 9, 30, 15, tzinfo=UTC),
        until=datetime(2026, 10, 3, 9, tzinfo=UTC),
        step_seconds=86400,
    )
    assert [(p.bucket_start.day, p.changes_count) for p in filled] == [
        (30, 0), (1, 0), (2, 3), (3, 0),
    ]


def test_chart_period_defaults_to_last_days():
    period = get_chart_period(days=7, date_range=DateRange())
    assert period.date_to - period.date_from == timedelta(days=7)


def test_chart_period_zoom_uses_explicit_range():
    date_from = datetime(2026, 9, 1, tzinfo=UTC)
    date_to = datetime(2026, 9, 2, tzinfo=UTC)
    period = get_chart_period(days=30, date_range=DateRange(date_from=date_from, date_to=date_to))
    assert (period.date_from, period.date_to) == (date_from, date_to)


def test_chart_period_future_end_is_clamped_to_now():
    period = get_chart_period(
        days=30,
        date_range=DateRange(date_to=datetime.now(tz=UTC) + timedelta(days=5)),
    )
    assert period.date_to <= datetime.now(tz=UTC)


@pytest.mark.parametrize(
    'date_range',
    [
        DateRange(date_from=datetime(2026, 9, 2, tzinfo=UTC), date_to=datetime(2026, 9, 2, tzinfo=UTC)),
        DateRange(date_from=datetime.now(tz=UTC) + timedelta(days=1)),
        DateRange(date_from=datetime(2024, 1, 1, tzinfo=UTC), date_to=datetime(2026, 1, 1, tzinfo=UTC)),
    ],
)
def test_chart_period_invalid_range_is_rejected(date_range):
    with pytest.raises(HTTPException) as error:
        get_chart_period(days=30, date_range=date_range)
    assert error.value.status_code == 422
