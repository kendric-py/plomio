# apps/worker_sessions

Воркер, генерирующий браузерные сессии (куки, заголовки, данные прокси) для OZON и Wildberries —
используются `apps/worker_parser` для запросов к маркетплейсам. Основная логика перенесена и
переосмыслена из отдельного (вне монорепы) прототипа `session-service`: генерация через Camoufox
сохранена, доставка результата переосмыслена под Redis вместо RabbitMQ.

## Структура

Плоская, по образцу `apps/api/src/`: точка входа — `src/__main__.py` напрямую в `src/`, остальные
модули (`config.py`, `enums.py`, `entities.py`, `exceptions.py`, `pool_manager.py`, `generation/`,
`proxy/`) — тоже прямо в `src/`. Пул сессий (запись в Redis) и liveness-heartbeat — не здесь, а в
[`packages/sessions`](../../packages/sessions/AGENTS.md)/[`packages/worker_health`](../../packages/worker_health/AGENTS.md),
общих с `apps/worker_parser`. Папка приложения называется `worker_sessions` (подчёркивание, не
дефис) специально — так внутренние импорты пишутся полным путём от корня репозитория,
`apps.worker_sessions.src.*`, тем же способом, что и `apps.api.src.*` у `apps/api` (дефис в имени
папки сделал бы такой путь синтаксически невалидным Python-импортом). Запуск —
`make run-worker_sessions` → `poetry -C apps/worker_sessions run python -m
apps.worker_sessions.src`.

## Поток генерации

`pool_manager.py::run_pool_manager` поднимает по `GENERATION_CONCURRENCY_PER_MARKETPLACE` воркеров
на каждый `Marketplace` (`OZON`, `WILDBERRIES`) — enum живёт в `core/enums.py` (общий с
`apps/worker_parser`), не переопределяется локально. Каждый воркер в цикле:

1. Проверяет `SessionPoolStore.live_count(marketplace)` (см.
   [`packages/sessions`](../../packages/sessions/AGENTS.md)) — если пул уже не меньше
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
5. Валидную сессию сохраняет в Redis (`SessionPoolStore.save`, `packages/sessions`).

**Прогретые браузеры** (`generation/browser.py::_BrowserPool`): запуск Firefox — главная фиксированная
стоимость генерации, поэтому один процесс Camoufox живёт на прокси и обслуживает до
`GENERATION_BROWSER_MAX_USES` сессий, каждая — в новом изолированном `context` (куки не пересекаются).
Пул работает на отдельном потоке с собственным event loop; браузер выбрасывается при ошибке сессии,
по возрасту (`BROWSER_MAX_AGE_S`), числу использований и простое (`BROWSER_IDLE_TTL_S`).
`BROWSER_MAX_AGE_S` + таймаут попытки обязаны быть меньше `PROCESS_REAPER_MAX_AGE_S`, иначе реапер убьёт
живой браузер как осиротевший. Картинки/шрифты/медиа блокируются через `context.route`, переход —
`wait_until='commit'`, фиксированные `sleep` убраны (ожидание по появлению кук).
Замер (прямое соединение): Ozon ~9,3 с → ~5 с,
WB ~12 с → ~7,5 с на сессию; нижняя граница — сам антибот-челлендж (WB ~3,6 с, Ozon ~2,8 с).

## Режим js_runtime (генерация без браузера)

Альтернатива Camoufox — [`js_runtime/`](./js_runtime/AGENTS.md): HTTP в `curl_cffi` + challenge-скрипт
маркетплейса в Node. ~1,6 с (WB) и ~2 с (Ozon) на сессию против ~7,5 / ~5 с. Режим выбирается
**по маркетплейсу**: `GENERATION_OZON_MODE` / `GENERATION_WB_MODE` = `browser` (по умолчанию) |
`js_runtime`. `registry.build_session` берёт builder по режиму; адаптеры —
`generation/marketplaces/{ozon,wb}/session_js.py`, подключение `js_runtime/ready/*` —
`generation/js_runtime/loader.py`. Фолбэка на браузер нет: `JsRuntimeError`
завершает попытку ошибкой (её обрабатывает `pool_manager`, как любую ошибку генерации).

- **Идентичность.** js_runtime-сессия говорит TLS `chrome146` (Ozon) / Firefox 135 (WB). UA и
  Client-Hints Ozon-сессии зависят от поданной сборки челленджа: поток берёт их из genuine-захвата
  сборки (`raw/real_script_vNN_M_0.json`, сейчас Chrome 154/155) или общего эталона
  (`template_chrome155.json`) — `oz_flow.identity_for_build`. В `SessionMessage` это попадает как
  `user_agent`/`sec_ch_ua` + `extra['impersonate']`; `validation.py` и `apps/worker_parser`
  (`create_*_http_session`) берут TLS-профиль оттуда (по умолчанию — прежние значения для
  браузерных сессий). Не хардкодить impersonate мимо этого поля.
