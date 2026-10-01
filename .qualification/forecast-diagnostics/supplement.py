"""Supplement saved numerical evidence without reloading source histories."""
import hashlib
import json
from pathlib import Path
import numpy as np
import pandas as pd
from run_diagnostics import bootstrap

root=Path(__file__).resolve().parent
z=np.load(root/'reconstructed-samples.npz')
dates=z['cal_dates'];y=z['ycal']
models=['ridge','extra_trees','hist_gradient_boosting','multi_head_mlp','equal_ensemble','calibrated_ensemble']
daily=[];selected=[];tails=[]
for model in models:
    p=z['cal_'+model]
    for hi,horizon in enumerate([1,3,5]):
        net=p[:,hi]*.998-.004
        penalty=.5*p[:,hi+3]
        score=net-penalty
        for date in np.unique(dates):
            ix=dates==date
            daily.append({'model':model,'horizon':horizon,'session':date,'count':int(ix.sum()),
                'predicted_return_mean':float(p[ix,hi].mean()),'fee_deduction_mean':float((.004+.002*p[ix,hi]).mean()),
                'return_after_fees_mean':float(net[ix].mean()),'half_downside_mean':float(penalty[ix].mean()),
                'score_mean':float(score[ix].mean()),'score_max':float(score[ix].max()),
                'positive_gross':int((p[ix,hi]>0).sum()),'positive_after_fees':int((net[ix]>0).sum()),
                'positive_after_risk':int((score[ix]>0).sum())})
        for stage,mask in [('positive_return',p[:,hi]>0),('positive_after_fees',net>0),('positive_full_score',score>0)]:
            daily_means=[float((y[(dates==date)&mask,hi]*.998-.004).mean())
                         for date in np.unique(dates) if ((dates==date)&mask).any()]
            selected.append({'model':model,'horizon':horizon,'stage':stage,'count':int(mask.sum()),
                'dates_with_members':len(daily_means),
                'pooled_actual_return':float(y[mask,hi].mean()) if mask.any() else None,
                'pooled_actual_after_fees':float((y[mask,hi]*.998-.004).mean()) if mask.any() else None,
                'equal_selected_date_after_fees':float(np.mean(daily_means)) if daily_means else None,
                'warning':'Descriptive membership; dates with no selection excluded; not account simulation.'})
        errors=(p[:,hi]-y[:,hi])**2
        n=max(1,int(np.ceil(len(errors)*.01)))
        tails.append({'model':model,'horizon':horizon,'top_one_percent_error_rows':n,
            'top_one_percent_share_total_squared_error':float(np.sort(errors)[-n:].sum()/errors.sum())})

extremes=[]
for hi,horizon in enumerate([1,3,5]):
    order=np.argsort(y[:,hi])
    for index in list(order[:10])+list(order[-10:]):
        extremes.append({'horizon':horizon,'session':str(dates[index]),'symbol':str(z['cal_symbols'][index]),
            'actual_return':float(y[index,hi]),'actual_downside':float(y[index,hi+3])})

pd.DataFrame(daily).to_csv(root/'per-date-score-decomposition.csv',index=False)
pd.DataFrame(extremes).to_csv(root/'extreme-target-rows.csv',index=False)
(root/'positive-membership-outcomes.json').write_text(json.dumps(selected,indent=2,allow_nan=False),encoding='utf-8')
(root/'tail-error-concentration.json').write_text(json.dumps(tails,indent=2,allow_nan=False),encoding='utf-8')

# Fresh post-run structural checks independently inspect persisted evidence coverage.
checks={
 'calibration_rows':len(y),'calibration_dates':len(np.unique(dates)),'latest_symbols':len(z['latest_symbols']),
 'date_head_rows':len(pd.read_csv(root/'per-date-head-metrics.csv')),
 'date_decile_rows':len(pd.read_csv(root/'per-date-deciles.csv')),
 'latest_forecast_rows':len(pd.read_csv(root/'latest-all-model-forecasts.csv')),
 'date_score_rows':len(daily),
 'all_saved_predictions_finite':all(np.isfinite(z[prefix+model]).all() for prefix in ['cal_','latest_'] for model in models),
 'calibrated_equals_extra_trees_all_heads':all(np.array_equal(z[prefix+'calibrated_ensemble'],z[prefix+'extra_trees']) for prefix in ['cal_','latest_']),
 'six_heads_purged_and_complete':bool(np.isfinite(y).all()),
 'all_decile_samples_accounted_for':bool(pd.read_csv(root/'per-date-deciles.csv').groupby(['model','horizon','rank_by','session'])['count'].sum().eq(96).all()),
}
assert checks['date_head_rows']==6*6*246
assert checks['date_decile_rows']==6*3*2*10*246
assert checks['latest_forecast_rows']==6*3*2878
assert checks['date_score_rows']==6*3*246
assert all(checks[k] for k in ['all_saved_predictions_finite','calibrated_equals_extra_trees_all_heads','six_heads_purged_and_complete','all_decile_samples_accounted_for'])
checks.update(status='passed',failed_checks=[],missing_tests=[
 'No untouched later holdout exists in this saved September 18 candidate capture.',
 'No realized latest outcomes, broker fills or portfolio performance are inferred.',
 'Sampled calibration covers 96 stocks/date, not every eligible calibration stock.',
 'Extreme targets remain unaltered; corporate-action/vendor validation is not performed.'])
(root/'verification.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
inventory={p.name:{'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
           for p in root.iterdir() if p.is_file() and p.name!='artifact-inventory.json'}
(root/'artifact-inventory.json').write_text(json.dumps(inventory,indent=2),encoding='utf-8')
print(json.dumps(checks,indent=2))
print('H5 selected-outcome summaries:')
for row in selected:
    if row['horizon']==5 and row['stage']=='positive_full_score': print(row)
print('Extreme h5 rows:', [r for r in extremes if r['horizon']==5][-3:])
