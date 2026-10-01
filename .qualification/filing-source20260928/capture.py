"""Bounded original10-Q source capture. Source qualification is a separate stage."""
from collections import Counter
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlparse, urljoin, parse_qs
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError, URLError
from zoneinfo import ZoneInfo
import hashlib, json, os, re, sqlite3, time
from frontier.historical_lab import _save

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent.parent

def now(): return datetime.now(timezone.utc).isoformat()
def sha(data): return hashlib.sha256(data).hexdigest()
def load(path): return json.loads(path.read_text(encoding='utf-8'))
class CaptureError(Exception): pass
class Halt(CaptureError): pass

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs): return None

def allowed_url(url):
    x=urlparse(url)
    return x.scheme=='https' and not x.query and not x.fragment and not x.username and ((x.netloc=='data.sec.gov' and re.fullmatch(r'/submissions/CIK\d{10}(?:-submissions-\d+)?\.json',x.path)) or (x.netloc=='www.sec.gov' and re.fullmatch(r'/Archives/edgar/data/\d+/[A-Za-z0-9_.\-/]+',x.path) and '..' not in x.path.split('/')))

class Cache:
    def __init__(self,root,request,repo=REPO,opener=None):
        self.root,self.request,self.repo=root,request,repo
        self.opener=opener or build_opener(NoRedirect())
        self.reuse={r['url']:r for r in request['reuse']}
        self.last_request=0.
        (root/'resources').mkdir(exist_ok=True); (root/'raw').mkdir(exist_ok=True)
        self.journal=root/'requests.jsonl'
        self.starts=[r for r in map(json.loads,self.journal.read_text().splitlines()) if r['event']=='request_started'] if self.journal.exists() else []
        self.used_bytes=sum(f.stat().st_size for f in (root/'raw').glob('*.bin'))
    def append(self,row):
        with self.journal.open('a',encoding='utf-8') as f:
            f.write(json.dumps(dict(at=now(),**row))+'\n'); f.flush(); os.fsync(f.fileno())
    def read(self,meta):
        if 'path' not in meta: raise CaptureError('Saved source failure: '+meta['url']+' '+meta.get('error','missing payload'))
        path=self.repo/meta['path'] if meta.get('reused') else self.root/meta['path']
        try: data=path.read_bytes()
        except OSError as exc: raise Halt('Cached source missing/unreadable: '+str(path)) from exc
        if len(data)!=meta['bytes'] or sha(data)!=meta['sha256']: raise Halt('Cached source identity mismatch: '+str(path))
        if meta.get('error') or meta.get('status')!=200: raise CaptureError('Saved source failure: '+meta['url'])
        return data,meta
    def get(self,url):
        if not allowed_url(url): raise Halt('URL outside fixed SEC data scope: '+url)
        if (self.root/'STOP.json').exists(): raise Halt('Prior access/limit stop requires review')
        record=self.root/'resources'/(sha(url.encode())+'.json')
        if record.exists(): return self.read(load(record))
        if url in self.reuse:
            meta=dict(self.reuse[url],reused=True,status=200); data,result=self.read(meta); _save(record,meta); return data,result
        attempts=sum(r['url']==url for r in self.starts)
        if len(self.starts)>=self.request['max_lifetime_network_attempts'] or attempts>=self.request['max_attempts_per_url']: raise Halt('Lifetime request/URL attempt ceiling reached')
        remaining=self.request['max_total_raw_bytes']-self.used_bytes
        if remaining<=0: raise Halt('Raw source byte ceiling reached')
        time.sleep(max(0,self.request['minimum_request_interval_seconds']-(time.monotonic()-self.last_request)))
        started=dict(event='request_started',url=url,attempt=attempts+1); self.append(started); self.starts.append(started); self.last_request=time.monotonic()
        meta=dict(url=url,requested_at_utc=now(),attempt=attempts+1,reused=False)
        limit=min(self.request['max_response_bytes'],remaining)
        try:
            try: response=self.opener.open(Request(url,headers={'User-Agent':self.request['user_agent'],'Accept-Encoding':'identity'}),timeout=self.request['timeout_seconds'])
            except HTTPError as exc: response=exc
            with response:
                raw=response.read(limit+1); meta.update(status=response.status,final_url=response.url,headers=dict(response.headers),retrieved_at_utc=now(),sha256=sha(raw),bytes=len(raw),path='raw/'+sha(raw)+'.bin')
            target=self.root/meta['path']
            if not target.exists(): target.write_bytes(raw); self.used_bytes+=len(raw)
            if len(raw)>limit: meta['error']='Response/raw byte ceiling exceeded; payload truncated'
            elif meta['status']!=200: meta['error']='HTTP '+str(meta['status'])
        except (URLError,TimeoutError,OSError) as exc:
            meta.update(error=type(exc).__name__+': '+str(exc),status=None)
        _save(record,meta); self.append(dict(event='request_finished',url=url,status=meta.get('status'),error=meta.get('error'),bytes=meta.get('bytes',0)))
        if meta.get('status') in self.request['stop_http_status'] or meta.get('error','').startswith('Response/raw'):
            _save(self.root/'STOP.json',meta); raise Halt(meta['error'])
        if meta.get('error'): raise CaptureError(meta['error'])
        return self.read(meta)

