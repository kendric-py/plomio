from datetime import datetime

from pydantic import BaseModel, Field


class TimeBucketCount(BaseModel):
    """Одна точка временного ряда: сколько событий `key` попало в интервал, начинающийся в
    `bucket` (UTC). Интервалы без событий репозитории не отдают — нули достраивает вызывающий."""

    bucket: datetime = Field(description='Начало интервала (UTC)')
    key: str = Field(description='Ряд: статус, итог или другая категория события')
    count: int = Field(description='Число событий (или сумма, например кредитов) за интервал')
