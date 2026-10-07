"""Run the browserless Ozon flow N times; each session is verified by a real search-API request.

Usage: python oz_check.py [N]         — N full flows (default 5), 2s pause between runs.
Set FORCE_CHAIN=v3|v4|v5 to override the md5 chain the forge encrypts with (chain-matching experiment).
"""
import json
import os
import statistics
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from oz_flow import get_ozon_cookies, check_api, OZ

N = int(sys.argv[1]) if len(sys.argv) > 1 else 5
res = []
for i in range(N):
    t0 = time.monotonic()
    try:
        o = get_ozon_cookies()
        api = check_api(o['session']) if o['ok'] else False
        # which md5 chain did the VM pick for this challenge (and what did the forge use)?
        meta = subprocess.run(
            ['node', '-e', "const c=require('./fpcodec.js');const b=JSON.parse(require('fs').readFileSync('raw/last_vm_body.json','utf8'));const d=c.decode(b.fp,b.token);console.log(d.chain)"],
            capture_output=True, text=True, cwd=OZ).stdout.strip()
        chain = os.environ.get('FORCE_CHAIN') or meta
        print(i, 'OK' if o['ok'] else 'FAIL', 'api=' + ('OK' if api else 'FAIL'), 'chain=' + chain,
              'solve=%.2fs total=%.2fs' % (o['solve_s'], o['total_s']), o.get('resp', '')[:60], flush=True)
        res.append((o['ok'] and api, o['total_s']))
    except Exception as e:
        print(i, 'EXC', repr(e)[:200], flush=True)
        res.append((False, 0))
    time.sleep(2)
v = sum(1 for ok, _ in res if ok)
print('valid %d/%d, mean total %.2fs' % (v, N, statistics.mean(t for ok, t in res if t) if any(t for _, t in res) else 0))
