# apps/api

REST API. Точка входа для клиентов (фронтенд, внешние интеграции) и администраторов.

## Роуты

`src/routers/router.py::api_router` — глобальный роут `/api`, к которому подключаются все
остальные роутеры (`api_router.include_router(...)`). Это единственная точка входа в
`configure_rest_server` — сам `FastAPI()` инклюдит только `api_router`, не отдельные роутеры доменов
напрямую.

- `routers/auth/endpoints.py` + `routers/auth/schema.py` (`/api/auth`):
  - `GET /status` — `{"has_users": bool}`. Публичный, без авторизации — фронт вызывает его перед
    показом экрана логина, чтобы решить: показывать логин или «зарегистрируйте администратора» (если
    `has_users == false`).
  - `POST /register`, `POST /login`. Оба дергают `AuthService` через DI
    (`Depends(Provide[DependencyContainer.auth_service])`), на успехе выпускают JWT
    (`packages.auth.src.security.create_access_token`) и возвращают `TokenResponse`.
    `UserAlreadyExistsError` → 409, `InvalidCredentialsError` → 401. Первый зарегистрированный в
    пустой системе получает роль `ADMIN` (логика — в `AuthService.register_user`, не в роутере).
- `routers/user/endpoints.py` + `routers/user/schema.py` (`/api/user`):
  - `GET /me` — требует авторизации (`Depends(get_current_user)`), возвращает `UserResponse` текущего
    пользователя.
  - `admin_router` (`/api/admin/users`, `Depends(get_current_admin_user)`): `GET /` — постраничный
    список всех пользователей, сортировка по `id` (`UserListResponse`: `items: list[UserResponse]` +
    `meta: PaginationMeta`), `limit` 1..500 (по умолчанию 100), `offset` ≥ 0, через
    `UserService.list_page`. Модуль добавлен в `container.wire(modules=[...])`.
    `PATCH /{user_id}` — частичное обновление (`UpdateUserRequest`: `display_name`/`email`/`role`/
    `telegram_id`, все опциональны; `null` = «не менять», очистить `telegram_id` нельзя, т.к.
    `BaseRepository.update` игнорирует `None`) через `UserService.update_profile`, ответ —
    `UserResponse`. Несуществующий пользователь → `404`, занятый email
    (`DuplicatedObjectError`) → `409`. Пароль этой ручкой не меняется.
    `POST /` — регистрация пользователя администратором (`CreateUserRequest`: `email`, `password`
    ≥ 8, опциональные `display_name` (по умолчанию — email), `role` (по умолчанию `CLIENT`) и `credits` ≥ 0 —
    начальный баланс: не указан → обычный signup-бонус, `0` → ничего, `> 0` → именно столько
    (`BillingService.grant` от имени админа, `comment='admin_create'`, заменяет бонус; сбой
    начисления, в отличие от бонуса, не скрывается — пользователь уже создан, кредиты можно выдать
    через `POST /api/admin/billing/users/{user_id}/grant`)),
    `201` + `UserResponse`, токен не выдаётся. Идёт через `AuthService.register_user(role=...)` —
    тот же сценарий, что публичный `POST /api/auth/register` (хэш пароля, audit, signup-бонус), но
    с явной ролью вместо «первый — ADMIN». Занятый email → `409`.
    `DELETE /{user_id}` — удаление, `204`. Несуществующий → `404`; удалить самого себя → `409`
    (чтобы админ не лишил систему доступа). Связанные данные (задачи, автоматизации, кошелёк,
    настройки уведомлений) удаляются каскадом на уровне БД (`ondelete='CASCADE'`), audit-записи и
    `granted_by_admin_id` обнуляются (`SET NULL`).
