from pathlib import Path
import importlib.util
from decimal import Decimal
import copy
import hashlib
import pytest

REPO=Path(__file__).resolve().parents[3]

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def module():return load(Path(__file__).with_name('cash_backing.py'),'cash_backing_test')
def fixture_module():return load(REPO/'.qualification/filing-features20260928/test_features.py','original_fixture_helpers')
def xml(extra='',current_cfo='120',prior_cfo='70'):
    raw=fixture_module().document().decode()
    context='<xbrli:context id="priorYTD"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2023-01-01</xbrli:startDate><xbrli:endDate>2023-06-30</xbrli:endDate></xbrli:period></xbrli:context>'
    def f(concept,ctx,value):return f'<us-gaap:{concept} contextRef="{ctx}" unitRef="USD">{value}</us-gaap:{concept}>'
    added=context+f('NetIncomeLoss','ytd','50')+f('NetIncomeLoss','priorYTD','30')
    added+=f('NetCashProvidedByUsedInOperatingActivities','ytd',current_cfo)+f('NetCashProvidedByUsedInOperatingActivities','priorYTD',prior_cfo)
    return raw.replace('</xbrli:xbrl>',added+extra+'</xbrli:xbrl>').encode()

def qualify(raw):return module().qualify_document(raw,'original_xbrl_instance','1','2024-06-30')

def test_ytd_difference_with_frozen_quarter_s_unchanged():
    r=qualify(xml());assert r['status']==r['q_status']=='qualified'
    assert Decimal(r['u'])==Decimal('.2') and Decimal(r['Q'])==Decimal('.3')
    assert r['q_current_ni']=='50' and r['current_ni']=='30'
    assert r['q_current_start']=='2024-01-01' and r['q_prior_start']=='2023-01-01'

@pytest.mark.parametrize('mode',['wrong_current','wrong_prior','wrong_currency','dimensional','alternative_concept','duplicate_conflict'])
def test_unavailable_cash_backing_preserves_s(mode):
    raw=xml()
    if mode=='wrong_current':raw=raw.replace(b'Activities contextRef="ytd"',b'Activities contextRef="cur"')
    elif mode=='wrong_prior':raw=raw.replace(b'Activities contextRef="priorYTD"',b'Activities contextRef="prior"')
    elif mode=='wrong_currency':raw=raw.replace(b'Activities contextRef="ytd" unitRef="USD"',b'Activities contextRef="ytd" unitRef="CAD"')
    elif mode=='alternative_concept':raw=raw.replace(b'NetCashProvidedByUsedInOperatingActivities',b'NetCashProvidedByUsedInOperatingActivitiesContinuingOperations')
    elif mode=='duplicate_conflict':raw=xml(extra='<us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="ytd" unitRef="USD">121</us-gaap:NetCashProvidedByUsedInOperatingActivities>')
    else:
        extra='<xbrli:context id="dim"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier><xbrli:segment>specific segment</xbrli:segment></xbrli:entity><xbrli:period><xbrli:startDate>2024-01-01</xbrli:startDate><xbrli:endDate>2024-06-30</xbrli:endDate></xbrli:period></xbrli:context>'
        raw=xml(extra=extra).replace(b'Activities contextRef="ytd"',b'Activities contextRef="dim"')
    r=qualify(raw);assert r['status']=='qualified';assert r['q_status']=='unavailable' and r['Q'] is None

def test_duplicate_amount_agreement_and_exact_source_spans():
    raw=xml(extra='<us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="ytd" unitRef="USD">120.0</us-gaap:NetCashProvidedByUsedInOperatingActivities>')
    r=qualify(raw);assert r['q_status']=='qualified'
    cf=[f for f in r['q_selected_facts'] if f['concept'].endswith('Activities')];assert len(cf)==3
    for f in r['q_selected_facts']:
        for part in (f,f['context_source'],f['unit_source']):
            a,b=part['source_span'];assert 0<=a<b<=len(raw);assert hashlib.sha256(raw[a:b]).hexdigest()==part['fragment_sha256']

def test_prior_period_ambiguity_not_chosen_by_value():
    extra='<xbrli:context id="other"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2023-01-02</xbrli:startDate><xbrli:endDate>2023-06-30</xbrli:endDate></xbrli:period></xbrli:context>'
    for tag in ['NetCashProvidedByUsedInOperatingActivities','NetIncomeLoss']:extra+=f'<us-gaap:{tag} contextRef="other" unitRef="USD">999</us-gaap:{tag}>'
    r=qualify(xml(extra));assert r['q_status']=='unavailable';assert 'ambiguous' in str(r['q_reasons'])

def test_future_period_facts_do_not_change_current_q():
    raw=xml();extra='<xbrli:context id="future"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">1</xbrli:identifier></xbrli:entity><xbrli:period><xbrli:startDate>2025-01-01</xbrli:startDate><xbrli:endDate>2025-06-30</xbrli:endDate></xbrli:period></xbrli:context>'
    for tag in ['NetCashProvidedByUsedInOperatingActivities','NetIncomeLoss']:extra+=f'<us-gaap:{tag} contextRef="future" unitRef="USD">99999</us-gaap:{tag}>'
    assert qualify(xml(extra))['Q']==qualify(raw)['Q']

