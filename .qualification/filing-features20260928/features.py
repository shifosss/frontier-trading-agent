"""Original-accession quarterly financial extraction. No network or market-return access."""
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, localcontext
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import html
import re
import xml.etree.ElementTree as ET

ET_ZONE=ZoneInfo('America/New_York')
SELECTED={'NetIncomeLoss','Assets','DocumentFiscalYearFocus','DocumentFiscalPeriodFocus'}
ATTR=re.compile(rb'([\w:.-]+)\s*=\s*([\"\x27])(.*?)\2',re.S)

def attrs(raw):
    return {m[1].decode():html.unescape(m[3].decode('utf-8')) for m in ATTR.finditer(raw)}

def text_value(raw):
    return html.unescape(re.sub(rb'<[^>]*>',b'',raw).decode('utf-8')).strip()

def local(tag):
    return tag.rsplit('}',1)[-1]

def extract_document(raw, representation, cik):
    """Keep selected fact/context/unit byte spans; reject unsupported interpretations explicitly."""
    if representation not in ('inline_primary','original_instance','original_xbrl_instance'):
        return {'facts':[],'issues':['unsupported_fact_representation'],'source_sha256':sha256(raw).hexdigest()}
    root=re.search(rb'<(?:[\w.-]+:)?(?:html|xbrl)\b[^>]*>',raw,re.I)
    if not root: raise ValueError('Missing namespace-bearing document root')
    root_attrs=attrs(root[0]); namespaces={k.split(':',1)[1]:v for k,v in root_attrs.items() if k.startswith('xmlns:')}
    ns_attrs=b' '.join(m[0] for m in ATTR.finditer(root[0]) if m[1]==b'xmlns' or m[1].startswith(b'xmlns:'))
    contexts={};units={};issues=[]
    def fragment_node(fragment):
        return ET.fromstring(b'<root '+ns_attrs+b'>'+fragment+b'</root>')[0]
    def identity(m):
        return {'source_span':[m.start(),m.end()],'fragment_sha256':sha256(m[0]).hexdigest(),'xml':m[0].decode('utf-8')}
    for kind,storage in (('context',contexts),('unit',units)):
        pat=rb'<((?:[\w.-]+:)?'+kind.encode()+rb')\b[^>]*>.*?</\1\s*>'
        for m in re.finditer(pat,raw,re.S):
            node=fragment_node(m[0]); record=identity(m); key=node.get('id')
            if kind=='context':
                values={local(e.tag):(e.text or '').strip() for e in node.iter() if local(e.tag) in ('identifier','startDate','endDate','instant')}
                dimensions=[ET.tostring(e,encoding='unicode') for e in node.iter() if local(e.tag) in ('segment','scenario','explicitMember','typedMember')]
                identifiers=[e for e in node.iter() if local(e.tag)=='identifier']
                entity_ok=len(identifiers)==1 and identifiers[0].get('scheme','').lower()=='http://www.sec.gov/cik' and values.get('identifier','').isdigit() and int(values['identifier'])==int(cik)
                record.update(values=values,dimensions=dimensions,entity_ok=entity_ok)
            else:
                measures=[(e.text or '').strip() for e in node.iter() if local(e.tag)=='measure']
                q=measures[0].split(':') if len(measures)==1 else []
                record['usd']=len(q)==2 and q[1]=='USD' and namespaces.get(q[0])=='http://www.xbrl.org/2003/iso4217' and not any(local(e.tag)=='divide' for e in node.iter())
            if key in storage and record['xml']!=storage[key]['xml']:issues.append('conflicting_'+kind+'_id:'+str(key))
            else:storage[key]=record
    if representation=='inline_primary':
        pat=rb'<((?:[\w.-]+:)?(?:nonFraction|nonNumeric))\b(?=[^>]*\bname\s*=\s*[\"\x27][\w.-]+:(?:NetIncomeLoss|Assets|DocumentFiscalYearFocus|DocumentFiscalPeriodFocus)[\"\x27])([^>]*)>(.*?)</\1\s*>'
    else:
        pat=rb'<([\w.-]+:(?:NetIncomeLoss|Assets|DocumentFiscalYearFocus|DocumentFiscalPeriodFocus))\b([^>]*)>(.*?)</\1\s*>'
    facts=[]
    for m in re.finditer(pat,raw,re.S):
        a=attrs(m[2]); qname=a.get('name',m[1].decode()); parts=qname.split(':')
        if len(parts)!=2 or parts[1] not in SELECTED:continue
        prefix,name=parts; uri=namespaces.get(prefix,'')
        expected=(name in ('NetIncomeLoss','Assets') and re.fullmatch(r'https?://(?:fasb\.org|xbrl\.us)/us-gaap/[^/]+',uri)) or (name.startswith('DocumentFiscal') and re.fullmatch(r'https?://(?:xbrl\.sec\.gov|xbrl\.us)/dei/[^/]+',uri))
        if not expected:continue
        ctx=contexts.get(a.get('contextRef'));unit=units.get(a.get('unitRef'))
        content=m[3]
        for ns_prefix,ns_uri in namespaces.items():
            if ns_uri in ('http://www.xbrl.org/2013/inlineXBRL','http://www.xbrl.org/2008/inlineXBRL'):
                content=re.sub(rb'<'+re.escape(ns_prefix.encode())+rb':exclude\b[^>]*>.*?</'+re.escape(ns_prefix.encode())+rb':exclude\s*>',b'',content,flags=re.S)
        f={'concept':('us-gaap:' if name in ('NetIncomeLoss','Assets') else 'dei:')+name,'namespace':uri,'attributes':a,'text':text_value(content),'source_span':[m.start(),m.end()],'fragment_sha256':sha256(m[0]).hexdigest(),'context':ctx['values'] if ctx else {},'context_source':ctx,'unit_source':unit,'entity_wide':bool(ctx and ctx['entity_ok'] and not ctx['dimensions']),'value':None,'errors':[]}
        if not ctx:f['errors'].append('missing_context')
        if any(k.endswith(':nil') and v in ('true','1') for k,v in a.items()):f['errors'].append('nil_fact')
        if a.get('continuedAt'):f['errors'].append('continued_fact_unsupported')
        if name in ('NetIncomeLoss','Assets'):
            if not unit or not unit['usd']:f['errors'].append('non_USD_or_missing_unit')
            fmt=a.get('format',''); transform=fmt.rsplit(':',1)[-1]
            if fmt and transform not in ('numdotdecimal','num-dot-decimal','fixed-zero','zerodash'):f['errors'].append('unsupported_numeric_transform:'+fmt)
            if fmt and not namespaces.get(fmt.split(':')[0],'').startswith(('http://www.xbrl.org/inlineXBRL/transformation/','http://www.sec.gov/inlineXBRL/transformation/')):f['errors'].append('unsupported_transform_namespace')
            if a.get('sign') not in (None,'-'):f['errors'].append('unsupported_sign')
            try:
                value=Decimal(0) if transform in ('fixed-zero','zerodash') else Decimal(f['text'].replace(',','').replace('\u00a0','').replace(' ',''))
                scale=int(a.get('scale','0'))
                if not value.is_finite() or abs(scale)>20:raise ValueError('nonfinite/unsupported scale')
                value=value*(Decimal(10)**scale)*(-1 if a.get('sign')=='-' else 1)
                if not f['errors']:f['value']=format(value,'f')
            except (InvalidOperation,ValueError):f['errors'].append('unreadable_numeric_value')
        elif not f['errors']:f['value']=f['text']
        facts.append(f)
    return {'source_sha256':sha256(raw).hexdigest(),'facts':facts,'issues':issues}

