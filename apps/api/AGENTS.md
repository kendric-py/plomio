# apps/api

REST API. Точка входа для клиентов (фронтенд, внешние интеграции) и администраторов.

## Роуты

`src/routers/router.py::api_router` — глобальный роут `/api`, к которому подключаются все
остальные роутеры (`api_router.include_router(...)`). Это единственная точка входа в
`configure_rest_server` — сам `FastAPI()` инклюдит только `api_router`, не отдельные роутеры доменов
напрямую.

- `routers/auth/endpoints.py` + `routers/auth/schema.py` (`/api/auth`):
  - `GET /status` — `{"has_users": bool}`. Публичный, без авторизации — фронт вызывает его перед
    показом экрана логина, чтобы решить: показывать логин или «зарегистрируйте администратора» (если
    `has_users == false`).
  - `POST /register`, `POST /login`. Оба дергают `AuthService` через DI
    (`Depends(Provide[DependencyContainer.auth_service])`), на успехе выпускают JWT
    (`packages.auth.src.security.create_access_token`) и возвращают `TokenResponse`.
    `UserAlreadyExistsError` → 409, `InvalidCredentialsError` → 401. Первый зарегистрированный в
    пустой системе получает роль `ADMIN` (логика — в `AuthService.register_user`, не в роутере).
- `routers/user/endpoints.py` + `routers/user/schema.py` (`/api/user`):
  - `GET /` — заглушка `{"message": "Hello World"}`.
  - `GET /me` — требует авторизации (`Depends(get_current_user)`), возвращает `UserResponse` текущего
    пользователя.

Новый роутер домена: создать `routers/<domain>/endpoints.py` с `router = APIRouter(prefix='/<domain>',
tags=[...])`, подключить в `routers/router.py` через `api_router.include_router(router=...)`. Если
роутер использует `@inject`/`Provide[...]` (напрямую или через зависимость вроде `get_current_user`,
которая сама `@inject`) — добавить путь модуля в `container.wire(modules=[...])` в
`configure_rest_server` (`src/server.py`), иначе DI не сработает.

