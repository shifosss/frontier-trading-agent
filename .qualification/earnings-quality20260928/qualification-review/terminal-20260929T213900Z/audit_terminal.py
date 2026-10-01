from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
import hashlib,json,re,sqlite3

REPO=Path.cwd().resolve()
S=REPO/'.qualification/earnings-quality20260928/source'
OUT=REPO/'.qualification/earnings-quality20260928/qualification-review/terminal-20260929T213900Z'
def read(p): return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def pathof(meta):
    return (REPO if meta.get('reused') or meta['path'].startswith('.qualification/') else S)/meta['path']
checks=[]; files={}; raw={}; blockers=[]
def check(label,condition):
    checks.append({'check':label,'passed':bool(condition)})
    if not condition: blockers.append(label)
def bind(p,expected=None):
    p=Path(p).resolve(); actual=sha(p)
    if expected is not None: check('identity:'+str(p.relative_to(REPO)),actual==expected)
    if str(p) in files: check('stable:'+str(p.relative_to(REPO)),files[str(p)]==actual)
    files[str(p)]=actual
    return actual
def bindraw(meta):
    p=pathof(meta).resolve()
    if str(p) not in raw:
        with p.open('rb') as f: digest=hashlib.file_digest(f,'sha256').hexdigest()
        raw[str(p)]={'sha256':digest,'bytes':p.stat().st_size}
    v=raw[str(p)]
    if v['sha256']!=meta['sha256'] or (meta.get('bytes') is not None and meta['bytes']!=v['bytes']):
        blockers.append('raw source hash or length mismatch: '+str(p))
    return p
req=read(S/'request.json'); impl=read(S/'implementation.json'); reg=read(S/'registry.json'); done=read(S/'completion.json'); cohort=read(S/'cohort.json')
check('request unchanged',bind(S/'request.json')=='2d688da497c4c58a8701db66083d88b5f07aff28a436a65dcb9395bdcb26dfe1')
check('implementation unchanged',bind(S/'implementation.json')=='3570a2d8067ea9031ec84d4eeb0cb6e17530039402b60a75d2fdd4bc4e4b303c')
check('cohort unchanged',bind(S/'cohort.json')=='41a26bef5fa3c449a2f627c57e9da34aaeabdf551506c31f907e279339d0c76a')
for name,expected in impl['files'].items(): bind(S/name,expected)
for name,expected in impl['external_files'].items(): bind(REPO/name,expected)
for name in ['registry.json','completion.json','progress.jsonl','requests.jsonl','finalization-definition.json','finalization-completion.json']:
    bind(S/name)
