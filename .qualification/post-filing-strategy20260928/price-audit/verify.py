"""Read-only independent input audit; no strategy results or preparation imports."""
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from decimal import Decimal, getcontext
from collections import deque
import hashlib, json
import numpy as np
import joblib
import exchange_calendars as xcals

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
REPO=ROOT.parents[1]
PREP=ROOT.parent/'conditional-selection20260928/preparation'
SOURCE=ROOT/'T-price-source'
def read(p): return json.loads(p.read_text(encoding='utf-8'))
def sha(p):
    with p.open('rb') as f: return hashlib.file_digest(f,'sha256').hexdigest()
def save(name,obj): (HERE/name).write_text(json.dumps(obj,indent=2)+'\n',encoding='utf-8')
getcontext().prec=40
D=Decimal
save('declaration.json',{'at':datetime.now(timezone.utc).isoformat(),'scope':'Two retained T daily pages; seven market columns; no account outcome reads, network, or preparation imports','ATR':'Independent40-digit Decimal arithmetic for every observed T session. True range=max(adjusted high-low, abs(adjusted high-prior adjusted close), abs(adjusted low-prior adjusted close)); mean14 regular sessions then divide current adjusted/raw close factor. First14 source rows unavailable. No forward filling.','tolerance_raw_USD':'1e-10','reported_sample':'First finite ATR, last observed and20lowest SHA256(session) ranked dates, plus2022-04-08/2022-04-11 source-action boundary; selection independent of returns','coverage':'Compare saved calendar, frozen cache calendar and installed XNYS session schedule; retain source revisions/action-accounting limits'})
checks={}
try:
    request,implementation,completed=[read(SOURCE/n) for n in ['request.json','implementation.json','completion.json']]
    market=read(ROOT/'market-inputs.json'); calendar=read(ROOT/'calendar.json')
    assert sha(SOURCE/'request.json')==implementation['request_sha256']==completed['request_sha256']
    assert sha(ROOT/'capture_t.py')==implementation['capture_sha256']
    assert request['endpoint']=='https://data.alpaca.markets/v2/stocks/bars'
    assert request['params']=={'symbols':'T','timeframe':'1Day','start':'2016-01-04T00:00:00Z','end':'2026-09-19T00:00:00Z','asof':'2026-09-18','feed':'sip','currency':'USD','limit':10000,'sort':'asc'}
    assert request['adjustments']==['raw','all'] and request['automatic_retries']==0
    sources={}; page_evidence=[]
    for source in completed['sources']:
        adjustment=source['adjustment']; rows={}; prior=None; token=None
        assert len(source['pages'])<=request['maximum_pages_per_adjustment']
        for number,page in enumerate(source['pages']):
            assert page==read(SOURCE/f'{adjustment}-{number:02d}.metadata.json')
            expected=request['params']|{'adjustment':adjustment}
            if token is not None: expected['page_token']=token
            assert page['params']==expected and page['url']==request['endpoint'] and page['status']==200
            path=SOURCE/page['raw']; raw=path.read_bytes()
            assert sha(path)==page['sha256'] and len(raw)==page['bytes']
            body=json.loads(raw,parse_float=D)
            assert set(body['bars'])=={'T'}
            for bar in body['bars']['T']:
                stamp=datetime.fromisoformat(bar['t'].replace('Z','+00:00'))
                assert stamp.tzinfo is not None and (prior is None or stamp>prior)
                prior=stamp
                local=stamp.astimezone(ZoneInfo('America/New_York'))
                assert (local.hour,local.minute,local.second,local.microsecond)==(0,0,0,0)
                day=local.date().isoformat(); assert day not in rows
                assert all(D(bar[k]).is_finite() for k in ['o','h','l','c','v'])
                assert D(bar['l'])>0 and D(bar['v'])>=0
                assert D(bar['l'])<=min(D(bar['o']),D(bar['c']))<=max(D(bar['o']),D(bar['c']))<=D(bar['h'])
                rows[day]=bar
            token=body.get('next_page_token')
            page_evidence.append({k:page[k] for k in ['raw','sha256','bytes','requested_at','received_at']}|{'adjustment':adjustment,'bar_count':len(body['bars']['T']),'next_page_token':token})
            assert token is not None or number==len(source['pages'])-1
        assert token is None
        sources[adjustment]=rows
    assert set(sources)=={'raw','all'} and list(sources['raw'])==list(sources['all'])
    assert len(page_evidence)==2<=request['maximum_total_requests']
    assert (datetime.fromisoformat(page_evidence[1]['requested_at'])-datetime.fromisoformat(page_evidence[0]['requested_at'])).total_seconds()>=1
    sessions=market['sessions']; days=list(sources['raw'])
    xnys=xcals.get_calendar('XNYS',start=sessions[0],end=sessions[-1])
    exchange_days=[d.date().isoformat() for d in xnys.sessions_in_range(sessions[0],sessions[-1])]
    assert sessions==exchange_days==[r['session'] for r in calendar['sessions']]
    requested=[d for d in sessions if '2016-01-04'<=d<='2026-09-18']
    assert requested==days and market['T_observed_sessions']==len(days) and market['T_missing_requested_sessions']==[]
    arrays=np.load(ROOT/'market-arrays.npz',allow_pickle=False)
    assert sha(ROOT/'market-arrays.npz')==market['arrays_sha256']
    assert sha(ROOT/'calendar.json')==market['calendar_sha256']
    assert sha(SOURCE/'completion.json')==market['T_completion_sha256']
    assert market['symbols']==sorted(['AAPL','MSFT','F','T','HRL','BANF','SPY'])
    j=market['symbols'].index('T'); matches=[]; tr=deque(maxlen=14); previous=None; maxerr=D(0)
    expected_atr={}
    for day in days:
        raw,adjusted=sources['raw'][day],sources['all'][day]
        factor=D(adjusted['c'])/D(raw['c'])
        upper=D(raw['h'])*factor; lower=D(raw['l'])*factor
        if previous is not None: tr.append(max(upper-lower,abs(upper-previous),abs(lower-previous)))
        previous=D(adjusted['c'])
        expected_atr[day]=sum(tr,D(0))/D(14)/factor if len(tr)==14 else None
    for i,day in enumerate(sessions):
        if day not in sources['raw']:
            assert all(np.isnan(arrays[k][i,j]) for k in ['close','adjusted','atr'])
            continue
        assert arrays['close'][i,j]==float(sources['raw'][day]['c'])
        assert arrays['adjusted'][i,j]==float(sources['all'][day]['c'])
        value=expected_atr[day]
        if value is None: assert np.isnan(arrays['atr'][i,j])
        else:
            error=abs(D(str(arrays['atr'][i,j]))-value); maxerr=max(maxerr,error)
            assert error<=D('1e-10'),(day,str(error))
            matches.append(day)
    report_days=sorted(set(sorted(matches,key=lambda x:hashlib.sha256(x.encode()).hexdigest())[:20]+[matches[0],days[-1],'2022-04-08','2022-04-11']))
    sample=[{'session':d,'raw_close':str(sources['raw'][d]['c']),'adjusted_close':str(sources['all'][d]['c']),'independent_ATR_raw_USD':str(expected_atr[d]),'array_ATR_raw_USD':str(arrays['atr'][sessions.index(d),j])} for d in report_days]
    cache=PREP/'market-features.joblib'; manifest=read(PREP/'cache-manifest.json')
    assert cache.stat().st_size==manifest['bytes'] and sha(cache)==manifest['sha256']==market['source_cache_sha256']
    old,_=joblib.load(cache,mmap_mode='r')
    assert old['sessions']==sessions and np.array_equal(arrays['settlement_index'],old['settlement_index'],equal_nan=True)
    unchanged=[]
    for symbol in market['symbols']:
        if symbol=='T': continue
        a,b=market['symbols'].index(symbol),old['symbols'].index(symbol)
        for key in ['close','adjusted','atr']: assert np.array_equal(arrays[key][:,a],old[key][:,b],equal_nan=True)
        unchanged.append(symbol)
    evidence=read(PREP/'source-evidence.json'); source_hashes={r['symbol']:r['sha256'] for r in evidence['source_hashes']}
    index_path=REPO/'artifacts/historical-lab/runs/90af4c840aad48f7ab58fba7a682f96a/capture-index.json'
    assert sha(index_path)==evidence['capture_index_sha256']
    index={x['symbol']:x for x in read(index_path)}
    provenance={}
    for symbol in unchanged:
        assert market['source_by_symbol'][symbol]=={'provider':'Frozen Yahoo capture','identity':source_hashes[symbol]}
        source=index[symbol]; assert sha(REPO/'data/historical/capture-workspace'/source['path'])==source['sha256']==source_hashes[symbol]
        provenance[symbol]={k:source[k] for k in ['path','sha256','captured_at','url']}|{'capture_path_root':'data/historical/capture-workspace'}
    assert market['source_by_symbol']['T']=={'provider':'Alpaca SIP','identity':sha(SOURCE/'request.json')}
    amendment=read(SOURCE/'credential-reader-amendment.json')
    assert sha(SOURCE/amendment['preserved_attempt'])==amendment['preserved_attempt_sha256']
    assert amendment['source_request_changed'] is False and amendment['new_network_requests_before_resume']==0
    checks={'status':'passed','audited_at':datetime.now(timezone.utc).isoformat(),'script_sha256':sha(Path(__file__)),'page_evidence':page_evidence,'T_observed_sessions':len(days),'source_bounds':[days[0],days[-1]],'T_missing_requested_sessions':[],'market_sessions':len(sessions),'calendar_identity':sha(ROOT/'calendar.json'),'exchange_calendar_package':xcals.__version__,'all_T_close_and_adjusted_values_match_source':True,'independent_Decimal_ATR_finite_count':len(matches),'ATR_unavailable_initial_source_rows':len(days)-len(matches),'max_ATR_absolute_error_USD':str(maxerr),'ATR_samples':sample,'unchanged_columns':unchanged,'settlement_index_unchanged':True,'source_by_symbol_verified':True,'retained_six_source_provenance':provenance,'source_cache_sha256':manifest['sha256'],'cache_manifest_sha256':sha(PREP/'cache-manifest.json'),'market_arrays_sha256':market['arrays_sha256'],'prepare_market_sha256':sha(ROOT/'prepare_market.py'),'credential_amendment_verified':True,'network_requests_by_auditor':0,'outcome_files_read':0,'limitations':['Raw and adjusted source consistency does not establish full corporate-action cash accounting or security lineage.','Mixed retrospective provider revisions remain; all-adjusted factors are not point-in-time public information.','T history begins2016; earlier source absence remains explicit, no manufactured prices.','Retained initial attempt plus unchanged code places credential environment lookup before HTTPclient creation; this is a code/provenance check, not independent network packet evidence.']}
    save('verification.json',checks)
    print(json.dumps({k:checks[k] for k in ['status','T_observed_sessions','market_sessions','independent_Decimal_ATR_finite_count','max_ATR_absolute_error_USD','unchanged_columns']}))
except Exception as exc:
    save('failure.json',{'at':datetime.now(timezone.utc).isoformat(),'error':type(exc).__name__+': '+str(exc)})
    raise
