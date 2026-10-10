# js_runtime/ready/ozon — рабочий поток Ozon

Статус (2026-10-10): **работает** — 10/10 валидных сессий подряд (`debug/ozon/oz_check.py`),
≈ 2,2 с на сессию в среднем (solve ≈ 1,1 с, холодный Node; ~175 МБ RSS), прямое соединение.
Проверено при ротации сборок `script_v47_1` / `v47_2` / `v47_3` — идентичность сессии
подстраивается под genuine-захват поданной сборки (см. п.1).
В проде пока Camoufox (≈ 5 с на сессию), этот каталог прод-код не подключён.

## Рабочий путь (`python oz_flow.py`)

1. `curl_cffi` (impersonate `chrome146`) `GET /` → 307 `/?__rr=1` → 403 «Antibot Challenge Page»
   (ставит `__Secure-ETC`, `abt_data`), в HTML — скрипт `script_vNN_M.js` и скрытое `#challenge`.
   Сборка определяет **идентичность сессии**: `oz_flow.identity_for_build(version)` берёт
   user-agent/`sec-ch-ua` из того же genuine-источника, что и фордж (`raw/real_script_vNN_M_0.json`
   при наличии, иначе `template_chrome155.json`); если они не совпадают с текущими заголовками,
   челлендж берётся заново с подходящими заголовками (Ozon крутит сборки между запросами —
   до 3 попыток). HTTP user-agent обязан совпадать с `user_agent` в fp.
2. Node (`oz_solve.js`, jsdom) прогоняет оригинальный скрипт и формирует тело `POST /abt/result`.
3. `oz_forge.js` расшифровывает `fp` (`fpcodec.js`) и собирает его заново: **схема (набор ключей)
   и константы сборки (`browser_2`, `fn_1..3`) — от своего VM-прогона**, динамика челленджа
   (`challenge,ts,nonce,pzs,pzc`) — своя, метки `performance.timing` перебазируются на текущий
   запуск, остальное окружение — из genuine-источника идентичности (см. п.1). Шифрует обратно
   **той же цепочкой md5, что выбрала VM**. Стеки VM-полей подменяются только по
   `evalmachine.<anonymous>` → настоящий URL скрипта — безусловно; **остальное содержимое
   стеков не трогать** (фреймы `node:internal` принимаются сервером, а их вырезание ломает
   сессию — сервер сверяет структуру, инцидент 2026-10-10).
4. `POST /abt/result` → `200 {"ok":true}`. **Куки в этом ответе не приходят — нужен повторный
   `GET /`**: он отдаёт 200 (≈475 КБ) и полный набор токенов.
5. Проверка: `entrypoint-api.bx/page/json/v2` (поиск «телефон») → 200, JSON ~190 КБ
   (`check_api(session)`).

Cwd для Node-подпроцессов — эта папка (`OZ = HERE` в `oz_flow.py`): относительные пути `raw/…` отсюда.
**Полный разбор формата отпечатка и принципа форджа — в [`FINGERPRINT.md`](./FINGERPRINT.md).**

## Что выдаётся (куки)

Обязательные: `abt_data`, `__Secure-ETC`, `__Secure-access-token` (без него API отвечает
403 «Antibot Captcha»). Опционально приходят: `__Secure-refresh-token`, `__Secure-user-id`,
`__Secure-ext_xcid`, `xcid`, `__Secure-ab-group`.

## Файлы
| Файл | Что делает | Кто запускает / подключает |
|---|---|---|
| `oz_flow.py` | **Точка входа.** `get_ozon_cookies(proxy=None, verbose=False, impersonate='chrome146', forge_body=True)` — полный поток (GET → solve → forge → POST `/abt/result` → reload), возвращает `{'ok', 'session', 'ua', 'ch', …}` (`ua`/`ch` — итоговая идентичность сессии, обязательно переиспользовать во всех последующих запросах); `identity_for_build(version)` — идентичность из fp-базы сборки; `check_api(session, ua=…, ch=…)` — проверка сессии реальным поисковым запросом. Внутри `solve()` (запуск `oz_solve.js`) и `forge()` (запуск `oz_forge.js`). Пишет `raw/last_vm_body.json`, `raw/last_challenge.html`, при неудаче `raw/failed_body_<ts>.json`, временные `tmp_*` | `scripts/ozon/search_stream.py`, `debug/ozon/oz_check.py`, `debug/ozon/oz_probe.py` |
| `oz_solve.js` | Прогоняет оригинальный challenge-скрипт в jsdom/`vm`; печатает JSON с телом (`body`), `ms`, `rss`. Аргументы: `<challenge.html> <script.js> <UA>`. Env: `NOWEBGL=1` (рабочий режим), `HOOK` (подключает `debug/ozon/hook.js`), `ENCOUT` (дамп шифр-входа) | `oz_flow.py` (subprocess), `debug/ozon/oz_repeat.js`, `debug/ozon/oz_probe.py` |
| `oz_forge.js` | Форджер: расшифровывает `fp` (через `fpcodec.js`), заменяет статичные/вычисляемые поля по эталону (`template_chrome155.json` или `raw/real_script_vNN_M_0.json`, если есть для версии сборки), шифрует обратно. Аргументы: `<body.json> <template.json>` | `oz_flow.py` (subprocess) |
| `fpcodec.js` | Кодек отпечатка: `decode(fp, token)` / `encode(...)` — цепочка md5-раундов (1–8) + XOR. Самотест: `node fpcodec.js` (читает `../../debug/ozon/fixtures/real_body.json`, `real_pw.txt`) | `oz_forge.js`, `debug/ozon/*` |
| `env_extra.js` | Заглушки окружения браузера (navigator, screen, performance и т. п.) поверх jsdom | `oz_solve.js`, `debug/ozon/oz_trace.js` |
| `env_canvas.js` | Подмена canvas/WebGL через `@napi-rs/canvas` (при `NOWEBGL` WebGL не грузится) | `oz_solve.js`, `debug/ozon/oz_trace.js` |
| `template_chrome155.json` | Общий эталонный отпечаток Chrome 155 (источник статичных полей) | `oz_forge.js` |
| `raw/real_script_v47_1_*.json`, `raw/real_script_v47_3_*.json` | Настоящие захваты из браузера, по сборкам скрипта (`v47_1`, `v47_3`). Источник истины по классам полей; `oz_forge.js` подхватывает автоматически, если Ozon вернёт эту сборку. **Важно:** захваты обязаны быть с `navigator.webdriver=false` (снимать с `--disable-blink-features=AutomationControlled`, иначе сервер отвергает тело — инцидент 2026-10-10) | `oz_forge.js` |
| `cache_script_v47_*.js` | Кэш скачанного challenge-скрипта (создаётся потоком, `.gitignore`). Можно удалять — скачается заново | `oz_flow.py` |
| `FINGERPRINT.md` | Формат отпечатка, принцип форджа, что делать при смене сборки (раздел 6) | Люди и агенты при адаптации |

