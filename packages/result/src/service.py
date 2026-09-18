from uuid import UUID

from pydantic import BaseModel

from core.enums import Marketplace
from core.transaction_manager import AsyncTransactionManager
from packages.result.src.entities import ResultItemEntity
from packages.task.src.enums import ParseType


class ResultService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def record_results(
        self,
        task_item_id: UUID,
        marketplace: Marketplace,
        parse_type: ParseType,
        payloads: list[BaseModel],
    ) -> None:
        async with self.transaction_manager(use_result_repository=True) as transaction:
            for payload in payloads:
                await transaction.result_repository.create(
                    entity=ResultItemEntity(
                        task_item_id=task_item_id,
                        marketplace=marketplace,
                        parse_type=parse_type,
                        payload=payload.model_dump(mode='json'),
                    ),
                )
            await self.transaction_manager.commit()

    async def get_results_for_task(
        self,
        task_id: UUID,
        limit: int,
        offset: int,
    ) -> tuple[list[ResultItemEntity], int]:
        async with self.transaction_manager(use_result_repository=True) as transaction:
            items = await transaction.result_repository.get_by_task_id(
                task_id=task_id, limit=limit, offset=offset,
            )
            total = await transaction.result_repository.count_by_task_id(task_id=task_id)
        return items, total
