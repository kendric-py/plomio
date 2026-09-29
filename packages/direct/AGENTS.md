# packages/direct

Доменная область **direct-запросов** — синхронных запросов клиента к маркетплейсу:
`клиент → apps/api → apps/worker_parser (WORKER_MODE=direct) → apps/api → клиент`. Время ответа
определяется в основном самим маркетплейсом. Запросы идут **мимо** очереди задач и Postgres и
ничего не сохраняют. Название домена — `direct` (не realtime/lookup).

Пакет держит общий протокол: сущности, енамы, транспорт (`DirectBus`) и подписанный `page_key`.
Логика выполнения — в `apps/worker_parser` (`direct_runner.py`), REST — в
`apps/api/src/routers/direct/`.

## Транспорт — Redis (`redis_bus.py`, класс `DirectBus`)

- **Запрос:** `XADD direct:requests:{marketplace}` (`MAXLEN ~1000`), тело `DirectRequest` в JSON
  в поле `data`. Поля: `request_id`, `request_type` (`product_page`/`reviews`/`search`/`category`/`seller`),
  `marketplace`, `input_value`, `page_cursor` (dict | None), `created_at`, `deadline_at`.
  `created_at`/`deadline_at` — unix-секунды (`float`): осознанное исключение из правила «все даты
  — ISO8601», воркер сравнивает срок с `time.time()` на каждом запросе.
- **Чтение:** воркеры читают `XREADGROUP` группой `direct-workers` с `BLOCK` (без поллинга);
  сообщение сразу `XACK` + `XDEL`. Группа создаётся `ensure_groups` (`id='0'`, `MKSTREAM`).
- **Ответ:** `RPUSH direct:reply:{request_id}` + `EXPIRE 30`, тело `DirectReply`: `request_id`,
  `status`, `payload` (dict | None), `next_cursor` (dict | None), `error`. `apps/api` ждёт `BLPOP`.
- Методы: `enqueue`, `wait_reply`, `publish_reply`, `ensure_groups`, `consume`, `close`.

### At-most-once, без ретраев транспорта

Сообщение снимается со стрима при чтении, поэтому упавший воркер = таймаут у клиента, а не
повторная обработка: у ответа всё равно есть срок годности, а повтор запроса к маркетплейсу для
уже ушедшего клиента — лишняя нагрузка. Просроченные (`deadline_at`) запросы воркер отбрасывает
без ответа (`[direct_expired]`). Ретраи внутри дедлайна (смена сессии) делает сам воркер —
`DIRECT_MAX_ATTEMPTS` (по умолчанию 2 — общее число попыток).

## Статусы ответа (`enums.py::DirectStatus`)

`ok`, `invalid_input`, `not_found`, `unavailable`, `error`. Маппинг из ошибок парсера —
`apps/worker_parser/src/error_classifier.py`: `InputResolutionError` → `invalid_input`;
`RequestError` с 404 → `not_found`; дедлайн/нет сессии → `unavailable`; прочие `ParserError` после
исчерпания попыток и любое неожиданное исключение (`internal error: <тип>`) → `error`.

## Ошибки клиенту — жёсткое правило

Клиенту **ни в коем случае** не отдаются ошибки маркетплейсов, парсера, инфраструктуры, названия
внутренних сущностей и устройство потока (сессии, прокси, блокировки). `DirectReply.error` — только
для логов (воркер: `[direct_failed] request_id marketplace status reason(300 симв.)`; api:
`[direct_api_failed]`/`[direct_api_bad_reply]` со стектрейсом). Фиксированные сообщения
(`apps/api/src/routers/direct/errors.py`):

