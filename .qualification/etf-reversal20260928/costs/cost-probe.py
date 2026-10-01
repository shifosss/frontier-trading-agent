"""Bounded historical GET capture; offline analysis is a separate invocation."""
import sys, json, hashlib
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
import httpx
from frontier.paper_broker import _paper_credentials
ROOT=Path(__file__).resolve().parent
DEF=ROOT/'cost-definition.json'
def dump(p,v): p.write_text(json.dumps(v,indent=2,allow_nan=False),encoding='utf-8')
def declare():
    assert not DEF.exists()
    windows=[]
    for date in ['2016-01-04','2020-01-02','2024-01-02']:
        for clock in ['09:30','12:00','15:59']:
            start=pd.Timestamp(date+' '+clock,tz='America/New_York')
            windows.append({'id':date+'-'+clock.replace(':',''),'start':start.tz_convert('UTC').isoformat(),'end':(start+pd.Timedelta(minutes=1)).tz_convert('UTC').isoformat()})
    dump(DEF,{'declared_at':datetime.now(timezone.utc).isoformat(),'selection':'Return-independent purposive variation: AAPL/MSFT high-activity/high-price candidates, F/T lower-price active candidates, HRL/BANF lower-activity candidates. These are hypotheses, not measured liquidity bins. Fixed first trading sessions of 2016/2020/2024; no strategy outcomes inspected. No substitutions for empty/error cells.','symbols':['AAPL','MSFT','F','T','HRL','BANF'],'windows':windows,'max_pages_per_window':10,'endpoint':'https://data.alpaca.markets/v2/stocks/quotes','feed':'sip','analysis':'[start,end), no pre-window carry; mechanical positive price/size and noncrossed; locked retained; persist each quote to next update, equal timestamp last record receives time; no stale timeout; all conditions retained; missing is uncovered leading/empty time, not proof missing feed updates.'})
def capture():
    definition=json.loads(DEF.read_text()); key,secret=_paper_credentials(); summary=[]
    with httpx.Client(headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},timeout=30,follow_redirects=False) as client:
        for w in definition['windows']:
            params={'symbols':','.join(definition['symbols']),'start':w['start'],'end':w['end'],'feed':'sip','sort':'asc','limit':10000,'asof':w['id'][:10]}
            row={'window':w['id'],'pages':[],'complete':False}
            for page in range(1,definition['max_pages_per_window']+1):
                stem='cost-'+w['id']+'-page-'+str(page)
                assert not (ROOT/(stem+'.capture.json')).exists(), 'Never overwrite captures'
                meta={'window':w['id'],'page':page,'method':'GET','url':definition['endpoint'],'params':params.copy(),'captured_at':datetime.now(timezone.utc).isoformat()}
                try:
                    response=client.get(definition['endpoint'],params=params)
                    raw=response.content; digest=hashlib.sha256(raw).hexdigest(); name=stem+'.'+digest+'.json'
                    (ROOT/name).write_bytes(raw)
                    meta.update(status_code=response.status_code,sha256=digest,raw_file=name,bytes=len(raw),response_date=response.headers.get('date'))
                    dump(ROOT/(stem+'.capture.json'),meta); row['pages'].append(stem+'.capture.json')
                    if response.status_code!=200: row['error']='HTTP '+str(response.status_code); break
                    token=response.json().get('next_page_token')
                    if not token: row['complete']=True; break
                    params['page_token']=token
                except httpx.TransportError as exc:
                    meta['error']=type(exc).__name__; dump(ROOT/(stem+'.capture.json'),meta); row['error']=meta['error']; break
            summary.append(row); dump(ROOT/'cost-capture-summary.json',summary)
            print(w['id'],len(row['pages']),row['complete'],flush=True)
if __name__=='__main__':
    {'declare':declare,'capture':capture}[sys.argv[1]]()
