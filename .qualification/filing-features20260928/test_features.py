"""Source-only regression tests; expected values come from original statements or hand arithmetic."""
from pathlib import Path
import importlib.util
import math
import pytest

ROOT=Path(__file__).resolve().parents[2]
MODULE=Path(__file__).with_name('features.py')

def module():
    assert MODULE.exists(), 'feature parser not implemented'
    spec=importlib.util.spec_from_file_location('filing_feature_test',MODULE)
    obj=importlib.util.module_from_spec(spec); spec.loader.exec_module(obj); return obj

NS='xmlns:xbrli="http://www.xbrl.org/2003/instance" xmlns:us-gaap="http://fasb.org/us-gaap/2024" xmlns:dei="http://xbrl.sec.gov/dei/2024" xmlns:iso4217="http://www.xbrl.org/2003/iso4217"'

def document(extra='', current='30',prior='10',assets='100',start='2024-04-01',end='2024-06-30',year=2024,quarter='Q2',dim=''):
    def ctx(cid,s,e):
        return f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier>{dim if cid=="cur" else ""}</xbrli:entity><xbrli:period><xbrli:startDate>{s}</xbrli:startDate><xbrli:endDate>{e}</xbrli:endDate></xbrli:period></xbrli:context>'
    def fact(tag,ctxid,v):
        return f'<{tag} contextRef="{ctxid}" unitRef="USD" decimals="0">{v}</{tag}>'
    body=ctx('ytd','2024-01-01',end)+ctx('cur',start,end)+ctx('prior','2023-04-01','2023-06-30')
    body+='<xbrli:context id="fy"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:instant>2023-12-31</xbrli:instant></xbrli:period></xbrli:context>'
    body+='<xbrli:unit id="USD"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
    body+=f'<dei:DocumentFiscalYearFocus contextRef="ytd">{year}</dei:DocumentFiscalYearFocus><dei:DocumentFiscalPeriodFocus contextRef="ytd">{quarter}</dei:DocumentFiscalPeriodFocus>'
    body+=fact('us-gaap:NetIncomeLoss','cur',current)+fact('us-gaap:NetIncomeLoss','prior',prior)+fact('us-gaap:Assets','fy',assets)
    return f'<xbrli:xbrl {NS}>{body}{extra}</xbrli:xbrl>'.encode()

def qualify(raw):
    m=module(); return m.qualify_facts(m.extract_document(raw,'original_instance','1'),'2024-06-30')

@pytest.mark.parametrize('name,report,cik,want',[
 ('aapl_2020q3','2020-06-27','320193',('11253000000','10044000000','338516000000',2020,'Q3','2019-09-28')),
 ('msft_2024q3','2024-03-31','789019',('21939000000','18299000000','411976000000',2024,'Q3','2023-06-30')),
 ('f_2024q2','2024-06-30','37996',('1831000000','1917000000','273310000000',2024,'Q2','2023-12-31'))])
def test_original_three_fixtures(name,report,cik,want):
    m=module(); raw=(ROOT/'.qualification/filing-feasibility20260928/raw'/f'{name}_original.bin').read_bytes()
    doc=m.extract_document(raw,'inline_primary',cik); r=m.qualify_facts(doc,report)
    assert r['status']=='qualified',r
    assert tuple(r[k] for k in ('current_ni','prior_ni','prior_fy_assets','fiscal_year','fiscal_period','prior_fy_end'))==want
    for f in r['selected_facts']:
        span=f['source_span']; import hashlib
        assert hashlib.sha256(raw[span[0]:span[1]]).hexdigest()==f['fragment_sha256']


def test_quarter_not_year_to_date_and_exact_assets_instant():
    extra='<us-gaap:NetIncomeLoss contextRef="ytd" unitRef="USD">999</us-gaap:NetIncomeLoss>'
    r=qualify(document(extra=extra)); assert r['status']=='qualified'; assert float(r['u'])==.2
    assert r['current_start']=='2024-04-01' and r['prior_fy_end']=='2023-12-31'

@pytest.mark.parametrize('change',[
 {'dim':'<xbrli:segment><xbrli:foo>segment</xbrli:foo></xbrli:segment>'},
 {'extra':'<us-gaap:NetIncomeLoss contextRef="cur" unitRef="USD">31</us-gaap:NetIncomeLoss>'},
 {'start':'2024-01-01'}, {'assets':'0'}, {'quarter':'FY'}])
def test_ambiguous_or_nonquarter_inputs_never_imputed(change):
    assert qualify(document(**change))['status']=='unavailable'

