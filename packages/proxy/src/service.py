from datetime import datetime, timedelta, timezone
from typing import Any

from core.enums import Marketplace
from core.transaction_manager import AsyncTransactionManager
from core.exceptions import ObjectNotFoundError
from packages.proxy.src.entities import (
    OutcomeCount,
    OutcomeDayCount,
    ProxyEntity,
    SessionGenerationEntity,
)
from packages.proxy.src.enums import ProxyType
from packages.sessions.src.enums import SessionGenerationOutcome
from packages.sessions.src.errors import SESSION_GENERATIONS_KEEP


class ProxyService:
    def __init__(self, transaction_manager: AsyncTransactionManager):
        self.transaction_manager = transaction_manager

    async def list_page(
        self, limit: int, offset: int, is_active: bool | None = None,
    ) -> tuple[list[ProxyEntity], int]:
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            return await transaction.proxy_repository.list_page(
                limit=limit, offset=offset, is_active=is_active,
            )

    async def create_proxy(
        self,
        proxy_type: ProxyType,
        host: str,
        port: int,
        username: str | None = None,
        password: str | None = None,
        note: str | None = None,
        is_active: bool = True,
    ) -> ProxyEntity:
        """`DuplicatedObjectError`, если прокси с таким (тип, хост, порт, логин) уже есть."""
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            created_proxy = await transaction.proxy_repository.create(
                entity=ProxyEntity(
                    proxy_type=proxy_type,
                    host=host,
                    port=port,
                    username=username,
                    password=password,
                    note=note,
                    is_active=is_active,
                ),
            )
            await self.transaction_manager.commit()
        return created_proxy

    async def update_proxy(self, proxy_id: int, values: dict[str, Any]) -> ProxyEntity:
        """`values` — только реально переданные поля (`None` допустим: сбрасывает логин/пароль/
        заметку). `ObjectNotFoundError` / `DuplicatedObjectError` пробрасываются вызывающему."""
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            updated_proxy = await transaction.proxy_repository.update_fields(
                proxy_id=proxy_id, values=values,
            )
            await self.transaction_manager.commit()
        return updated_proxy

    async def delete_proxy(self, proxy_id: int) -> None:
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            await transaction.proxy_repository.delete(entity_id=proxy_id)
            await self.transaction_manager.commit()

    async def issue_random(self, proxy_type: ProxyType | None = None) -> ProxyEntity | None:
        """Случайный активный прокси (опционально заданного типа); `None`, если таких нет."""
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            return await transaction.proxy_repository.get_random_active(proxy_type=proxy_type)

    async def get_proxy(self, proxy_id: int) -> ProxyEntity:
        """`ObjectNotFoundError`, если прокси нет."""
        async with self.transaction_manager(use_proxy_repository=True) as transaction:
            return await transaction.proxy_repository.get_by_id(entity_id=proxy_id)

    async def record_generation(
        self,
        marketplace: Marketplace,
        outcome: SessionGenerationOutcome,
        proxy_id: int | None = None,
        traceback: str | None = None,
    ) -> None:
        """Пишет итог попытки генерации сессии (вызывает `worker_sessions` через api). Если прокси
        уже удалён, пока воркер им пользовался, генерация всё равно записывается — без прокси."""
        async with self.transaction_manager(
            use_proxy_repository=True, use_session_generation_repository=True,
        ) as transaction:
            if proxy_id is not None:
                try:
                    await transaction.proxy_repository.get_by_id(entity_id=proxy_id)
                except ObjectNotFoundError:
                    proxy_id = None
            await transaction.session_generation_repository.create(
                entity=SessionGenerationEntity(
                    proxy_id=proxy_id,
                    marketplace=marketplace,
                    outcome=outcome,
                    traceback=traceback,
                ),
            )
            await self.transaction_manager.commit()

    async def get_recent_generations(
        self, marketplace: Marketplace,
    ) -> list[SessionGenerationOutcome]:
        """Итоги последних `SESSION_GENERATIONS_KEEP` (50) генераций маркетплейса, новые первыми."""
        async with self.transaction_manager(use_session_generation_repository=True) as transaction:
            return await transaction.session_generation_repository.recent_outcomes(
                marketplace=marketplace, limit=SESSION_GENERATIONS_KEEP,
            )

    async def get_generation_stats(
        self,
        proxy_id: int,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        outcomes: list[SessionGenerationOutcome] | None = None,
        include_antibot: bool = False,
    ) -> tuple[list[OutcomeCount], list[OutcomeDayCount]]:
        """Генерации через прокси: сводка по итогам (успех и типы ошибок) и разбивка по дням.
        Антибот-ошибки не зависят от прокси, поэтому по умолчанию не учитываются
        (`include_antibot`) — ни в числителе, ни в знаменателе долей. `ObjectNotFoundError`, если
        прокси нет."""
        async with self.transaction_manager(
            use_proxy_repository=True, use_session_generation_repository=True,
        ) as transaction:
            await transaction.proxy_repository.get_by_id(entity_id=proxy_id)
            repository = transaction.session_generation_repository
            by_outcome = await repository.count_by_outcome(
                proxy_id=proxy_id, date_from=date_from, date_to=date_to,
                outcomes=outcomes, include_antibot=include_antibot,
            )
            by_day = await repository.count_by_day(
                proxy_id=proxy_id, date_from=date_from, date_to=date_to,
                outcomes=outcomes, include_antibot=include_antibot,
            )
        return by_outcome, by_day

    async def get_antibot_by_day(
        self,
        marketplace: Marketplace | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
    ) -> list[OutcomeDayCount]:
        """Антибот-ошибки по дням (по всем прокси) — индикатор смены скриптов антибота."""
        async with self.transaction_manager(use_session_generation_repository=True) as transaction:
            return await transaction.session_generation_repository.count_by_day(
                marketplace=marketplace, date_from=date_from, date_to=date_to,
                outcomes=[SessionGenerationOutcome.ANTIBOT_INIT], include_antibot=True,
            )

    async def sweep_generation_retention(self, retention_days: int) -> int:
        """Удаляет генерации старше `retention_days`; возвращает число удалённых строк."""
        threshold = datetime.now(timezone.utc) - timedelta(days=retention_days)
        async with self.transaction_manager(use_session_generation_repository=True) as transaction:
            deleted_count = await transaction.session_generation_repository.delete_older_than(
                threshold=threshold,
            )
            await self.transaction_manager.commit()
        return deleted_count
