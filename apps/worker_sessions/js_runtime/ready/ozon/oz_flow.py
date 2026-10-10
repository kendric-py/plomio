"""Ozon antibot without browser: curl_cffi for HTTP, Node (jsdom+napi-canvas) runs the original challenge script."""
import json, os, re, subprocess, sys, threading, time, html as htmllib
from curl_cffi.requests import Session

# Default identity — matches template_chrome155.json (the fp base for builds without a genuine capture).
# If Ozon serves a build with its own genuine capture (raw/real_script_vNN_M_0.json) speaking ANOTHER
# identity (e.g. v47_3's capture is Chrome 154), the flow restarts the challenge with the capture's
# identity: the forged fp claims it, so the HTTP headers of the whole session must match it.
CH = {'sec-ch-ua': '"Not(A:Brand";v="24", "Chromium";v="155", "Google Chrome";v="155"', 'sec-ch-ua-mobile': '?0', 'sec-ch-ua-platform': '"Windows"'}
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/155.0.0.0 Safari/537.36'
HERE = os.path.dirname(os.path.abspath(__file__))
OZ = HERE
# Writable dir for caches/temp/last_* artifacts (JS_RUNTIME_CACHE_DIR in containers); Node still runs with cwd=OZ to read raw/ and templates.
CACHE = os.environ.get('JS_RUNTIME_CACHE_DIR') or HERE
os.makedirs(os.path.join(CACHE, 'raw'), exist_ok=True)
SCRIPT_URL_RE = re.compile(r'<script src="(https://st\.ozone\.ru/s3/abt-challenge/script_[^"]+\.js)"')
TEMPLATE_FP = os.path.join(OZ, 'template_chrome155.json')

# Decodes a genuine capture (raw body {token,fp,...}) or reads a decoded template and prints
# [user_agent, sec-ch-ua] built from userAgentData fullVersionList (major versions only).
_IDENTITY_JS = r"""
const fs=require('fs');const c=require('./fpcodec.js');
const b=JSON.parse(fs.readFileSync(process.argv[1],'utf8'));
const o=b.fp?(()=>{const d=c.decode(b.fp,b.token);let t=d.json,i=t.length;while((i=t.lastIndexOf('}',i))>0){try{return JSON.parse(t.slice(0,i+1))}catch(e){i--}}})():b;
const brands=((o.hev&&o.hev.fullVersionList)||[]).map(x=>'"'+x.brand+'";v="'+x.version.split('.')[0]+'"');
process.stdout.write(JSON.stringify([o.user_agent||'',brands.join(', ')]));
"""
_IDENTITY_CACHE = {}


def identity_for_build(version):
    """(user_agent, sec-ch-ua) of the fp base the forge will use for this script build —
    the forged fp claims exactly this identity, so HTTP headers must match it."""
    if version in _IDENTITY_CACHE:
        return _IDENTITY_CACHE[version]
    gf = os.path.join(OZ, 'raw', 'real_script_v%s_0.json' % version)
    src = gf if os.path.exists(gf) else TEMPLATE_FP
    ua, ch = UA, CH['sec-ch-ua']
    try:
        b = json.load(open(src, encoding='utf8'))
        if 'fp' not in b:
            brands = ['"%s";v="%s"' % (x['brand'], x['version'].split('.')[0]) for x in (b.get('hev') or {}).get('fullVersionList') or []]
            ua, ch = b.get('user_agent') or ua, ', '.join(brands) or ch
        else:
            r = subprocess.run(['node', '-e', _IDENTITY_JS, src], capture_output=True, text=True, timeout=20, cwd=OZ)
            if r.returncode == 0:
                fua, fch = json.loads(r.stdout)
                ua, ch = fua or ua, fch or ch
    except Exception:
        pass
    _IDENTITY_CACHE[version] = (ua, ch)
    return ua, ch