def test_exact_duplicate_is_retained_and_profitloss_not_substitute():
    r=qualify(document(extra='<us-gaap:NetIncomeLoss contextRef="cur" unitRef="USD">30</us-gaap:NetIncomeLoss>'))
    assert r['status']=='qualified' and len([f for f in r['selected_facts'] if f['context'].get('startDate')=='2024-04-01'])==2
    raw=document().replace(b'us-gaap:NetIncomeLoss',b'us-gaap:ProfitLoss')
    assert qualify(raw)['status']=='unavailable'

def test_inline_scale_sign_and_context_unit_identity():
    raw=document(current='30').decode().replace('<xbrli:xbrl ', '<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" ').replace('</xbrli:xbrl>','</html>')
    raw=raw.replace('<us-gaap:NetIncomeLoss contextRef="cur" unitRef="USD" decimals="0">30</us-gaap:NetIncomeLoss>','<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="cur" unitRef="USD" scale="6" sign="-">30</ix:nonFraction>')
    m=module(); facts=m.extract_document(raw.encode(),'inline_primary','1')['facts']
    assert [f['value'] for f in facts if f['context'].get('startDate')=='2024-04-01']==['-30000000']
    wrong=document().replace(b'iso4217:USD',b'iso4217:CAD')
    assert qualify(wrong)['status']=='unavailable'

def records():
    out=[]
    for n in range(9):
        fy=2020+n//3;q=n%3+1;end=f'{fy}-{q*3:02}-28';filed=f'{fy}-{q*3+1:02}-20'
        out.append({'symbol':'A','accession':str(n),'report_date':end,'filing_date':filed,'acceptance_et':filed+'T16:00:00-04:00','availability_floor':filed+'T01:00:00-04:00','status':'qualified','fiscal_year':fy,'fiscal_period':f'Q{q}','slot':fy*3+q-1,'u':str(n+1)})
    return out

def test_scaler_uses_eight_prior_original_slots_and_does_not_demean():
    m=module(); r=m.build_features(records(),[]) [-1]
    assert r['feature_status']=='qualified'; assert float(r['S'])==pytest.approx(9/math.sqrt(6)); assert r['history_accessions']==list(map(str,range(8)))
    changed=records()+[{**records()[-1],'accession':'later','filing_date':'2023-01-20','u':'999'}]
    assert m.build_features(changed,[])[-1]['feature_status']=='duplicate_original'

@pytest.mark.parametrize('mode',['missing','unavailable','unknown_slot','future','zero_variance'])
def test_history_never_skips_missing_or_unavailable_events(mode):
    m=module(); rs=records()
    if mode=='missing':rs.pop(4)
    elif mode=='unavailable':rs[4]['status']='unavailable'
    elif mode=='unknown_slot':rs[4].pop('slot');rs[4]['status']='unavailable'
    elif mode=='future':rs[4]['availability_floor']='2029-01-01T01:00:00-05:00'
    else:
        for r in rs[:-1]:r['u']='1'
    assert m.build_features(rs,[])[-1]['feature_status']=='unavailable'

def test_clock_uses_public_filing_date_and_next_session_actual_close():
    m=module(); c=m.event_clock('2020-07-30T19:29:09-04:00','2020-07-31',[{'session':'2020-07-31','open':'2020-07-31T13:30:00+00:00','close':'2020-07-31T20:00:00+00:00'},{'session':'2020-08-03','open':'2020-08-03T13:30:00+00:00','close':'2020-08-03T20:00:00+00:00'}])
    assert c['availability_floor']=='2020-08-01T01:00:00-04:00'
    assert c['decision_time']=='2020-08-03T09:00:00-04:00' and c['entry_time']=='2020-08-03T20:00:00+00:00'


def test_nested_selected_inline_fact_is_not_swallowed_by_other_fact():
    m=module()
    raw=b'<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" '+NS.encode()+b'><xbrli:context id="a"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-03-31</xbrli:endDate></xbrli:period></xbrli:context><ix:nonNumeric name="dei:DocumentPeriodEndDate" contextRef="a">March31,<ix:nonNumeric name="dei:DocumentFiscalYearFocus" contextRef="a">2024</ix:nonNumeric></ix:nonNumeric></html>'
    assert [f['value'] for f in m.extract_document(raw,'inline_primary','1')['facts']]==['2024']


