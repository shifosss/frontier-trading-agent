"""Bounded market-data GETs for the frozen event sample; no order endpoints."""
from pathlib import Path
from datetime import datetime,timedelta,timezone
from zoneinfo import ZoneInfo
import hashlib,json
import httpx
from frontier.paper_broker import _paper_credentials
ROOT=Path(__file__).resolve().parent

def dump(name,obj):
 (ROOT/name).write_text(json.dumps(obj,indent=2,allow_nan=False),encoding='utf-8')

def main():
 definition=json.loads((ROOT/'definition.json').read_text())
 key,secret=_paper_credentials()
 with httpx.Client(headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},timeout=30,follow_redirects=False) as client:
  for event in definition['selected']:
   day=datetime.fromisoformat(event['effective_session']).replace(tzinfo=ZoneInfo('America/New_York'))
   start=day-timedelta(days=10);end=min(day+timedelta(days=11),datetime(2026,9,19,tzinfo=ZoneInfo('America/New_York')))
   url=definition['market_data']['endpoint'].format(symbol=event['symbol'])
   for adjustment in definition['market_data']['adjustments']:
    params={'timeframe':'1Day','start':start.astimezone(timezone.utc).isoformat(),'end':(end-timedelta(microseconds=1)).astimezone(timezone.utc).isoformat(),'feed':'sip','adjustment':adjustment,'asof':'2026-09-18','currency':'USD','limit':10000,'sort':'asc'}
    for page in range(1,3):
     stem=f"{event['symbol']}-{event['effective_session']}-{adjustment}-{page}"
     path=ROOT/(stem+'.capture.json')
     assert not path.exists(),'Do not overwrite attempts'
     meta={'symbol':event['symbol'],'effective_session':event['effective_session'],'method':'GET','url':url,'params':params.copy(),'started_at':datetime.now(timezone.utc).isoformat(),'status':'request_started'}
     dump(path.name,meta)
     try:
      response=client.get(url,params=params);raw=response.content;digest=hashlib.sha256(raw).hexdigest();name=stem+'.'+digest+'.raw.json'
      (ROOT/name).write_bytes(raw)
      meta.update(status='response_retained',status_code=response.status_code,url=str(response.url),raw_file=name,sha256=digest,bytes=len(raw),captured_at=datetime.now(timezone.utc).isoformat(),response_date=response.headers.get('date'))
      token=None
      if response.status_code==200:
       payload=response.json();token=payload.get('next_page_token');meta.update(bar_count=len(payload.get('bars') or []),response_symbol=payload.get('symbol'),pagination_complete=not bool(token))
      dump(path.name,meta)
      print(stem,response.status_code,meta.get('bar_count'),flush=True)
      if not token:break
      params['page_token']=token
     except httpx.HTTPError as exc:
      meta.update(status='failed',error_type=type(exc).__name__,completed_at=datetime.now(timezone.utc).isoformat());dump(path.name,meta);print(stem,meta['error_type'],flush=True);break
if __name__=='__main__':main()
