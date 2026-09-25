# packages/notifications

Универсальная, провайдер-агностичная доменная область уведомлений. Не знает про `packages/task`/
`packages/automation` вообще — не только не зависит от них в коде, но и не хранит ссылок на их
объекты (никакого `reference_type`/`reference_id`, в отличие от `packages/billing`): настройки
пользователя полностью **глобальны**, не привязаны к конкретной автоматизации или задаче.

## Модель — каталог событий, по образцу `packages/billing`

Ключевое требование, симметричное `packages/billing` (см. [`packages/billing/AGENTS.md`](../billing/AGENTS.md),
"Конструктор"): новый тип события подключается без миграции схемы — новой строкой в каталоге плюс
одним вызовом `NotificationService.notify(...)` в коде вызывающего домена.

- **`NotificationEvent`** (`notification_events`) — каталог: `event_code` (человекочитаемый код,
  **primary key** — `"automation.change_detected"`, `"task.completed"`, `"task.failed"`),
  `description` (для UI), `is_active` (неактивное событие никогда не создаёт доставок — способ
  временно выключить событие без удаления строки/ссылок на него из `notification_deliveries`),
  `available_fields: JSONB list[str] | None` — имена полей, по которым можно фильтровать подписку
  на это событие (для `automation.change_detected` — все значения `TrackedField` из
  `packages/automation`, для `task.*` — `NULL`, у задач нет понятия "поле"). Домен **не
  интерпретирует** эти строки и не знает про `TrackedField` — просто хранит и отдаёт список,
  сравнение делает вызывающий код через `changed_fields` в `notify()` (см. ниже).
- **`NotificationSetting`** (`notification_settings`) — **одна строка на пользователя** (PK =
  `user_id`, тот же приём, что `CreditWallet`), `preferences: JSONB` — карта `{event_code:
  {"channels": [...], "fields": [...] | null}}`. Отсутствие ключа для `event_code` или пустой
  список каналов = уведомления по этому событию выключены — **безопасный дефолт**: новый
  пользователь ничего не получает, пока явно не включит `PUT /api/notifications/preferences`.
  `fields` (подмножество `available_fields` этого события) — необязательный фильтр: `null`/пусто =
  уведомлять по любому срабатыванию события, непустой список = только если оно затронуло хотя бы
  одно из перечисленных полей.
- **`NotificationDelivery`** (`notification_deliveries`) — append-only журнал: "это уведомление
  нужно отправить", тот же принцип, что `automation_check_log`/`credit_transactions`. `payload`
  (JSONB) — произвольные данные события для будущего отправителя (у `automation.*` — `changes`ы,
  у `task.*` — `task_id`/`error_reason`). `status` — `PENDING`/`SENT`/`FAILED`; в этой итерации
  создаются только `PENDING`, `SENT`/`FAILED` никогда не проставляются этим доменом.

## `NotificationService` — один generic-метод, все домены зовут только его

- **`notify(user_id, event_code, payload, changed_fields=None)`** — единственная точка интеграции.
  No-op (возвращает `[]`, ничего не пишет), если `event_code` не в каталоге/неактивен, или
  пользователь не включил ни одного канала для этого события, или у настройки задан фильтр `fields`
  и он не пересекается с `changed_fields` — вызывающий домен никогда не должен падать из-за
  отсутствующей/выключенной/отфильтрованной настройки, тот же контракт, что у
  `BillingService.charge`. Иначе создаёт по одной строке `NotificationDelivery` на каждый
  включённый канал. `changed_fields` — какие поля затронуло конкретное срабатывание (например,
  `[c['field'] for c in changes]` из `AutomationCheckLog`); вызывающий домен передаёт `None`, если
  у события нет понятия "поле" (`task.*`).
- **`get_preferences`/`update_preferences`** — чтение/полная замена карты `preferences` текущего
  пользователя; `update_preferences` проверяет каждый `event_code` карты против каталога
  (`is_active`, иначе `UnknownNotificationEventError`) и, если задан `fields`, что он —
  подмножество `available_fields` этого события (иначе `InvalidNotificationFieldFilterError`).
