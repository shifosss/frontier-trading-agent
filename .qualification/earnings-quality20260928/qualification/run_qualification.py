"""Offline terminal-only100-issuer qualification; no source writes or network."""
from collections import Counter
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
import argparse,hashlib,importlib.util,json,sqlite3,uuid
from frontier.historical_lab import _save

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[2]

def module(path,name):
    spec=importlib.util.spec_from_file_location(name,path);result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result

ADAPTER=module(ROOT/'header_industry.py','original_industry_qualification')

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):
    with Path(path).open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()

def verify_inputs(identities):
    for name,expected in identities.items():
        path=Path(name);actual=sha(path) if path.is_file() else None
        if actual!=expected:raise ValueError('Source input changed: '+name)

def verify_source(source_root):
    return module(Path(source_root)/'capture.py','verified_frozen_original_capture').verify_frozen(source_root)

@contextmanager
def source_read_guard(source_root):
    path=(Path(source_root)/'capture.lock.sqlite').resolve()
    if not path.is_file():raise ValueError('Source worker lock is missing')
    connection=sqlite3.connect(path.as_uri()+'?mode=ro',uri=True,timeout=0)
    try:
        connection.execute('BEGIN')
        connection.execute('SELECT count(*) FROM sqlite_master').fetchone()
        yield
    finally:connection.rollback();connection.close()


def collect_records(source_root,repo_root):
    source_root,repo_root=Path(source_root).resolve(),Path(repo_root).resolve()
    identities={}
    def remember(path,missing=False,expected=None):
        path=Path(path).resolve();name=str(path)
        if not path.is_file() and not missing:raise ValueError('Required source missing: '+name)
        actual=sha(path) if path.is_file() else None
        if expected is not None and actual!=expected:raise ValueError('Raw source identity changed: '+name)
        if name in identities and identities[name]!=actual:raise ValueError('Source changed during collection: '+name)
        identities.setdefault(name,actual);return actual
    with source_read_guard(source_root):
        if (source_root/'STOP.json').exists():raise ValueError('Unresolved source STOP requires reconciliation')
        if not (source_root/'completion.json').is_file():raise ValueError('Source has no terminal completion')
        request=verify_source(source_root)
        for name in ['request.json','registry.json','completion.json']:remember(source_root/name)
        registry=read(source_root/'registry.json');completion=read(source_root/'completion.json')
        if completion.get('status') not in ['captured','captured_with_coverage_review_needed','incomplete']:
            raise ValueError('Source status is not terminal')
        expected=[(x['symbol'],x['cik']) for x in request['issuers']]
        actual=[(x['issuer']['symbol'],x['issuer']['cik']) for x in registry['issuers']]
        if len(expected)!=100 or len(set(expected))!=100 or len({x[1] for x in expected})!=100 or actual!=expected:
            raise ValueError('Exact ordered100-member registry/request mismatch')
        if registry.get('request_sha256')!=sha(source_root/'request.json'):
            raise ValueError('Registry request identity mismatch')
        originals={};issuers=[];registered=0
        for item in registry['issuers']:
            issuer=item['issuer'];discovery=item['discovery'];rows=discovery.get('original_accessions',[])
            for source in discovery.get('sources',[]):
                remember(ADAPTER.source_path(source,source_root,repo_root),expected=source['sha256'])
            if discovery.get('complete'):registered+=len(rows)
            issuers.append({'issuer':issuer,'discovery_complete':bool(discovery.get('complete')),
                            'discovery_status':discovery.get('status'),'discovery_error':discovery.get('error'),
                            'retained_original_rows':len(rows),'undiscovered_original_count':0 if discovery.get('complete') else None,
                            'coverage_review_needed':discovery.get('coverage_review_needed',[])})
            for row in rows:
                key=(issuer['symbol'],row['accessionNumber'])
                if key in originals:raise ValueError('Duplicate original registry accession')
                originals[key]=(issuer,row)
        if completion.get('registered_originals')!=registered:
            raise ValueError('Terminal registered-original denominator mismatch')
        if sum(completion.get('counts',{}).values())!=completion.get('processed_originals') or completion['processed_originals']>registered:
            raise ValueError('Terminal processed-original denominator mismatch')
        records=[]
        for (symbol,accession),(issuer,row) in originals.items():
            path=source_root/'filings'/symbol/(accession+'.json');digest=remember(path,missing=True)
            manifest=read(path) if digest is not None else {'issuer':issuer,'registry_row':row,'status':'unavailable','error':'manifest_missing','sources':[]}
            if manifest.get('issuer')!=issuer or manifest.get('registry_row')!=row:raise ValueError('Original manifest registry identity mismatch')
            for source in manifest.get('sources',[])+manifest.get('fact_sources',[]):
                remember(ADAPTER.source_path(source,source_root,repo_root),expected=source['sha256'])
            try:record=ADAPTER.enrich_filing(manifest,source_root,repo_root)
            except Exception as error:
                failed={'issuer':issuer,'registry_row':row,'status':'unavailable','error':'qualification_exception:'+type(error).__name__+':'+str(error),'sources':[]}
                record=ADAPTER.enrich_filing(failed,source_root,repo_root)
            record['source_input']={'manifest_path':str(path),'manifest_sha256':digest,'source_status':manifest.get('status'),'source_error':manifest.get('error')}
            records.append(record)
        verify_inputs(identities)
    return records,issuers,identities


