"""Offline supplement checks against all20actual indexes and originalHTML spans."""
from pathlib import Path
from unittest.mock import patch
import importlib.util, json, unittest, re, tempfile, sqlite3
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('filing_supplement',ROOT/'capture_supplement.py'); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
request=m.base.load(ROOT/'request.json')

class Tests(unittest.TestCase):
    def test_all_twenty_exact_primary_rows_and_retained_pdfs(self):
        self.assertEqual(len(request['items']),20); self.assertEqual(len(set(request['planned_new_resource_urls'])),60)
        reused={r['sha256']:r for r in request['reuse']}
        for item in request['items']:
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
        cache=object.__new__(m.DeclaredCache); cache.request=request; cache.reuse={x['url']:x for x in request['reuse']}
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

if __name__=='__main__': unittest.main()