| Ситуация | HTTP | `detail` |
|---|---|---|
| `invalid_input` (карточка, отзывы) | 422 | `Invalid article` |
| `invalid_input` (поиск) | 422 | `Invalid search query` |
| `invalid_input` (категория) | 422 | `Invalid category url` |
| `invalid_input` (продавец) | 422 | `Invalid seller` |
| `invalid_input` при переданном `page_key` / плохой `page_key` | 422 | `Invalid or expired page key` |
| `not_found` (карточка, отзывы) | 404 | `Product not found` |
| `not_found` (категория) | 404 | `Category not found` |
| `not_found` (продавец) | 404 | `Seller not found` |
| `not_found` (поиск), `unavailable`, `error`, сбой транспорта/разбора ответа | 503 | `Service temporarily unavailable, please try again later` |
| нет ответа за `DIRECT_REQUEST_TIMEOUT_SECONDS` | 504 | `Request timed out, please try again later` |
| баланс кредитов `<= 0` | 402 | `Insufficient credits` |
| сбой проверки/списания кредитов | 503 | `Service temporarily unavailable, please try again later` |

Разные внутренние причины сбоя намеренно сведены к одному 503. Новые статусы/типы запросов обязаны
идти через `errors.py`, а не пробрасывать `reply.error` в `detail`. (Стандартные 422 FastAPI на
валидацию path/query — длина артикула, неизвестный маркетплейс — эхо входных данных клиента, не
внутренности.)

## Типы запросов и курсоры

Курсор — состояние пагинации маркетплейса; на сервере ничего не хранится.

- **`product_page`** — карточка по артикулу. Числовой артикул → URL (WB
  `https://www.wildberries.ru/catalog/{id}/detail.aspx`, Ozon `https://www.ozon.ru/product/{id}/`;
  Ozon принимает путь только с артикулом). Нечисловой ввод, не являющийся ссылкой (и Ozon-ссылка
  без артикула) → `invalid_input`. Курсора нет.
- **`reviews`** — отзывы постранично.
  - **Ozon:** `{product}/reviews/` через `entrypoint-api`, 30 на страницу, один запрос на
    страницу. Курсор — `OzonReviewCursor {marketplace, sort_order, next_params, seen_uuids}`, где
    `next_params` — query-строка следующей страницы из `paging.nextButton` (**с `page_key` Ozon**).
    Курсор `{"page": N}`, как предполагалось изначально, работать не может: без `page_key` Ozon
    глубже ~5-й страницы отдаёт повторы (проверено на живых ответах). Потолок Ozon — около 33
    страниц (~990 отзывов) на сортировку; direct идёт по одной сортировке.
  - **WB:** WB отдаёт все отзывы одним ответом, курсор — `WbReviewCursor {marketplace, offset,
    root_id, feedback_host}`, страница — срез `[offset:offset+DIRECT_REVIEWS_WB_PAGE_SIZE]`. На
    первой странице прогрев, карточка, `root_id` и хост фидбеков; дальше — один запрос.
- **`category`** — товары категории по ссылке на неё (`?url=`); те же фетчеры, что у задач `CATEGORY`.
  Курсор — `OzonPaginationCursor`/`WildberriesPaginationCursor`. У WB категория должна быть в меню
  маркетплейса, иначе `invalid_input`.
- **`seller`** — товары продавца (`?seller=`): числовой id (только Wildberries, → `/seller/{id}`) или ссылка на
  витрину; у Ozon ссылка требует слаг, по одному id её не построить — `invalid_input`. Профиль продавца
  (`SELLER_PROFILE`) в direct не отдаётся, только список товаров.
- **Ссылки** во всех типах (карточка, отзывы, категория, продавец) принимаются только на хосты самого
  маркетплейса (`www.wildberries.ru`/`wildberries.ru`, `www.ozon.ru`/`ozon.ru`): воркер запрашивает их своей
  сессией с куками маркетплейса, чужой хост позволил бы направить эти запросы куда угодно.
- **`search`** — выдача по тексту; те же фетчеры, что у задач `SEARCH_QUERY`; курсор маркетплейса
  (`OzonPaginationCursor`/`WildberriesPaginationCursor`) едет целиком.

Курсор невалиден по форме (`ValidationError` в воркере) → `invalid_input`.

## Конец пагинации — единое правило

Конец выдачи выражается одинаково у отзывов и поиска и на каждой странице:

- Воркер: `DirectReply.next_cursor is None` — конец. Пустая страница (`items=[]`) **всегда** конец,
  даже если маркетплейс отдал ссылку дальше (`direct_runner.build_ok_reply`).
