import time
from curl_cffi.requests import Session
s=Session(impersonate='firefox135')
B='https://www.wildberries.ru/__wbaas/challenges/antibot/__static/v2/'
for f in ['browser-check.js','index-yz9dDw8g.js','index-CAPy0gUu.css']:
    r=s.get(B+f); print(f,r.status_code,len(r.content),r.headers.get('content-type'))
    open('wb/raw/'+f,'wb').write(r.content); time.sleep(2)
