# apps/worker-sessions

Воркер, генерирующий браузерные сессии (куки, заголовки, данные прокси) для OZON и Wildberries —
используются `apps/worker-parser` для запросов к маркетплейсам. Основная логика перенесена и
переосмыслена из отдельного (вне монорепы) прототипа `session-service`: генерация через Camoufox
сохранена, доставка результата переосмыслена под Redis вместо RabbitMQ.

## Поток генерации

`pool_manager.py::run_pool_manager` поднимает по `GENERATION_CONCURRENCY_PER_MARKETPLACE` воркеров
на каждый `Marketplace` (`OZON`, `WILDBERRIES`). Каждый воркер в цикле:

1. Проверяет `RedisSessionStore.live_count(marketplace)` — если пул уже не меньше
   `GENERATION_TARGET_POOL_DEPTH`, ждёт и проверяет снова.
2. Получает прокси через `ProxyRotator.acquire()` (см. «Прокси» ниже). Если прокси нет — ждёт и
   пробует снова.
3. На отдельном потоке (`ThreadPoolExecutor`, т.к. Camoufox/Playwright синхронно блокируют) поднимает
   браузер (`generation/browser.py::initialize_browser_session`), проходит антибот-челлендж
   маркетплейса, извлекает куки/`user-agent`/`sec-ch-ua`/версию приложения
   (`generation/marketplaces/{ozon,wb}/session.py`).
4. Валидирует сессию реальным поисковым запросом к API маркетплейса
   (`generation/validation.py::validate_session`) — отсеивает сессии, заблокированные антиботом уже
   на уровне API, а не только главной страницы.
5. Валидную сессию сохраняет в Redis (`store/redis_store.py::RedisSessionStore.save`).

`generation/process_reaper.py` параллельно подчищает осиротевшие процессы Camoufox/Playwright
(крэш/зависание инициализации браузера оставляет процесс висеть).

## Хранение сессии — Redis

Подключение к Redis (`RedisConfig`: `HOST`/`PORT`/`DB`/`PASSWORD`) — глобальный конфиг
[`core/configs.py`](../../core/configs.py), а не локальный для этого воркера: Redis — часть
инфраструктуры приложения, по аналогии с `PostgresConfig`. `worker_sessions/config.py` импортирует
его оттуда (`from core.configs import RedisConfig`) и подключает как `config.REDIS`.

Формат решён (закрывает соответствующую часть TODO в `docs/reference/architecture.md`):

- `session:{marketplace}:{session_id}` — сериализованный `SessionMessage` (JSON), `PEXPIRE` на
  `GENERATION_TTL_MS` (по умолчанию 7 минут — с запасом от естественного времени жизни сессии на
  маркетплейсе). Ключ исчезает сам по истечении TTL — не требует отдельного механизма реапинга,
  в отличие от брокера сообщений (RabbitMQ реапит TTL только при попытке доставки, а не проактивно).
- `sessions:pool:{marketplace}` — `ZSET`, score = `expire_at` (unix-время). Используется для учёта
  актуальной глубины пула (`ZCOUNT ... now +inf`), без отдельного wall-clock трекера.
- `{SESSIONS_STREAM_PREFIX}:{marketplace}` (по умолчанию `sessions:ozon` / `sessions:wildberries`)
  — Redis Stream, отдельный канал на маркетплейс (`SessionsStreamConfig` в `config.py`). При каждом
  `RedisSessionStore.save` в него добавляется запись (`session_id`, `expire_at`) через `XADD` с
  `MAXLEN ~ SESSIONS_STREAM_MAXLEN` (не даёт стриму расти неограниченно, если потребитель отстаёт
  или отсутствует). Канал — **дополнение** к TTL-хранилищу выше, а не замена: источник истины по
  тому, жива ли сессия, остаётся `session:{marketplace}:{id}` с `PEXPIRE` — у записей в Stream нет
  собственного TTL. Название явно вынесено в конфиг (не захардкожено), т.к. один и тот же Redis
  со временем будет обслуживать не только сессии, и разные домены не должны делить неймспейс молча.
  Кто и как читает этот стрим (`XREAD`/`XREADGROUP` со стороны `worker-parser`) — пока не реализовано
  здесь, это относится к тому же открытому вопросу протокола ниже.

**Не решено этим воркером:** как именно `worker-parser` получает сессию (прямое чтение Redis,
HTTP-ручка на `worker-sessions`, что-то ещё) — см. открытый вопрос в `docs/reference/architecture.md`
и `apps/worker-parser/DEVELOPMENT_PROMPT.md`. Эта часть протокола проектируется на стороне
`worker-parser`.

