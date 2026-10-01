# packages/billing

Доменная область кредитной тарификации Plomio. Тарифов/подписок нет — у каждого пользователя один
общий баланс кредитов (`CreditWallet`), правила ценообразования общие для всех и полностью
настраиваются администратором через таблицы, без деплоя кода.

Отдельно от [`packages/membership`](../membership/AGENTS.md) — та доменная область остаётся
заглушкой под возможные будущие подписки, эта система на неё не опирается.

## Модель — "конструктор"

Ключевое требование: новое тарифицируемое действие или новый множитель стоимости добавляется без
миграции схемы — только новой строкой в одной из двух таблиц, плюс (для нового *действия*, а не
цены на уже существующее) одной точкой вызова `BillingService.charge(...)` в коде домена.

- **`BillingAction`** (`billing_actions`) — каталог действий: `action_code` (уникальный,
  человекочитаемый код — `"task.create"`, `"automation.create"`,
  `"result.<ParseType>"` — по одной строке на каждый `ParseType`
  [`packages/task/src/enums.py`](../task/src/enums.py)), `base_cost` (цена за единицу в кредитах,
  `0` — действие бесплатно), `unit_label` (для UI).
- **`PricingMultiplierRule`** (`pricing_multiplier_rules`) — множитель `base_cost` по диапазону
  значений произвольного измерения (`dimension_code`, `value_min`..`value_max` включительно,
  `multiplier`). Одна таблица для всех измерений, текущих и будущих — `"task_priority"`
  (диапазон вырождается в точку, `priority` уже дискретен, 1..10) и
  `"automation_check_frequency"` (реальный диапазон минут: `15–29`, `30–59`, `60–…`) заданы сейчас
  ([`packages/billing/src/enums.py::PricingDimension`](./src/enums.py) — не исчерпывающий список,
  просто общие константы для двух известных вызывающих доменов). Непересечение диапазонов в рамках
  одного `dimension_code` проверяет `BillingService.create_pricing_rule`
  (`PricingMultiplierRuleRepository.has_overlap`), не БД-констрейнт — для `exclusion constraint`
  по диапазону в Postgres нужно расширение `btree_gist`, которого в проекте нет. Если для
  `(dimension_code, value)` не нашлось правила — множитель `1.00` (не ошибка): нетронутое админом
  измерение не блокирует тарификацию.

Формула: `credits = ceil(base_cost(action_code) × multiplier(dimension_code, dimension_value) ×
quantity)` — округление вверх, чтобы дробный множитель никогда не давал бесплатные результаты.

- **`CreditWallet`** (`credit_wallets`) — текущий баланс, PK = `user_id`. Источник правды для
  быстрого чтения баланса (не пересчитывается по журналу на каждый запрос). **Может уйти в
  минус** — `BillingService.charge` никогда не бросает исключение из-за нехватки кредитов, минус
  разрешён осознанно (см. "Блокировка при недостатке кредитов" ниже).
- **`CreditTransaction`** (`credit_transactions`) — append-only журнал, тот же принцип, что
  `automation_history` для истории проверок: одна строка на одно списание/начисление, никогда не
  обновляется. `balance_after` — снэпшот баланса сразу после этой строки (без пересчёта при чтении
  истории). `transaction_metadata` (не `metadata` — зарезервировано на `Base.metadata` в
  SQLAlchemy) хранит полную расшифровку расчёта (`quantity`/`unit_cost`/`multiplier`/
  `dimension_code`/`dimension_value`) либо комментарий администратора для ручного начисления.

## `BillingService` — два generic-метода, все домены зовут только их

- **`charge(user_id, action_code, quantity=1, dimension_code=None, dimension_value=None,
  reference_type=None, reference_id=None)`** — атомарно (одна транзакция,
  `SELECT ... FOR UPDATE` на `credit_wallets` через `CreditWalletRepository.lock_or_create`, тот
  же паттерн блокировки строки, что `TaskRepository.lock_by_id`) списывает и пишет журнал.
  No-op (возвращает `None`, ничего не пишет), если действия нет в каталоге, его `base_cost == 0`,
  `quantity <= 0` или итоговая сумма после округления — `0`.
- **`grant(user_id, amount, admin_id, comment)`** — начисление, та же блокировка кошелька. Обычно
  ручное админом; `admin_id=None` (`granted_by_admin_id` NULL) — начисление не админом: бонус при
  регистрации (`AuthService`, `comment='signup_bonus'`, размер — `BILLING_SIGNUP_BONUS_CREDITS`).
