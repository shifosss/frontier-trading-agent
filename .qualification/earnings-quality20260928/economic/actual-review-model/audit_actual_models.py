from pathlib import Path
from collections import Counter,defaultdict
from datetime import datetime,timezone
from decimal import Decimal
from zoneinfo import ZoneInfo
import hashlib,importlib.util,json,math,statistics,sys
import numpy as np
from threadpoolctl import threadpool_limits

R=Path.cwd().resolve();ROOT=R/'.qualification/earnings-quality20260928';A=ROOT/'economic/attempts/7487019bf15a4eb89e1a3702f5a0f7fb';OUT=ROOT/'economic/actual-review-model'
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):
    with Path(p).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def identity(x):return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()
issues=[];checks=Counter();stats=Counter();fold_reports=[];tolerances={'independent_float_arithmetic_absolute':1e-12,'independent_float_arithmetic_relative':1e-12,'reloaded_prediction':'exact'}
def check(name,condition,item=''):
    checks[name]+=1
    if not condition:issues.append({'check':name,'item':item})
def near(a,b):return bool(np.allclose(a,b,rtol=1e-12,atol=1e-12,equal_nan=False))
def finite(a):return all(math.isfinite(float(x)) for x in a)
attempt=read(A/'attempt.json');definition=attempt['definition'];bound=read(A/'bound-inputs.json')
paths={k:R/v for k,v in definition['paths'].items()}
old=read(ROOT/'qualification-review/terminal-20260929T213900Z/terminal-review.json')
known={str(Path(p).resolve()):h for p,h in old['source_files'].items()}
known.update({str(Path(p).resolve()):v['sha256'] for p,v in old['raw_identities'].items()})
for p,h in bound.items():
    path=Path(p);path=path if path.is_absolute() else R/path;k=str(path.resolve())
    if k in known:check('retained verified source identity',known[k]==h,p)
    else:check('bound input current identity',(sha(path) if path.is_file() else None)==h,p)
completion=read(A/'completion.json')
for p,h in definition['inputs'].items():check('declaration identity retained',bound[p]==h,p)
events=read(paths['terminal_events']);prep=read(A/'prepared-events.json');rows=prep['rows'];byid={x['event_id']:x for x in rows};cohort=read(paths['cohort'])['selected']
calendar=read(paths['calendar'])['sessions'];sessions=[x['session'] for x in calendar];ix={s:i for i,s in enumerate(sessions)}
meta=read(paths['market_inputs']);syms=meta['symbols'];col={s:i for i,s in enumerate(syms)};b=meta['benchmark']
with np.load(paths['market_arrays'],allow_pickle=False) as data:arrays={k:data[k] for k in data.files}
check('market arrays identity',sha(paths['market_arrays'])==meta['arrays_sha256'])
check('market calendar identity',meta['sessions']==sessions and syms[b]=='SPY' and {x['symbol'] for x in cohort}.issubset(syms))
check('all 4057 originals preserved',len(rows)==len(events)==len(byid)==4057 and {(x['symbol'],x['accession']) for x in rows}=={(x['symbol'],x['accession']) for x in events})
eventbyid={x['cik']+':'+x['accession']:x for x in events};rowhash={k:identity(v) for k,v in byid.items()}
for row in rows:
    eid=row['event_id'];event=eventbyid[eid];check('prepared event fields unchanged',all(row[k]==v for k,v in event.items()),eid)
    v=[None]*5
    for j,k in enumerate(['S','Q']):
        try:
            d=Decimal(str(event.get(k)));val=float(d)
            if d.is_finite() and math.isfinite(val):v[j]=val
        except Exception:pass
    if event['execution_status']=='qualified':
        entry=ix[event['entry_session']];p=entry-1;c=col[event['symbol']]
        check('strict prior-session feature index',row['prior_price_index']==p and row['entry_index']==entry and row['planned_label_end_index']==entry+5 and row['planned_label_end_session']==sessions[entry+5],eid)
        stock=arrays['adjusted'][p-5:p+1,c].tolist();spy=arrays['adjusted'][p-5:p+1,b].tolist()
        if p>=5 and finite(stock+spy) and min(stock+spy)>0:v[2]=stock[-1]/stock[0]-spy[-1]/spy[0]
        price=arrays['vendor_quote_close'][p-20:p+1,c].tolist();vol=arrays['vendor_quote_volume'][p-20:p+1,c].tolist()
        if p>=20 and finite(price+vol) and min(price)>0 and min(vol)>=0:
            activity=[x*y for x,y in zip(price,vol)]
            if finite(activity) and statistics.median(activity[:-1])>0:v[3]=activity[-1]/statistics.median(activity[:-1])
        spy200=arrays['adjusted'][p-199:p+1,b].tolist()
        if p>=199 and finite(spy200) and min(spy200)>0:v[4]=spy200[-1]/(math.fsum(spy200)/200)-1
    check('five causal original-source values',all((a is None and z is None) or (a is not None and z is not None and near(a,z)) for a,z in zip(v,row['model_inputs'])),eid)
    expected=all(event.get(k)=='qualified' for k in ['feature_status','q_status','execution_status','strategy_source_status']) and all(x is not None and math.isfinite(x) for x in v)
    check('input eligibility independent of future labels',(row['model_input_status']=='qualified')==expected,eid)
    stats['causal_input_rows']+=1
