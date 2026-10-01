"""Offline identity, missingness and fixed-cohort freeze checks."""
from pathlib import Path
from unittest.mock import patch
import copy,importlib.util,json,tempfile,unittest
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('source_finalizer_test',ROOT/'finalize_source.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def put(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(obj),encoding='utf-8')
def fixture(repo):
    root=repo/'profiles';root.mkdir()
    members=[{'symbol':'A','cik':'0000000001'},{'symbol':'B','cik':'0000000002'}]
    rows=[];wrapper={}
    for n,member in enumerate(members):
        cik=member['cik'];url='https://data.sec.gov/submissions/CIK'+cik+'.json'
        raw={'cik':int(cik),'tickers':[member['symbol']]}
        path=root/'raw'/(cik+'.json');put(path,raw)
        source={'url':url,'path':'raw/'+cik+'.json','sha256':m.digest(path),
                'bytes':path.stat().st_size,'status':200,'reused':False}
        row={'member':member,'url':url,'status':'captured','source':source}
        if n:
            row.update(status='unavailable',error='fixture HTTP503',source=None)
            failure=dict(source,status=503,error='HTTP503')
            f=root/'resources'/'failure.json';put(f,failure)
            row['resource_record']={'path':'resources/failure.json','sha256':m.digest(f)}
        rows.append(row);wrapper[cik]=raw if not n else None
        put(root/'profiles'/(cik+'.json'),row)
    request={'members':members,'pool_sha256':'frozenpool'};put(root/'request.json',request)
    manifest={'complete':True,'profiles':rows,'request_sha256':m.digest(root/'request.json'),'pool_sha256':'frozenpool'}
    put(root/'source-manifest.json',manifest);put(root/'profiles_by_CIK.json',wrapper)
    completion={'status':'complete','requested':2,'counts':{'captured':1,'unavailable':1},'history_requests':0,
        'pool_sha256':'frozenpool','request_sha256':m.digest(root/'request.json'),
        'source_manifest_sha256':m.digest(root/'source-manifest.json'),'profiles_by_CIK_sha256':m.digest(root/'profiles_by_CIK.json')}
    put(root/'completion.json',completion)
    return root,{'members':members}
class Tests(unittest.TestCase):
    def test_all_profiles_retained_with_raw_and_failure_bindings(self):
        with tempfile.TemporaryDirectory() as t:
            repo=Path(t);root,pool=fixture(repo)
            profiles,bindings,observed=m.verified_profiles(root,pool,repo)
            self.assertEqual(list(profiles),[r['cik'] for r in pool['members']])
            self.assertIsNone(profiles['0000000002'])
            self.assertEqual(len(bindings),2);self.assertEqual([r['status'] for r in observed],[200,503])
            self.assertIn('failed_source',bindings[1])
            (repo/observed[1]['path']).write_bytes(b'corrupted')
            with self.assertRaises(ValueError):m.verified_profiles(root,pool,repo)
    def test_stop_incomplete_order_and_denominator_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            repo=Path(t);root,pool=fixture(repo)
            with self.assertRaises(ValueError):m.verified_profiles(root,{'members':pool['members'][::-1]},repo)
            with self.assertRaises(ValueError):m.verified_profiles(root,{'members':pool['members'][:1]},repo)
            put(root/'STOP.json',{'status':429})
            with self.assertRaises(ValueError):m.verified_profiles(root,pool,repo)
    def test_wrapper_substitution_and_captured_source_corruption_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            repo=Path(t);root,pool=fixture(repo)
            wrapper=m.base.load(root/'profiles_by_CIK.json');wrapper['0000000001']['cik']=999
            put(root/'profiles_by_CIK.json',wrapper)
            completion=m.base.load(root/'completion.json')
            completion['profiles_by_CIK_sha256']=m.digest(root/'profiles_by_CIK.json');put(root/'completion.json',completion)
            with self.assertRaisesRegex(ValueError,'wrapper'):m.verified_profiles(root,pool,repo)
    def test_catalog_keeps_failures_reuses_identical_and_stops_vintage_conflict(self):
        with tempfile.TemporaryDirectory() as t:
            repo=Path(t);root,pool=fixture(repo)
            _,_,observed=m.verified_profiles(root,pool,repo)
            first=observed[0]
            old={'observations':[first], 'successful_urls':[first]}
            merged=m.merged_catalog(old,observed,repo)
            self.assertEqual(len(merged['observations']),3);self.assertEqual(len(merged['successful_urls']),1)
            self.assertEqual(old['observations'],[first])
            with self.assertRaisesRegex(ValueError,'vintages'):
                m.merged_catalog(old,[dict(first,sha256='0'*64)],repo)
    def test_qualifier_shortage_never_refills(self):
        pool={'members':[{'symbol':'A','cik':'0000000001'},{'symbol':'B','cik':'0000000002'}]}
        profile={'cik':1,'entityType':'operating','sic':'3571','stateOfIncorporation':'CA','tickers':['A']}
        result=m.cohort_code.qualify_pool(pool,{'0000000001':profile,'0000000002':None},{'target_issuers':100})
        self.assertEqual(result['status'],'insufficient_qualified_issuers')
        self.assertEqual(len(result['selected']),1);self.assertEqual(len(result['classification']),2)
        self.assertFalse(result['discovery_pool_refilled'])
    def test_request_preserves_exact100_and_replaces_stale_pilot_scope(self):
        draft=m.base.load(ROOT/'request-draft.json');before=copy.deepcopy(draft)
        selected=[{'symbol':'I'+str(i),'cik':str(i).zfill(10)} for i in range(1,101)]
        definition={'dated_classification_rule':'original same-CIK header only','model_spec_path':'model.json','inputs':{'model.json':'fixed'}}
        req=m.prepare_request(draft,{'selected':selected},{'successful_urls':[]},'source/cohort.json','cohortsha','catalogsha',definition)
        self.assertEqual(req['issuers'],selected);self.assertEqual(draft,before)
        self.assertNotIn('pending_freeze',req);self.assertNotIn('strategy_memo',req)
        self.assertEqual(req['model_specification']['sha256'],'fixed')
        with self.assertRaises(m.base.Halt):
            m.prepare_request(draft,{'selected':selected[:-1]},{'successful_urls':[]},'x','a','b',definition)
if __name__=='__main__':unittest.main()
