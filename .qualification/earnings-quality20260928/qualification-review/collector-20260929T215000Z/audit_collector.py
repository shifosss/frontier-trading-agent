from pathlib import Path
from datetime import date,datetime,time,timedelta,timezone
from zoneinfo import ZoneInfo
from fractions import Fraction
from decimal import Decimal,localcontext
from collections import Counter,defaultdict
from bisect import bisect_left
import hashlib,html,json,re

R=Path.cwd().resolve(); ROOT=R/'.qualification/earnings-quality20260928'; A=ROOT/'qualification/attempts/b1258d8e28124eea8ffdd227f6ac71cf'
OUT=ROOT/'qualification-review/collector-20260929T215000Z'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
old=read(ROOT/'qualification-review/terminal-20260929T213900Z/terminal-review.json')
records=read(A/'records.json');events=read(A/'events.json');summary=read(A/'summary.json')
inputs=read(A/'source-inputs.json')['files'];issuer_status=read(A/'issuer-status.json')
registry=read(ROOT/'source/registry.json');calendar=read(R/'.qualification/post-filing-strategy20260928/calendar.json')['sessions']
check_counts=Counter();issues=[];stats=Counter()
def check(label,condition,identity=''):
    check_counts[label]+=1
    if not condition:issues.append({'check':label,'identity':identity})
known=dict(old['source_files']);known.update({p:v['sha256'] for p,v in old['raw_identities'].items()})
for p,digest in inputs.items():
    if p in known:
        check('bound prior verified source identity',digest==known[p],p)
    elif digest is None:
        check('declared missing source still missing',not Path(p).exists(),p)
    else:
        check('additional declared source identity',sha(p)==digest,p)
for name,digest in summary['files'].items():check('collector output identity',sha(A/name)==digest,name)
expected=[(x['issuer']['symbol'],row['accessionNumber']) for x in registry['issuers'] for row in x['discovery']['original_accessions']]
key=lambda x:(x['symbol'],x['accession'])
record_map={key(x):x for x in records};event_map={key(x):x for x in events}
check('all originals retained',len(records)==len(events)==len(record_map)==len(event_map)==4057 and list(record_map)==expected and set(event_map)==set(record_map))
check('all issuer denominators retained',len(issuer_status)==100 and [x['issuer'] for x in issuer_status]==[x['issuer'] for x in registry['issuers']] and sum(x['retained_original_rows'] for x in issuer_status)==4057)
ET=ZoneInfo('America/New_York');dates=[date.fromisoformat(x['session']) for x in calendar]
decisions=[datetime.combine(d,time(9),ET) for d in dates]
clock_fields={'availability_floor','decision_time','entry_time','exit_time','entry_session','exit_session','execution_status'}
big={'all_facts','selected_facts','q_all_facts','q_selected_facts'}
attrs_pattern=re.compile(rb'([\w:.-]+)\s*=\s*(["\x27])(.*?)\2',re.S)
def attrs(raw):return {m[1].decode():html.unescape(m[3].decode()) for m in attrs_pattern.finditer(raw)}
def piece(f,span):f.seek(span[0]);return f.read(span[1]-span[0])
def amount(fact,fragment,namespaces):
    opening=fragment.split(b'>',1)[0];a=attrs(opening);tag=re.match(rb'<([\w:.-]+)',opening)[1].decode()
    qname=a.get('name',tag);prefix,local=qname.split(':',1)
    check('selected concept namespace',namespaces.get(prefix)==fact['namespace'] and local==fact['concept'].split(':',1)[1],fact['concept'])
    check('original fact attributes',a==fact['attributes'],fact['concept'])
    content=fragment[fragment.find(b'>')+1:fragment.rfind(b'</')]
    content=re.sub(rb'<[\w.-]+:exclude\b[^>]*>.*?</[\w.-]+:exclude\s*>',b'',content,flags=re.S)
    decoded=html.unescape(re.sub(rb'<[^>]*>',b'',content).decode()).strip()
    check('original fact text',decoded==fact['text'],fact['concept'])
    if fact['concept'].startswith('dei:'):return
    form=a.get('format','').split(':')[-1]
    value=Fraction(0) if form in ['fixed-zero','zerodash'] else Fraction(decoded.replace(',','').replace('\u00a0','').replace(' ',''))
    value*=Fraction(10)**int(a.get('scale','0'))
    if a.get('sign')=='-':value=-value
    check('exact source numeric decoding',value==Fraction(fact['value']),fact['concept'])