- **Ограничения.** `spa_version` (WB) — константа `WB_FALLBACK_SPA_VERSION`: безбраузерный поток SPA не
  грузит. `app_version` (Ozon) читается из страницы после reload, иначе fallback.
- **Параллельность.** WB: свой постоянный `NodeSolver` на поток executor'а (один pipe — не thread-safe),
  упавший процесс пересоздаётся. Ozon: Node-подпроцесс на сессию, временные файлы уникальны по потоку.
- **Docker.** Образ — multi-stage: `node:22-slim` ставит `npm ci --omit=dev`, в финальный образ едут
  `node`, `node_modules` и только `js_runtime/ready` (`debug/`, `history/` — в `.dockerignore`).
  Кэши и временные файлы — в `JS_RUNTIME_CACHE_DIR` (`/tmp/js_runtime`), а не в код. `js-beautify` — devDependency.

`generation/process_reaper.py` параллельно подчищает осиротевшие процессы Camoufox/Playwright
(крэш/зависание инициализации браузера оставляет процесс висеть).

**Контейнер обязан запускаться с `init: true`** (`docker-compose.yml`, сервис `worker_sessions`) и
`MOZ_DISABLE_SANDBOX=1` — как в `session-service`. Без init PID 1 — Python, который не делает
`wait()` на осиротевших потомках Firefox/Node: они остаются зомби. `process_reaper` их не убирает
(у зомби пустой cmdline, `_matches_target` их пропускает, да и убить зомби нельзя — его должен
забрать родитель). Инцидент 2026-10-02: за ~6 часов 3465 зомби, `pids.current` 3473 при
`pids.max` 3521 — Firefox падал с `SIGSEGV` сразу при запуске, пул сессий переставал пополняться.
Диагностика: `docker exec <контейнер> sh -c 'ps -eo stat | grep -c Z'`.

## Хранение сессии — Redis

Подключение к Redis (`RedisConfig`: `HOST`/`PORT`/`DB`/`PASSWORD`) — глобальный конфиг
[`core/configs.py`](../../core/configs.py), а не локальный для этого воркера: Redis — часть
инфраструктуры приложения, по аналогии с `PostgresConfig`. `worker_sessions/config.py` импортирует
его оттуда (`from core.configs import RedisConfig`) и подключает как `config.REDIS`. Сам клиент
собирается через [`core.redis.get_redis_client`](../../core/redis.py) — общая фабрика для всех
Redis-потребителей проекта, не только этого воркера.

Ключи/запись/чтение пула — не здесь, а в [`packages/sessions`](../../packages/sessions/AGENTS.md)
(`SessionPoolStore`), общем с `apps/worker_parser` и `apps/api`. Формат решён (закрывает
соответствующую часть TODO в `docs/reference/architecture.md`):

- `session:{marketplace}:{session_id}` — сериализованный `SessionMessage` (JSON), `PEXPIRE` на
  `GENERATION_TTL_MS` (по умолчанию 7 минут — с запасом от естественного времени жизни сессии на
  маркетплейсе). Ключ исчезает сам по истечении TTL — не требует отдельного механизма реапинга,
  в отличие от брокера сообщений (RabbitMQ реапит TTL только при попытке доставки, а не проактивно).
- `sessions:pool:{marketplace}` — `ZSET`, score = `expire_at` (unix-время). Используется для учёта
  актуальной глубины пула (`ZCOUNT ... now +inf`), без отдельного wall-clock трекера.
- `{SESSIONS_STREAM_PREFIX}:{marketplace}` (по умолчанию `sessions:ozon` / `sessions:wildberries`)
  — Redis Stream, отдельный канал на маркетплейс (`SessionsStreamConfig` в `config.py`). При каждом
  `SessionPoolStore.save` в него добавляется запись (`session_id`, `expire_at`) через `XADD` с
  `MAXLEN ~ SESSIONS_STREAM_MAXLEN` (не даёт стриму расти неограниченно, если потребитель отстаёт
  или отсутствует). Канал — **дополнение** к TTL-хранилищу выше, а не замена: источник истины по
  тому, жива ли сессия, остаётся `session:{marketplace}:{id}` с `PEXPIRE` — у записей в Stream нет
  собственного TTL. Название явно вынесено в конфиг (не захардкожено), т.к. один и тот же Redis
  со временем будет обслуживать не только сессии, и разные домены не должны делить неймспейс молча.
  Стрим остаётся не потребляемым никем сознательно (см. `apps/worker_parser/AGENTS.md`) —
  зарезервирован под push-модель, если она когда-нибудь понадобится.

