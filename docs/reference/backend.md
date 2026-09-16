# Backend

## Стек

- Python 3.12, Poetry (монорепо, workspaces по `apps/*` + общий `src/shared`).
- FastAPI — `apps/api`.
- `pydantic-settings` — конфигурация приложений через `.env` (см. `core/configs.py`).
- PostgreSQL + `asyncpg` — основное хранилище. Локально поднимается через
  `docker compose -f docker-compose.dev.yml up -d` (порт хоста — 5433, см.
  [`apps/api/AGENTS.md`](../../apps/api/AGENTS.md#локальный-postgres)).
- Alembic — миграции БД. `alembic.ini`/`alembic/` — в **корне репозитория** (глобальный скоуп, не
  внутри `apps/api/`), т.к. `target_metadata` собирается из моделей всех доменных областей
  (`packages/*`), см. [`apps/api/AGENTS.md`](../../apps/api/AGENTS.md#миграции-alembic).

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
  `retrieve_all_by_filter`/`exists`. Репозиторий доменной области наследует его и добавляет
  специфичные для домена методы выборки (пример — `UserRepository` в `packages/user`).
- **`core/transaction_manager.py`** — `AsyncTransactionManager(session_factory)`: асинхронный
  контекст-менеджер, на входе в `async with` открывает `AsyncSession` и поднимает только запрошенные
  репозитории (`transaction_manager(use_user_repository=True)`), на выходе — коммитит и закрывает
  сессию (или откатывает при исключении). Сервисы доменных областей (например, `UserService` в
  `packages/user`) работают с БД только через него, не держат `AsyncSession` напрямую. Список
  доступных репозиториев — реестр `REPOSITORIES` в этом же модуле; при добавлении репозитория в новую
  доменную область его нужно зарегистрировать там же.
- **`dependency-injector`** — установлен как зависимость `apps/api`. У каждого app — свой DI-контейнер
  (`DeclarativeContainer`) в `apps/<app>/src/container.py`, собирается из его собственного `config`
  (`core.database.get_database_connection(config=...)` → `async_sessionmaker`). Общей инфраструктуры
  для контейнера в `core/` нет и не нужно — `core/transaction_manager.py` и сервисы `packages/*`
  общие, а конкретная сборка (какой config, какие сервисы нужны) — дело каждого app. См.
  `apps/api/src/container.py`.

## Пакеты

- **`packages/user`** — доменные модели пользователя сервиса SMPCrawl (клиент/администратор).
- **`packages/membership`** — доменная область подписок/тарифов пользователя (заглушка).
- **`packages/api_keys`** — доменная область API-ключей пользователя (заглушка).
- **`packages/auth`** — доменная область авторизации и регистрации пользователей (хэширование
  пароля, JWT access-токены, сценарии `register_user`/`authenticate_user`/`has_users`). Первый
  зарегистрированный пользователь в пустой системе получает роль `ADMIN`.

## Правила кода

См. [`gold-rules.md`](./gold-rules.md) и [`anti-patterns.md`](./anti-patterns.md).

> TODO: описать структуру слоёв приложения (роутеры/сервисы/репозитории и т.д.), конвенции по тестам,
> линтерам и форматтерам, когда они появятся в проекте.
