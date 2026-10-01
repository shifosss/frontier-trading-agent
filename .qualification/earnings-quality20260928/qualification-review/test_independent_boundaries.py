from pathlib import Path
import importlib.util,json,sqlite3,hashlib
from unittest.mock import patch
import pytest
HERE=Path(__file__).resolve().parent
QUAL=HERE.parent/'qualification'
s=importlib.util.spec_from_file_location('independent_existing_fixture',QUAL/'test_collector.py')
fixture_module=importlib.util.module_from_spec(s);s.loader.exec_module(fixture_module)
m=fixture_module.m
save=fixture_module.save

def test_discovery_source_corruption_refused(tmp_path):
    source,request,registry,row=fixture_module.fixture(tmp_path)
    raw=source/'discovery-raw.bin';raw.write_bytes(b'original submissions history')
    registry['issuers'][0]['discovery']['sources']=[{'url':'https://data.sec.gov/submissions/CIK0000000001.json','path':raw.name,'sha256':hashlib.sha256(raw.read_bytes()).hexdigest(),'status':200}]
    save(source/'registry.json',registry)
    raw.write_bytes(b'changed submissions history')
    with patch.object(m,'verify_source',return_value=request):
        with pytest.raises(ValueError,match='Raw source identity changed'):
            m.collect_records(source,tmp_path)

def test_reader_is_read_only_and_prevents_capture_writer(tmp_path):
    source,request,_,_=fixture_module.fixture(tmp_path)
    path=source/'capture.lock.sqlite';before=path.read_bytes()
    with m.source_read_guard(source):
        writer=sqlite3.connect(path,timeout=0)
        try:
            with pytest.raises(sqlite3.OperationalError):writer.execute('BEGIN EXCLUSIVE')
        finally:writer.close()
    assert path.read_bytes()==before

def test_partial_discovery_retained_originals_not_silently_removed(tmp_path):
    source,request,registry,row=fixture_module.fixture(tmp_path)
    registry['issuers'][0]['discovery'].update(complete=False,error='partial_history')
    save(source/'registry.json',registry)
    save(source/'completion.json',{'status':'incomplete','registered_originals':0,'processed_originals':0,'counts':{}})
    with patch.object(m,'verify_source',return_value=request):
        records,issuers,_=m.collect_records(source,tmp_path)
    assert len(records)==1 and len(issuers)==100
    assert issuers[0]['retained_original_rows']==1 and issuers[0]['undiscovered_original_count'] is None
    assert records[0]['status']=='unavailable'

def test_absent_expected_raw_file_not_qualified(tmp_path):
    source,request,registry,row=fixture_module.fixture(tmp_path)
    manifest={'issuer':request['issuers'][0],'registry_row':row,'status':'captured','sources':[{'path':'missing.bin','sha256':'0'*64,'status':200,'url':'https://fixture.invalid/source'}]}
    save(source/'filings'/'S0'/(row['accessionNumber']+'.json'),manifest)
    with patch.object(m,'verify_source',return_value=request):
        with pytest.raises(ValueError,match='Required source missing'):m.collect_records(source,tmp_path)
