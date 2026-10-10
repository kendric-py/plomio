"""Разовый захват настоящих тел POST /abt/result из реального Chromium в файлы."""
import re
import sys

from playwright.sync_api import sync_playwright

OZON_URL = "https://www.ozon.ru/"
COOKIE_NAME = "__Secure-access-token"
SCRIPT_RE = re.compile(r"abt-challenge/(script_v[\d_]+)\.js")
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
ITERATIONS = int(sys.argv[2]) if len(sys.argv) > 2 else 2
WAIT_MS = 30_000


def run_iteration(context, index):
    page = context.new_page()
    state = {"version": None, "body": None}

    def on_request(request):
        m = SCRIPT_RE.search(request.url)
        if m and not state["version"]:
            state["version"] = m.group(1)
        if request.method == "POST" and "/abt/result" in request.url and state["body"] is None:
            state["body"] = request.post_data

    def on_response(response):
        if "/abt/result" in response.url:
            print(f"  [resp] POST /abt/result -> {response.status}")

    page.on("response", on_response)

    page.on("request", on_request)
    page.goto(OZON_URL, wait_until="domcontentloaded")

    waited = 0
    while waited < WAIT_MS and not (state["body"] and has_token(context)):
        page.wait_for_timeout(500)
        waited += 500

    ok = bool(state["body"]) and has_token(context)
    if state["body"]:
        name = f"{OUT_DIR}/fresh_{state['version'] or 'script_unknown'}_{index}.json"
        with open(name, "w", encoding="utf8") as f:
            f.write(state["body"])
        print(f"[{index}] saved {name} ({len(state['body'])} bytes), token={'yes' if ok else 'NO'}")
    else:
        print(f"[{index}] /abt/result not seen in {WAIT_MS // 1000}s")
    page.close()
    return ok


def has_token(context):
    return any(c["name"] == COOKIE_NAME for c in context.cookies())


with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=False, args=["--disable-blink-features=AutomationControlled"])
    results = []
    for i in range(ITERATIONS):
        context = browser.new_context()
        try:
            results.append(run_iteration(context, i))
        finally:
            context.close()
    browser.close()
print(f"accepted: {sum(results)}/{len(results)}")
