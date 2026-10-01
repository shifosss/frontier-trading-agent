"""Offline economic-source boundaries and durable resume cases; no public requests."""
import copy, importlib.util, json, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError
from io import BytesIO
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('filing_capture',P/'capture.py'); c=importlib.util.module_from_spec(spec); spec.loader.exec_module(c)
BASE=json.loads((P/'request.json').read_text())

class Response(BytesIO):
    def __init__(self,raw,status=200,url='https://data.sec.gov/submissions/CIK0000320193.json'):
        super().__init__(raw); self.status=status; self.url=url; self.headers={}
class Opener:
    def __init__(self,responses): self.responses=list(responses); self.calls=[]
    def open(self,request,timeout):
        self.calls.append(request.full_url); response=self.responses.pop(0)
        if isinstance(response,Exception): raise response
        return response
class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.root=Path(self.tmp.name); self.request=copy.deepcopy(BASE); self.request['reuse']=[]; self.request['minimum_request_interval_seconds']=0
    def tearDown(self): self.tmp.cleanup()
    def cache(self,responses=()):
        opener=Opener(responses); return c.Cache(self.root,self.request,repo=self.root,opener=opener),opener
    def test_real_three_indexes_and_original_clock(self):
        evidence=P.parent/'filing-feasibility20260928'; rows=json.loads((evidence/'raw/aapl_submissions.bin').read_bytes())['filings']['recent']; n=rows['accessionNumber'].index('0000320193-20-000062'); row={k:v[n] for k,v in rows.items()}
        cases=[('aapl_2020q3','0000320193','0000320193-20-000062','aapl-20200627.htm'),('msft_2024q3','0000789019','0000950170-24-048288','msft-20240331.htm'),('f_2024q2','0000037996','0000037996-24-000144','f-20240630.htm')]
        for name,cik,acc,primary in cases:
            index=c.parse_index((evidence/'raw'/(name+'_index.bin')).read_bytes(),c.archive_base({'cik':cik},acc),acc,primary); self.assertTrue(index['primary'].endswith(primary)); self.assertEqual(index['original_instances'],[])
            if name=='aapl_2020q3':
                clock=c.clock_check(row,index,(evidence/'raw/aapl_2020q3_header.bin').read_text(),{'cik':cik}); self.assertTrue(clock['timestamp_sources_consistent']); self.assertFalse(clock['public_dissemination_instant_verified'])
                changed=dict(row,acceptanceDateTime='2020-07-30T19:29:09'); self.assertIn('API acceptance missing/invalid timezone',c.clock_check(changed,index,(evidence/'raw/aapl_2020q3_header.bin').read_text(),{'cik':cik})['issues'])
    def test_inline_link_alias_and_old_instance(self):
        base=c.archive_base({'cik':'0000320193'},'0000320193-12-000001'); path=base.split('www.sec.gov')[1]+'main.htm'
        for prefix in ['/ix?doc=','/ixviewer/doc/action?doc=']:
            raw=f'SEC Accession No. 0000320193-12-000001 Filing Date 2012-04-20 Accepted 2012-04-20 16:00:00<table><tr><td>1</td><td>Report</td><td><a href="{prefix}{path}">main.htm</a></td><td>10-Q</td></tr><tr><td>2</td><td>XBRL INSTANCE</td><td><a href="facts.xml">facts.xml</a></td><td>EX-101.INS</td></tr></table>'.encode()
            index=c.parse_index(raw,base,'0000320193-12-000001','main.htm'); self.assertEqual(index['original_instances'],[base+'facts.xml'])
        with self.assertRaises(c.CaptureError): c.document_url(base,'https://example.com/other.htm')
        with self.assertRaises(c.CaptureError): c.document_url(base,'../other.htm')
    def test_ambiguous_primary_and_instance_not_silently_selected(self):
        base=c.archive_base({'cik':'0000320193'},'0000320193-12-000001'); header='SEC Accession No. 0000320193-12-000001 Filing Date 2012-04-20 Accepted 2012-04-20 16:00:00'
        row='<tr><td>1</td><td>Report</td><td><a href="main.htm">main</a></td><td>10-Q</td></tr>'
        with self.assertRaises(c.CaptureError): c.parse_index((header+'<table>'+row+row+'</table>').encode(),base,'0000320193-12-000001','main.htm')
        raw=(header+'<table>'+row+'<tr><td>2</td><td>XBRL</td><td><a href="one.xml">one</a></td><td>EX-101.INS</td></tr><tr><td>3</td><td>XBRL</td><td><a href="two.xml">two</a></td><td>EX-101.INS</td></tr></table>').encode()
        self.assertEqual(len(c.parse_index(raw,base,'0000320193-12-000001','main.htm')['original_instances']),2)
    def test_history_overlap_and_missing_ranges(self):
        def f(start,end,n=1): return dict(name=f'CIK0000320193-submissions-{n:03}.json',filingFrom=start,filingTo=end)
        body={'filings':{'files':[f('2000-01-01','2011-12-31'),f('2011-01-01','2012-01-01',2),f('2025-12-31','2026-12-31',3)]}}
        self.assertEqual(len(c.history_files(body,self.request)),2)
        body['filings']['files'].append(f('unknown','2024-01-01',4))
        with self.assertRaises(c.CaptureError): c.history_files(body,self.request)
        body['filings']['files']=[f('2010-01-01','2013-01-01',i) for i in range(9)]
        with self.assertRaises(c.Halt): c.history_files(body,self.request)
    def test_cache_resume_and_exact_reuse(self):
        url='https://data.sec.gov/submissions/CIK0000320193.json'; cache,opener=self.cache([Response(b'{}')]); first=cache.get(url); self.assertEqual(cache.get(url),first); self.assertEqual(len(opener.calls),1)
        resumed,other=self.cache(); self.assertEqual(resumed.get(url),first); self.assertEqual(other.calls,[])
        (self.root/'raw'/ (c.sha(b'{}')+'.bin')).write_bytes(b'bad')
        with self.assertRaises(c.Halt): resumed.get(url)
    def test_external_exact_source_reuse(self):
        url='https://data.sec.gov/submissions/CIK0000320193.json'; (self.root/'old.bin').write_bytes(b'{}'); self.request['reuse']=[dict(url=url,path='old.bin',bytes=2,sha256=c.sha(b'{}'))]
        cache,opener=self.cache(); self.assertEqual(cache.get(url)[0],b'{}'); self.assertEqual(opener.calls,[])
    def test_transport_failure_survives_resume_without_retry(self):
        url='https://data.sec.gov/submissions/CIK0000320193.json'; cache,opener=self.cache([URLError('offline')])
        with self.assertRaises(c.CaptureError): cache.get(url)
        resumed,other=self.cache()
        with self.assertRaises(c.CaptureError): resumed.get(url)
        self.assertEqual(other.calls,[]); self.assertIn('URLError',(self.root/'resources'/(c.sha(url.encode())+'.json')).read_text())
    def test_access_stop_and_byte_ceiling(self):
        url='https://data.sec.gov/submissions/CIK0000320193.json'; cache,opener=self.cache([Response(b'denied',429)])
        with self.assertRaises(c.Halt): cache.get(url)
        self.assertTrue((self.root/'STOP.json').exists())
        with self.assertRaises(c.Halt): cache.get('https://data.sec.gov/submissions/CIK0000789019.json')
        self.assertEqual(len(opener.calls),1)
    def test_oversize_raw_preserved_not_complete(self):
        url='https://data.sec.gov/submissions/CIK0000320193.json'; self.request['max_response_bytes']=3; cache,opener=self.cache([Response(b'12345')])
        with self.assertRaises(c.Halt): cache.get(url)
        self.assertEqual(sum(x.stat().st_size for x in (self.root/'raw').glob('*.bin')),4)
        self.assertIn('truncated',(self.root/'STOP.json').read_text())
    def test_interrupted_request_bounded_resume(self):
        url='https://data.sec.gov/submissions/CIK0000320193.json'; cache,opener=self.cache(); cache.append(dict(event='request_started',url=url,attempt=1))
        resumed,opener=self.cache([Response(b'{}')]); resumed.get(url); self.assertEqual(len(opener.calls),1); self.assertEqual(len(resumed.starts),2)
    def test_membership_and_partial_discovery_retained(self):
        issuer={'symbol':'AAPL','cik':'0000320193'}
        rows={'accessionNumber':['0000320193-11-000001','0000320193-12-000001','0000320193-25-000001','0000320193-26-000001'],'form':['10-Q','10-Q','10-Q','10-Q/A'],'filingDate':['2011-12-31','2012-01-01','2025-12-31','2026-01-01']}
        body={'cik':'0000320193','name':'Apple','tickers':['AAPL'],'filings':{'recent':rows,'files':[]}}
        cache,opener=self.cache([Response(json.dumps(body).encode())]); result=c.discover(cache,issuer)
        self.assertTrue(result['complete']); self.assertEqual(len(result['original_accessions']),2); self.assertEqual(len(result['amendment_metadata']),1)
        with self.assertRaises(c.CaptureError): c.table_rows({'accessionNumber':['x']})
        # A failed required history resource keeps already discovered originals and marks discovery incomplete.
        body['filings']['files']=[dict(name='CIK0000320193-submissions-001.json',filingFrom='2000-01-01',filingTo='2015-01-01')]
        class Fake:
            root=self.root; request=self.request
            def get(self,url):
                if '-submissions-'in url: raise c.CaptureError('fixture history missing')
                return json.dumps(body).encode(),{'url':url}
        partial=c.discover(Fake(),issuer); self.assertFalse(partial['complete']); self.assertEqual(len(partial['original_accessions']),2); self.assertEqual(len(partial['rows']),4)

    def test_filing_resume_checks_bytes_and_registry_identity(self):
        issuer={'symbol':'AAPL','cik':'0000320193'}; row={'accessionNumber':'0000320193-12-000001'}; source=self.root/'old.bin'; source.write_bytes(b'original')
        cache,opener=self.cache(); meta={'url':'https://data.sec.gov/submissions/CIK0000320193.json','path':'old.bin','sha256':c.sha(b'original'),'bytes':8,'status':200,'reused':True}
        destination=self.root/'filings/AAPL'; destination.mkdir(parents=True); saved={'issuer':issuer,'registry_row':row,'status':'captured','sources':[meta]}; c._save(destination/(row['accessionNumber']+'.json'),saved)
        self.assertEqual(c.capture_filing(cache,issuer,row),saved); self.assertEqual(opener.calls,[])
        with self.assertRaises(c.Halt): c.capture_filing(cache,issuer,dict(row,filingDate='2012-01-01'))
        source.write_bytes(b'changed!')
        with self.assertRaises(c.Halt): c.capture_filing(cache,issuer,row)
    def test_zero_accessions_and_full_year_coverage_visible(self):
        issuer={'symbol':'AAPL','cik':'0000320193'}; body={'cik':'0000320193','tickers':['AAPL'],'filings':{'recent':{'accessionNumber':[],'form':[],'filingDate':[]},'files':[]}}
        cache,opener=self.cache([Response(json.dumps(body).encode())]); result=c.discover(cache,issuer)
        self.assertFalse(result['complete']); self.assertIn('Zero original',result['error']); self.assertEqual(len(result['filed_year_counts']),14); self.assertEqual(len(result['coverage_review_needed']),14)
    def test_old_original_instance_capture_and_ambiguity(self):
        issuer={'symbol':'AAPL','cik':'0000320193'}; acc='0000320193-12-000001'; base=c.archive_base(issuer,acc)
        row={'accessionNumber':acc,'primaryDocument':'main.htm','filingDate':'2012-04-20','acceptanceDateTime':'2012-04-20T20:00:00Z','isInlineXBRL':0}
        index=f'SEC Accession No. {acc} Filing Date 2012-04-20 Accepted 2012-04-20 16:00:00<table><tr><td>1</td><td>10Q</td><td><a href="main.htm">main</a></td><td>10-Q</td></tr><tr><td>2</td><td>Facts</td><td><a href="facts.xml">facts</a></td><td>EX-101.INS</td></tr></table>'.encode()
        header=f'<ACCESSION-NUMBER>{acc}\n<TYPE>10-Q\n<CIK>0000320193\n<FILING-DATE>20120420\n<ACCEPTANCE-DATETIME>20120420160000\n'.replace('\\n','\n').encode()
        payloads={base+acc+'-index.html':index,base+acc+'.hdr.sgml':header,base+'main.htm':b'<html>Original report</html>',base+'facts.xml':b'<xbrl xmlns="http://www.xbrl.org/2003/instance"></xbrl>'}
        for i,(url,raw) in enumerate(payloads.items()):
            file=self.root/f'fixture{i}.bin'; file.write_bytes(raw); self.request['reuse'].append(dict(url=url,path=file.name,sha256=c.sha(raw),bytes=len(raw)))
        cache,opener=self.cache(); result=c.capture_filing(cache,issuer,row)
        self.assertEqual(result['status'],'captured'); self.assertEqual(result['fact_representation'],'original_xbrl_instance'); self.assertEqual(len(result['fact_sources']),1); self.assertEqual(result['fact_sources'][0]['url'],base+'facts.xml'); self.assertEqual(opener.calls,[])

if __name__=='__main__': unittest.main()
