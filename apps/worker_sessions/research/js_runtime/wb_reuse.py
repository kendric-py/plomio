import sys,time
sys.path.insert(0,'.')
from wb_flow_warm import *
from wb_check import P, API
import wb_check
from curl_cffi.requests import Session
sv=NodeSolver(); o=get_token(sv,lean=True); sv.close(); tok=o['token']
res=[]
for i in range(12):
    s=Session(impersonate='firefox135'); s.cookies.set('x_wbaas_token',tok,domain='www.wildberries.ru')
    r=s.get(API,params=P,headers=wb_check.H); res.append(r.status_code); time.sleep(2)
print('same token x12:',res)
s=Session(impersonate='firefox135'); s.cookies.set('x_wbaas_token',tok,domain='www.wildberries.ru')
h=dict(wb_check.H); h['user-agent']='Mozilla/5.0 (X11; Linux x86_64; rv:128.0) Gecko/20100101 Firefox/128.0'
print('other UA:',s.get(API,params=P,headers=h).status_code)
