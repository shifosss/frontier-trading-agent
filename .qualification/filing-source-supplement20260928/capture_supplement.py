"""Bounded31-accession source supplement; baseline failures stay unchanged."""
from pathlib import Path
from collections import Counter
from contextlib import contextmanager
import importlib.util, json, re, sqlite3
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parent.parent
ORIGINAL=REPO/'.qualification/filing-source20260928'
spec=importlib.util.spec_from_file_location('original_filing_capture_for_supplement',ORIGINAL/'capture.py')
base=importlib.util.module_from_spec(spec); spec.loader.exec_module(base)

def select_registry_primary(raw,directory,accession,primary):
    parser=base.Index(); parser.feed(raw.decode('utf-8')); text=' '.join(' '.join(parser.text).split())
    def field(pattern):
        found=re.search(pattern,text)
        if not found: raise base.CaptureError('Missing index field: '+pattern)
        return found[1]
    if field(r'SEC Accession No\.\s+([0-9-]+)')!=accession: raise base.CaptureError('Index accession mismatch')
    docs=[]
    for row in parser.rows:
        if len(row)>=4 and row[2]['links']:
            docs.append({'description':row[1]['text'],'type':row[3]['text'],'url':base.document_url(directory,row[2]['links'][0])})
    expected=base.document_url(directory,primary)
    matches=[d for d in docs if d['type']=='10-Q' and d['url']==expected]
    if len(matches)!=1: raise base.CaptureError('Original registry primary does not match exactly one10-Q row')
    return {'accepted_local':field(r'Accepted\s+(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})'),'filing_date':field(r'Filing Date\s+(\d{4}-\d{2}-\d{2})'),'primary':expected,'original_instances':[d['url'] for d in docs if d['type']=='EX-101.INS'],'documents':docs,'other_10q_documents':[d for d in docs if d['type']=='10-Q' and d['url']!=expected]}

class DeclaredCache(base.Cache):
    def get(self,url):
        allowed=set(self.request['planned_new_resource_urls'])|set(self.reuse)
        if url not in allowed and not self.conditional_original_instance(url):
            raise base.Halt('URL not in frozen supplement request: '+url)
        return super().get(url)

    def conditional_original_instance(self,url):
        for item in self.request['items']:
            if item['recovery_class']!='one_time_transient_index_retry': continue
            row=item['registry_row']; acc=row['accessionNumber']
            directory=base.archive_base(item['issuer'],acc)
            if not url.startswith(directory): continue
            record=self.root/'resources'/(base.sha(item['retry_index_url'].encode())+'.json')
            if not record.exists(): return False
            raw,meta=self.read(base.load(record))
            index=select_registry_primary(raw,directory,acc,row['primaryDocument'])
            if index['original_instances']!=[url]: return False
            base._save(self.root/'continuations'/(acc+'.json'),{
                'accession':acc,'index_url':meta['url'],'index_sha256':meta['sha256'],
                'original_instance_url':url,'rule':'Exactly one original EX-101.INS from this recovered original index'})
            return True
        return False

def validate_originals(request):
    if base.sha((ORIGINAL/'capture.py').read_bytes())!=request['original_capture_code_sha256']: raise base.Halt('Original frozen capture source changed')
    if base.sha((ORIGINAL/'implementation.json').read_bytes())!=request['original_capture_implementation_sha256']: raise base.Halt('Original capture implementation identity changed')
    for item in request['items']:
        path=REPO/item['original_manifest_path']
        if base.sha(path.read_bytes())!=item['original_manifest_sha256']: raise base.Halt('Original failure manifest changed: '+str(path))
    for source in request['reuse']:
        if base.sha((REPO/source['path']).read_bytes())!=source['sha256']: raise base.Halt('Original index source changed')
    if base.sha((REPO/request['original_completion_path']).read_bytes())!=request['original_completion_sha256']:
        raise base.Halt('Original completion identity changed')
    for item in request['items']:
        source=item.get('original_failed_source')
        if not source: continue
        if base.sha((REPO/source['resource_record_path']).read_bytes())!=source['resource_record_sha256']:
            raise base.Halt('Original failed resource metadata changed')
        if 'raw_path' in source and base.sha((REPO/source['raw_path']).read_bytes())!=source['raw_sha256']:
            raise base.Halt('Original HTTP failure payload changed')

@contextmanager
def source_locks(original=ORIGINAL,root=ROOT):
    connections=[]
    try:
        if not (original/'capture.lock.sqlite').exists(): raise base.Halt('Baseline source lock is missing')
        for directory in [original,root]:
            lock=sqlite3.connect(directory/'capture.lock.sqlite',timeout=0); connections.append(lock)
            try: lock.execute('BEGIN EXCLUSIVE')
            except sqlite3.OperationalError as exc: raise base.Halt('Another source worker holds '+str(directory/'capture.lock.sqlite')) from exc
        yield
    finally:
        for lock in reversed(connections): lock.rollback(); lock.close()

def run():
    request=base.load(ROOT/'request.json'); implementation=base.load(ROOT/'implementation.json')
    for name,digest in implementation['files'].items():
        if base.sha((ROOT/name).read_bytes())!=digest: raise base.Halt('Frozen supplement changed: '+name)
    if base.sha((REPO/'src/frontier/historical_lab.py').read_bytes())!=implementation['durable_writer_source_sha256']: raise base.Halt('Durable writer source changed')
    validate_originals(request)
    if not (ORIGINAL/'completion.json').exists(): raise base.Halt('Baseline capture has not completed; root must wait for its lock release')
    with source_locks():
      try:
        cache=DeclaredCache(ROOT,request)
        # Runtime amendment only in this isolated module/process; no frozen source file is edited.
        base.parse_index=select_registry_primary
        results=[]
        for item in request['items']:
            result=base.capture_filing(cache,item['issuer'],item['registry_row'])
            result['supplement_of']={k:item[k] for k in ['original_manifest_path','original_manifest_sha256','original_error','recovery_class']}
            base._save(ROOT/'filings'/item['issuer']['symbol']/(item['registry_row']['accessionNumber']+'.json'),result)
            results.append(result)
            progress={'at':base.now(),'accession':item['registry_row']['accessionNumber'],'status':result['status'],'completed':len(results)}
            with (ROOT/'progress.jsonl').open('a',encoding='utf-8') as f: f.write(json.dumps(progress)+'\n')
            print(json.dumps(progress),flush=True)
        validate_originals(request)
        summary={'at':base.now(),'status':'captured' if len(results)==len(request['items']) and all(r['status']=='captured' for r in results) else 'incomplete','declared_original_accessions':len(request['items']),'scope_counts':request['scope_counts'],'results':[{k:r.get(k) for k in ['issuer','registry_row','status','error','fact_representation','clock','supplement_of']} for r in results],'counts':dict(Counter(r['status'] for r in results)),'by_recovery_class':{kind:dict(Counter(r['status'] for r in results if r['supplement_of']['recovery_class']==kind)) for kind in ['duplicate_primary','one_time_transient_index_retry']},'network_attempts':len(cache.starts),'original_failures_unchanged':True,'features_qualified':False}
        base._save(ROOT/'completion.json',summary)
      except Exception as exc:
        base._save(ROOT/'status.json',{'at':base.now(),'status':'stopped','error':type(exc).__name__+': '+str(exc)}); raise

if __name__=='__main__': run()
