# packages/audit_log

Доменная область audit-логирования действий пользователей SMPCrawl. Единая таблица `audit_logs`
для всех доменов — не привязана к `User` или к какому-то одному сценарию.

## Модель `AuditLog`

- `id` — первичный ключ.
- `action` — `AuditAction` (enum), источник события, например `AuditAction.AUTH_REGISTER_USER`.
  **Единый реестр** всех действий, которые пишутся в audit log, живёт в `enums.py` — новое действие
  сначала добавляется туда, потом используется в сервисе. Произвольные строки не допускаются
  (колонка типизирована native Postgres enum, как `role` в `packages/user`).
- `action_type` — `AuditActionType` (`CREATE`, `UPDATE`, `DELETE`, `AUTH`). `AUTH` — для событий,
  которые не являются изменением полей сущности (логин), в отличие от `CREATE`/`UPDATE`/`DELETE`.
- `status` — `AuditStatus` (`SUCCESS`, `FAILURE`). Логируются и успешные, и неуспешные попытки
  (неверный пароль, дубликат email) — важно для security-аудита.
- `details` — `JSONB`, единый конверт `{"fields": {field: {"before": ..., "after": ...}}}` для всех
  `action_type`. Для `CREATE` — `before=null`, для `DELETE` — `after=null`, для `UPDATE` — оба
  заполнены, для `AUTH` — `fields={}`.
- `error_reason` — короткий код причины неуспеха (`'invalid_credentials'`, `'user_already_exists'`),
  `NULL` при успехе.
- `target_type` — имя сущности, над которой произведено действие (`'User'`).
- `target_id` — id этой сущности; `NULL`, если действие не удалось до создания/определения сущности.
- `user_id` — FK `users.id`, `ondelete='SET NULL'`, кто выполнил действие; `NULL`, если актор не
  определён (например, регистрация до появления пользователя не логируется как безакторная — по
  соглашению `user_id = target_id`, self-action; при провале — `NULL`, актор не определён).
- `ip_address` — IP-адрес запроса, `String(45)` (совместимо с IPv6).
- `created_at` — время создания записи.

Таблица append-only: `update`/`delete` у audit-записей не используются.

## `utils.py` — единая система построения `details.fields`

Глобальный по имени поля (не по домену) deny-list чувствительных полей — `SENSITIVE_FIELD_MARKERS`
(`password`, `token`, `secret`, `hashed_`) — гарантирует, что `hashed_password` и подобные поля
никогда не попадут в `details`, независимо от домена, который логирует событие.

- `build_create_fields(entity)` — снапшот всех полей новой сущности.
- `build_delete_fields(entity)` — снапшот сущности перед удалением.
- `build_update_fields(before, patch)` — диффует `patch` (сущность с изменёнными полями, как её
  передают в `BaseRepository.update`) относительно `before` (сущность до изменения) и возвращает
  только реально изменившиеся поля. Это и есть автоматическое построение `details` при `UPDATE` —
  вызывающему сервису не нужно вручную перечислять, что изменилось.

## Репозиторий и запись audit-события

- **`repository.py`** — `AuditLogRepository(BaseRepository[AuditLog, AuditLogEntity])`, используется
  только через `create()` (репозиторий не переопределяет `update`/`delete`).
- Подключается в [`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py)
  через `use_audit_log_repository=True`, как `UserRepository`.

**Важно:** audit-запись пишется в собственной, независимой транзакции, а не в той же, что бизнес-
логика (см. [`packages/auth`](../auth/AGENTS.md) — `AuthService._record_audit_event`). Причины:
- При исключении в бизнес-транзакции `AsyncTransactionManager` откатывает и закрывает сессию без
  коммита — если бы audit писался в той же транзакции, запись о неудачной попытке пропадала бы
  вместе с остальным.
- Сбой самого audit-логирования не должен блокировать/откатывать успешное действие пользователя.

## Middleware

Сейчас не реализован. Изначально планировалось логировать регистрацию/логин через middleware, но
`POST /auth/register` отвечает только `access_token` (без данных о созданном пользователе), а сама
сущность `User` создаётся глубоко внутри `AuthService` — middleware не имеет доступа к созданной
сущности. Поэтому регистрация и логин логируются напрямую в `AuthService`. Middleware-механизм стоит
добавлять отдельно, когда появится конкретный кейс, где он действительно необходим (например,
событие, полностью описываемое самим HTTP-запросом/ответом, без обращения к доменной сущности).
