"""Снимает реальные тела POST /abt/result, которые Chromium шлёт при прохождении челленджа Ozon.

4 итерации: новый чистый контекст -> https://www.ozon.ru/ (без подмен и блокировок скриптов) ->
перехват запроса POST /abt/result -> request.postData() сохраняется на локальный http_solver:
POST http://127.0.0.1:8765/save/real_<версия скрипта>_<номер>.json
Версия (script_v47_3) берётся из URL загруженного браузером скрипта abt-challenge.
Сохраняются только тела запроса; куки не сохраняются, но их наличие (__Secure-access-token)
проверяется — это признак того, что сервер принял тело.

Запуск: python scripts/ozon/capture_real_abt.py [--iterations 4] [--headless]
"""

import argparse
import re
import urllib.request

from playwright.sync_api import BrowserContext, Page, Request, sync_playwright

SOLVER_URL = "http://127.0.0.1:8765"
OZON_URL = "https://www.ozon.ru/"
COOKIE_NAME = "__Secure-access-token"
SCRIPT_RE = re.compile(r"abt-challenge/(script_v[\d_]+)\.js")
WAIT_MS = 30_000


def save_body(name: str, body: str) -> None:
    req = urllib.request.Request(
        f"{SOLVER_URL}/save/{name}",
        data=body.encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        resp.read()


def run_iteration(context: BrowserContext, index: int) -> bool:
    page: Page = context.new_page()
    state: dict = {"version": None, "body": None}

    def on_request(request: Request) -> None:
        m = SCRIPT_RE.search(request.url)
        if m and not state["version"]:
            state["version"] = m.group(1)
        if request.method == "POST" and "/abt/result" in request.url and state["body"] is None:
            state["body"] = request.post_data

    page.on("request", on_request)
    page.goto(OZON_URL, wait_until="domcontentloaded")

    waited = 0
    while waited < WAIT_MS and not (state["body"] and has_token(context)):
        page.wait_for_timeout(500)
        waited += 500

    ok = bool(state["body"]) and has_token(context)
    if state["body"]:
        name = f"real_{state['version'] or 'script_unknown'}_{index}.json"
        save_body(name, state["body"])
        print(f"[{index}] saved {name} ({len(state['body'])} bytes), token={'yes' if ok else 'NO'}")
    else:
        print(f"[{index}] /abt/result не замечен за {WAIT_MS // 1000}с")
    page.close()
    return ok


def has_token(context: BrowserContext) -> bool:
    return any(c["name"] == COOKIE_NAME for c in context.cookies())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=4)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args()

    with sync_playwright() as p:
        # Без --disable-blink-features=AutomationControlled у Chromium navigator.webdriver=true,
        # и захват рождается отравленным: сервер такие тела отвергает, а использовать их как
        # эталон форджа нельзя (инцидент 2026-10-10). Для эталона также лучше настоящий
        # Google Chrome (channel="chrome"), а не сборка Chromium из Playwright.
        browser = p.chromium.launch(headless=args.headless, args=["--disable-blink-features=AutomationControlled"])
        results = []
        for i in range(args.iterations):
            context = browser.new_context()  # чистый контекст на каждую итерацию
            try:
                results.append(run_iteration(context, i))
            finally:
                context.close()
        browser.close()
    print(f"accepted: {sum(results)}/{len(results)}")


if __name__ == "__main__":
    main()