class Index(HTMLParser):
    def __init__(self):
        super().__init__(); self.text=[]; self.rows=[]; self.row=None; self.cell=None
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='tr': self.row=[]
        elif tag=='td' and self.row is not None: self.cell={'text':[],'links':[]}
        elif tag=='a' and self.cell is not None and 'href'in attrs: self.cell['links'].append(attrs['href'])
    def handle_data(self,data):
        self.text.append(data)
        if self.cell is not None: self.cell['text'].append(data)
    def handle_endtag(self,tag):
        if tag=='td' and self.cell is not None:
            self.cell['text']=' '.join(''.join(self.cell['text']).split()); self.row.append(self.cell); self.cell=None
        elif tag=='tr' and self.row is not None: self.rows.append(self.row); self.row=None

def archive_base(issuer,acc):
    if not re.fullmatch(r'\d{10}-\d{2}-\d{6}',acc): raise CaptureError('Invalid accession')
    return f'https://www.sec.gov/Archives/edgar/data/{int(issuer["cik"])}/{acc.replace("-","")}/'

def document_url(base,href):
    if href.startswith('/ix?') or href.startswith('/ixviewer/doc/action?'):
        values=parse_qs(urlparse(href).query).get('doc',[])
        if len(values)!=1: raise CaptureError('Ambiguous inline document route')
        href=values[0]
    url=urljoin(base,href)
    if not url.startswith(base) or not allowed_url(url): raise CaptureError('Document outside original accession: '+url)
    return url

def parse_index(raw,base,accession,primary):
    parser=Index(); parser.feed(raw.decode('utf-8')); text=' '.join(' '.join(parser.text).split())
    def field(pattern):
        match=re.search(pattern,text)
        if not match: raise CaptureError('Missing index field: '+pattern)
        return match[1]
    if field(r'SEC Accession No\.\s+([0-9-]+)')!=accession: raise CaptureError('Index accession mismatch')
    docs=[]
    for row in parser.rows:
        if len(row)>=4 and row[2]['links']:
            docs.append({'description':row[1]['text'],'type':row[3]['text'],'url':document_url(base,row[2]['links'][0])})
    primaries=[d for d in docs if d['type']=='10-Q']
    expected=document_url(base,primary)
    if len(primaries)!=1 or primaries[0]['url']!=expected: raise CaptureError('Ambiguous/mismatched original10-Q document rows')
    return {'accepted_local':field(r'Accepted\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'),'filing_date':field(r'Filing Date\s+(\d{4}-\d{2}-\d{2})'),'primary':expected,'original_instances':[d['url'] for d in docs if d['type']=='EX-101.INS'],'documents':docs}

