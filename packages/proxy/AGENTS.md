# packages/proxy

Доменная область пула прокси. Админ ведёт список прокси (создание, правка, список, удаление), а
`worker_sessions` получает из него **случайный активный** прокси для генерации сессий — см.
[`apps/worker_sessions/AGENTS.md`](../../apps/worker_sessions/AGENTS.md), "Прокси".

## Модель

`Proxy` (`proxies`): `proxy_type` (`ProxyType`: `http` / `socks5`, в БД — native enum, хранит
*имена* членов: `HTTP`, `SOCKS5`), `host`, `port`, `username`/`password` (nullable — прокси без
авторизации), `is_active` (участвует ли в выдаче; по умолчанию `true`), `note` (заметка админа),
`created_at`/`updated_at`.

Уникальность — `(proxy_type, host, port, username)` с `NULLS NOT DISTINCT` (Postgres 15+): два
прокси без логина с одним адресом тоже дубль. Нарушение → `DuplicatedObjectError` → `409`.

Пароль хранится открытым текстом: воркеру он нужен как есть, хэшировать нельзя. Поэтому админские
ответы **никогда** не возвращают пароль — только `has_password` (см. ниже), а сам пароль уходит
наружу единственной ручкой `GET /api/proxy/issue`, закрытой токеном воркера.

## Сервис (`ProxyService`)

- `list_page(limit, offset, is_active)` → `(items, total)`.
- `create_proxy(...)` — `DuplicatedObjectError` при дубле.
- `update_proxy(proxy_id, values)` — `values` это только реально переданные поля
  (`UpdateProxyRequest.changed_fields()`); `None` допустим и **сбрасывает** `username`/`password`/
  `note`. Поэтому используется `ProxyRepository.update_fields`, а не `BaseRepository.update`
  (тот отбрасывает `None`). `ObjectNotFoundError` / `DuplicatedObjectError` пробрасываются.
- `delete_proxy(proxy_id)` — `ObjectNotFoundError`, если нет такого.
- `issue_random(proxy_type=None)` — случайный активный прокси (`ORDER BY random() LIMIT 1`),
  опционально заданного типа; `None`, если подходящих нет. Пул маленький, равномерности выборки
  этого достаточно, отдельная схема выбора не нужна.

## REST

Роутер — `apps/api/src/routers/proxy`. Подробный контракт для фронтенда — в
[`docs/reference/frontend-api.md`](../../docs/reference/frontend-api.md), раздел `/api/admin/proxies`.

- Админ (`get_current_admin_user`): `GET`/`POST /api/admin/proxies/`, `PATCH`/`DELETE
  /api/admin/proxies/{proxy_id}`.
- Воркер: `GET /api/proxy/issue` — авторизация заголовком `X-Worker-Token`, сравнивается с
  `PROXY_WORKER_TOKEN` api (`secrets.compare_digest`). Пустой `PROXY_WORKER_TOKEN` — выдача
  выключена, ответ `503` (а не открытая всем ручка). Нет активных прокси — `404`, это ожидаемо
  обрабатывает `worker_sessions` (`proxy/client.py`: «прокси сейчас нет»).

Формат ответа `issue` — контракт с `worker_sessions`: `proxy_type`, `proxy_host`, `proxy_port`,
`proxy_username`, `proxy_password`. Менять поля нельзя без правки `get_proxy()` воркера.

## Что не сделано

- Audit-лог правок прокси не пишется (остальные админские CRUD, кроме начисления кредитов, тоже не
  аудируются).
- Нет проверки работоспособности прокси и автоматического отключения неживых — `is_active`
  переключает админ вручную.
- Выдача не учитывает нагрузку на конкретный прокси: `GENERATION_MAX_SESSIONS_PER_PROXY` ограничивает
  только то, сколько сессий подряд воркер генерирует через уже выданный прокси.
