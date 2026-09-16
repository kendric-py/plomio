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

## `core`

Общая инфраструктура, переиспользуемая всеми `apps/*` и `packages/*`:

- **`core/database.py`** — `BaseSQLModel` (декларативная база SQLAlchemy-моделей).
- **`core/configs.py`** — конфиги через `pydantic-settings` (`PostgresConfig`, `AuthConfig`).
- **`core/exceptions.py`** — общие исключения уровня БД: `DuplicatedObjectError`,
  `ObjectNotFoundError`.
- **`core/repository.py`** — `BaseRepositoryInterface`/`BaseRepository[DataBaseObject, EntityObject]`:
  базовый generic-репозиторий поверх `AsyncSession`. Конвертирует SQLAlchemy-модель в pydantic-entity
  (`from_attributes=True`) и обратно. Даёт `create`/`get_by_id`/`retrieve_all`/`update`/`delete`/
  `retrieve_all_by_filter`. Репозиторий доменной области наследует его и добавляет специфичные для
  домена методы выборки (пример — `UserRepository` в `packages/user`).

## Пакеты

- **`packages/user`** — доменные модели пользователя сервиса SMPCrawl (клиент/администратор).
- **`packages/membership`** — доменная область подписок/тарифов пользователя (заглушка).
- **`packages/api_keys`** — доменная область API-ключей пользователя (заглушка).
- **`packages/auth`** — доменная область авторизации и регистрации пользователей (хэширование
  пароля, JWT access-токены, сценарии `register_user`/`authenticate_user`).

## Правила кода

См. [`gold-rules.md`](./gold-rules.md) и [`anti-patterns.md`](./anti-patterns.md).

> TODO: описать структуру слоёв приложения (роутеры/сервисы/репозитории и т.д.), конвенции по тестам,
> линтерам и форматтерам, когда они появятся в проекте.