- `routers/audit_log/{endpoints,dependencies,schema}.py` (`admin_router`, `/api/admin/audit-logs`,
  `Depends(get_current_admin_user)`; см. [`packages/audit_log/AGENTS.md`](../../packages/audit_log/AGENTS.md)):
  `GET /` — постраничный журнал аудита, новые сверху (`AuditLogListResponse`: `items:
  list[AuditLogResponse]` + `meta: PaginationMeta`), `limit` 1..500 (по умолчанию 100), `offset` ≥ 0.
  Фильтры (AND) собирает `dependencies.py::get_audit_log_filters` в доменный `AuditLogFilters`:
  `user_id`, `action`, `action_type`, `status`, `error_reason`, `target_type`, `target_id`,
  `ip_address` (точное совпадение) и общий `date_from`/`date_to` (`get_date_range`, по `created_at`).
  Через `AuditLogService` (`audit_log_service` в `container.py`); модуль добавлен в
  `container.wire(modules=[...])`.
- `routers/schema.py` — REST-примитивы, переиспользуемые несколькими роутерами (а не одним доменом),
  в отличие от `routers/<domain>/schema.py`. Сейчас там `PaginationMeta` (`total`/`limit`/`offset`) —
  используется в `routers/task/schema.py` (`TaskListResponse`/`TaskResultsResponse`),
  `routers/user/schema.py` (`UserListResponse`) и
  `routers/automation/schema.py` (`AutomationListResponse`/`AutomationHistoryListResponse`); до
  выноса была продублирована в обоих файлах дословно. Там же `DateRange` (`date_from`/`date_to`) —
  результат общей зависимости `routers/dependencies.py::get_date_range` (опциональный фильтр по
  датам: UTC, границы включительные, naive → UTC, `from > to` → 422). Подключается точечно через
  `Depends(get_date_range)`, сейчас — `GET /api/tasks/`, `GET /api/automations/` и `GET /api/automations/with-history` (по
  `created_at`); в домен передаются просто
  `date_from`/`date_to`, колонку времени выбирает репозиторий.
