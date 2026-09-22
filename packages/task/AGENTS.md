# packages/task

Доменная область задач парсинга маркетплейсов (OZON, Wildberries) — единоразовые задачи (не
периодические; периодические задачи-мониторинги — см. [`packages/automation`](../automation/AGENTS.md),
которая переиспользует этот домен для одноэлементных проверочных задач). Хранит
только оркестрацию (статус, приоритет, TTL, прогресс, курсор возобновления, ошибки), а не сами
результаты парсинга (товары/отзывы) — это отдельная будущая доменная область.

Очередь реализована поверх Postgres (без брокера — RabbitMQ/Redis намеренно не используются, см.
`docs/reference/architecture.md`): захват задачи воркером — `SELECT ... FOR UPDATE SKIP LOCKED`.

## Модель

Задача = родитель + дочерние элементы, а не одна плоская строка:

- **`Task`** (`tasks`) — сама задача: `parse_type`, `marketplace` (`core.enums.Marketplace` —
  общий с `apps/worker_sessions`/`apps/worker_parser`, определяет, какие фетчеры/сессии
  использовать; не выводится эвристикой из `input_value`, задаётся явно при создании), `status`,
  `priority` (1..10, 1 — наивысший, `CheckConstraint`), `queue_expires_at` (абсолютное время
  истечения TTL — не `ttl_seconds`, чтобы claim-запрос был простым сравнением), `result_limit`,
  поля lease (`claimed_by`/`claimed_at`/`lease_expires_at`), `error_reason`, `user_id`,
  `automation_id` (`UUID | None`, FK на `automations.id`, `SET NULL`) — проставляется один раз
  [`packages/automation`](../automation/AGENTS.md) при создании проверочной задачи и не
  обнуляется; `TaskRepository.get_by_user_id`/`count_by_user_id` по умолчанию скрывают такие
  задачи (`WHERE automation_id IS NULL`) — обычный список задач пользователя (фронтенд) не должен
  показывать проверочные задачи автоматизаций вперемешку со своими.
- **`TaskItem`** (`task_items`) — один на каждый вход из списка (ссылка/поисковый
  запрос), с собственными `status`, `cursor` (JSONB), `result_count`, `error_reason`.

Разделение на родителя и элементы — намеренное архитектурное решение: пользователь должен уметь
убрать один невалидный вход (перевести его в `EXCLUDED`) и продолжить задачу с сохранением прогресса
остальных входов, не теряя уже собранные результаты (см. `TaskService.exclude_task_item`).

**`id`/`task_id` — `UUID` (`uuid.uuid4`, генерируется на стороне Python при `INSERT`, не
`gen_random_uuid()` на стороне БД — не требует включённого расширения `pgcrypto`), а не
автоинкрементный `int`, как у остальных доменов репозитория (`users`, `audit_logs` и т.д.).**
Осознанное отступление для этого домена по явному требованию — `id` задачи возвращается клиенту в
`POST /api/tasks/` и используется как публичный идентификатор ресурса.

## Курсор — персистентный, не эфемерный

В существующем парсере (`marketplace-parser`) курсор пагинации (`resume_state`) живёт только в
памяти на время retry внутри одного процесса и теряется при падении/рестарте воркера. Здесь курсор
(`TaskItem.cursor`) обязан персистироваться в БД по ходу работы (`record_item_progress`,
вызывается воркером после каждой страницы/батча — периодичность решает воркер), а не только в момент
ошибки — иначе он не переживёт падение воркера и `reclaim_expired_leases`.

## Lease/heartbeat — детект упавшего воркера

`claimed_by`/`claimed_at`/`lease_expires_at` — это аренда: воркер обязан периодически продлевать её
через `TaskRepository.heartbeat`, пока обрабатывает задачу. `reclaim_expired_leases()`
(вызывается снаружи периодически, например планировщиком) возвращает в очередь (`QUEUED`) любую
задачу, чья аренда протухла — это и есть сигнал "воркер упал/завис". Прогресс не теряется, так как
курсор уже сохранён на уровне `TaskItem`.

