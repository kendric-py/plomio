# Архитектура

## Компоненты

- **`apps/api`** — REST API. Точка входа для клиентов (фронтенд, внешние интеграции) и администраторов.
  Создаёт задачи (единоразовые и периодические) и отдаёт результаты.
- **`apps/worker_parser`** — исполняет задачи парсинга OZON и Wildberries. Забирает задачи из очереди,
  запрашивает сессию у `worker_sessions`, шлёт heartbeat.
- **`apps/worker_sessions`** — генерирует сессии (куки, заголовки, прокси) для работы `worker_parser`
  с маркетплейсами.
- **Scheduler** — периодически ставит в очередь очередной запуск для периодических задач (мониторинг
  цены и т.д.).

  > TODO: уточнить, это отдельный процесс/приложение или часть `apps/api` / cron внутри инфраструктуры.

## Поток данных

```
Клиент (фронтенд / API) ──> apps/api ──> задача создаётся
                                            │
                                            ▼
                           очередь задач (таблицы PostgreSQL)
                                            │
                     scheduler повторно ставит периодические задачи
                                            │
                                            ▼
                                  apps/worker_parser забирает задачу
                                            │
                              запрашивает сессию ──> apps/worker_sessions
                                            │
                                   выполняет парсинг OZON / Wildberries
                                            │
                          HTTP heartbeat (статус) ──> apps/api (POST /api/worker-health/*)
                                            │
                                            ▼
                                результат сохраняется в PostgreSQL
```

## Очередь задач

Очередь реализована **поверх таблиц PostgreSQL** (не отдельный брокер сообщений вроде RabbitMQ/Kafka).

> TODO: описать схему таблиц очереди, механизм блокировки/захвата задачи воркером (`SELECT ... FOR UPDATE
> SKIP LOCKED`?), приоритизацию.

## Heartbeat

Решено (см. [`packages/worker_health`](../../packages/worker_health/AGENTS.md) за полным
контрактом): каждый воркер (`worker_parser`, `worker_sessions`) отправляет `POST` с телом
`{"worker_name": ..., "status": ...}` на `apps/api` (`POST /api/worker-health/{parser,sessions}
/heartbeat`) раз в `LIVENESS_INTERVAL_SECONDS`. `apps/api` не пишет каждый heartbeat в Postgres —
последний heartbeat живёт в Redis, а периодическая проверка на event loop `apps/api`
(`packages/cron`) детектирует пропуск (`WORKER_HEALTH_MISSED_THRESHOLD_SECONDS`) и пишет
переход `MISSED`/`RECOVERED` в БД (`worker_heartbeat_logs`). Текущий статус всех воркеров —
`GET /api/worker-health/workers`.

Тело запроса сейчас — только `worker_name`+`status`, без списка текущих задач (это было в
изначальной идее, но не реализовано — при необходимости расширяется отдельно).

`worker_sessions` отправляет свой собственный, независимый процесс-уровневый heartbeat (имя воркера
из `.env`, статус готов/генерирует/ждёт прокси) на тот же `apps/api` (`POST /api/worker-health
/sessions/heartbeat`) — тем же общим механизмом, что и `worker_parser` (оба используют один
`LivenessReporter` из `packages/worker_health`). См.
[`apps/worker_sessions/AGENTS.md`](../../apps/worker_sessions/AGENTS.md).

## Взаимодействие worker_parser ↔ worker_sessions

Решено полностью: `worker_sessions` пишет сгенерированные сессии в Redis (`session:{marketplace}:{id}`
с TTL на ключе, `sessions:pool:{marketplace}` — `ZSET` для учёта глубины пула), `worker_parser`
атомарно забирает их прямым чтением Redis (`ZPOPMIN`, не HTTP-ручка на `worker_sessions`) —
`SessionPoolStore.acquire_session`, общий для обоих воркеров класс в
[`packages/sessions`](../../packages/sessions/AGENTS.md). Подробности —
[`apps/worker_sessions/AGENTS.md`](../../apps/worker_sessions/AGENTS.md) и
[`apps/worker_parser/AGENTS.md`](../../apps/worker_parser/AGENTS.md).

## Хранение данных

- PostgreSQL — основное хранилище задач и результатов.
- Redis — эфемерный пул сессий `worker_sessions` (TTL, не постоянное хранилище — см.
  [`apps/worker_sessions/AGENTS.md`](../../apps/worker_sessions/AGENTS.md)).
- Срок хранения результата единоразовой задачи — **7 дней**.
- Срок хранения результата периодической задачи — задаёт администратор.
- Миграции — **Alembic**.

## Роли и доступ

- **Клиент** — фронтенд (постановка задач) и/или API.
- **Администратор** — управляет тарифами/квотами пользователей, сроком хранения результатов периодических
  задач, отдельный аккаунт/API-доступ.

Квоты на частоту парсинга применяются не к воркерам, а к пользователям — через тарифы, которые выдаёт
администратор.
