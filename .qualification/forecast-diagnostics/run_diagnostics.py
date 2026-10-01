"""Exploratory saved-model diagnostics; no fitting or production mutations."""
import os
for key in ('OMP_NUM_THREADS', 'OPENBLAS_NUM_THREADS', 'MKL_NUM_THREADS', 'NUMEXPR_NUM_THREADS'):
    os.environ[key] = '2'
import gc
import hashlib
import json
import sys
import time
import traceback
import warnings
from pathlib import Path
import numpy as np
import pandas as pd
from scipy.stats import spearmanr
from threadpoolctl import threadpool_limits
from frontier.candidate_daily import load_saved_history, _sample_audit, _digest
from frontier.ensemble_features import build_features, HORIZONS, LABEL_NAMES
from frontier.ensemble_models import predict_heads
from frontier.ensemble_study import CONFIG
from frontier.historical_study import _build_market
from frontier.model_artifact import load_heads
from frontier.strategy_study import BOOKS

ROOT = Path(__file__).resolve().parent
WORK = ROOT.parent.parent
CANDIDATE = '83d99338fd394e7cad44bdad045b25ad'
CAPTURE = '814780d48b4141b9a82a3fb917d1b85a'
START = time.time()

def write(name, value):
    (ROOT / name).write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')

def log(message):
    print(f'{time.time()-START:.1f}s {message}', flush=True)

