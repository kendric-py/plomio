from sqlalchemy import ColumnElement, func, literal

from core.enums import BucketUnit


def bucket_start(column: ColumnElement, unit: BucketUnit) -> ColumnElement:
    """Начало интервала `unit` (по UTC), в который попадает `column`; результат — `timestamptz`."""
    return func.date_trunc(literal(unit.value), column, literal('UTC'))
