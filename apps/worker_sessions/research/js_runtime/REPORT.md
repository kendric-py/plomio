# Антибот-куки без браузера: WB и Ozon (исследование)

Дата: 2026-10-06 (Ozon обновлён 2026-10-07). Прод-код не менялся; всё в `research/js_runtime/`. Один IP, без прокси, ≤1 запроса / 2 с.
Python — venv worker-sessions; Node v22.23.2.

## Сводка

| | Wildberries | Ozon |
|---|---|---|
| Вердикт | **работает, внедрять стоит** | **работает** (2026-10-07, `script_v47_2`: 10/10, `oz_check.py`; см. [`ozon_summary.md`](./ozon_summary.md) и [`oz/FINGERPRINT.md`](./oz/FINGERPRINT.md)) |
| Время на сессию | **0,92 с** (lean, 2 HTTP) / 1,07 с (полный поток, warm Node) | **~2,05 с** (холодный Node на каждый прогон) |
| Бейзлайн Camoufox | ~7,5 с | ~5 с |
| Валидных сессий | **12/12 + 12/12** (валидатор приложения) | **10/10** (поисковый API после reload) |
| RAM Node-решателя | ~160–180 МБ RSS (jsdom + vm) | ~175 МБ |

Раздел «Ozon» ниже — исторический (до исправления форджа 2026-10-07); актуальное состояние — в
`ozon_summary.md` и `oz/FINGERPRINT.md`.

## Wildberries

### Механика (разобрана)
Страница-челлендж (HTTP 498) грузит SDK `index-*.js` (не обфусцирован), который делает чистый HTTP:
1. `POST /__wbaas/challenges/antibot/api/v1/find-frontend-settings` → `solverPath`, `analytics` (для токена не нужен).
2. `POST .../api/v1/create-token` с `{}` → **498** `{challenge:{scriptPath, payload}}` (payload ≈8 КБ).
3. Скрипт `scriptPath` (`/statics/<hash>.js`, 208 КБ, VM-обфускатор с байткодом, коды ошибок `E2xx`) регистрирует
   функцию в `window[Symbol.for(...)]`; `solve(payload)` → строка `"<n>|<base64>"`.
4. `POST create-token` с `{"challenge":{scriptPath,payload},"solution":{"payload":"<решение>"}}` → 200 `{secureToken}`
   → кука `x_wbaas_token`. Заголовки: `X-Guardium-Antibot-Key` (= `data-site-key`, статичный),
   `X-Guardium-Antibot-SDK-Version: js-front-browser/3.1.0`.

Токен: `1.1000.<id>.<b64(ip|UA|exp|reusable|…)>.<подпись>`; в нём IP и UA выдачи, срок ≈ **72 ч**
(exp = выдача + 259200 с; второй штамп +36 ч, вероятно «обновить после»). **Фактический срок жизни вживую не проверялся.**

### Подходы
- **(а) оригинальный JS в лёгком рантайме — работает.** В «голом» jsdom `eval` падает (`E217/E227`: нет глобалей), а в
  `node:vm` с Proxy-глобалом поверх jsdom-окна (`wb/env_min.js`) отдаёт валидное решение. Canvas = `null` — сервер не придирается.
  Само решение ~220 мс; остальное — старт jsdom (первый `require('jsdom')` ≈750 мс → нужен постоянный Node-процесс).
- **(б) чистый Python без JS — не пробовал**: решение считает VM-байткод, реверс не окупается.
- **(в) гибрид — финальная схема**: HTTP в curl_cffi (TLS firefox135), JS только для `solve(payload)`
  (`wb_flow_warm.py` + `wb/solve_server.js`, JSON-lines по stdin/stdout).

### Замеры
- Полный поток (GET / → settings → create-token ×2): **1,03–1,06 с**, solve 0,44 с. Lean (без GET `/` и settings, статичный
  site-key): **0,81–0,94 с**.
- Валидация `generation/validation.py::validate_session` (homepage + реальный поиск): `wb_validate_full.log` 12/12,
  `wb_validate_lean.log` 12/12. Контроль: без токена поиск → 498; с токеном → 200, 100 товаров.
- Один токен на 12 поисков подряд (интервал 2 с): 12×200. С другим UA в запросе тоже 200 (UA на API не проверяется);
  IP, судя по токену, зашит — выдавать через тот же прокси, через который сессия будет использоваться.
