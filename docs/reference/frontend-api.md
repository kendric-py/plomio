# API — справочник для фронтенда

Полный контракт REST API (`/api/*`): все ручки, все поля тел запросов/ответов, query-параметры,
коды ошибок и неочевидные тонкости поведения, нужные для интеграции UI.

Базовый префикс всех ручек — `/api`. WebSocket/SSE-эндпоинтов в проекте нет — только обычный REST.

## Оглавление

1. Авторизация
2. Общий формат ошибок
3. Конвенция пагинации
4. Важно про регистр значений enum'ов
5. `/api/auth`
6. `/api/user`
7. `/api/tasks` — задачи парсинга
8. `/api/automations` — мониторинг цены
9. `/api/billing` и `/api/admin/billing` — кредиты и тарификация
10. `/api/notifications` — уведомления
11. `/api/worker-health`
12. `/api/sessions`
13. Известные ограничения текущего API

## Авторизация

Все ручки, кроме `GET /api/auth/status`, `POST /api/auth/register`, `POST /api/auth/login`,
`GET /api/sessions/pool` и ручек приёма heartbeat (`POST /api/worker-health/{parser,sessions}/heartbeat`
— их дёргают воркеры, не фронт), требуют заголовок:

```
Authorization: Bearer <access_token>
```

Токен выдаётся `POST /api/auth/login` или `POST /api/auth/register`.

**Разное поведение при отсутствии и при невалидности токена**:

| Ситуация | Код | Тело |
|---|---|---|
| Заголовок `Authorization` вообще отсутствует | `403` | `{"detail": "Not authenticated"}` (стандартное поведение FastAPI `HTTPBearer`) |
| Токен есть, но невалиден/просрочен | `401` | `{"detail": "Invalid or expired token"}` |
| Токен валиден, но пользователь уже не существует | `401` | `{"detail": "User not found"}` |

**Роли.** Есть две роли — `client` и `admin` (`UserRole`, нижний регистр в JSON). Первый
зарегистрированный в пустой системе (`GET /api/auth/status` вернул `has_users: false`) автоматически
получает роль `admin`, все последующие — `client`. Роль видна в `GET /api/user/me`. Ручки под
`/api/admin/billing/*` требуют роль `admin` — иначе `403 {"detail": "Admin access required"}`.
Остальные ручки ролей не различают.

CORS настроен максимально открыто (`allow_origins=['*']`, `allow_methods=['*']`, `allow_headers=['*']`),
`allow_credentials` не выставлен (по умолчанию `False`) — авторизация только через заголовок
`Authorization`, на cookies полагаться нельзя.

## Общий формат ошибок

- `404` / `409` / `401` / `403` / `402` — всегда `{"detail": "<строка>"}`.
- `422` — в двух разных формах:
  - Стандартная ошибка валидации тела/query FastAPI: `{"detail": [{"type": "...", "loc": [...], "msg": "...", ...}]}`, по одному элементу на каждое невалидное поле.
  - Доменная ошибка (например, слишком маленький `check_frequency_minutes`, неизвестный `event_code` в настройках уведомлений) — та же форма `{"detail": "<строка>"}`, что у остальных кодов, несмотря на код `422`. Различать по форме `detail` (строка vs список).

Владение ресурсом (задача/автоматизация чужая или не существует) везде даёт один и тот же `404` —
намеренно, чтобы перебором id нельзя было узнать о существовании чужих ресурсов.

## Конвенция пагинации

Все постраничные ответы (`GET /api/tasks/`, `GET /api/tasks/{id}/results`, `GET /api/automations/`,
`GET /api/automations/with-history`, `GET /api/automations/{id}/history`,
`GET /api/billing/transactions/by-reference`, `GET /api/notifications/deliveries`) имеют одну и ту же форму:

```json
{ "items": [ /* ... */ ], "meta": { "total": 0, "limit": 100, "offset": 0 } }
```

`meta` — всегда последнее поле, состоит из `total` (int, общее количество), `limit` (int, размер
страницы), `offset` (int, смещение). Query-параметры везде одинаковые: `limit` (1..500, по умолчанию
100), `offset` (≥0, по умолчанию 0).

Есть и **непагинированные** списки — просто `{"items": [...]}` (или своё поле-контейнер) без `meta`:
`GET /api/admin/billing/actions`, `GET /api/admin/billing/pricing-rules`,
`GET /api/notifications/events`, `GET /api/worker-health/workers` (поле называется `workers`),
`GET /api/sessions/pool` (поле называется `marketplaces`).

## Фильтр по датам

Опциональный общий фильтр, подключён не ко всем ручкам — сейчас `GET /api/tasks/`, `GET /api/automations/` и
`GET /api/automations/with-history`. Query-параметры
`date_from` и `date_to` (ISO8601, оба необязательны, можно указать один). Границы включительные;
значение без часового пояса трактуется как UTC, с поясом — приводится к UTC. `date_from` позже
`date_to` → `422`. Какое именно поле времени фильтруется, определяет ручка (указано в её описании).
`meta.total` считается с учётом фильтра.

## Важно про регистр значений enum'ов

`marketplace` в JSON — **нижний регистр** (`"ozon"`, `"wildberries"`), `role` пользователя —
**нижний регистр** (`"client"`, `"admin"`). Все остальные enum'ы (`parse_type`, статус
задачи/автоматизации, статус элемента, `worker_type`, отслеживаемое поле, статус доставки
уведомления, канал уведомления) — **верхний регистр** (`"SEARCH_QUERY"`, `"RUNNING"`, `"PARSER"`,
`"PRICE"`, `"SENT"`, `"TELEGRAM"`). Это не опечатка и не единообразно специально — так исторически
определены значения в `core.enums.Marketplace`/`packages.user.src.enums.UserRole` против enum'ов
остальных пакетов. При сравнении на фронте регистр важен буквально.

---

## `/api/auth`

Не требует авторизации ни на одной из трёх ручек.

### `GET /api/auth/status` — есть ли уже зарегистрированные пользователи

Фронт вызывает её перед показом экрана логина, чтобы решить: показать логин или экран "зарегистрируйте
администратора".

**Ответ `200`**:

| Поле | Тип | Описание |
|---|---|---|
| `has_users` | bool | есть ли хотя бы один зарегистрированный пользователь |

### `POST /api/auth/register` — регистрация

**Тело запроса**:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `email` | string | да | email пользователя, используется и как `display_name` |
| `password` | string, ≥8 символов | да | пароль в открытом виде (хешируется на бэкенде) |

**Первый зарегистрированный в пустой системе (когда `has_users == false`) автоматически получает
роль `admin`**, все последующие — `client`. Роль в ответе регистрации не видна (эта ручка отдаёт
только токен) — узнать роль можно отдельным вызовом `GET /api/user/me` после логина.

**Ответ `201`** (`TokenResponse`):

| Поле | Тип | Описание |
|---|---|---|
| `access_token` | string | JWT access-токен |
| `token_type` | string | всегда `"bearer"` |

`409` — пользователь с таким `email` уже существует (`{"detail": "User with this email already exists"}`).

### `POST /api/auth/login` — вход

**Тело запроса**:

| Поле | Тип | Обязательное |
|---|---|---|
| `email` | string | да |
| `password` | string | да |

**Ответ `200`** — тот же `TokenResponse`, что у `register`.

`401` — неверный email или пароль (`{"detail": "Invalid email or password"}`) — намеренно один и
тот же ответ для "нет такого email" и "неверный пароль".

---

## `/api/user`

### `GET /api/user/` — заглушка

Не требует авторизации. Возвращает нетипизированный `{"message": "Hello World"}`. Не имеет отношения
к профилю, для UI пользы не несёт.

