"""Bounded100-CIK original-filing capture; reuse reviewed transport and parsers."""
from pathlib import Path
from contextlib import contextmanager
from collections import Counter
from urllib.parse import urlparse
import importlib.util, json, re, sqlite3

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
SUPPLEMENT=REPO/'.qualification/filing-source-supplement20260928'
spec=importlib.util.spec_from_file_location('reviewed_filing_primary_selector',SUPPLEMENT/'capture_supplement.py')
supplement=importlib.util.module_from_spec(spec);spec.loader.exec_module(supplement)
base=supplement.base
BUDGETS={'max_issuer_roots':100,'max_history_pages_per_issuer':8,
         'max_original_accessions_per_issuer':60,'max_original_accessions_total':6000,
         'max_lifetime_network_attempts':24900,'max_attempts_per_url':2,
         'max_response_bytes':32*1024**2,'max_total_raw_bytes':40*1024**3,
         'minimum_request_interval_seconds':1}

def validate_request(request):
    issuers=request['issuers']
    if len(issuers)!=100 or len({i['cik'] for i in issuers})!=100:
        raise base.Halt('Exactly100 unique fixed CIKs required')
    if any(not re.fullmatch(r'\d{10}',i['cik']) or not i.get('symbol') for i in issuers):
        raise base.Halt('Invalid fixed issuer identity')
    if len({i['symbol'] for i in issuers})!=100:
        raise base.Halt('A distinct frozen common-share symbol is required for each issuer')
    if any(request.get(k)!=v for k,v in BUDGETS.items()):
        raise base.Halt('Declared source envelope differs from reviewed bounds')
    if request['filed_from']!='2012-01-01' or request['filed_through']!='2025-12-31':
        raise base.Halt('Original filing-date interval differs')
    if request['stop_http_status']!=[403,429] or request['original_form']!='10-Q':
        raise base.Halt('Source stop/form contract differs')

class ScopedCache(base.Cache):
    """Only frozen issuer roots, declared overlapping history, and registered originals."""
    def __init__(self,root,request,repo=REPO,opener=None):
        validate_request(request)
        super().__init__(root,request,repo=repo,opener=opener)
        self.ciks={i['cik'] for i in request['issuers']}
        self.filings={}
    def cached(self,url):
        record=self.root/'resources'/(base.sha(url.encode())+'.json')
        if record.exists():return self.read(base.load(record))
        if url in self.reuse:return self.read(dict(self.reuse[url],reused=True,status=200))
        raise base.Halt('Required registry/index is not cached: '+url)
    def register_filings(self,issuer,rows):
        if issuer not in self.request['issuers'] or len(rows)>60:
            raise base.Halt('Original accession registration outside fixed cohort/limit')
        for row in rows:
            acc=row['accessionNumber'];base.archive_base(issuer,acc)
            if row.get('form')!='10-Q' or not self.request['filed_from']<=row.get('filingDate','')<=self.request['filed_through']:
                raise base.Halt('Original accession outside declared form/filing dates')
            if acc in self.filings and self.filings[acc]!=(issuer,row):
                raise base.Halt('Conflicting registered accession')
            self.filings[acc]=(issuer,row)
        if len(self.filings)>6000:raise base.Halt('Total original accession limit exceeded')
    def authorize(self,url):
        if not base.allowed_url(url):raise base.Halt('URL outside official SEC scope')
        match=re.fullmatch(r'https://data\.sec\.gov/submissions/CIK(\d{10})(-submissions-\d+)?\.json',url)
        if match:
            cik,suffix=match.groups()
            if cik not in self.ciks:raise base.Halt('Unrequested issuer metadata')
            if suffix:
                raw,_=self.cached('https://data.sec.gov/submissions/CIK'+cik+'.json')
                body=json.loads(raw)
                if str(body.get('cik')).zfill(10)!=cik:raise base.Halt('Cached root CIK mismatch')
                allowed={'https://data.sec.gov/submissions/'+f['name'] for f in base.history_files(body,self.request)}
                if url not in allowed:raise base.Halt('History page not declared by overlapping original root')
            return
        for acc,index in self.request['index_url_overrides'].items():
            if url==index:
                if acc not in self.filings:raise base.Halt('Index alias outside registered originals')
                issuer,_=self.filings[acc];directory=base.archive_base(issuer,acc)
                legacy=f'https://www.sec.gov/Archives/edgar/data/{int(issuer["cik"])}/'
                if url not in {prefix+acc+'-index.'+ext for prefix in [directory,legacy] for ext in ['htm','html']}:
                    raise base.Halt('Index alias is not this issuer/original accession')
                return
        match=re.fullmatch(r'/Archives/edgar/data/(\d+)/(\d{18})/[^/]+',urlparse(url).path)
        if not match:raise base.Halt('Unsupported original accession path')
        cik,compact=match.groups();acc=compact[:10]+'-'+compact[10:12]+'-'+compact[12:]
        if acc not in self.filings:raise base.Halt('Accession not in frozen discovered registry')
        issuer,row=self.filings[acc]
        if int(cik)!=int(issuer['cik']):raise base.Halt('Archive CIK mismatch')
        directory=base.archive_base(issuer,acc)
        index=self.request['index_url_overrides'].get(acc,directory+acc+'-index.html')
        primary=base.document_url(directory,row['primaryDocument'])
        if url in {index,directory+acc+'.hdr.sgml',primary}:return
        raw,_=self.cached(index)
        parsed=supplement.select_registry_primary(raw,directory,acc,row['primaryDocument'])
        if parsed['original_instances']!=[url]:
            raise base.Halt('Only unique original EX-101.INS is authorized beyond primary/header/index')
    def get(self,url):
        self.authorize(url)
        return super().get(url)

