"""Same-original cash-backing change; frozen S parser and history remain unchanged."""
from datetime import date
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from pathlib import Path
import importlib.util
import re

REPO=Path(__file__).resolve().parents[3]
BASE_PATH=REPO/'.qualification/filing-features20260928/features.py'
BASE_SHA256='991260b80547c03c873c0d5bf62c57d86bf3fc1f5c0df0c192a7b4cc1fcc372f'
if sha256(BASE_PATH.read_bytes()).hexdigest()!=BASE_SHA256:
    raise ValueError('Frozen original S parser changed')
_spec=importlib.util.spec_from_file_location('original_filing_parser_for_cash_backing',BASE_PATH)
BASE=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(BASE)
CFO='NetCashProvidedByUsedInOperatingActivities'
CFO_CONCEPT='us-gaap:'+CFO
NI_CONCEPT='us-gaap:NetIncomeLoss'


def extract_cash_facts(raw,representation,cik):
    """Decode exact CFO originals through local aliases; restore original evidence.

    Appending aliases leaves every original context/unit byte offset intact.
    Only appended decoder output is taken; original NI facts are never renamed.
    No preserved source, global parser constant, or financial concept is changed.
    """
    concept=CFO.encode()
    if representation=='inline_primary':
        pattern=rb'<((?:[\w.-]+:)?nonFraction)\b(?=[^>]*\bname\s*=\s*[\x22\x27][\w.-]+:'+concept+rb'[\x22\x27])([^>]*)>(.*?)</\1\s*>'
    elif representation in ('original_instance','original_xbrl_instance'):
        pattern=rb'<([\w.-]+:'+concept+rb')\b([^>]*)>(.*?)</\1\s*>'
    else:
        return {'facts':[],'issues':['unsupported_fact_representation']}
    aliases=[];originals={};offset=len(raw)
    for match in re.finditer(pattern,raw,re.S):
        tag,attributes,content=match[1],match[2],match[3]
        if representation=='inline_primary':
            attributes=re.sub(rb'(\bname\s*=\s*[\x22\x27][\w.-]+:)'+concept+rb'(?=[\x22\x27])',rb'\1NetIncomeLoss',attributes,count=1)
        else:
            tag=tag.rsplit(b':',1)[0]+b':NetIncomeLoss'
        alias=b'\n<'+tag+attributes+b'>'+content+b'</'+tag+b'>'
        originals[offset+1]=match
        aliases.append(alias);offset+=len(alias)
    if not aliases:return {'facts':[],'issues':[]}
    decoded=BASE.extract_document(raw+b''.join(aliases),representation,cik)
    facts=[]
    for fact in decoded['facts']:
        start=fact['source_span'][0]
        if start not in originals:continue
        original=originals[start]
        restored=dict(fact,concept=CFO_CONCEPT,attributes=BASE.attrs(original[2]),
                      source_span=[original.start(),original.end()],fragment_sha256=sha256(original[0]).hexdigest(),
                      decoder='frozen_numeric_decoder_local_CFO_alias',decoder_sha256=BASE_SHA256)
        facts.append(restored)
    return {'facts':facts,'issues':decoded['issues']}


