# packages/sessions

Доменная область пула браузерных сессий в Redis — единственный источник правды про формат ключей
и запись/чтение пула, которым пользуются три независимых процесса:

- `apps/worker_sessions` — пишет (`SessionPoolStore.save`).
- `apps/worker_parser` — потребляет (`SessionPoolStore.acquire_session`).
- `apps/api` — читает статистику для наблюдения (`SessionPoolStore.get_live_sessions`,
  `GET /api/sessions/pool`).

## Почему это пакет, а не код внутри одного из воркеров

До выноса сюда эта логика была независимо реализована трижды: `RedisSessionStore`
(`apps/worker_sessions`), `RedisSessionClient` (`apps/worker_parser`), `SessionPoolReader`
(`apps/api`) — включая ключевые хелперы (`_session_key`/`_pool_key`), которые приходилось
синхронизировать вручную при любом изменении формата.

Отдельно — `SessionMessage`/`ProxyConfig` в `apps/worker_parser/src/entities.py` были явно
задокументированы как "intentional wire-contract duplicate" сущностей из
`apps/worker_sessions/src/entities.py`, потому что действовало правило "apps/* не импортируют
исходники друг друга, только `core`/`packages`". Правило осталось верным — но оно означало
"общий код должен жить в `packages`", а не "общий код недопустим". Перенос сюда убирает
дублирование, не нарушая правило: оба воркера по-прежнему не импортируют друг друга напрямую,
оба импортируют только `packages.sessions`.

`apps/worker_sessions/src/entities.py` и `apps/worker_parser/src/entities.py` теперь просто
реэкспортируют `ProxyConfig`/`SessionMessage` отсюда (`from packages.sessions.src.entities import
...`), чтобы не трогать импорты во всех файлах, которые уже ссылались на них по старому пути.

## Формат в Redis

- `session:{marketplace}:{session_id}` — `SET ... PX <ttl_ms>`, сериализованный `SessionMessage`
  (JSON). Исчезает сам по TTL — отдельного реапинга не требуется.
- `sessions:pool:{marketplace}` — `ZSET`, score = `expire_at` (unix-время). `ZPOPMIN` —
  атомарный single-consumer забор (`acquire_session`), `ZCOUNT`/`ZRANGEBYSCORE` — учёт глубины
  пула (`live_count`/`get_live_sessions`).

  TTL в Redis истекает у ключа целиком, а не у отдельного элемента `ZSET` — поэтому протухший по
  TTL `session:{marketplace}:{id}` не убирает сам себя из `sessions:pool:{marketplace}`. Раньше
  `acquire_session` полагался только на ленивую чистку (`ZPOPMIN` по одному, отбросить, если `PTTL`
  говорит, что сессия мертва) — при накоплении большого бэклога протухших записей (например,
  `worker_sessions` генерирует быстрее, чем `worker_parser` потребляет, пока тот не работал) это
  вычерпывалось пачками по `max_pop_attempts` с `EMPTY_POOL_BACKOFF_SECONDS` сна между вызовами —
  наблюдались многоминутные простои перед тем, как воркер добирался до живой сессии. Поэтому
  `acquire_session` теперь в начале делает один `ZREMRANGEBYSCORE` (score < now) — массово выкидывает
  все уже протухшие элементы одним запросом, до того как пытаться `ZPOPMIN`.
- `{stream_prefix}:{marketplace}` — Redis Stream, **дополнение** к TTL-пулу выше, не замена —
  источник истины по тому, жива ли сессия, остаётся `session:{marketplace}:{id}` с TTL. См.
  `apps/worker_sessions/AGENTS.md` за полным обоснованием.

## `SessionPoolStore`

Один класс на все три роли (`save`/`acquire_session`/`live_count`/`get_live_sessions`), а не три
отдельных класса — потому что все три метода работают с одним и тем же ключевым пространством, и
у любого изменения формата (например, что именно кладётся в `SET`) должно быть ровно одно место,
которое это знает.

Конструктор принимает `redis_config: RedisConfig` (не 4 отдельных скаляра) и строит клиента через
[`core.redis.get_redis_client`](../../core/redis.py) — общая для всех Redis-клиентов в проекте
фабрика (аналог `core.database.get_database_connection` для Postgres), вместо того чтобы каждый
потребитель заново собирал `redis.Redis(host=..., port=..., db=..., password=...)`.

TTL/лимиты (`ttl_ms`, `max_pop_attempts`, `min_ttl_margin_seconds`, `stream_maxlen`, ...) —
параметры методов, а не поля пакета: пакеты не импортируют `Config` приложений (только `core`),
поэтому вызывающая сторона (`apps/worker_sessions`/`apps/worker_parser`) передаёт значения из
своего собственного конфига явно.
