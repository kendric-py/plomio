# apps/worker_parser

Воркер, который забирает задачи парсинга OZON/Wildberries из очереди `packages/task` (Postgres,
`SELECT ... FOR UPDATE SKIP LOCKED`), получает браузерную сессию из Redis (наполняется
`apps/worker_sessions`), выполняет HTTP-парсинг через `curl_cffi` и сохраняет прогресс/результаты
через `TaskService`/`ResultService` (`packages/result`).

## Структура

Плоская, по образцу `apps/api/src/` (и `apps/worker_sessions/src/`): точка входа — `src/__main__.py`
напрямую в `src/`, остальные модули (`config.py`, `enums.py`, `exceptions.py`, `entities.py`,
`http_client.py`, `retry_policy.py`, `runner.py`) — тоже прямо в `src/`. Пул сессий (потребление из
Redis) и liveness-heartbeat — не здесь, а в
[`packages/sessions`](../../packages/sessions/AGENTS.md)/[`packages/worker_health`](../../packages/worker_health/AGENTS.md),
общих с `apps/worker_sessions`. Единственная дополнительная вложенность — `marketplaces/{ozon,wb}/`
(constants/headers/utils/parsers/fetchers, Ozon дополнительно — `pagination.py`, Wildberries —
`menu.py` для кэша категорий), оправданная реальным разделением по маркетплейсам.

Папка приложения называется `worker_parser` (подчёркивание, не дефис) специально — так внутренние
импорты пишутся полным путём от корня репозитория, `apps.worker_parser.src.*`, тем же способом, что
и `apps.api.src.*` у `apps/api` (дефис в имени папки сделал бы такой путь синтаксически невалидным
Python-импортом). Запуск — `make run-worker_parser` → `poetry -C apps/worker_parser run python -m
apps.worker_parser.src` (см. корневой `Makefile`, идентично `run-api`/`run-worker_sessions`); `core.*`
и `packages.*` резолвятся тем же способом — через cwd=корень репозитория, который `python -m`
добавляет в `sys.path`.

Импорты `core.*`/`packages.*` резолвятся отдельно, через cwd=корень репозитория (`python -m` добавляет
текущую директорию в `sys.path`) — тот же механизм, что и у `apps/worker_sessions`.

## Курсор — персистентный, не эфемерный

`TaskItem.cursor` (JSONB) обязан персистироваться в БД по ходу работы через
`TaskService.record_item_progress`, вызывается после каждой обработанной страницы. Это отличает
дизайн от референсного `marketplace-parser`, где `resume_state` живёт только в памяти процесса и
теряется при падении воркера.

Форма курсора по `ParseType` × маркетплейс:

| ParseType | Ozon | Wildberries |
|---|---|---|
| `PRODUCT_PAGE` | `null` (без пагинации) | `null` |
| `SEARCH_QUERY`/`CATEGORY` | `{"marketplace":"ozon","next_url":"...\|null","referer":"...","prev_request_id":"...\|null"}` | `{"marketplace":"wildberries","page_num":N}` |
| `SELLER` | как `SEARCH_QUERY`/`CATEGORY` | `{"marketplace":"wildberries","page_num":N,"total_on_site":N,"collected_so_far":N}` |
| `REVIEWS` | `{"marketplace":"ozon","product_path":"...","start_page_id":"...","sort_order":"...","next_url":"...\|null","referer":"...","prev_request_id":"...\|null","seen_uuids":[...]}` | `{"marketplace":"wildberries","nm_id":N,"root_id":N\|null,"feedback_host":"...\|null"}` |

Ozon-пагинация: `next_url == null` = исчерпано. WB-пагинация: исчерпание определяется по короткой
странице (`< 100` элементов, `WB_PAGE_SIZE`) или `collected_so_far >= total_on_site` (seller), не
по полю курсора. Wildberries-отзывы получаются одним запросом (WB отдаёт все фидбеки в одном
payload) — курсор им не нужен, `record_item_progress(cursor=None, ...)` вызывается один раз.

Каждый cursor несёт `"marketplace"` как защитную сверку (не используется активно в v1, но формат
зарезервирован под неё при появлении расхождений в резюме).

**Известное упрощение**: дедупликация внутри одной страницы/группы страниц (`seen_keys`/`seen_uuids`
кроме reviews) держится в памяти процесса на время обработки одного `TaskItem`, а не персистируется
в курсоре целиком (кроме reviews, где `seen_uuids` персистируется, так как без этого дедуп между
сортировками потерялся бы при возобновлении). Если воркер падает и другой воркер резюмирует с
последней сохранённой страницы, теоретически возможны редкие дубликаты строк `result_items` на
границе рестарта — это принятый компромисс v1, не решается в этой итерации.

## Потребление сессии из Redis — `ZPOPMIN`, не `XREADGROUP`

`SessionPoolStore.acquire_session` (общий с `apps/worker_sessions` класс из
[`packages/sessions`](../../packages/sessions/AGENTS.md)) атомарно забирает сессию с ближайшим
`expire_at` через `ZPOPMIN sessions:pool:{marketplace}`, затем проверяет остаток TTL через `PTTL
session:{marketplace}:{id}` (порог — `SESSION_POOL_MIN_TTL_MARGIN_SECONDS`, передаётся вызывающей
стороной) и читает тело через `GET`. При отсутствии ключа/тонком остатке TTL — отбрасывает и
повторяет (до `SESSION_POOL_MAX_POP_ATTEMPTS`).

