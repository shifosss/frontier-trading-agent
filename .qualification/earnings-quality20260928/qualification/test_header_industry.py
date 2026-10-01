"""Offline SIC/source qualification tests; no capture or financial outcome access."""
from pathlib import Path
from unittest.mock import patch
import importlib.util, hashlib, json, sqlite3
import pytest
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('industry_test_module',ROOT/'header_industry.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
CIK='0000000123';ACC='0000000123-24-000001'
def company(cik=CIK,sic='2834',extra=''):
    return f'<COMPANY-DATA>\n<CIK>{cik}\n<ASSIGNED-SIC>{sic}\n{extra}</COMPANY-DATA>\n'
def filer(body=None):return '<FILER>\n'+(company() if body is None else body)+'</FILER>\n'
def header(body=None):return ('<SEC-HEADER>'+ACC+'.hdr.sgml\n<ACCESSION-NUMBER>'+ACC+'\n'+(filer() if body is None else body)+'</SEC-HEADER>\n').encode()
def test_valid_original_spans_and_cik_normalization():
    raw=header(filer(company('123','0100','<ASSIGNED-SIC>100\n')));r=m.parse_header(raw,CIK,ACC)
    assert r['industry_status']=='qualified' and r['industry_sic']=='0100'
    assert r['industry_header_sha256']==hashlib.sha256(raw).hexdigest()
    for part in r['industry_evidence']:
        a,b=part['span'];assert hashlib.sha256(raw[a:b]).hexdigest()==part['sha256'];assert raw[a:b].decode()==part['raw_text']
def test_cofiler_first_value_never_substituted():
    r=m.parse_header(header(filer(company('456','6021'))+filer()),CIK,ACC)
    assert r['industry_status']=='qualified' and r['industry_sic']=='2834'
    r=m.parse_header(header(filer(company('456','2834'))+filer(company(CIK,'6021'))),CIK,ACC)
    assert r['industry_status']=='excluded' and r['industry_sic']=='6021'
@pytest.mark.parametrize('body',[filer(company(CIK,'2834','<ASSIGNED-SIC>6021\n')),filer(company(CIK,'2X34')),filer(company(CIK,'')),filer(company(CIK,'99999')),filer(company(CIK,'2834','<CIK>456\n')),filer(company('','2834')),filer()+filer(),filer(company('456','2834')),filer(company()+company()),filer().replace('</FILER>',''),filer(company('456'))+filer(company('', '2834'))])
def test_ambiguous_missing_and_malformed_stay_unavailable(body):
    assert m.parse_header(header(body),CIK,ACC)['industry_status']=='unavailable'
@pytest.mark.parametrize('sic,status',[('0099','excluded'),('0100','qualified'),('5999','qualified'),('6000','excluded'),('6999','excluded'),('7000','qualified'),('8999','qualified'),('9000','excluded'),('0000','excluded')])
def test_declared_ranges(sic,status):assert m.parse_header(header(filer(company(CIK,sic))),CIK,ACC)['industry_status']==status
def test_other_context_and_original_accession_not_substituted():
    raw=header(filer(company('456','2834'))+'<SUBJECT-COMPANY>'+company()+'</SUBJECT-COMPANY>')
    assert m.parse_header(raw,CIK,ACC)['industry_status']=='unavailable'
    assert m.parse_header(header(),CIK,'0000000123-24-000002')['industry_status']=='unavailable'
def test_gate_preserves_every_original_field_and_history():
    old=[{'symbol':'X','S':'1.5','Q':'0.2','u':'0.01','selected':True,'joint_feature_status':'qualified','joint_feature_reasons':[],'history_accessions':['a','b'],'industry_status':'excluded','industry_reasons':['sic_outside_declared_ranges']}]
    with patch.object(m.Q,'build_features',return_value=old):result=m.build_features([],[])
    assert all(result[0][k]==v for k,v in old[0].items());assert result[0]['strategy_source_status']=='unavailable';assert result[0]['selected'] is True
    assert 'strategy_source_status' not in old[0]
def test_manifest_header_identity_is_exact_and_hash_bound(tmp_path):
    raw=header();(tmp_path/'header.bin').write_bytes(raw)
    source={'url':f'https://www.sec.gov/Archives/edgar/data/123/{ACC.replace("-","")}/{ACC}.hdr.sgml','path':'header.bin','sha256':hashlib.sha256(raw).hexdigest(),'status':200}
    manifest={'issuer':{'symbol':'X','cik':CIK},'registry_row':{'accessionNumber':ACC},'sources':[source]}
    assert m.qualify_header(manifest,tmp_path,tmp_path)['industry_status']=='qualified'
    (tmp_path/'header.bin').write_bytes(raw+b'changed')
    assert m.qualify_header(manifest,tmp_path,tmp_path)['industry_status']=='unavailable'
    source['url']=source['url'].replace('/123/','/456/')
    assert m.qualify_header(manifest,tmp_path,tmp_path)['industry_status']=='unavailable'
def test_two_saved_original_header_fixtures():
    repo=ROOT.parents[2];source_root=repo/'.qualification/earnings-quality20260928/source'
    for symbol,acc,cik,sic in [('MCRB','0000950170-21-000674','0001609809','2834'),('CAG','0000023217-13-000005','0000023217','2000')]:
        manifest=json.loads((source_root/'filings'/symbol/(acc+'.json')).read_text());r=m.qualify_header(manifest,source_root,repo)
        assert manifest['issuer']['cik']==cik;assert r['industry_status']=='qualified' and r['industry_sic']==sic


def test_actual_eight_prior_history_unchanged_by_industry_gate():
    path=m.Q.BASE_PATH.with_name('test_features.py');spec=importlib.util.spec_from_file_location('original_history_fixture_for_industry',path);fixture=importlib.util.module_from_spec(spec);spec.loader.exec_module(fixture)
    records=fixture.records()
    for i,row in enumerate(records):row.update(q_status='qualified',Q='0.3',q_reasons=[],industry_status='excluded' if i<8 else 'qualified',industry_reasons=[])
    original=m.Q.build_features(records,[]);gated=m.build_features(records,[])
    assert original[-1]['feature_status']=='qualified'
    for before,after in zip(original,gated):assert all(after[k]==v for k,v in before.items())
    assert len(gated[-1]['history_accessions'])==8
    for row in records:row['industry_status']='unavailable'
    changed=m.build_features(records,[])
    assert changed[-1]['S']==gated[-1]['S'] and changed[-1]['history_accessions']==gated[-1]['history_accessions']