for rec in records:
    ident=rec['symbol']+'/'+rec['accession'];event=event_map[key(rec)]
    check('original fields preserved',all(event.get(k)==v for k,v in rec.items() if k not in big|clock_fields),ident)
    for field in ['q_status','Q','q_reasons','industry_status','industry_sic','industry_header_source','source_input']:
        check('feature evidence retained',event.get(field)==rec.get(field),ident+':'+field)
    check('manifest source bound',inputs.get(rec['source_input']['manifest_path'])==rec['source_input']['manifest_sha256'],ident)
    if rec['source_input']['source_status']!='captured':
        check('unavailable original never qualified',rec['status']=='unavailable' and event['strategy_source_status']!='qualified',ident)
    if rec['status']=='qualified':
        with localcontext() as c:
            c.prec=40
            f=(Fraction(rec['current_ni'])-Fraction(rec['prior_ni']))/Fraction(rec['prior_fy_assets'])
            check('S primitive exact rational',Decimal(rec['u'])==Decimal(f.numerator)/Decimal(f.denominator),ident)
        stats['qualified_u']+=1
        accepted=datetime.fromisoformat(rec['registry_acceptance_utc'].replace('Z','+00:00')).astimezone(ET)
        floor=datetime.combine(max(accepted.date(),date.fromisoformat(rec['filing_date']))+timedelta(days=1),time(1),ET)
        i=bisect_left(decisions,floor)
        check('independent causal decision and five-session clock',event['availability_floor']==floor.isoformat() and event['decision_time']==decisions[i].isoformat() and event['entry_session']==calendar[i]['session'] and event['exit_session']==calendar[i+5]['session'] and event['entry_time']==calendar[i]['close'] and event['exit_time']==calendar[i+5]['close'],ident)
        stats['event_clocks']+=1
        check('financial original body bound',inputs.get(rec['source_path'])==rec['source_sha256']==known.get(rec['source_path']),ident)
        with Path(rec['source_path']).open('rb') as f:
            head=f.read(4096);root=re.search(rb'<(?:[\w.-]+:)?(?:html|xbrl)\b[^>]*>',head,re.I)
            while root is None and len(head)<65536:
                head+=f.read(4096);root=re.search(rb'<(?:[\w.-]+:)?(?:html|xbrl)\b[^>]*>',head,re.I)
            check('namespace-bearing original root located',root is not None,ident)
            namespace={k.split(':',1)[1]:v for k,v in attrs(root[0]).items() if k.startswith('xmlns:')}
            for fact in rec.get('selected_facts',[])+rec.get('q_selected_facts',[]):
                fragment=piece(f,fact['source_span']);check('original fact span hash',hashlib.sha256(fragment).hexdigest()==fact['fragment_sha256'],ident)
                amount(fact,fragment,namespace);stats['selected_fact_observations']+=1
                for field in ['context_source','unit_source']:
                    source=fact.get(field)
                    if source:
                        body=piece(f,source['source_span'])
                        check('context/unit original source span',hashlib.sha256(body).hexdigest()==source['fragment_sha256'] and body.decode()==source['xml'],ident)
                        stats['context_unit_spans']+=1
                        if field=='context_source':
                            check('entity-wide exact original context',source['entity_ok'] and not source['dimensions'] and fact['entity_wide'] and int(source['values']['identifier'])==int(rec['cik']) and fact['context']==source['values'],ident)
                            check('no original dimensional context',re.search(rb'<(?:[\w.-]+:)?(?:segment|scenario|explicitMember|typedMember)\b',body) is None,ident)
                        else:
                            measures=re.findall(rb'<(?:[\w.-]+:)?measure\b[^>]*>(.*?)</',body,re.S)
                            check('original USD unit',source['usd'] and len(measures)==1 and measures[0].strip().split(b':')[-1]==b'USD' and namespace.get(measures[0].strip().split(b':')[0].decode())=='http://www.xbrl.org/2003/iso4217' and b'divide' not in body,ident)
    if rec['q_status']=='qualified':
        q=int(rec['fiscal_period'][1]);cs=date.fromisoformat(rec['q_current_start']);ce=date.fromisoformat(rec['q_current_end']);ps=date.fromisoformat(rec['q_prior_start']);pe=date.fromisoformat(rec['q_prior_end'])
        check('original Q YTD durations',84*q<=(ce-cs).days+1<=98*q and 84*q<=(pe-ps).days+1<=98*q and 357<=(cs-ps).days<=371 and 357<=(ce-pe).days<=371 and abs((ce-cs).days-(pe-ps).days)<=7,ident)
        check('Q original S anchors',rec['q_current_start']==rec['ytd_start'] and rec['q_current_end']==rec['current_end'] and rec['q_prior_fy_assets']==rec['prior_fy_assets'],ident)
        for concept,start,end,value in [('NetCashProvidedByUsedInOperatingActivities',rec['q_current_start'],rec['q_current_end'],rec['q_current_cfo']),('NetIncomeLoss',rec['q_current_start'],rec['q_current_end'],rec['q_current_ni']),('NetCashProvidedByUsedInOperatingActivities',rec['q_prior_start'],rec['q_prior_end'],rec['q_prior_cfo']),('NetIncomeLoss',rec['q_prior_start'],rec['q_prior_end'],rec['q_prior_ni'])]:
            selected=[x for x in rec['q_selected_facts'] if x['concept']=='us-gaap:'+concept and x['context'].get('startDate')==start and x['context'].get('endDate')==end]
            check('exact original Q concept/period/value',bool(selected) and all(Fraction(x['value'])==Fraction(value) and x['entity_wide'] and not x['errors'] for x in selected),ident)
        with localcontext() as c:
            c.prec=40
            f=((Fraction(rec['q_current_cfo'])-Fraction(rec['q_current_ni']))-(Fraction(rec['q_prior_cfo'])-Fraction(rec['q_prior_ni'])))/Fraction(rec['q_prior_fy_assets'])
            check('Q exact rational',Decimal(rec['Q'])==Decimal(f.numerator)/Decimal(f.denominator),ident)
        stats['qualified_Q']+=1
    if rec['industry_status']=='qualified':
        meta=rec['industry_header_source'];check('header source identity bound',inputs.get(meta['path'])==meta['sha256']==known.get(meta['path']),ident)
        raw=Path(meta['path']).read_bytes()
        for proof in rec['industry_evidence']:
            frag=raw[slice(*proof['span'])]
            check('header evidence original bytes',hashlib.sha256(frag).hexdigest()==proof['sha256'] and frag.decode('utf-8',errors='replace')==proof['raw_text'],ident)
            stats['header_spans']+=1
        companies=[]
        for filer in re.findall(rb'<FILER>(.*?)</FILER>',raw,re.S):
            for company in re.findall(rb'<COMPANY-DATA>(.*?)</COMPANY-DATA>',filer,re.S):
                ciks=re.findall(rb'<CIK>\s*([0-9]+)',company)
                if ciks and {int(x) for x in ciks}=={int(rec['cik'])}:companies.append(company)
        check('exact original target FILER',len(companies)==1,ident)
        sic={int(x) for x in re.findall(rb'<ASSIGNED-SIC>\s*([0-9]+)',companies[0])}
        check('original header SIC range and value',sic=={int(rec['industry_sic'])} and (100<=int(rec['industry_sic'])<=5999 or 7000<=int(rec['industry_sic'])<=8999),ident)
        stats['qualified_header']+=1
    check('joint strategy gate', (event['strategy_source_status']=='qualified')==(event['joint_feature_status']=='qualified' and event['industry_status']=='qualified'),ident)
    if event['feature_status']=='qualified':
        history=[record_map[(rec['symbol'],acc)] for acc in event['history_accessions']]
        check('unchanged eight scheduled historical slots',len(history)==8 and [x['slot'] for x in history]==list(range(rec['slot']-8,rec['slot'])) and [x['u'] for x in history]==event['history_u'],ident)
        check('prior financial evidence available before decision',all(x['status']=='qualified' and x['report_date']<rec['report_date'] and datetime.fromisoformat(x['availability_floor'])<=datetime.fromisoformat(event['decision_time']) for x in history),ident)
        with localcontext() as c:
            c.prec=40;v=[Decimal(x['u']) for x in history];mean=sum(v)/8;sd=(sum((x-mean)**2 for x in v)/7).sqrt();score=Decimal(rec['u'])/sd
            check('independent S history and threshold',str(sd)==event['prior_sample_sd'] and str(score)==event['S'] and event['selected']==(score>=1),ident)
        stats['qualified_S']+=1
        if any(x['q_status']!='qualified' for x in history):stats['S_histories_preserving_prior_Q_unavailable']+=1
        if any(x['industry_status']!='qualified' for x in history):stats['S_histories_preserving_prior_industry_unavailable']+=1
