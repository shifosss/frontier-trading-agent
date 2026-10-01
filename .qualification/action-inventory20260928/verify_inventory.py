"""Independent sample and reconstruction checks; does not rerun the inventory."""
from pathlib import Path
from itertools import product
from collections import defaultdict
import csv,hashlib,json,math
import numpy as np
import pandas as pd
from frontier.historical_data import _reported_split_factors
ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parent.parent
rows=[json.loads(line) for line in (ROOT/'events.jsonl').read_text().splitlines()]
coverage=[json.loads(line) for line in (ROOT/'source-coverage.jsonl').read_text().splitlines()]
definition=json.loads((ROOT/'definition.json').read_text())
summary=json.loads((ROOT/'summary.json').read_text())
sample=list(csv.DictReader((ROOT/'validation-sample.csv').open(encoding='utf-8',newline='')))
assert len(rows)==7143 and len(coverage)==8234 and all(r['status']=='verified' for r in coverage)
assert sum(r['raw_split_count'] for r in coverage)==len(rows)
assert len({(r['symbol'],r['event_key']) for r in rows})==len(rows)
groups=defaultdict(list)
for row in rows:
 year=int(row['effective_session'][:4]); era=next(label for end,label in [(2009,'<=2009'),(2019,'2010-2019'),(2023,'2020-2023'),(2026,'2024-2026')] if year<=end)
 factor=row['new_shares_per_old']; magnitude=max(factor,1/factor)
 liquidity=row['prior20_native_dollar_volume_proxy']
 bucket='unavailable' if liquidity is None else '<1000000' if liquidity<1_000_000 else '>=1000000'
 cell='|'.join((row['currency'],row['direction'],era,'<=2' if magnitude<=2 else '>2',bucket))
 key=f"{definition['followup_sample']['seed']}|{row['symbol']}|{row['effective_session']}|{row['numerator']}:{row['denominator']}"
 rank=hashlib.sha256(key.encode()).hexdigest()
 groups[cell].append((rank,row))
assert len(sample)==len(groups)==91
checks=[]
for chosen in sample:
 candidates=sorted(groups[chosen['stratum']],key=lambda pair:pair[0]); rank,row=candidates[0]
 assert chosen['sample_rank_sha256']==rank and chosen['symbol']==row['symbol'] and chosen['effective_session']==row['effective_session']
 assert int(chosen['stratum_events'])==len(candidates)
 path=WORKSPACE/'data/historical/capture-workspace'/row['source_path']
 raw=path.read_bytes(); assert hashlib.sha256(raw).hexdigest()==row['source_sha256']
 result=json.loads(raw)['chart']['result'][0]
 prefixes=[prefix for prefix in ('prior','effective') if row.get(prefix+'_session')]
 dates=pd.Index([row[prefix+'_session'] for prefix in prefixes])
 factors,_=_reported_split_factors(result,dates,pd.Timestamp(row['captured_at']))
 for prefix,factor in zip(prefixes,factors):
  assert math.isclose(row[prefix+'_reported_later_split_factor'],float(factor),rel_tol=1e-12,abs_tol=0)
 checks.append({'stratum':chosen['stratum'],'symbol':row['symbol'],'effective_session':row['effective_session'],'hash_rank_minimum':True,'normalizer_helper_factors_match':True,'tested_boundaries':len(prefixes)})
volume_checks=0
for row in rows:
 for prefix in ('prior','effective'):
  close=row.get(prefix+'_provider_close'); volume=row.get(prefix+'_provider_volume'); nclose=row.get(prefix+'_reconstructed_nominal_close');nvolume=row.get(prefix+'_reconstructed_nominal_volume')
  if all(value is not None for value in (close,volume,nclose,nvolume)):
   assert math.isclose(close*volume,nclose*nvolume,rel_tol=1e-12,abs_tol=1e-12);volume_checks+=1
cells={'|'.join(parts) for parts in product(['USD','CAD'],['forward','reverse'],['<=2009','2010-2019','2020-2023','2024-2026'],['<=2','>2'],['<1000000','>=1000000','unavailable'])}
assert len(cells)==96
result={'all_source_coverage_reconciled':True,'all_event_counts_reconciled':True,'unique_event_keys':7143,'sample_minimum_ranks_verified':91,'sample_helper_factor_checks':checks,'price_volume_product_checks':volume_checks,'empty_predeclared_cells':sorted(cells-set(groups)),'network_requests':0,'trading_outputs_read':False,'corrections_applied':False}
(ROOT/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({k:v for k,v in result.items() if k!='sample_helper_factor_checks'},indent=2))
