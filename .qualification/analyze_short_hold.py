"""Summarize every declared short-hold result; never selects a deployed rule."""
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
RUN='90af4c840aad48f7ab58fba7a682f96a'
BASE='577a24e71a844022b3ac86ca66e32c34'
run_root=ROOT/'artifacts/historical-lab/runs'/RUN
study=json.loads((run_root/'summary.json').read_bytes())
base=json.loads((run_root.parent/BASE/'summary.json').read_bytes())
report_root=ROOT/'artifacts/historical-lab/reports'/RUN
report_root.mkdir(parents=True,exist_ok=True)

def pct(x):
    return 'incomplete' if x is None else f'{100*x:.2f}%'

def number(x):
    return '—' if x is None else f'{x:.2f}'

def view(row):
    keys=('currency','budget','cost_bps','strategy','horizon','status','ending_equity','total_return','max_drawdown','cagr','trades','fees','missing','first_session','last_session','trade_metrics','period_metrics','profit_concentration')
    value={key:row[key] for key in keys if key in row}
    if 'folds' in row:
        value['fold_count']=len(row['folds'])
        value['selected_rules']=dict(Counter(f"{f['selected_strategy']}:{f['selected_horizon']}" for f in row['folds']))
    return value

groups=[]
for currency in ('USD','CAD'):
    for budget in (500,2000,10000,100000):
        for cost in (20,40,100):
            rows=[r for r in study['portfolios'] if (r['currency'],r['budget'],r['cost_bps'])==(currency,budget,cost)]
            complete=[r for r in rows if r['status']=='complete']
            groups.append({'currency':currency,'budget':budget,'cost_bps':cost,'statuses':dict(Counter(r['status'] for r in rows)),
                'profitable':sum(r['total_return']>0 for r in complete),
                'profitable_and_under_30pct_dd':sum(r['total_return']>0 and r['max_drawdown']<=.3 for r in complete),
                'best_exploratory_return':view(max(complete,key=lambda r:r['total_return'])) if complete else None,
                'worst_exploratory_return':view(min(complete,key=lambda r:r['total_return'])) if complete else None})
base_walk={(r['currency'],r['budget'],r['cost_bps']):r for r in base['walk_forward']}
walk=[]
for row in study['walk_forward']:
    old=base_walk[(row['currency'],row['budget'],row['cost_bps'])]
    walk.append({**view(row),'legacy':{k:old[k] for k in ('status','total_return','max_drawdown','trades')}})
analysis={'run_id':RUN,'source_run_id':BASE,'code_identity':study['definition']['code_identity'],
    'data_cutoff':study['as_of'],'created_at':study['created_at'],
    'capture':{k:study['capture'][k] for k in ('discovered','usable','rows','markets')},
    'statuses':{key:dict(Counter(r['status'] for r in study[key])) for key in ('portfolios','walk_forward','benchmarks')},
    'fixed_groups':groups,'rolling':walk,
    'missing':dict(Counter(m for key in ('portfolios','walk_forward') for r in study[key] for m in r['missing']))}