def test_actual_original_instance_manifest_qualifies_end_to_end():
    import json
    m=module();root=ROOT/'.qualification/filing-source20260928'
    manifest=json.loads((root/'filings/AAPL/0001193125-12-023398.json').read_text(encoding='utf-8'))
    r=m.qualify_filing(manifest,root,ROOT)
    assert r['status']=='qualified',r['reasons']
    assert r['fiscal_period']=='Q1' and r['fiscal_year']==2012
    assert r['prior_fy_end']=='2011-09-24' and r['current_start']=='2011-09-25'


@pytest.mark.parametrize('mode',['same_slot','unknown_slot'])
def test_future_filing_metadata_does_not_change_earlier_features(mode):
    m=module();rs=records();expected=m.build_features(rs,[])[8]
    future=dict(rs[4],accession='future',filing_date='2025-01-20',acceptance_et='2025-01-20T16:00:00-05:00',availability_floor='2025-01-21T01:00:00-05:00',report_date='2021-06-29')
    if mode=='unknown_slot':future.pop('slot');future['status']='unavailable'
    got=next(r for r in m.build_features(rs+[future],[]) if r['accession']=='8')
    assert got['feature_status']=='qualified' and got['S']==expected['S']


def test_excluded_footnote_and_equivalent_numeric_duplicates():
    m=module();raw=document().decode().replace('<xbrli:xbrl ', '<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" ').replace('</xbrli:xbrl>','</html>')
    raw=raw.replace('<us-gaap:NetIncomeLoss contextRef="cur" unitRef="USD" decimals="0">30</us-gaap:NetIncomeLoss>','<ix:nonFraction name="us-gaap:NetIncomeLoss" contextRef="cur" unitRef="USD">1,234<ix:exclude>1</ix:exclude></ix:nonFraction>')
    facts=m.extract_document(raw.encode(),'inline_primary','1')['facts']
    assert [f['value'] for f in facts if f['concept']=='us-gaap:NetIncomeLoss']==['1234']
    r=qualify(document(extra='<us-gaap:NetIncomeLoss contextRef="cur" unitRef="USD">30.0</us-gaap:NetIncomeLoss>'))
    assert r['status']=='qualified'


def test_intervening_quarterly_assets_not_used_as_fiscal_year_end():
    assert qualify(document().replace(b'<xbrli:instant>2023-12-31',b'<xbrli:instant>2024-03-31'))['status']=='unavailable'


def test_missing_report_dates_remain_distinct_and_block_only_relevant_history():
    m=module();rs=records()
    unknown1={'symbol':'A','accession':'bad1','report_date':None,'filing_date':'2021-08-01','status':'unavailable'}
    unknown2=dict(unknown1,accession='bad2',filing_date='2021-08-02')
    got=m.build_features(rs+[unknown1,unknown2],[])
    assert all(r['feature_status']=='unavailable' for r in got if r['accession'].startswith('bad'))
    assert next(r for r in got if r['accession']=='8')['feature_status']=='unavailable'
    ancient=dict(unknown1,accession='ancient',filing_date='2010-01-01')
    assert next(r for r in m.build_features(rs+[ancient],[]) if r['accession']=='8')['feature_status']=='qualified'


def test_original_fact_source_cannot_be_borrowed_from_another_accession():
    import json
    m=module();root=ROOT/'.qualification/filing-source20260928'
    manifest=json.loads((root/'filings/AAPL/0001193125-12-023398.json').read_text(encoding='utf-8'))
    manifest['fact_sources'][0]['url']=manifest['fact_sources'][0]['url'].replace('000119312512023398','000119312599999999')
    assert m.qualify_filing(manifest,root,ROOT)['status']=='unavailable'


def test_calendar_boundaries_are_not_fabricated_execution_dates():
    m=module();cal=[{'session':'2020-08-03','open':'2020-08-03T13:30:00+00:00','close':'2020-08-03T20:00:00+00:00'}]
    early=m.event_clock('2012-01-01T16:00:00-05:00','2012-01-01',cal)
    assert early['entry_time'] is None and early['execution_status']=='calendar_starts_after_availability'
    last=m.event_clock('2020-08-02T16:00:00-04:00','2020-08-02',cal)
    assert last['entry_time']=='2020-08-03T20:00:00+00:00' and last['execution_status']=='exit_outside_calendar'


def test_later_original_cannot_replace_first_original_failure():
    m=module();rs=records();rs[4]['status']='unavailable'
    replacement=dict(rs[4],accession='replacement',filing_date='2021-08-21',status='qualified')
    got=m.build_features(rs+[replacement],[])
    assert next(r for r in got if r['accession']=='replacement')['feature_status']=='duplicate_original'
    assert next(r for r in got if r['accession']=='8')['feature_status']=='unavailable'