### `GET /api/user/me` — профиль текущего пользователя

Требует авторизации.

**Ответ `200`** (`UserResponse`):

| Поле | Тип | Описание |
|---|---|---|
| `id` | int | идентификатор пользователя |
| `display_name` | string | отображаемое имя (сейчас всегда совпадает с `email`) |
| `email` | string | email |
| `role` | enum | `client` \| `admin` (нижний регистр) |
| `telegram_id` | int \| null | Telegram ID; `null` — пока не привязан. Привязка — через `POST /api/notifications/telegram/link` (см. раздел `/api/notifications`), не через эту ручку — `PATCH`/`PUT` на `telegram_id` напрямую не существует |
| `last_active_at` | datetime | время последней активности |
| `created_at` | datetime | время создания аккаунта |

---

## `/api/tasks` — задачи парсинга

Все ручки требуют авторизации и владелец-only (`404` на чужой/несуществующий `task_id`, без различия
"не найдена" / "принадлежит другому").

### `parse_type` и смысл `input_value`

Каждый вход задачи (`inputs[i]` при создании) интерпретируется по-разному в зависимости от
`parse_type` — валидации формата на бэкенде нет, невалидная ссылка просто провалит соответствующий
элемент задачи:

| `parse_type` | Что кладётся в `input_value` | Форма `payload` результатов |
|---|---|---|
| `PRODUCT_PAGE` | Ссылка на карточку товара | Одна строка `ProductPagePayload` на вход (без пагинации) |
| `SEARCH_QUERY` | Текст поискового запроса (не URL) | Постранично `ProductPayload` — элементы выдачи |
| `CATEGORY` | Ссылка на страницу категории | Постранично `ProductPayload` |
| `SELLER` | Ссылка на витрину продавца | Постранично `ProductPayload` + ровно одна строка `SellerProfilePayload` |
| `REVIEWS` | Ссылка на карточку товара (отзывы этого товара) | Постранично `ReviewPayload` |

### `status` задачи (`TaskStatus`)

```
QUEUED --[взята воркером]--> RUNNING --[все входы обработаны]--> SUCCEEDED | FAILED
QUEUED --[pause]-----------> PAUSED  --[resume]--> QUEUED
RUNNING -[pause]-----------> PAUSED
QUEUED | PAUSED | RUNNING --[cancel]--> CANCELLED
QUEUED --[не взята до queue_expires_at]--> EXPIRED
```

- `QUEUED` — в очереди, ждёт свободного воркера.
- `RUNNING` — воркер обрабатывает задачу прямо сейчас.
- `PAUSED` — приостановлена пользователем; уже начатые входы доводятся до конца текущей страницы, новые не начинаются.
- `SUCCEEDED` / `FAILED` — терминальные. `FAILED` — хотя бы один вход провалился (`error_reason: "item_failed"`).
- `CANCELLED` — отменена пользователем (терминальный).
- `EXPIRED` — не была взята в работу воркером до истечения `queue_expires_at` (терминальный, `started_at` всегда `null`).

### `status` элемента входа (`TaskItemStatus`)

`PENDING → RUNNING → (SUCCEEDED | FAILED)`, плюс `EXCLUDED`. Виден фронту только в ответе на
создание задачи (см. известные ограничения в конце документа).

### `POST /api/tasks/` — создать задачу

**Тело запроса** (`CreateTaskRequest`):

| Поле | Тип | Обязательное | По умолчанию | Описание |
|---|---|---|---|---|
| `parse_type` | enum `ParseType` | да | — | `PRODUCT_PAGE` \| `SEARCH_QUERY` \| `REVIEWS` \| `CATEGORY` \| `SELLER` |
| `marketplace` | enum `Marketplace` | да | — | `ozon` \| `wildberries` |
| `inputs` | `string[]`, ≥1 элемент | да | — | ссылки/запросы, см. таблицу `parse_type` |
| `priority` | int, 1..10 | нет | `5` | 1 — наивысший приоритет, 10 — наинизший |
| `ttl_seconds` | int, `> 0` | да | — | сколько секунд задача может ждать в очереди, прежде чем станет `EXPIRED` |
| `result_limit` | int \| null | нет | `null` (без лимита) | общий лимит результатов по задаче (сумма по всем входам) |

**Ответ `201`** (`CreateTaskResponse`) — все поля из раздела "Поля задачи" ниже, плюс:

| Поле | Тип | Описание |
|---|---|---|
| `items` | `TaskItemResponse[]` | созданные входы: `id` (UUID), `position` (int), `input_value` (string), `status` (все `PENDING` в момент создания) |

`402` — недостаточно кредитов (`{"detail": "Insufficient credits"}`).

**Единственный момент, когда фронт видит `id` элементов входа** — этот ответ. Никакая другая ручка их
не возвращает.

### `GET /api/tasks/` — список задач пользователя

