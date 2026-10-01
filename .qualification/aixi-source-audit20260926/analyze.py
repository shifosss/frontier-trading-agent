"""Offline comparison; does not create a corrected source or rerun models."""
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal
import hashlib,json
import numpy as np
import pandas as pd
from frontier.historical_data import read_history
ROOT=Path(__file__).resolve().parent
WORKSPACE=ROOT.parent.parent
RUN='90af4c840aad48f7ab58fba7a682f96a'
def digest(b):return hashlib.sha256(b).hexdigest()
def dump(name,v):(ROOT/name).write_text(json.dumps(v,indent=2,allow_nan=False),encoding='utf-8')
index_path=WORKSPACE/'artifacts/historical-lab/runs'/RUN/'capture-index.json'
record=next(r for r in json.loads(index_path.read_text()) if r['symbol']=='AIXI')
raw_path=WORKSPACE/'data/historical/capture-workspace'/record['path']
raw=raw_path.read_bytes();assert digest(raw)==record['sha256']
(ROOT/'frozen-yahoo.raw.json').write_bytes(raw)
result=json.loads(raw)['chart']['result'][0]
f=read_history(WORKSPACE/'data/historical/capture-workspace',record).rename(columns={'close':'normalized_close','high':'normalized_high','low':'normalized_low','volume':'normalized_volume'})
quote=result['indicators']['quote'][0]
y=pd.DataFrame(quote);y['provider_adjclose']=result['indicators']['adjclose'][0]['adjclose'];y['timestamp']=result['timestamp']
y['source_timestamp_utc']=pd.to_datetime(y.timestamp,unit='s',utc=True).astype(str)
y['session']=pd.to_datetime(y.timestamp,unit='s',utc=True).dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
y=y.rename(columns={k:'yahoo_'+k for k in quote})
f=f.merge(y,on='session',validate='one_to_one')
source_meta=[]
for adjustment in ('raw','split'):
 meta=json.loads((ROOT/f'alpaca-{adjustment}-1.capture.json').read_text())
 content=(ROOT/meta['raw_file']).read_bytes();assert digest(content)==meta['sha256']
 p=json.loads(content);assert p['next_page_token'] is None and p['symbol']=='AIXI'
 a=pd.DataFrame(p['bars']);a['session']=pd.to_datetime(a.t,utc=True).dt.tz_convert('America/New_York').dt.strftime('%Y-%m-%d')
 a=a.rename(columns={k:f'alpaca_{adjustment}_{k}' for k in a.columns if k!='session'})
 f=f.merge(a,on='session',how='outer',validate='one_to_one',indicator='merge_status')
 assert (f.merge_status=='both').all();f=f.drop(columns='merge_status');source_meta.append(meta)