def run(definition_path,repo_root=REPO,output_root=ROOT):
    repo_root,output_root=Path(repo_root).resolve(),Path(output_root).resolve();definition_path=Path(definition_path).resolve()
    definition=read(definition_path)
    if definition.get('schema')!=1:raise ValueError('Unsupported qualification definition')
    source_root=repo_root/definition['source_root'];calendar_path=repo_root/definition['calendar']
    inputs={str((repo_root/name).resolve()):digest for name,digest in definition['inputs'].items()}
    required=[calendar_path,source_root/'request.json',source_root/'implementation.json',source_root/'registry.json',source_root/'completion.json',
              source_root/'capture.py',source_root/'cohort.json',source_root/'finalization-definition.json',source_root/'finalization-completion.json',
              repo_root/'.qualification/earnings-quality20260928/cohort/model-specification.json',ADAPTER.Q_PATH,ADAPTER.Q.BASE_PATH,
              repo_root/'src/frontier/historical_lab.py']
    required.extend(ROOT/name for name in ['header_industry.py','run_qualification.py','test_header_industry.py','test_collector.py','extraction-declaration.json'])
    if not {str(path.resolve()) for path in required}.issubset(inputs):raise ValueError('Definition omits required frozen code/source identities')
    inputs[str(definition_path)]=sha(definition_path);verify_inputs(inputs)
    lock=sqlite3.connect(output_root/'qualification.lock.sqlite',timeout=0)
    try:
        lock.execute('BEGIN EXCLUSIVE')
        attempt=output_root/'attempts'/uuid.uuid4().hex;attempt.mkdir(parents=True)
        started={'status':'running','started_at':datetime.now(timezone.utc).isoformat(),'definition_sha256':inputs[str(definition_path)]}
        _save(attempt/'attempt.json',started)
        try:
            calendar=read(calendar_path);sessions=calendar['sessions'] if isinstance(calendar,dict) else calendar
            records,issuers,discovered=collect_records(source_root,repo_root)
            for name,digest in discovered.items():
                if name in inputs and inputs[name]!=digest:raise ValueError('Frozen input changed during collection: '+name)
                inputs.setdefault(name,digest)
            if len(records)!=definition['expected_retained_original_records']:raise ValueError('Declared original-record count mismatch')
            events=ADAPTER.build_features(records,sessions)
            if len(events)!=len(records):raise ValueError('Event denominator differs from original records')
            compact=[{key:value for key,value in event.items() if key not in ['all_facts','selected_facts','q_all_facts','q_selected_facts']} for event in events]
            verify_inputs(inputs)
            for name,value in [('records.json',records),('events.json',compact),('issuer-status.json',issuers),('source-inputs.json',{'definition_sha256':started['definition_sha256'],'files':inputs})]:_save(attempt/name,value)
            counts=lambda rows,key:dict(Counter(row.get(key,'unavailable') for row in rows))
            summary={'status':'complete','declared_issuers':100,'issuer_discoveries_complete':sum(x['discovery_complete'] for x in issuers),
                     'unknown_undiscovered_original_count':any(x['undiscovered_original_count'] is None for x in issuers),
                     'retained_original_records':len(records),'events':len(events),'financial_status':counts(records,'status'),
                     'q_status':counts(records,'q_status'),'industry_status':counts(records,'industry_status'),
                     'feature_status':counts(events,'feature_status'),'joint_feature_status':counts(events,'joint_feature_status'),
                     'strategy_source_status':counts(events,'strategy_source_status'),'execution_status':counts(events,'execution_status'),
                     'industry_reasons':dict(Counter(reason for row in records for reason in row.get('industry_reasons',[]))),
                     'by_issuer':{x['issuer']['symbol']:{'records':x['retained_original_rows'],'strategy_source_qualified':sum(e['symbol']==x['issuer']['symbol'] and e['strategy_source_status']=='qualified' for e in events)} for x in issuers},
                     'definition_sha256':started['definition_sha256'],'network_requests':0,'prices_or_returns_read':False,
                     'prior_history_industry_gate_applied':False,
                     'files':{name:sha(attempt/name) for name in ['records.json','events.json','issuer-status.json','source-inputs.json']}}
            verify_inputs(inputs);_save(attempt/'summary.json',summary)
            _save(attempt/'attempt.json',dict(started,status='complete',completed_at=datetime.now(timezone.utc).isoformat()))
            print(json.dumps({'attempt':str(attempt),'original_records':len(records),'strategy_source_status':summary['strategy_source_status']}),flush=True)
            return attempt
        except Exception as error:
            _save(attempt/'failure.json',{'error':type(error).__name__+': '+str(error)})
            _save(attempt/'attempt.json',dict(started,status='failed'));raise
    finally:lock.rollback();lock.close()

if __name__=='__main__':
    cli=argparse.ArgumentParser(description=__doc__);cli.add_argument('--definition',required=True,type=Path)
    run(cli.parse_args().definition)
