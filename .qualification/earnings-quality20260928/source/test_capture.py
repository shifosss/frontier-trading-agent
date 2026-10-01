"""Offline checks for100-issuer scope, reused transport, and persistent failure semantics."""
from pathlib import Path
from unittest.mock import patch
import importlib.util,json,tempfile,unittest,sqlite3
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('broad_source',ROOT/'capture.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def request():
    return dict(m.BUDGETS,issuers=[{'symbol':f'I{i}','cik':str(i).zfill(10)} for i in range(1,101)],
        filed_from='2012-01-01',filed_through='2025-12-31',original_form='10-Q',
        stop_http_status=[403,429],reuse=[],index_url_overrides={},timeout_seconds=1,user_agent='offline fixture')
class Response:
    def __init__(self,url,status=200,body=b'{}'):self.url=url;self.status=status;self.body=body;self.headers={}
    def __enter__(self):return self
    def __exit__(self,*args):pass
    def read(self,n):return self.body[:n]
class Opener:
    def __init__(self,status=200,body=b'{}'):self.status=status;self.body=body;self.calls=[]
    def open(self,req,timeout):self.calls.append(req.full_url);return Response(req.full_url,self.status,self.body)
def row(acc='0000000001-13-000001'):
    return {'accessionNumber':acc,'form':'10-Q','filingDate':'2013-05-01','primaryDocument':'main.htm'}
def cached(cache,url,raw):
    name='raw/'+m.base.sha(raw)+'.bin';(cache.root/name).write_bytes(raw)
    m.base._save(cache.root/'resources'/(m.base.sha(url.encode())+'.json'),{'url':url,'status':200,'path':name,'sha256':m.base.sha(raw),'bytes':len(raw)})
class Tests(unittest.TestCase):
    def test_exact_selected_cohort_identity_and_order(self):
        q=request();cohort={'selected':[dict(i) for i in q['issuers']]}
        m.validate_cohort_members(q,cohort)
        cohort['selected'][0]={'symbol':'OTHER','cik':'0000000999'}
        with self.assertRaises(m.base.Halt):m.validate_cohort_members(q,cohort)
        with self.assertRaises(m.base.Halt):m.validate_cohort_members(q,{'selected':list(reversed(q['issuers']))})
    def test_100_root_identity_and_bounds(self):
        q=request();m.validate_request(q)
        for change in [{'issuers':q['issuers'][:-1]},{'issuers':q['issuers']+[q['issuers'][0]]},{'max_lifetime_network_attempts':24901},{'max_attempts_per_url':3}]:
            with self.assertRaises(m.base.Halt):m.validate_request(q|change)
        with tempfile.TemporaryDirectory() as t:
            opener=Opener();cache=m.ScopedCache(Path(t),q,opener=opener)
            with self.assertRaises(m.base.Halt):cache.get('https://data.sec.gov/submissions/CIK0000000101.json')
            self.assertEqual(opener.calls,[])
    def test_existing_root_reused_without_get_and_history_scope(self):
        with tempfile.TemporaryDirectory() as t:
            p=Path(t);(p/'run').mkdir();q=request()
            url='https://data.sec.gov/submissions/CIK0000000001.json'
            history='CIK0000000001-submissions-001.json'
            raw=json.dumps({'cik':1,'filings':{'files':[{'name':history,'filingFrom':'2011-01-01','filingTo':'2015-12-31'},{'name':'CIK0000000001-submissions-002.json','filingFrom':'2000-01-01','filingTo':'2011-12-31'}]}}).encode()
            (p/'cached-root.bin').write_bytes(raw);q['reuse']=[{'url':url,'path':'cached-root.bin','sha256':m.base.sha(raw),'bytes':len(raw)}]
            opener=Opener();cache=m.ScopedCache(p/'run',q,repo=p,opener=opener)
            self.assertEqual(cache.get(url)[0],raw);self.assertEqual(opener.calls,[])
            cache.authorize('https://data.sec.gov/submissions/'+history)
            for other in ['CIK0000000001-submissions-002.json','CIK0000000001-submissions-999.json','CIK0000000002-submissions-001.json']:
                with self.assertRaises(m.base.Halt):cache.get('https://data.sec.gov/submissions/'+other)
            self.assertEqual(opener.calls,[])
    def test_history_ceiling_and_missing_metadata_remain_failures(self):
        with tempfile.TemporaryDirectory() as t:
            cache=m.ScopedCache(Path(t),request());url='https://data.sec.gov/submissions/CIK0000000001.json'
            files=[{'name':f'CIK0000000001-submissions-{i:03}.json','filingFrom':'2012-01-01','filingTo':'2025-12-31'} for i in range(9)]
            cached(cache,url,json.dumps({'cik':1,'filings':{'files':files}}).encode())
            with self.assertRaises(m.base.Halt):cache.authorize('https://data.sec.gov/submissions/CIK0000000001-submissions-000.json')
            files[0].pop('filingFrom');cached(cache,url,json.dumps({'cik':1,'filings':{'files':files[:1]}}).encode())
            with self.assertRaises(m.base.CaptureError):cache.authorize('https://data.sec.gov/submissions/CIK0000000001-submissions-000.json')
    def test_registered_exact_primary_instance_and_legacy_index_only(self):
        with tempfile.TemporaryDirectory() as t:
            q=request();opener=Opener();cache=m.ScopedCache(Path(t),q,opener=opener)
            issuer=q['issuers'][0];r=row();acc=r['accessionNumber'];directory=m.base.archive_base(issuer,acc)
            with self.assertRaises(m.base.Halt):cache.authorize(directory+acc+'-index.html')
            cache.register_filings(issuer,[r]);index=directory+acc+'-index.html'
            cache.authorize(index);cache.authorize(directory+acc+'.hdr.sgml');cache.authorize(directory+'main.htm')
            raw=(f'SEC Accession No. {acc} Filing Date 2013-05-01 Accepted 2013-05-01 09:00:00'
                 '<table><tr><td>1</td><td>Report</td><td><a href="main.htm">main</a></td><td>10-Q</td></tr>'
                 '<tr><td>2</td><td>Printable</td><td><a href="print.pdf">pdf</a></td><td>10-Q</td></tr>'
                 '<tr><td>3</td><td>Facts</td><td><a href="facts.xml">xml</a></td><td>EX-101.INS</td></tr></table>').encode()
            cached(cache,index,raw);cache.authorize(directory+'facts.xml')
            for bad in [directory+'print.pdf',directory+'later.xml',directory+'facts.xsd','https://example.com/facts.xml']:
                with self.assertRaises(m.base.Halt):cache.get(bad)
            alias='https://www.sec.gov/Archives/edgar/data/1/'+acc+'-index.htm'
            q['index_url_overrides'][acc]=alias;cache.authorize(alias)
            self.assertEqual(opener.calls,[])
    def test_registered_original_limit_and_wrong_form(self):
        with tempfile.TemporaryDirectory() as t:
            cache=m.ScopedCache(Path(t),request());issuer=cache.request['issuers'][0]
            with self.assertRaises(m.base.Halt):cache.register_filings(issuer,[row()]*61)
            with self.assertRaises(m.base.Halt):cache.register_filings(issuer,[row()|{'form':'10-Q/A'}])
            with self.assertRaises(m.base.Halt):cache.register_filings(issuer,[row()|{'filingDate':'2026-01-01'}])
    def test_completed_failure_no_retry_and_403_429_stop(self):
        url='https://data.sec.gov/submissions/CIK0000000001.json'
        for status in [503,403,429]:
            with tempfile.TemporaryDirectory() as t,patch.object(m.base.time,'sleep'):
                opener=Opener(status);cache=m.ScopedCache(Path(t),request(),opener=opener)
                with self.assertRaises(m.base.CaptureError):cache.get(url)
                with self.assertRaises(m.base.CaptureError):cache.get(url)
                self.assertEqual(len(opener.calls),1);self.assertEqual((Path(t)/'STOP.json').exists(),status in [403,429])
    def test_interrupted_only_one_resume_attempt_with_lifetime_bound(self):
        url='https://data.sec.gov/submissions/CIK0000000001.json'
        with tempfile.TemporaryDirectory() as t,patch.object(m.base.time,'sleep'):
            opener=Opener();cache=m.ScopedCache(Path(t),request(),opener=opener)
            cache.starts=[{'event':'request_started','url':url,'attempt':1}]
            cache.get(url);cache.get(url)
            self.assertEqual(len(opener.calls),1);self.assertEqual(cache.starts[-1]['attempt'],2)
        with tempfile.TemporaryDirectory() as t:
            opener=Opener();cache=m.ScopedCache(Path(t),request(),opener=opener)
            cache.starts=[{'url':url},{'url':url}]
            with self.assertRaises(m.base.Halt):cache.get(url)
            cache.starts=[{'url':'other'}]*24900
            with self.assertRaises(m.base.Halt):cache.get(url)
            self.assertEqual(opener.calls,[])
    def test_shared_and_capture_lock_exclusion(self):
        with tempfile.TemporaryDirectory() as t:
            root=Path(t)/'source';root.mkdir()
            held=sqlite3.connect(root.parent/'sec-source.lock.sqlite',timeout=0);held.execute('BEGIN EXCLUSIVE')
            with self.assertRaises(m.base.Halt):
                with m.source_locks(root):self.fail('Concurrent SEC worker admitted')
            held.rollback();held.close()
            with m.source_locks(root):
                other=sqlite3.connect(root/'capture.lock.sqlite',timeout=0)
                with self.assertRaises(sqlite3.OperationalError):other.execute('BEGIN EXCLUSIVE')
                other.close()
if __name__=='__main__':unittest.main()
