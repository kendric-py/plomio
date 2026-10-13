# packages/api_keys

API-ключи пользователя — доступ к API в обход фронтенда (интеграции, скрипты). Пользователь сам
выпускает ключи, задаёт им срок жизни и лимит кредитов, видит, сколько потратил каждый ключ, и
отзывает их. REST — [`apps/api/src/routers/api_keys`](../../apps/api/AGENTS.md#api-ключи).

## Модель (`ApiKey`, `api_keys`)

- `name`, `user_id` (FK `CASCADE`), `created_at`/`updated_at`.
- **Значение ключа не хранится.** Формат — `plm_` + 43 символа `secrets.token_urlsafe(32)`
  (`security.py`). В БД — `key_hash` (SHA-256, уникальный: по нему ключ находится одним индексным
  запросом; bcrypt не нужен — у ключа 256 бит случайности) и `prefix` (первые 12 символов, чтобы
  пользователь узнал ключ в списке). Значение отдаётся один раз — в ответе на создание.
- `credit_limit` — лимит трат **за всё время жизни ключа**, `NULL` — без лимита.
- `expires_at` — срок действия, `NULL` — бессрочный. При создании/изменении должен быть в будущем
  (`InvalidApiKeyExpiryError`).
- `revoked_at` — отзыв. Ключи **не удаляются**: по отозванному ключу остаётся статистика трат.
  Отозванный ключ нельзя изменить (`ApiKeyRevokedError`), повторный отзыв — no-op.
- `last_used_at` — последняя авторизация ключом, пишется не чаще раза в минуту
  (`LAST_USED_RESOLUTION`), чтобы запросы по ключу не писали в БД каждый раз.
- Статус (`ApiKeyStatus`: `ACTIVE`/`EXPIRED`/`REVOKED`) не хранится — `resolve_api_key_status`.
- Квота: не больше `MAX_ACTIVE_KEYS_PER_USER` (20) неотозванных ключей (`ApiKeyQuotaExceededError`).

## Учёт трат — через `packages/billing`

Потраченное по ключу не хранится счётчиком: у `credit_transactions` есть колонка `api_key_id`
(индекс), «потрачено» = сумма списаний по ней (`BillingService.get_spent_by_api_keys`, один
`GROUP BY` на список ключей). Зависимость однонаправленная: `api_keys → billing`.

Ключ доходит до списания так: работа, созданная запросом с ключом, запоминает его —
`Task.api_key_id`, `Automation.api_key_id` (проверочные задачи автоматизации наследуют ключ
автоматизации), а `BillingService.charge(api_key_id=...)` записывает его в журнал:

- задачи — `task.create` и инкрементальные `result.*` (`TaskService.record_item_progress`, его
  вызывает воркер, поэтому `ApiKeyService` собирается и в `apps/worker_parser/src/services.py`);
- автоматизации — `automation.create` и результаты всех её проверок;
- direct-запросы — `charge_direct_request` в `apps/api/src/routers/direct/dependencies.py`.

## Блокировка трат по ключу

`resolve_block_reason` — по ключу тратить нельзя, если он отозван/истёк
(`ApiKeyBlockReason.INACTIVE`) или потрачено `>= credit_limit` (`CREDIT_LIMIT`). Лимит «мягкий»,
как и баланс: последнее списание может его перешагнуть, дальше новые траты запрещены.

- `ensure_can_spend(api_key_id)` — guard перед новой тратой, рядом с
  `BillingService.ensure_can_spend(user_id)`: создание задачи/автоматизации (одиночное и массовое),
  direct-запрос, возобновление/перезапуск/исключение элемента задачи, созданной ключом. Ошибки —
  `ApiKeyCreditLimitExceededError`/`ApiKeyInactiveError`, **подклассы
  `InsufficientCreditsError`**: все обработчики 402 ловят их без изменений, отличается `detail`.
- `can_spend(api_key_id)` — после каждого списания результатов задачи: если нельзя, задача
  ставится на паузу (`TaskService._can_continue`, как при нулевом балансе).
- `get_blocked_api_key_ids(ids)` — батч для диспатча автоматизаций: проверка пропускается,
  `Automation.last_check_error = 'api_key_inactive' | 'api_key_credit_limit'`.

Итог: **отзыв, истечение или исчерпание лимита ключа останавливает все траты по нему** — новые
запросы, идущие задачи и проверки автоматизаций, созданных ключом. Чтобы автоматизация,
созданная ключом, работала дальше, ключ должен оставаться действующим (продлить срок, поднять лимит)
— переназначить её на другой ключ пока нельзя.

## Авторизация

`authenticate(raw_key)` — ключ по значению: неизвестный → `InvalidApiKeyError`, отозванный →
`ApiKeyRevokedError`, истёкший → `ApiKeyExpiredError` (все → 401 в REST). Лимит здесь не
проверяется: исчерпанный ключ читает данные, запрещены только траты. REST-зависимости —
`apps/api/src/routers/auth/dependencies.py` (`get_auth_context`, см. `apps/api/AGENTS.md`).
Управлять ключами и заходить в админку можно только из сессии фронтенда (JWT), не ключом.

## Аудит

Создание, изменение и отзыв ключа пишутся в `audit_logs` (`AuditAction.API_KEY_CREATE`/
`API_KEY_UPDATE`/`API_KEY_REVOKE`, `target_type='ApiKey'`), значение ключа — никогда.