f=f.sort_values('session').reset_index(drop=True)
f['yahoo_adjusted_return']=f.adjusted_close.pct_change();f['yahoo_nominal_return']=f.normalized_close.pct_change();f['alpaca_raw_return']=f.alpaca_raw_c.pct_change();f['alpaca_split_return']=f.alpaca_split_c.pct_change()
f['yahoo_adj_to_alpaca_split']=f.adjusted_close/f.alpaca_split_c
f['normalized_to_alpaca_raw']=f.normalized_close/f.alpaca_raw_c
f.to_csv(ROOT/'all-886-session-comparison.csv',index=False)
f.loc[f.session>='2026-08-10'].to_csv(ROOT/'surrounding-window.csv',index=False)
f.loc[f.session.isin(['2024-08-22','2024-08-23','2026-05-08','2026-05-11','2026-09-04','2026-09-08'])].to_csv(ROOT/'three-action-boundaries.csv',index=False)
tails=pd.concat([f.nlargest(12,'yahoo_adjusted_return').assign(selection='12_largest'),f.nsmallest(12,'yahoo_adjusted_return').assign(selection='12_smallest')])
tails.to_csv(ROOT/'both-directions-largest-12.csv',index=False)
extreme=pd.read_csv(WORKSPACE/'.qualification/forecast-diagnostics/extreme-target-rows.csv');extreme=extreme[extreme.symbol=='AIXI']
print(extreme.to_dict('records'))
entry=f.loc[f.session=='2026-08-31'].iloc[0];exit=f.loc[f.session=='2026-09-08'].iloc[0]
frozen_label=float(np.float32(exit.adjusted_close/entry.adjusted_close-1))
# Match the original model target dtype; independent exact-money illustration uses Decimal.
exact=Decimal('3.26')/(Decimal('0.503')*Decimal(7))-Decimal(1)
pre=f[f.session<'2026-09-08'];post=f[f.session>='2026-09-08']
res={
 'completed_at':datetime.now(timezone.utc).isoformat(),'status':'confirmed inconsistent ADS units at September 8 reverse exchange; no corrected dataset or strategy result produced',
 'source_record':record,'capture_index_sha256':digest(index_path.read_bytes()),'frozen_payload_verified':True,'frozen_yahoo_meta':result['meta'],'frozen_events':result.get('events',{}),
 'independent_sources':source_meta,'all_three_sources_session_count':len(f),'first_session':f.session.min(),'last_session':f.session.max(),
 'label':{'signal_session':'2026-08-28','entry_session':'2026-08-31','exit_session':'2026-09-08','five_post_entry_sessions':['2026-09-01','2026-09-02','2026-09-03','2026-09-04','2026-09-08'],'frozen_entry_adjusted_close':float(entry.adjusted_close),'frozen_exit_adjusted_close':float(exit.adjusted_close),'frozen_float32_return':frozen_label,'saved_diagnostic_rows':extreme.to_dict('records'),'independent_raw_entry':float(entry.alpaca_raw_c),'independent_raw_exit':float(exit.alpaca_raw_c),'independent_split_entry':float(entry.alpaca_split_c),'independent_split_exit':float(exit.alpaca_split_c),'common_unit_gross_price_return_decimal':str(exact),'qualification':'Price-unit arithmetic only. Not a corrected account: fees, actual cash in lieu, fractional positions, settlement and execution omitted.'},
 'unit_ratio_comparison':{name:{'rows':len(g),'adjusted_to_independent_split_median':float(g.yahoo_adj_to_alpaca_split.median()),'adjusted_to_independent_split_min':float(g.yahoo_adj_to_alpaca_split.min()),'adjusted_to_independent_split_max':float(g.yahoo_adj_to_alpaca_split.max()),'normalized_to_independent_raw_median':float(g.normalized_to_alpaca_raw.median())} for name,g in [('before_sep8',pre),('on_after_sep8',post)]},
 'yahoo_reported_close_equals_adjclose_all_rows':bool((f.yahoo_close==f.provider_adjclose).all()),
 'retained_tails':{'selection':'12 largest and 12 smallest frozen adjusted daily returns, selected before independent-bar comparison; all 886 rows also retained','up_count':12,'down_count':12},
 'limitations':['Alpaca data downloaded later and may contain revisions; source close/volume differences remain in full table','Provider raw and split daily bars are aggregate data, not proof of closing-auction fills','No primary trade tape or broker-specific depositary fee and cash-in-lieu posting obtained','No complete all-company action registry; this is one issuer audit','No automatic deletion, rescaling, model refit, portfolio rerun or promotion'],
}
dump('findings.json',res)
dump('inventory.json',[{'file':p.name,'sha256':digest(p.read_bytes()),'bytes':p.stat().st_size} for p in sorted(ROOT.iterdir()) if p.is_file() and p.name!='inventory.json'])
print(json.dumps({k:res[k] for k in ('all_three_sources_session_count','label','unit_ratio_comparison','yahoo_reported_close_equals_adjclose_all_rows')},indent=2))
print(tails[['session','yahoo_adjusted_return','alpaca_split_return','selection']].to_string(index=False))
