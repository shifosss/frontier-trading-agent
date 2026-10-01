"""Offline tests only: no SEC or broker access."""
from pathlib import Path
from unittest.mock import patch
import importlib.util,json,tempfile,unittest,sqlite3
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('profile_capture',ROOT/'capture_profiles.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def request(n=2):
    members=[{'symbol':f'I{i}','cik':str(i).zfill(10)} for i in range(1,n+1)]
    return dict(m.LIMITS,members=members,root_urls=[m.root_url(x['cik']) for x in members],reuse=[],stop_http_status=[403,429],user_agent='offline fixture',pool_sha256='fixture')
class Response:
    def __init__(self,url,status,raw):self.url=url;self.status=status;self.raw=raw;self.headers={}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.raw[:n]
class Opener:
    def __init__(self,status=200,raw=None):self.status=status;self.raw=raw;self.calls=[]
    def open(self,req,timeout):
        self.calls.append(req.full_url);cik=req.full_url.rsplit('CIK',1)[-1].split('.')[0]
        return Response(req.full_url,self.status,self.raw if self.raw is not None else json.dumps({'cik':int(cik),'entityType':'operating'}).encode())
class Tests(unittest.TestCase):
    def test_exact_pool_and_bounds(self):
        q=request();m.validate_request(q,{'members':q['members']})
        for pool in [{'members':list(reversed(q['members']))},{'members':q['members']+[{'symbol':'EXTRA','cik':'0000000999'}]}]:
            with self.assertRaises(m.base.Halt):m.validate_request(q,pool)
        for change in [{'max_attempts_per_url':2},{'root_urls':[q['root_urls'][0]]},{'members':[q['members'][0]]*301}]:
            with self.assertRaises(m.base.Halt):m.validate_request(q|change,{'members':(q|change)['members']})
    def test_reuse_without_get_and_no_history_or_other_CIK(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t);q=request();raw=b'{"cik":1}';(root/'fixture.bin').write_bytes(raw)
            q['reuse']=[{'url':q['root_urls'][0],'path':'fixture.bin','sha256':m.base.sha(raw),'bytes':len(raw)}]
            opener=Opener();cache=m.ProfileCache(root,q,repo=root,opener=opener)
            result,body=m.capture_profile(cache,q['members'][0]);self.assertEqual(body['cik'],1);self.assertEqual(result['status'],'captured')
            m.capture_profile(cache,q['members'][0]);self.assertEqual(opener.calls,[])
            for url in [q['root_urls'][0].replace('.json','-submissions-001.json'),m.root_url('0000000999'),'https://www.sec.gov/files/company_tickers.json']:
                with self.assertRaises(m.base.Halt):cache.get(url)
            self.assertEqual(opener.calls,[])
    def test_completed_failure_and_wrong_CIK_remain_without_retry(self):
        for status,raw in [(503,b'HTTP503'),(200,b'{"cik":9}')]:
            with tempfile.TemporaryDirectory() as t,patch.object(m.base.time,'sleep'):
                q=request();opener=Opener(status,raw);cache=m.ProfileCache(Path(t),q,opener=opener)
                first,body=m.capture_profile(cache,q['members'][0]);second,_=m.capture_profile(cache,q['members'][0])
                self.assertIsNone(body);self.assertEqual(first,second);self.assertEqual(first['status'],'unavailable');self.assertEqual(len(opener.calls),1)
                meta=m.base.load(Path(t)/first['resource_record']['path'])
                (Path(t)/meta['path']).write_bytes(b'corrupted retained failure')
                with self.assertRaises(m.base.Halt):m.capture_profile(cache,q['members'][0])
                self.assertEqual(len(opener.calls),1)
    def test_access_and_response_limit_halt_and_interrupted_never_retry(self):
        for status,raw in [(403,b'denied'),(429,b'rate'),(200,b'x'*(8*1024**2+1))]:
            with tempfile.TemporaryDirectory() as t,patch.object(m.base.time,'sleep'):
                q=request();opener=Opener(status,raw);cache=m.ProfileCache(Path(t),q,opener=opener)
                with self.assertRaises(m.base.Halt):m.capture_profile(cache,q['members'][0])
                self.assertTrue((Path(t)/'STOP.json').exists());self.assertEqual(len(opener.calls),1)
        with tempfile.TemporaryDirectory() as t:
            q=request();opener=Opener();cache=m.ProfileCache(Path(t),q,opener=opener);cache.starts=[{'url':q['root_urls'][0]}]
            with self.assertRaises(m.base.Halt):cache.get(q['root_urls'][0])
            cache.starts=[{'url':'other'}]*300
            with self.assertRaises(m.base.Halt):cache.get(q['root_urls'][0])
            self.assertEqual(opener.calls,[])
    def test_full_wrapper_preserves_every_pool_member(self):
        with tempfile.TemporaryDirectory() as t,patch.object(m.base.time,'sleep'):
            root=Path(t)/'earnings/discovery/profiles';root.mkdir(parents=True);q=request()
            (root/'request.json').write_text(json.dumps(q));opener=Opener();cls=m.ProfileCache
            with patch.object(m,'verify_frozen',return_value=q),patch.object(m,'ProfileCache',side_effect=lambda r,q:cls(r,q,opener=opener)):
                m.run(root)
            output=m.base.load(root/'profiles_by_CIK.json');self.assertEqual(list(output),[x['cik'] for x in q['members']]);self.assertEqual(len(opener.calls),2)
            self.assertEqual(m.base.load(root/'completion.json')['history_requests'],0)
            (root/'STOP.json').write_text('{}')
            with patch.object(m,'verify_frozen',return_value=q):
                with self.assertRaises(m.base.Halt):m.run(root)
    def test_shared_lock_exclusion(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'earnings/discovery/profiles';root.mkdir(parents=True)
            shared=root.parents[1]/'sec-source.lock.sqlite';held=sqlite3.connect(shared,timeout=0);held.execute('BEGIN EXCLUSIVE')
            with self.assertRaises(m.base.Halt):
                with m.locks(root):self.fail('Concurrent SEC access allowed')
            held.rollback();held.close()
            with m.locks(root):
                other=sqlite3.connect(root/'capture.lock.sqlite',timeout=0)
                with self.assertRaises(sqlite3.OperationalError):other.execute('BEGIN EXCLUSIVE')
                other.close()
if __name__=='__main__':unittest.main()