def solve(html_text: str, script_path: str, ua=UA):
    hp = os.path.join(CACHE, 'tmp_challenge_%d_%d.html' % (os.getpid(), threading.get_ident()))
    open(hp, 'w', encoding='utf8').write(html_text)
    try:
        r = subprocess.run(['node', os.path.join(OZ, 'oz_solve.js'), hp, script_path, ua], capture_output=True, text=True, timeout=40, cwd=OZ, env={**os.environ, 'NOWEBGL': '1'})
    finally:
        os.unlink(hp)
    if r.returncode:
        raise RuntimeError('node rc=%s %s' % (r.returncode, r.stderr[-400:]))
    return json.loads(r.stdout)


def forge(body: str, verbose=False) -> str:
    """Swaps the jsdom environment sections of the VM-built body for a genuine Chrome template
    (key set stays the one the CURRENT script build produced). FORCE_CHAIN env overrides the md5 chain."""
    bp = os.path.join(CACHE, 'tmp_body_%d_%d.json' % (os.getpid(), threading.get_ident()))
    open(bp, 'w', encoding='utf8').write(body)
    try:
        r = subprocess.run(['node', os.path.join(OZ, 'oz_forge.js'), bp, TEMPLATE_FP], capture_output=True, text=True, timeout=30, cwd=OZ)
    finally:
        os.unlink(bp)
    if r.returncode:
        keep = os.path.join(CACHE, 'raw', 'failed_body_%d.json' % int(time.time()))
        open(keep, 'w', encoding='utf8').write(body)
        raise RuntimeError('forge rc=%s %s (body saved to %s)' % (r.returncode, r.stderr[-600:], keep))
    if verbose:
        print(r.stderr.strip())
    return r.stdout


def get_ozon_cookies(proxy=None, verbose=False, impersonate='chrome146', forge_body=True):
    """On success the returned dict holds the open curl `session`; the caller must close() it."""
    s = Session(impersonate=impersonate, proxies={'http': proxy, 'https': proxy} if proxy else None)
    try:
        out = _get_ozon_cookies(s, verbose, forge_body)
    except BaseException:
        s.close()
        raise
    if 'session' not in out:
        s.close()
    return out