## Проверено (ключевые факты)

- Цепочка md5 пароля — 2–5 раундов, выбирает VM per challenge; сервер выводит ожидаемую из
  челленджа: чужая цепочка отвергается (принудительная r6 → 0/3), выбор VM всегда принимается.
- Отказ определяется **содержимым fp, а не транспортом**: тело из нашего окружения, отправленное
  из настоящего Chromium (родной TLS/заголовки/куки), всё равно получало 403 (дифф-эксперимент).
- `x-o3-bot-score` одинаков (10) у принятых и отклонённых — это оценка транспорта, а не отпечатка;
  `x-o3-antibot-ja4-*` — серверу виден TLS/HTTP-fingerprint клиента.
- `evalmachine.<anonymous>` в стеках `fn_1` — мгновенный маркер `node:vm` → 403 (инцидент
  2026-10-08: подмена URL срабатывала только при расхождении версий с шаблоном и пропускала
  совпадение). Теперь URL-замена для VM-полей — **всегда**, независимо от версии.
- Фреймы `at process.processTicksAndRejections (node:internal/…)` в стеках VM-полей — **не**
  маркер: старый фордж с ними работал 10/10, а их вырезание дало стабильный 403 (сервер, видимо,
  сверяет структуру/контрольную сумму тела; инцидент 2026-10-10). Правило: подменять в стеках
  только `evalmachine.<anonymous>`, больше ничего.
- HTTP user-agent/`sec-ch-ua` обязаны совпадать с `user_agent`/`hev` того genuine-источника, из
  которого фордж берёт окружение. Источник зависит от поданной сборки: v47_1 → свежий захват
  (Chrome 155), v47_3 → его захват (Chrome 154), остальные → `template_chrome155.json` — поэтому
  идентичность выбирается динамически (`oz_flow.identity_for_build`, повторный GET при смене).
- `navigator.webdriver=true` в эталоне/захвате → сервер отвергает тело (инцидент 2026-10-10:
  старые per-build захваты `real_script_v47_1_*` были сняты Playwright'ом без
  `--disable-blink-features=AutomationControlled` и отравили фордж, когда Ozon вернул сборку
  v47_1). Захваты снимать только с этим флагом; проверка эталона: `@get:webdriver` в `navigator`
  обязан быть `false`.
- Секции `battery/storage/hev/media_devices` собираются через async-API (`getBattery`,
  `storage.estimate`, `userAgentData.getHighEntropyValues`, `enumerateDevices`), которых в jsdom
  нет — без прокладок VM их молча пропускает (28 секций вместо 32). Прокладки в `env_extra.js`
  дают схему настоящего Chrome для любой сборки. Сервер толерантен к их отсутствию (v47_2
  принимал 28 секций 10/10), но с прокладками мы совпадаем с эталоном вплоть до набора секций.
- Сквозной пример «сессия → поиск → поток названий»: `python scripts/ozon/search_stream.py`
  (из корня репозитория; релевантная выдача, ~8 товаров/страница, 1 с/страница).

## Не проверено

Прокси, нагрузка/rate-limit, срок жизни токена, параллельные прогоны, привязка JA4 к UA
(шлём chrome146-TLS под UA Chrome 155 — принимается).

## Когда что-то сломалось
См. `docs/mp-cookies/oz_flow_fragility.md` (симптомы → диагностика → правка) и
`debug/ozon/AGENTS.md` — инструменты диагностики там. История реверса — `history/REPORT.md`.