# js_runtime/debug/ozon — отладка и проверки Ozon

Рабочий код лежит в `../../ready/ozon/`. Здесь — то, что запускают вручную при проверке и адаптации.
`cwd = ready/ozon/` обязателен для скриптов, помеченных ⚠.

## Проверки (тесты)
| Файл | Что делает | Запуск |
|---|---|---|
| `oz_check.py` | N полных прогонов `oz_flow.get_ozon_cookies`; каждую сессию проверяет реальным поисковым запросом (`check_api`), печатает цепочку md5-раундов, `solve`/`total`, итог `valid N/N`. Пауза 2 с между прогонами. Env `FORCE_CHAIN` принудительно задаёт цепочку | `python debug/ozon/oz_check.py [N=5]` — цель 10/10 |
| `fixtures/real_body.json`, `fixtures/real_pw.txt` | Фикстура самотеста кодека: настоящее тело и пароль | `cd ready/ozon && node fpcodec.js` → `pw ok true`, `roundtrip identical: true` |

## Отладка и адаптация
| Файл | Что делает | Когда нужен |
|---|---|---|
| `oz_probe.py` | Один запрос к ozon.ru без POST: сохраняет `ready/ozon/raw/probe_<tag>.html`, `.js` (challenge-скрипт) и `_body.json` (тело, собранное VM) | Новая сборка — снять материалы для разбора |
| `oz_trace.js` ⚠ | Прогон challenge-скрипта с логирующим Proxy: какие глобалы/свойства читает VM. `node oz_trace.js <challenge.html> <script.js>` | Симптом «`oz_solve.js` падает» — найти недостающее окружение для `env_extra.js` |
| `brute_chain.js` ⚠ | Перебор длины md5-цепочки (раундов) на упавших `raw/failed_body_*.json` | Ozon сменил число раундов (`decode fail`) → расширить `chainPw`/`GENUINE` в `fpcodec.js` |
| `oz_cmp.js` ⚠ | Сравнивает поля отпечатка по эталонам `raw/real_script_v47_3_*.json` и `template_chrome154.json`: какие поля стабильны, какие меняются между захватами | Решить, какие поля идут в статичный эталон, а какие — `VM_DERIVED` в `oz_forge.js` |
| `oz_repeat.js` | Офлайн (без сети): N раз гоняет VM на сохранённом челлендже и проверяет, что `oz_forge` корректно decode+encode каждое тело. `node oz_repeat.js <challenge.html> <script.js> [N=10]` | Проверка форджа после правок без обращения к Ozon |
| `hook.js` | Хук `encodeURIComponent` в VM (запоминает длинные строки в `globalThis.__js`) для ре-реверса кодека. Подхватывается `ready/ozon/oz_solve.js` при `HOOK=1` | Кодек сменился — перехватить вход шифра |

## Если нужен новый эталон
Снять настоящий захват из браузера → положить как `ready/ozon/raw/real_script_vNN_M_0.json` (подхватится
автоматически) или обновить `template_chrome154.json`. Порядок — `docs/mp-cookies/oz_flow_fragility.md`.