def qualify_cash_backing(document,financial):
    """Require unique matching original current and seasonal prior YTD periods."""
    result={'q_status':'unavailable','Q':None,'q_reasons':[],'q_selected_facts':[]}
    try:
        if financial['status']!='qualified':raise ValueError('original_S_financial_inputs_unavailable')
        if document['issues']:raise ValueError('document_context_unit_conflict')
        q=int(financial['fiscal_period'][1]);current=(financial['ytd_start'],financial['current_end'])
        period_facts={CFO_CONCEPT:{},NI_CONCEPT:{}}
        for fact in document['facts']:
            if fact['concept'] not in period_facts or not fact['entity_wide']:continue
            ctx=fact['context'];unit=fact.get('unit_source')
            if not unit or not unit['usd'] or 'startDate' not in ctx or 'endDate' not in ctx:continue
            period=(ctx['startDate'],ctx['endDate'])
            period_facts[fact['concept']].setdefault(period,[]).append(fact)
        def value(concept,period,role):
            rows=period_facts[concept].get(period,[])
            try:return BASE._value(rows),rows
            except ValueError as error:raise ValueError(role+':'+str(error)) from error
        current_cfo,cf=value(CFO_CONCEPT,current,'current_YTD_CFO')
        current_ni,cn=value(NI_CONCEPT,current,'current_YTD_NI')
        cs,ce=map(date.fromisoformat,current);duration=(ce-cs).days+1
        if not 84*q<=duration<=98*q:raise ValueError('invalid_current_YTD_duration')
        common=period_facts[CFO_CONCEPT].keys() & period_facts[NI_CONCEPT].keys()
        prior=[]
        for period in common:
            ps,pe=map(date.fromisoformat,period);days=(pe-ps).days+1
            if 84*q<=days<=98*q and 357<=(cs-ps).days<=371 and 357<=(ce-pe).days<=371 and abs(duration-days)<=7:
                prior.append(period)
        if len(prior)!=1:raise ValueError('missing_or_ambiguous_prior_YTD_period')
        previous=prior[0]
        prior_cfo,pf=value(CFO_CONCEPT,previous,'prior_YTD_CFO')
        prior_ni,pn=value(NI_CONCEPT,previous,'prior_YTD_NI')
        assets=financial['prior_fy_assets']
        with localcontext() as precision:
            precision.prec=40
            if Decimal(assets)<=0:raise ValueError('nonpositive_prior_FY_assets')
            score=((Decimal(current_cfo)-Decimal(current_ni))-(Decimal(prior_cfo)-Decimal(prior_ni)))/Decimal(assets)
        af=[f for f in financial['selected_facts'] if f['concept']=='us-gaap:Assets']
        result.update(q_status='qualified',Q=str(score),q_current_cfo=current_cfo,q_current_ni=current_ni,
                      q_prior_cfo=prior_cfo,q_prior_ni=prior_ni,q_prior_fy_assets=assets,
                      q_current_start=current[0],q_current_end=current[1],q_prior_start=previous[0],q_prior_end=previous[1],
                      q_selected_facts=cf+cn+pf+pn+af)
    except (ValueError,KeyError,InvalidOperation) as error:result['q_reasons'].append(str(error))
    return result


def qualify_document(raw,representation,cik,report_date):
    """Offline fixture API; original S financial extraction is not extended."""
    doc=BASE.extract_document(raw,representation,cik)
    financial=BASE.qualify_facts(doc,report_date)
    cfo=extract_cash_facts(raw,representation,cik)
    combined={'facts':doc['facts']+cfo['facts'],'issues':doc['issues']+cfo['issues']}
    return {**financial,**qualify_cash_backing(combined,financial),'q_all_facts':cfo['facts']}


def enrich_record(record):
    """Append Q to a retained frozen qualified record; no source/date substitutions."""
    result=dict(record)
    try:
        if record['status']!='qualified':
            result.update(qualify_cash_backing({'facts':[],'issues':[]},record));return result
        raw=Path(record['source_path']).read_bytes()
        if sha256(raw).hexdigest()!=record['source_sha256']:raise ValueError('original_source_hash_changed')
        cfo=extract_cash_facts(raw,record['representation'],record['cik'])
        combined={'facts':record['all_facts']+cfo['facts'],'issues':cfo['issues']}
        result.update(qualify_cash_backing(combined,record),q_all_facts=cfo['facts'])
    except (ValueError,KeyError,OSError,BASE.ET.ParseError) as error:
        result.update(q_status='unavailable',Q=None,q_reasons=[str(error)],q_selected_facts=[])
    return result


def enrich_filing(manifest,source_root,repo_root):
    return enrich_record(BASE.qualify_filing(manifest,source_root,repo_root))


def build_features(records,calendar):
    """Frozen S/history/clock first; Q missingness does not rewrite that population."""
    results=BASE.build_features(records,calendar)
    for result in results:
        reasons=[]
        for field in ('feature_status','q_status','execution_status'):
            if result.get(field)!='qualified':reasons.append(field+':'+str(result.get(field,'unavailable')))
        result['joint_feature_status']='unavailable' if reasons else 'qualified'
        result['joint_feature_reasons']=reasons
    return results
