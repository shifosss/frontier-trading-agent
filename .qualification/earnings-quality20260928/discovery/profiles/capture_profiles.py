"""One bounded current SEC submissions profile per frozen discovery-pool CIK."""
from pathlib import Path
from contextlib import contextmanager
from collections import Counter
import importlib.util,json,re,sqlite3
ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[3]
ORIGINAL=REPO/'.qualification/filing-source20260928'
spec=importlib.util.spec_from_file_location('frozen_sec_profile_transport',ORIGINAL/'capture.py')
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
LIMITS={'max_lifetime_network_attempts':300,'max_attempts_per_url':1,
        'max_response_bytes':8*1024**2,'max_total_raw_bytes':2*1024**3,
        'minimum_request_interval_seconds':1,'timeout_seconds':30}
def root_url(cik):return 'https://data.sec.gov/submissions/CIK'+cik+'.json'
def validate_request(request,pool):
    members=request['members']
    expected=[(m['symbol'],m['cik']) for m in pool['members']]
    actual=[(m['symbol'],m['cik']) for m in members]
    if actual!=expected or not 1<=len(actual)<=300 or len({x[1] for x in actual})!=len(actual):
        raise base.Halt('Profile request differs from exact ordered frozen pool')
    if any(not re.fullmatch(r'\d{10}',cik) or not symbol for symbol,cik in actual):
        raise base.Halt('Invalid fixed profile identity')
    if any(request.get(k)!=v for k,v in LIMITS.items()) or request['stop_http_status']!=[403,429]:
        raise base.Halt('Profile source bounds changed')
    if request['root_urls']!=[root_url(cik) for _,cik in actual]:
        raise base.Halt('Profile URLs differ from fixed pool')
class ProfileCache(base.Cache):
    def get(self,url):
        if url not in self.request['root_urls']:
            raise base.Halt('Only the fixed current submissions roots are authorized')
        return super().get(url)
def validate_body(raw,cik):
    body=json.loads(raw)
    if not isinstance(body,dict) or str(body.get('cik','')).zfill(10)!=cik:
        raise base.CaptureError('Current submissions response CIK missing/mismatched')
    return body
def capture_profile(cache,member):
    cik=member['cik'];path=cache.root/'profiles'/(cik+'.json')
    if path.exists():
        saved=base.load(path)
        if saved['member']!=member:raise base.Halt('Saved profile member identity changed')
        if saved['status']=='captured':
            raw,_=cache.read(saved['source']);return saved,validate_body(raw,cik)
        # Preserve and revalidate a completed failure; never replace it by another GET.
        if saved.get('source'):cache.read(saved['source'])
        record=saved.get('resource_record')
        if record:
            path=cache.root/record['path']
            if base.sha(path.read_bytes())!=record['sha256']:raise base.Halt('Saved failed source metadata changed')
            meta=base.load(path)
            if meta.get('path'):
                try:cache.read(meta)
                except base.Halt:raise
                except base.CaptureError:pass
        return saved,None
    result={'member':member,'url':root_url(cik),'status':'unavailable','source':None}
    try:
        raw,meta=cache.get(result['url']);result['source']=meta
        body=validate_body(raw,cik)
        result['status']='captured';result['classification_qualified']=False
        base._save(path,result);return result,body
    except (base.CaptureError,ValueError,TypeError) as exc:
        result['error']=type(exc).__name__+': '+str(exc)
        record=cache.root/'resources'/(base.sha(result['url'].encode())+'.json')
        if record.exists():result['resource_record']={'path':record.relative_to(cache.root).as_posix(),'sha256':base.sha(record.read_bytes())}
        base._save(path,result)
        if isinstance(exc,base.Halt):raise
        return result,None
@contextmanager
def locks(root=ROOT):
    held=[]
    try:
        for path in [root.parents[1]/'sec-source.lock.sqlite',root/'capture.lock.sqlite']:
            lock=sqlite3.connect(path,timeout=0);held.append(lock)
            try:lock.execute('BEGIN EXCLUSIVE')
            except sqlite3.OperationalError as exc:raise base.Halt('SEC/profile worker already active') from exc
        yield
    finally:
        for lock in reversed(held):lock.rollback();lock.close()
def verify_frozen(root=ROOT,repo=REPO):
    request=base.load(root/'request.json');identity=base.load(root/'implementation.json')
    for name,digest in identity['files'].items():
        if base.sha((root/name).read_bytes())!=digest:raise base.Halt('Frozen profile file changed: '+name)
    for name,digest in identity['external_files'].items():
        if base.sha((repo/name).read_bytes())!=digest:raise base.Halt('Frozen profile dependency/pool changed: '+name)
    path=repo/request['pool_path']
    if base.sha(path.read_bytes())!=request['pool_sha256']:raise base.Halt('Frozen pool identity changed')
    validate_request(request,base.load(path))
    return request
def run(root=ROOT):
    request=verify_frozen(root)
    with locks(root):
        try:
            if (root/'STOP.json').exists():raise base.Halt('Prior SEC access/limit stop requires explicit reconciliation')
            cache=ProfileCache(root,request)
            results=[{'member':m,'url':root_url(m['cik']),'status':'pending','source':None} for m in request['members']]
            profiles={m['cik']:None for m in request['members']}
            manifest={'request_sha256':base.sha((root/'request.json').read_bytes()),'pool_sha256':request['pool_sha256'],'profiles':results,'complete':False}
            base._save(root/'source-manifest.json',manifest)
            for i,member in enumerate(request['members']):
                try:
                    results[i],profiles[member['cik']]=capture_profile(cache,member)
                except base.Halt:
                    path=root/'profiles'/(member['cik']+'.json')
                    if path.exists():results[i]=base.load(path)
                    base._save(root/'source-manifest.json',manifest);raise
                base._save(root/'source-manifest.json',manifest)
                progress={'at':base.now(),'cik':member['cik'],'symbol':member['symbol'],'status':results[i]['status'],'processed':i+1,'requested':len(results)}
                with (root/'progress.jsonl').open('a',encoding='utf-8') as f:f.write(json.dumps(progress)+'\n')
                print(json.dumps(progress),flush=True)
            verify_frozen(root)
            manifest['complete']=True;base._save(root/'source-manifest.json',manifest)
            base._save(root/'profiles_by_CIK.json',profiles)
            completion={'at':base.now(),'status':'complete','requested':len(results),'counts':dict(Counter(r['status'] for r in results)),
                        'pool_sha256':request['pool_sha256'],'request_sha256':manifest['request_sha256'],
                        'source_manifest_sha256':base.sha((root/'source-manifest.json').read_bytes()),
                        'profiles_by_CIK_sha256':base.sha((root/'profiles_by_CIK.json').read_bytes()),
                        'network_attempts':len(cache.starts),'classification_qualified':False,'history_requests':0}
            base._save(root/'completion.json',completion)
        except Exception as exc:
            base._save(root/'status.json',{'at':base.now(),'status':'stopped','error':type(exc).__name__+': '+str(exc)});raise
if __name__=='__main__':run()