def _day(value):return date.fromisoformat(value)

def _duration(ctx):return (_day(ctx['endDate'])-_day(ctx['startDate'])).days+1

def _value(rows):
    if not rows or any(f['errors'] or f['value'] is None for f in rows):raise ValueError('missing_or_unreadable_selected_fact')
    values={Decimal(f['value']) if f['concept'].startswith('us-gaap:') else f['value'] for f in rows}
    if len(values)!=1:raise ValueError('conflicting_duplicate_values')
    return rows[0]['value']

def qualify_facts(document,report_date):
    """Qualify fiscal identity and a single genuine current/prior quarter pair."""
    result={'status':'unavailable','reasons':list(document['issues']),'selected_facts':[],'u':None}
    try:
        if result['reasons']:raise ValueError('document_context_unit_conflict')
        rows=[f for f in document['facts'] if f['entity_wide']]
        fy_rows=[f for f in rows if f['concept']=='dei:DocumentFiscalYearFocus']
        fp_rows=[f for f in rows if f['concept']=='dei:DocumentFiscalPeriodFocus']
        fy=int(_value(fy_rows));fp=_value(fp_rows)
        if fp not in ('Q1','Q2','Q3'):raise ValueError('not_Q1_Q2_Q3')
        q=int(fp[1]);ctxs={(f['context'].get('startDate'),f['context'].get('endDate')) for f in fy_rows+fp_rows}
        if len(ctxs)!=1:raise ValueError('ambiguous_DEI_YTD_context')
        ys,ye=next(iter(ctxs))
        if not ys or ye!=report_date or not 84*q<=(_day(ye)-_day(ys)).days+1<=98*q:raise ValueError('invalid_fiscal_YTD_period')
        if fy not in (_day(ys).year,_day(ys).year+1) or fy not in (_day(ye).year,_day(ye).year+1):raise ValueError('fiscal_year_inconsistent_with_period')
        prior_fy=(_day(ys)-timedelta(days=1)).isoformat()
        result.update(fiscal_year=fy,fiscal_period=fp,slot=fy*3+q-1,ytd_start=ys,prior_fy_end=prior_fy)
        nis=[f for f in rows if f['concept']=='us-gaap:NetIncomeLoss' and f['unit_source'] and f['unit_source']['usd'] and 'startDate' in f['context'] and 'endDate' in f['context']]
        periods={}
        for f in nis:periods.setdefault((f['context']['startDate'],f['context']['endDate']),[]).append(f)
        current=[]
        for (s,e),fs in periods.items():
            length=(_day(e)-_day(s)).days+1
            prefix=(_day(s)-_day(ys)).days
            if e==report_date and 84<=length<=98 and ((q==1 and s==ys) or (q>1 and 84*(q-1)<=prefix<=98*(q-1))):current.append((s,e,fs))
        if len(current)!=1:raise ValueError('missing_or_ambiguous_current_quarter')
        cs,ce,cf=current[0];previous=[]
        for (s,e),fs in periods.items():
            length=(_day(e)-_day(s)).days+1
            if 84<=length<=98 and 357<=(_day(cs)-_day(s)).days<=371 and 357<=(_day(ce)-_day(e)).days<=371 and abs(length-((_day(ce)-_day(cs)).days+1))<=7:previous.append((s,e,fs))
        if len(previous)!=1:raise ValueError('missing_or_ambiguous_prior_year_quarter')
        ps,pe,pf=previous[0]
        af=[f for f in rows if f['concept']=='us-gaap:Assets' and f['context'].get('instant')==prior_fy and f['unit_source'] and f['unit_source']['usd']]
        cv,pv,av=_value(cf),_value(pf),_value(af)
        if Decimal(av)<=0:raise ValueError('nonpositive_prior_fiscal_assets')
        with localcontext() as precision:
            precision.prec=40;u=(Decimal(cv)-Decimal(pv))/Decimal(av)
        result.update(status='qualified',current_ni=cv,prior_ni=pv,prior_fy_assets=av,current_start=cs,current_end=ce,prior_start=ps,prior_end=pe,u=str(u),selected_facts=fy_rows+fp_rows+cf+pf+af)
    except (ValueError,KeyError,InvalidOperation) as error:result['reasons'].append(str(error))
    return result

