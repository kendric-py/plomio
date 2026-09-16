# packages/auth

Доменная область авторизации и регистрации пользователей SMPCrawl. Работает поверх модели `User`
из [`packages/user`](../user/AGENTS.md).

## Состав

- **`security.py`** — хэширование пароля (`hash_password`, `verify_password`, `bcrypt`) и работа с
  JWT access-токеном (`create_access_token`, `decode_access_token`). Секрет/алгоритм/срок жизни
  токена берутся из `AuthConfig` (`core/configs.py`, переменные окружения с префиксом `AUTH_`:
  `AUTH_SECRET_KEY`, `AUTH_ALGORITHM`, `AUTH_ACCESS_TOKEN_EXPIRE_MINUTES`).
- **`schemas.py`** — pydantic-схемы запросов/ответов: `RegisterRequest`, `LoginRequest`,
  `TokenResponse`.
- **`service.py`** — сценарии домена, работают с `AsyncSession` через
  [`UserRepository`](../user/AGENTS.md#репозиторий) (`packages/user`), возвращают `UserEntity`:
  - `register_user` — создаёт пользователя с ролью `UserRole.CLIENT`, хэширует пароль, кидает
    `UserAlreadyExistsError`, если email уже занят (проверка + перехват гонки по уникальному
    ограничению БД через `core.exceptions.DuplicatedObjectError`).
  - `authenticate_user` — проверяет email/пароль, обновляет `last_active_at`, кидает
    `InvalidCredentialsError` при неверных данных.
- **`exceptions.py`** — доменные исключения: `UserAlreadyExistsError`, `InvalidCredentialsError`,
  `InvalidTokenError`.

## Что не входит в эту реализацию

Это только доменная логика. В проекте пока нет подключения к БД (`AsyncSession`/`Depends`) и
Alembic-миграций для таблицы `users`, поэтому в `packages/auth` **нет** REST-роутов, FastAPI-зависимостей
(`get_current_user` и т.д.) и refresh-токенов — только access-токен.

> TODO: при появлении в `apps/api` подключения к БД — добавить роутер `/auth/register`, `/auth/login`,
> зависимость получения текущего пользователя из access-токена, и решить, нужны ли refresh-токены.
