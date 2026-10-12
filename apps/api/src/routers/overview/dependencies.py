from datetime import datetime, timedelta, timezone

from apps.api.src.routers.overview.enums import OverviewWindow
from apps.api.src.routers.overview.schema import OverviewPoint, WorkerGroupHealth
from core.entities import TimeBucketCount
from core.enums import BucketUnit
from packages.worker_health.src.enums import WorkerType
from packages.worker_health.src.redis_store import parse_member

# Окно -> (длина, шаг точек графика): 60 точек по минуте, 24 по часу, 7 по дню.
WINDOWS: dict[OverviewWindow, tuple[timedelta, BucketUnit]] = {
    OverviewWindow.HOUR: (timedelta(hours=1), BucketUnit.MINUTE),
    OverviewWindow.DAY: (timedelta(hours=24), BucketUnit.HOUR),
    OverviewWindow.WEEK: (timedelta(days=7), BucketUnit.DAY),
}

UNIT_STEPS: dict[BucketUnit, timedelta] = {
    BucketUnit.MINUTE: timedelta(minutes=1),
    BucketUnit.HOUR: timedelta(hours=1),
    BucketUnit.DAY: timedelta(days=1),
}

# Прокси с меньшим числом генераций за окно в «худших» не показываем: одна неудача из одной
# попытки даёт «0 %» и не говорит ничего о прокси.
WORST_PROXIES_LIMIT = 5
WORST_PROXIES_MIN_TOTAL = 5


def truncate_to_unit(moment: datetime, unit: BucketUnit) -> datetime:
    moment = moment.astimezone(timezone.utc)
    if unit == BucketUnit.MINUTE:
        return moment.replace(second=0, microsecond=0)
    if unit == BucketUnit.HOUR:
        return moment.replace(minute=0, second=0, microsecond=0)
    return moment.replace(hour=0, minute=0, second=0, microsecond=0)


def build_series(
    points: list[TimeBucketCount],
    keys: list[str],
    date_from: datetime,
    unit: BucketUnit,
    now: datetime,
) -> list[OverviewPoint]:
    """Непрерывный ряд от начала окна до текущего интервала: пустые интервалы — нули по всем
    `keys`, чтобы график не рвался и фронтенду не нужно достраивать ось."""
    step = UNIT_STEPS[unit]
    rows: dict[datetime, dict[str, int]] = {}
    cursor = truncate_to_unit(date_from, unit)
    last = truncate_to_unit(now, unit)
    while cursor <= last:
        rows[cursor] = {key: 0 for key in keys}
        cursor += step
    for point in points:
        row = rows.get(truncate_to_unit(point.bucket, unit))
        if row is not None and point.key in row:
            row[point.key] += point.count
    return [OverviewPoint(bucket=bucket, values=values) for bucket, values in rows.items()]


def sum_series(points: list[TimeBucketCount], key: str) -> int:
    return sum(point.count for point in points if point.key == key)


def percent(part: int, total: int) -> int:
    return round(part * 100 / total) if total else 0


def build_workers_health(
    last_seen_members: list[str], missed_members: set[str],
) -> tuple[WorkerGroupHealth, WorkerGroupHealth]:
    """`(парсеры, генераторы сессий)`: сколько воркеров шлют heartbeat вовремя и сколько пропустили."""
    counters = {
        WorkerType.PARSER: [0, 0],
        WorkerType.SESSIONS: [0, 0],
    }
    for member in last_seen_members:
        worker_type, _ = parse_member(member)
        if worker_type in counters:
            counters[worker_type][1 if member in missed_members else 0] += 1
    parser, sessions = counters[WorkerType.PARSER], counters[WorkerType.SESSIONS]
    return (
        WorkerGroupHealth(online=parser[0], missed=parser[1]),
        WorkerGroupHealth(online=sessions[0], missed=sessions[1]),
    )