- **`get_balance(user_id)`** / **`has_positive_balance(user_id)`** — используются как guard перед
  созданием новых задач/автоматизаций и перед диспатчем существующих (см. ниже).
- **`list_transactions_grouped_by_reference(user_id, limit, offset)`** — пагинированные траты,
  сгруппированные по (`reference_type`, `reference_id`): сумма, число транзакций, первая/последняя
  дата. Строки без источника (ручное начисление) не входят. Плоского списка транзакций в сервисе нет.
- **`get_spending_stats(date_from, date_to)`** — админская статистика трат **всех** пользователей
  за период (`created_at`, границы включительные, оба необязательны): `total_spent`, `tasks_spent`,
  `automations_spent`, `direct_spent` (кредиты, положительные числа; считаются только списания
  `amount < 0`, начисления не входят). Один агрегирующий запрос
  (`CreditTransactionRepository.get_spending_stats`, `SUM ... FILTER`). Классификация без обращения к
  `packages/task`/`packages/automation`: **автоматизации** — `reference_type=AUTOMATION` (создание)
  либо `transaction_metadata.dimension_code == automation_check_frequency` (результаты проверочных
  задач — они списываются с `reference_type=TASK`, но с этим измерением); **задачи** — `TASK` без
  признака автоматизации; **direct** — `DIRECT`. `total_spent` может быть больше суммы задач и
  автоматизаций на `direct_spent`. Если появится новый `reference_type`, он попадёт только в
  `total_spent`.
- **`list_actions`/`update_action_cost`/`list_pricing_rules`/`create_pricing_rule`/
  `delete_pricing_rule`** — админский CRUD над каталогом/правилами (без REST-специфики — схемы и
  auth-guard в `apps/api/src/routers/billing/`).

## Интеграция с `packages/task`/`packages/automation`

`packages/billing` не знает про `packages/task`/`packages/automation` — зависимость
однонаправленная, они зовут `BillingService`, не наоборот.

- **`task.create`**/**`automation.create`** — плоские действия, по умолчанию `base_cost=0`.
  `TaskService.create_task` (при `automation_id is None` — обычная, не проверочная задача) и
  `AutomationService.create_automation` сначала проверяют `has_positive_balance` (иначе
  `InsufficientCreditsError`), затем после успешного создания зовут `charge(...)`.
- **`result.<ParseType>`** — списывается инкрементально, по мере сохранения результатов, в
  `TaskService.record_item_progress` (см. [`packages/task/AGENTS.md`](../task/AGENTS.md) за
  деталями хука и денормализованных на `Task` полей `pricing_dimension_code`/
  `pricing_dimension_value`, которыми `packages/task` передаёт множитель без обращения к
  `packages/automation`).
- Если после инкрементального списания баланс пользователя уходит в `<= 0` — задача переводится в
  `PAUSED` (кооперативно, воркер сам заметит статус между страницами) — см.
  `TaskService.pause_task_system`.
- `AutomationService.dispatch_due_checks` проверяет баланс автоматизации **перед** каждым
  диспатчем — при `<= 0` проверка этого цикла пропускается (без отмены самой автоматизации),
  `Automation.last_check_error = "insufficient_credits"`.

- **`direct.<DirectRequestType>`** — direct-запросы ([`packages/direct`](../direct/AGENTS.md)),
  списываются в `apps/api/src/routers/direct/dependencies.py` (`charge_direct_request`) после успешного ответа,
  `quantity` = число возвращённых элементов, `reference_type=DIRECT`, `reference_id=request_id`.
  Баланс `<= 0` проверяется до запроса (402).

## Блокировка при недостатке кредитов

Пока баланс пользователя `<= 0`: `POST /api/tasks/`/`POST /api/automations/` отвечают `402`
(`InsufficientCreditsError`), уже существующие `ACTIVE`-автоматизации перестают диспатчиться (см.
выше). Уже запущенная задача, которая опустошает баланс в процессе парсинга (инкрементальное
списание), не блокируется целиком — списание проходит, баланс может на этом шаге уйти в минус,
задача ставится на паузу для следующих страниц.

## Не входит в эту итерацию

- Автопополнение/покупка кредитов — выдаёт администратор вручную; единственное автоначисление —
  разовый бонус при регистрации (`BILLING_SIGNUP_BONUS_CREDITS`, по умолчанию `0`).
- Уведомления о низком/отрицательном балансе.
- Тарифы/подписки — намеренно нет; см. [`packages/membership`](../membership/AGENTS.md), отдельная
  и никак не связанная с этим доменная область.