counts=lambda rows,k:dict(Counter(x.get(k,'unavailable') for x in rows))
for field in ['q_status','industry_status']:check('summary '+field,counts(records,field)==summary[field])
check('summary financial_status',counts(records,'status')==summary['financial_status'])
for field in ['feature_status','joint_feature_status','strategy_source_status','execution_status']:check('summary '+field,counts(events,field)==summary[field])
groups=defaultdict(list)
for e in events:
    if e['strategy_source_status']=='qualified':groups[(e['symbol'],e['decision_time'])].append(e['accession'])
collisions=[{'symbol':s,'decision':t,'accessions':v} for (s,t),v in groups.items() if len(v)>1]
check('no strategy-source same-decision collision',not collisions)
year_qualified=dict(sorted(Counter(e['decision_time'][:4] for e in events if e['strategy_source_status']=='qualified').items()))
for name,digest in summary['files'].items():check('final collector output stability',sha(A/name)==digest,name)
report={'schema':1,'at_utc':datetime.now(timezone.utc).isoformat(),'collector_attempt':str(A),'summary_sha256':sha(A/'summary.json'),'source_terminal_review_sha256':sha(ROOT/'qualification-review/terminal-20260929T213900Z/terminal-review.json'),'source_terminal_reconciliation_sha256':sha(ROOT/'qualification-review/terminal-20260929T213900Z/terminal-review-reconciliation.json'),'material_blockers':issues,'checked_counts':dict(check_counts),'stats':dict(stats),'qualified_events_by_decision_year':year_qualified,'qualified_collisions':collisions,'source_binding_count':len(inputs),'original_records':len(records),'eligible_source_events':sum(e['strategy_source_status']=='qualified' for e in events),'no_prices_models_or_accounts_read':True,'source_mutations':0,'network_requests':0,'qualification_to_economic_run_gate_clear':not issues}
OUT.mkdir(parents=True,exist_ok=True)
p=OUT/'collector-review.json'
with p.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
print(json.dumps({'path':str(p),'sha256':sha(p),'material_blockers':issues,'total_checks':sum(check_counts.values()),'stats':stats,'qualified_events_by_decision_year':year_qualified},indent=2))