def event_clock(acceptance_et,filing_date,calendar):
    accepted=datetime.fromisoformat(acceptance_et)
    if accepted.tzinfo is None:raise ValueError('Acceptance timezone is missing')
    d=max(accepted.astimezone(ET_ZONE).date(),_day(filing_date))
    floor=datetime.combine(d+timedelta(days=1),time(1),ET_ZONE)
    result={'availability_floor':floor.isoformat(),'decision_time':None,'entry_time':None,'exit_time':None,'entry_session':None,'exit_session':None,'execution_status':'calendar_unavailable'}
    if calendar and floor.date()<_day(calendar[0]['session']):
        result['execution_status']='calendar_starts_after_availability';return result
    if calendar:result['execution_status']='entry_outside_calendar'
    for i,row in enumerate(calendar):
        decision=datetime.combine(_day(row['session']),time(9),ET_ZONE)
        if decision>=floor:
            result.update(decision_time=decision.isoformat(),entry_time=row['close'],entry_session=row['session'],execution_status='exit_outside_calendar')
            if i+5<len(calendar):result.update(exit_time=calendar[i+5]['close'],exit_session=calendar[i+5]['session'],execution_status='qualified')
            return result
    return result

def qualify_filing(manifest,source_root,repo_root):
    """Only committed captured files are inputs; source failures remain records."""
    row=manifest['registry_row'];issuer=manifest['issuer']
    result={'symbol':issuer['symbol'],'cik':issuer['cik'],'accession':row['accessionNumber'],'report_date':row.get('reportDate'),'filing_date':row.get('filingDate'),'registry_acceptance_utc':row.get('acceptanceDateTime'),'status':'unavailable','reasons':[],'u':None}
    try:
        if row.get('form')!='10-Q':raise ValueError('not_original_10Q')
        if manifest.get('status')!='captured':raise ValueError('source_capture_unavailable:'+str(manifest.get('error')))
        clock=manifest.get('clock',{})
        if not clock.get('timestamp_sources_consistent') or clock.get('issues'):raise ValueError('unqualified_source_clock')
        api=datetime.fromisoformat(row['acceptanceDateTime'].replace('Z','+00:00'))
        if api.tzinfo is None:raise ValueError('unverified_API_timezone')
        accepted=api.astimezone(ET_ZONE)
        if accepted.strftime('%Y-%m-%d %H:%M:%S')!=clock['index_accepted_local'] or accepted.strftime('%Y%m%d%H%M%S')!=clock['header_accepted'] or row['filingDate']!=clock['filing_date']:raise ValueError('clock_values_do_not_reconcile')
        sources=manifest.get('fact_sources',[])
        if len(sources)!=1:raise ValueError('not_exactly_one_original_fact_source')
        source=sources[0]
        accession_prefix='https://www.sec.gov/Archives/edgar/data/'+str(int(issuer['cik']))+'/'+row['accessionNumber'].replace('-','')+'/'
        if not source['url'].startswith(accession_prefix) or source.get('status')!=200:raise ValueError('fact_source_not_original_accession_HTTP200')
        p=Path(repo_root)/source['path'] if source['path'].startswith('.qualification/') else Path(source_root)/source['path']
        raw=p.read_bytes()
        if sha256(raw).hexdigest()!=source['sha256']:raise ValueError('source_hash_changed')
        doc=extract_document(raw,manifest['fact_representation'],issuer['cik'])
        result.update(qualify_facts(doc,row['reportDate']))
        result.update(acceptance_et=accepted.isoformat(),source_path=str(p),source_sha256=source['sha256'],source_url=source['url'],representation=manifest['fact_representation'],all_facts=doc['facts'],**event_clock(accepted.isoformat(),row['filingDate'],[]))
    except (ValueError,KeyError,OSError,ET.ParseError) as error:result['reasons'].append(str(error))
    return result

