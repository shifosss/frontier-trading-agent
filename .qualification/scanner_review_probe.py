from pathlib import Path
import json
import runpy
import pandas as pd
from frontier.scanner import forward_diagnostics
from frontier.scan_data import normalize_chart
helpers=runpy.run_path('tests/test_scanner.py')
spec, make=helpers['_spec'], helpers['_frame']
stock, benchmark=spec(), spec('SPY', asset_type='etf')
frame=pd.concat([make(stock),make(benchmark)],ignore_index=True)
original=forward_diagnostics(frame,[stock,benchmark], '2025-07-01T21:00Z', {'USD':10000})
cohort=original['cohorts'][0]
delayed=frame.copy()
mask=(delayed.symbol=='SPY') & (delayed.session==cohort['entry_session'])
delayed.loc[mask,'available_at'] += pd.Timedelta(days=2)
changed=forward_diagnostics(delayed,[stock,benchmark], '2025-07-01T21:00Z', {'USD':10000})
benchmark_result={'entry':cohort['entry_session'],'benchmark_available':str(delayed.loc[mask,'available_at'].iloc[0]),'benchmark_return_before':cohort['benchmark_return'],'benchmark_return_after':changed['cohorts'][0]['benchmark_return'],'excess_return_after':changed['cohorts'][0]['excess_return']}
payload={'chart':{'error':None,'result':[{'meta':{'symbol':'DIFFERENT','currency':'USD'},'timestamp':[pd.Timestamp('2025-06-30T13:30Z').timestamp()],'indicators':{'quote':[{'close':[100.0],'high':[101.0],'low':[99.0],'volume':[10000]}],'adjclose':[{'adjclose':[100.0]}]}}]}}
wrong_symbol=normalize_chart(payload,stock,'2025-07-01T21:00Z')
result={'late_benchmark':benchmark_result,'provider_wrong_symbol_accepted_as':wrong_symbol.symbol.iloc[0]}
Path('.qualification/scanner_review_probe.json').write_text(json.dumps(result,indent=2))
print(json.dumps(result,indent=2))