## Статусы

`Task.status`: `QUEUED → RUNNING → (SUCCEEDED | FAILED)`, плюс `PAUSED`, `EXPIRED`,
`CANCELLED`. Пауза и отмена — **кооперативные**: домен только выставляет статус, воркер обязан сам
проверять его и прекращать работу — доменная область не может принудительно прервать выполняющийся
код воркера.

`TaskItem.status`: `PENDING → RUNNING → (SUCCEEDED | FAILED)`, плюс `EXCLUDED` (вход убран
пользователем как невалидный).

TTL: задача, не взятая в работу (`claim_next`) до истечения `queue_expires_at`, получает явный статус
`EXPIRED` через `expire_stale_queued()` — это видно в истории задач, а не просто "зависает" в очереди
молча.

## Прогресс

`TaskService.get_progress` возвращает `{total_items, processed_items, result_count}`,
вычисляемые на лету по `task_items` (не хранятся отдельными полями — не могут рассинхро-
низироваться). Для `ParseType.PRODUCT_PAGE` (заранее известное количество входов) потребитель
показывает `processed_items` из `total_items`; для остальных типов (неизвестный заранее общий
объём) — `result_count`. Домен не ветвится по `parse_type` — оба агрегата считаются одинаково для
всех типов, выбор представления — на стороне потребителя.

## Интеграция

`TaskRepository` и `TaskItemRepository` подключаются в
[`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py) через
`use_task_repository=True`/`use_task_item_repository=True`.

`TaskService` дополнительно оборачивает захват/аренду задачи, чтобы `apps/worker_parser` работал
через сервисный слой, а не напрямую через `TaskRepository` (единая точка входа в домен, как и у
`apps/api`):

- `claim_next(worker_id, lease_duration)` — обёртка над `TaskRepository.claim_next`.
- `heartbeat(task_id, worker_id, lease_duration)` — обёртка над `TaskRepository.heartbeat`,
  продлевает `lease_expires_at`, пока воркер обрабатывает задачу.
- `reclaim_expired_leases()` — обёртка над `TaskRepository.reclaim_expired_leases`, вызывается
  снаружи периодически (планировщиком).
- `get_task_by_id(task_id)` — без проверки `user_id` (в отличие от `get_task_status`); внутренний
  вызов воркера для кооперативной проверки `PAUSED`/`CANCELLED` между страницами/батчами, не
  REST-контракт.
- `get_task_items(task_id)` — список всех `TaskItem` задачи; воркер использует его, чтобы получить
  входы для обработки при захвате задачи.
- `ensure_task_owner(task_id, user_id)` — проверяет `task.user_id == user_id`, иначе
  `ObjectNotFoundError` (как и `get_task_status`, единообразно с несуществующей задачей); REST-ручки,
  которым нужен только факт владения без пересчёта прогресса (например, результаты задачи),
  используют этот метод вместо `get_task_status`.

## REST

`apps/api/src/routers/task/` (см. [`apps/api/AGENTS.md`](../../apps/api/AGENTS.md)) — две
реализованные ручки:

- `POST /api/tasks/` — создание задачи авторизованным пользователем.
- `GET /api/tasks/{task_id}` — статус и прогресс задачи, только для владельца (`TaskService.get_task_status`
  проверяет `task.user_id == current_user.id`, иначе `ObjectNotFoundError`, как для несуществующей
  задачи — единообразно, без утечки самого факта существования чужой задачи).

Остальные операции сервиса (`cancel_task`/`pause_task`/`resume_task`/`exclude_task_item` и т.д.)
REST-ручек пока не имеют.

## Не входит в эту итерацию

Хранение результатов парсинга (товары/отзывы) — отдельная доменная область `packages/result`.
`packages/task` хранит только оркестрацию, не сами результаты.
