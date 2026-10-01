"""Offline collection keeps the full original registry and both source identities."""
import importlib.util
from pathlib import Path
import json
import hashlib
import pytest

ROOT=Path(__file__).resolve().parents[2]

def load():
    p=Path(__file__).with_name('run_qualification.py');assert p.exists(),'qualification driver not implemented'
    spec=importlib.util.spec_from_file_location('qualification_test',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def setup(tmp_path):
    source=ROOT/'.qualification/filing-source20260928/filings/AAPL/0000320193-20-000062.json'
    manifest=json.loads(source.read_text(encoding='utf-8'));base=tmp_path/'baseline';p=base/'filings/AAPL'/source.name;p.parent.mkdir(parents=True);p.write_text(json.dumps(manifest),encoding='utf-8')
    missing=dict(manifest['registry_row'],accessionNumber='missing',reportDate='2020-09-26',filingDate='2020-10-30')
    registry={'complete':True,'issuers':[{'issuer':manifest['issuer'],'discovery':{'complete':True,'original_accessions':[manifest['registry_row'],missing]}}]}
    return base,p,manifest,registry


def test_registry_denominator_and_missing_manifests_retained(tmp_path):
    m=load();base,p,manifest,registry=setup(tmp_path)
    records,identities=m.collect_records(registry,base,[],ROOT)
    assert len(records)==2 and records[0]['status']=='qualified'
    assert records[1]['status']=='unavailable' and 'manifest_missing' in records[1]['reasons']
    assert records[0]['source_input']['baseline_sha256']==hashlib.sha256(p.read_bytes()).hexdigest()
    assert str(p) in identities


def test_overlay_preserves_baseline_failure_and_effective_source(tmp_path):
    m=load();base,p,manifest,registry=setup(tmp_path)
    p.write_text(json.dumps(dict(manifest,status='failed',error='bounded source failure')),encoding='utf-8')
    before=p.read_bytes();overlay=tmp_path/'overlay';q=overlay/'filings/AAPL'/p.name;q.parent.mkdir(parents=True)
    supplemented=dict(manifest,supplement_of={'original_manifest_path':str(p),'original_manifest_sha256':hashlib.sha256(before).hexdigest(),'original_error':'bounded source failure','recovery_class':'fixture_recovery'})
    q.write_text(json.dumps(supplemented),encoding='utf-8')
    (overlay/'completion.json').write_text(json.dumps({'declared_original_accessions':1,'results':[{'issuer':manifest['issuer'],'registry_row':manifest['registry_row']}]}),encoding='utf-8')
    records,identities=m.collect_records(registry,base,[overlay],ROOT)
    assert len(records)==2 and records[0]['status']=='qualified'
    assert records[0]['source_input']['baseline_status']=='failed' and records[0]['source_input']['effective_sha256']==hashlib.sha256(q.read_bytes()).hexdigest()
    assert p.read_bytes()==before
    supplemented['supplement_of']['original_manifest_sha256']='bad';q.write_text(json.dumps(supplemented),encoding='utf-8')
    with pytest.raises(ValueError,match='baseline'):m.collect_records(registry,base,[overlay],ROOT)


def test_incomplete_overlay_is_not_silently_used(tmp_path):
    m=load();base,p,manifest,registry=setup(tmp_path);overlay=tmp_path/'overlay';overlay.mkdir()
    with pytest.raises(ValueError,match='terminal'):m.collect_records(registry,base,[overlay],ROOT)


def overlay_fixture(tmp_path, p, manifest, name='overlay', status='captured'):
    if json.loads(p.read_text(encoding='utf-8'))['status']=='captured':
        p.write_text(json.dumps(dict(manifest,status='incomplete',error='original source gap')),encoding='utf-8')
    directory=tmp_path/name;file=directory/'filings/AAPL'/p.name;file.parent.mkdir(parents=True)
    saved=dict(manifest,status=status,supplement_of={'original_manifest_path':str(p),
        'original_manifest_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),
        'original_error':'original source gap','recovery_class':'fixture_recovery'})
    if status!='captured':saved.update(error='retry unavailable',sources=[],fact_sources=[])
    file.write_text(json.dumps(saved),encoding='utf-8')
    (directory/'completion.json').write_text(json.dumps({'declared_original_accessions':1,
        'results':[{'issuer':manifest['issuer'],'registry_row':manifest['registry_row'],'status':status}]}),encoding='utf-8')
    return directory


def test_unsuccessful_overlay_is_retained_and_conflicting_overlays_rejected(tmp_path):
    m=load();base,p,manifest,registry=setup(tmp_path)
    first=overlay_fixture(tmp_path,p,manifest,status='incomplete')
    records,_=m.collect_records(registry,base,[first],ROOT)
    assert len(records)==2 and records[0]['status']=='unavailable'
    assert records[0]['source_input']['effective_status']=='incomplete'
    assert 'retry unavailable' in str(records[0]['reasons'])
    second=overlay_fixture(tmp_path,p,manifest,name='second')
    with pytest.raises(ValueError,match='Conflicting overlays'):m.collect_records(registry,base,[first,second],ROOT)


def test_terminal_overlay_denominator_mismatch_is_rejected(tmp_path):
    m=load();base,p,manifest,registry=setup(tmp_path);overlay=overlay_fixture(tmp_path,p,manifest)
    complete=json.loads((overlay/'completion.json').read_text());complete['declared_original_accessions']=2
    (overlay/'completion.json').write_text(json.dumps(complete))
    with pytest.raises(ValueError,match='denominator'):m.collect_records(registry,base,[overlay],ROOT)


def test_identity_verification_detects_missing_source_appearing_later(tmp_path):
    m=load();base,p,manifest,registry=setup(tmp_path)
    _,identities=m.collect_records(registry,base,[],ROOT)
    missing=base/'filings/AAPL/missing.json';missing.write_text('{}')
    with pytest.raises(ValueError,match='changed'):m.verify_inputs(identities)


def runner_fixture(tmp_path,monkeypatch,m):
    base,p,manifest,registry=setup(tmp_path);overlay=overlay_fixture(tmp_path,p,manifest)
    runner=tmp_path/'runner';runner.mkdir()
    for name in ('features.py','test_features.py','extraction-definition.json','extraction-amendment1.json',
                 'interface.md','run_qualification.py','test_qualification.py'):
        (runner/name).write_bytes((Path(__file__).parent/name).read_bytes())
    monkeypatch.setattr(m,'ROOT',runner)
    registry_path=base/'registry.json';registry_path.write_text(json.dumps(registry),encoding='utf-8')
    calendar=tmp_path/'calendar.json';calendar.write_text(json.dumps({'sessions':[]}),encoding='utf-8')
    for source in (base,overlay):
        for name in ('request.json','implementation.json'):(source/name).write_text('{}',encoding='utf-8')
    (base/'completion.json').write_text(json.dumps({'original_accessions':2}),encoding='utf-8')
    files=[*runner.iterdir(),registry_path,calendar,ROOT/'src/frontier/historical_lab.py']
    files += [directory/name for directory in (base,overlay) for name in ('request.json','implementation.json','completion.json')]
    definition=runner/'qualification-definition.json'
    definition.write_text(json.dumps({'schema':1,'expected_original_records':2,'baseline_root':str(base),
        'overlay_roots':[str(overlay)],'registry':str(registry_path),'calendar':str(calendar),
        'inputs':{str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in files}}),encoding='utf-8')
    return definition,overlay


def test_cli_writes_unique_attempts_with_full_and_compact_denominators(tmp_path,monkeypatch):
    m=load();definition,_=runner_fixture(tmp_path,monkeypatch,m)
    first=m.run(definition);second=m.run(definition)
    assert first!=second
    records=json.loads((first/'records.json').read_text());events=json.loads((first/'events.json').read_text())
    assert len(records)==len(events)==2 and 'all_facts' in records[0] and 'all_facts' not in events[0]
    summary=json.loads((first/'summary.json').read_text())
    assert summary['original_records']==2 and summary['financial_status']=={'qualified':1,'unavailable':1}
    assert summary['price_returns_read'] is False
    for name,want in summary['files'].items():assert hashlib.sha256((first/name).read_bytes()).hexdigest()==want


def test_frozen_input_cannot_be_replaced_by_new_collection_identity(tmp_path,monkeypatch):
    m=load();definition,overlay=runner_fixture(tmp_path,monkeypatch,m);original=m.collect_records
    def changed(*args):
        path=overlay/'completion.json';path.write_bytes(path.read_bytes()+b'\n')
        return original(*args)
    monkeypatch.setattr(m,'collect_records',changed)
    with pytest.raises(ValueError,match='changed during collection'):m.run(definition)
    attempt=next((m.ROOT/'attempts').iterdir())
    assert json.loads((attempt/'attempt.json').read_text())['status']=='failed'
    assert not (attempt/'summary.json').exists()
