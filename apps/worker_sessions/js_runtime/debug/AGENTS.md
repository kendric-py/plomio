# js_runtime/debug — отладка, адаптация, проверки

Инструменты для двух задач: (1) **проверить**, что рабочий поток из [`../ready`](../ready/AGENTS.md)
всё ещё выдаёт валидные сессии; (2) **адаптироваться**, когда маркетплейс сменил сборку антибота
(выяснить, что изменилось, и поправить `ready/`). Поток от этих файлов не зависит (единственное
исключение — `ozon/hook.js`, подключается по env `HOOK`).

- [`ozon/`](./ozon/AGENTS.md) — проверки и реверс-инструменты Ozon.
- [`wb/`](./wb/AGENTS.md) — проверки и трассировка Wildberries.

## Правила запуска
- Python-скрипты сами добавляют `../../ready/<mp>` в `sys.path` — запускать можно откуда угодно.
- JS-скрипты `ozon/*.js`, читающие `raw/…` или `template_chrome154.json` по относительному пути (`oz_cmp.js`, `brute_chain.js`, `oz_trace.js`), запускать с **cwd = `ready/ozon/`**: `cd ready/ozon && node ../../debug/ozon/oz_cmp.js`.
- Сеть дергают `oz_check.py`, `oz_probe.py`, `wb_check.py`, `wb_reuse.py`, `wb_validate.py` — соблюдать ≤1 запроса / 2 с, один IP, без параллельных прогонов.
- Диагностику любого сбоя начинать с `docs/mp-cookies/oz_flow_fragility.md` (Ozon) и `ready/wb/AGENTS.md` (WB, раздел «Хрупкость»).
