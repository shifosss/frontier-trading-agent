"""Independent full descriptive event audit, without importing the study/helper."""
from pathlib import Path
from decimal import Decimal, getcontext
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json,hashlib
import numpy as np
ROOT=Path(__file__).resolve().parent.parent
REPO=ROOT.parents[1]
OUT=ROOT/'reference-audit'
ATTEMPT=ROOT/'attempts/54fd505baeb347cfae5d79bcf96925e3'
D=Decimal;getcontext().prec=40
def load(p):return json.loads(p.read_text(encoding='utf-8'),parse_float=D)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(name,x):(OUT/name).write_text(json.dumps(x,indent=2,default=str)+'\n',encoding='utf-8')
metrics=['stock_gross_return','benchmark_gross_return','stock_minus_benchmark']
save('declaration.json',{'at':datetime.now(timezone.utc).isoformat(),'scope':'All252 source events and121eligible references, all endpoint ratios/selection labels and overall/issuer/year aggregations; no funded account files or network','arithmetic':'Decimal40precision from exact displayed float64 endpoint values; absolute return/mean tolerance1e-12','selection':'Alleligible fixed rows, no return filtering or sampling','do_not_import':['event_reference.py','run_study.py','adapter.py']})
try:
 definition=load(ROOT/'definition.json'); request=load(ROOT/'request.json')
 pointer=load(ROOT/'completed.json')
 assert pointer['definition_sha256']==sha(ROOT/'definition.json')=='ca842ce2c901b5ea3ae9e21bb0501ae4b1c8271804780c6292bab3846d81b5dc'
 refpath=ATTEMPT/'event-reference.json'
 assert pointer['files'][refpath.relative_to(ROOT).as_posix()]==sha(refpath)
 for path in [ROOT/'request.json',ROOT/'market-inputs.json',ROOT/'market-arrays.npz',REPO/request['events']]:
  assert definition['files'][path.relative_to(REPO).as_posix()]==sha(path)
 reference=load(refpath); features=load(REPO/request['events']); market=load(ROOT/'market-inputs.json')
 prices=np.load(ROOT/'market-arrays.npz',allow_pickle=False)['adjusted']
 sessions=market['sessions']; symbols=market['symbols']; bi=symbols.index('SPY'); assert market['benchmark']==bi and reference['benchmark_symbol']=='SPY'
 expected_indices=[]; exclusions=[]
 for i,event in enumerate(features):
  reason=None
  if not '2017-01-01'<=event.get('filing_date','')<='2025-12-31':reason='filing_date_outside_2017_2025_or_missing'
  elif event.get('feature_status')!='qualified':reason='feature_not_qualified'
  elif event.get('execution_status')!='qualified':reason='execution_not_qualified'
  if reason:exclusions.append({'input_row':i,'symbol':event['symbol'],'accession':event['accession'],'filing_date':event.get('filing_date',''),'reason':reason})
  else:expected_indices.append(i)
 assert reference['exclusions']==exclusions
 assert [r['input_row'] for r in reference['rows']]==expected_indices
 assert len(set(expected_indices))==len(expected_indices)
 rows=[]; max_error=D(0)
 for saved in reference['rows']:
  event=features[saved['input_row']]
  assert all(saved[k]==event[k] for k in ['symbol','accession','filing_date','entry_session','exit_session'])
  assert saved['selected']==event['selected']==(D(event['S'])>=1)
  i=sessions.index(event['entry_session']); last=sessions.index(event['exit_session']); j=symbols.index(event['symbol'])
  assert last-i==saved['holding_sessions']==5
  endpoints={'stock_entry':prices[i,j],'stock_exit':prices[last,j],'benchmark_entry':prices[i,bi],'benchmark_exit':prices[last,bi]}
  assert all(np.isfinite(x) and x>0 for x in endpoints.values())
  values={k:D(str(float(v))) for k,v in endpoints.items()}
  assert saved['adjusted_endpoints']==values
  stock=values['stock_exit']/values['stock_entry']-1;spy=values['benchmark_exit']/values['benchmark_entry']-1
  returns={'stock_gross_return':stock,'benchmark_gross_return':spy,'stock_minus_benchmark':stock-spy}
  assert saved['status']=='matched' and saved['identity_issues']==[] and saved['unavailable_endpoints']==[]
  for key,value in returns.items():
   error=abs(saved[key]-value);max_error=max(max_error,error);assert error<=D('1e-12')
  rows.append({'input_row':saved['input_row'],'symbol':saved['symbol'],'accession':saved['accession'],'selected':saved['selected'],'entry_session':saved['entry_session'],'exit_session':saved['exit_session'],'entry_year':saved['entry_session'][:4],'adjusted_endpoints':values,**returns})
 assert reference['scope_counts']=={'input_events':len(features),'filed_in_2017_2025':sum('2017-01-01'<=e.get('filing_date','')<='2025-12-31' for e in features),'outside_filing_period':sum(not('2017-01-01'<=e.get('filing_date','')<='2025-12-31') for e in features),'structurally_eligible':len(rows),'structurally_ineligible_in_period':sum(e['reason']!='filing_date_outside_2017_2025_or_missing' for e in exclusions)}
 aggregate_checks=[]
 def aggregate(group,saved,label):
  global max_error
  dates=sorted(set(r['entry_session'] for r in group)); n=len(group)
  assert all(saved[k]==v for k,v in {'eligible_events':n,'matched_events':n,'unmatched_events':0,'matched_entry_dates':len(dates),'available_stock_returns':n,'available_benchmark_returns':n}.items())
  assert saved['unavailable_endpoint_counts']==saved['identity_issue_counts']=={}
  eventmeans={};datemeans={}
  for key in metrics:
   eventmeans[key]=sum((r[key] for r in group),D(0))/n if n else None
   # Equal-date weights assigned explicitly; avoids importing/replaying original summarize.
   datemeans[key]=sum((r[key]/D(sum(x['entry_session']==r['entry_session'] for x in group))/D(len(dates)) for r in group),D(0)) if dates else None
   for convention,value in [('equal_event_mean',eventmeans[key]),('equal_entry_date_mean',datemeans[key])]:
    actual=saved[convention][key]
    if value is None:assert actual is None
    else:
     error=abs(actual-value);max_error=max(max_error,error);assert error<=D('1e-12'),(label,key,convention,str(error))
  aggregate_checks.append({'group':label,'events':n,'entry_dates':len(dates),'equal_event_mean':eventmeans,'equal_entry_date_mean':datemeans})
 aggregate(rows,reference['all_eligible'],'all_eligible')
 selected=[r for r in rows if r['selected']]
 aggregate(selected,reference['selected'],'selected')
 for field,key in [('symbol','by_issuer'),('entry_year','by_entry_year')]:
  values=sorted(set(r[field] for r in rows));assert list(reference[key])==values
  for value in values:
   group=[r for r in rows if r[field]==value]
   aggregate(group,reference[key][value]['all_eligible'],key+'/'+value+'/all_eligible')
   aggregate([r for r in group if r['selected']],reference[key][value]['selected'],key+'/'+value+'/selected')
 expected_support={'matched_selected_events':len(selected),'matched_selected_issuers':len(set(r['symbol'] for r in selected)),'matched_selected_entry_years':len(set(r['entry_year'] for r in selected)),'failed_gates':['fewer_than_30_matched_selected_events'],'sufficient_descriptive_sample':False,'establishes_profitability':False}
 assert reference['sample_support']==expected_support
 allm,selm=aggregate_checks[:2]
 bps={g['group']:{convention:{metric:str(value*10000) for metric,value in g[convention].items()} for convention in ['equal_event_mean','equal_entry_date_mean']} for g in [allm,selm]}
 totals={symbol:{'original_features':sum(e['symbol']==symbol for e in features),'in_period':sum(e['symbol']==symbol and '2017-01-01'<=e.get('filing_date','')<='2025-12-31' for e in features),'structurally_eligible':sum(r['symbol']==symbol for r in rows),'selected':sum(r['symbol']==symbol for r in selected)} for symbol in request['symbols']}
 result={'status':'passed','at':datetime.now(timezone.utc).isoformat(),'definition_sha256':sha(ROOT/'definition.json'),'event_reference_sha256':sha(refpath),'events_sha256':sha(REPO/request['events']),'market_arrays_sha256':sha(ROOT/'market-arrays.npz'),'audit_script_sha256':sha(Path(__file__)),'scope_counts':reference['scope_counts'],'exclusion_reason_counts':dict(Counter(e['reason'] for e in exclusions)),'full_six_issuer_denominator':totals,'verified_endpoint_count':len(rows)*4,'all_five_session_alignments':True,'selection_labels_match_frozen_S':True,'missing_endpoint_events':0,'sample_support':expected_support,'aggregate_groups_verified':len(aggregate_checks),'maximum_absolute_return_or_mean_error':str(max_error),'means_basis_points':bps,'selected_minus_all_eligible_excess_bps':{c:str((selm[c]['stock_minus_benchmark']-allm[c]['stock_minus_benchmark'])*10000) for c in ['equal_event_mean','equal_entry_date_mean']},'interpretation':'Selected observations show less stock-minus-SPY association than all eligible filings under both descriptive weights. This does not establish superior stock-specific selection or causal alpha;27selected events fail the predeclared30-event support gate. Gross event means omit costs/cash and are not funded account profits.','strategy_or_helper_rerun':False,'funded_account_files_read':0,'network_requests':0}
 save('independent-event-rows.json',rows);save('independent-aggregates.json',aggregate_checks);save('verification.json',result)
 print(json.dumps({k:result[k] for k in ['status','scope_counts','means_basis_points','selected_minus_all_eligible_excess_bps','maximum_absolute_return_or_mean_error']}))
except Exception as exc:
 save('failure.json',{'at':datetime.now(timezone.utc).isoformat(),'error':type(exc).__name__+': '+str(exc)})
 raise
