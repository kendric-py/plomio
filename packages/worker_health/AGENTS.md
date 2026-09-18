# packages/worker_health

Доменная область мониторинга доступности воркеров (`apps/worker_parser`, `apps/worker_sessions`).
Не хранит текущее состояние воркеров (это в Redis, эфемерно) — только append-only лог переходов
`alive → missed` / `missed → alive`, который пишется реже, чем приходят сами heartbeat'ы.

## Почему не пишем каждый heartbeat в Postgres

`LivenessReporter` в воркерах шлёт heartbeat раз в `LIVENESS_INTERVAL_SECONDS` (по умолчанию 15с) —
писать в Postgres на каждый такой сигнал не имеет смысла: это просто "воркер жив", не событие.
Последний heartbeat каждого воркера живёт в Redis (`packages/worker_health/src/redis_store.py`,
ZSET `worker_health:heartbeats`, `WorkerHeartbeatStore.touch()`), а в БД попадает только сам факт
пропуска/восстановления сигнала — обнаруживает его периодическая проверка в `apps/api`
(`apps/api/src/jobs/worker_heartbeat_sweep.py`, запускается через `packages/cron`).

## Модель `WorkerHeartbeatLog`

- `worker_type` — `WorkerType` (`PARSER`, `SESSIONS`).
- `worker_name` — имя инстанса воркера (то же значение, что воркер шлёт в `LIVENESS_WORKER_NAME`).
- `event_type` — `WorkerHeartbeatEventType` (`MISSED`, `RECOVERED`).
- `last_seen_at` — последний известный heartbeat перед этим событием.
- `detected_at` — когда переход зафиксирован проверкой (не когда воркер реально пропал).
- `details` — `JSONB`, произвольные детали (например, `gap_seconds`).

Таблица append-only, как `audit_logs` — `update`/`delete` не используются.

## Дедупликация переходов

Наивная проверка "воркер сейчас просрочен → пишем лог" на каждом тике планировщика написала бы
одну и ту же запись многократно, пока воркер остаётся недоступным. `WorkerHeartbeatStore` решает
это атомарными Redis-операциями: `try_claim_missed`/`try_claim_recovered` (`SADD`/`SREM` над
`worker_health:missed`) возвращают `True` только тому вызову, который реально поменял состояние
флага в Redis — остальные тики (и другие реплики `apps/api`, если их несколько) видят `False` и
не пишут повторную запись. Это же снимает необходимость гонять проверку строго в одном экземпляре
процесса — см. `packages/cron/AGENTS.md`.

## Репозиторий и сервис

`WorkerHeartbeatLogRepository(BaseRepository[WorkerHeartbeatLog, WorkerHeartbeatLogEntity])` — как
`AuditLogRepository`, только `create()`. `WorkerHealthService` — `record_missed`/`record_recovered`,
каждый в своей независимой транзакции. Подключается в
[`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py) через
`use_worker_heartbeat_log_repository=True`.

## Текущий статус воркеров: `GET /api/worker-health/workers`

Читает состояние прямо из Redis (без БД): для каждого воркера, у которого есть heartbeat в ZSET,
отдаёт `worker_type`, `worker_name`, `status`, `last_seen_at`, `gap_seconds` и `is_missed`.
`is_missed` берётся из того же флага (`worker_health:missed`), который использует sweep для
решения "писать ли лог" — статус в ручке и то, что реально попадёт в `worker_heartbeat_logs`,
никогда не расходятся.

`status` — последний статус, присланный воркером в теле heartbeat (`READY`/`WORKING`/...),
хранится как свободная строка в отдельном Redis HASH (`worker_health:status`, `WorkerHeartbeatStore
.touch()`), **не валидируется** против `WorkerParserStatus`/`WorkerSessionsStatus` — эти enum'ы
живут в `apps/worker_parser`/`apps/worker_sessions` и не должны быть видны из `packages` (apps не
должны знать друг про друга через shared-код). `null` в ответе — если heartbeat был получен до
появления этого поля (запись есть в ZSET last-seen, но ещё нет в HASH статусов).

## Что не входит в эту итерацию

- История missed/recovered (чтение `worker_heartbeat_logs`) — только текущий снепшот из Redis.
- Аутентификация HTTP-ручек приёма heartbeat (`apps/api/src/routers/worker_health`) —
  `packages/api_keys` ещё не реализован, ручки открытые.