check('no unresolved source STOP/status',not (S/'STOP.json').exists() and not (S/'status.json').exists())
check('terminal incomplete status is explicit',done['status']=='incomplete')
ordered=lambda rows:[(x['symbol'],x['cik']) for x in rows]
members=ordered(req['issuers'])
check('exact ordered100 unique symbols and CIKs',len(members)==100 and len(set(members))==100 and len({x[0] for x in members})==100 and len({x[1] for x in members})==100 and members==ordered(cohort['selected'])==ordered([x['issuer'] for x in reg['issuers']]))
check('registry binds request',reg['request_sha256']==sha(S/'request.json'))
locks=[]; lock_status=[]
try:
    for p in [S.parent/'sec-source.lock.sqlite',S/'capture.lock.sqlite']:
        before=sha(p); db=sqlite3.connect(p.as_uri()+'?mode=ro',uri=True,timeout=0)
        db.execute('BEGIN'); db.execute('SELECT count(*) FROM sqlite_master').fetchone()
        locks.append((db,p,before)); lock_status.append({'path':str(p.relative_to(REPO)),'readonly_shared_transaction_acquired':True,'sha256':before})
    manifests=[]; years=Counter(); by_issuer=[]; coverage=[]; clocks=[]; failures=[]; manifest_paths=set(); discovery_source_count=0
    for item in reg['issuers']:
        issuer=item['issuer']; d=item['discovery']; original=d['original_accessions']
        for meta in d['sources']: bindraw(meta); discovery_source_count+=1
        # Independently rebuild row membership from original root/history JSON column tables.
        from_raw=[]
        for i,meta in enumerate(d['sources']):
            data=read(pathof(meta))
            table=data['filings']['recent'] if i==0 else data
            if i==0:
                check('root CIK/symbol '+issuer['symbol'],str(data['cik']).zfill(10)==issuer['cik'] and issuer['symbol'] in data['tickers'])
                expected_history=['https://data.sec.gov/submissions/'+f['name'] for f in data['filings']['files'] if f['filingFrom']<=req['filed_through'] and f['filingTo']>=req['filed_from']]
                check('all declared overlapping history '+issuer['symbol'],expected_history==[x['url'] for x in d['sources'][1:]])
            lengths={len(v) for v in table.values() if isinstance(v,list)}
            check('column lengths '+issuer['symbol']+' '+str(i),len(lengths)==1)
            from_raw.extend({k:v[n] for k,v in table.items() if isinstance(v,list)} for n in range(len(table['accessionNumber'])))
        check('all discovery rows retained '+issuer['symbol'],from_raw==d['rows'])
        unique={}
        for row in from_raw:
            if row['accessionNumber'] in unique:check('duplicate original metadata agrees '+issuer['symbol'],unique[row['accessionNumber']]==row)
            unique.setdefault(row['accessionNumber'],row)
        reconstructed=[x for x in unique.values() if x.get('form')=='10-Q' and req['filed_from']<=x.get('filingDate','')<=req['filed_through']]
        reconstructed.sort(key=lambda x:(x['filingDate'],x.get('acceptanceDateTime') or '',x['accessionNumber']))
        check('original membership '+issuer['symbol'],reconstructed==original and len(original)<=60)
        check('amendments retained '+issuer['symbol'],[x for x in unique.values() if x.get('form')=='10-Q/A']==d['amendment_metadata'])
        counts={str(y):sum(x['filingDate'].startswith(str(y)+'-') for x in original) for y in range(2012,2026)}
        expected_cov=[{'filed_year':y,'observed_originals':n,'reason':'fewer than3 observed; fiscal-quarter completeness not inferred'} for y,n in counts.items() if n<3]
        check('year denominators and coverage '+issuer['symbol'],counts==d['filed_year_counts'] and expected_cov==d['coverage_review_needed'])
        if expected_cov:coverage.append({'issuer':issuer,'items':expected_cov})
        issuer_status=Counter(); issuer_clocks=0; reasons=Counter()
        for row in original:
            p=S/'filings'/issuer['symbol']/(row['accessionNumber']+'.json'); manifest_paths.add(p.resolve())
            m=read(p); bind(p); manifests.append(m); years[row['filingDate'][:4]]+=1
            check('manifest membership '+issuer['symbol']+'/'+row['accessionNumber'],m['issuer']==issuer and m['registry_row']==row)
            issuer_status[m['status']]+=1
            for meta in m.get('sources',[])+m.get('fact_sources',[]):bindraw(meta)
            clock=m.get('clock')
            if clock:
                headers=[x for x in m['sources'] if x['url'].endswith('.hdr.sgml')]
                check('one original header for saved clock '+row['accessionNumber'],len(headers)==1)
                if len(headers)==1:
                    text=pathof(headers[0]).read_text(encoding='utf-8')
                    field=lambda name:next(iter(re.findall('<'+name+r'>\s*([^\r\n<]+)',text)),None)
                    acceptance=field('ACCEPTANCE-DATETIME')
                    check('clock raw fields '+row['accessionNumber'],acceptance==clock['header_accepted'] and row['acceptanceDateTime']==clock['api_acceptance'] and m['index']['accepted_local']==clock['index_accepted_local'])
                    known_consistent=bool(field('ACCESSION-NUMBER')==row['accessionNumber'] and issuer['cik'] in [x.zfill(10) for x in re.findall(r'<CIK>\s*(\d+)',text)] and field('TYPE')=='10-Q' and field('FILING-DATE')==row['filingDate'].replace('-','')==m['index']['filing_date'].replace('-','') and acceptance==re.sub('[- :]','',m['index']['accepted_local']) and datetime.fromisoformat(row['acceptanceDateTime'].replace('Z','+00:00')).astimezone(ZoneInfo('America/New_York')).strftime('%Y-%m-%d %H:%M:%S')==m['index']['accepted_local'])
                    check('clock agreement '+row['accessionNumber'],known_consistent==clock['timestamp_sources_consistent'] and not clock['public_dissemination_instant_verified'])
            if not (clock or {}).get('timestamp_sources_consistent'):
                clocks.append({'issuer':issuer,'accession':row['accessionNumber'],'clock':clock}); issuer_clocks+=1
            if m['status']!='captured':
                failures.append({k:m.get(k) for k in ['issuer','registry_row','error']}); reasons[m.get('error','unknown').split(': https://')[0]]+=1
        by_issuer.append({'issuer':issuer,'discovery_complete':d['complete'],'originals':len(original),'filed_year_counts':counts,'status_counts':dict(issuer_status),'clock_issue_records':issuer_clocks,'failure_reasons':dict(reasons),'coverage_review_entries':len(expected_cov),'undiscovered_original_count':0 if d['complete'] else None})
    check('no extra or missing filing manifests',set(x.resolve() for x in (S/'filings').glob('*/*.json'))==manifest_paths)
    status_counts=dict(Counter(m['status'] for m in manifests))
    check('completion counts reconciled',len(manifests)==4057==done['registered_originals']==done['processed_originals'] and status_counts==done['counts'] and done['declared_issuers']==100)
    check('all discovery completions reconciled',reg['complete'] and all(x['discovery']['complete'] for x in reg['issuers']) and done['incomplete_discoveries']==[])
    check('all original failures retained',failures==done['failed_filings'])
    check('all coverage records retained',coverage==done['coverage_review_needed'])
    check('all clock issues retained',clocks==done['clock_issues'])
    requests=[json.loads(x) for x in (S/'requests.jsonl').read_text().splitlines()]
    starts=[x for x in requests if x['event']=='request_started']; finishes=[x for x in requests if x['event']=='request_finished']
    start_urls=Counter(x['url'] for x in starts); finish_urls=Counter(x['url'] for x in finishes)
    check('request budget and summary reconciled',len(starts)==done['network_attempts']==13845 and len(starts)<=req['max_lifetime_network_attempts'] and max(start_urls.values())<=req['max_attempts_per_url'])
    check('no completed URL retry',max(finish_urls.values())==1 and all(n==1 or finish_urls[u]==1 for u,n in start_urls.items()))
    interrupted=[{'url':u,'starts':n,'finishes':finish_urls[u]} for u,n in start_urls.items() if n!=1 or finish_urls[u]!=1]
    recovery=read(S/'recoveries/20260929T134513Z/recovery.json')
    check('sole interrupted start reconciles',interrupted==[{'url':recovery['unfinished_request']['url'],'starts':2,'finishes':1}])
    for name,expected in recovery['prior_identities'].items():bind(S/'recoveries/20260929T134513Z'/name,expected)
    check('request and progress journals preserve prior prefixes',all((S/name).read_bytes().startswith((S/'recoveries/20260929T134513Z'/name).read_bytes()) for name in ['requests.jsonl','progress.jsonl']))
    resources=[read(p) for p in (S/'resources').glob('*.json')]
    resource_by_url={x['url']:x for x in resources}
    check('unique resource URLs',len(resource_by_url)==len(resources))
    check('all started URLs have durable outcomes',set(start_urls).issubset(resource_by_url))
    check('interrupted header resolved HTTP200',resource_by_url[recovery['unfinished_request']['url']].get('status')==200 and resource_by_url[recovery['unfinished_request']['url']].get('attempt')==2)
    for meta in resources:
        if meta.get('path') and meta.get('sha256'):bindraw(meta)
    for row in finishes:
        meta=resource_by_url[row['url']]
        check('request outcome '+row['url'],row.get('status')==meta.get('status') and row.get('error')==meta.get('error') and row.get('bytes')==meta.get('bytes'))
    check('no HTTP stop codes',not any(x.get('status') in [403,429] for x in finishes))
    progress=[json.loads(x) for x in (S/'progress.jsonl').read_text().splitlines()]
    terminal_pass=progress[-4057:]
    expected_keys=[(x['issuer']['symbol'],x['registry_row']['accessionNumber'],x['status']) for x in manifests]
    check('complete ordered terminal progress pass',[(x['issuer'],x['accession'],x['status']) for x in terminal_pass]==expected_keys and [x['completed'] for x in terminal_pass]==list(range(1,4058)))
    check('source bytes and response envelope',sum(p.stat().st_size for p in (S/'raw').glob('*.bin'))<=req['max_total_raw_bytes'] and max(x['bytes'] for x in raw.values())<=req['max_response_bytes'])
    for p,digest in list(files.items()):check('final stability '+str(Path(p).relative_to(REPO)),sha(p)==digest)
