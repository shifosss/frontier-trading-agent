"""Offline terminal-source collector gates, all-issuer denominator and failure retention."""
from pathlib import Path
from unittest.mock import patch
import importlib.util,json,sqlite3
import pytest
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('industry_collector_test',ROOT/'run_qualification.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def save(path,value):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(value))
def fixture(tmp_path):
    source=tmp_path/'source';source.mkdir();sqlite3.connect(source/'capture.lock.sqlite').close()
    issuers=[{'symbol':'S'+str(i),'cik':str(i+1).zfill(10)} for i in range(100)]
    request={'issuers':issuers};save(source/'request.json',request)
    rows=[{'issuer':i,'discovery':{'complete':True,'status':'complete','original_accessions':[]}} for i in issuers]
    registry={'complete':True,'request_sha256':m.sha(source/'request.json'),'issuers':rows}
    row={'accessionNumber':'0000000001-24-000001','filingDate':'2024-05-01','reportDate':'2024-03-31','form':'10-Q'}
    rows[0]['discovery']['original_accessions']=[row]
    save(source/'registry.json',registry)
    save(source/'completion.json',{'status':'incomplete','registered_originals':1,'processed_originals':1,'counts':{'unavailable':1}})
    return source,request,registry,row

def test_missing_terminal_and_unresolved_stop_refuse(tmp_path):
    source,request,_,_=fixture(tmp_path)
    (source/'completion.json').unlink()
    with patch.object(m,'verify_source',return_value=request):
        with pytest.raises(ValueError,match='terminal'):m.collect_records(source,tmp_path)
    save(source/'completion.json',{'status':'incomplete'})
    save(source/'STOP.json',{})
    with patch.object(m,'verify_source',return_value=request):
        with pytest.raises(ValueError,match='STOP'):m.collect_records(source,tmp_path)

def test_source_writer_lock_refuses_without_modifying_source(tmp_path):
    source,request,_,_=fixture(tmp_path);held=sqlite3.connect(source/'capture.lock.sqlite',timeout=0);held.execute('BEGIN EXCLUSIVE')
    try:
        with patch.object(m,'verify_source',return_value=request):
            with pytest.raises(sqlite3.OperationalError):m.collect_records(source,tmp_path)
    finally:held.rollback();held.close()

def test_incomplete_source_preserves_missing_original_and_all_issuers(tmp_path):
    source,request,registry,_=fixture(tmp_path)
    registry['complete']=False;registry['issuers'][1]['discovery']={'complete':False,'status':'unavailable','error':'registry_timeout','original_accessions':[]}
    save(source/'registry.json',registry)
    with patch.object(m,'verify_source',return_value=request):records,issuers,identities=m.collect_records(source,tmp_path)
    assert len(records)==1 and len(issuers)==100
    assert records[0]['status']=='unavailable' and 'manifest_missing' in records[0]['reasons'][0]
    assert records[0]['q_status']=='unavailable' and records[0]['industry_status']=='unavailable'
    assert issuers[1]['undiscovered_original_count'] is None
    assert issuers[0]['undiscovered_original_count']==0
    assert any(value is None for value in identities.values())

def test_membership_order_and_registry_request_identity_required(tmp_path):
    source,request,registry,_=fixture(tmp_path)
    for changed in [dict(registry,issuers=list(reversed(registry['issuers']))),dict(registry,request_sha256='other')]:
        save(source/'registry.json',changed)
        with patch.object(m,'verify_source',return_value=request):
            with pytest.raises(ValueError):m.collect_records(source,tmp_path)

def test_raw_corruption_is_identity_failure_not_source_qualification(tmp_path):
    source,request,registry,row=fixture(tmp_path);raw=source/'raw.bin';raw.write_bytes(b'original')
    manifest={'issuer':request['issuers'][0],'registry_row':row,'status':'unavailable','error':'fact_missing','sources':[{'path':'raw.bin','sha256':m.sha(raw),'status':200,'url':'https://fixture.invalid/header'}]}
    save(source/'filings'/'S0'/(row['accessionNumber']+'.json'),manifest);raw.write_bytes(b'changed')
    with patch.object(m,'verify_source',return_value=request):
        with pytest.raises(ValueError,match='Raw'):m.collect_records(source,tmp_path)

def test_retained_failure_is_not_replaced_and_duplicate_registry_refused(tmp_path):
    source,request,registry,row=fixture(tmp_path)
    manifest={'issuer':request['issuers'][0],'registry_row':row,'status':'unavailable','error':'original_clock_mismatch','sources':[]}
    path=source/'filings'/'S0'/(row['accessionNumber']+'.json');save(path,manifest);before=path.read_bytes()
    with patch.object(m,'verify_source',return_value=request):records,_,_=m.collect_records(source,tmp_path)
    assert 'original_clock_mismatch' in records[0]['reasons'][0] and path.read_bytes()==before
    registry['issuers'][0]['discovery']['original_accessions'].append(row);save(source/'registry.json',registry)
    with patch.object(m,'verify_source',return_value=request):
        with pytest.raises(ValueError,match='Duplicate'):m.collect_records(source,tmp_path)

def test_bound_inputs_rechecked_without_overwriting_expected_hash(tmp_path):
    file=tmp_path/'fixed';file.write_bytes(b'a');identities={str(file):m.sha(file)};file.write_bytes(b'b')
    with pytest.raises(ValueError,match='changed'):m.verify_inputs(identities)
    assert identities[str(file)]!=m.sha(file)


def test_full_offline_collector_writes_all_denominators(tmp_path):
    source,request,_,_=fixture(tmp_path);calendar=tmp_path/'calendar.json';save(calendar,{'sessions':[]})
    for name in ['implementation.json','capture.py','cohort.json','finalization-definition.json','finalization-completion.json']:save(source/name,{})
    model=tmp_path/'.qualification/earnings-quality20260928/cohort/model-specification.json';save(model,{})
    lab=tmp_path/'src/frontier/historical_lab.py';lab.parent.mkdir(parents=True);lab.write_text('# synthetic identity only')
    paths=[calendar,source/'request.json',source/'implementation.json',source/'registry.json',source/'completion.json',source/'capture.py',source/'cohort.json',source/'finalization-definition.json',source/'finalization-completion.json',model,m.ADAPTER.Q_PATH,m.ADAPTER.Q.BASE_PATH,lab]
    paths.extend(ROOT/name for name in ['header_industry.py','run_qualification.py','test_header_industry.py','test_collector.py','extraction-declaration.json'])
    definition=tmp_path/'definition.json';save(definition,{'schema':1,'source_root':'source','calendar':'calendar.json','expected_retained_original_records':1,'inputs':{str(p.resolve()):m.sha(p)for p in paths}})
    out=tmp_path/'out';out.mkdir()
    with patch.object(m,'verify_source',return_value=request):attempt=m.run(definition,repo_root=tmp_path,output_root=out)
    summary=m.read(attempt/'summary.json');events=m.read(attempt/'events.json');issuers=m.read(attempt/'issuer-status.json')
    assert summary['declared_issuers']==100 and len(issuers)==100 and summary['retained_original_records']==len(events)==1
    assert summary['strategy_source_status']=={'unavailable':1} and summary['prices_or_returns_read'] is False
    assert m.read(attempt/'attempt.json')['status']=='complete'


def test_discovery_root_and_history_raw_identities_are_bound(tmp_path):
    source,request,registry,_=fixture(tmp_path)
    raw=source/'original-history.json';raw.write_bytes(b'original submissions history')
    registry['issuers'][0]['discovery']['sources']=[{'path':raw.name,'sha256':m.sha(raw),'status':200,'url':'https://data.sec.gov/submissions/CIK0000000001-submissions-001.json'}]
    save(source/'registry.json',registry)
    with patch.object(m,'verify_source',return_value=request):
        _,_,identities=m.collect_records(source,tmp_path)
        assert identities[str(raw.resolve())]==m.sha(raw)
        raw.write_bytes(b'changed submissions history')
        with pytest.raises(ValueError,match='Raw source identity changed'):
            m.collect_records(source,tmp_path)