def build_features(records,calendar):
    """Scheduled-slot history never skips missing originals or later rewrites."""
    ordered=sorted(records,key=lambda r:(r['filing_date'],r.get('registry_acceptance_utc') or r.get('acceptance_et',''),r['accession']))
    first={};out=[]
    def period_key(r):return (r['symbol'],r['report_date'] or ('unknown',r['accession']))
    for r in ordered:
        first.setdefault(period_key(r),r)
    for r in ordered:
        result=dict(r,feature_status='unavailable',feature_reasons=[],S=None,history_accessions=[])
        if first[period_key(r)] is not r:
            result.update(feature_status='duplicate_original',feature_reasons=['first_original_preserved']);out.append(result);continue
        try:
            if r['status']!='qualified':raise ValueError('current_input_unavailable')
            if calendar:result.update(event_clock(r['acceptance_et'],r['filing_date'],calendar))
            cutoff=datetime.fromisoformat(result.get('decision_time') or r['availability_floor'])
            # Future metadata must not retroactively change eligibility of this decision.
            known=[];slots={}
            for h in first.values():
                if h['symbol']!=r['symbol']:continue
                floor=h.get('availability_floor')
                observed=datetime.fromisoformat(floor) if floor else datetime.combine(_day(h['filing_date'])+timedelta(days=1),time(1),ET_ZONE)
                if observed<=cutoff:
                    known.append(h)
                    if h.get('slot') is not None:slots.setdefault(h['slot'],[]).append(h)
            if len(slots.get(r['slot'],[]))!=1:raise ValueError('ambiguous_fiscal_slot')
            history=[]
            for n in range(r['slot']-8,r['slot']):
                found=slots.get(n,[])
                if len(found)!=1:raise ValueError('missing_or_ambiguous_scheduled_slot:'+str(n))
                history.append(found[0])
            if any(h['status']!='qualified' or not h.get('availability_floor') for h in history):raise ValueError('prior_input_unavailable_or_not_yet_public')
            if any(h['report_date']>=r['report_date'] for h in history):raise ValueError('nonchronological_fiscal_history')
            start=history[0]['report_date'];first_history_date=min(h['filing_date'] for h in history)
            if any(h.get('slot') is None and ((not h.get('report_date') and h['filing_date']>=first_history_date) or (h.get('report_date') and start<=h['report_date']<r['report_date'])) for h in known):raise ValueError('unresolved_intervening_report')
            with localcontext() as precision:
                precision.prec=40;values=[Decimal(h['u']) for h in history];mean=sum(values)/8;variance=sum((v-mean)**2 for v in values)/7
                if variance==0:raise ValueError('zero_prior_sample_variance')
                sd=variance.sqrt();score=Decimal(r['u'])/sd
            result.update(feature_status='qualified',S=str(score),prior_sample_sd=str(sd),history_accessions=[h['accession'] for h in history],history_u=[h['u'] for h in history],selected=score>=1)
        except (ValueError,KeyError,InvalidOperation) as error:result['feature_reasons'].append(str(error))
        out.append(result)
    return out