Альтернатива `XREADGROUP` по стриму `{SESSIONS_STREAM_PREFIX}:{marketplace}` сознательно не
выбрана: `ZPOPMIN` даёт атомарную single-consumer семантику бесплатно (без bookkeeping consumer
group), а у стрима нет собственного TTL — потребителю на его основе всё равно потребовалась бы та
же перепроверка через `GET` перед использованием. Стрим остаётся нетронутым, зарезервирован под
push-модель, если она когда-нибудь понадобится — этот воркер тянет сессию по запросу в момент
захвата задачи, а не подписывается на уведомления.

## Retry/эскалация — упрощена до одного уровня

`retry_policy.py`: `BlockedError`/`SuspiciousThinResultError`/`RequestError` → до 3 попыток,
`REINIT_SESSION` (забрать новую сессию из Redis-пула); `UpstreamDataError` → 1 попытка, `KEEP`
(та же сессия); `InputResolutionError`/`BrowserInitError` → 0 попыток, fail fast.

В референсном `marketplace-parser` эскалация на "отдельную сессию" была отдельным (третьим) ярусом
поверх retry с той же сессией — нужна была, чтобы не терять `resume_state`, привязанный к
процессу/исключению. Здесь курсор уже персистентен в БД независимо от того, сколько раз воркер
меняет сессию — поэтому "retry с новой сессией" и "эскалация на отдельную сессию" стали одним и тем
же действием (`REINIT_SESSION`), отдельный ярус не нужен.

## Lease-heartbeat vs liveness-heartbeat — два независимых механизма

- **Lease-heartbeat** (`TaskService.heartbeat`) — работает, только пока задача захвачена
  (`run_lease_heartbeat_loop`, параллельная `asyncio.Task` на время обработки), продлевает
  `lease_expires_at` в Postgres каждые `POLL_HEARTBEAT_INTERVAL_SECONDS`. Если воркер падает,
  `reclaim_expired_leases()` (вызывается снаружи, например планировщиком) вернёт задачу в очередь —
  прогресс не теряется, так как курсор уже сохранён на уровне `TaskItem`.
- **Liveness-heartbeat** (`LivenessReporter`, [`packages/worker_health`](../../packages/worker_health/AGENTS.md)
  — общий с `apps/worker_sessions`, не локальный класс) — работает постоянно, независимо от того,
  захвачена ли задача, HTTP POST на `LIVENESS_ENDPOINT_URL` каждые `LIVENESS_INTERVAL_SECONDS`. Имя
  воркера — `LIVENESS_WORKER_NAME` из `.env` (не hostname/PID), статус — `WorkerParserStatus`
  (`READY`/`WORKING`/`WAITING_FOR_SESSION`), передаётся в `set_status()` как `.value` (класс
  общий для всех воркеров и не знает про `WorkerParserStatus`).

`POLL_WORKER_ID` (владелец lease в БД) и `LIVENESS_WORKER_NAME` (идентификатор в HTTP-heartbeat) —
сознательно разные ключи `.env`, хотя оператор обычно будет ставить их одинаковыми.

Принимающая ручка на бэкенде существует: `POST /api/worker-health/parser/heartbeat`
(`apps/api/src/routers/worker_health`, см. [`packages/worker_health`](../../packages/worker_health/AGENTS.md)
за полным контрактом — тело запроса, поведение при пропуске heartbeat). Раньше это было открытым
вопросом ("получателя нет") — закрыто.

## Модель конкурентности

Один `Task` в обработке на процесс, элементы (`TaskItem`) внутри задачи — последовательно.
Горизонтальное масштабирование — через запуск нескольких процессов воркера, а не конкурентность
внутри одного: `claim_next` — одна строка за вызов, liveness-статус `WORKING` остаётся однозначным
(не "1 из N"), и одна задача не выедает общий Redis-пул сессий у остальных воркеров. Параллелизм по
`TaskItem` внутри одной задачи — сознательно отложен на будущую итерацию.

## Что перенесено из `marketplace-parser`, что переосмыслено, что не перенесено

**Перенесено почти дословно**: HTTP-фетчеры по типам (детальная карточка, поиск, категория,
продавец, отзывы) для OZON и Wildberries — запросы, заголовки, извлечение данных из ответа;
`extract_next_page` (Ozon); дедупликация товаров (`seen_keys`/`seen_ids`); `curl_cffi.AsyncSession`
как HTTP-клиент (нативно асинхронный, без обёртки в thread-pool).

**Переосмыслено**: fetch-функции для пагинируемых типов разбиты на однострочные (single-page)
вызовы вместо внутреннего `while`-цикла до исчерпания/исключения — так обработчик в `runner.py`
может персистировать курсор/результаты после каждой страницы, а не только по завершении всего
входа. 3-уровневая retry-лестница референса сведена к одному уровню (см. выше). `resume_state`,
передаваемый через `PartialResultError`, заменён персистентным `TaskItem.cursor`.

**Не перенесено**: RabbitMQ/`aio_pika`-консьюмер (`src/entrypoints/worker.py`) — заменён
poll-лупом, вызывающим `TaskService.claim_next`; собственная модель БД `marketplace-parser`
(`TaskModel`/`data_manager`) — не используется, оркестрация только через `packages/task`, результаты
только через `packages/result`.

## Хранение результатов — `packages/result`

Спарсенные сущности (товары, карточки товара, отзывы, профили продавцов) сохраняются через
`ResultService.record_results` — по одной строке `result_items` на сущность, в паре с
`record_item_progress` на каждой странице. См. [`packages/result/AGENTS.md`](../../packages/result/AGENTS.md)
за полным контрактом payload-моделей по (маркетплейс, тип парсинга).

## Зависимости

`core.configs.RedisConfig`/`PostgresConfig` переиспользуются (не дублируются). Без
`dependency_injector`: одна точка входа (`run_main` в `runner.py`), один долгоживущий набор
зависимостей, без per-request-скоупинга — как и в `apps/worker_sessions`.