**Pydantic-схемы запросов/ответов REST — в `routers/<domain>/schema.py`, не в `packages/<domain>/`.**
Домен (`packages/*`) не знает про REST-транспорт; схема — контракт конкретного роута этого app. См.
[правило в gold-rules.md](../../docs/reference/gold-rules.md#rest-схемы).

## Авторизация в Swagger

`routers/auth/dependencies.py::get_current_user` — FastAPI-зависимость `HTTPBearer()` +
`packages.auth.src.security.decode_access_token` + `UserService.get_by_id`. Любой эндпоинт с
`Depends(get_current_user)` автоматически получает схему безопасности `HTTPBearer` в OpenAPI — в
Swagger UI (`/docs`) появляется кнопка **Authorize**, куда вставляется access-токен
(`Bearer <access_token>`, полученный из `POST /api/auth/login`/`register`), и дальше он подставляется
во все защищённые запросы из UI. Невалидный/просроченный токен или несуществующий пользователь → 401.

Модуль `routers/auth/dependencies.py` добавлен в `container.wire(modules=[...])` в `src/server.py` —
без этого `Depends(Provide[...])` внутри `get_current_user` не резолвится.

## DI-контейнер

`src/container.py` — `DependencyContainer(DeclarativeContainer)`, собственный для этого app (у
каждого `apps/*`, которому он нужен, — свой контейнер, общего контейнера в `core/` нет).

- `session_factory` — `async_sessionmaker`, полученный через
  [`core.database.get_database_connection(config=...)`](../../core/database.py) от `apps.api.src.config.config`
  (`config.POSTGRES`).
- `transaction_manager` — [`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py).
- `user_service` — [`packages.user.src.service.UserService`](../../packages/user/AGENTS.md#сервис).
- `auth_service` — [`packages.auth.src.service.AuthService`](../../packages/auth/AGENTS.md).

Контейнер создаётся в `src/server.py::configure_rest_server` и кладётся в `app.container`.
`container.wire(modules=['apps.api.src.routers.auth.endpoints'])` — `routers/auth/endpoints.py`
использует `@inject`/`Provide[...]`, `routers/user/endpoints.py` пока нет (заглушка без DI).

> TODO: `user_service` пока не используется ни одним роутером (`routers/user/endpoints.py` —
> заглушка) — когда появятся реальные эндпоинты профиля, подключить через
> `Depends(Provide[DependencyContainer.user_service])` и добавить модуль в `container.wire(modules=[...])`.

## Конфигурация

`src/config.py::Config` — `REST` (host/port/title) и `POSTGRES` (`core.configs.PostgresConfig`).
Значения из `.env` (см. `.env.example`): `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_DB`,
`POSTGRES_USER`, `POSTGRES_PASSWORD`, `AUTH_SECRET_KEY`, `AUTH_ALGORITHM`,
`AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`.

`.env` резолвится по абсолютному пути (`config.py::ENV_FILE = Path(__file__).resolve().parent.parent
/ '.env'`), а не относительно cwd — иначе `Config()`/`PostgresConfig()` ищут `.env` там, откуда
запущена команда (`poetry run ...`), а не в `apps/api/`, и падают с ошибкой валидации, если этот
каталог — не `apps/api/` (ровно так и ломался alembic, пока не переехал в корень — см. ниже).

## Локальный Postgres

`docker-compose.dev.yml` в корне репозитория поднимает dev-Postgres на **порту хоста 5433** (не 5432
— чтобы не конфликтовать с другими Postgres-контейнерами на машине разработчика), с кредами
`postgres`/`postgres`/`smpcrawl`, совпадающими со значениями по умолчанию в `.env.example`:

```
docker compose -f docker-compose.dev.yml up -d
```

## Миграции (Alembic)

`alembic.ini` + `alembic/` — в **корне репозитория** (глобальный скоуп), не внутри `apps/api/`.
Причина не в самих миграциях (они всё равно только про БД `apps/api`, единственного app с БД), а в
том, что репозиторий уже так устроен: `core.*`/`packages.*.src.*` — абсолютные импорты от корня
репозитория, и alembic как инструмент, который обходит все доменные области ради `target_metadata`,
естественно живёт на этом же уровне, а не внутри одного конкретного app.

- `alembic/env.py` — асинхронный шаблон (`async_engine_from_config` + `connection.run_sync`), URL
  берётся из `apps.api.src.config.config.POSTGRES.DSN` (не дублируется в `alembic.ini`),
  `target_metadata = core.database.BaseSQLModel.metadata`. Модели из доменных областей
  (`packages/user`, `packages/membership`, `packages/api_keys`) импортируются в `env.py` только ради
  побочного эффекта — регистрации таблиц в `BaseSQLModel.metadata` — иначе autogenerate их не увидит.
- Команды выполняются из **корня репозитория** через poetry-окружение `apps/api` (там установлен
  `alembic`+`asyncpg`; свой отдельный `pyproject.toml` для alembic не заводили):

```
poetry -C apps/api run alembic revision --autogenerate -m "message"
poetry -C apps/api run alembic upgrade head
poetry -C apps/api run alembic downgrade -1
```

  Если появится второй app со своей БД — у него будет свой `PostgresConfig`/своя `DSN`, но
  таблицы/модели физически разных БД всё равно не должны пересекаться в одном `target_metadata`
  — тогда этот alembic-каталог нужно будет либо параметризовать (`-x db=...`), либо завести второй,
  решать по факту, когда появится второй app с БД.

- `alembic/versions/589dc8c271ea_initial.py` — первая миграция (`users`, `api_keys`, `memberships`).
  В `downgrade()` после `op.drop_table('users')` явно дропается Postgres ENUM `userrole`
  (`sa.Enum(name='userrole').drop(...)`) — `drop_table` сам его не удаляет, и без этой строки
  следующий `upgrade` падает с `type "userrole" already exists`. Держать это в уме при написании
  будущих миграций, если в модели добавляется/меняется `sqlalchemy.Enum`-колонка.
