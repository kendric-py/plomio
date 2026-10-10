"""One request to ozon.ru: save the current challenge HTML, its script, and the VM-built body into ready/ozon/raw/ (no POST to /abt/result)."""
import json, os, subprocess, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', '..', 'ready', 'ozon'))
from curl_cffi.requests import Session
import oz_flow as F

s = Session(impersonate='chrome146')
r = s.get('https://www.ozon.ru/', headers={'user-agent': F.UA, 'accept-language': 'ru-RU,ru;q=0.9'})
m = F.SCRIPT_URL_RE.search(r.text)
print('status', r.status_code, 'script', m.group(1) if m else None)
if not m:
    sys.exit(1)
tag = m.group(1).split('/')[-1].replace('.js', '')
raw = os.path.join(F.OZ, 'raw')
open(os.path.join(raw, f'probe_{tag}.html'), 'w', encoding='utf8').write(r.text)
open(os.path.join(raw, f'probe_{tag}.js'), 'w', encoding='utf8').write(s.get(m.group(1)).text)
o = subprocess.run(['node', 'oz_solve.js', f'raw/probe_{tag}.html', f'raw/probe_{tag}.js', F.UA], cwd=F.OZ,
                   capture_output=True, text=True, env={**os.environ, 'NOWEBGL': '1'})
sol = json.loads(o.stdout)
open(os.path.join(raw, f'probe_{tag}_body.json'), 'w', encoding='utf8').write(sol['body'])
print('saved', tag, 'body', len(sol['body']), o.stderr[-200:])
