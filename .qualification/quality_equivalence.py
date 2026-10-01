import json
from pathlib import Path
from frontier.data import load_dataset
from frontier.domain import RunConfig
from frontier.replay import code_identity,replay_dataset
root=Path.cwd()
baseline=json.loads((root/'artifacts/quality-review-baseline.json').read_text(encoding='utf-8'))
fields=['config','dataset','summary','equity_curve','decisions','fills','positions','balances','engine_identity','exposure_drift','unfilled_intents']
comparisons=[]
datasets={}
for id in baseline['run_ids']:
    before=json.loads((root/'artifacts'/id/'result.json').read_text(encoding='utf-8'))
    config=RunConfig.model_validate(before['config'])
    if config.dataset_id not in datasets:
        datasets[config.dataset_id]=load_dataset(root/'data/datasets',config.dataset_id)
    after=replay_dataset(datasets[config.dataset_id],config)
    differences=[key for key in fields if before[key]!=after[key]]
    assert not differences,(id,config.strategy.name,differences)
    comparisons.append({'run_id':id,'strategy':config.strategy.name,'identical':True})
result={'before_commit':baseline['commit'],'before_code_identity':baseline['code_identity'],'after_code_identity':code_identity(),'compared_fields':fields,'comparisons':comparisons}
(root/'artifacts/quality-equivalence.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps({'identical_runs':len(comparisons),'fields':fields,'after_code_identity':result['after_code_identity']},indent=2))