- API: поле `next_page_key` есть в каждом постраничном ответе, на последней странице оно `null` —
  это и есть конец выдачи. Схема — `DirectPageResponse` (`routers/direct/schema.py`), от неё наследуются
  ответы отзывов, поиска, категории и продавца; новый постраничный ответ обязан наследоваться от неё же.
- Последняя страница может быть неполной или пустой — признак конца только `next_page_key = null`, не размер
  страницы. Просроченный/чужой `page_key` — 422, не конец.
- Потолок маркетплейса (Ozon-отзывы ~33 страницы на сортировку) для клиента тоже конец выдачи
  (`next_page_key = null`): отличить его от естественного конца нельзя.

## `page_key` (`page_key.py`)

Пагинация — ответственность клиента. Ответ постраничных ручек содержит `next_page_key` (или
`null`), клиент передаёт его в `?page_key=`.

Формат: `base64url(json{m: marketplace, a: артикул-или-текст-запроса, e: unix-срок, c: курсор}) + "."
+ base64url(HMAC-SHA256)`; секрет — `sha256("direct-page-key:" + AUTH_SECRET_KEY)`
(`derive_page_key_secret`), сравнение — `hmac.compare_digest`. Срок годности —
`DIRECT_PAGE_KEY_TTL_SECONDS` (api, по умолчанию 900). API: `encode_page_key`, `decode_page_key`,
`InvalidPageKeyError`.

Ключ формирует и проверяет **только `apps/api`**; воркер получает курсор (`DirectRequest.page_cursor`)
лишь из проверенного ключа и возвращает сырой `next_cursor`. Клиент не видит внутренностей, не может
подсунуть свой курсор или использовать ключ от другого товара/запроса/маркетплейса. Плохой,
просроченный или чужой ключ → 422 `Invalid or expired page key`.

## Тарификация (`packages/billing`)

Цена — за каждый возвращённый элемент, как у `result.<ParseType>` в задачах. Действия каталога:
`direct.PRODUCT_PAGE`/`REVIEWS`/`SEARCH`/`CATEGORY`/`SELLER` (по имени `DirectRequestType`);
`quantity` = `1` для карточки и `len(items)` для страниц (пустая страница бесплатна). Множителей нет
(`dimension_code=None`). Логика — в `apps/api/src/routers/direct/dependencies.py`
(`require_positive_balance` — `Depends` на весь роутер, `charge_direct_request` — вызывается из
обработчиков после ответа); воркер и протокол `DirectBus` о тарификации не знают.

- **Проверка до запроса:** `has_positive_balance`; баланс `<= 0` → 402 `Insufficient credits`, запрос
  воркеру не уходит.
- **Списание только за успех:** после `reply.status == OK` и успешного разбора `items`. Любая ошибка,
  таймаут, `not_found`, `invalid_input` — бесплатно.
- **Сбой проверки/списания** (например, недоступен Postgres) → 503 фиксированным сообщением, данные не
  отдаются; в лог — `[direct_billing_failed] stage=check|charge`.
- **Журнал:** `reference_type=DIRECT`, `reference_id=request_id` — связь со строками `[direct_api]`.
- Как и в задачах, баланс может уйти в минус (параллельные запросы, страница дороже остатка).
- Миграция `e5b2a8d4f631` сидирует действия: `direct.PRODUCT_PAGE` = 1, остальные = 0 (бесплатны, пока
  админ не выставит цену через `PATCH /api/admin/billing/actions/{action_code}`).

## Наблюдаемость

- Воркер, одна строка на запрос: `[direct_done] request_id marketplace status attempts queue_ms
  session_ms fetch_ms worker_ms since_created_ms` (`queue_ms` — от `created_at` до взятия воркером;
  `session_ms` — получение сессии; `fetch_ms` — запросы к маркетплейсу суммарно по попыткам;
  `worker_ms` — весь путь в воркере).
- API: `[direct_api] request_id type marketplace article status total_ms`.

## Ограничения MVP

Нет кэша и singleflight по одному товару и rate-limit на пользователя — добавляются поверх, не
меняя протокол. Пул сессий общий с режимом задач
(изоляция не делалась).