finally:
    for db,p,before in reversed(locks):
        db.rollback();db.close();check('lock bytes unchanged '+p.name,sha(p)==before)
required=['.qualification/post-filing-strategy20260928/calendar.json']
required += [str((S/n).relative_to(REPO)) for n in ['request.json','implementation.json','registry.json','completion.json','capture.py','cohort.json','finalization-definition.json','finalization-completion.json']]
required += ['.qualification/earnings-quality20260928/cohort/model-specification.json','.qualification/earnings-quality20260928/features/cash_backing.py','.qualification/filing-features20260928/features.py','src/frontier/historical_lab.py']
required += ['.qualification/earnings-quality20260928/qualification/'+n for n in ['header_industry.py','run_qualification.py','test_header_industry.py','test_collector.py','extraction-declaration.json']]
required_hashes={n:sha(REPO/n) for n in required}
review={'schema':1,'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'review_scope':'Read-only independent terminal source and identity review; no source worker, collector, features, labels, models, economic accounts or network called.','source_process_inventory':'Separate escalated Win32_Process query returned no Python source commands matching earnings-quality20260928.','locks':lock_status,'terminal_status':done['status'],'qualification_permitted_subject_to_root_definition':not blockers,'blockers':blockers,'summary':{'issuers':100,'originals':len(manifests),'statuses':status_counts,'clock_issue_records':len(clocks),'clock_issue_with_saved_clock':sum(x['clock'] is not None for x in clocks),'coverage_issuers':len(coverage),'coverage_issuer_years':sum(len(x['items']) for x in coverage),'unknown_discovery_count':0,'network_starts':len(starts),'network_finishes':len(finishes),'http_outcomes':dict(Counter(str(x.get('status')) for x in finishes)),'interrupted_starts':interrupted,'resources':len(resources),'unique_verified_raw_files':len(raw),'verified_raw_bytes':sum(x['bytes'] for x in raw.values()),'discovery_source_count':discovery_source_count,'progress_records':len(progress),'terminal_progress':progress[-1],'filed_year_counts':dict(sorted(years.items()))},'issuer_denominators':by_issuer,'failure_categories':dict(Counter(m.get('error','unknown').split(': https://')[0] for m in manifests if m['status']!='captured')),'root_definition_required_inputs':required_hashes,'expected_retained_original_records':4057,'limitations':['Terminal incomplete source is eligible for qualification only with all 190 original failure records retained unavailable.','All 100 discoveries are source-complete; 19 issuer coverage flags do not establish fiscal-quarter completeness.','No feature qualification or economic result has been computed by this review.','Current selected-cohort membership, SIC/domicile profile selection and survivorship limits remain.','Original-header SIC qualification and original eight-event seasonal history must remain unchanged.','Root must bind terminal registry/completion and declared code inputs before executing collector.'],'checks':checks,'source_files':files,'raw_identities':raw}
OUT.mkdir(parents=True,exist_ok=True)
with (OUT/'terminal-review.json').open('x',encoding='utf-8') as f:json.dump(review,f,indent=2)
print(json.dumps({'path':str(OUT/'terminal-review.json'),'sha256':sha(OUT/'terminal-review.json'),'blockers':blockers,'checks':len(checks),'summary':review['summary'],'failure_categories':review['failure_categories']},indent=2))
