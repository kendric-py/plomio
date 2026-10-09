"""Same as wb_flow but with a persistent Node solver process."""
import json, os, re, subprocess, time, itertools, sys
from curl_cffi.requests import Session
from wb_flow import UA, HOST, BASE, HERE, CACHE

class NodeSolver:
    def __init__(self):
        self.p = subprocess.Popen(['node', os.path.join(HERE, 'solve_server.js')], stdin=subprocess.PIPE,
                                  stdout=subprocess.PIPE, text=True, bufsize=1, cwd=HERE)
        self.ids = itertools.count()
    def solve(self, script_file, payload, ua=UA):
        i = next(self.ids)
        self.p.stdin.write(json.dumps({'id': i, 'script': script_file, 'payload': payload, 'ua': ua}) + '\n'); self.p.stdin.flush()
        r = json.loads(self.p.stdout.readline())
        if 'error' in r: raise RuntimeError(r['error'])
        return r
    def close(self):
        # kill() alone leaves a zombie and the stdin/stdout pipe fds open -> "Too many open files" over time.
        try:
            self.p.kill()
        except OSError:
            pass
        for pipe in (self.p.stdin, self.p.stdout):
            try:
                pipe.close()
            except (OSError, ValueError):
                pass
        try:
            self.p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass

SCRIPTS = {}
STATIC_KEY = '7400bd5df8b843b28254659f10915f31'
def get_token(solver, proxy=None, impersonate='firefox135', ua=UA, lean=False):
    t0 = time.monotonic()
    s = Session(impersonate=impersonate, proxies={'http': proxy, 'https': proxy} if proxy else None)
    try:
        return _get_token(s, solver, t0, lean, ua)
    finally:
        s.close()

def _get_token(s, solver, t0, lean, ua):
    if lean:
        key = STATIC_KEY
    else:
        r = s.get(HOST + '/', headers={'accept': 'text/html,*/*', 'accept-language': 'ru-RU,ru;q=0.9', 'user-agent': ua})
        key = re.search(r'data-site-key="([0-9a-f]+)"', r.text).group(1)
    h = {'user-agent': ua, 'accept-language': 'ru-RU,ru;q=0.9', 'X-Guardium-Antibot-Key': key, 'X-Guardium-Antibot-SDK-Version': 'js-front-browser/3.1.0',
         'content-type': 'application/json', 'origin': HOST, 'referer': HOST + '/'}
    if not lean:
        s.post(BASE + '/api/v1/find-frontend-settings', data='{}', headers=h)
    ch = s.post(BASE + '/api/v1/create-token', data='{}', headers=h).json()['challenge']
    sp = ch['scriptPath']; f = os.path.join(CACHE, 'cache_' + sp.split('/')[-1])
    if not os.path.exists(f):
        open(f, 'w', encoding='utf8').write(s.get(BASE + sp, headers={'user-agent': ua}).text)
    t1 = time.monotonic()
    sol = solver.solve(f, ch['payload'], ua)
    t2 = time.monotonic()
    body = {'challenge': ch, 'solution': {'payload': sol['solution']}}
    j = s.post(BASE + '/api/v1/create-token', data=json.dumps(body, separators=(',', ':')), headers=h).json()
    return {'token': j.get('secureToken'), 'resp': j, 'cookies': s.cookies.get_dict(), 'total_s': time.monotonic() - t0, 'solve_s': t2 - t1, 'node_ms': sol['ms'], 'rss': sol['rss']}

if __name__ == '__main__':
    sv = NodeSolver()
    for i in range(4):
        o = get_token(sv); print(bool(o['token']), 'total %.2f solve %.2f node %.0fms rss %.0fMB' % (o['total_s'], o['solve_s'], o['node_ms'], o['rss']/1e6)); time.sleep(2)
    sv.close()
