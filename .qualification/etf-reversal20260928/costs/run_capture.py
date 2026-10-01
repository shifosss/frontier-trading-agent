"""Fixed ETF quote probe with bounded streaming and preserved failures."""
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
import hashlib,importlib.util,json,math,sqlite3,time
import httpx
from frontier.historical_lab import _save
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
ENDPOINT="https://data.alpaca.markets/v2/stocks/quotes"
def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def now():return datetime.now(timezone.utc).isoformat()

class BoundedClient(httpx.Client):
    def __init__(self,definition,root,**kwargs):
        super().__init__(**kwargs)
        self.definition,self.root=definition,root
        self.calls,self.bytes,self.last,self.limit_error=0,0,0.,None
    def get(self,url,*,params):
        d=self.definition
        expected=[{'symbols':','.join(d['symbols']),'start':w['start'],'end':w['end'],
                   'feed':'sip','sort':'asc','limit':10000,'asof':w['id'][:10]} for w in d['windows']]
        basic={k:v for k,v in params.items() if k!='page_token'}
        if url!=ENDPOINT or basic not in expected or ('page_token' in params and not isinstance(params['page_token'],str)):
            raise ValueError('Request outside frozen historical quotes')
        if self.calls>=d['max_total_request_starts']:raise RuntimeError('Declared request budget exhausted')
        remaining=d['max_total_raw_bytes']-self.bytes
        if remaining<=0:raise RuntimeError('Declared total raw byte budget exhausted')
        limit=min(d['max_response_bytes'],remaining)
        time.sleep(max(0,d['minimum_request_interval_seconds']-(time.monotonic()-self.last)))
        self.last=time.monotonic();self.calls+=1
        with (self.root/'request-starts.jsonl').open('a',encoding='utf-8') as f:
            f.write(json.dumps({'at':now(),'number':self.calls,'method':'GET','url':url,'params':params})+'\n');f.flush()
        chunks=[];size=0
        with self.stream('GET',url,params=params) as response:
            for chunk in response.iter_bytes(chunk_size=65536):
                take=min(len(chunk),limit+1-size);chunks.append(chunk[:take]);size+=take
                if size>limit:
                    self.limit_error='Raw response/total byte ceiling exceeded; one-byte overflow sentinel retained'
                    break
            raw=b''.join(chunks);self.bytes+=len(raw)
            return httpx.Response(response.status_code,content=raw,headers={'date':response.headers.get('date','')},request=response.request)

def complete_denominator(root,definition):
    rows=[]
    for window in definition['windows']:
        paths=sorted(root.glob('cost-'+window['id']+'-page-*.capture.json'),key=lambda p:int(p.name.split('-page-')[1].split('.')[0]))
        row={'window':window['id'],'pages':[],'request_attempts':[p.name for p in paths],'complete':False}
        for path in paths:
            meta=json.loads(path.read_text())
            if meta.get('raw_file'):
                raw=(root/meta['raw_file']).read_bytes()
                if hashlib.sha256(raw).hexdigest()!=meta['sha256']:raise ValueError('Saved raw identity changed')
                if not meta.get('error'):
                    try:
                        body=json.loads(raw) if meta.get('status_code')==200 else None
                    except ValueError:
                        row['error']='Unparseable response preserved';break
                    row['pages'].append(path.name)
                else:body=None
            else:body=None
            row['complete']=bool(meta.get('status_code')==200 and body is not None and not body.get('next_page_token') and not meta.get('error'))
            if not row['complete']:row['error']=meta.get('error','Incomplete pagination or unsuccessful response')
        if not paths:row['error']='Not attempted after stop'
        if row['complete']:row.pop('error',None)
        rows.append(row)
    _save(root/'cost-capture-summary.json',rows);return rows

def qualify_costs(root,definition):
    cells=json.loads((root/'cost-analysis.json').read_text())['cells']
    expected={(w['id'],s) for w in definition['windows'] for s in definition['symbols']}
    actual=[(c['window'],c['symbol']) for c in cells]
    if len(actual)!=len(expected) or set(actual)!=expected:raise ValueError('Cell denominator mismatch')
    invalid=[]
    for cell in cells:
        spread=cell.get('duration_weighted_spread_bps')
        if (not cell.get('pagination_complete') or cell.get('error')
            or cell.get('valid_observed_seconds',0)<definition['cost_rule']['minimum_valid_seconds_per_cell']
            or not spread or not math.isfinite(spread['mean']) or spread['mean']<0):
            invalid.append({'window':cell['window'],'symbol':cell['symbol'],'reason':'Incomplete source/statistics or insufficient valid quoted-state duration'})
    result={'at':now(),'status':'unqualified' if invalid else 'qualified_quote_informed_sensitivity',
            'cells':len(cells),'invalid_cells':invalid,'definition_sha256':sha(root/'cost-definition.json'),
            'not_realized_slippage_or_all_in_cost':True}
    if not invalid:
        maximum=max(c['duration_weighted_spread_bps']['mean'] for c in cells)
        result.update(maximum_duration_weighted_full_spread_bps=maximum,
            round_trip_bps=math.ceil(maximum)+definition['cost_rule']['additional_round_trip_bps'],
            limiting_cells=[{'window':c['window'],'symbol':c['symbol']} for c in cells if c['duration_weighted_spread_bps']['mean']==maximum])
    _save(root/'cost-qualification.json',result);return result

def main():
    definition=json.loads((ROOT/'cost-definition.json').read_text())
    identity=json.loads((ROOT/'implementation.json').read_text())
    for name,h in identity['files'].items():
        if sha(ROOT/name)!=h:raise ValueError('Frozen local input changed: '+name)
    for name,h in identity['external_files'].items():
        if sha(REPO/name)!=h:raise ValueError('Frozen dependency changed: '+name)
    lock=sqlite3.connect(ROOT/'capture.lock.sqlite',timeout=0)
    try:
        lock.execute('BEGIN EXCLUSIVE')
        if (ROOT/'request-starts.jsonl').exists() or list(ROOT.glob('cost-*-page-*.capture.json')):
            raise ValueError('Existing attempts require separate reviewed reconciliation; no automatic retries')
        probe=load('unchanged_etf_probe',ROOT/'cost-probe.py')
        clients=[]
        def factory(**kwargs):
            client=BoundedClient(definition,ROOT,**kwargs);clients.append(client);return client
        def save_capture(path,value):
            if isinstance(value,dict) and value.get('raw_file') and clients and clients[0].limit_error:
                value['error']=clients[0].limit_error
            _save(path,value)
            if isinstance(value,dict) and (value.get('status_code') in [401,403,429] or value.get('error','').startswith('Raw response/total')):
                raise PermissionError('Preserved access/rate/byte failure; no further requests')
        probe.httpx=SimpleNamespace(Client=factory,TransportError=httpx.TransportError);probe.dump=save_capture
        error=None
        try:probe.capture()
        except Exception as exc:error={'type':type(exc).__name__,'message':str(exc)}
        summary=complete_denominator(ROOT,definition)
        load('unchanged_etf_analyzer',ROOT/'cost-analyze.py').main()
        qualified=qualify_costs(ROOT,definition)
        result={'at':now(),'error':error,'complete_windows':sum(r['complete'] for r in summary),
                'planned_windows':3,'planned_cells':33,'cost_status':qualified['status'],
                'request_starts':sum(c.calls for c in clients),'raw_bytes':sum(c.bytes for c in clients)}
        _save(ROOT/'completion.json',result);print(json.dumps(result),flush=True)
        if error:raise SystemExit(1)
    finally:lock.rollback();lock.close()
if __name__=='__main__':main()