specification=read(paths['specification'])
spec=importlib.util.spec_from_file_location('independent_earnings_reload',ROOT/'models/earnings_models.py');models=importlib.util.module_from_spec(spec);sys.modules[spec.name]=models;spec.loader.exec_module(models)
def nofit(*a,**k):raise AssertionError('Refitting is forbidden in independent saved-model audit')
models.fit_family_fold=nofit;models.fit_fold=nofit;models.shared._fit_family=nofit
models_by_family={f:[] for f in models.FAMILIES};all_test_labels={}
def year(row):
    if not row.get('decision_timestamp'):return None
    return datetime.fromisoformat(row['decision_timestamp']).astimezone(ZoneInfo('America/New_York')).year
def label(row):
    e=row['entry_index'];z=row['planned_label_end_index'];targets=None;reasons=[]
    if e is None or z!=e+5:reasons=['scheduled_label_interval:unavailable']
    else:
        price=arrays['adjusted'][e:z+1,col[row['symbol']]].tolist()
        if len(price)!=6 or not finite(price) or min(price)<=0:reasons=['label_closes:missing_or_invalid']
        else:
            moves=[x/price[0]-1 for x in price[1:]]
            targets=[moves[-1],max(0,-min(moves))]
    return {'status':'unavailable' if reasons else 'qualified','targets':targets,'reasons':reasons,'entry_session':row.get('entry_session'),'label_end_session':row.get('planned_label_end_session')}