def test_q_missingness_does_not_change_original_s_history():
    m=module();rs=fixture_module().records()
    for r in rs:r.update(q_status='unavailable',Q=None,q_reasons=['missing_CFO'])
    rs[-1].update(q_status='qualified',Q='0.3',q_reasons=[])
    a=m.build_features(rs,[])[-1];assert a['feature_status']=='qualified' and a['Q']=='0.3'
    assert a['joint_feature_status']=='unavailable' # no supplied execution calendar
    changed=copy.deepcopy(rs);changed[3].update(q_status='qualified',Q='9999')
    b=m.build_features(changed,[])[-1];assert a['S']==b['S'] and a['history_accessions']==b['history_accessions']


def test_inline_sign_scale_exclude_and_original_identities_without_s_mutation():
    raw=xml().decode().replace('<xbrli:xbrl ','<html xmlns:ix="http://www.xbrl.org/2013/inlineXBRL" ').replace('</xbrli:xbrl>','</html>')
    old='<us-gaap:NetCashProvidedByUsedInOperatingActivities contextRef="ytd" unitRef="USD">120</us-gaap:NetCashProvidedByUsedInOperatingActivities>'
    fact='<ix:nonFraction name="us-gaap:NetCashProvidedByUsedInOperatingActivities" contextRef="ytd" unitRef="USD" sign="-" scale="6">1,234<ix:exclude>1</ix:exclude></ix:nonFraction>'
    raw=raw.replace(old,fact).encode();m=module();before=m.BASE.extract_document(raw,'inline_primary','1')
    out=m.extract_cash_facts(raw,'inline_primary','1');assert len(out['facts'])==1;f=out['facts'][0]
    assert f['value']=='-1234000000' and f['text']=='1,234'
    assert f['attributes']['name']=='us-gaap:NetCashProvidedByUsedInOperatingActivities'
    assert f['attributes']['scale']=='6' and f['attributes']['sign']=='-'
    assert raw[slice(*f['source_span'])]==fact.encode()
    for obj in (f['context_source'],f['unit_source']):
        original=raw[slice(*obj['source_span'])];assert original.decode()==obj['xml']
        assert hashlib.sha256(original).hexdigest()==obj['fragment_sha256']
    assert f['context']=={'identifier':'1','startDate':'2024-01-01','endDate':'2024-06-30'}
    assert f['unit_source']['usd'] and f['entity_wide']
    assert m.BASE.extract_document(raw,'inline_primary','1')==before
    assert 'NetCashProvidedByUsedInOperatingActivities' not in m.BASE.SELECTED

@pytest.mark.parametrize('name,report,cik,want',[
    ('aapl_2020q3','2020-06-27','320193',('60098000000','44738000000','49481000000','41570000000','338516000000')),
    ('msft_2024q3','2024-03-31','789019',('81353000000','66100000000','58812000000','52280000000','411976000000')),
    ('f_2024q2','2024-06-30','37996',None),
])
def test_original_source_examples_and_all_original_spans(name,report,cik,want):
    raw=(REPO/'.qualification/filing-feasibility20260928/raw'/f'{name}_original.bin').read_bytes()
    m=module();r=m.qualify_document(raw,'inline_primary',cik,report)
    original=m.BASE.qualify_facts(m.BASE.extract_document(raw,'inline_primary',cik),report)
    assert {k:r[k] for k in original}==original
    if want is None:
        assert r['q_status']=='unavailable' and r['q_reasons']==['current_YTD_NI:missing_or_unreadable_selected_fact']
        return
    assert r['q_status']=='qualified'
    keys=['q_current_cfo','q_current_ni','q_prior_cfo','q_prior_ni','q_prior_fy_assets']
    assert tuple(r[k] for k in keys)==want
    values=list(map(Decimal,want));expected=((values[0]-values[1])-(values[2]-values[3]))/values[4]
    assert abs(Decimal(r['Q'])-expected)<Decimal('1e-27')
    for f in r['q_selected_facts']:
        a,b=f['source_span'];fragment=raw[a:b];assert hashlib.sha256(fragment).hexdigest()==f['fragment_sha256']
        # Independently read original nonFraction markup, without the alias decoder.
        from html.parser import HTMLParser
        class FactReader(HTMLParser):
            def __init__(self):super().__init__();self.values=[];self.attrs={}
            def handle_starttag(self,tag,attrs):
                if tag.endswith('nonfraction'):self.attrs=dict(attrs)
            def handle_data(self,data):self.values.append(data)
        reader=FactReader();reader.feed(fragment.decode());attrs=reader.attrs
        assert attrs['name']==f['concept']
        printed=Decimal(''.join(reader.values).replace(',','').strip())
        independent=printed*(Decimal(10)**int(attrs.get('scale','0')))*(-1 if attrs.get('sign')=='-' else 1)
        assert independent==Decimal(f['value'])
        for obj in [f['context_source'],f['unit_source']]:
            assert raw[slice(*obj['source_span'])].decode()==obj['xml']
            assert hashlib.sha256(raw[slice(*obj['source_span'])]).hexdigest()==obj['fragment_sha256']


def test_accession_mismatch_never_fetches_or_uses_other_original():
    import json
    m=module();root=REPO/'.qualification/filing-source20260928'
    manifest=json.loads((root/'filings/AAPL/0001193125-12-023398.json').read_text())
    bad=copy.deepcopy(manifest);bad['registry_row']['accessionNumber']='0001193125-99-999999'
    r=m.enrich_filing(bad,root,REPO)
    assert r['status']==r['q_status']=='unavailable'
    assert 'fact_source_not_original_accession_HTTP200' in r['reasons']