@contextmanager
def source_locks(root=ROOT):
    locks=[]
    try:
        for path in [root.parent/'sec-source.lock.sqlite',root/'capture.lock.sqlite']:
            lock=sqlite3.connect(path,timeout=0);locks.append(lock)
            try:lock.execute('BEGIN EXCLUSIVE')
            except sqlite3.OperationalError as exc:raise base.Halt('Source worker already holds '+str(path)) from exc
        yield
    finally:
        for lock in reversed(locks):lock.rollback();lock.close()

def validate_cohort_members(request,cohort):
    declared=[(i['symbol'],i['cik']) for i in request['issuers']]
    selected=[(i['symbol'],i['cik']) for i in cohort['selected']]
    if declared!=selected or len(selected)!=100:
        raise base.Halt('Request issuer order/identity differs from frozen selected cohort')

def verify_frozen(root):
    request=base.load(root/'request.json');identity=base.load(root/'implementation.json')
    for name,digest in identity['files'].items():
        if base.sha((root/name).read_bytes())!=digest:raise base.Halt('Frozen source adapter changed: '+name)
    for name,digest in identity['external_files'].items():
        if base.sha((REPO/name).read_bytes())!=digest:raise base.Halt('Frozen dependency/cohort changed: '+name)
    validate_request(request)
    if base.sha((REPO/request['cohort_path']).read_bytes())!=request['cohort_sha256']:
        raise base.Halt('Frozen selected cohort identity changed')
    validate_cohort_members(request,base.load(REPO/request['cohort_path']))
    return request

def run(root=ROOT):
    request=verify_frozen(root)
    with source_locks(root):
        try:
            if (root/'STOP.json').exists():raise base.Halt('Prior SEC access/limit stop requires explicit reconciliation')
            cache=ScopedCache(root,request)
            base.parse_index=supplement.select_registry_primary
            registry={'request_sha256':base.sha((root/'request.json').read_bytes()),
                      'issuers':[{'issuer':i,'discovery':{'complete':False,'status':'pending','original_accessions':[]}} for i in request['issuers']],
                      'complete':False}
            base._save(root/'registry.json',registry)
            for entry in registry['issuers']:
                issuer=entry['issuer']
                try:entry['discovery']=base.discover(cache,issuer)
                except base.Halt:
                    partial=root/'issuers'/issuer['symbol']/'discovery.json'
                    if partial.exists():entry['discovery']=base.load(partial)
                    base._save(root/'registry.json',registry);raise
                base._save(root/'registry.json',registry)
            registry['complete']=all(e['discovery']['complete'] for e in registry['issuers'])
            base._save(root/'registry.json',registry)
            # A non-access discovery failure stays visible; it does not erase other fixed issuers.
            for entry in registry['issuers']:
                if entry['discovery']['complete']:
                    cache.register_filings(entry['issuer'],entry['discovery']['original_accessions'])
            results=[]
            for entry in registry['issuers']:
                if not entry['discovery']['complete']:continue
                for row in entry['discovery']['original_accessions']:
                    result=base.capture_filing(cache,entry['issuer'],row);results.append(result)
                    progress={'at':base.now(),'issuer':entry['issuer']['symbol'],'accession':row['accessionNumber'],
                              'status':result['status'],'completed':len(results),'registered_originals':len(cache.filings)}
                    with (root/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(progress)+'\n')
                    print(json.dumps(progress),flush=True)
            verify_frozen(root)
            summary={'at':base.now(),'status':'captured' if registry['complete'] and len(results)==len(cache.filings) and all(r['status']=='captured' for r in results) else 'incomplete',
                     'declared_issuers':100,'registered_originals':len(cache.filings),'processed_originals':len(results),
                     'counts':dict(Counter(r['status'] for r in results)),
                     'incomplete_discoveries':[e for e in registry['issuers'] if not e['discovery']['complete']],
                     'failed_filings':[{k:r.get(k) for k in ['issuer','registry_row','error']} for r in results if r['status']!='captured'],
                     'coverage_review_needed':[{'issuer':e['issuer'],'items':e['discovery'].get('coverage_review_needed',[])} for e in registry['issuers'] if e['discovery'].get('coverage_review_needed')],
                     'clock_issues':[{'issuer':r['issuer'],'accession':r['registry_row']['accessionNumber'],'clock':r.get('clock')} for r in results if not r.get('clock',{}).get('timestamp_sources_consistent')],
                     'network_attempts':len(cache.starts),'features_qualified':False,'returns_computed':False}
            if summary['status']=='captured' and summary['coverage_review_needed']:summary['status']='captured_with_coverage_review_needed'
            base._save(root/'completion.json',summary)
        except Exception as exc:
            base._save(root/'status.json',{'at':base.now(),'status':'stopped','error':type(exc).__name__+': '+str(exc)});raise

if __name__=='__main__':run()