model_attempts=read(A/'models/model-attempts.json');attempt_map={(x['family'],x['test_decision_year']):x for x in model_attempts}
check('exactly ten declared model attempts',len(model_attempts)==10 and len(attempt_map)==10 and all(x['status']=='complete' for x in model_attempts))
for fold in specification['chronology']['folds']:
    y=fold['test_decision_year'];directory=A/'models'/str(y);test_rows=[r for r in rows if year(r)==y]
    labels_file=read(directory/'fit-calibration-labels.json');labels=labels_file['labels'];barrier=read(directory/'forecasts-persisted.json');test_labels=read(directory/'test-labels.json');all_test_labels.update(test_labels)
    boundary={'fit':next(s for s in sessions if int(s[:4])==fold['calibration_decision_year']),'calibration':next(s for s in sessions if int(s[:4])==y)}
    check('both family forecast barriers',barrier['fold']==fold and set(barrier['forecast_sha256'])==set(models.FAMILIES),str(y))
    for family,h in barrier['forecast_sha256'].items():check('durable forecast barrier bytes',sha(directory/family/'forecasts.json')==h,str(y)+family)
    check('forecast/label persisted file ordering',max((directory/f/'forecasts.json').stat().st_mtime_ns for f in models.FAMILIES)<=(directory/'forecasts-persisted.json').stat().st_mtime_ns<=(directory/'test-labels.json').stat().st_mtime_ns,str(y))
    expected_access=set()
    expected_groups={p:[] for p in ['fit','calibration','test']}
    expected_dispositions={}
    for row in rows:
        eid=row['event_id'];dy=year(row)
        part='unassigned' if dy is None else 'fit' if dy in fold['fit_decision_years'] else 'calibration' if dy==fold['calibration_decision_year'] else 'test' if dy==y else 'outside'
        status='outside' if part=='outside' else 'unavailable'
        if part in expected_groups and row['model_input_status']=='qualified':
            if part!='test' and row['planned_label_end_session']>=boundary[part]:status='purged'
            elif part=='test':status='eligible';expected_groups['test'].append(eid)
            else:
                expected_access.add(eid)
                l=label(row);check('fit calibration labels recomputed from frozen closes',labels.get(eid)==l,eid)
                if l['status']=='qualified':status='retained';expected_groups[part].append(eid)
        expected_dispositions[eid]=(part,status)
    check('fit/cal lookup excludes test/unavailable/purged',set(labels)==expected_access,str(y))
    accesses=Counter(x['event_id'] for x in labels_file['accesses'])
    check('two fixed families share same label set',set(accesses)==expected_access and set(accesses.values())=={2},str(y))
    for x in labels_file['accesses']:
        row=byid[x['event_id']];part=expected_dispositions[x['event_id']][0]
        check('every label access causal gate',x['partition']==part and x['label_end']==row['planned_label_end_session']<x['strictly_before']==boundary[part],x['event_id'])
    check('test denominator retained before outcome checks',set(test_labels)=={r['event_id'] for r in test_rows},str(y))
    for eid,l in test_labels.items():check('test labels independently recomputed',l==label(byid[eid]),eid)
    for family in models.FAMILIES:
        d=directory/family;bundle=models.load_bundle(d);audit=bundle.audit;saved=read(d/'forecasts.json');manifest=read(d/'manifest.json');observed=attempt_map[(family,y)]
        check('all 4057 saved model source rows',bundle.rows==rows and audit['rows_sha256']==identity(rows),str(y)+family)
        check('fold/code/spec identities',audit['fold']==fold and audit['boundaries']==boundary and audit['calendar_sha256']==identity(sessions) and manifest['specification_sha256']==sha(paths['specification']),str(y)+family)
        check('saved forecast and manifest identities',sha(d/'forecasts.json')==observed['forecasts_sha256'] and sha(d/'manifest.json')==observed['manifest_sha256'] and audit['attempt_id']==observed['attempt_id'],str(y)+family)
        for disp in audit['row_dispositions']:
            eid=disp['event_id'];part,status=expected_dispositions[eid]
            check('every row partition/disposition/identity',disp['partition']==part and disp['status']==status and disp['row_sha256']==rowhash[eid],str(y)+family+eid)
            if 'label_sha256' in disp:check('fit calibration label binding',disp['label_sha256']==identity(labels[eid]) and eid in expected_access,eid)
        check('all row dispositions retained',len(audit['row_dispositions'])==4057,str(y)+family)
        for part,expected in expected_groups.items():
            expected=sorted(expected,key=lambda eid:(datetime.fromisoformat(byid[eid]['decision_timestamp']),byid[eid]['cik'],byid[eid]['accession']))
            sample=audit['samples'][part]
            check('exact purged sample identities and issuer count',sample['event_ids']==expected and sample['rows']==len(expected) and sample['distinct_ciks']==len({byid[eid]['cik'] for eid in expected}),str(y)+family+part)
            if part!='test':
                check('fit calibration feature/target matrices',sample['X']==[byid[eid]['model_inputs'] for eid in expected] and sample['targets']==[labels[eid]['targets'] for eid in expected],str(y)+family+part)
        training=np.array(audit['samples']['fit']['X']);target=np.array(audit['samples']['fit']['targets']);cal=np.array(audit['samples']['calibration']['X']);caltarget=np.array(audit['samples']['calibration']['targets'])
        check('unchanged sample floors',len(training)>=256 and audit['samples']['fit']['distinct_ciks']>=25 and len(cal)>=64 and audit['samples']['calibration']['distinct_ciks']>=16,str(y)+family)
        check('training-only mean target',np.array_equal(target.mean(axis=0),bundle.training_mean),str(y)+family)
        preprocess=audit['preprocessing']
        check('training-only imputation',np.array_equal(np.median(training,axis=0),preprocess['feature_medians']) and preprocess['missing_indicator_features']==[],str(y)+family)
        if family=='ridge':
            check('training-only scaling',near(training.mean(axis=0),preprocess['feature_mean']) and near(training.std(axis=0),preprocess['feature_scale']),str(y))
            params=bundle.model.steps[-1][1].get_params();check('fixed Ridge preset',params['alpha']==100,str(y))
        else:
            estimators=bundle.model.steps[-1][1].estimators_;check('exactly two fixed boosted heads',len(estimators)==2,str(y))
            for m in estimators:
                p=m.get_params();check('fixed boosted preset',p['max_iter']==60 and p['max_leaf_nodes']==15 and p['learning_rate']==.05 and p['l2_regularization']==10 and p['min_samples_leaf']==64 and p['early_stopping'] is False and p['random_state']==1729,str(y))
        with threadpool_limits(limits=2):raw=np.array(bundle.model.predict(cal))
        check('exact saved model calibration reload',np.array_equal(raw,np.array(audit['calibration']['raw'])),str(y)+family)
        uncal=raw.copy();uncal[:,1]=np.maximum(0,uncal[:,1]);bias=(caltarget-uncal).mean(axis=0);corrected=uncal+bias;corrected[:,1]=np.maximum(0,corrected[:,1])
        check('calibration-only mean bias and downside clips',np.array_equal(bias,bundle.bias) and np.array_equal(uncal,audit['calibration']['uncalibrated']) and np.array_equal(corrected,audit['calibration']['corrected']),str(y)+family)
        for name,value in [('raw',raw),('corrected',corrected)]:
            edges=[]
            for head in value.T:
                sorted_head=sorted(head.tolist());n=len(sorted_head)
                quantiles=[]
                for q in [.2,.4,.6,.8]:
                    location=(n-1)*q;lo=int(math.floor(location));hi=int(math.ceil(location));v=sorted_head[lo]+(sorted_head[hi]-sorted_head[lo])*(location-lo)
                    if sorted_head[0]<v<sorted_head[-1]:quantiles.append(v)
                edges.append(sorted(set(quantiles)))
            check('calibration-only quantile edges',all(near(x,z) for x,z in zip(edges,bundle.quantile_edges[name])),str(y)+family+name)
        replay=models.predict_events(bundle,test_rows)
        check('exact reloaded full test forecasts',replay==saved,str(y)+family)
        forecast_map={x['event_id']:x for x in saved['forecasts']}
        for eid,f in forecast_map.items():
            expected_eligible=expected_dispositions[eid]==('test','eligible')
            check('forecast binds causal eligibility',f['cik']==byid[eid]['cik'] and f['prepared_row_sha256']==rowhash[eid] and ((f['status']=='predicted')==expected_eligible),str(y)+family+eid)
            if f['status']=='predicted':
                rawf=np.array(f['raw']);u=rawf.copy();u[1]=max(0,u[1]);c=u+bias;c[1]=max(0,c[1])
                check('forecast calibration retained',np.array_equal(u,f['uncalibrated']) and np.array_equal(c,f['corrected']),eid)
                for layer in ['raw','corrected']:
                    bins=[int(np.searchsorted(bundle.quantile_edges[layer][i],f[layer][i],side='right')) for i in range(2)]
                    check('calibration-defined test bins',bins==f['quantile_bins'][layer],eid)
        models_by_family[family].extend(dict(x,family=family,test_decision_year=y,model_attempt_id=saved['model_attempt_id']) for x in saved['forecasts'])
        diag=read(d/'diagnostics.json')
        for hi,h in enumerate(['return_5','downside_5']):
            for layer in ['raw','corrected','training_mean']:
                entries=[f for f in saved['forecasts'] if f['status']=='predicted' and test_labels[f['event_id']]['status']=='qualified']
                actual=np.array([test_labels[f['event_id']]['targets'][hi] for f in entries]);pred=np.array([bundle.training_mean[hi] if layer=='training_mean' else f[layer][hi] for f in entries]);error=pred-actual;ds=diag['heads'][h][layer]
                check('heldout errors and training-mean baseline',ds['count']==len(entries) and near(ds['mae'],np.abs(error).mean()) and near(ds['mse'],(error**2).mean()) and near(ds['mean_error'],error.mean()),str(y)+family+h+layer)
                if layer!='training_mean':
                    check('all calibration-defined bins reported',len(ds['bins'])==len(bundle.quantile_edges[layer][hi])+1,str(y)+family+h+layer)
                    for binrow in ds['bins']:
                        group=[f for f in entries if f['quantile_bins'][layer][hi]==binrow['bin']]
                        check('test bin denominator',binrow['count']==len(group),str(y)+family+h+layer+str(binrow['bin']))
        fold_reports.append({'year':y,'family':family,'fit_rows':len(training),'calibration_rows':len(cal),'test_requested':len(test_rows),'test_predicted':sum(f['status']=='predicted' for f in saved['forecasts']),'purged':sum(x['status']=='purged' for x in audit['row_dispositions']),'warnings':audit['warnings'],'exact_reload':replay==saved})
