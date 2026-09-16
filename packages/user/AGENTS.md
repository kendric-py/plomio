# packages/user

Доменная область пользователя сервиса SMPCrawl (клиент/администратор).

## Модель `User`

- `id` — первичный ключ.
- `display_name` — отображаемое имя.
- `email` — email, уникален.
- `hashed_password` — хэш пароля.
- `role` — роль пользователя, `UserRole` (`CLIENT`, `ADMIN`).
- `telegram_id` — `BIGINT`, nullable, Telegram ID пользователя (для уведомлений).
- `last_active_at` — время последней активности.
- `created_at` — время создания.
- `memberships` — связь с доменной областью [`packages/membership`](../membership/AGENTS.md):
  подписки/тарифы пользователя (в том числе действующая на данный момент).
- `api_keys` — связь с доменной областью [`packages/api_keys`](../api_keys/AGENTS.md):
  API-ключи пользователя.

> TODO: описать правила смены роли, условия признания подписки активной, жизненный цикл API-ключей —
> по мере проработки доменных областей `membership` и `api_keys`.

## Репозиторий

- **`entities.py`** — `UserEntity`, pydantic-DTO модели `User` (все поля опциональны — используется и
  для чтения, и как патч для частичного обновления через `BaseRepository.update`).
- **`repository.py`** — `UserRepository(BaseRepository[User, UserEntity])`, наследует CRUD
  (`create`/`get_by_id`/`retrieve_all`/`update`/`delete`/`retrieve_all_by_filter`) от
  [`core.repository.BaseRepository`](../../core/repository.py) и добавляет `get_by_email`,
  `get_by_telegram_id`.

Используется в [`packages/auth`](../auth/AGENTS.md).

## Сервис

- **`service.py`** — `UserService(transaction_manager: AsyncTransactionManager)`: профильные
  операции над пользователем — `get_by_id`, `get_by_email`, `retrieve_all`, `update`, `delete`.
  Работает с БД только через
  [`core.transaction_manager.AsyncTransactionManager`](../../core/transaction_manager.py)
  (`transaction_manager(use_user_repository=True)` открывает `AsyncSession` и поднимает
  `UserRepository`), не держит `AsyncSession` напрямую.

  Регистрация/аутентификация (хэширование пароля, JWT) в этот сервис не входят — это отдельная
  доменная область [`packages/auth`](../auth/AGENTS.md). `AuthService` не инжектит `UserService` и не
  зовёт его методы: он сам владеет `AsyncTransactionManager` и работает с `UserRepository` напрямую —
  так весь сценарий регистрации/логина выполняется в одной БД-транзакции, а не в отдельной транзакции
  на каждый вызов `UserService`.
