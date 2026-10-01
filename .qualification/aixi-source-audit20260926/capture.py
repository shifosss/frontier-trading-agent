"""AIXI bounded, read-only-source audit. Writes only this qualification folder."""
from pathlib import Path
from datetime import datetime,timezone
import hashlib,json,sys
import httpx
from frontier.paper_broker import _paper_credentials
ROOT=Path(__file__).resolve().parent
SOURCES={
 'nasdaq-sep2026':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-643',
 'sec-sep2026-6k':'https://www.sec.gov/Archives/edgar/data/1935172/000121390026096964/ea0304260-6k_xiao1.htm',
 'sec-sep2026-release':'https://www.sec.gov/Archives/edgar/data/1935172/000121390026096964/ea030426001ex99-1.htm',
 'citi-sep2026-notice':'https://depositaryreceipts.citi.com/adr/common/file.aspx?idf=7973',
 'nasdaq-may2026':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2026-312',
 'nasdaq-aug2024':'https://www.nasdaqtrader.com/TraderNews.aspx?id=ECA2024-396',
}
def dump(name,v): (ROOT/name).write_text(json.dumps(v,indent=2,allow_nan=False),encoding='utf-8')
def save(stem,response,params=None):
 raw=response.content; digest=hashlib.sha256(raw).hexdigest()
 suffix='.pdf' if 'pdf' in response.headers.get('content-type','') else '.raw'
 name=stem+'.'+digest+suffix
 (ROOT/name).write_bytes(raw)
 meta={'method':'GET','url':str(response.url),'params':params,'captured_at':datetime.now(timezone.utc).isoformat(),'status_code':response.status_code,'sha256':digest,'bytes':len(raw),'content_type':response.headers.get('content-type'),'response_date':response.headers.get('date'),'raw_file':name}
 dump(stem+'.capture.json',meta); return meta

def capture():
 definition={'declared_at':datetime.now(timezone.utc).isoformat(),'frozen_run':'90af4c840aad48f7ab58fba7a682f96a','frozen_symbol':'AIXI','selection':'Diagnose independently flagged extreme label, inspect all surrounding returns in both directions; no profit-based corrections or fitting','sources':SOURCES,'bar_request':{'endpoint':'https://data.alpaca.markets/v2/stocks/AIXI/bars','timeframe':'1Day','start':'2023-03-09T00:00:00Z','end':'2026-09-18T23:59:59Z','feed':'sip','asof':'2026-09-18','currency':'USD','limit':10000,'sort':'asc'},'adjustments':['raw','split'],'max_pages_per_adjustment':2,'no_mutations':'No raw capture, model, policy, journal, broker, orders or funds changed'}
 assert not (ROOT/'definition.json').exists(),'Preserve original attempt'
 dump('definition.json',definition)
 results=[]
 with httpx.Client(timeout=30,follow_redirects=True,headers={'User-Agent':'Mozilla/5.0'}) as client:
  for stem,url in SOURCES.items():
   try: results.append(save(stem,client.get(url)))
   except httpx.HTTPError as exc: results.append({'source':stem,'error_type':type(exc).__name__})
   dump('capture-summary.json',results)
 key,secret=_paper_credentials()
 with httpx.Client(timeout=30,follow_redirects=False,headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret}) as client:
  for adjustment in definition['adjustments']:
   params={k:v for k,v in definition['bar_request'].items() if k!='endpoint'};params['adjustment']=adjustment
   for page in range(1,3):
    try:
     response=client.get(definition['bar_request']['endpoint'],params=params)
     meta=save(f'alpaca-{adjustment}-{page}',response,params.copy());results.append(meta)
     dump('capture-summary.json',results)
     if response.status_code!=200:break
     token=response.json().get('next_page_token')
     if not token:break
     params['page_token']=token
    except httpx.HTTPError as exc:
     results.append({'source':f'alpaca-{adjustment}-{page}','error_type':type(exc).__name__});dump('capture-summary.json',results);break
 print(json.dumps([{k:v for k,v in x.items() if k in ('url','status_code','bytes','error_type')} for x in results],indent=2))
if __name__=='__main__':capture()