- `routers/task/endpoints.py` + `routers/task/schema.py` (`/api/tasks`). Схема файла разложена на
  секции: сверху переиспользуемые сущности (`TaskItemResponse`, `TaskBaseResponse` — общие поля
  задачи, `TaskProgressFields` — агрегаты прогресса, `ResultItemResponse`), ниже — запрос
  (`CreateTaskRequest`) и ответы, которые их комбинируют. `PaginationMeta` в этот файл не входит —
  она общая для нескольких роутеров, см. ниже раздел про `routers/schema.py`. `TaskBaseResponse` и
  `TaskProgressFields` существуют именно для того, чтобы одинаковые по смыслу ручки не расходились
  составом полей — раньше `GET /{task_id}` (тогда `TaskStatusResponse`) и `GET /` (`TaskListItemResponse`)
  описывали пересекающийся набор полей задачи вручную и разошлись (в статусе не было `priority`,
  `queue_expires_at`, `result_limit`, `user_id`, `automation_id`, `updated_at`). Теперь обе ручки
  используют один класс `TaskDetailResponse(TaskProgressFields, TaskBaseResponse)` — порядок
  родителей важен (pydantic собирает поля в порядке обратного MRO), `TaskBaseResponse` как основная
  сущность указан последним, чтобы её поля шли в начале JSON-ответа, см.
  [gold-rules.md](../../docs/reference/gold-rules.md#rest-схемы). `TaskBaseResponse` также содержит
  `started_at`/`finished_at` — время начала/конца парсинга (см.
  [`packages/task/AGENTS.md`](../../packages/task/AGENTS.md#время-парсинга)), поэтому оба доступны
  и в `GET /{task_id}`, и в `GET /`, и в ответе `POST /`.
  - `POST /` — требует авторизации (`Depends(get_current_user)`), создаёт задачу парсинга через
    `Depends(Provide[DependencyContainer.task_service])`
    (`TaskService.create_task` — см. [`packages/task/AGENTS.md`](../../packages/task/AGENTS.md)).
    `user_id` берётся из текущего пользователя, не из тела запроса. `CreateTaskRequest.ttl_seconds`
    конвертируется в `timedelta` в роутере — домен принимает `timedelta`, а не секунды, REST-контракт
    этого не знает. Ответ (`CreateTaskResponse(TaskBaseResponse)`) отдаёт всю доступную на момент создания
    информацию о задаче (включая `error_reason`, `automation_id`, `updated_at`), а также `items` —
    созданные `TaskItem` (`id`/`position`/`input_value`/`status`), которые роутер дополнительно
    запрашивает через `TaskService.get_task_items`: без этого клиент не узнал бы `id` элементов
    задачи, нужные для будущих ручек вроде `exclude_task_item`.
  - `GET /{task_id}` — требует авторизации, возвращает `TaskDetailResponse` (все поля задачи +
    агрегированный прогресс `total_items`/`processed_items`/`result_count` из
    `TaskService.get_task_status`). Задача, принадлежащая другому пользователю, или несуществующий
    `task_id` — оба дают `404` (`ObjectNotFoundError` → `HTTPException(404)`), без различия между
    «не найдено» и «чужое», чтобы не давать возможность перебором `task_id` узнавать о чужих задачах.
  - `GET /` — требует авторизации, постранично отдаёт задачи пользователя (`TaskListResponse`:
    `items: list[TaskDetailResponse]` + `meta`), тот же `TaskDetailResponse`, что и у `GET /{task_id}`.
    Фильтры: `status` и общий `date_from`/`date_to` (по `created_at`).
  - `GET /{task_id}/results` — требует авторизации, постранично отдаёт результаты задачи
    (`TaskResultsResponse`: `items` + `meta` — см. [конвенцию пагинации в
    gold-rules.md](../../docs/reference/gold-rules.md#пагинация-в-rest-ответах), `meta` всегда
    последним полем), `limit` 1..500 (по умолчанию 100), `offset` ≥ 0. Владение проверяется через
    `TaskService.ensure_task_owner` (тот же 404-паттерн, что и у `GET /{task_id}`, без различия между
    «не найдено» и «чужое»), сами результаты — через `ResultService.get_results_for_task` (см.
    [`packages/result/AGENTS.md`](../../packages/result/AGENTS.md)) — join `result_items`↔`task_items`
    по `task_id`, сортировка по `created_at`.
  - `GET /{task_id}/results/export` — требует авторизации, отдаёт **все** результаты задачи
    файлом xlsx (`Content-Disposition: attachment`). Владение — тот же `ensure_task_owner`/404.
    Результаты забираются из `ResultService.get_results_for_task` страницами по 500, файл
    собирается в `routers/task/xlsx_export.py::build_results_xlsx` (XlsxWriter, в потоке через
    `run_in_threadpool`): отдельный лист на тип сущности (товары, карточки, отзывы, продавцы —
    определяется по ключам `payload`), цветные колонки по смыслу (заголовок насыщенного цвета,
    14pt bold, белый текст; ячейки колонки — светлый тон того же цвета), закреплённая шапка и
    автофильтр. Новая колонка — запись `_col(...)` в нужном списке модуля. Весь результат
    держится в памяти (лимит — `result_limit` задачи).
  - `POST /{task_id}/cancel`, `POST /{task_id}/pause`, `POST /{task_id}/resume` — требуют
    авторизации, возвращают `TaskDetailResponse` (та же форма, что и `GET /{task_id}`/`GET /`;
    сервис не пересчитывает прогресс сам, роутер дополнительно запрашивает его через
    `TaskService.get_progress`, аналогично тому, как `POST /` дополнительно запрашивает `items`).
    `TaskService.cancel_task`/`pause_task`/`resume_task` проверяют `task.user_id == current_user.id`
    **до** проверки допустимости перехода — чужая или несуществующая задача даёт `404`
    (`ObjectNotFoundError`), а собственная задача в недопустимом для операции статусе (например,
    повторная пауза уже приостановленной задачи, или `resume` не-`PAUSED` задачи) даёт `409`
    (`InvalidTaskTransitionError` → `HTTPException(409)`) — первый такой домен-специфичный (не
    `ObjectNotFoundError`) exception-маппинг в этом роутере, см.
    [`packages/task/AGENTS.md`](../../packages/task/AGENTS.md#rest). `cancel` разрешён и для задачи в
    `RUNNING` (уже идёт парсинг) — отмена **кооперативная**: домен только выставляет `CANCELLED`,
    сам воркер обязан заметить это между страницами/батчами и прекратить работу (см.
    [`packages/task/AGENTS.md`](../../packages/task/AGENTS.md#статусы)); REST не может прервать уже
    выполняющийся код воркера напрямую. `POST /{task_id}/resume` — единственный из трёх, что требует
    тело запроса (`ResumeTaskRequest.ttl_seconds`, тот же смысл, что у `CreateTaskRequest.ttl_seconds`):
    `TaskService.resume_task` пересчитывает `queue_expires_at = now + ttl`, а не оставляет исходный
    дедлайн из создания задачи — тот почти наверняка уже в прошлом к моменту паузы/возобновления уже
    поработавшей задачи, см. [`packages/task/AGENTS.md`](../../packages/task/AGENTS.md#статусы) за
    объяснением, почему без этого `claim_next` не забрал бы её обратно.
    `exclude_task_item` пока не имеет REST-ручки.

- `routers/task_admin/{endpoints,dependencies,schema}.py` (`admin_router`, `/api/admin/tasks`,
  `Depends(get_current_admin_user)`; доменная часть — [`packages/task/AGENTS.md`](../../packages/task/AGENTS.md#админский-мониторинг)):
  - `GET /summary` — `AdminTaskSummaryResponse`: только `tasks` — **пользовательские** задачи по статусам +
    `total` за период (`date_from`/`date_to` по `created_at`). «Просроченные задачи» — `EXPIRED`. Проверочные
    задачи автоматизаций считаются в `GET /api/admin/automations/summary`. Регистрируется **до** `/{task_id}`.
  - `GET /` — страница задач всех пользователей (`AdminTaskListResponse`, `limit` 1..500, по умолчанию 50).
    Фильтры (AND, `dependencies.py::get_admin_task_filters`): `task_id`, `item_id`, `automation_id`, `purpose`
    (`task`|`automation`), `user_id`, `marketplace`, `status`, `parse_type`, `date_from`/`date_to`. Элемент
    списка (`AdminTaskListItemResponse`) — `TaskDetailResponse` + `failed_items[]` (до 3 упавших элементов
    с `error_reason` и `input_value` — оригинальные причины ошибок).
  - `GET /{task_id}` — `AdminTaskDetailResponse`: задача + прогресс + аренда воркера + все элементы с
    `cursor`/`error_reason` + `notifications[]` (уведомления задачи: канал, статус `PENDING`/`SENT`/`FAILED`,
    `sent_at`, `failure_reason`, `event_code` и `payload` — причина; см.
    [`packages/notifications/AGENTS.md`](../../packages/notifications/AGENTS.md#доставки-задачи-админка)).
    `GET /{task_id}/results` — результаты без проверки владельца.
  - `POST /{task_id}/cancel|pause|resume|restart` и `POST /{task_id}/items/{item_id}/exclude` → `404`
    (нет задачи/элемента), `409` (недопустимый статус), `402` (нет кредитов у владельца); `resume` и
    `restart` принимают `ttl_seconds`. Модуль в `container.wire(modules=[...])`.

- `routers/automation_admin/{endpoints,dependencies,schema}.py` (`admin_router`, `/api/admin/automations`,
  `Depends(get_current_admin_user)`) — раздел «Автоматизации» админки (отдельно от «Задач»):
  - `GET /summary` — `AdminAutomationSummaryResponse`: `automations` (`active`/`paused`/`overdue`/`with_error` —
    на сейчас; `checks`/`failed_checks` — тики за период) и `check_tasks` (проверочные задачи по статусам за
    период). **Просроченная автоматизация** — `ACTIVE`, `next_check_at <= now()`, `pending_task_id IS NULL`.
    Регистрируется **до** `/{automation_id}`.
  - `GET /` — автоматизации всех пользователей (`AdminAutomationListResponse`, `limit` 1..500, по умолчанию 50,
    новые сверху; элемент — `AutomationResponse` + `user_id`, `pending_task_id`, `is_overdue`). Фильтры (AND,
    `dependencies.py::get_admin_automation_filters`): `automation_id`, `user_id`, `marketplace`, `status`,
    `in_stock`, `overdue=true`, `has_error=true`, `search` (подстрока в названии/артикуле/ссылке, без
    регистра), `date_from`/`date_to` по `created_at`.
  - `GET /{automation_id}` — `AdminAutomationResponse` (деталь с `last_info` + `user_id`, `pending_task_id`,
    `is_overdue`); `POST /{id}/pause`, `POST /{id}/resume` (элемент списка), `DELETE /{id}` (`204`) — без
    проверки владельца (`AutomationService.*(user_id=None)`). `404` — нет автоматизации.
  - `GET /{automation_id}/notifications` — вся история уведомлений (по `payload.automation_id`, новые сверху,
    `limit` 1..200, по умолчанию 20 + `meta`), элементы той же формы, что `notifications[]` у
    `GET /api/admin/tasks/{id}`. Проверочные задачи автоматизации — `GET /api/admin/tasks/?automation_id=`.
  Модуль в `container.wire(modules=[...])`.

- `routers/billing/endpoints.py` + `routers/billing/schema.py` — два роутера в одном файле:
  `router` (`/api/billing`, owner-only, `Depends(get_current_user)`) — `GET /balance`,
  `GET /transactions` (плоский журнал: списания и начисления), `GET /transactions/export` (CSV, UTF-8 с BOM,
  `routers/billing/csv_export.py`), `GET /transactions/by-reference` (траты, сгруппированные по
  `reference_type`+`reference_id`) — все три принимают общие фильтры `reference_type`/`reference_id`/`kind`
  (`spend`|`grant`)/`date_from`/`date_to` (`dependencies.py::get_transaction_filters`); `GET /stats` и
  `GET /stats/daily` (траты пользователя за период, итог и по дням), `GET /spending/{reference_type}/{reference_id}`
  (расход на одну задачу/автоматизацию/direct-запрос; для автоматизации — с её проверками; чужой id даёт нули),
  `GET`/`PUT /limits` (собственные лимиты расходов и потрачено), `GET /pricing` (прайс для расчёта
  стоимости на фронте: каталог действий + правила множителей, только чтение, `PricingResponse`); `admin_router`
  (`/api/admin/billing`, `Depends(get_current_admin_user)`) — CRUD над каталогом действий
  (`GET`/`PATCH /actions/{action_code}`), `GET /stats` — статистика трат всех пользователей за
  период (`SpendingStatsResponse`: `total_spent`/`tasks_spent`/`automations_spent`/`direct_spent` в
  кредитах + эхо `date_from`/`date_to`; период — общий `Depends(get_date_range)`, по `created_at`
  транзакций, без периода — за всё время; классификация — см.
  [`packages/billing/AGENTS.md`](../../packages/billing/AGENTS.md)), и правилами множителей (`GET`/`POST /pricing-rules`,
  `DELETE /pricing-rules/{rule_id}`), `POST /users/{user_id}/grant` — ручное начисление кредитов.
  `routers/billing/dependencies.py::get_current_admin_user` — первая admin-only зависимость в
  проекте, оборачивает `get_current_user` проверкой `current_user.role == UserRole.ADMIN` (иначе
  `403`). `OverlappingPricingRuleError` → `409`, `ObjectNotFoundError` → `404`. См.
  [`packages/billing/AGENTS.md`](../../packages/billing/AGENTS.md) за доменной логикой.
  `packages.billing.src.exceptions.InsufficientCreditsError` → `402` — обрабатывается также в
  `routers/task/endpoints.py::create_task`/`resume_task` и
  `routers/automation/endpoints.py::create_automation`, не только в этом роутере.

- `routers/notifications/endpoints.py` + `routers/notifications/schema.py` (`/api/notifications`,
  owner-only, `Depends(get_current_user)`, без admin-роутера — настройки полностью принадлежат
  пользователю, см. [`packages/notifications/AGENTS.md`](../../packages/notifications/AGENTS.md)):
  `GET /events` (каталог активных типов событий), `GET`/`PUT /preferences` (карта
  `{event_code: [channel, ...]}` пользователя целиком; `PUT` с неизвестным/неактивным `event_code`
  → `UnknownNotificationEventError` → `422`), `GET /deliveries` (read-only постраничный журнал —
  доставки создаются только доменом, не пользователем).

- `routers/direct/{endpoints,dependencies,schema,errors}.py` (`endpoints.py` — только обработчики;
  обмен с воркером, `page_key`, проверка баланса и списание — в `dependencies.py`) (`/api/marketplace`, tag `Marketplace`, всё с
  `Depends(get_current_user)`; см. [`packages/direct/AGENTS.md`](../../packages/direct/AGENTS.md)):
  `GET /{marketplace}/product/{article}` (карточка), `GET /{marketplace}/product/{article}/reviews`
  `GET /{marketplace}/search?query=`, `GET /{marketplace}/category?url=` и
  `GET /{marketplace}/seller?seller=` (числовой id — только Wildberries, либо ссылка; все постраничные: `?page_key=`, в ответе `next_page_key`).
  Запрос уходит воркеру через `DirectBus` (Redis), `api` ждёт ответ до
  `DIRECT_REQUEST_TIMEOUT_SECONDS`. `page_key` формирует и проверяет только этот роутер.
  **Клиенту не отдаются ошибки маркетплейсов/парсера/инфраструктуры — только фиксированные
  сообщения из `errors.py`**; новые статусы обязаны идти через него. Тарификация: проверка баланса
  до запроса (402), списание через `BillingService.charge` только за успешный ответ, сбой
  проверки/списания → 503 (см. [`packages/direct/AGENTS.md`](../../packages/direct/AGENTS.md#тарификация-packagesbilling)). Провайдер `direct_bus`
  (`providers.Singleton(DirectBus)`) — в `container.py`.

`routers/automation/endpoints.py::bulk_create_automations` (`POST /api/automations/bulk`) — до 100
`CreateAutomationRequest` за запрос (`BulkCreateAutomationsRequest.items`, `min_length=1`,
`max_length=100`). Один вызов `AutomationService.bulk_create_automations` (пакетный поиск дублей и
один multi-row `INSERT ... RETURNING` в репозитории, не цикл по `create_automation`), частичный успех:
ответ всегда `200`, `BulkCreateAutomationsResponse.results[i]` содержит либо `automation`, либо
`error` (`BulkAutomationErrorCode`: `INVALID_CHECK_FREQUENCY`/`DUPLICATE`/`INSUFFICIENT_CREDITS` — те
же доменные ошибки, что дают `422`/`409`/`402` у одиночной ручки; роутер мапит класс ошибки из
`BulkCreateResult.error` через `BULK_ERROR_CODES`). Неожиданные исключения не перехватываются.

`routers/automation/dependencies.py::get_automation_filters` — Depends со всеми опциональными
фильтрами списка автоматизаций (`status`, `in_stock`, `price_from`/`price_to`, плюс общий
`get_date_range`), общий для `GET /api/automations/` и `/with-history`; возвращает доменный
`AutomationListFilters`.

Новый роутер домена: создать `routers/<domain>/endpoints.py` с `router = APIRouter(prefix='/<domain>',
tags=[...])`, подключить в `routers/router.py` через `api_router.include_router(router=...)`. Если
роутер использует `@inject`/`Provide[...]` (напрямую или через зависимость вроде `get_current_user`,
которая сама `@inject`) — добавить путь модуля в `container.wire(modules=[...])` в
`configure_rest_server` (`src/server.py`), иначе DI не сработает.

**Pydantic-схемы запросов/ответов REST — в `routers/<domain>/schema.py`, не в `packages/<domain>/`.**
Домен (`packages/*`) не знает про REST-транспорт; схема — контракт конкретного роута этого app. См.
[правило в gold-rules.md](../../docs/reference/gold-rules.md#rest-схемы).

## Авторизация в Swagger

`routers/auth/dependencies.py::get_current_user` — FastAPI-зависимость `HTTPBearer()` +
`packages.auth.src.security.decode_access_token` + `UserService.get_by_id`. Любой эндпоинт с
`Depends(get_current_user)` автоматически получает схему безопасности `HTTPBearer` в OpenAPI — в
Swagger UI (`/docs`) появляется кнопка **Authorize**, куда вставляется access-токен
(`Bearer <access_token>`, полученный из `POST /api/auth/login`/`register`), и дальше он подставляется
во все защищённые запросы из UI. Невалидный/просроченный токен или несуществующий пользователь → 401.

Модуль `routers/auth/dependencies.py` добавлен в `container.wire(modules=[...])` в `src/server.py` —
без этого `Depends(Provide[...])` внутри `get_current_user` не резолвится.

## DI-контейнер

`src/container.py` — `DependencyContainer(DeclarativeContainer)`, собственный для этого app (у
каждого `apps/*`, которому он нужен, — свой контейнер, общего контейнера в `core/` нет).

- `session_factory` — `async_sessionmaker`, полученный через
  [`core.database.get_database_connection(config=...)`](../../core/database.py) от `apps.api.src.config.config`
  (`config.POSTGRES`).
- `transaction_manager` — [`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py).
- `user_service` — [`packages.user.src.service.UserService`](../../packages/user/AGENTS.md#сервис).
- `auth_service` — [`packages.auth.src.service.AuthService`](../../packages/auth/AGENTS.md).
- `task_service` — [`packages.task.src.service.TaskService`](../../packages/task/AGENTS.md), теперь
  также принимает `billing_service` и `notification_service`.
- `result_service` — [`packages.result.src.service.ResultService`](../../packages/result/AGENTS.md).
- `proxy_service` — [`packages.proxy.src.service.ProxyService`](../../packages/proxy/AGENTS.md); роутер
  `routers/proxy` (`/api/admin/proxies` для админа, `/api/proxy/issue` для воркера по `X-Worker-Token`).
- `billing_service` — [`packages.billing.src.service.BillingService`](../../packages/billing/AGENTS.md),
  инжектируется и в `task_service`, и в `automation_service` (каждый получает свой отдельный
  `AsyncTransactionManager`-экземпляр — `transaction_manager` сам `providers.Factory`, повторное
  разрешение внутри одного графа создаёт новый инстанс, тот же принцип, что описан в
  [`packages/automation/AGENTS.md`](../../packages/automation/AGENTS.md#композиция-сервисов-и-транзакции)).
- `notification_service` — [`packages.notifications.src.service.NotificationService`](../../packages/notifications/AGENTS.md),
  тем же принципом инжектируется и в `task_service`, и в `automation_service`.

Контейнер создаётся в `src/server.py::configure_rest_server` и кладётся в `app.container`.
`container.wire(modules=[...])` перечисляет каждый модуль роутера, который использует
`@inject`/`Provide[...]`: сейчас `routers/auth/dependencies.py`, `routers/auth/endpoints.py`,
`routers/task/endpoints.py`. `routers/user/endpoints.py` пока нет (заглушка без DI).

> TODO: `user_service` пока не используется ни одним роутером (`routers/user/endpoints.py` —
> заглушка) — когда появятся реальные эндпоинты профиля, подключить через
> `Depends(Provide[DependencyContainer.user_service])` и добавить модуль в `container.wire(modules=[...])`.

## Конфигурация

`src/config.py::Config` — `REST` (host/port/title) и `POSTGRES` (`core.configs.PostgresConfig`).
Значения из `.env` (см. `.env.example`): `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `AUTH_SECRET_KEY`, `AUTH_ALGORITHM`,
`AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`, `DIRECT_REQUEST_TIMEOUT_SECONDS` (20.0 — ожидание ответа воркера,
он же `deadline_at` запроса), `DIRECT_PAGE_KEY_TTL_SECONDS` (900.0). `configure_rest_server` настраивает
`logging.basicConfig(level=INFO)` — иначе INFO-логи приложения не выводятся.

`.env` резолвится по абсолютному пути (`config.py::ENV_FILE = Path(__file__).resolve().parent.parent
/ '.env'`), а не относительно cwd — иначе `Config()`/`PostgresConfig()` ищут `.env` там, откуда
запущена команда (`poetry run ...`), а не в `apps/api/`, и падают с ошибкой валидации, если этот
каталог — не `apps/api/` (ровно так и ломался alembic, пока не переехал в корень — см. ниже).

## Локальный Postgres

`docker-compose.dev.yml` в корне репозитория поднимает dev-Postgres на **порту хоста 5433** (не 5432
— чтобы не конфликтовать с другими Postgres-контейнерами на машине разработчика), с кредами
`postgres`/`postgres`/`plomio`, совпадающими со значениями по умолчанию в `.env.example`:

```
docker compose -f docker-compose.dev.yml up -d
```

## Миграции (Alembic)

`alembic.ini` + `alembic/` — в **корне репозитория** (глобальный скоуп), не внутри `apps/api/`.
Причина не в самих миграциях (они всё равно только про БД `apps/api`, единственного app с БД), а в
том, что репозиторий уже так устроен: `core.*`/`packages.*.src.*` — абсолютные импорты от корня
репозитория, и alembic как инструмент, который обходит все доменные области ради `target_metadata`,
естественно живёт на этом же уровне, а не внутри одного конкретного app.

- `alembic/env.py` — асинхронный шаблон (`async_engine_from_config` + `connection.run_sync`), URL
  берётся из `apps.api.src.config.config.POSTGRES.DSN` (не дублируется в `alembic.ini`),
  `target_metadata = core.database.BaseSQLModel.metadata`. Модели из доменных областей
  (`packages/user`, `packages/membership`, `packages/api_keys`) импортируются в `env.py` только ради
  побочного эффекта — регистрации таблиц в `BaseSQLModel.metadata` — иначе autogenerate их не увидит.
- Команды выполняются из **корня репозитория** через poetry-окружение `apps/api` (там установлен
  `alembic`+`asyncpg`; свой отдельный `pyproject.toml` для alembic не заводили):

```
poetry -C apps/api run alembic revision --autogenerate -m "message"
poetry -C apps/api run alembic upgrade head
poetry -C apps/api run alembic downgrade -1
```

  Если появится второй app со своей БД — у него будет свой `PostgresConfig`/своя `DSN`, но
  таблицы/модели физически разных БД всё равно не должны пересекаться в одном `target_metadata`
  — тогда этот alembic-каталог нужно будет либо параметризовать (`-x db=...`), либо завести второй,
  решать по факту, когда появится второй app с БД.

- **Автонакатка при старте.** `apps/api/src/migrations.py::upgrade_to_head` (`alembic upgrade head`) вызывается
  из `run_rest_server` синхронно до `uvicorn.run` (`env.py` сам делает `asyncio.run`, из lifespan его вызывать
  нельзя). Ошибка логируется и не валит запуск. При нескольких репликах `apps/api` одновременный старт
  может гонять миграции параллельно — при масштабировании вынести в отдельный шаг деплоя.

- `alembic/versions/589dc8c271ea_initial.py` — первая миграция (`users`, `api_keys`, `memberships`).
  В `downgrade()` после `op.drop_table('users')` явно дропается Postgres ENUM `userrole`
  (`sa.Enum(name='userrole').drop(...)`) — `drop_table` сам его не удаляет, и без этой строки
  следующий `upgrade` падает с `type "userrole" already exists`. Держать это в уме при написании
  будущих миграций, если в модели добавляется/меняется `sqlalchemy.Enum`-колонка.