def table_rows(table):
    if not isinstance(table,dict) or not isinstance(table.get('accessionNumber'),list): raise CaptureError('Unrecognized submissions table')
    if not {'form','filingDate'}.issubset(table): raise CaptureError('Missing submissions membership columns')
    n=len(table['accessionNumber'])
    if any(not isinstance(v,list) or len(v)!=n for v in table.values()): raise CaptureError('Submissions parallel arrays differ')
    rows=[{k:v[i] for k,v in table.items()} for i in range(n)]
    for r in rows:
        if not isinstance(r['accessionNumber'],str) or not re.fullmatch(r'\d{10}-\d{2}-\d{6}',r['accessionNumber']): raise CaptureError('Invalid registry accession')
        if not isinstance(r['filingDate'],str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',r['filingDate']): raise CaptureError('Missing/invalid registry filing date')
        datetime.strptime(r['filingDate'],'%Y-%m-%d')
    return rows

def history_files(body,request):
    files=body['filings']['files']; selected=[]
    for f in files:
        if not all(k in f for k in ['name','filingFrom','filingTo']): raise CaptureError('Missing history range')
        try:
            dates=[datetime.strptime(f[k],'%Y-%m-%d') for k in ['filingFrom','filingTo']]
            if dates[0]>dates[1]: raise ValueError('Reversed range')
        except (TypeError,ValueError) as exc: raise CaptureError('Invalid history filing range') from exc
        if f['filingFrom']<=request['filed_through'] and f['filingTo']>=request['filed_from']: selected.append(f)
    if len(selected)>request['max_history_pages_per_issuer']: raise Halt('History page ceiling; discovery incomplete')
    return selected

def clock_check(row,index,header,issuer):
    def sgml(name):
        m=re.search('<'+name+r'>\s*([^\r\n<]+)',header); return m[1].strip() if m else None
    issues=[]; accepted=sgml('ACCEPTANCE-DATETIME'); date=sgml('FILING-DATE'); ciks=re.findall(r'<CIK>\s*(\d+)',header)
    if sgml('ACCESSION-NUMBER')!=row['accessionNumber']: issues.append('header accession mismatch/missing')
    if issuer['cik'] not in [x.zfill(10) for x in ciks]: issues.append('header CIK mismatch/missing')
    if sgml('TYPE')!='10-Q': issues.append('header form mismatch/missing')
    if date!=index['filing_date'].replace('-','') or row['filingDate']!=index['filing_date']: issues.append('filing date mismatch/missing')
    if accepted!=re.sub(r'[- :]', '',index['accepted_local']): issues.append('acceptance header/index mismatch/missing')
    try:
        stamp=datetime.fromisoformat(row['acceptanceDateTime'].replace('Z','+00:00'))
        if stamp.tzinfo is None: raise ValueError('No explicit timezone')
        if stamp.astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M:%S')!=index['accepted_local']: issues.append('API/index acceptance mismatch')
    except (KeyError,TypeError,ValueError): issues.append('API acceptance missing/invalid timezone')
    return {'api_acceptance':row.get('acceptanceDateTime'),'index_accepted_local':index['accepted_local'],'header_accepted':accepted,'filing_date':index['filing_date'],'timezone':'America/New_York','issues':issues,'timestamp_sources_consistent':not issues,'public_dissemination_instant_verified':False}

def discover(cache,issuer):
    root=cache.root; request=cache.request; destination=root/'issuers'/issuer['symbol']; destination.mkdir(parents=True,exist_ok=True)
    sources=[]; rows=[]; failure=None
    try:
        data,meta=cache.get(f'https://data.sec.gov/submissions/CIK{issuer["cik"]}.json'); body=json.loads(data); sources.append(meta)
        if str(body['cik']).zfill(10)!=issuer['cik'] or issuer['symbol'] not in body['tickers']: raise CaptureError('Current issuer metadata identity mismatch')
        rows=table_rows(body['filings']['recent']); _save(destination/'current-identity.json',{k:body.get(k) for k in ['cik','name','tickers','exchanges','formerNames']})
        for f in history_files(body,request):
            if not re.fullmatch('CIK'+issuer['cik']+r'-submissions-\d+\.json',f['name']): raise CaptureError('History filename/issuer mismatch')
            data,meta=cache.get('https://data.sec.gov/submissions/'+f['name']); sources.append(meta); rows.extend(table_rows(json.loads(data)))
    except (CaptureError,ValueError,KeyError,TypeError) as exc:
        failure=type(exc).__name__+': '+str(exc)
        if isinstance(exc,Halt):
            _save(destination/'discovery.json',{'complete':False,'error':failure,'sources':sources,'rows':rows}); raise
    unique={}; duplicates=[]
    for row in rows:
        acc=row['accessionNumber']
        if acc in unique:
            if row!=unique[acc]: failure='Conflicting accession metadata: '+acc
            duplicates.append(acc)
        else: unique[acc]=row
    originals=[r for r in unique.values() if r.get('form')=='10-Q' and request['filed_from']<=r.get('filingDate','')<=request['filed_through']]
    originals.sort(key=lambda r:(r['filingDate'],r.get('acceptanceDateTime') or '',r['accessionNumber']))
    result={'complete':failure is None,'error':failure,'sources':sources,'rows':rows,'duplicate_accessions':duplicates,'original_accessions':originals,'amendment_metadata':[r for r in unique.values() if r.get('form')=='10-Q/A']}
    result['filed_year_counts']={str(y):sum(r['filingDate'].startswith(str(y)+'-') for r in originals) for y in range(2012,2026)}
    periods={}
    for r in originals: periods.setdefault(r.get('reportDate') or 'missing',[]).append(r['accessionNumber'])
    result['report_period_accessions']=periods
    result['duplicate_report_periods']={k:v for k,v in periods.items() if k!='missing' and len(v)>1}
    result['coverage_review_needed']=[{'filed_year':y,'observed_originals':n,'reason':'fewer than3 observed; fiscal-quarter completeness not inferred'} for y,n in result['filed_year_counts'].items() if n<3]
    if not originals: result.update(complete=False,error='Zero original accessions; unresolved coverage')
    _save(destination/'discovery.json',result)
    if len(originals)>request['max_original_accessions_per_issuer']:
        result.update(complete=False,error='Original accession ceiling; membership preserved'); _save(destination/'discovery.json',result); raise Halt(result['error'])
    return result

def capture_filing(cache,issuer,row):
    acc=row['accessionNumber']; path=cache.root/'filings'/issuer['symbol']/(acc+'.json')
    if path.exists():
        saved=load(path)
        if saved.get('issuer')!=issuer or saved.get('registry_row')!=row: raise Halt('Saved filing registry identity mismatch: '+acc)
        for source in saved.get('sources',[]): cache.read(source)
        return saved
    result={'issuer':issuer,'registry_row':row,'status':'incomplete','sources':[]}
    try:
        base=archive_base(issuer,acc); index_url=cache.request['index_url_overrides'].get(acc,base+acc+'-index.html')
        raw,meta=cache.get(index_url); result['sources'].append(meta)
        if not isinstance(row.get('primaryDocument'),str) or not row['primaryDocument']: raise CaptureError('Missing original primary document metadata')
        index=parse_index(raw,base,acc,row['primaryDocument']); result['index']=index
        raw,meta=cache.get(base+acc+'.hdr.sgml'); result['sources'].append(meta); result['clock']=clock_check(row,index,raw.decode('utf-8'),issuer)
        raw,meta=cache.get(index['primary']); result['sources'].append(meta)
        inline=bool(re.search(rb'<ix:non(?:fraction|numeric)\b',raw,re.I)); result['fact_representation']='inline_primary' if inline else 'original_xbrl_instance'
        result['inline_API_flag']=row.get('isInlineXBRL'); result['fact_sources']=[meta] if inline else []
        if not inline:
            if len(index['original_instances'])!=1: raise CaptureError('Non-inline original requires exactly one EX-101.INS; no substitute selected')
            raw,meta=cache.get(index['original_instances'][0]); result['sources'].append(meta); result['fact_sources'].append(meta)
            if not re.search(rb'<(?:[A-Za-z_][\w.-]*:)?xbrl\b',raw): raise CaptureError('Original instance has no XBRL root marker')
        result['status']='captured'; result['feature_qualified']=False
    except CaptureError as exc:
        result['error']=str(exc)
        if isinstance(exc,Halt): _save(path,result); raise
    _save(path,result); return result

def run(root=ROOT):
    request=load(root/'request.json'); implementation=load(root/'implementation.json')
    for name,digest in implementation['files'].items():
        if sha((root/name).read_bytes())!=digest: raise Halt('Frozen implementation mismatch: '+name)
    if sha((REPO/'src/frontier/historical_lab.py').read_bytes())!=implementation['durable_writer_source_sha256']: raise Halt('Durable writer source changed')
    lock=sqlite3.connect(root/'capture.lock.sqlite',timeout=0); lock.execute('BEGIN EXCLUSIVE')
    try:
        cache=Cache(root,request)
        discoveries=[{'issuer':i,'discovery':{'complete':False,'status':'pending','original_accessions':[]}} for i in request['issuers']]
        registry={'request_sha256':sha((root/'request.json').read_bytes()),'issuers':discoveries,'complete':False}
        _save(root/'registry.json',registry)
        # Retain every requested issuer before acquisition; stopped discoveries keep their partial rows.
        for item in discoveries:
            try: item['discovery']=discover(cache,item['issuer'])
            except Halt:
                partial=root/'issuers'/item['issuer']['symbol']/'discovery.json'
                if partial.exists(): item['discovery']=load(partial)
                _save(root/'registry.json',registry); raise
            _save(root/'registry.json',registry)
        registry['complete']=all(x['discovery']['complete'] for x in discoveries)
        _save(root/'registry.json',registry)
        if not registry['complete']: raise Halt('Incomplete issuer discovery; registry preserved, no document acquisition')
        if sum(len(x['discovery']['original_accessions']) for x in discoveries)>request['max_original_accessions_total']: raise Halt('Total accession ceiling; registry preserved')
        results=[]
        for x in discoveries:
            for row in x['discovery']['original_accessions']:
                r=capture_filing(cache,x['issuer'],row); results.append(r)
                progress={'at':now(),'issuer':x['issuer']['symbol'],'accession':row['accessionNumber'],'status':r['status'],'completed':len(results),'counts':dict(Counter(y['status'] for y in results))}
                with (root/'progress.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(progress)+'\n')
                print(json.dumps(progress),flush=True)
        summary={'at':now(),'status':'captured' if all(r['status']=='captured' for r in results) else 'incomplete','original_accessions':len(results),'captured':sum(r['status']=='captured' for r in results),'failed':[{k:r.get(k) for k in ['issuer','registry_row','error']} for r in results if r['status']!='captured'],'clock_issues':[{'symbol':r['issuer']['symbol'],'accession':r['registry_row']['accessionNumber'],'clock':r.get('clock')} for r in results if not r.get('clock',{}).get('timestamp_sources_consistent')],'representations':dict(Counter(r.get('fact_representation','unresolved') for r in results)),'features_qualified':False,'network_attempts':len(cache.starts)}
        summary['issuer_coverage']=[{'issuer':x['issuer'],**{k:x['discovery'][k] for k in ['filed_year_counts','report_period_accessions','duplicate_report_periods','coverage_review_needed']}} for x in discoveries]
        if summary['status']=='captured' and any(x['coverage_review_needed'] for x in summary['issuer_coverage']): summary['status']='captured_with_coverage_review_needed'
        _save(root/'completion.json',summary)
    except Exception as exc:
        _save(root/'status.json',{'at':now(),'status':'stopped','error':type(exc).__name__+': '+str(exc)}); raise
    finally: lock.rollback(); lock.close()

if __name__=='__main__': run()
