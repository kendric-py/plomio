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
  поля lease (`claimed_by`/`claimed_at`/`lease_expires_at`), `started_at`/`finished_at` (время
  парсинга — см. ниже), `error_reason`, `user_id`,
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

**`resume_task` обязан пересчитывать `queue_expires_at`, а не оставлять исходный.** `queue_expires_at`
— это дедлайн "взять в работу", проверяемый `claim_next` (`WHERE ... queue_expires_at > now`).
Исходный дедлайн выставляется один раз в `create_task` и рассчитан на самое первое ожидание в
очереди; к моменту, когда уже запущенную (`RUNNING`) задачу ставят на паузу и потом возобновляют, он
почти наверняка уже в прошлом. Поэтому `resume_task(task_id, user_id, ttl)` принимает новый `ttl` и
выставляет `queue_expires_at = now + ttl` заново — без этого `claim_next` больше не подхватил бы
возобновлённую задачу, а ближайший `expire_stale_queued()` перевёл бы её в `EXPIRED` вместо
повторного взятия в работу.

## Время парсинга

`Task.started_at`/`Task.finished_at` — специально отдельные от `claimed_at`/`updated_at` поля, чтобы
клиент мог посчитать длительность парсинга (`finished_at - started_at`):

- **`started_at`** проставляется один раз в `TaskRepository.claim_next`, только если ещё `None` —
  момент **первого** захвата задачи воркером. В отличие от `claimed_at` (тоже проставляется в
  `claim_next`, но означает «текущая аренда» и обнуляется в `reclaim_expired_leases` при потере
  лизы), `started_at` не сбрасывается при повторном захвате после падения воркера — иначе
  длительность парсинга обнулялась бы при каждом ретрае.
- **`finished_at`** проставляется в `TaskService.complete_item` (когда все `TaskItem` пришли к
  терминальному статусу — задача становится `SUCCEEDED`/`FAILED`), в `TaskService.cancel_task`
  (`CANCELLED`) и в `TaskService.exclude_task_item`, если исключение последнего активного входа
  переводит задачу в `SUCCEEDED`. Не проставляется при `expire_stale_queued()` — задача, ни разу не
  взятая в работу (`started_at is None`), не «завершила» парсинг, а просто протухла в очереди.
- `updated_at` для этой цели не подходит — он меняется от любого `UPDATE` строки `Task` (heartbeat,
  промежуточный прогресс сиблингов и т.д.), а не только от начала/конца обработки.

## `complete_item` блокирует родительский `Task` — конкурентные siblings

