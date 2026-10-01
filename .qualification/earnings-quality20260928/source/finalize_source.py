"""Freeze the fixed cohort and source capture offline; never sends an HTTP request."""
from pathlib import Path
from collections import Counter
import copy, hashlib, importlib.util, json, sys, zipfile

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]
STUDY=ROOT.parent
PROFILES=STUDY/'discovery/profiles'
COHORT=STUDY/'cohort'

def module(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result)
    return result

capture=module('broad_capture_for_freeze',ROOT/'capture.py')
cohort_code=module('frozen_cohort_for_freeze',COHORT/'cohort.py')
base=capture.base
def digest(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def relative(path,repo=REPO):return path.resolve().relative_to(repo.resolve()).as_posix()
def check(path,expected):
    if digest(path)!=expected:raise ValueError('Source identity changed: '+str(path))
def save_new(path,value):
    with path.open('x',encoding='utf-8') as f:json.dump(value,f,indent=2,allow_nan=False)

def source_record(meta,origin,repo=REPO):
    """Resolve capture-local versus reused repository-relative bytes without copying."""
    result={k:meta.get(k) for k in ('url','status','error','sha256','bytes','requested_at_utc','retrieved_at_utc','reused')}
    if meta.get('path'):
        path=(repo if meta.get('reused') else origin)/meta['path']
        check(path,meta['sha256'])
        if path.stat().st_size!=meta['bytes']:raise ValueError('Source byte size differs')
        result['path']=relative(path,repo)
    return result

def verified_profiles(root,pool,repo=REPO):
    completion=base.load(root/'completion.json')
    request=base.load(root/'request.json')
    if (root/'STOP.json').exists() or completion['status']!='complete':
        raise ValueError('Profile capture is stopped/incomplete')
    if completion['pool_sha256']!=request['pool_sha256'] or completion['request_sha256']!=digest(root/'request.json'):
        raise ValueError('Profile completion request/pool identity differs')
    check(root/'source-manifest.json',completion['source_manifest_sha256'])
    check(root/'profiles_by_CIK.json',completion['profiles_by_CIK_sha256'])
    manifest=base.load(root/'source-manifest.json');wrapper=base.load(root/'profiles_by_CIK.json')
    expected=[{k:m[k] for k in ('symbol','cik')} for m in pool['members']]
    if (not manifest['complete'] or [r['member'] for r in manifest['profiles']]!=expected
        or request['members']!=expected or set(wrapper)!={m['cik'] for m in expected}
        or completion['requested']!=len(expected) or completion['history_requests']!=0
        or manifest['request_sha256']!=completion['request_sha256']
        or manifest['pool_sha256']!=completion['pool_sha256']):
        raise ValueError('Profile denominator/order/identity differs')
    profiles={};observations=[];bindings=[]
    for row in manifest['profiles']:
        cik=row['member']['cik'];record=root/'profiles'/(cik+'.json')
        if base.load(record)!=row:raise ValueError('Saved profile row differs from manifest')
        binding={'cik':cik,'symbol':row['member']['symbol'],'status':row['status'],
                 'profile_record':relative(record,repo),'profile_record_sha256':digest(record),
                 'url':row['url'],'error':row.get('error')}
        expected_url='https://data.sec.gov/submissions/CIK'+cik+'.json'
        if row['url']!=expected_url:raise ValueError('Profile root URL differs')
        observed=None
        if row.get('source'):
            if row['source']['url']!=expected_url:raise ValueError('Source URL differs')
            observed=source_record(row['source'],root,repo)
        failed=row.get('resource_record')
        if failed:
            path=root/failed['path'];check(path,failed['sha256'])
            failure=base.load(path)
            if failure['url']!=expected_url:raise ValueError('Failed source URL differs')
            retained=source_record(failure,root,repo)
            retained.update(resource_record=relative(path,repo),resource_record_sha256=digest(path))
            observations.append(retained)
            binding['failed_source']=retained
        if row['status']=='captured':
            if not observed or observed['status']!=200 or observed['error']:
                raise ValueError('Captured profile lacks successful source')
            body=base.load(repo/observed['path'])
            if str(body.get('cik','')).zfill(10)!=cik or body!=wrapper[cik]:
                raise ValueError('Profile wrapper differs from original matching-CIK source')
            profiles[cik]=body
        elif row['status']=='unavailable':
            if wrapper[cik] is not None:raise ValueError('Unavailable profile has substituted metadata')
            if not row.get('error'):raise ValueError('Unavailable profile lacks retained error')
            profiles[cik]=None
        else:raise ValueError('Pending/unknown profile status')
        if observed:
            observations.append(observed);binding['source']=observed
        bindings.append(binding)
    if dict(Counter(r['status'] for r in manifest['profiles']))!=completion['counts']:
        raise ValueError('Profile terminal counts differ')
    return profiles,bindings,observations

def merged_catalog(old,observations,repo=REPO):
    successful={r['url']:r for r in old['successful_urls']}
    for row in old['successful_urls']:
        check(repo/row['path'],row['sha256'])
        if (repo/row['path']).stat().st_size!=row['bytes']:raise ValueError('Prior source size differs')
    for row in observations:
        if row.get('status')!=200 or row.get('error') or not row.get('path'):continue
        prior=successful.get(row['url'])
        if prior and prior['sha256']!=row['sha256']:
            raise ValueError('Conflicting successful same-URL source vintages: '+row['url'])
        successful.setdefault(row['url'],row)
    return {'schema':2,'observations':old['observations']+observations,
            'successful_urls':list(successful.values()),'conflicting_successful_URLs':[],
            'policy':'Keep all original and new observations/errors. Exact successful URL/hash reuse only; conflicts stop without choosing a vintage.',
            'network_requests_by_catalog_builder':0}

def prepare_request(draft,cohort,catalog,cohort_path,cohort_sha,catalog_sha,definition):
    request=copy.deepcopy(draft)
    request.update(declared_at_utc=base.now(),stage='Frozen source-only original-filing capture',
        issuers=[{k:m[k] for k in ('symbol','cik')} for m in cohort['selected']],
        cohort_path=cohort_path,cohort_sha256=cohort_sha,reuse_catalog_sha256=catalog_sha,
        reuse=[{k:r[k] for k in ('url','path','sha256','bytes','retrieved_at_utc') if k in r} for r in catalog['successful_urls']],
        classification=definition['dated_classification_rule'],
        qualification_limits=['100 current-member surviving issuers; not historical universe membership.',
          'Original historical archives retrieved now; revisions and source gaps remain visible.',
          'Current US incorporation is not a historical domicile claim.',
          'Dated same-CIK header SIC is a separate event gate, never a replacement-cohort rule.',
          'Fact/context, public clock and security/action continuity require separate qualification.'])
    request.pop('pending_freeze',None);request.pop('strategy_memo',None)
    request['model_specification']={'path':definition['model_spec_path'],
        'sha256':definition['inputs'][definition['model_spec_path']]}
    capture.validate_request(request);capture.validate_cohort_members(request,cohort)
    return request

def run(definition_path):
    definition_path=Path(definition_path).resolve()
    definition=base.load(definition_path);definition_sha=digest(definition_path)
    for name,expected in definition['inputs'].items():check(REPO/name,expected)
    if definition['model_spec_path'] not in definition['inputs']:
        raise ValueError('Frozen model specification missing')
    required={relative(ROOT/n) for n in ('finalize_source.py','test_finalize_source.py','capture.py',
        'test_capture.py','request-draft.json','reusable-source-catalog.json')}
    required|={relative(COHORT/n) for n in ('cohort.py','criteria.json','definition.json','pool-completion.json')}
    required|={relative(PROFILES/n) for n in ('implementation.json','request.json','capture_profiles.py')}
    if required-definition['inputs'].keys():raise ValueError('Finalizer definition omits required inputs')
    with capture.source_locks(ROOT):
        completed=ROOT/'finalization-completion.json'
        if completed.exists():
            result=base.load(completed)
            if result['definition_sha256']!=definition_sha:raise ValueError('Existing finalization identity differs')
            for name,expected in result['outputs'].items():check(ROOT/name,expected)
            print(json.dumps(result));return result
        profile_code=module('frozen_profile_read_validation',PROFILES/'capture_profiles.py')
        profile_request=profile_code.verify_frozen(PROFILES,REPO)
        pool_path=REPO/profile_request['pool_path'];check(pool_path,profile_request['pool_sha256'])
        pool=base.load(pool_path)
        profiles,bindings,observations=verified_profiles(PROFILES,pool)
        rules=base.load(COHORT/'criteria.json')
        result=cohort_code.qualify_pool(pool,profiles,rules)
        result.update(at=base.now(),pool_path=relative(pool_path),pool_sha256=digest(pool_path),
            current_profile_sources=bindings,profile_completion_path=relative(PROFILES/'completion.json'),
            profile_completion_sha256=digest(PROFILES/'completion.json'),
            finalization_definition_sha256=definition_sha,
            dated_classification_rule=definition['dated_classification_rule'],
            forbidden_inputs_used=[],network_requests=0)
        outputs={}
        save_new(ROOT/'cohort.json',result);outputs['cohort.json']=digest(ROOT/'cohort.json')
        if result['status']!='ready_for_cohort_freeze':
            summary={'status':result['status'],'definition_sha256':definition_sha,'outputs':outputs,
                     'selected_count':len(result['selected']),'qualified_count':result['qualified_count'],
                     'no_capture_request_written':True}
            save_new(completed,summary);print(json.dumps(summary));return summary
        old=base.load(ROOT/'reusable-source-catalog.json')
        catalog=merged_catalog(old,observations)
        catalog['prior_catalog_sha256']=digest(ROOT/'reusable-source-catalog.json')
        catalog['profile_completion_sha256']=result['profile_completion_sha256']
        save_new(ROOT/'reusable-source-catalog-v2.json',catalog)
        outputs['reusable-source-catalog-v2.json']=digest(ROOT/'reusable-source-catalog-v2.json')
        request=prepare_request(base.load(ROOT/'request-draft.json'),result,catalog,
             relative(ROOT/'cohort.json'),outputs['cohort.json'],
             outputs['reusable-source-catalog-v2.json'],definition)
        save_new(ROOT/'request.json',request);outputs['request.json']=digest(ROOT/'request.json')
        local_names=['capture.py','test_capture.py','finalize_source.py','test_finalize_source.py',
                     'source-plan.md','finalization-definition.json',*outputs]
        external=dict(definition['inputs'])
        for name in ['completion.json','source-manifest.json','profiles_by_CIK.json']:
            external[relative(PROFILES/name)]=digest(PROFILES/name)
        # The request freezes expected raw hashes; Cache.read rechecks bytes upon reuse.
        identity={'schema':1,'at':base.now(),'files':{n:digest(ROOT/n) for n in local_names},
          'external_files':external,'finalization_definition_sha256':definition_sha,
          'selected_issuers':100,'profile_denominator':len(bindings),'reuse_urls':len(catalog['successful_urls']),
          'source_only':True,'acquisition_started':False}
        save_new(ROOT/'implementation.json',identity);outputs['implementation.json']=digest(ROOT/'implementation.json')
        members={relative(ROOT/n):ROOT/n for n in [*identity['files'],'implementation.json']}
        members.update({name:REPO/name for name in external})
        with zipfile.ZipFile(ROOT/'frozen-source.zip','x',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,path in sorted(members.items()):archive.write(path,name)
        with zipfile.ZipFile(ROOT/'frozen-source.zip') as archive:
            for name,path in members.items():
                if base.sha(archive.read(name))!=digest(path):raise ValueError('Archive member differs')
        outputs['frozen-source.zip']=digest(ROOT/'frozen-source.zip')
        for name,expected in definition['inputs'].items():check(REPO/name,expected)
        capture.verify_frozen(ROOT)
        summary={'status':'ready_for_root_launch','at':base.now(),'definition_sha256':definition_sha,
                 'outputs':outputs,'selected_count':100,'qualified_count':result['qualified_count'],
                 'profile_denominator':len(bindings),'archive_members':len(members),
                 'reuse_urls':len(catalog['successful_urls']),'network_requests':0}
        save_new(completed,summary);print(json.dumps(summary));return summary

if __name__=='__main__':run(sys.argv[1] if len(sys.argv)>1 else ROOT/'finalization-definition.json')