- Холодный `node solve_vm.js` на каждое решение: ~1,3 с — нужен постоянный процесс.

### Как воспроизвести
```
cd apps/worker_sessions/research/js_runtime && npm i     # jsdom, js-beautify, @napi-rs/canvas
python wb_flow_warm.py          # 4 токена, тайминги
python wb_validate.py 12 [lean] # N сессий + валидатор приложения (запускать с корнем репо в PYTHONPATH — скрипт добавляет сам)
python wb_reuse.py              # один токен x12 запросов
```

### Хрупкость
- Имена: SDK `index-yz9dDw8g.js` (хэш Vite — меняется при каждой сборке), solver `challenge-solver_v1.0.8.js`,
  tracker `behavior-tracker_v1.0.3.js`, SDK `3.1.0`, скрипт челленджа `/statics/94d22af85ae5f449.js`.
  Наш код берёт эти URL из ответов (`scriptPath` из 498) и от хэшей не зависит; `data-site-key` статичен, но в «безопасном»
  режиме читается с главной (+1 запрос).
- За время работы (~1 ч, десятки челленджей) `scriptPath` не менялся; частота деплоев WB неизвестна.
- Риски: WB добавит проверку окружения (WebGL/canvas/шрифты) — скрипт в jsdom начнёт бросать `E2xx` или токены перестанут
  валидироваться; смена версии протокола (`/api/v1`); включение приёма `behavior-tracker`/метрик (`meta`); привязка к TLS-JA3/JA4.
  Митигация: метрика доли ошибок solve/валидации → автоматический откат на Camoufox.

### Вердикт и трудозатраты
**Внедрять**: ≈1 с против ≈7,5 с (~7×), ~170 МБ на Node-процесс. Оценка: 2–3 дня на продакшн-реализацию (пул Node-решателей,
curl_cffi через socks5h-прокси, `spa_version`/`device_id` как сейчас, метрики, фолбэк на Camoufox, тесты) и ~0,5 дня/мес поддержки,
пока протокол не меняется. Не проверено: работа за реальным прокси и под нагрузкой, живой срок токена, RAM Camoufox для сравнения.

## Ozon

### Механика (разобрана, кроме криптографии VM)
`GET /` → 307 `/?__rr=1` (ставит `__Secure-ETC`, `abt_data`) → 403 «Antibot Challenge Page» со скриптом
`https://st.ozone.ru/s3/abt-challenge/script_v47_4.js` (112 КБ, `Last-Modified: 2026-08-03`, `lib_version 0.7.4`, `build_ts 2026-07-31`).
В HTML скрытые поля `#challenge` (≈4,7 КБ), `#incident`, `#complaints-token`. Скрипт — байткод-VM + встроенный CryptoJS и **антиотладка**
(`debugger`, проверка `
`/пробелов в исходниках функций → бесконечный цикл; код нельзя «красиво» форматировать). Он декодирует
`#challenge` в токен `sc:<id22>:<blob>` (+ `:<b64 {"ts","support_domain"}>`), собирает fp, шифрует и делает `POST /abt/result`
с `{token, fp, info, error, timings}`. Успех → `200 {"ok":true}` и куки (`__Secure-access-token`, `refresh-token`, `user-id`,
`ext_xcid`, `ab-group`, `xcid`…). Ответ несёт `x-o3-bot-score` и `x-o3-antibot-ja4-http` (JA4 виден серверу).

**Формат fp (расшифрован):** `base64("Salted__"+salt+AES-256-CBC(EvpKDF-MD5, пароль=32-hex md5))`, внутри — JSON, предварительно
XOR-нутый повторяющимся токеном. Пароль в VM строится цепочкой md5 (`md5("d116")` → `md5(prev+token)` → …; «d116» — 4-символьный
seed, источник не установлен; линейной цепочкой не описывается). Расшифровать удалось только **первую половину** (≈10 КБ,
блоки 0–627); со 628-го блока данные не расшифровываются ни тем же ключом с продолжением CBC, ни со сбросом IV, ни XOR-ом токеном,
ни хэш-кандидатами — вероятно, вторая часть (canvas/WebGL/шрифты/audio?) шифруется другим ключом.
Как достать плейнтекст/пароль: патч сырого скрипта (строки-якоря в CryptoJS: `execute` = EvpKDF, `_append`), см. `oz/` — хуки на
`__enc` в `oz_solve.js`; в настоящем браузере тот же патч подкладывается через `page.route` (получен эталон).

