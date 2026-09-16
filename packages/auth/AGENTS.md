# packages/auth

Доменная область авторизации и регистрации пользователей SMPCrawl. Работает поверх модели `User`
из [`packages/user`](../user/AGENTS.md).

## Состав

- **`security.py`** — хэширование пароля (`hash_password`, `verify_password`, `bcrypt`) и работа с
  JWT access-токеном (`create_access_token`, `decode_access_token`). Секрет/алгоритм/срок жизни
  токена берутся из `AuthConfig` (`core/configs.py`, переменные окружения с префиксом `AUTH_`:
  `AUTH_SECRET_KEY`, `AUTH_ALGORITHM`, `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`).
- **`service.py`** — `AuthService(transaction_manager: AsyncTransactionManager)`, возвращает
  `UserEntity`. Работает с БД так же, как [`UserService`](../user/AGENTS.md#сервис) — через
  [`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py)
  (`transaction_manager(use_user_repository=True)`), а не через `UserService` напрямую: это
  сознательное решение, чтобы весь сценарий (проверка email → создание/обновление пользователя)
  выполнялся в одной БД-транзакции, а не в отдельных транзакциях каждого сервиса (если бы `AuthService`
  дергал методы `UserService`, каждый вызов открывал бы свою собственную транзакцию — см.
  [`core/transaction_manager.py`](../../core/transaction_manager.py)).
  - `register_user` — создаёт пользователя, хэширует пароль, кидает `UserAlreadyExistsError`, если
    email уже занят (проверка + перехват гонки по уникальному ограничению БД через
    `core.exceptions.DuplicatedObjectError`). **Первый пользователь в пустой системе получает роль
    `UserRole.ADMIN`** (иначе — `UserRole.CLIENT`) — так после чистого деплоя всегда есть способ
    администрировать систему без отдельного bootstrap/seed-шага. Проверка «пуста ли таблица»
    (`user_repository.exists()`) и `create` — в одной транзакции, но **не race-safe** при
    одновременной регистрации на пустой таблице (два параллельных запроса оба могут стать ADMIN) —
    приемлемо для одноразового bootstrap-действия, не для обычного потока регистрации.
  - `authenticate_user` — проверяет email/пароль, обновляет `last_active_at`, кидает
    `InvalidCredentialsError` при неверных данных.
  - `has_users` — есть ли хотя бы один пользователь (`user_repository.exists()`). Нужен фронту, чтобы
    решить, показывать форму логина или «зарегистрируйте администратора» (см. `GET /api/auth/status`).
- **`exceptions.py`** — доменные исключения: `UserAlreadyExistsError`, `InvalidCredentialsError`,
  `InvalidTokenError`.

## REST

`AuthService` собирается в DI-контейнере `apps/api`
([`apps/api/src/container.py`](../../apps/api/AGENTS.md#di-контейнер)) и используется роутером
`GET /api/auth/status`, `POST /api/auth/register`, `POST /api/auth/login`
([`apps/api/src/routers/auth/endpoints.py`](../../apps/api/AGENTS.md#роуты)). `register`/`login` на
успехе выпускают access-токен и возвращают `TokenResponse`; `status` возвращает
`{"has_users": bool}` — фронт вызывает его перед показом экрана логина/регистрации, и если
`has_users == false`, показывает не логин, а «зарегистрируйте администратора» (первый
зарегистрированный после этого получит роль `ADMIN`, см. `register_user` выше).

Pydantic-схемы запросов/ответов (`RegisterRequest`, `LoginRequest`, `TokenResponse`) в этой доменной
области не живут — это REST-контракт конкретного app, а не доменная логика. Они лежат в
`apps/api/src/routers/auth/schema.py`, см.
[правило в gold-rules.md](../../docs/reference/gold-rules.md#rest-схемы).

Зависимость получения текущего пользователя из access-токена — `get_current_user` в
`apps/api/src/routers/auth/dependencies.py` (декодирует токен через `security.decode_access_token`,
поднимает `UserEntity` через `UserService`); она же регистрирует схему `HTTPBearer` в OpenAPI, из-за
чего в Swagger UI (`/docs`) появляется кнопка Authorize — см.
[`apps/api/AGENTS.md`](../../apps/api/AGENTS.md#авторизация-в-swagger). `require_roles`
(проверка роли, не только наличия пользователя) и refresh-токены — всё ещё нет, только access-токен.

> TODO: `require_roles([UserRole.ADMIN])` — зависимость поверх `get_current_user`, отклоняющая запрос
> по роли (403), когда появятся эндпоинты, доступные только администратору; решить, нужны ли
> refresh-токены.
