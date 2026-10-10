"""Захват тел POST /abt/result из Camoufox (который проходит антибот) + проверка токена."""
import re
import sys

from camoufox.sync_api import Camoufox

OZON_URL = "https://www.ozon.ru/"
SCRIPT_RE = re.compile(r"abt-challenge/(script_v[\d_]+)\.js")
OUT_DIR = sys.argv[1] if len(sys.argv) > 1 else "."
ITERATIONS = int(sys.argv[2]) if len(sys.argv) > 2 else 2

with Camoufox(headless=True) as browser:
    for i in range(ITERATIONS):
        context = browser.new_context()
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

        page.on("request", on_request)
        page.on("response", on_response)
        page.goto(OZON_URL, wait_until="domcontentloaded")
        page.wait_for_timeout(20000)
        token = any(c["name"] == "__Secure-access-token" for c in context.cookies())
        if state["body"]:
            name = f"{OUT_DIR}/camoufox_{state['version'] or 'unknown'}_{i}.json"
            with open(name, "w", encoding="utf8") as f:
                f.write(state["body"])
            print(f"[{i}] saved {name} ({len(state['body'])} bytes), token={'yes' if token else 'NO'}")
        else:
            print(f"[{i}] no POST seen, token={'yes' if token else 'NO'}")
        page.close()
        context.close()
