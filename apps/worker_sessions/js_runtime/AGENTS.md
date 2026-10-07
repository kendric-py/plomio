# apps/worker_sessions/js_runtime

Безбраузерная генерация антибот-кук для **Ozon** и **Wildberries**: HTTP-протокол в `curl_cffi` (Python) +
оригинальный challenge-скрипт маркетплейса в Node (`jsdom`/`vm`). Заменяет Camoufox (~5–7,5 с на сессию)
на ~1–2 с. Прод-код подключает `ready/` через `src/generation/js_runtime/loader.py` и `session_js.py`
(режим `GENERATION_*_MODE=js_runtime`, см. [`../AGENTS.md`](../AGENTS.md)); также потребители —
`scripts/ozon/search_stream.py` и `scripts/wb/search_stream.py`.

## Карта

| Папка | Назначение | Кто сюда смотрит |
|---|---|---|
| [`ready/`](./ready/AGENTS.md) | Рабочий код: то, что реально исполняется при получении сессии | Любой, кто запускает/интегрирует поток. Менять осторожно |
| [`debug/`](./debug/AGENTS.md) | Отладка, адаптация под новые сборки антибота, прогоны и проверки | Тот, кто чинит поток после смены сборки маркетплейса |
| [`history/`](./history/AGENTS.md) | Справка: итоговый отчёт и первые захваты. Потоку не нужны | Тот, кому нужно понять «откуда это взялось» |

В каждой папке есть подпапки `ozon/` и `wb/` со своим `AGENTS.md` — там построчно описан каждый файл.

## Общее в корне
- `package.json`, `package-lock.json`, `node_modules/` — зависимости Node (`jsdom`, `@napi-rs/canvas`, `js-beautify`). Лежат в корне, потому что Node ищет модули вверх по дереву — так работают `ready/`, `debug/`, `history/`. Установка: `cd apps/worker_sessions/js_runtime && npm i`. `js-beautify` — devDependency (в Docker не ставится).
- `JS_RUNTIME_CACHE_DIR` — куда `ready/` пишет кэши `cache_*`, `tmp_*`, `raw/last_*` (по умолчанию — рядом с кодом; в контейнере `/tmp/js_runtime`).
- `.gitignore` — кэши challenge-скриптов (`ready/*/cache_*`), артефакты прогонов (`ready/ozon/raw/last_*`, `failed_body_*`, `tmp_*`), логи, `node_modules/`.

## Правила
- Python — venv `worker-sessions`; Node ≥ v22. Один IP без прокси, ≤1 запроса / 2 с, иначе антибот режет.
- Файлы из `ready/` не импортируют ничего из `debug/`, кроме опционального `debug/ozon/hook.js` (включается переменной `HOOK`).
- Скрипты из `debug/`, которые читают `raw/` или `template_chrome154.json` по относительному пути, запускать с cwd `ready/ozon/`.
- Новые отладочные скрипты — в `debug/`, не в `ready/`. Устаревшие материалы переносить в `history/`, а не копить рядом с рабочим кодом.
- При изменении потока обновлять `AGENTS.md` соответствующей подпапки (`docs/reference/agent-documentation.md`).
