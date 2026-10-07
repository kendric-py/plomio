"""WB antibot without browser: HTTP protocol in curl_cffi + challenge script in Node vm. Returns x_wbaas_token."""
import json, os, subprocess, sys, tempfile, time
from curl_cffi.requests import Session

UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0'
HOST = 'https://www.wildberries.ru'
BASE = HOST + '/__wbaas/challenges/antibot'
HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPT_CACHE: dict[str, str] = {}


def solve_in_node(script_path: str, script_src: str, payload: str, ua: str = UA):
    key = script_path.split('/')[-1]
    sp = os.path.join(HERE, 'wb', 'cache_' + key)
    if not os.path.exists(sp):
        open(sp, 'w', encoding='utf8').write(script_src)
    pp = tempfile.NamedTemporaryFile('w', delete=False, suffix='.txt')
    pp.write(payload); pp.close()
    try:
        r = subprocess.run(['node', os.path.join(HERE, 'wb', 'solve_vm.js'), sp, pp.name, ua],
                           capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(pp.name)
    if r.returncode:
        raise RuntimeError('node: ' + r.stderr[-500:])
    return json.loads(r.stdout)


def get_wb_token(proxy: str | None = None, with_meta=False, verbose=False, impersonate='firefox135'):
    t0 = time.monotonic()
    s = Session(impersonate=impersonate, proxies={'http': proxy, 'https': proxy} if proxy else None)
    r = s.get(HOST + '/', headers={'accept': 'text/html,*/*', 'accept-language': 'ru-RU,ru;q=0.9', 'user-agent': UA})
    import re
    m = re.search(r'data-site-key="([0-9a-f]+)"', r.text)
    if not m:
        raise RuntimeError(f'no site key, status={r.status_code}')
    key = m.group(1)
    h = {'X-Guardium-Antibot-Key': key, 'X-Guardium-Antibot-SDK-Version': 'js-front-browser/3.1.0',
         'content-type': 'application/json', 'origin': HOST, 'referer': HOST + '/'}
    st = s.post(BASE + '/api/v1/find-frontend-settings', data='{}', headers=h).json()
    r = s.post(BASE + '/api/v1/create-token', data='{}', headers=h)
    ch = r.json()['challenge']
    sp = ch['scriptPath']
    if sp not in SCRIPT_CACHE:
        SCRIPT_CACHE[sp] = s.get(BASE + sp, headers={'user-agent': UA}).text
    t1 = time.monotonic()
    sol = solve_in_node(sp, SCRIPT_CACHE[sp], ch['payload'])
    t2 = time.monotonic()
    body = {'challenge': ch, 'solution': {'payload': sol['solution']}}
    r = s.post(BASE + '/api/v1/create-token', data=json.dumps(body, separators=(',', ':')), headers=h)
    if verbose:
        print('create-token#2', r.status_code, r.text[:300])
    j = r.json()
    tok = j.get('secureToken')
    return {'token': tok, 'resp': j if not tok else None, 'cookies': s.cookies.get_dict(), 'script': sp,
            'total_s': time.monotonic() - t0, 'solve_s': t2 - t1, 'node': sol, 'session': s}


if __name__ == '__main__':
    out = get_wb_token(verbose=True)
    print({k: v for k, v in out.items() if k != 'session'})
