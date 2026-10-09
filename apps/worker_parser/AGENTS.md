# apps/worker_parser

Воркер, который забирает задачи парсинга OZON/Wildberries из очереди `packages/task` (Postgres,
`SELECT ... FOR UPDATE SKIP LOCKED`), получает браузерную сессию из Redis (наполняется
`apps/worker_sessions`), выполняет HTTP-парсинг через `curl_cffi` и сохраняет прогресс/результаты
через `TaskService`/`ResultService` (`packages/result`).

## Структура

Плоская, по образцу `apps/api/src/` (и `apps/worker_sessions/src/`): точка входа — `src/__main__.py`
напрямую в `src/`, остальные модули (`config.py`, `enums.py`, `exceptions.py`, `entities.py`,
`http_client.py`, `retry_policy.py`, `error_classifier.py`, `registry.py`, `fetch_context.py`,
`session_provider.py`, `execution.py`, `services.py`, `task_runner.py`, `runner.py` — только `run_main`) — тоже
прямо в `src/`. Пул сессий (потребление из
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
| `REVIEWS` | `{"marketplace":"ozon","sort_order":"usefulness_desc","next_params":"?page=2&page_key=...\|null","seen_uuids":[...]}` | `{"marketplace":"wildberries","offset":N,"root_id":N,"feedback_host":"..."}` (в режиме задач курсора нет — все отзывы одной страницей) |

Ozon-пагинация: `next_url == null` = исчерпано. WB-пагинация: исчерпание определяется по короткой
странице (`< 100` элементов, `WB_PAGE_SIZE`) или `collected_so_far >= total_on_site` (seller), не
по полю курсора. Единая операция — `fetch_page(input_value, cursor, ctx: FetchContext) -> Page(items, next_cursor)`
для каждой пары (маркетплейс, `ParseType`); реестр — `registry.OPERATIONS` (фетчер + модель курсора),
`FetchContext` (`fetch_context.py`) несёт HTTP-сессию, `SessionMessage`, лимит, лимит HTTP-ретраев и
дедлайн (`ctx.request` подставляет их в `execute_request`). Карточка — страница с `next_cursor=None`.
**Лимит результатов** (`task.result_limit`) применяет `task_runner.process_item_pages` для `SEARCH_QUERY`, `CATEGORY`, `SELLER` и `REVIEWS` (для карточки — нет): передаёт остаток лимита в `ctx.limit` и сам обрезает страницу до остатка — списочные фетчеры режут её по `ctx.limit` сами, отзывные (Ozon/WB) отдают страницу целиком. Лимит считается по каждому элементу задачи (входу) отдельно.

**Поиск WB** (`fetch_wb_search_page`) — конец выдачи определяется не по размеру страницы, а по ответу WB:
- HTTP 200 с телом `{"error": "binding request: page param malformed", "code": 500}` — страница больше
  лимита WB (60 страниц, ~6000 позиций на запрос; воспроизводится на любой сессии) — конец. Любая
  другая `error` в теле — сбой (`UpstreamDataError`), а не конец.
- Ответ без товаров (форма «ничего не найдено» или пустой `products`) — конец. Короткая страница концом
  не считается.
- Смена набора (`metadata.catalog_type`: `merger` — точные совпадения → `preset` — подмешанный WB набор по
  упрощённому запросу) ничего не отбрасывает и конца не означает: `preset`-товары входят в результат.
  Клиент/потребитель, которому нужны только точные совпадения, отличает их по составу выдачи сам.
- Категории и продавцы WB конец по `error` не используют (по-прежнему короткая или пустая страница), но
  разделяют с поиском защиту от сбоев сессии (ниже).

**Хост `card.json` (CDN-корзина WB)** — `basket-NN.wbbasket.ru`, номер выводится из `vol = nm_id // 100000`
по таблице `WB_BASKET_RANGES`. WB открывает новые корзины чаще, чем обновляется таблица, а для `vol` за её
пределами берётся последняя корзина — на ней 404. Поэтому `fetch_wb_product_page` (`_fetch_wb_card_json`) при
404 перебирает соседние корзины (`utils.get_wb_basket_host_candidates`: табличный хост, затем 4 вверх и 2
вниз) и запоминает найденный хост на `vol` в памяти процесса (`remember_wb_basket_host`) — следующие
запросы и URL фото (`get_wb_basket_host`) идут сразу на верный хост. 404 на всех кандидатах — настоящее
«карточки нет»; не-404 (блок, 5xx) не перебираются. Таблицу всё равно стоит иногда дополнять — это экономит
лишние запросы после рестарта.

**Сбои сессии WB** (выдачи поиска, категории и продавца, отзывы; карточка товара не затронута):
- **Деградировавший ответ** — нет `products` верхнего уровня, вместо него `data`/`state`/`version` с одним
  посторонним товаром (`wb.utils.is_degraded_wb_listing`) — сессия деградирует после 11–34 страниц. Фетчер
  бросает `SuspiciousThinResultError`: политика — `REINIT_SESSION`, страница повторяется на новой сессии, а
  посторонний товар в результат не попадает (раньше его принимали за короткую последнюю страницу и обход
  обрывался: в задачах категорий — 601 и 1601 товар вместо ~3400). HTTP 498 (антибот) — уже `BlockedError`
  с той же политикой.
- **Первая пустая страница** (`products: []` в нормальной форме) — не конец: `EmptyPageUnconfirmedError`,
  `PageExecutor` повторяет вызов на другой сессии с `FetchContext.confirm_empty_page=True`; пусто и там —
  настоящий конец (потолок выдачи), иначе берутся данные новой сессии. Цена: на естественном конце выдачи
  расходуется одна сессия. Ответ без ключа `products` («ничего не найдено») конец без подтверждения.
- **Повторы на той же сессии не делаются** — на живых ответах они не помогали (0 из 12), а смена сессии
  лечила деградацию и 498 с первой попытки.
- **Отзывы:** ответ без `feedbacks` или пустой список при `feedbackCount > 0` — тот же сбой сессии
  (`SuspiciousThinResultError`); товар без отзывов (`feedbackCount == 0`) — норма.
- Потолок выдачи плавает во времени: поиск — 60 страниц, категория в живых прогонах — от 26 до 35.

**Отзывы Ozon** — `{product}/reviews/?...` через `entrypoint-api`, 30 отзывов на страницу, один запрос
на страницу без прогрева. Следующая страница берётся из `paging.nextButton` виджета `webListReviews`
(содержит `page_key`) — голый `?page=N` без `page_key` глубже ~5-й страницы отдаёт повторы (проверено на
живых ответах). Потолок Ozon — около 33 страниц (~990 отзывов) на одну сортировку; режим задач
(`FetchContext.walk_all_review_sorts`) обходит `usefulness_desc` → `score_desc` → `score_asc` с
дедупликацией по `uuid` (на товаре с 3368 отзывами: ~1690 уникальных против 258 у прежнего обхода
через `reviewshelfpaginator`). `published_at_desc` Ozon молча заменяет на `usefulness_desc`, поэтому
его в обходе нет.

**Отзывы WB** — WB отдаёт все отзывы одним ответом, поэтому страница — срез результата
(`FetchContext.review_page_size`); `None` (режим задач) — все отзывы одной страницей. Курсор несёт
`root_id`/`feedback_host`, следующая страница — один запрос без прогрева и определения хоста.

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

## Единый цикл выполнения

`execution.PageExecutor` — единственное место цикла «взять сессию → выполнить → ретрай по
`retry_policy`», для одного элемента задачи или (в режиме direct) одного запроса. Различия режимов
задаются `ExecutionOptions` (потолок попыток `max_attempts`, `deadline` в `time.monotonic()`,
`http_retries`, размер страницы WB-отзывов, обход сортировок Ozon-отзывов), а не копиями цикла:

- **`SessionProvider`** (`session_provider.py`) — откуда берётся сессия: `PoolSessionProvider` (режим
  задач) берёт её из Redis-пула через `ZPOPMIN` и возвращает в пул в `release` (только если сессии
  доверяем; `discard` — не возвращает). Провайдер отдаёт `SessionHandle` — сессию вместе с HTTP-клиентом,
  клиент закрывается при `release`/`discard`.
- **Классификатор** (`error_classifier.classify_error`) — одна классификация на два потребителя:
  `RetryPolicy` (цикл выполнения) и `ErrorOutcome` (`INVALID_INPUT`/`NOT_FOUND`/`UNAVAILABLE`/`ERROR` —
  статус ответа direct). `RequestError` с 404 → `NOT_FOUND`, `InputResolutionError` → `INVALID_INPUT`,
  дедлайн/нет сессии → `UNAVAILABLE`.
- **Исчерпание попыток** — `FetchFailedError` с исходной ошибкой и классификацией; вызывающий сам решает,
  завершить элемент задачи (`task_runner.process_item_pages`) или ответить клиенту.
- **Дедлайн** — `asyncio.wait_for` вокруг операции плюс `FetchContext.request` не отправляет запрос
  после дедлайна и обрезает таймаут по остатку (`DeadlineExceededError`).
- **Сессия при неожиданном сбое** (не `ParserError`: БД, баг) в пул не возвращается —
  `handle_task_item` вызывает `discard_session()`.
- Профиль продавца (`SELLER`) выполняется через `executor.run(..., retry=False)` — одна попытка, при
  ошибке сессия выбрасывается, элемент всё равно завершается успешно.

## Режимы: `WORKER_MODE=tasks|direct`

Один процесс — один режим (`WorkerMode`, по умолчанию `tasks`; выбор в `runner.run_main`).

- **`tasks`** — описано выше: очередь Postgres, `PoolSessionProvider`.
- **`direct`** — синхронные запросы клиента из Redis (см. [`packages/direct`](../../packages/direct/AGENTS.md)).
  Подключение к Postgres не открывается. `direct_runner.py`: читает `XREADGROUP` группой
  `direct-workers` (`BLOCK`), свободных слотов = `DIRECT_MAX_CONCURRENT_REQUESTS - running`
  (если 0 — `asyncio.wait(FIRST_COMPLETED)`, иначе `consume(count=free)`), каждый запрос — отдельная
  `asyncio.Task`. Запрос: разбор входа (артикул → ссылка) и курсора → тот же `PageExecutor` с
  `ExecutionOptions(max_attempts=DIRECT_MAX_ATTEMPTS, deadline=...)` → `DirectReply`. Liveness-статус
  `READY`/`WORKING`. Новый тип direct-запроса = запись в `registry.OPERATIONS` + маппинг в
  `direct_runner.PARSE_TYPE_BY_REQUEST_TYPE`, а не новый цикл.

Конфиг `DIRECT_*` (`config.DirectConfig`, `.env.example`): `CONSUMER_NAME`, `MAX_CONCURRENT_REQUESTS`,
`BLOCK_MS`, `MAX_ATTEMPTS`, `HOT_SESSION_MAX_AGE_SECONDS`, `SESSION_WAIT_SECONDS`, `MARKETPLACES`,
`REVIEWS_WB_PAGE_SIZE`.

### Горячая сессия (`hot_session.py::HotSessionSlot`) — второй `SessionProvider`

По одной на маркетплейс. Берётся из пула при старте (прогрев) и **не возвращается** в пул между
запросами — следующий запрос не платит за `ZPOPMIN` и новый HTTP-клиент, keep-alive соединение живёт
(в логе `session_ms=0`). Одна сессия делится между конкурентными запросами процесса; выбор/ротация —
под `asyncio.Lock`.

- **Ротация:** по возрасту (`HOT_SESSION_MAX_AGE_SECONDS`, 120 с; сессия возвращается в пул) или при
  `discard` (ошибка с политикой `REINIT_SESSION`; в пул не возвращается). Ротируемую сессию нельзя
  закрывать под ногами запросов, которые её ещё используют, поэтому освобождение откладывается до
  ухода последнего.
- **Ловушка:** порог остаточного TTL при `acquire_session` — обычный
  `SESSION_POOL_MIN_TTL_MARGIN_SECONDS` (30 с). **Нельзя** добавлять к нему возраст ротации: TTL
  сессий у `worker_sessions` (`GENERATION_TTL_MS`) — 7 минут, и большой порог заставит
  `acquire_session` выбрасывать из пула все живые сессии (покрыто тестом).
- Сессии нет — ждём не дольше `min(SESSION_WAIT_SECONDS, остаток дедлайна)`, затем `unavailable`.
- Пул сессий общий с режимом задач (известное ограничение, изоляция не делалась).

## Retry/эскалация — упрощена до одного уровня

`retry_policy.py`: `BlockedError`/`SuspiciousThinResultError`/`RequestError` → до 3 попыток,
`REINIT_SESSION` (забрать новую сессию из Redis-пула); `UpstreamDataError` → 1 попытка, `KEEP`
(та же сессия); `InputResolutionError`/`BrowserInitError` → 0 попыток, fail fast; `RequestError` с HTTP 404 (не блокировка)
→ 0 попыток, `KEEP` — «такого нет» окончательно, смена сессии не поможет.

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

До нескольких `Task` в обработке на процесс одновременно (`POLL_MAX_CONCURRENT_TASKS`, по
умолчанию 3) — каждая как независимый `asyncio.Task` (`run_claimed_task` в `task_runner.py`), со своим
lease-heartbeat-лупом. Внутри одной задачи `TaskItem`-элементы тоже обрабатываются конкурентно, до
`POLL_MAX_CONCURRENT_ITEMS_PER_TASK` (по умолчанию 5) одновременно — `process_claimed_task`
запускает их через `asyncio.gather` за общим `asyncio.Semaphore`, не последовательным циклом.
Каждый элемент сам перепроверяет статус задачи (`RUNNING`) непосредственно перед стартом, а не
один раз в начале — пауза/отмена, случившаяся в процессе, останавливает ещё не начатые элементы,
уже запущенные доводятся до конца (не прерываются на середине страницы).

Конкурентное завершение элементов одной задачи требует блокировки: `TaskService.complete_item`
берёт `SELECT ... FOR UPDATE` на родительский `Task` (`TaskRepository.lock_by_id`,
[`packages/task`](../../packages/task/AGENTS.md)) перед проверкой "все ли siblings терминальны" —
без этого два элемента, завершившиеся почти одновременно, могут каждый увидеть другого как ещё не
завершённого и не перевести родительскую задачу в терминальный статус вообще (упущенное обновление,
race, которой не было при строго последовательной обработке).

`run_poll_loop` — плоский fan-out, не пул воркеров со своим шедулингом: пока запущенных задач
меньше лимита, зовёт `claim_next` и сразу пытается забрать ещё; при достижении лимита ждёт
завершения хотя бы одной (`asyncio.wait(..., FIRST_COMPLETED)`). Это безопасно без дополнительной
координации, потому что:

- `claim_next` — `SELECT ... FOR UPDATE SKIP LOCKED` (`packages/task`), конкурентные вызовы из
  одного процесса не пересекаются так же, как не пересекаются вызовы из разных процессов;
- `SessionPoolStore.acquire_session` — атомарный `ZPOPMIN` (`packages/sessions`), конкурентные
  вызовы не выдадут одну и ту же сессию дважды;
- Каждая независимо запланированная конкурентная корутина (каждая claimed-задача, её
  heartbeat-луп, каждый конкурентно обрабатываемый `TaskItem`) получает **свою собственную пару**
  `TaskService`/`ResultService` через `services.build_services(session_factory)`, а не общие на
  процесс — `AsyncTransactionManager` хранит активную сессию/репозитории как мутируемые атрибуты
  самого себя (`self.session`, выставляется в `__aenter__`), а не per-call-локальное состояние.
  Он безопасен при **последовательном** переиспользовании, но если два `asyncio.gather`/
  `asyncio.create_task`-сиблинга одновременно войдут в `async with` одного и того же экземпляра,
  они гонятся за одним `self.session` — раньше здесь был один `AsyncTransactionManager` на весь
  процесс, и это приводило к `sqlalchemy.exc.InvalidRequestError: This session is provisioning a
  new connection; concurrent operations are not permitted` и падению всего воркера.
  `apps/api` эта гонка не касается — там DI (`providers.Factory`) сам выдаёт свежий
  `AsyncTransactionManager` на каждый HTTP-запрос.

Liveness-статус (`WorkerParserStatus`) остаётся общим на процесс, не per-task: `WORKING` значит
"хотя бы одна задача выполняется" (не "N из M слотов заняты"), `WAITING_FOR_SESSION`/`WORKING` от
разных конкурентных задач перезаписывают друг друга по `set_status()` без координации — это
осознанно принятая грубая аппроксимация, точный статус каждого слота не отслеживается.

Горизонтальное масштабирование сверх `MAX_CONCURRENT_TASKS` одного процесса — по-прежнему через
запуск нескольких процессов воркера.

## Что перенесено из `marketplace-parser`, что переосмыслено, что не перенесено

**Перенесено почти дословно**: HTTP-фетчеры по типам (детальная карточка, поиск, категория,
продавец, отзывы) для OZON и Wildberries — запросы, заголовки, извлечение данных из ответа;
`extract_next_page` (Ozon); дедупликация товаров (`seen_keys`/`seen_ids`); `curl_cffi.AsyncSession`
как HTTP-клиент (нативно асинхронный, без обёртки в thread-pool).

**Переосмыслено**: fetch-функции для пагинируемых типов разбиты на однострочные (single-page)
вызовы вместо внутреннего `while`-цикла до исчерпания/исключения — так обработчик в `task_runner.py`
может персистировать курсор/результаты после каждой страницы, а не только по завершении всего
входа. 3-уровневая retry-лестница референса сведена к одному уровню (см. выше). `resume_state`,
передаваемый через `PartialResultError`, заменён персистентным `TaskItem.cursor`.

**Не перенесено**: RabbitMQ/`aio_pika`-консьюмер (`src/entrypoints/worker.py`) — заменён
poll-лупом, вызывающим `TaskService.claim_next`; собственная модель БД `marketplace-parser`
(`TaskModel`/`data_manager`) — не используется, оркестрация только через `packages/task`, результаты
только через `packages/result`.

## Тарификация — `packages/billing`

`services.build_services` теперь дополнительно строит `BillingService`/`NotificationService` (каждый
со своим отдельным `AsyncTransactionManager`, тем же принципом, что и `TaskService`/`ResultService`
— см. докстринг `build_services`) и передаёт их в `TaskService`. `NotificationService` нужен
`TaskService.complete_item`, чтобы завершение задачи могло породить `task.completed`/`task.failed`
уведомление (см. [`packages/task/AGENTS.md`](../../packages/task/AGENTS.md), "Уведомления") — воркер
сам его не вызывает, только конструирует и передаёт. `build_services` также передаёт
`frontend_base_url=config.FRONTEND_BASE_URL` (`apps/worker_parser/src/config.py::Config`, `.env`:
`FRONTEND_BASE_URL`) — **этот воркер, не `apps/api`, реально вызывает `complete_item`** для обычных
(не проверочных) задач, поэтому `task_link` в payload `task.completed`/`task.failed` строится именно
здесь, из своего собственного `.env`, а не из `apps/api`'s `REST_FRONTEND_BASE_URL` — два раздельных
процесса/деплоймента, значение нужно задавать в обоих. Воркер сам не вызывает `BillingService`
напрямую —
списание за сохранённые результаты происходит внутри `TaskService.record_item_progress` (см.
[`packages/task/AGENTS.md`](../../packages/task/AGENTS.md), "Тарификация"), воркер просто продолжает
звать этот метод как раньше, без изменений в `task_runner.py`. Если баланс
пользователя уходит в минус — задача переходит в `PAUSED`, что воркер обнаружит стандартной
кооперативной проверкой статуса перед следующим элементом/страницей (см. "Модель конкурентности" —
`RUNNING` перепроверяется перед стартом каждого элемента).

## Хранение результатов — `packages/result`

Спарсенные сущности (товары, карточки товара, отзывы, профили продавцов) сохраняются через
`ResultService.record_results` — по одной строке `result_items` на сущность, в паре с
`record_item_progress` на каждой странице. См. [`packages/result/AGENTS.md`](../../packages/result/AGENTS.md)
за полным контрактом payload-моделей по (маркетплейс, тип парсинга).

## Зависимости

`core.configs.RedisConfig`/`PostgresConfig` переиспользуются (не дублируются). Без
`dependency_injector`: одна точка входа (`run_main` в `runner.py`, вся логика задач — `task_runner.py`), один долгоживущий набор
зависимостей, без per-request-скоупинга — как и в `apps/worker_sessions`.
