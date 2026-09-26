from datetime import datetime
from uuid import UUID

from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from core.enums import Marketplace
from core.repository import BaseRepository
from packages.automation.src.entities import AutomationCheckLogEntity, AutomationEntity
from packages.automation.src.models import Automation, AutomationCheckLog


class AutomationRepository(BaseRepository[Automation, AutomationEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(model=Automation, entity_object=AutomationEntity, session=session)

    async def find_duplicate(
        self,
        user_id: int,
        marketplace: Marketplace,
        article: str | None,
        input_value: str,
    ) -> AutomationEntity | None:
        """Matches by `article` when it was extracted (any status — a PAUSED automation on the
        same product still counts); falls back to an exact `input_value` match when the article
        couldn't be extracted for the new one, since there's then nothing else reliable to
        compare on."""

        statement = select(self.model).where(
            self.model.user_id == user_id,
            self.model.marketplace == marketplace,
        )
        if article is not None:
            statement = statement.where(self.model.article == article)
        else:
            statement = statement.where(self.model.input_value == input_value)
        statement = statement.limit(1)

        database_object = await self.session.scalar(statement)
        return self._to_entity(database_object=database_object) if database_object else None

    async def claim_due_for_dispatch(
        self,
        now: datetime,
        limit: int,
        out_of_stock_check_frequency_minutes: int,
    ) -> list[AutomationEntity]:
        """Atomically claims due automations by advancing `next_check_at` in the same statement
        that locks them (`FOR UPDATE SKIP LOCKED`) — this is the whole claim, `pending_task_id` is
        set later by `set_pending_task`, in a separate transaction, once the check `Task` actually
        exists. The caller MUST commit right after this call, before creating any `Task` — holding
        this row lock across that cross-session INSERT would deadlock against `tasks.automation_id`'s
        FK, which needs to lock the very same automation row to validate its reference (see
        packages/automation/AGENTS.md).

        An automation whose last check found the product out of stock (`in_stock = false`) is
        rescheduled after `out_of_stock_check_frequency_minutes` instead of its own
        `check_frequency_minutes` — that cadence is config-only, not user-configurable, since it's
        about detecting restock, not about the user's chosen price-check interval."""

        claim_statement = text(
            "UPDATE automations "
            "SET next_check_at = :now + ("
            "    CASE WHEN in_stock = false THEN :out_of_stock_check_frequency_minutes "
            "         ELSE check_frequency_minutes END * interval '1 minute'"
            ") "
            "WHERE id IN ("
            "    SELECT id FROM automations "
            "    WHERE status = 'ACTIVE' AND next_check_at <= :now AND pending_task_id IS NULL "
            "    ORDER BY next_check_at ASC "
            "    LIMIT :limit "
            "    FOR UPDATE SKIP LOCKED"
            ") "
            "RETURNING id",
        )
        result = await self.session.execute(
            claim_statement,
            {
                'now': now,
                'limit': limit,
                'out_of_stock_check_frequency_minutes': out_of_stock_check_frequency_minutes,
            },
        )
        claimed_ids = [row[0] for row in result.fetchall()]
        if not claimed_ids:
            return []

        select_statement = select(self.model).where(self.model.id.in_(claimed_ids))
        database_objects = await self.session.scalars(select_statement)
        return self._to_entities(database_objects=database_objects)

    async def set_pending_task(self, automation_id: UUID, task_id: UUID) -> None:
        statement = (
            update(self.model)
            .where(self.model.id == automation_id)
            .values(pending_task_id=task_id)
        )
        await self.session.execute(statement)

    async def get_awaiting_result(self, limit: int) -> list[AutomationEntity]:
        statement = (
            select(self.model)
            .where(self.model.pending_task_id.is_not(None))
            .order_by(self.model.last_checked_at.asc().nulls_first())
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def get_by_user_id(
        self,
        user_id: int,
        limit: int,
        offset: int,
    ) -> list[AutomationEntity]:
        statement = (
            select(self.model)
            .where(self.model.user_id == user_id)
            .order_by(self.model.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_user_id(self, user_id: int) -> int:
        statement = select(func.count(self.model.id)).where(self.model.user_id == user_id)
        return await self.session.scalar(statement)

    async def finalize_check(
        self,
        automation_id: UUID,
        last_checked_at: datetime,
        last_check_error: str | None,
        baseline_updates: dict[str, int | bool],
    ) -> None:
        """Clears `pending_task_id` and sets `last_check_error` explicitly to `None` on success —
        both need a raw UPDATE rather than `BaseRepository.update`, which drops `None` fields
        (`exclude_none=True`) and so can't null out a previously-set value. `baseline_updates` may
        also carry `in_stock` (a bool, not a baseline_*_kopecks column) — same "only include what
        actually changed" contract, just not restricted to price columns despite the name."""

        statement = (
            update(self.model)
            .where(self.model.id == automation_id)
            .values(
                pending_task_id=None,
                last_checked_at=last_checked_at,
                last_check_error=last_check_error,
                **baseline_updates,
            )
        )
        await self.session.execute(statement)


class AutomationCheckLogRepository(BaseRepository[AutomationCheckLog, AutomationCheckLogEntity]):
    def __init__(self, session: AsyncSession):
        super().__init__(
            model=AutomationCheckLog,
            entity_object=AutomationCheckLogEntity,
            session=session,
        )

    async def get_by_automation_id(
        self,
        automation_id: UUID,
        limit: int,
        offset: int,
    ) -> list[AutomationCheckLogEntity]:
        statement = (
            select(self.model)
            .where(self.model.automation_id == automation_id)
            .order_by(self.model.checked_at.desc())
            .limit(limit)
            .offset(offset)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_automation_id(self, automation_id: UUID) -> int:
        statement = select(func.count(self.model.id)).where(
            self.model.automation_id == automation_id,
        )
        return await self.session.scalar(statement)

    async def get_latest_succeeded(self, automation_id: UUID) -> AutomationCheckLogEntity | None:
        """Последний успешный тик этой автоматизации — источник snapshot, с которым сравнивается
        текущий тик для вычисления has_changes (см. AutomationService._finalize_check)."""

        statement = (
            select(self.model)
            .where(self.model.automation_id == automation_id, self.model.succeeded.is_(True))
            .order_by(self.model.checked_at.desc())
            .limit(1)
        )
        database_object = await self.session.scalar(statement)
        return self._to_entity(database_object=database_object) if database_object else None

    async def get_recent_by_automation_ids(
        self,
        automation_ids: list[UUID],
        limit_per_automation: int,
    ) -> dict[UUID, list[AutomationCheckLogEntity]]:
        """Batched "last N ticks per automation" for a whole page of automations in one query
        (`ROW_NUMBER() OVER (PARTITION BY automation_id ORDER BY checked_at DESC)`), instead of one
        `get_by_automation_id` round-trip per automation — avoids N+1 for
        `AutomationService.list_automations_with_recent_checks`."""

        if not automation_ids:
            return {}

        ranked = (
            select(
                self.model,
                func.row_number()
                .over(
                    partition_by=self.model.automation_id,
                    order_by=self.model.checked_at.desc(),
                )
                .label('rn'),
            )
            .where(self.model.automation_id.in_(automation_ids))
            .subquery()
        )
        ranked_model = aliased(self.model, ranked)
        statement = (
            select(ranked_model)
            .where(ranked.c.rn <= limit_per_automation)
            .order_by(ranked.c.automation_id, ranked.c.rn)
        )
        database_objects = await self.session.scalars(statement)

        grouped: dict[UUID, list[AutomationCheckLogEntity]] = {
            automation_id: [] for automation_id in automation_ids
        }
        for entity in self._to_entities(database_objects=database_objects):
            grouped[entity.automation_id].append(entity)
        return grouped

    async def delete_expired(self) -> int:
        """Deletes every check-log row older than its own automation's `history_retention_days` —
        one statement across all automations (join on the parent table), rather than looping over
        automations in Python and issuing one DELETE per row — to avoid N+1 round-trips."""

        statement = text(
            "DELETE FROM automation_check_log "
            "USING automations "
            "WHERE automation_check_log.automation_id = automations.id "
            "AND automation_check_log.checked_at < now() - "
            "(automations.history_retention_days * interval '1 day')",
        )
        result = await self.session.execute(statement)
        return result.rowcount