for family,forecasts in models_by_family.items():
    check('one family forecast source shared across accounts',read(A/'models'/(family+'-all-forecasts.json'))=={'family':family,'forecasts':forecasts},family)
denom=read(A/'denominators.json');groups=defaultdict(list)
for row in rows:groups[(row['symbol'],row['cik'],str(year(row)) if year(row) is not None else 'unassigned')].append(row)
for member in cohort:
    for y in range(2012,2026):groups.setdefault((member['symbol'],member['cik'],str(y)),[])
check('all issuer-year denominators retained',len(denom['by_issuer_year'])==len(groups) and denom['requested_issuers']==100 and denom['retained_events']==4057 and denom['issuers_without_events']==[])
fmap={f:{x['event_id']:x for x in v} for f,v in models_by_family.items()}
for d in denom['by_issuer_year']:
    group=groups[(d['symbol'],d['cik'],d['decision_year'])]
    check('issuer/year original and label denominator',d['structural']==len(group) and d['test_labels_accessed']==sum(r['event_id'] in all_test_labels for r in group) and d['test_label_available']==sum(all_test_labels.get(r['event_id'],{}).get('status')=='qualified' for r in group),d['symbol']+d['decision_year'])
    for k in ['feature_status','q_status','joint_feature_status','strategy_source_status','execution_status','model_input_status']:check('issuer/year qualification denominator',d[k]==sum(r.get(k)=='qualified' for r in group),d['symbol']+d['decision_year']+k)
    for family in models.FAMILIES:check('issuer/year forecast denominator',d['predicted'][family]==sum(fmap[family].get(r['event_id'],{}).get('status')=='predicted' for r in group),d['symbol']+d['decision_year']+family)
check('all missing input reasons retained',denom['missing_reason_counts']==dict(Counter(z for r in rows for z in r['model_input_reasons'])))
report={'schema':1,'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),'economic_attempt':str(A),'definition_sha256':attempt['definition_sha256'],'material_blockers':issues,'checks':dict(checks),'total_checks':sum(checks.values()),'tolerances':tolerances,'folds':fold_reports,'all_original_events':len(rows),'causally_eligible_events':sum(r['model_input_status']=='qualified' for r in rows),'issuer_year_denominators':len(groups),'source_bindings':len(bound),'saved_models_reloaded':10,'model_refits':0,'network_requests':0,'source_or_bound_artifact_changes':0,'scope_limitations':['Frozen source and corporate-action/current-member limits remain unchanged.','Persisted barriers, code ordering and file timestamps corroborate forecast-before-test-label access; this is not cryptographic proof of historical model operation.','No profitability or account-ledger conclusion is made by this audit.']}
OUT.mkdir(parents=True,exist_ok=True);p=OUT/'model-chronology-review.json'
with p.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
print(json.dumps({'path':str(p),'sha256':sha(p),'material_blockers':issues,'total_checks':sum(checks.values()),'folds':fold_reports},indent=2))
