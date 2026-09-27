# packages/cron

Generic-обвязка для периодических job'ов, выполняемых на event loop приложения (`asyncio.sleep` в
цикле), а не отдельным процессом и не внешним планировщиком (cron/systemd timer/k8s CronJob). Сам
по себе `packages/cron` не про расписание "секунды/минуты/часы" — это тривиально решается
`asyncio.sleep`. Это про то, что общее для *любого* такого job'а: запуск на интервале, журнал
каждого прогона (успех/провал/детали), устойчивость к исключению внутри job'а (одна неудачная
итерация не должна убивать весь цикл).

## Почему это домен, а не просто функция в apps/api

В проекте было минимум два независимых потребителя одного и того же паттерна "выполнить и
залогировать запуск периодического job'а" — heartbeat-проверка (`packages/worker_health`) и
`TaskService.reclaim_expired_leases()` (`packages/task/AGENTS.md`, "вызывается снаружи периодически
(планировщиком)"). Это генерализовано в отдельную область, а не продублировано в каждом job'е.

Подключены (запускаются через `apps/api/src/server.py` lifespan, `asyncio.create_task` +
`run_periodic`): `WORKER_HEARTBEAT_SWEEP` (`apps/api/src/jobs/worker_heartbeat_sweep.py`),
`TASK_EXPIRY_SWEEP` (`apps/api/src/jobs/task_expiry_sweep.py`), `TASK_LEASE_RECLAIM_SWEEP`
(`apps/api/src/jobs/task_lease_reclaim_sweep.py` → `TaskService.reclaim_expired_leases()`,
`config.TASK.LEASE_RECLAIM_SWEEP_INTERVAL_SECONDS`), `AUTOMATION_DISPATCH`,
`AUTOMATION_RESULT_SWEEP`, `AUTOMATION_HISTORY_RETENTION_SWEEP`.

`TASK_LEASE_RECLAIM_SWEEP` было исторически "документировано, но не подключено" — задача, у
которой воркер упал/потерял heartbeat, зависала в `RUNNING` навсегда (`lease_expires_at` истекал,
но никто не переводил её обратно в `QUEUED`). Для проверочной задачи автоматизации это дополнительно
блокировало саму автоматизацию: пока `pending_task_id` указывает на такую зависшую задачу,
`AutomationRepository.claim_due_for_dispatch` не берёт эту автоматизацию в новый цикл (см.
[`packages/automation/AGENTS.md`](../automation/AGENTS.md)) — автоматизация молча переставала
проверяться вовсе, без явной ошибки.

## Модель `CronJobRun`

Append-only лог прогонов (как `AuditLog`/`WorkerHeartbeatLog`): `job` (`CronJobName` — единый
реестр, новый job сначала регистрируется в `enums.py`), `status` (`SUCCESS`/`FAILURE`),
`started_at`/`finished_at`, `details` (JSONB, произвольная сводка от самого job'а — например,
сколько воркеров проверено), `error_reason` (текст исключения при `FAILURE`).

Это лог состояния *самой проверки* (тикает ли планировщик, не падает ли) — отдельный от
доменных логов конкретных job'ов (`worker_heartbeat_logs` логирует состояние *воркеров*, не
планировщика).

## `scheduler.py::run_periodic`

```python
await run_periodic(CronJobName.WORKER_HEARTBEAT_SWEEP, interval_seconds, func, cron_job_service)
```

Бесконечный цикл `while True: await asyncio.sleep(interval); ...`. Исключение внутри `func()`
перехватывается и пишется как `FAILURE` — цикл продолжает тикать дальше. Запускается вызывающим
кодом через `asyncio.create_task(...)` в `lifespan` FastAPI-приложения; останавливается через
`task.cancel()` при shutdown.

## Несколько реплик apps/api

`run_periodic` не координирует несколько инстансов между собой — при N репликах `apps/api` каждая
крутит свой независимый таск с одинаковым интервалом. Для `WORKER_HEARTBEAT_SWEEP` это безопасно,
потому что дедупликация самой записи о переходе состояния сделана на уровне
`WorkerHeartbeatStore` (атомарные Redis `SADD`/`SREM`, см. `packages/worker_health/AGENTS.md`), а
не на уровне "кто именно выполняет проверку". Для `TASK_EXPIRY_SWEEP`/`TASK_LEASE_RECLAIM_SWEEP`
безопасно по другой причине: `TaskRepository.expire_stale_queued`/`reclaim_expired_leases` — это
каждый одно `UPDATE ... WHERE status = ... AND <дедлайн> <= now()`, идемпотентное на уровне SQL —
несколько реплик, выполнившие его одновременно, просто переведут одно и то же (уже
не удовлетворяющее `WHERE` после первого `UPDATE`) множество строк, без двойной обработки одной
строки и без гонки за "кто именно выполняет проверку".
