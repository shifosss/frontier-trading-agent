import json
import shutil
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from frontier.data import import_dataset, list_datasets
from frontier.domain import RunConfig, StrategyConfig
from frontier.replay import run_research, code_identity
from frontier.campaign import run_campaign, verify_replay
from frontier.observation import freeze_run, observe
from frontier.store import Registry

root=Path.cwd()
data=root/'data/datasets'
artifacts=root/'artifacts'
registry=Registry(root/'data/frontier.sqlite')
fixture=next(d for d in list_datasets(data) if d.mode=='synthetic_fixture')
daily='3c041e7b3772e7662ec019cf4fb4101e2020695169dd7f6164e54d3431259e5a'
hourly='c45b18a7ce3ad18a53d18e5534ff1148aa46861bec3ec5bc0a802c524a167f81'
evidence={'created_at':datetime.now(timezone.utc).isoformat(),'code_identity':code_identity(),'lanes':{},'revalidated_model_runs':[]}
for name,id,incomplete in [('synthetic',fixture.dataset_id,False),('historical_daily',daily,True),('historical_hourly',hourly,True)]:
    record=run_research(RunConfig(dataset_id=id,strategy=StrategyConfig(family='trend' if name.endswith('hourly') else 'passive',name=f'{name} final validation',lookback=20,rebalance_every=7 if name.endswith('hourly') else 5),allow_incomplete_actions=incomplete),data,registry,artifacts)
    verified=verify_replay(record['id'],data,registry)
    assert verified['identical'],verified
    summary=record['summary']
    for currency,native in summary['native_market_contribution'].items():
        attributed=sum(v[currency] for v in summary['per_market_contribution'].values())
        assert abs(attributed-native)<1e-7,(currency,attributed,native)
    evidence['lanes'][name]={'run_id':record['id'],'summary':summary,'verification':verified}
    if name!='historical_hourly':
        tournament=run_campaign(id,data,registry,artifacts,allow_incomplete_actions=incomplete)
        assert len(tournament['run_ids'])==11
        assert all(registry.get_run(i)['status']=='COMPLETED' for i in tournament['run_ids'])
        evidence['lanes'][name]['campaign_id']=tournament['campaign_id']
        evidence['lanes'][name]['completed_trials']=11
    print(name,record['id'],'reproduced and reconciled',flush=True)
for campaign_id in ['25342cad16ea475fbc7e6fe791274400','787940fbcd694c7194724efd76324925']:
    campaign=json.loads((artifacts/'model-campaigns'/campaign_id/'campaign.json').read_text(encoding='utf-8'))
    for attempt in campaign['attempts']:
        record=run_research(RunConfig.model_validate(attempt['config']),data,registry,artifacts)
        evidence['revalidated_model_runs'].append({'campaign_id':campaign_id,'attempt':attempt['number'],'original_run_id':attempt['run_id'],'revalidated_run_id':record['id']})
# Validate observations against actual retained prices, explicitly historical at today's time.
source=root/'data/imports/observation-prefix-through-2026-09-16'
shutil.copytree(data/daily/'source',source,dirs_exist_ok=True)
metadata=json.loads((source/'dataset.json').read_text(encoding='utf-8'))
metadata['name']='SPY + XIU historical observation prefix through 2026-09-16'
metadata['limitations'].append('Prefix derived today for historical observation validation; not a past prospective freeze')
(source/'dataset.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
bars=pd.read_csv(source/'bars.csv')
bars=bars.loc[pd.to_datetime(bars.event_time,utc=True).dt.date<=pd.Timestamp('2026-09-16').date()]
bars.to_csv(source/'bars.csv',index=False)
manifest=import_dataset(source,data)
record=run_research(RunConfig(dataset_id=manifest.dataset_id,strategy=StrategyConfig(family='passive',rebalance_every=1),allow_incomplete_actions=True),data,registry,artifacts)
frozen=freeze_run(record,artifacts)
observation=observe(frozen['frozen_id'],daily,data,artifacts)
assert observation['classification']=='historical_only'
assert observation==observe(frozen['frozen_id'],daily,data,artifacts)
evidence['observation']={'frozen_id':frozen['frozen_id'],'run_id':record['id'],'observation_id':observation['observation_id'],'classification':observation['classification']}
try:
    run_research(RunConfig(dataset_id='f31316b05cdfd12ab3a93b136cea3fa805858000631de518f4f1b94263e5f833',allow_incomplete_actions=True),data,registry,artifacts)
except ValueError as exc:
    assert 'Known split/dividend' in str(exc)
    evidence['known_action_rejection']=str(exc)
else:
    raise AssertionError('Known dividend replay unexpectedly accepted')
(artifacts/'final-validation.json').write_text(json.dumps(evidence,indent=2),encoding='utf-8')
print(json.dumps({'code_identity':evidence['code_identity'],'observation':evidence['observation'],'artifact':str(artifacts/'final-validation.json')},indent=2))