## Прокси — заглушка

`proxy/client.py::get_proxy()` — HTTP-клиент на будущую ручку выдачи прокси (`PROXY_API_ISSUE_URL`
в `.env`), которой пока не существует. Пустой `PROXY_API_ISSUE_URL` (значение по умолчанию) —
`get_proxy()` возвращает `None`, воркер трактует это как «прокси сейчас нет» и ждёт, не падает.
`ProxyRotator` переиспользует один выданный прокси для `GENERATION_MAX_SESSIONS_PER_PROXY` генераций
подряд, прежде чем запросить новый. Когда ручка появится — меняется только `PROXY_API_ISSUE_URL`
и, при необходимости, разбор ответа в `get_proxy()`; остальной код воркера не зависит от источника.

**Дев-режим без прокси:** `GENERATION_REQUIRE_PROXY=false` (по умолчанию в `.env.example`) полностью
убирает ожидание прокси — `pool_manager` генерирует сессию напрямую (`proxy=None` во всех слоях:
`SessionMessage.proxy`, Camoufox без `proxy_url`, curl_cffi-валидация без `proxies`). Воркер при
старте пишет предупреждение в лог, если это включено. **На реальных окружениях обязано быть
`true`** — маркетплейсы банят IP, с которого массово генерируются сессии без прокси.

`generation/socks5_tunnel/` — локальный SOCKS5-мост для аутентифицированных upstream-прокси, т.к.
Camoufox/Playwright не умеет SOCKS5 с логином/паролем. Перенесён как есть из `session-service`:
поднимает на `127.0.0.1` неаутентифицированный SOCKS5-листенер, который проксирует каждое соединение
на реальный (аутентифицированный) upstream-прокси.

## HTTP-heartbeat воркера (liveness)

`liveness.py::LivenessReporter` — процесс-уровневый сигнал "воркер жив", независимый от того,
генерирует ли воркер сейчас сессию. Раз в `LIVENESS_INTERVAL_SECONDS` шлёт `POST` на
`LIVENESS_ENDPOINT_URL` с телом `{"worker_name": ..., "status": ...}`, где `worker_name` — значение
`LIVENESS_WORKER_NAME` из `.env` (не генерируется рантаймом), `status` — `WorkerSessionsStatus`
(`enums.py`): `READY` (простаивает), `GENERATING` (поднимает браузер/генерирует сессию),
`WAITING_FOR_PROXY` (ждёт прокси от `ProxyRotator`).

Известное упрощение этой итерации: при нескольких параллельных generator-воркерах (по
`GENERATION_CONCURRENCY_PER_MARKETPLACE` на маркетплейс) статус — один общий на процесс, отражает
последний переход состояния любого из них, а не агрегат по всем. Если понадобится точность на
уровне отдельного generator-воркера — расширить `LivenessReporter` до отчёта по каждому воркеру
отдельно.

**Не решено (открытый вопрос, как и для `worker-parser`, см. `docs/reference/architecture.md`):**
адрес/эндпоинт на бэкенде, принимающий этот запрос; остальной состав тела запроса, если
понадобится больше, чем имя+статус; поведение бэкенда при пропуске нескольких heartbeat подряд.
Пока `LIVENESS_ENDPOINT_URL` пуст по умолчанию — `LivenessReporter` не шлёт запросы и не падает.

## Что перенесено из `session-service`, а что нет

Перенесены и адаптированы (см. `pyproject.toml` — зависимости те же): генерация через Camoufox
(`generation/browser.py`), логика по маркетплейсам (`generation/marketplaces/`), валидация
(`generation/validation.py`), SOCKS5-мост (`generation/socks5_tunnel/`), реапер процессов
(`generation/process_reaper.py`).

Не перенесены (переосмыслены): публикация в RabbitMQ и отдельный `LiveSessionTracker`-костыль
(TTL-реап Rabbit ненадёжен при простое) — заменены на `RedisSessionStore` с TTL на самих ключах.

## Не входит в эту итерацию

Ручка выдачи прокси на бэкенде — не существует, `proxy/client.py` работает как заглушка. Получатель
HTTP-heartbeat на бэкенде — не существует. Протокол получения сессии `worker-parser`'ом из Redis —
не спроектирован здесь, это открытый вопрос на стороне `worker-parser`.
