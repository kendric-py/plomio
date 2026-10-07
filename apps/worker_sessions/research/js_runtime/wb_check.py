import sys,time,json
sys.path.insert(0,'.')
from wb_flow import *
from curl_cffi.requests import Session
P={'ab_testing':'false','appType':'1','curr':'rub','dest':'-1257786','hide_dtype':'15','hide_vflags':'4294967296','inheritFilters':'false','lang':'ru','locale':'ru','resultset':'catalog','sort':'popular','spp':'30','suppressSpellcheck':'false','query':'телефон','page':'1'}
API='https://www.wildberries.ru/__internal/u-search/exactmatch/ru/common/v18/search'
H={'accept':'*/*','user-agent':UA,'referer':HOST+'/','x-requested-with':'XMLHttpRequest','x-spa-version':'14.13.6','x-userid':'0','deviceid':'site_abc'}