def bootstrap(values):
    """Equal-date mean, circular moving blocks, exploratory percentile interval."""
    values = np.asarray(values, dtype=float)
    n = len(values)
    rng = np.random.default_rng(1729)
    starts = rng.integers(0, n, size=(2000, (n + 9)//10))
    indices = ((starts[:, :, None] + np.arange(10)) % n).reshape(2000, -1)[:, :n]
    samples = np.nanmean(values[indices], axis=1)
    return {'mean': float(np.nanmean(values)), 'valid_dates': int(np.isfinite(values).sum()),
            'ci95': np.quantile(samples, [0.025, 0.975]).tolist(), 'block_sessions': 10,
            'replicates': 2000, 'seed': 1729, 'interpretation': 'exploratory; no multiplicity correction'}

def rebuild():
    bundle, manifest = load_heads(WORK / 'artifacts/daily-candidates' / CANDIDATE / 'model')
    meta = manifest['metadata']
    implementation = {name: hashlib.sha256((WORK / 'src/frontier' / name).read_bytes()).hexdigest()
                      for name in meta['implementation_sha256']}
    mismatch = [name for name in implementation if implementation[name] != meta['implementation_sha256'][name]]
    # Root is concurrently extending cost/state handling. No silent change to data/features/models.
    causal_names = ['candidate_daily.py', 'ensemble_features.py', 'ensemble_models.py',
                    'historical_data.py', 'historical_study.py', 'strategy_study.py']
    if set(mismatch) & set(causal_names):
        raise ValueError(f'Causal reconstruction implementation changed: {mismatch}')
    log('verified saved bundle; loading bounded frozen USD history once')
    frame, universe, current, data = load_saved_history(WORK, CAPTURE, meta['signal_session'])
    log(f'loaded {len(frame)} history rows')
    assert _digest(data) == meta['data_id'], 'frozen data identity mismatch'
    market = _build_market(frame, universe, current, 'USD', None, include_activity=True)
    del frame
    gc.collect()
    log('market built; reconstructing features')
    specs = {spec['symbol']: spec for spec in universe}
    f = build_features(market, stock_mask=np.array([specs[s]['asset_type']=='stock' for s in market['symbols']]),
                       liquidity_floor=BOOKS['USD'][2], turnover=market.pop('turnover'),
                       dollar_volume=market.pop('dollar_volume'))
    sessions, symbols = market['sessions'], market['symbols']
    signal = len(sessions)-1
    tr, tc, fit = _sample_audit(f, sessions, symbols, signal-756, signal-253, signal-252, CONFIG['seed'])
    cr, cc, cal = _sample_audit(f, sessions, symbols, signal-252, signal-1, signal, CONFIG['seed']+1)
    assert fit == meta['fit_sample'], 'fit sample audit mismatch'
    assert cal == meta['calibration_sample'], 'calibration sample audit mismatch'
    assert f['feature_names'] == meta['feature_names']
    assert f['label_names'] == meta['head_names']
    write('sample-identities.json', {'fit': fit, 'calibration': cal})
    yfit = f['labels'][tr, tc].astype(float)
    ycal = f['labels'][cr, cc].astype(float)
    assert np.array_equal(yfit.mean(axis=0), np.array(bundle.audit['calibration']['training_target_mean']))
    ci = np.flatnonzero(f['eligible'][signal] & f['benchmark_known'][signal])
    log(f'exact fit/calibration identities verified: {len(tr)}/{len(cr)}; latest eligible {len(ci)}')
    pred = predict_heads(bundle, f['X'][cr, cc])
    latest = predict_heads(bundle, f['X'][signal, ci])
    original = json.loads((WORK/'artifacts/daily-candidates'/CANDIDATE/'report.json').read_text(encoding='utf-8'))
    original_rows = {row['symbol']: row for row in original['rankings']}
    exact = all(np.array_equal(latest['calibrated_ensemble'][i], original_rows[symbols[int(j)]]['forecasts']) for i,j in enumerate(ci))
    assert exact, 'latest persisted forecasts mismatch'
    baseline_mse = np.mean((ycal-yfit.mean(axis=0))**2, axis=0)
    assert np.array_equal(baseline_mse, np.array(bundle.audit['calibration']['baseline_mse']))
    for name, stored in bundle.audit['calibration']['model_mse'].items():
        assert np.array_equal(np.mean((pred[name]-ycal)**2,axis=0), np.array(stored)), name+' calibration MSE mismatch'
    exclusion_dates=[]
    for d in range(signal-252, signal+1):
        eligible=f['eligible'][d] & f['benchmark_known'][d]
        known=np.isfinite(f['labels'][d]).all(axis=1)
        exclusion_dates.append({'session':sessions[d], 'requested':len(symbols), 'eligible':int(eligible.sum()),
            'ineligible_or_benchmark_missing':int((~eligible).sum()), 'eligible_missing_any_label':int((eligible & ~known).sum()),
            'sampled_calibration':int((cr==d).sum()), 'all_heads_purged':bool(f['label_end'][d].max()>=signal)})
    pd.DataFrame(exclusion_dates).to_csv(ROOT/'date-exclusions.csv',index=False)
    write('source-and-verification.json', {'candidate_id':CANDIDATE,'model_payload_sha256':manifest['payload_sha256'],
        'capture_id':CAPTURE,'data_id':meta['data_id'],'data':data, 'implementation_original':meta['implementation_sha256'],
        'implementation_current':implementation,'implementation_mismatches':mismatch,
        'fit_identities_exact':True,'calibration_identities_exact':True,'latest_forecasts_exact':exact,
        'training_means_exact':True,'baseline_mse_exact':True,'base_model_calibration_mse_exact':True,
        'model_audit':bundle.audit,'latest_original_rejections':original['rejections'],
        'script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()})
    np.savez_compressed(ROOT/'reconstructed-samples.npz', yfit=yfit,ycal=ycal,
        cal_dates=np.array([sessions[int(r)] for r in cr]), cal_symbols=np.array([symbols[int(c)] for c in cc]),
        cal_close=market['close'][cr,cc],cal_atr=market['atr'][cr,cc],
        latest_symbols=np.array([symbols[int(c)] for c in ci]), latest_close=market['close'][signal,ci],latest_atr=market['atr'][signal,ci],
        **{'cal_'+k:v for k,v in pred.items()}, **{'latest_'+k:v for k,v in latest.items()})
    log('all identity/prediction/MSE exact checks passed; checkpoint saved')

def analyze():
    z=np.load(ROOT/'reconstructed-samples.npz')
    y=z['ycal']; trainmean=z['yfit'].mean(axis=0)
    dates=z['cal_dates']; unique=np.unique(dates)
    models=[key[4:] for key in z.files if key.startswith('cal_') and key[4:] not in ('dates','symbols','close','atr')]
    date_rows=[]; summary=[]; decile_rows=[]; decomposition=[]; latest_rows=[]
    for period in ('cal','latest'):
        close=z[period+'_close']; atr=z[period+'_atr']
        # Isolated 2000 USD reference-price feasibility; not actual portfolio membership.
        qty=np.minimum(np.floor(400/(close*1.002)), np.floor(10/(2*atr))).astype(int)
        tradable=qty>=1
        for model in models:
            p=z[period+'_'+model]
            for hi,horizon in enumerate(HORIZONS):
                gross=p[:,hi]; fee=.004+.002*gross; net=gross-fee; risk=.5*p[:,hi+3]; score=net-risk
                decomposition.append({'period':period,'model':model,'horizon':horizon,'count':len(p),
                    'positive_gross':int((gross>0).sum()),'positive_after_fees':int((net>0).sum()),
                    'positive_after_risk':int((score>0).sum()),'reference_one_share_feasible':int(tradable.sum()),
                    'positive_score_and_reference_feasible':int(((score>0)&tradable).sum()),
                    'gross_mean':float(gross.mean()),'fee_mean':float(fee.mean()),'net_mean':float(net.mean()),
                    'half_downside_mean':float(risk.mean()),'score_mean':float(score.mean()),
                    'score_min':float(score.min()),'score_max':float(score.max())})
                if period=='latest':
                    for i,symbol in enumerate(z['latest_symbols']):
                        latest_rows.append({'symbol':symbol,'model':model,'horizon':horizon,'predicted_return':gross[i],
                            'fee_return_deduction':fee[i],'return_after_fees':net[i],'predicted_downside':p[i,hi+3],
                            'half_downside_penalty':risk[i],'score':score[i],'reference_quantity':qty[i]})
                    continue
                for head in (hi,hi+3):
                    records=[]
                    for date in unique:
                        ix=dates==date; actual=y[ix,head]; predicted=p[ix,head]
                        ic=float(spearmanr(actual,predicted).statistic) if np.ptp(actual)>0 and np.ptp(predicted)>0 else np.nan
                        record={'model':model,'horizon':horizon,'head':LABEL_NAMES[head],'session':date,'count':int(ix.sum()),
                            'actual_mean':float(actual.mean()),'predicted_mean':float(predicted.mean()),
                            'bias':float((predicted-actual).mean()),'mse':float(np.mean((predicted-actual)**2)),
                            'training_mean_baseline_mse':float(np.mean((actual-trainmean[head])**2)),
                            'same_date_mean_oracle_mse':float(np.mean((actual-actual.mean())**2)),
                            'spearman_ic':ic,'ic_count':int(ix.sum()) if np.isfinite(ic) else 0}
                        records.append(record);date_rows.append(record)
                    rows=pd.DataFrame(records)
                    summary.append({'model':model,'horizon':horizon,'head':LABEL_NAMES[head],'count':len(p),
                        'date_count':len(unique),'actual_mean':float(y[:,head].mean()),'predicted_mean':float(p[:,head].mean()),
                        'bias':float((p[:,head]-y[:,head]).mean()),'mse':float(np.mean((p[:,head]-y[:,head])**2)),
                        'training_mean_baseline':float(trainmean[head]),
                        'training_mean_baseline_mse':float(np.mean((y[:,head]-trainmean[head])**2)),
                        'calibration_mean_oracle_mse':float(np.mean((y[:,head]-y[:,head].mean())**2)),
                        'daily_ic':bootstrap(rows.spearman_ic),
                        'daily_mse_improvement':bootstrap(rows.training_mean_baseline_mse-rows.mse)})
                for rank_by,rank_value in [('predicted_return',gross),('risk_adjusted_score',score)]:
                    for date in unique:
                        indices=np.flatnonzero(dates==date)
                        # Stable deterministic ranks; report tie count, small daily samples 9-10 per decile.
                        order=indices[np.argsort(rank_value[indices],kind='stable')]
                        for decile,selected in enumerate(np.array_split(order,10),1):
                            feasible=selected[tradable[selected]]
                            decile_rows.append({'model':model,'horizon':horizon,'rank_by':rank_by,'session':date,
                                'decile':decile,'count':len(selected),'reference_feasible_count':len(feasible),
                                'unique_forecasts_on_date':len(np.unique(rank_value[indices])),
                                'predicted_return':float(gross[selected].mean()),'actual_return':float(y[selected,hi].mean()),
                                'actual_downside':float(y[selected,hi+3].mean()),'predicted_downside':float(p[selected,hi+3].mean()),
                                'predicted_score':float(score[selected].mean()),
                                'actual_after_proportional_fees':float((y[selected,hi]*.998-.004).mean()),
                                'reference_feasible_actual_return':float(y[feasible,hi].mean()) if len(feasible) else np.nan})
    pd.DataFrame(date_rows).to_csv(ROOT/'per-date-head-metrics.csv',index=False)
    deciles=pd.DataFrame(decile_rows);deciles.to_csv(ROOT/'per-date-deciles.csv',index=False)
    decile_summary=[]
    for (model,horizon,rank_by,decile), group in deciles.groupby(['model','horizon','rank_by','decile']):
        decile_summary.append({'model':model,'horizon':int(horizon),'rank_by':rank_by,'decile':int(decile),
            'count':int(group['count'].sum()),'reference_feasible_count':int(group.reference_feasible_count.sum()),
            'equal_date_actual_return':float(group.actual_return.mean()),
            'equal_date_predicted_return':float(group.predicted_return.mean()),
            'equal_date_actual_downside':float(group.actual_downside.mean()),
            'equal_date_predicted_downside':float(group.predicted_downside.mean()),
            'equal_date_after_fees':float(group.actual_after_proportional_fees.mean()),
            'reference_feasible_equal_date_return':float(group.reference_feasible_actual_return.mean()),
            'actual_return_bootstrap':bootstrap(group.actual_return)})
    spread=[]
    for (model,horizon,rank_by),group in deciles.groupby(['model','horizon','rank_by']):
        pivot=group.pivot(index='session',columns='decile',values='actual_return')
        spread.append({'model':model,'horizon':int(horizon),'rank_by':rank_by,
            'top_minus_bottom':bootstrap(pivot[10]-pivot[1])})
    write('metrics-summary.json', summary)
    write('decile-summary.json',decile_summary)
    write('decile-spreads.json',spread)
    write('score-decomposition.json',decomposition)
    pd.DataFrame(latest_rows).to_csv(ROOT/'latest-all-model-forecasts.csv',index=False)
    log('completed model/head/date metrics, deciles, block intervals and latest comparisons')
    for row in decomposition:
        if row['horizon']==5:
            log(str(row))

if __name__=='__main__':
    attempt={'started_at':pd.Timestamp.now(tz='UTC').isoformat(),'status':'running','refit':False}
    write('attempt.json',attempt)
    try:
        with warnings.catch_warnings(record=True) as caught, threadpool_limits(limits=2):
            warnings.simplefilter('always')
            if '--analyze-only' not in sys.argv:
                rebuild()
            analyze()
            write('runtime-warnings.json',[{'category':x.category.__name__,'message':str(x.message)} for x in caught])
        attempt['status']='complete'
    except BaseException as exc:
        attempt.update(status='failed',error_type=type(exc).__name__,error=str(exc),traceback=traceback.format_exc())
        write('failed-attempt-'+str(int(time.time()))+'.json',attempt)
        raise
    finally:
        attempt['elapsed_seconds']=time.time()-START
        attempt['finished_at']=pd.Timestamp.now(tz='UTC').isoformat()
        write('attempt.json',attempt)
