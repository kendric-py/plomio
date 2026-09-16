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
