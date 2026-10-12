from datetime import datetime

from core.entities import TimeBucketCount
from core.enums import BucketUnit
from core.transaction_manager import AsyncTransactionManager
from packages.direct.src.entities import (
    DirectRequestFilters,
    DirectRequestRecordEntity,
    DirectSummaryEntity,
)

# Длина `input_value` и `error_detail` в истории: полный текст запроса не нужен, а ссылка или
# поисковая фраза от клиента может быть сколь угодно длинной.
INPUT_VALUE_LIMIT = 500
ERROR_DETAIL_LIMIT = 300


class DirectService:
    """История direct-запросов. Сам обмен с воркером остаётся в `apps/api` (`DirectBus`) — этот
    сервис только пишет и читает журнал `direct_requests`."""

    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def record_request(self, record: DirectRequestRecordEntity) -> None:
        """Пишет одну запись истории. Вызывающий обязан не давать сбою записи ломать ответ клиенту."""
        record = record.model_copy(update={
            'input_value': (record.input_value or '')[:INPUT_VALUE_LIMIT],
            'error_detail': record.error_detail[:ERROR_DETAIL_LIMIT] if record.error_detail else None,
        })
        async with self.transaction_manager(use_direct_request_repository=True) as transaction:
            await transaction.direct_request_repository.create(entity=record)
            await self.transaction_manager.commit()

    async def list_requests(
        self, filters: DirectRequestFilters, limit: int, offset: int,
    ) -> tuple[list[DirectRequestRecordEntity], int]:
        async with self.transaction_manager(use_direct_request_repository=True) as transaction:
            return await transaction.direct_request_repository.list_page(
                filters=filters, limit=limit, offset=offset,
            )

    async def get_summary(self, filters: DirectRequestFilters) -> DirectSummaryEntity:
        async with self.transaction_manager(use_direct_request_repository=True) as transaction:
            return await transaction.direct_request_repository.get_summary(filters=filters)

    async def get_series(self, date_from: datetime, unit: BucketUnit) -> list[TimeBucketCount]:
        """Запросы по интервалам времени; ключ — итог."""
        async with self.transaction_manager(use_direct_request_repository=True) as transaction:
            return await transaction.direct_request_repository.count_by_bucket(
                date_from=date_from, unit=unit,
            )