`apps/worker_parser` обрабатывает `TaskItem`-элементы одной задачи конкурентно (см.
[`apps/worker_parser/AGENTS.md`](../../apps/worker_parser/AGENTS.md#модель-конкурентности)), а не
последовательно. `TaskService.complete_item` перед проверкой "все ли siblings терминальны" берёт
`SELECT ... FOR UPDATE` на строку `Task` (`TaskRepository.lock_by_id`) — без этого два элемента,
завершившиеся почти одновременно в параллельных транзакциях, могут каждый прочитать другого ещё не
терминальным (снимок READ COMMITTED до чужого коммита) и оба решить "рано обновлять статус
задачи" — упущенное обновление, задача так и останется в `RUNNING` навсегда. Лок на строку `Task`
сериализует эту проверку между siblings одной задачи (разные задачи по-прежнему завершаются
независимо, блокировка на разных строках не пересекается).

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
  снаружи периодически (`TASK_LEASE_RECLAIM_SWEEP`, `apps/api/src/jobs/task_lease_reclaim_sweep.py`,
  `config.TASK.LEASE_RECLAIM_SWEEP_INTERVAL_SECONDS` — см. [`packages/cron/AGENTS.md`](../cron/AGENTS.md)).
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

`apps/api/src/routers/task/` — полный список ручек и деталей REST-контракта см. в
[`apps/api/AGENTS.md`](../../apps/api/AGENTS.md), здесь — только правило владения. Все ручки, кроме
создания задачи, принадлежат только автору задачи: `cancel_task`/`pause_task`/`resume_task`
(добавлены вместе с `POST /{task_id}/cancel|pause|resume`) проверяют `task.user_id == user_id` **до**
проверки допустимости перехода статуса — точно так же, как `get_task_status`/`ensure_task_owner`/
`delete_task`. Порядок проверок важен: если сначала проверить статус, а не владение, ответ по
чужому `task_id` будет отличаться в зависимости от статуса задачи (`404` vs `409`) — а значит,
перебором `task_id` можно было бы косвенно узнавать статус чужих задач.

`exclude_task_item` REST-ручки пока не имеет — остальные мутирующие операции сервиса
(`cancel_task`/`pause_task`/`resume_task`) уже подключены.

## Тарификация — `packages/billing`

`TaskService` инжектит `BillingService` (см. [`packages/billing/AGENTS.md`](../billing/AGENTS.md) за
полным контрактом `charge`/`has_positive_balance`) — единственная точка интеграции с тарификацией:

- **`create_task`** — для обычной (не проверочной, `automation_id is None`) задачи сначала
  проверяет `billing_service.has_positive_balance(user_id)` (иначе `InsufficientCreditsError`,
  REST — `402`), после успешного создания зовёт `charge(action_code='task.create', ...)`
  (no-op, пока `base_cost=0`). Проверочные задачи автоматизации (`automation_id` задан) не
  проверяются и не тарифицируются здесь — их экономика полностью в `packages/automation`
  (`AutomationService.dispatch_due_checks` сам проверяет баланс до вызова `create_task`).
- **`pricing_dimension_code`/`pricing_dimension_value`** (`Task`) — денормализованный снэпшот,
  проставляется один раз при создании и не меняется: для обычной задачи —
  `("task_priority", priority)`, для проверочной — `("automation_check_frequency",
  automation.check_frequency_minutes на момент диспатча)`, передаётся вызывающим кодом
  (`AutomationService.dispatch_due_checks`). Так `record_item_progress` резолвит множитель
  тарификации без обращения к `packages/automation` — зависимость односторонняя
  (`task`/`automation` → `billing`, не наоборот).
- **`record_item_progress`** — главный хук инкрементального списания. `result_count`, который
  передаёт воркер, кумулятивный (не дельта — см. `apps/worker_parser/AGENTS.md`); метод сам
  считает `delta = result_count - TaskItem.result_count (до апдейта)` и после коммита апдейта
  зовёт `billing_service.charge(action_code=f'result.{parse_type}', quantity=delta,
  dimension_code=task.pricing_dimension_code, dimension_value=task.pricing_dimension_value, ...)`.
  Если после списания баланс пользователя `<= 0` — задача переводится в `PAUSED` через
  `pause_task_system` (см. ниже). Списание никогда не блокирует уже идущий парсинг — баланс может
  на этом шаге уйти в минус, следующая страница просто не будет запрошена (кооперативная пауза).
- **`pause_task_system(task_id)`** — internal-аналог `pause_task`, без проверки `user_id` (та же
  связь, что `get_task_by_id`/`get_task_status`), no-op, если задача уже не в паузируемом статусе.
  Вызывается только из `record_item_progress`, не имеет REST-ручки.
- **`resume_task`** — для обычной задачи (`automation_id is None`) тоже проверяет
  `has_positive_balance` (иначе `InsufficientCreditsError`, REST — `402`), **до** перевода в
  `QUEUED`. Без этой проверки задачу, автопаузированную `record_item_progress` из-за нехватки
  кредитов, можно было бы возобновить с тем же нулевым/отрицательным балансом — воркер успел бы
  собрать ещё немного результатов до следующей кооперативной проверки статуса
  (`config.POLL.STATUS_CHECK_INTERVAL_PAGES` страниц, не каждая страница — см.
  `apps/worker_parser/AGENTS.md`), баланс ушёл бы ещё глубже в минус, и задача тут же встала бы на
  паузу заново — цикл "resume → чуть поработал → снова PAUSED", пока пользователь не пополнит
  баланс настолько, чтобы задача успела дойти до конца между двумя проверками статуса. Проверочные
  задачи автоматизации (`automation_id` задан) не проверяются здесь — они и не паузируются этим
  путём (см. выше).
- **`exclude_task_item`** — та же проверка по той же причине: исключение последнего `FAILED`-
  элемента может вернуть задачу `FAILED → QUEUED` (см. "Статусы"), а это тоже решение "возобновить
  трату", не просто чистка. Проверяется до коммита — при недостатке кредитов откатывается и само
  исключение элемента, пользователь повторяет операцию после пополнения баланса, симметрично
  `resume_task`. REST-ручки у метода пока нет (см. `apps/api/AGENTS.md`), но домен обязан быть
  корректен и без неё.

## Уведомления — `packages/notifications`

`TaskService` инжектит `NotificationService` (см. [`packages/notifications/AGENTS.md`](../notifications/AGENTS.md)
за полным контрактом `notify`). Единственная точка интеграции — **`complete_item`**: когда все
`TaskItem` задачи дошли до терминального статуса и `Task` переходит в `SUCCEEDED`/`FAILED`, после
коммита транзакции (вне блока `async with`, отдельная сессия — тот же принцип, что описан в
[`packages/automation/AGENTS.md`](../automation/AGENTS.md#композиция-сервисов-и-транзакции)) зовёт
`notification_service.notify(event_code='task.completed'|'task.failed', payload={'task_id': ...,
'error_reason': ..., 'task_link': ..., 'result_count': ...})`. `task_link` — ссылка на страницу
задачи в веб-интерфейсе (`{frontend_base_url}/tasks/{task_id}`, `TaskService.frontend_base_url`);
`None`, если не задан. `result_count` — `sum(item.result_count for item in items)` по уже
прочитанным (для проверки терминальности) сиблингам, тот же агрегат, что в `get_progress`.
**Важно**: обычные задачи завершает `apps/worker_parser`, не `apps/api` — значение приходит из
**его собственного** `.env` (`FRONTEND_BASE_URL`, не `apps/api`'s `REST_FRONTEND_BASE_URL`), см.
[`packages/notifications/AGENTS.md`](../notifications/AGENTS.md#базовый-url-фронтенда).

**Пропускается, если `Task.automation_id is not None`** — это внутренняя проверочная задача
автоматизации (см. "`Task.automation_id`" в [`packages/automation/AGENTS.md`](../automation/AGENTS.md)),
её завершение уже обрабатывается `AutomationService._finalize_check` собственным событием
(`automation.change_detected`) — повторное `task.*`-уведомление на том же тике было бы дублем.

## Не входит в эту итерацию

Хранение результатов парсинга (товары/отзывы) — отдельная доменная область `packages/result`.
`packages/task` хранит только оркестрацию, не сами результаты.