**Решено** (было открытым вопросом на момент написания этого раздела): `worker_parser` получает
сессию прямым чтением Redis, не через HTTP-ручку — `SessionPoolStore.acquire_session` (`ZPOPMIN`
по `sessions:pool:{marketplace}`, см. [`packages/sessions`](../../packages/sessions/AGENTS.md) и
`apps/worker_parser/AGENTS.md`).

## Прокси

`proxy/client.py::get_proxy()` — HTTP-клиент ручки выдачи прокси `GET /api/proxy/issue` api
(`packages/proxy`, см. [`packages/proxy/AGENTS.md`](../../packages/proxy/AGENTS.md)): отдаёт
**случайный активный** прокси из пула, который ведёт админ. Настройка в `.env` воркера:
`PROXY_API_ISSUE_URL=https://<api>/api/proxy/issue` и `PROXY_API_TOKEN` — тот же секрет, что
`PROXY_WORKER_TOKEN` в `.env` api (уходит заголовком `X-Worker-Token`). Пустой `PROXY_API_ISSUE_URL`
(значение по умолчанию) — `get_proxy()` возвращает `None`, воркер трактует это как «прокси сейчас
нет» и ждёт, не падает; то же при `404` (пул пуст), `401`/`503` (неверный/не настроенный токен).
`ProxyRotator` переиспользует один выданный прокси для `GENERATION_MAX_SESSIONS_PER_PROXY` генераций
подряд, прежде чем запросить новый.

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

`LivenessReporter` ([`packages/worker_health`](../../packages/worker_health/AGENTS.md) — общий с
`apps/worker_parser` класс, не локальный) — процесс-уровневый сигнал "воркер жив", независимый от
того, генерирует ли воркер сейчас сессию. Раз в `LIVENESS_INTERVAL_SECONDS` шлёт `POST` на
`LIVENESS_ENDPOINT_URL` с телом `{"worker_name": ..., "status": ...}`, где `worker_name` — значение
`LIVENESS_WORKER_NAME` из `.env` (не генерируется рантаймом), `status` — свободная строка, которую
передаёт `pool_manager.py` из `WorkerSessionsStatus` (`enums.py`) через `.value`: `READY`
(простаивает), `GENERATING` (поднимает браузер/генерирует сессию), `WAITING_FOR_PROXY` (ждёт
прокси от `ProxyRotator`).

Известное упрощение этой итерации: при нескольких параллельных generator-воркерах (по
`GENERATION_CONCURRENCY_PER_MARKETPLACE` на маркетплейс) статус — один общий на процесс, отражает
последний переход состояния любого из них, а не агрегат по всем. Если понадобится точность на
уровне отдельного generator-воркера — расширить `LivenessReporter` до отчёта по каждому воркеру
отдельно.

Принимающая ручка на бэкенде существует: `POST /api/worker-health/sessions/heartbeat`
(`apps/api/src/routers/worker_health`, см. [`packages/worker_health`](../../packages/worker_health/AGENTS.md)
за полным контрактом). Раньше это было открытым вопросом (как и для `worker_parser`) — закрыто.

## Что перенесено из `session-service`, а что нет

Перенесены и адаптированы (см. `pyproject.toml` — зависимости те же): генерация через Camoufox
(`generation/browser.py`), логика по маркетплейсам (`generation/marketplaces/`), валидация
(`generation/validation.py`), SOCKS5-мост (`generation/socks5_tunnel/`), реапер процессов
(`generation/process_reaper.py`).

Не перенесены (переосмыслены): публикация в RabbitMQ и отдельный `LiveSessionTracker`-костыль
(TTL-реап Rabbit ненадёжен при простое) — заменены на `SessionPoolStore` с TTL на самих ключах.

## Безбраузерный рантайм — `js_runtime/`

Исследовательский безбраузерный способ получить антибот-куки Ozon/WB (curl_cffi + Node-решатель,
~1–2 с вместо ~5–7,5 с у Camoufox). В прод-поток пока **не подключён**. Разложен на `ready/` (рабочий
код), `debug/` (отладка и проверки), `history/` (справка) — см. [`js_runtime/AGENTS.md`](./js_runtime/AGENTS.md).

## Не входит в эту итерацию

Ручка выдачи прокси на бэкенде — не существует, `proxy/client.py` работает как заглушка.

Закрыто с момента написания этого раздела (оставлено для истории): получатель HTTP-heartbeat на
бэкенде теперь есть (`POST /api/worker-health/sessions/heartbeat`, см. выше); протокол получения
сессии `worker_parser`'ом из Redis реализован — `SessionPoolStore.acquire_session` (`ZPOPMIN`), см.
[`packages/sessions`](../../packages/sessions/AGENTS.md) и `apps/worker_parser/AGENTS.md`.
