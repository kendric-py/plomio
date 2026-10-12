from datetime import datetime, timedelta, timezone

from apps.api.src.routers.overview.dependencies import build_series, percent, sum_series
from core.entities import TimeBucketCount
from core.enums import BucketUnit

NOW = datetime(2026, 10, 12, 12, 30, tzinfo=timezone.utc)


def test_build_series_fills_empty_buckets_with_zeros():
    points = [TimeBucketCount(bucket=datetime(2026, 10, 12, 11, tzinfo=timezone.utc), key='a', count=3)]
    series = build_series(
        points=points, keys=['a', 'b'], date_from=NOW - timedelta(hours=3), unit=BucketUnit.HOUR, now=NOW,
    )
    assert [point.bucket.hour for point in series] == [9, 10, 11, 12]
    assert [point.values for point in series] == [
        {'a': 0, 'b': 0}, {'a': 0, 'b': 0}, {'a': 3, 'b': 0}, {'a': 0, 'b': 0},
    ]


def test_build_series_ignores_unknown_keys_and_out_of_window_points():
    points = [
        TimeBucketCount(bucket=datetime(2026, 10, 12, 12, tzinfo=timezone.utc), key='x', count=1),
        TimeBucketCount(bucket=datetime(2026, 10, 1, tzinfo=timezone.utc), key='a', count=9),
    ]
    series = build_series(
        points=points, keys=['a'], date_from=NOW - timedelta(hours=1), unit=BucketUnit.HOUR, now=NOW,
    )
    assert all(point.values == {'a': 0} for point in series)


def test_percent_and_sum_series():
    assert percent(1, 3) == 33
    assert percent(0, 0) == 0
    points = [
        TimeBucketCount(bucket=NOW, key='a', count=2),
        TimeBucketCount(bucket=NOW, key='b', count=5),
    ]
    assert sum_series(points, 'a') == 2