**Содержимое первой половины** (эталон Chromium 154 vs мой jsdom): это не набор значений, а **глубокий дамп объектов браузера**
(`"@proto:Screen":{"@get:width":…}`, `"@val:…"`, `"_fn_"`, `"_n_"`): `screen`, `visualViewport`, `BatteryManager`,
`navigator.userAgentData`/high-entropy values, `plugins`/`mimeTypes` («Chromium PDF Viewer»), `storage.estimate()`, `window.chrome`
(`app`, `csi`, `loadTimes`), флаги `isChrome/isBlink…`, `props` (15 замеров размеров/позиций), `checkStr`, `challenge.version`.
У jsdom в дампе — исходный код геттеров (`get availWidth() { const $impl = $requireImpl(...`), `screen` 0×0, `props=-1|-1|…`,
`isFirefox/isChrome=false` → заведомо «не браузер».

### Что получилось и что нет
- Оригинальный скрипт в `node:vm` + jsdom (+ `performance.timing/mark`, `matchMedia`, `visualViewport`, canvas на `@napi-rs/canvas`
  с поправкой `arc(…,1)`→bool) отрабатывает до конца: полный `fp` (≈28 КБ), `error` пуст, ~175 мс. **Важно:** мой WebGL-стаб
  (`env_webgl.js`) ломал вычисление (`fp` пустой) — все прогоны с ним невалидны; в рабочем режиме `NOWEBGL=1`.
- **Сервер отвечает `403 {"ok":false}`**, `__Secure-access-token` не выдаётся. Валидных сессий 0.
- **Дифференциальный эксперимент** (повторён корректно, с `fp` 28 КБ): в настоящем Chromium заблокировал штатный скрипт, решил тот же
  HTML в Node и отправил моё тело `fetch`-ом **из браузера** (родной TLS/заголовки/куки) → `403 {"ok":false}`. Значит, отвергается
  **содержимое fp**, а не транспорт. Контроль: штатный браузер (в т.ч. с моим патчем-логгером) проходит, `x-o3-bot-score: 10`.

### Оценка путей
1. **Дотягивать окружение до браузерного** (мок-объекты по эталонному дампу: Screen/Navigator/UAData/plugins/chrome/Battery/…).
   Дамп устроен как обход прототипов, поэтому мок надо строить «зеркально» по реальному дампу; плюс неизвестная вторая половина
   (скорее всего canvas/WebGL/шрифты — реальный рендер Skia/ANGLE не воспроизвести, придётся подставлять сохранённые значения),
   и привязка к UA/TLS (JA4). Объём: недели, итог не гарантирован.
2. **Реверс VM-криптографии и сборка fp «с нуля» по шаблону из реального браузера** (подставляя `challenge.id/checkStr/props/timings`):
   нужны схема пароля (seed «d116»), вторая половина, `checkStr`, преобразование `#challenge → token`. Объём: недели, максимально хрупко
   (каждый `script_vN_M` — новый байткод, шаблон придётся пересобирать).
3. **Ничего не менять в подходе, ускорять Camoufox** (~5 с уже достигнуто).

### Вердикт
**Не внедрять** без дополнительного бюджета; пути 1–2 — исследовательские, ≥2–4 недели, высокая хрупкость (версия скрипта в имени,
сейчас v47_4 с 03.08.2026 → ≈1 релиз в 2 месяца, но формат fp/ключей может меняться с ним).

## Файлы
`wb_flow.py`, `wb_flow_warm.py`, `wb_validate.py`, `wb_check.py`, `wb_reuse.py`, `wb/{solve_vm,solve_server,env_min,trace}.js`;
`oz_flow.py`, `oz_check.py`, `oz_probe.py`, `oz/{oz_solve,oz_forge,fpcodec,env_extra,oz_trace,oz_cmp,oz_repeat,brute_chain,hook}.js`, `env_canvas.js`,
`oz/template_chrome154.json`, разбор формата — `oz/FINGERPRINT.md`;
сырьё `wb/raw/`, `oz/raw/` (там только настоящие браузерные захваты `real_*` — артефакты прогонов вычищены 2026-10-07);
логи `wb_validate_{full,lean}.log`. `node_modules` (67 МБ) в `.gitignore`.
