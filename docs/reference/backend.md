# Backend

## Стек

- Python 3.12, Poetry (монорепо, workspaces по `apps/*` + общий `src/shared`).
- FastAPI — `apps/api`.
- `pydantic-settings` — конфигурация приложений через `.env` (см. `core/configs.py`).
- PostgreSQL + `asyncpg` — основное хранилище.
- Alembic — миграции БД.

## Приложения

- **`apps/api`** — REST API. Создание задач, отдача результатов, управление пользователями/тарифами
  (роль администратора).
- **`apps/worker-parser`** — исполнение задач парсинга OZON и Wildberries.
- **`apps/worker-sessions`** — генерация сессий (куки, заголовки, прокси) для `worker-parser`.

## Пакеты

- **`packages/user`** — доменные модели пользователя сервиса SMPCrawl (клиент/администратор).

## Правила кода

См. [`gold-rules.md`](./gold-rules.md) и [`anti-patterns.md`](./anti-patterns.md).

> TODO: описать структуру слоёв приложения (роутеры/сервисы/репозитории и т.д.), конвенции по тестам,
> линтерам и форматтерам, когда они появятся в проекте.