def _nav_headers(ua, ch):
    return {**ch, 'upgrade-insecure-requests': '1', 'sec-fetch-dest': 'document', 'sec-fetch-mode': 'navigate', 'sec-fetch-site': 'none', 'sec-fetch-user': '?1', 'user-agent': ua, 'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'accept-language': 'ru-RU,ru;q=0.9'}


def _get_ozon_cookies(s, verbose, forge_body):
    t0 = time.monotonic()
    ua, ch = UA, CH
    h = _nav_headers(ua, ch)
    # Ozon rotates builds between requests; the fp base (and its identity) depends on the served
    # build — so re-derive the identity from each fresh challenge until it matches the headers.
    for attempt in range(3):
        r = s.get('https://www.ozon.ru/', headers=h, allow_redirects=True)
        if verbose: print('GET /', r.status_code, len(r.text), list(s.cookies.get_dict()))
        m = SCRIPT_URL_RE.search(r.text)
        if not m:
            why = 'no challenge script' if attempt == 0 else 'no challenge script after identity switch'
            return {'ok': False, 'why': why, 'status': r.status_code, 'cookies': s.cookies.get_dict(), 'ua': ua, 'ch': ch}
        url = m.group(1)
        version = url.rsplit('script_v', 1)[-1][:-3]
        b_ua, b_ch = identity_for_build(version)
        if b_ua == ua and b_ch == ch['sec-ch-ua']:
            break
        if verbose: print('identity switch for build %s: %s' % (version, b_ua[:70]))
        ua, ch = b_ua, {**CH, 'sec-ch-ua': b_ch}
        h = _nav_headers(ua, ch)
    fn = os.path.join(CACHE, 'cache_' + url.split('/')[-1])
    if not os.path.exists(fn):
        open(fn, 'w', encoding='utf8').write(s.get(url, headers={'user-agent': ua}).text)
    t1 = time.monotonic()
    sol = solve(r.text, fn, ua)
    t2 = time.monotonic()
    body = sol['body']
    open(os.path.join(CACHE, 'raw', 'last_vm_body.json'), 'w', encoding='utf8').write(body)
    open(os.path.join(CACHE, 'raw', 'last_challenge.html'), 'w', encoding='utf8').write(r.text)
    if forge_body:
        body = forge(body, verbose=verbose)
    h2 = {**ch, 'user-agent': ua, 'accept': '*/*', 'accept-language': 'ru-RU,ru;q=0.9', 'content-type': 'application/json;charset=UTF-8',
          'origin': 'https://www.ozon.ru', 'referer': str(r.url), 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin'}
    rr = s.post('https://www.ozon.ru' + sol['url'] if sol['url'].startswith('/') else sol['url'], data=body, headers=h2)
    if verbose: print('POST', sol['url'], rr.status_code, rr.text[:300], list(s.cookies.get_dict()))
    post_ok = rr.status_code == 200 and '"ok":true' in rr.text
    reload_html = ''
    # The POST answer itself sets no cookies — a reload of / is what materializes the token set.
    if post_ok:
        r2 = s.get(str(r.url), headers={**h, 'sec-fetch-site': 'same-origin', 'referer': str(r.url)})
        reload_html = r2.text
        if verbose: print('RELOAD', r2.status_code, len(r2.text), list(s.cookies.get_dict()))
    return {'ok': '__Secure-access-token' in s.cookies.get_dict(), 'post_ok': post_ok, 'status': rr.status_code, 'resp': rr.text[:300],
            'hdr': {k: v for k, v in rr.headers.items() if k.lower().startswith('x-o3')}, 'cookies': s.cookies.get_dict(),
            'script': url, 'solve_s': t2 - t1, 'node_ms': sol['ms'], 'rss': sol['rss'], 'total_s': time.monotonic() - t0, 'session': s, 'final_url': str(r.url), 'reload_html': reload_html, 'ua': ua, 'ch': ch}


def check_api(s: Session, query='телефон', verbose=False, ua=None, ch=None):
    """Real search-API request with the obtained cookies — the same check the summary's 5/5 run did.
    Uses the session's own identity (pass the `ua`/`ch` the flow returned), no app imports (js_runtime-local)."""
    from urllib.parse import quote_plus
    ua, ch = ua or UA, ch or CH
    q = quote_plus(query)
    nav = 'https://www.ozon.ru/search/?from_global=true&text=' + q
    s.get(nav, headers={**ch, 'user-agent': ua, 'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8', 'accept-language': 'ru-RU,ru;q=0.9', 'sec-fetch-dest': 'document', 'sec-fetch-mode': 'navigate', 'sec-fetch-site': 'same-origin', 'referer': 'https://www.ozon.ru/'})
    r = s.get('https://www.ozon.ru/api/entrypoint-api.bx/page/json/v2', params={'url': '/search/?from_global=true&text=' + q},
              headers={**ch, 'user-agent': ua, 'accept': 'application/json', 'accept-language': 'ru-RU,ru;q=0.9', 'content-type': 'application/json',
                       'referer': nav, 'sec-fetch-dest': 'empty', 'sec-fetch-mode': 'cors', 'sec-fetch-site': 'same-origin',
                       'x-o3-app-name': 'dweb_client', 'x-o3-app-version': 'release_30-6-2026_35d481b8'})
    if verbose: print('API', r.status_code, len(r.text), r.text[:120])
    return r.status_code == 200 and len(r.text) > 10000


if __name__ == '__main__':
    o = get_ozon_cookies(verbose=True)
    print({k: (v if k not in ('cookies', 'reload_html') else (list(v) if k == 'cookies' else '<%d bytes>' % len(v))) for k, v in o.items() if k != 'session'})
    if o['ok']:
        print('API check:', check_api(o['session'], verbose=True, ua=o.get('ua'), ch=o.get('ch')))
