from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import Select, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from core.enums import Marketplace
from core.repository import BaseRepository
from packages.automation.src.entities import (
    AutomationCheckLogEntity,
    AutomationEntity,
    AutomationListFilters,
    AutomationPriceChangeBucketEntity,
    AutomationPricePointEntity,
)
from packages.automation.src.models import Automation, AutomationCheckLog

# Общая основа графиков цены: успешные тики со снимком + значения предыдущего успешного тика
# (`LAG` считается по всей истории, до фильтра по периоду — иначе первый тик периода всегда
# выглядел бы "изменившимся"). `windowed` — уже только тики с `since`. `IS DISTINCT FROM` — чтобы
# NULL (цена пропала с карточки) тоже считался значением, а не "неизвестно".
_PRICE_TICKS_CTE = (
    'WITH ticks AS ('
    "    SELECT checked_at, (snapshot->>'PRICE')::bigint AS price, "
    "           (snapshot->>'DISCOUNTED_PRICE')::bigint AS discounted_price, "
    "           (snapshot->>'ORIGINAL_PRICE')::bigint AS original_price, "
    "           (snapshot->>'IN_STOCK')::boolean AS in_stock "
    '    FROM automation_check_log '
    '    WHERE automation_id = :automation_id AND succeeded AND snapshot IS NOT NULL'
    '), lagged AS ('
    '    SELECT *, '
    '           row_number() OVER w > 1 AS has_previous, '
    '           price IS DISTINCT FROM lag(price) OVER w '
    '           OR discounted_price IS DISTINCT FROM lag(discounted_price) OVER w '
    '           OR original_price IS DISTINCT FROM lag(original_price) OVER w AS price_changed '
    '    FROM ticks WINDOW w AS (ORDER BY checked_at)'
    '), windowed AS ('
    '    SELECT * FROM lagged WHERE checked_at >= :since'
    ')'
)


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

    async def find_duplicates(
        self,
        user_id: int,
        entities: list[AutomationEntity],
    ) -> set[int]:
        """Batch version of `find_duplicate` — one query for the whole batch. Returns indexes into
        `entities` that already exist for the user (same matching rule: by `article` when
        extracted, otherwise by exact `input_value`)."""

        if not entities:
            return set()

        articles = {entity.article for entity in entities if entity.article is not None}
        raw_inputs = {entity.input_value for entity in entities if entity.article is None}
        conditions = []
        if articles:
            conditions.append(self.model.article.in_(articles))
        if raw_inputs:
            conditions.append(self.model.input_value.in_(raw_inputs))

        statement = select(
            self.model.marketplace, self.model.article, self.model.input_value,
        ).where(
            self.model.user_id == user_id,
            self.model.marketplace.in_({entity.marketplace for entity in entities}),
            or_(*conditions),
        )
        rows = (await self.session.execute(statement)).all()
        existing_articles = {(row.marketplace, row.article) for row in rows}
        existing_inputs = {(row.marketplace, row.input_value) for row in rows}
        return {
            index
            for index, entity in enumerate(entities)
            if (
                (entity.marketplace, entity.article) in existing_articles
                if entity.article is not None
                else (entity.marketplace, entity.input_value) in existing_inputs
            )
        }

    async def bulk_create(self, entities: list[AutomationEntity]) -> list[AutomationEntity]:
        """One multi-row `INSERT ... RETURNING`. Rows that collide on the partial unique index
        `(user_id, marketplace, article)` (a concurrent request won the race after
        `find_duplicates`) are skipped via `ON CONFLICT DO NOTHING` instead of failing the whole
        batch — they are simply absent from the result, the caller compares by `id`. Every entity
        must come with a preset `id`."""

        if not entities:
            return []

        statement = (
            insert(self.model)
            .values([
                entity.model_dump(exclude_none=True, exclude_unset=True) for entity in entities
            ])
            .on_conflict_do_nothing(
                index_elements=['user_id', 'marketplace', 'article'],
                index_where=text('article IS NOT NULL'),
            )
            .returning(self.model)
        )
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects.all())

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
        this row lock across that cross-session INSERT would deadlock against
        `tasks.automation_id`'s FK, which needs to lock the very same automation row to validate
        its reference (see packages/automation/AGENTS.md).

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
        filters: AutomationListFilters | None = None,
    ) -> list[AutomationEntity]:
        statement = self._apply_user_filters(
            statement=select(self.model), user_id=user_id, filters=filters,
        )
        statement = statement.order_by(self.model.created_at.desc()).limit(limit).offset(offset)
        database_objects = await self.session.scalars(statement)
        return self._to_entities(database_objects=database_objects)

    async def count_by_user_id(
        self,
        user_id: int,
        filters: AutomationListFilters | None = None,
    ) -> int:
        statement = self._apply_user_filters(
            statement=select(func.count(self.model.id)), user_id=user_id, filters=filters,
        )
        return await self.session.scalar(statement)

    def _apply_user_filters(
        self,
        statement: Select,
        user_id: int,
        filters: AutomationListFilters | None,
    ) -> Select:
        """Общие фильтры списка автоматизаций пользователя — для выборки и count. Цена —
        `price_kopecks` (текущая цена без скидки), период — `created_at`."""
        statement = statement.where(self.model.user_id == user_id)
        if filters is None:
            return statement
        if filters.status is not None:
            statement = statement.where(self.model.status == filters.status)
        if filters.in_stock is not None:
            statement = statement.where(self.model.in_stock == filters.in_stock)
        if filters.price_from is not None:
            statement = statement.where(self.model.price_kopecks >= filters.price_from)
        if filters.price_to is not None:
            statement = statement.where(self.model.price_kopecks <= filters.price_to)
        if filters.date_from is not None:
            statement = statement.where(self.model.created_at >= filters.date_from)
        if filters.date_to is not None:
            statement = statement.where(self.model.created_at <= filters.date_to)
        return statement

    async def finalize_check(
        self,
        automation_id: UUID,
        last_checked_at: datetime,
        last_check_error: str | None,
        baseline_updates: dict[str, int | bool],
        current_values: dict[str, int | str | None] | None = None,
    ) -> None:
        """Clears `pending_task_id` and sets `last_check_error` explicitly to `None` on success —
        both need a raw UPDATE rather than `BaseRepository.update`, which drops `None` fields
        (`exclude_none=True`) and so can't null out a previously-set value. `baseline_updates` may
        also carry `in_stock` (a bool, not a baseline_*_kopecks column) — same "only include what
        actually changed" contract, just not restricted to price columns despite the name.
        `current_values` — актуальные `name`/`*price_kopecks` по успешной проверке; пишутся как
        есть, включая `None` (цена пропала с карточки — это и есть текущее состояние)."""

        statement = (
            update(self.model)
            .where(self.model.id == automation_id)
            .values(
                pending_task_id=None,
                last_checked_at=last_checked_at,
                last_check_error=last_check_error,
                **baseline_updates,
                **(current_values or {}),
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

    async def get_price_dynamics(
        self,
        automation_id: UUID,
        start: datetime,
        until: datetime,
        step_seconds: int,
    ) -> list[AutomationPricePointEntity]:
        """Регулярный ряд для графика динамики: на каждую точку сетки `start..until` с шагом
        `step_seconds` — состояние карточки по последнему успешному тику на конец её интервала
        (цена "держится", пока не изменится, поэтому пропусков нет, даже если тиков в интервале не
        было). Тик ищется по всей истории, а не только внутри периода — так первые точки несут
        цену, действовавшую до начала периода. Точки до самого первого тика автоматизации не
        возвращаются. `at` — конец интервала (не позже `until`): значение в точке верно именно на
        этот момент."""

        statement = text(
            'WITH ticks AS ('
            "    SELECT checked_at, (snapshot->>'PRICE')::bigint AS price, "
            "           (snapshot->>'DISCOUNTED_PRICE')::bigint AS discounted_price, "
            "           (snapshot->>'ORIGINAL_PRICE')::bigint AS original_price, "
            "           (snapshot->>'IN_STOCK')::boolean AS in_stock "
            '    FROM automation_check_log '
            '    WHERE automation_id = :automation_id AND succeeded AND snapshot IS NOT NULL'
            '), grid AS ('
            "    SELECT least(g + cast(:step AS double precision) * interval '1 second', "
            '                 cast(:until AS timestamptz)) AS at '
            '    FROM generate_series('
            '        cast(:start AS timestamptz), cast(:until AS timestamptz), '
            "        cast(:step AS double precision) * interval '1 second'"
            '    ) AS g'
            ') '
            'SELECT grid.at, t.price, t.discounted_price, t.original_price, t.in_stock '
            'FROM grid JOIN LATERAL ('
            '    SELECT * FROM ticks WHERE checked_at <= grid.at '
            '    ORDER BY checked_at DESC LIMIT 1'
            ') t ON true '
            'ORDER BY grid.at ASC',
        )
        result = await self.session.execute(
            statement,
            {
                'automation_id': automation_id,
                'start': start,
                'until': until,
                'step': step_seconds,
            },
        )
        return [
            AutomationPricePointEntity(
                at=row['at'],
                price_kopecks=row['price'],
                discounted_price_kopecks=row['discounted_price'],
                original_price_kopecks=row['original_price'],
                in_stock=row['in_stock'],
            )
            for row in result.mappings()
        ]

    async def get_price_change_frequency(
        self,
        automation_id: UUID,
        since: datetime,
        until: datetime,
        step_seconds: int,
    ) -> list[AutomationPriceChangeBucketEntity]:
        """Число тиков с изменением цены по корзинам `since..until` шириной `step_seconds`
        (корзина выровнена по шагу от эпохи, UTC). Корзины без изменений не возвращаются
        (достраивает сервис). Самый первый тик автоматизации изменением не считается — не с чем
        сравнивать."""

        statement = text(
            f'{_PRICE_TICKS_CTE} '
            'SELECT to_timestamp('
            '    floor(extract(epoch FROM checked_at) / cast(:step AS double precision)) '
            '    * cast(:step AS double precision)'
            ') AS bucket_start, count(*) AS changes_count '
            'FROM windowed '
            'WHERE has_previous AND price_changed AND checked_at <= cast(:until AS timestamptz) '
            'GROUP BY 1 ORDER BY 1 ASC',
        )
        result = await self.session.execute(
            statement,
            {
                'automation_id': automation_id,
                'since': since,
                'until': until,
                'step': step_seconds,
            },
        )
        return [
            AutomationPriceChangeBucketEntity(
                bucket_start=row['bucket_start'].astimezone(timezone.utc),
                changes_count=row['changes_count'],
            )
            for row in result.mappings()
        ]

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
