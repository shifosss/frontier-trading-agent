"""Offline supplement checks against all26actual indexes and originalHTML spans."""
from pathlib import Path
from unittest.mock import patch
import importlib.util, json, unittest, re, tempfile, sqlite3
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('filing_supplement',ROOT/'capture_supplement.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
request=m.base.load(ROOT/'request.json')

class Tests(unittest.TestCase):
    def test_all_twenty_six_exact_primary_rows_and_retained_pdfs(self):
        self.assertEqual(len(request['items']),31); self.assertEqual(len(set(request['planned_new_resource_urls'])),93)
        self.assertEqual(sum(i['recovery_class']=='duplicate_primary' for i in request['items']),26)
        reused={r['sha256']:r for r in request['reuse']}
        for item in request['items']:
            if item['recovery_class']!='duplicate_primary': continue
            row=item['registry_row']; base=m.base.archive_base(item['issuer'],row['accessionNumber']); source=reused[item['index_source_sha256']]; raw=(m.REPO/source['path']).read_bytes()
            self.assertEqual(m.base.sha(raw),source['sha256']); parsed=m.select_registry_primary(raw,base,row['accessionNumber'],row['primaryDocument'])
            self.assertEqual(parsed['primary'],item['selected_primary']['url']); self.assertEqual(parsed['original_instances'],[item['original_instance']['url']]); self.assertEqual(len(parsed['other_10q_documents']),1); self.assertTrue(parsed['other_10q_documents'][0]['url'].endswith('.pdf'))
            self.assertEqual(item['new_resource_urls'],[base+row['accessionNumber']+'.hdr.sgml',parsed['primary'],parsed['original_instances'][0]])
    def test_duplicate_or_absent_exact_primary_remains_failure(self):
        acc='0000037996-12-000023'; base=m.base.archive_base({'cik':'0000037996'},acc); heading=f'SEC Accession No. {acc} Filing Date 2012-05-04 Accepted 2012-05-04 11:53:31'
        row='<tr><td>1</td><td>report</td><td><a href="main.htm">main.htm</a></td><td>10-Q</td></tr>'
        with self.assertRaises(m.base.CaptureError): m.select_registry_primary((heading+'<table>'+row+row+'</table>').encode(),base,acc,'main.htm')
        with self.assertRaises(m.base.CaptureError): m.select_registry_primary((heading+'<table>'+row+'</table>').encode(),base,acc,'other.htm')
    def test_frozen_scope_cannot_add_later_or_unrelated_get(self):
        cache=object.__new__(m.DeclaredCache); cache.request=request; cache.root=ROOT; cache.reuse={x['url']:x for x in request['reuse']}
        with patch.object(m.base.Cache,'get',return_value=('fixture','metadata')) as underlying:
            self.assertEqual(cache.get(request['planned_new_resource_urls'][0]),('fixture','metadata'))
            with self.assertRaises(m.base.Halt): cache.get('https://data.sec.gov/submissions/CIK0000037996.json')
            with self.assertRaises(m.base.Halt): cache.get(request['planned_new_resource_urls'][0]+'?later=1')
            self.assertEqual(underlying.call_count,1)
    def test_original_failure_and_source_hashes_unchanged(self):
        m.validate_originals(request)
        for item in request['items']:
            original=m.base.load(m.REPO/item['original_manifest_path']); self.assertEqual(original['status'],'incomplete'); self.assertEqual(original['error'],item['original_error'])
    def test_msft_original_table_spans_and_columns(self):
        a=m.base.load(ROOT/'msft-original-html-assessment.json'); raw=(m.REPO/a['raw_source_root']/a['raw_source']['path']).read_bytes(); self.assertEqual(m.base.sha(raw),a['raw_source']['sha256'])
        self.assertTrue(a['clock']['timestamp_sources_consistent']); self.assertFalse(a['clock']['public_dissemination_instant_verified']); self.assertEqual(a['registry_row']['isXBRL'],0)
        tables={t['kind']:t for t in a['tables']}
        for t in tables.values():
            start,end=t['byte_span_zero_based_half_open']; fragment=(ROOT/t['fragment_file']).read_bytes(); self.assertEqual(raw[start:end],fragment); self.assertEqual(m.base.sha(fragment),t['fragment_sha256'])
        income=next(r for r in tables['income_statement']['rows'] if r and r[0]=='Net income'); values=[x for x in income if re.fullmatch(r'\d[\d,]*',x)]; self.assertEqual(values,['6,624','6,634','12,362','12,044'])
        assets=next(r for r in tables['balance_sheet']['rows'] if r and r[0]=='Total assets'); self.assertEqual([x for x in assets if re.fullmatch(r'\d[\d,]*',x)],['112,243','108,704'])
        self.assertIn('Three Months',str(tables['income_statement']['rows'])); self.assertIn('Six Months',str(tables['income_statement']['rows'])); self.assertIn('June 30',str(tables['balance_sheet']['rows']))

    def test_baseline_and_supplement_source_locks_exclusive(self):
        with tempfile.TemporaryDirectory() as tmp:
            original=Path(tmp)/'original'; original.mkdir(); supplement=Path(tmp)/'supplement'; supplement.mkdir()
            held=sqlite3.connect(original/'capture.lock.sqlite',timeout=0); held.execute('BEGIN EXCLUSIVE')
            with self.assertRaises(m.base.Halt):
                with m.source_locks(original,supplement): self.fail('Concurrent baseline worker was admitted')
            held.rollback(); held.close()
            with m.source_locks(original,supplement):
                for directory in [original,supplement]:
                    other=sqlite3.connect(directory/'capture.lock.sqlite',timeout=0)
                    with self.assertRaises(sqlite3.OperationalError): other.execute('BEGIN EXCLUSIVE')
                    other.close()
            for directory in [original,supplement]:
                other=sqlite3.connect(directory/'capture.lock.sqlite',timeout=0); other.execute('BEGIN EXCLUSIVE'); other.rollback(); other.close()


    def test_six_att_mappings_and_five_exact_index_failures(self):
        extra=[i for i in request['items'] if i['recovery_class']=='duplicate_primary' and i['issuer']['symbol']=='T']
        self.assertEqual(len(extra),6)
        retries=[i for i in request['items'] if i['recovery_class']=='one_time_transient_index_retry']
        self.assertEqual(len(retries),5)
        self.assertEqual(sorted(i['issuer']['symbol'] for i in retries),['BANF','BANF','BANF','HRL','T'])
        self.assertEqual(sorted(str(i['original_failed_source']['status']) for i in retries),['503','503','503','503','None'])
        self.assertEqual(request['max_attempts_per_url'],1); self.assertEqual(request['max_lifetime_network_attempts'],98)
        for item in retries:
            failure=item['original_failed_source']; manifest=m.base.load(m.REPO/item['original_manifest_path'])
            self.assertEqual(manifest['sources'],[]); self.assertEqual(failure['url'],item['retry_index_url'])
            self.assertNotIn(failure['status'],request['stop_http_status'])
            self.assertEqual(len(item['new_resource_urls']),3)
        saved=m.base.load(ROOT/'preflight-v1/request.json')
        for item in saved['items']:
            current=next(i for i in request['items'] if i['registry_row']==item['registry_row'])
            self.assertEqual({k:current[k] for k in item},item)

    def test_conditional_instance_requires_saved_exact_unique_index(self):
        item=next(i for i in request['items'] if i['recovery_class']=='one_time_transient_index_retry')
        row=item['registry_row']; acc=row['accessionNumber']; directory=m.base.archive_base(item['issuer'],acc)
        heading=f'SEC Accession No. {acc} Filing Date 2017-05-04 Accepted 2017-05-04 11:53:31'
        primary=f'<tr><td>1</td><td>report</td><td><a href="{row["primaryDocument"]}">report</a></td><td>10-Q</td></tr>'
        instance='<tr><td>2</td><td>instance</td><td><a href="original.xml">instance</a></td><td>EX-101.INS</td></tr>'
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); cache=m.DeclaredCache(root,request)
            url=directory+'original.xml'
            self.assertFalse(cache.conditional_original_instance(url))
            record=root/'resources'/(m.base.sha(item['retry_index_url'].encode())+'.json')
            for suffix,expected in [(instance,True),(instance+instance,False),('',False)]:
                raw=(heading+'<table>'+primary+suffix+'</table>').encode()
                payload=root/'raw'/'fixture.bin'; payload.write_bytes(raw)
                m.base._save(record,{'url':item['retry_index_url'],'status':200,'path':'raw/fixture.bin','bytes':len(raw),'sha256':m.base.sha(raw)})
                self.assertEqual(cache.conditional_original_instance(url),expected)
            self.assertFalse(cache.conditional_original_instance(directory+'later.xml'))
            self.assertFalse(cache.conditional_original_instance('https://www.sec.gov/Archives/edgar/data/1/other/original.xml'))

    def test_completed_failure_is_not_retried_and_403_stops(self):
        import copy
        from urllib.error import HTTPError
        class Response:
            def __init__(self,url,status): self.url=url; self.status=status; self.headers={}
            def __enter__(self): return self
            def __exit__(self,*args): pass
            def read(self,n): return b'failure'
        class Opener:
            def __init__(self,status): self.status=status; self.count=0
            def open(self,req,timeout): self.count+=1; return Response(req.full_url,self.status)
        url=next(i['retry_index_url'] for i in request['items'] if i['recovery_class']=='one_time_transient_index_retry')
        q=copy.deepcopy(request); q['minimum_request_interval_seconds']=0
        for status in [503,403,429]:
            with tempfile.TemporaryDirectory() as tmp:
                opener=Opener(status); cache=m.DeclaredCache(Path(tmp),q,opener=opener)
                with self.assertRaises(m.base.CaptureError): cache.get(url)
                with self.assertRaises(m.base.CaptureError): cache.get(url)
                self.assertEqual(opener.count,1)
                self.assertEqual((Path(tmp)/'STOP.json').exists(),status in [403,429])
        with tempfile.TemporaryDirectory() as tmp:
            opener=Opener(200); cache=m.DeclaredCache(Path(tmp),q,opener=opener)
            cache.starts=[{'event':'request_started','url':url,'attempt':1}]
            with self.assertRaises(m.base.Halt): cache.get(url)
            self.assertEqual(opener.count,0)

if __name__=='__main__': unittest.main()