- **`list_deliveries`** — постраничный журнал доставок пользователя.
- **`list_events`** — активные `event_code` из каталога, чтобы фронтенд строил форму настройки без
  хардкода списка событий на клиенте.

Никакого админского CRUD над каталогом в этой итерации (в отличие от `packages/billing`, где
`BillingAction`/`PricingMultiplierRule` — центральные конфигурационные таблицы, которыми управляет
администратор): `notification_events` заполняется data-миграцией по мере появления вызывающих
доменов, `NotificationSetting` целиком принадлежит пользователю.

## Кто сейчас вызывает `notify`

- **`packages/automation`** (`AutomationService._finalize_check`) — после записи тика в
  `automation_check_log`, один вызов при `has_changes or threshold_breached`:
  `event_code='automation.change_detected'`, `payload={'automation_id': ..., 'changes': [...],
  'has_changes': ..., 'threshold_breached': ...}`, `changed_fields=[c['field'] for c in changes]`.
  Один `event_code` на оба случая — `threshold_breached` всегда подразумевает `has_changes`
  (поле, пробившее порог, всё равно попадает в `changes`), различать их отдельными событиями
  избыточно; получатель уведомления сам смотрит на `payload.threshold_breached`, если ему это
  важно. Фильтр по полям (`preferences[...].fields`) даёт то же самое различение на уровне
  подписки — например, подписаться только на `PRICE`/`DISCOUNTED_PRICE`. См.
  [`packages/automation/AGENTS.md`](../automation/AGENTS.md).
- **`packages/task`** (`TaskService.complete_item`) — при переходе задачи в терминальный статус:
  `event_code='task.completed'`/`'task.failed'`, `payload={'task_id': ..., 'error_reason': ...}`.
  **Пропускается**, если `Task.automation_id is not None` — это внутренняя проверочная задача
  автоматизации, её завершение уже обрабатывается событиями `automation.*` для того же тика,
  повторное `task.*`-уведомление было бы дублем. См. [`packages/task/AGENTS.md`](../task/AGENTS.md).

Оба вызова — вне открытого `async with self.transaction_manager(...)`-блока вызывающего домена
(после коммита его собственной транзакции), тот же принцип "композиции сервисов", что описан в
[`packages/automation/AGENTS.md`](../automation/AGENTS.md#композиция-сервисов-и-транзакции):
`NotificationService` резолвится DI-контейнером как отдельный `providers.Factory`, со своим
`AsyncTransactionManager`/сессией.

## Интеграция

`NotificationEventRepository`/`NotificationSettingRepository`/`NotificationDeliveryRepository`
подключаются в [`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py)
через `use_notification_event_repository=True`/`use_notification_setting_repository=True`/
`use_notification_delivery_repository=True`.

## REST

`apps/api/src/routers/notifications/` (`/api/notifications`, все owner-only,
`Depends(get_current_user)`): `GET /events` (включает `available_fields`, чтобы фронт строил
фильтр по полям без хардкода), `GET`/`PUT /preferences` (карта `{event_code: {channels, fields}}`),
`GET /deliveries` (read-only — доставки создаются только доменом, не пользователем).

## Не входит в эту итерацию

- Реальная отправка уведомлений (HTTP к Telegram Bot API и т.п.) — только фиксация факта в БД
  (`NotificationDelivery.status = PENDING`). `User.telegram_id` (`packages/user`) уже зарезервирован
  под это.
- Retry/backoff для неудачной отправки, переводы `PENDING → SENT/FAILED`.
- Настройки, привязанные к конкретному объекту (например, отдельная настройка на одну
  автоматизацию, а не глобально для пользователя) — сейчас `NotificationSetting` намеренно не
  хранит `reference_type`/`reference_id`; если понадобится — отдельное расширение модели, не эта
  итерация.
- Админский CRUD каталога `notification_events` — заполняется только миграциями.