Query: `limit` (1..500, по умолчанию 100), `offset` (≥0, по умолчанию 0), `status` (query-параметр
называется `status`, опциональный, одно значение `TaskStatus`), `date_from`/`date_to` (опциональный
[фильтр по датам](#фильтр-по-датам); для задач фильтруется `created_at`).

**Ответ `200`** (`TaskListResponse`): `{ "items": [ /* TaskDetailResponse */ ], "meta": { ... } }`.

По умолчанию скрывает проверочные задачи автоматизаций (`automation_id != null`) — их не увидеть
через эту ручку вообще, параметра "показать и их" REST-контракт не выставляет. Сортировка —
по `created_at` по убыванию (сначала новые).

### `GET /api/tasks/{task_id}` — статус и прогресс одной задачи

**Ответ `200`** (`TaskDetailResponse`) — поля задачи + агрегированный прогресс:

| Поле | Тип | Описание |
|---|---|---|
| `total_items` | int | всего входов в задаче |
| `processed_items` | int | входов, доведённых до терминального статуса (`SUCCEEDED`/`FAILED`/`EXCLUDED`) |
| `result_count` | int | суммарно спарсено результатов по всем входам |

Как показывать прогресс: для `PRODUCT_PAGE` — `processed_items / total_items` (общее число входов
известно заранее); для `SEARCH_QUERY` / `CATEGORY` / `SELLER` / `REVIEWS` — растущий `result_count`
(и, если задан `result_limit`, — `result_count / result_limit`), так как общий объём выдачи заранее не
известен.

`404` — задача не найдена или принадлежит другому пользователю (`{"detail": "Task not found"}`).

### `GET /api/tasks/{task_id}/results` — результаты парсинга (постранично)

Query: `limit` (1..500, по умолчанию 100), `offset` (≥0, по умолчанию 0). `404` — как у `GET
/{task_id}`. Сортировка — по `created_at` по возрастанию (сначала самые старые результаты), в отличие
от `GET /api/tasks/` (там — по убыванию).

**Ответ `200`** (`TaskResultsResponse`):

```json
{
  "items": [
    {
      "id": "...",
      "task_item_id": "...",
      "marketplace": "ozon",
      "parse_type": "SEARCH_QUERY",
      "payload": { "...": "..." },
      "created_at": "..."
    }
  ],
  "meta": { "total": 0, "limit": 100, "offset": 0 }
}
```

`payload` — непрозрачный `dict`, форма зависит от `parse_type` конкретной строки результата:

- **`PRODUCT_PAGE` → `ProductPagePayload`**: `external_id` (string), `product_url` (string), `title` (string), `brand` (string, `""` если нет), `vendor_code` (string), `category` (string), `category_root` (string), `seller_name` (string), `discounted_price_kopecks` (int \| null, копейки), `price_kopecks` (int \| null, копейки), `original_price_kopecks` (int \| null, копейки), `rating` (float \| null), `review_count` (int \| null), `in_stock` (bool, по умолчанию `true`), `description` (string), `characteristics` (`{name: string, value: string}[]`), `photo_urls` (`string[]`).
- **`SEARCH_QUERY` / `CATEGORY` / `SELLER` → `ProductPayload`**: `external_id` (string \| null), `title` (string), `product_url` (string), `price_text` (string \| null, цена **текстом как в выдаче**, не копейки), `discount` (string \| null, текст), `stock` (string \| null, текст) — три последних поля не структурированы.
- **`REVIEWS` → `ReviewPayload`**: `external_uuid` (string), `author_name` (string), `published_at` (**int, Unix-время**, не ISO8601 — единственное место в API, где дата не ISO8601), `score` (int), `comment_text` (string), `positive_text` (string), `negative_text` (string), `photo_urls` (`string[]`).
- **`SELLER` (доп. строка) → `SellerProfilePayload`**: `supplier_id` (int), `name` (string \| null), `full_name` (string \| null), `trademark` (string \| null), `inn` (string \| null), `ogrnip` (string \| null), `kpp` (string \| null), `rating` (string \| null), `feedbacks_count` (int \| null), `registration_date` (datetime \| null), `sale_item_quantity` (int \| null), `delivery_duration` (int \| null), `is_premium` (bool \| null), `is_deleted` (bool \| null), `deactivated` (bool \| null), `categories` (`{category_id: int, name: string, parent_name: string|null}[]`), `total_products` (int \| null), `seller_url` (string \| null).

**Для `SELLER` в одном списке `items` вперемешку два разных формата payload** — сами товары продавца
(`ProductPayload`) и ровно одна строка с профилем продавца (`SellerProfilePayload`). Явного
поля-дискриминатора нет — различать на фронте нужно по набору ключей в `payload` (например, наличие
`supplier_id` → профиль продавца; наличие `title`+`product_url` → товар).

### `POST /api/tasks/{task_id}/cancel` — отменить задачу

Без тела запроса. Разрешено из `QUEUED`, `PAUSED`, `RUNNING` (можно отменить уже парсящуюся задачу).
Ответ `200` — `TaskDetailResponse` со статусом `CANCELLED`.

- `404` — не найдена/чужая (`{"detail": "Task not found"}`).
- `409` — задача уже в терминальном статусе (`{"detail": "Task cannot be cancelled in its current status"}`).

**Кооперативность** — статус в ответе становится `CANCELLED` мгновенно, но это не значит, что воркер
уже остановился физически: элементы, уже находящиеся в обработке, доводят до конца текущую страницу
(воркер перепроверяет статус периодически, не после каждой строки). На практике задержка — доли
секунд – единицы секунд; `result_count` в `GET /{task_id}` может продолжить расти ещё чуть-чуть после
отмены.

### `POST /api/tasks/{task_id}/pause` — поставить на паузу

Без тела запроса. Разрешено из `QUEUED`, `RUNNING`. Ответ `200` — `TaskDetailResponse` со статусом
`PAUSED`.

- `404` — как у `cancel`.
- `409` — `{"detail": "Task cannot be paused in its current status"}`.

Та же кооперативность: уже идущие входы доводятся до конца текущей страницы, новые не начинаются.

### `POST /api/tasks/{task_id}/resume` — возобновить

**Тело запроса** (`ResumeTaskRequest`) — обязательное, дефолта нет:

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `ttl_seconds` | int, `> 0` | да | новый срок ожидания в очереди, отсчитывается заново от момента вызова |

Разрешено только из `PAUSED`. Ответ `200` — `TaskDetailResponse` со статусом `QUEUED`.

**Почему `ttl_seconds` обязателен, а не переиспользуется исходный** — исходный дедлайн
(`queue_expires_at`) считался от момента *создания* задачи и почти всегда уже в прошлом к моменту,
когда уже поработавшую задачу поставили на паузу и возобновляют. Без нового значения `resume` формально
пройдёт, но задача может почти сразу перейти в `EXPIRED`.

- `404` — как у `cancel`.
- `402` — недостаточно кредитов (`{"detail": "Insufficient credits"}`).
- `409` — задача не в `PAUSED` (`{"detail": "Task is not paused"}`).

### `DELETE /api/tasks/{task_id}` — удалить задачу

Без тела и без ограничений по статусу (можно удалить в любом статусе, в т.ч. `RUNNING`). Каскадно
удаляются все элементы задачи и их результаты. Если задача была `RUNNING`, воркер узнаёт об этом не
сразу, а при следующей периодической проверке статуса. Ответ — `204 No Content`. `404` — не
найдена/чужая (`{"detail": "Task not found"}`).

### Поля задачи (общие для `CreateTaskResponse` и `TaskDetailResponse`)

Гарантированно одинаковый состав во всех ручках, где отдаётся задача (создание, список, статус,
cancel/pause/resume):

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | публичный идентификатор задачи |
| `parse_type` | enum | см. выше |
| `marketplace` | enum | `ozon` / `wildberries` (нижний регистр) |
| `status` | enum | см. выше |
| `priority` | int | 1 (высший) .. 10 |
| `queue_expires_at` | datetime | дедлайн "взять в работу"; после него `QUEUED`-задача станет `EXPIRED` |
| `result_limit` | int \| null | общий лимит результатов, если задан |
| `error_reason` | string \| null | причина провала задачи целиком (сейчас единственное значение — `"item_failed"`); причина провала конкретного входа фронту не видна |
| `user_id` | int | владелец |
| `automation_id` | UUID \| null | не `null` только у проверочных задач автоматизаций — обычные задачи, созданные фронтом, всегда `null` |
| `pricing_dimension_code` | string \| null | код измерения billing-множителя, применённого к результатам этой задачи (например, `task_priority`) |
| `pricing_dimension_value` | int \| null | значение измерения billing-множителя на момент создания задачи |
| `started_at` | datetime \| null | момент первого захвата воркером; `null`, пока не начата |
| `finished_at` | datetime \| null | момент завершения (успех/провал/отмена); `null`, пока не завершена |
| `created_at` | datetime | |
| `updated_at` | datetime | меняется от любого изменения задачи (в т.ч. служебного heartbeat) — не использовать для определения времени завершения, для этого есть `finished_at` |

Длительность парсинга = `finished_at - started_at` (оба ISO8601, UTC).

---

## `/api/automations` — мониторинг цены

Все ручки требуют авторизации и владелец-only (`404` на чужую/несуществующую автоматизацию).

Автоматизация — периодическая проверка карточки товара: пользователь задаёт ссылку/артикул, порог
падения цены и периодичность, система сама создаёт проверочные `PRODUCT_PAGE`-задачи (скрыты из
`GET /api/tasks/`) и копит изменения восьми отслеживаемых полей карточки в истории. Срабатывание
записывается в историю и в журнал уведомлений (`GET /api/notifications/deliveries`) — реальная
отправка в Telegram теперь тоже происходит (см. раздел `/api/notifications`), но требует, чтобы
пользователь предварительно привязал Telegram и включил канал в настройках.

### `status` (`AutomationStatus`)

`ACTIVE` (проверяется по расписанию) ⇄ `PAUSED` (не проверяется, но не удалена).

### Отслеживаемые поля (`TrackedField`, используется в `changes[].field`)

| Значение | Смысл | Тип `old_value`/`new_value` | Участвует в `threshold_breached` |
|---|---|---|---|
| `PRICE` | цена без скидки, копейки | int | да, относительно `baseline_price_kopecks` |
| `DISCOUNTED_PRICE` | цена со скидкой/по карте, копейки | int | да, относительно `baseline_discounted_price_kopecks` |
| `ORIGINAL_PRICE` | перечёркнутая цена, копейки | int | да, относительно `baseline_original_price_kopecks` |
| `IN_STOCK` | наличие товара | bool | да, только на переходе `false → true` (товар снова в наличии) |
| `TITLE` | название товара | string | нет, только `has_changes` |
| `RATING` | рейтинг товара | float | нет, только `has_changes` |
| `REVIEW_COUNT` | количество отзывов | int | нет, только `has_changes` |
| `SELLER_NAME` | название продавца | string | нет, только `has_changes` |

### `POST /api/automations/` — создать автоматизацию

**Тело запроса** (`CreateAutomationRequest`):

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `marketplace` | enum `Marketplace` | да | `ozon` / `wildberries` |
| `input_value` | string | да | ссылка на карточку товара или артикул |
| `price_drop_threshold_percent` | int, 1..100 | да | порог падения цены от базовой, при котором фиксируется `threshold_breached` |
| `check_frequency_minutes` | int, `> 0` | да | периодичность проверки в минутах; минимум задаёт бэкенд-конфиг |
| `history_retention_days` | int, `> 0` | да | срок хранения истории проверок в днях |

**Ответ `201`** (`AutomationResponse`) — см. раздел "Поля автоматизации" ниже.

- `422` — `check_frequency_minutes` меньше минимально допустимого:
  `{"detail": "check_frequency_minutes must be at least <N>"}`, `N` — текущее значение
  `config.AUTOMATION.MIN_CHECK_FREQUENCY_MINUTES` (по умолчанию **15**); отдельной ручки, чтобы
  запросить актуальное значение с бэкенда, нет — ориентироваться по тексту ошибки или зафиксировать
  константу на фронте, синхронизированную с бэкендом.
- `409` — у пользователя уже есть автоматизация на этот же товар в этом же маркетплейсе, в любом
  статусе (включая `PAUSED`): `{"detail": "An automation for this product already exists"}`.
  Совпадение товара определяется по извлечённому из ссылки артикулу, а если извлечь не удалось — по
  точному совпадению `input_value` (см. поле `article` в ответе).
- `402` — недостаточно кредитов (`{"detail": "Insufficient credits"}`).

### `GET /api/automations/` — список автоматизаций пользователя

Query: `limit` (1..500, по умолчанию 100), `offset` (≥0, по умолчанию 0) и опциональные фильтры
(комбинируются через AND):

- `status` — `ACTIVE` / `PAUSED`;
- `in_stock` — `true`/`false` (по последней проверке; автоматизации без проверок не попадают в выдачу,
  если фильтр задан);
- `price_from` / `price_to` — текущая цена `price_kopecks` (без скидки), в копейках, границы
  включительные, `price_from > price_to` → `422`; автоматизации без успешной проверки (цена `null`)
  при заданном фильтре не попадают в выдачу;
- `date_from` / `date_to` — [фильтр по датам](#фильтр-по-датам), по `created_at`.

**Ответ `200`** (`AutomationListResponse`): `{ "items": [ /* AutomationResponse */ ], "meta": { ... } }`.

### `GET /api/automations/with-history` — список автоматизаций с последними проверками

Query: `limit`, `offset`, `status`, `in_stock`, `price_from`/`price_to`, `date_from`/`date_to` — те
же, что у `GET /api/automations/`, применяются к списку автоматизаций, не к историям внутри него.

Удобно для дашборда списка автоматизаций, где под каждой карточкой сразу нужен мини-график/индикатор
последних проверок — экономит по отдельному вызову `GET /api/automations/{id}/history` на каждую
автоматизацию страницы.

**Ответ `200`** (`AutomationWithHistoryListResponse`):

```json
{
  "items": [
    {
      "id": "...",
      "marketplace": "ozon",
      "...": "... все поля AutomationResponse ...",
      "recent_checks": [
        {
          "id": 42,
          "succeeded": true,
          "error_message": null,
          "changes": [],
          "has_changes": false,
          "threshold_breached": false,
          "checked_at": "2026-09-24T10:00:00Z",
          "snapshot": {
            "PRICE": 140000,
            "DISCOUNTED_PRICE": 135000,
            "ORIGINAL_PRICE": 150000,
            "IN_STOCK": true,
            "TITLE": "...",
            "RATING": 4.8,
            "REVIEW_COUNT": 120,
            "SELLER_NAME": "..."
          }
        }
      ]
    }
  ],
  "meta": { "total": 0, "limit": 100, "offset": 0 }
}
```

Каждый элемент `items` — все поля `AutomationResponse` (см. раздел "Поля автоматизации" ниже) плюс
`recent_checks`: до **5** последних строк истории этой автоматизации, отсортированные новые сначала.
Если проверок ещё не было — `recent_checks: []`. Это не пагинированный срез истории — просто
последние 5 тиков без `meta`; для полной постраничной истории конкретной автоматизации по-прежнему
нужен отдельный вызов `GET /api/automations/{id}/history`.

**Отличие от элементов `GET /api/automations/{id}/history`** — здесь у каждого тика есть
дополнительное поле `snapshot`: `dict | null`, снимок всех восьми отслеживаемых полей карточки
(`TrackedField` — ключи в верхнем регистре, как в `changes[].field`) на момент этого тика; `null` при
неуспешном тике (`succeeded: false`). В обычном `GET /api/automations/{id}/history` поле `snapshot`
не отдаётся вовсе — только в этом эндпоинте.

### `GET /api/automations/{automation_id}` — одна автоматизация

**Ответ `200`** — `AutomationResponse`. `404` — `{"detail": "Automation not found"}`.

### `PATCH /api/automations/{automation_id}/baseline` — обновить базовую цену вручную

**Тело запроса** (`UpdateBaselineRequest`) — все поля опциональны, передаются только те, что нужно
изменить (частичное обновление):

| Поле | Тип | Описание |
|---|---|---|
| `price_kopecks` | int, `≥0` \| null | новая базовая цена без скидки |
| `discounted_price_kopecks` | int, `≥0` \| null | новая базовая цена со скидкой |
| `original_price_kopecks` | int, `≥0` \| null | новая базовая перечёркнутая цена |

**Зачем это нужно** — базовая цена не "цена на предыдущей проверке", а зафиксированная точка отсчёта:
все последующие сравнения на предмет `threshold_breached` идут именно относительно неё. Ручка
позволяет пользователю осознанно "переустановить" точку отсчёта, не дожидаясь новой проверки.

**Ответ `200`** — `AutomationResponse`. `404` — `{"detail": "Automation not found"}`.

### `POST /api/automations/{automation_id}/pause` — поставить на паузу

Без тела. Проверки прекращаются, автоматизация не удаляется. **Ответ `200`** — `AutomationResponse` со
статусом `PAUSED`. `404` — `{"detail": "Automation not found"}`. Пауза идемпотентна на уровне
контракта — нет отдельного `409` за повторную паузу.

### `POST /api/automations/{automation_id}/resume` — возобновить

Без тела. **Ответ `200`** — `AutomationResponse` со статусом `ACTIVE`. `404` — как у `pause`.

### `DELETE /api/automations/{automation_id}` — удалить автоматизацию

Без тела. Ответ — `204 No Content`. `404` — `{"detail": "Automation not found"}`. Удаляет и саму
автоматизацию, и всю её историю проверок (каскадно).

### `GET /api/automations/{automation_id}/history` — история проверок (постранично)

Query: `limit` (1..500, по умолчанию 100), `offset` (≥0, по умолчанию 0). `404` — как у остальных
ручек уровня автоматизации.

**Ответ `200`** (`AutomationHistoryListResponse`):

```json
{
  "items": [
    {
      "id": 1,
      "succeeded": true,
      "error_message": null,
      "changes": [
        { "field": "PRICE", "old_value": 150000, "new_value": 140000, "threshold_breached": true }
      ],
      "has_changes": true,
      "threshold_breached": true,
      "checked_at": "2026-09-20T10:00:00Z"
    }
  ],
  "meta": { "total": 0, "limit": 100, "offset": 0 }
}
```

**Одна строка истории = один тик проверки**, а не одно изменившееся поле, и пишется **на каждый тик,
включая неуспешные** (не только успешные с изменениями):

| Поле | Тип | Описание |
|---|---|---|
| `id` | int | идентификатор строки лога (автоинкремент, не UUID) |
| `succeeded` | bool | проверка завершилась успешно |
| `error_message` | string \| null | причина провала проверки (например, `"check_task_failed"`, `"check_task_expired"`, `"check_task_cancelled"`, `"check_task_no_result"`); `null` при успехе |
| `changes` | `TrackedFieldChangeItem[]` | поля, изменившиеся относительно **предыдущего успешного** тика; при провале — всегда пустой список |
| `has_changes` | bool | `bool(changes)` — хотя бы одно поле изменилось относительно предыдущего тика |
| `threshold_breached` | bool | агрегат: хотя бы один элемент `changes` пробил порог (падение цены относительно baseline, либо `IN_STOCK` вернулся в `true`) |
| `checked_at` | datetime | момент проверки |

`TrackedFieldChangeItem`: `field` (enum `TrackedField`), `old_value` / `new_value` (`int | bool |
string | float | null`, тип зависит от `field`), `threshold_breached` (bool, на уровне конкретного
изменения).

В историю пишется любое изменение поля между тиками (не только просадка ниже порога) — под графики;
`threshold_breached` — отдельный флаг, удобен для фильтрации "показать только события, где что-то
сработало", без разбора содержимого `changes` на фронте.

### Поля автоматизации (`AutomationResponse`)

| Поле | Тип | Описание |
|---|---|---|
| `id` | UUID | идентификатор автоматизации |
| `marketplace` | enum | `ozon` / `wildberries` |
| `input_value` | string | ссылка/артикул, как ввёл пользователь |
| `article` | string \| null | артикул, извлечённый из `input_value` бэкендом; `null` — формат не распознан (тогда дедупликация идёт по точному совпадению `input_value`) |
| `status` | enum | `ACTIVE` / `PAUSED` |
| `price_drop_threshold_percent` | int | 1..100 |
| `check_frequency_minutes` | int | периодичность проверки, заданная пользователем |
| `history_retention_days` | int | срок хранения истории |
| `baseline_price_kopecks` | int \| null | базовая цена без скидки; `null` — ещё ни одной успешной проверки не было |
| `baseline_discounted_price_kopecks` | int \| null | базовая цена со скидкой |
| `baseline_original_price_kopecks` | int \| null | базовая перечёркнутая цена |
| `in_stock` | bool \| null | наличие по последней завершённой проверке; `null` — проверок ещё не было |
| `name` | string \| null | название товара по последней успешной проверке; `null` — успешных проверок ещё не было |
| `price_kopecks` | int \| null | текущая цена без скидки (последняя успешная проверка, перезаписывается каждым тиком) |
| `discounted_price_kopecks` | int \| null | текущая цена со скидкой |
| `original_price_kopecks` | int \| null | текущая перечёркнутая цена |
| `next_check_at` | datetime | момент следующей плановой проверки |
| `last_checked_at` | datetime \| null | момент последней завершённой проверки (успешной или нет) |
| `last_check_error` | string \| null | причина провала последней проверки, если она провалилась; при успехе — `null` |
| `created_at` | datetime | время создания автоматизации |

**Ускоренные проверки при отсутствии товара в наличии.** Пока `in_stock == false`, следующая проверка
планируется чаще, чем раз в `check_frequency_minutes` (используется отдельная, не настраиваемая
пользователем частота на бэкенде) — чтобы быстрее поймать момент появления товара. Не удивляться, если
`next_check_at` "чаще, чем должно быть" при разобранном товаре — это ожидаемое поведение.

**Ошибка проверки не переводит автоматизацию в какой-либо "ошибочный" статус** — `status` остаётся
`ACTIVE`, ошибка видна только в `last_check_error`, следующая проверка всё равно случится по
расписанию (у периодической задачи упавшая проверка — не провал самой задачи).

---

## `/api/billing` и `/api/admin/billing` — кредиты и тарификация

Тарифов/подписок нет — единая credit-based тарификация: у каждого пользователя баланс кредитов.
`/api/billing/*` — для владельца (свой баланс/история), `/api/admin/billing/*` — только для роли
`admin` (управление каталогом тарифицируемых действий и правилами множителей, ручная выдача кредитов).

### `GET /api/billing/balance` — текущий баланс

Требует авторизации.

**Ответ `200`** (`BalanceResponse`): `{ "balance": 0 }` (`balance`: int, текущий баланс кредитов
пользователя).

### `GET /api/billing/transactions/by-reference` — траты, сгруппированные по источнику (постранично)

Требует авторизации. Query: `limit` (1..500, по умолчанию 100), `offset` (≥0, по умолчанию 0).
Группировка — по паре `reference_type` + `reference_id`; строки без источника (ручное начисление
админом) в выдачу не входят. Порядок — по `last_at` (новые сверху). Плоского списка транзакций нет.

**Ответ `200`** (`CreditTransactionGroupListResponse`): `{ "items": [ /* CreditTransactionGroupResponse */ ], "meta": { ... } }`.

`CreditTransactionGroupResponse`:

| Поле | Тип | Описание |
|---|---|---|
| `reference_type` | enum | `task` \| `automation` \| `direct` (нижний регистр) — тип сущности, породившей списания |
| `reference_id` | string | идентификатор сущности-источника (id задачи/автоматизации, `request_id` direct-запроса) |
| `total_amount` | int | сумма транзакций группы; списания — отрицательные |
| `transactions_count` | int | число транзакций в группе |
| `first_at` | datetime | время первой транзакции группы |
| `last_at` | datetime | время последней транзакции группы |

### `GET /api/admin/billing/actions` — каталог тарифицируемых действий

Требует роль `admin`. Без query-параметров.

**Ответ `200`** (`BillingActionListResponse`, без `meta`): `{ "items": [ /* BillingActionResponse */ ] }`.

`BillingActionResponse`: `id` (int), `action_code` (string), `description` (string), `base_cost` (int,
базовая цена за единицу в кредитах; `0` — действие бесплатно), `unit_label` (string, что считается
единицей действия).

### `PATCH /api/admin/billing/actions/{action_code}` — изменить базовую стоимость действия

Требует роль `admin`. Path-параметр `action_code` (string).

**Тело запроса** (`UpdateActionCostRequest`): `base_cost` (int, `≥0`, обязательное).

**Ответ `200`** — `BillingActionResponse`. `404` — `{"detail": "Billing action not found"}`.

### `GET /api/admin/billing/pricing-rules` — правила множителей стоимости

Требует роль `admin`. Query: `dimension_code` (string \| null, опциональный фильтр по коду измерения,
например `task_priority` или `automation_check_frequency`).

**Ответ `200`** (`PricingMultiplierRuleListResponse`, без `meta`): `{ "items": [ /* PricingMultiplierRuleResponse */ ] }`.

`PricingMultiplierRuleResponse`: `id` (int), `dimension_code` (string), `value_min` (int, нижняя
граница диапазона включительно), `value_max` (int, верхняя граница диапазона включительно),
`multiplier` (Decimal — на что умножается базовая цена в этом диапазоне значения измерения).

### `POST /api/admin/billing/pricing-rules` — создать правило множителя

Требует роль `admin`.

**Тело запроса** (`CreatePricingRuleRequest`): `dimension_code` (string, обязательное), `value_min`
(int, обязательное), `value_max` (int, обязательное), `multiplier` (Decimal, `> 0`, обязательное).

**Ответ `201`** — `PricingMultiplierRuleResponse`. `409` — диапазон пересекается с уже существующим
правилом для этого `dimension_code`: `{"detail": "Pricing rule range overlaps an existing rule for this dimension_code"}`.

### `DELETE /api/admin/billing/pricing-rules/{rule_id}` — удалить правило

Требует роль `admin`. Path-параметр `rule_id` (int). Ответ — `204 No Content`. `404` —
`{"detail": "Pricing rule not found"}`.

### `POST /api/admin/billing/users/{user_id}/grant` — выдать кредиты вручную

Требует роль `admin`. Path-параметр `user_id` (int).

**Тело запроса** (`GrantCreditsRequest`): `amount` (int, `> 0`, обязательное — сколько кредитов
начислить), `comment` (string \| null, опциональный комментарий администратора).

**Ответ `201`** — `CreditTransactionResponse` (`amount` положительный, `action_code: null`).

---

## `/api/notifications` — уведомления

Все ручки требуют авторизации, владелец-only, без отдельного admin-роутера — настройки полностью
принадлежат пользователю. Домен провайдер-агностичный и не привязан к конкретному типу задачи: любое
событие (изменение карточки товара, завершение задачи) фиксируется здесь по общим правилам подписки
пользователя, и затем реально отправляется в Telegram периодическим фоновым процессом (не мгновенно —
см. `status` в `GET /api/notifications/deliveries`). Для получения уведомлений в Telegram
пользователю нужно: 1) привязать Telegram (`POST /api/notifications/telegram/link`, см. ниже),
2) включить нужные события/каналы в `PUT /api/notifications/preferences`.

### Каталог типов событий (сиды, `event_code` — первичный ключ)

| `event_code` | Когда создаётся | `available_fields` (фильтр подписки `fields`) | `payload` в `GET /api/notifications/deliveries` |
|---|---|---|---|
| `automation.change_detected` | тик проверки автоматизации дал `has_changes` или `threshold_breached` | все восемь значений `TrackedField` (`PRICE`, `DISCOUNTED_PRICE`, `ORIGINAL_PRICE`, `IN_STOCK`, `TITLE`, `RATING`, `REVIEW_COUNT`, `SELLER_NAME`) | см. ниже |
| `task.completed` | обычная (не проверочная) задача пользователя завершилась успехом | `null` (у задач нет понятия "поле") | `{"task_id": ..., "error_reason": null}` |
| `task.failed` | обычная задача пользователя завершилась провалом | `null` | `{"task_id": ..., "error_reason": "item_failed"}` |

`payload` события `automation.change_detected`:

```json
{
  "automation_id": "...",
  "product_name": "Наушники XYZ",
  "link": "https://www.ozon.ru/product/...",
  "changes": [{ "field": "DISCOUNTED_PRICE", "old_value": 150000, "new_value": 140000, "threshold_breached": true }],
  "changes_text": "DISCOUNTED_PRICE: 1 500,00 ₽ → 1 400,00 ₽",
  "threshold_breached": true,
  "price_old": 160000, "price_new": 160000,
  "discounted_price_old": 150000, "discounted_price_new": 140000,
  "original_price_old": 170000, "original_price_new": 170000,
  "in_stock_old": true, "in_stock_new": true,
  "title_old": "Наушники XYZ", "title_new": "Наушники XYZ",
  "rating_old": 4.5, "rating_new": 4.5,
  "review_count_old": 120, "review_count_new": 120,
  "seller_name_old": "ACME", "seller_name_new": "ACME"
}
```

`{field}_old`/`{field}_new` присутствуют **всегда**, для всех восьми полей, даже если сработавшее
изменение затронуло только одно из них (`_old` — значение на предыдущей успешной проверке, `null`
на самом первом успешном тике автоматизации; `_new` — значение на этой проверке). **Цены в
`payload` — в копейках, как и везде в API** (`price_old`/`price_new`/`discounted_price_old`/...),
без конвертации; но при подстановке в `template` (см. ниже) или в `changes_text` они уже
показываются в рублях (`"1 500,00 ₽"`, не `"150000"`) — конвертация происходит на бэкенде при
рендере текста для Telegram, а не в самом `payload`. `changes_text` — уже готовая многострочная
строка вида `"PRICE: 1 500,00 ₽ → 1 400,00 ₽\nRATING: 4.5 → 4.8"` (цены — в рублях, остальные поля
— как есть), по одной строке на реально изменившееся поле (сырой `changes` для подстановки прямо в
текстовый шаблон не годится — это структура, не текст, см. `template` ниже).

Проверочные задачи автоматизаций (`Task.automation_id != null`) не порождают отдельных `task.*`
событий — их завершение уже покрыто `automation.change_detected` того же тика, чтобы не дублировать
уведомление.

### `NotificationChannel` / `NotificationDeliveryStatus`

- `NotificationChannel` — сейчас единственное значение `TELEGRAM`.
- `NotificationDeliveryStatus` — `PENDING` (создана, ждёт отправки) → `SENT` (успешно отправлена,
  `sent_at` заполнен) \| `FAILED` (отправка не удалась, `failure_reason` заполнен — например,
  `"telegram_id не привязан"`, если пользователь включил канал `TELEGRAM`, но так и не привязал
  Telegram). Отправка происходит периодическим фоновым процессом с задержкой в несколько секунд
  после создания записи — не мгновенно и не в рамках HTTP-запроса, породившего событие. **Одна
  попытка на доставку** — `FAILED`-запись не переигрывается повторно (retry/backoff не реализован в
  этой итерации). Текст сообщения (в т.ч. `template`, если задан) рендерится на момент фактической
  отправки, а не на момент постановки в очередь — если пользователь поменяет `template` через
  `PUT /preferences`, пока доставка ещё `PENDING`, отправится уже новый текст.

### `GET /api/notifications/events` — каталог активных типов событий

Требует авторизации. Без query-параметров.

**Ответ `200`** (`NotificationEventListResponse`, без `meta`): `{ "items": [ /* NotificationEventResponse */ ] }`.

`NotificationEventResponse`: `event_code` (string), `description` (string, для UI), `available_fields`
(`string[] | null` — поля, по которым можно фильтровать подписку через `fields`; `null`/пусто — у
события нет понятия "поле"), `template_variables` (`dict[string, TemplateVariableResponse] | null`
— карта `{переменная: {field, description, is_money}}`, допустимые `{переменные}` в
пользовательском шаблоне этого события, см. `template` ниже; `null`/пусто целиком — у события нет
переменных). `TemplateVariableResponse`: `field` (string \| null — непусто означает, что
использование этой переменной в шаблоне подписывает уведомление именно на изменения этого поля, см.
"Фильтрация по переменным шаблона" под `template` ниже; `null` — переменная контекстная, ни на что
не подписывает), `description` (string — человекочитаемое объяснение для UI, что именно переменная
показывает; **это готовый текст подсказки, показывать его пользователю рядом с полем ввода
шаблона, не выдумывать свой**), `is_money` (bool — `true` значит, что в `payload` эта переменная —
копейки, но в самом отправленном сообщении она уже подставится как рубли, например `"1 500,00 ₽"`;
незачем показывать пользователю "копейки" в подсказке для такой переменной — он увидит и введёт её
именно как цену). Например, для `automation.change_detected`:

```json
{
  "product_name": { "field": null, "description": "Название товара на момент этой проверки", "is_money": false },
  "link": { "field": null, "description": "Ссылка на карточку товара", "is_money": false },
  "discounted_price_old": {
    "field": "DISCOUNTED_PRICE",
    "description": "Цена со скидкой на предыдущей успешной проверке",
    "is_money": true
  },
  "discounted_price_new": {
    "field": "DISCOUNTED_PRICE",
    "description": "Цена со скидкой на этой проверке",
    "is_money": true
  }
}
```

(полный список переменных `automation.change_detected` — в таблице `payload` события выше: то же
множество ключей, только там значения — пример данных, а здесь — метаданные для формы настройки).

Возвращает нужный набор для построения формы настроек без хардкода списка событий на клиенте — в
т.ч. подсказку "доступные переменные" (`description` каждой) рядом с полем ввода шаблона.

### `GET /api/notifications/preferences` — текущие настройки пользователя

Требует авторизации.

**Ответ `200`** (`NotificationPreferencesResponse`):

```json
{
  "preferences": {
    "automation.change_detected": {
      "channels": ["TELEGRAM"],
      "fields": null,
      "template": "{product_name}\n\nЦена была: {discounted_price_old}\nЦена стала: {discounted_price_new}\n\nСсылка на товар: {link}"
    },
    "task.failed": { "channels": ["TELEGRAM"], "fields": null, "template": null }
  },
  "updated_at": "2026-09-20T10:00:00Z"
}
```

`preferences` — карта `{event_code: {channels, fields, template}}`. У нового пользователя карта
пустая — это безопасный дефолт: без явной настройки уведомления по любому событию выключены.
`template: null` — используется встроенный текст сообщения по умолчанию (см. таблицу каталога
событий выше за примером готового текста для каждого `event_code`).

### `PUT /api/notifications/preferences` — полностью заменить настройки

Требует авторизации. **Полная замена карты** (не merge) — отправлять нужно весь желаемый набор
`event_code` → настройка, отсутствие ключа в теле означает "уведомления по этому событию выключены".

**Тело запроса** (`UpdatePreferencesRequest`):

| Поле | Тип | Обязательное | Описание |
|---|---|---|---|
| `preferences` | `dict[string, NotificationEventPreferenceItem]` | да | карта `{event_code: {channels, fields, template}}` |

`NotificationEventPreferenceItem`: `channels` (`NotificationChannel[]`, обязательное — пустой список
= выключено для этого события), `fields` (`string[] | null`, опционально — подмножество
`available_fields` события; `null`/пусто = уведомлять по любому срабатыванию, непустой список =
только если оно затронуло хотя бы одно из перечисленных полей — **игнорируется, если задан
`template`**, см. ниже), `template` (string \| null, опционально — свой текст сообщения; синтаксис
`{name}` — подставляется значение переменной из `payload`, никаких `{name.attr}`/`{name[0]}`/
`{name!r}`/форматирования, только плоская подстановка; допустимые имена — ключи `template_variables`
этого события из `GET /api/notifications/events`; `null` = использовать встроенный текст по
умолчанию).

**Сообщения в Telegram отправляются с `parse_mode=HTML` (всегда, не настраивается).** Это значит,
что **в тексте шаблона можно использовать HTML-теги Telegram** — `<b>жирный</b>`,
`<i>курсив</i>`, `<a href="URL">текст ссылки</a>`, `<code>моноширинный</code>` и т.д. (полный
список — [HTML-style в документации Bot API](https://core.telegram.org/bots/api#html-style)).
Теги пишутся прямо в тексте шаблона, вокруг `{переменных}` или отдельно:
`"<b>{product_name}</b>\nЦена: {discounted_price_new}"`. **Подставляемые значения переменных
экранируются автоматически** — если название товара содержит символы `<`, `>` или `&`, они
превратятся в тексте сообщения в `&lt;`/`&gt;`/`&amp;` и останутся видимым текстом, а не будут
считаны как разметка; специально экранировать значения самостоятельно не нужно и не даст эффекта
(экранирование бэкенд делает после подстановки, до отправки). Если в HTML-разметке шаблона
допущена ошибка (например, незакрытый тег) — Telegram Bot API отклонит сообщение, и доставка
получит `status: FAILED` с текстом ошибки парсинга в `failure_reason`.

**Если `template` задан, он определяет и фильтр постановки в очередь — `fields` в этом случае не
учитывается вовсе.** Эффективный фильтр — поля, на которые ссылаются реально использованные в
шаблоне переменные (по карте `template_variables` события): доставка создаётся, только если
сработавшее изменение затронуло хотя бы одно из них. Если ни одна использованная переменная не
привязана к полю (например, шаблон использует только `{product_name}`/`{link}`) — фильтра нет
вообще, уведомление приходит на любое срабатывание события, как и при `fields: null`. Пример: у
события `automation.change_detected` шаблон `"{product_name}\n\nЦена была: {discounted_price_old}\n
Цена стала: {discounted_price_new}"` использует `discounted_price_old`/`discounted_price_new`
(→ `DISCOUNTED_PRICE`) и `product_name` (не привязан к полю) — уведомление придёт только когда
сработавшее изменение включает `DISCOUNTED_PRICE`, даже если в `fields` этого же `preference`
исторически осталось что-то другое (например `["RATING"]`, если такое значение задавали раньше) —
оно в этом случае не используется.

**Ответ `200`** — `NotificationPreferencesResponse` (новое актуальное состояние).

- `422` — неизвестный или неактивный `event_code` в карте: `{"detail": "Unknown or inactive event_code in preferences"}`.
- `422` — `fields` содержит значение вне `available_fields` этого события (или `fields` задан у
  события без `available_fields`): `{"detail": "fields must be a subset of the event's available_fields"}`.
- `422` — `template` использует `{переменную}`, не входящую в ключи `template_variables` этого
  события: `{"detail": "template variables must be a subset of the event's template_variables"}`.
  Валидация — только по **именам** переменных, извлечённым из `{name}`, не по остальному тексту:
  одиночная `{` без закрывающей или `{` перед не-идентификатором не считается переменной и не
  отклоняется на сохранении — просто останется как есть в итоговом тексте при отправке.

### `GET /api/notifications/deliveries` — журнал поставленных в очередь уведомлений (постранично)

Требует авторизации. Read-only — записи создаёт только домен (при срабатывании события), не
пользователь. Query: `limit` (1..500, по умолчанию 100), `offset` (≥0, по умолчанию 0).

**Ответ `200`** (`NotificationDeliveryListResponse`): `{ "items": [ /* NotificationDeliveryResponse */ ], "meta": { ... } }`.

`NotificationDeliveryResponse`: `id` (int), `event_code` (string), `channel` (enum
`NotificationChannel`), `status` (enum `NotificationDeliveryStatus`), `payload` (dict, см. таблицу
каталога событий выше), `failure_reason` (string \| null, заполнен только при `status: FAILED`),
`sent_at` (datetime \| null, заполнен только при `status: SENT`), `created_at` (datetime, момент
постановки в очередь).

### `POST /api/notifications/telegram/link` — сгенерировать ссылку для привязки Telegram

Требует авторизации. Без тела запроса.

**Ответ `200`** (`CreateTelegramLinkResponse`):

| Поле | Тип | Описание |
|---|---|---|
| `deep_link` | string | `https://t.me/<bot>?start=<code>` — открыть в браузере/приложении, ведёт прямо в чат с ботом |
| `expires_in_seconds` | int | через сколько секунд код станет недействителен (по умолчанию 600) |

**Флоу для UI**: показать пользователю кнопку/ссылку `deep_link` (или QR-код с этим URL). После
перехода пользователь нажимает "Start" в Telegram — бот присылает подтверждение прямо в чат
(текстом, не через API). **Отдельной ручки "проверить, привязался ли Telegram" нет** — фронту нужно
поллить `GET /api/user/me` и следить за `telegram_id` (стал не `null`), либо просто попросить
пользователя обновить страницу после подтверждения в Telegram.

Код одноразовый и живёт `expires_in_seconds` — повторный вызов этой ручки выдаёт новый код (старый,
если не был использован, просто протухнет по TTL, отдельно инвалидировать его не нужно). Если код уже
устарел или пользователь кликнул старую ссылку — бот в Telegram ответит текстом об ошибке, HTTP здесь
ни при чём (сама привязка происходит не через REST-запрос от фронта, а через сообщение боту).

**Важно:** если этот Telegram-аккаунт уже привязан к **другому** пользователю SMPCrawl — бот в
Telegram сообщит об этом и ничего не изменит; текущая привязка (если есть) не будет пересоздана.

---

## `/api/worker-health`

Инфраструктурный мониторинг воркеров-парсеров — полезен для админ-панели/дашборда состояния системы,
не для клиентского UI постановки задач.

### `POST /api/worker-health/parser/heartbeat`, `POST /api/worker-health/sessions/heartbeat`

**Не для фронтенда** — эти ручки дёргают сами воркеры, не UI. **Не требуют авторизации** —
аутентификация воркеров (API-ключи) ещё не реализована, ручки открытые.

**Тело запроса** (`HeartbeatRequest`, одинаковое для обеих ручек):

| Поле | Тип | Описание |
|---|---|---|
| `worker_name` | string | имя инстанса воркера |
| `status` | string | текущий статус воркера (например `READY`/`WORKING`), свободная строка, не enum |

**Ответ `200`** (`HeartbeatResponse`): `{"accepted": true}`.

### `GET /api/worker-health/workers` — текущий статус всех воркеров

Требует авторизации. Читает состояние напрямую из Redis (без БД) — снепшот "сейчас", без истории.

**Ответ `200`** (`WorkerStatusResponse`, без `meta`): `{ "workers": [ /* WorkerStatusItem */ ] }`.

Список отсортирован по (`worker_type`, `worker_name`). Без пагинации.

`WorkerStatusItem`:

| Поле | Тип | Описание |
|---|---|---|
| `worker_type` | enum | `PARSER` / `SESSIONS` |
| `worker_name` | string | имя инстанса |
| `status` | string \| null | последний присланный воркером статус; `null` — heartbeat получен до появления этого поля |
| `last_seen_at` | datetime | время последнего heartbeat |
| `gap_seconds` | float | сколько секунд прошло с последнего heartbeat — считать "жив ли воркер прямо сейчас" удобнее по этому полю, чем сравнивать `last_seen_at` с текущим временем клиента |
| `is_missed` | bool | воркер считается пропустившим heartbeat |

### `DELETE /api/worker-health/workers/{worker_type}/{worker_name}` — забыть воркер

Требует авторизации. Path-параметры: `worker_type` (enum `PARSER`/`SESSIONS`), `worker_name` (string).
Удаляет запись о воркере из Redis (например, для инстанса, выведенного из эксплуатации). Ответ —
`204 No Content`. `404` — `{"detail": "Worker not found"}`.

---

## `/api/sessions`

Пул сессий (куки, заголовки, прокси) для работы воркеров-парсеров с маркетплейсами. Для клиентского
UI, как и `/api/worker-health`, скорее раздел мониторинга/админки, чем часть флоу постановки задачи.

### `GET /api/sessions/pool` — состояние пула сессий

**Не требует авторизации** (единственная ручка не в `/api/auth`, не требующая токен, кроме
heartbeat-ручек воркеров).

**Ответ `200`** (`SessionPoolResponse`, без `meta`):

```json
{
  "marketplaces": [
    { "marketplace": "ozon", "live_count": 12, "nearest_expires_at": "2026-09-23T12:00:00Z" },
    { "marketplace": "wildberries", "live_count": 0, "nearest_expires_at": null }
  ]
}
```

Всегда возвращает **все** значения `Marketplace` (сейчас `ozon` и `wildberries`), даже если пул пуст.

`MarketplaceSessionPool`: `marketplace` (enum, нижний регистр), `live_count` (int, количество живых —
не просроченных — сессий в пуле прямо сейчас), `nearest_expires_at` (datetime \| null, момент
истечения самой "старой" из живых сессий; `null` — живых сессий нет).

Полезно для дашборда "здоровья" системы: `live_count == 0` — новые задачи по этому маркетплейсу скоро
не смогут начать обрабатываться (воркеру нечем будет запросить сессию).

---

## Известные ограничения текущего API

- **`id` элементов входа задачи видны только в ответе `POST /api/tasks/`** (поле `items`). Никакая
  другая ручка (`GET /{task_id}`, `GET /`) их не возвращает — если фронт не сохранил `items` из ответа
  на создание, узнать `id` конкретного входа позже нельзя. Ручек уровня входа (пауза/исключение одного
  входа) пока не существует.
- **Причина провала конкретного входа не видна фронту.** На уровне задачи `error_reason` — только
  `"item_failed"`, без деталей, какой именно вход и почему.
- **Список задач не показывает проверочные задачи автоматизаций** и не даёт способа их запросить через
  эту ручку.
- **Отмена/пауза задач — не мгновенны по факту, только по статусу.** Планировать UI (спиннеры/дизейбл
  кнопок) с расчётом на секундную задержку.
- **Ретрая неудачной отправки нет** — `status: FAILED` в `GET /api/notifications/deliveries`
  окончательный, повторной попытки не будет (например, если пользователь включил канал `TELEGRAM`, не
  привязав Telegram, — доставка так и останется `FAILED` с этой причиной, пока он не привяжет Telegram
  и не дождётся следующего события).
- **Нет пуш/realtime-уведомлений на фронте** — только Telegram. Строить на фронте "непрочитанные
  уведомления" можно только поллингом `GET /api/notifications/deliveries` или
  `GET /api/automations/{id}/history`.
- **Привязка Telegram — не REST-флоу целиком**: `POST /api/notifications/telegram/link` только
  выдаёт ссылку, само подтверждение происходит в Telegram (сообщением от бота), не отдельным вызовом
  API. Проверить, привязался ли Telegram, можно только по `telegram_id` в `GET /api/user/me`.
  Привязка Telegram сейчас работает через long polling на бэкенде (не webhook) — задержка между
  нажатием "Start" в Telegram и ответом бота обычно доли секунды, но при недоступности бэкенда
  сообщения не выстроятся в очередь и потеряются, а не будут доставлены позже.
- **Квот на количество/частоту задач и автоматизаций по пользователю нет** — только кредитный баланс
  (`GET /api/billing/balance`), любые лимиты сверх него сейчас не выражены в API и не проверяются.
- **`GET /api/worker-health/*` и `GET /api/sessions/pool`** не привязаны к текущему пользователю — это
  общесистемный мониторинг, не персональные данные; в клиентском (не админском) UI обычно не нужны.
- **`GET /api/user/` — заглушка**, не содержит полезных для UI данных; реальный профиль — только
  `GET /api/user/me`.
- **Ролевых ограничений на большинстве ручек нет** — роль `admin` проверяется только для
  `/api/admin/billing/*`; управление сроком хранения результатов периодических задач администратором
  (упомянуто как обязанность администратора) отдельной ручкой не выражено.
