import json,time
from curl_cffi.requests import Session
s=Session(impersonate='firefox135')
H='https://www.wildberries.ru'
B=H+'/__wbaas/challenges/antibot'
key='7400bd5df8b843b28254659f10915f31'
h={'X-Guardium-Antibot-Key':key,'X-Guardium-Antibot-SDK-Version':'js-front-browser/3.1.0','content-type':'application/json'}
r=s.post(B+'/api/v1/find-frontend-settings',data='{}',headers=h)
print(r.status_code,r.text[:2000]); open('wb/raw/settings.json','w').write(r.text)
time.sleep(2)
r=s.post(B+'/api/v1/create-token',data='{}',headers=h)
print(r.status_code,r.text[:3000]); open('wb/raw/challenge1.json','w').write(r.text)
