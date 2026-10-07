import json,time
from curl_cffi.requests import Session
s=Session(impersonate='firefox135')
B='https://www.wildberries.ru/__wbaas/challenges/antibot'
c=json.load(open('wb/raw/challenge1.json'))['challenge']
for p in ['/statics/challenge-solver_v1.0.8.js','/statics/behavior-tracker_v1.0.3.js',c['scriptPath']]:
    r=s.get(B+p); print(p,r.status_code,len(r.content)); open('wb/raw/'+p.split('/')[-1],'wb').write(r.content); time.sleep(2)
