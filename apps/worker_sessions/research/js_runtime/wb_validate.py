"""Generate N WB sessions via the browserless flow and validate each with the app's own validator."""
import sys, time, json, statistics, uuid
sys.path.insert(0, '../../../..')
sys.path.insert(0, '.')
import logging
logging.disable(logging.CRITICAL)
from core.enums import Marketplace
from packages.sessions.src.entities import SessionMessage
from apps.worker_sessions.src.generation.validation import validate_session
from wb_flow_warm import get_token, NodeSolver, UA
sv=NodeSolver()
LEAN=len(sys.argv)>2 and sys.argv[2]=='lean'

N = int(sys.argv[1]) if len(sys.argv) > 1 else 10
res = []
for i in range(N):
    t0 = time.monotonic()
    try:
        out = get_token(sv, lean=LEAN)
    except Exception as e:
        print(i, 'GEN FAIL', e); res.append((False, 0)); time.sleep(2); continue
    if not out['token']:
        print(i, 'NO TOKEN', out['resp']); res.append((False, 0)); time.sleep(2); continue
    msg = SessionMessage(marketplace=Marketplace.WILDBERRIES, proxy=None, cookies={'x_wbaas_token': out['token']},
                         user_agent=UA, sec_ch_ua='', sec_ch_ua_platform='Windows',
                         extra={'device_id': 'site_' + uuid.uuid4().hex, 'spa_version': '14.13.6'})
    gen = time.monotonic() - t0
    ok = validate_session(msg)
    print(i, 'valid' if ok else 'INVALID', 'gen=%.2fs solve=%.2fs' % (gen, out['solve_s']), flush=True)
    res.append((ok, gen)); time.sleep(2)
v = sum(1 for o, _ in res if o)
print('valid %d/%d, mean gen %.2fs' % (v, N, statistics.mean(g for _, g in res if g) if any(g for _, g in res) else 0))
