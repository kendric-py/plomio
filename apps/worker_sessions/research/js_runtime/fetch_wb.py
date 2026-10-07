import sys
from curl_cffi.requests import Session
s=Session(impersonate='firefox135')
r=s.get('https://www.wildberries.ru/',headers={'accept':'text/html,*/*','accept-language':'ru-RU,ru;q=0.9'})
print(r.status_code, dict(r.headers))
open('wb/raw/index.html','w',encoding='utf8').write(r.text)
print(r.text[:3000])
print(s.cookies.get_dict())