(report_root/'analysis.json').write_text(json.dumps(analysis,indent=2,allow_nan=False),'utf-8')
lines=['# Daily short-hold historical study','',f'Run `{RUN}`, completed {study["created_at"]}. The owner requested that the agent run the study; no manual launch was needed. This report evaluates the daily 1/3/5-session lane and preserves every declared attempt.','',
'## Scope and interpretation','',
f'The study reused the exact original data cutoff ({study["as_of"]}), universe and **{study["capture"]["usable"]:,} usable histories / {study["capture"]["rows"]:,} daily bars** from `{BASE}`. No new download or issuer-data repair was inserted. Requested history starts in 2000, but individual listings have shorter histories. The 200 failed captures remain recorded. Current-listed membership and current-vintage adjusted prices introduce survivorship and availability limitations.','',
'Ten rule families × three holding periods × four native-currency balances × three round-trip costs × two markets produce **720 fixed portfolios**, plus **24 rolling-selection accounts**. Signals are screened daily; a close signal enters at the next close and each filled position exits after 1, 3 or 5 sessions. These are repeated overnight/daily trades, not five-year stock holdings or an hourly simulation.','',
'The selector uses the preceding 756 sessions at 100-bps costs and fixes the chosen rule for a 252-session evaluation block. Positions still change daily inside each block. Cash is a valid selection when no candidate qualifies. Whole-share sizing, dated settlement and independent cash/position management apply. Nominal sizing and synthetic adjusted-return marks are exploratory, not a complete corporate-action payment ledger.','',
'## All rolling accounts','',
'Each row is a separate simulated account. Return is cumulative over its stated historical evaluation interval; drawdown uses daily equity. Incomplete rows have no profitability aggregate. Trade counts on incomplete rows cover only the observed prefix.','',
'| Market | Start | Round-trip bps | Status | Return | Max drawdown | Trades | Trades / 5 sessions | Mean hold sessions | Profitable months |',
'| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for row in walk:
    t=row['trade_metrics']; monthly=row.get('period_metrics',{}).get('monthly',{})
    lines.append(f"| {row['currency']} | {row['budget']:,.0f} | {row['cost_bps']} | {row['status']} | {pct(row['total_return'])} | {pct(row['max_drawdown'])} | {row['trades']:,} | {number(t.get('trades_per_week'))} | {number(t.get('mean_holding_sessions'))} | {pct(monthly.get('profitable_fraction')) if row['status']=='complete' else '—'} |")
lines+=['','## Full fixed-rule grid','',
'These are exploratory comparisons after seeing the full historical period, not rules selected using only information available before that period. Positive/under-30% counts are descriptive screens and do not establish deployable edge. No failed path is omitted.','',
'| Market | Start | Round-trip bps | Complete / 30 | Incomplete | Positive return | Positive and ≤30% drawdown |',
'| --- | ---: | ---: | ---: | ---: | ---: | ---: |']
for g in groups:
    lines.append(f"| {g['currency']} | {g['budget']:,.0f} | {g['cost_bps']} | {g['statuses'].get('complete',0)} | {g['statuses'].get('incomplete',0)} | {g['profitable']} | {g['profitable_and_under_30pct_dd']} |")
lines+=['','## Missing-data failures','']
for missing,count in analysis['missing'].items():
    lines.append(f'- `{missing}` invalidated {count} declared account paths.')
if not analysis['missing']:
    lines.append('No required-mark failure occurred in these declared paths; that does not establish complete historical source coverage.')
lines+=['','## Evidence and limits','',
f'- Full result and compact summary: `artifacts/historical-lab/runs/{RUN}/`.',
f'- All result groups and comparison with the old rolling accounts: `artifacts/historical-lab/reports/{RUN}/analysis.json`.',
'- Fixed-grid reports retain daily equity and aggregate trade statistics. Rolling accounts retain all completed trades; detailed fixed views can be deterministically replayed.',
'- Weekly/monthly summaries include cash periods and partial first/last calendar periods. No monthly contributions, fixed commissions, FX conversion costs or taxes are modeled.',
'- A 30% training drawdown filter does not enforce a future loss cap. These results do not change the frozen paper account or authorize live execution.',
'- Source reuse validates membership, capture count and individual raw hashes. This older source lacks an originally frozen capture-index digest; the new run explicitly records that limitation and freezes its own index digest.',
'- See [methodology](historical-research.md), [cadence](trading-cadence.md), [sources](historical-research-sources.md) and [verification](code-quality-review.md).','']
(ROOT/'docs/short-hold-research-results.md').write_text('\n'.join(lines),'utf-8')
print(json.dumps({k:v for k,v in analysis.items() if k not in ('fixed_groups','rolling','capture')},indent=2))
print(json.dumps({'rolling':walk,'fixed_counts':[{k:v for k,v in g.items() if not k.startswith(('best_','worst_'))} for g in groups]},indent=2))
