# js_runtime/history/wb — снимки Wildberries

Статические материалы, скачанные с wildberries.ru при первом разборе антибота (2026-10-06). Потоком не
используются (поток сам скачивает актуальный скрипт в `ready/wb/cache_<hash>.js`). Нужны как эталон «как было»,
если WB сменит SDK или формат челленджа.

| Файл | Что это |
|---|---|
| `index.html` | Страница-челлендж (HTTP 498), `data-site-key` и подключение SDK |
| `index-yz9dDw8g.js`, `index-CAPy0gUu.css` | SDK страницы-челленджа (`js-front-browser/3.1.0`, не обфусцирован): описывает HTTP-протокол `find-frontend-settings` → `create-token` |
| `browser-check.js` | Скрипт предварительной проверки браузера |
| `challenge-solver_v1.0.8.js` | Обёртка-решатель (`solverPath` из `settings.json`) |
| `behavior-tracker_v1.0.3.js` | Трекер поведения (`analytics`); для получения токена **не нужен** |
| `settings.json` | Ответ `find-frontend-settings`: `solverPath`, `analytics`, `solverConfig` |
| `challenge1.json` | Пример ответа `create-token` (498): `scriptPath` и `payload` |
| `payload1.txt` | `payload` из `challenge1.json` в текстовом виде (вход решателя) |
| `94d22af85ae5f449.js` | Challenge-скрипт (VM-обфускатор, ~208 КБ) первой наблюдавшейся сборки |

Актуальное описание механики — `ready/wb/AGENTS.md`.
