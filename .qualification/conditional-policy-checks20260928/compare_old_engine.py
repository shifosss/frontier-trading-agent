"""Exact comparison against verified pre-change historical engine bytes."""
from pathlib import Path
from itertools import product
import hashlib,json,runpy,zipfile
import numpy as np
from frontier.execution_costs import ExecutionCosts
from frontier.short_horizon_study import _simulate_daily

ROOT=Path(__file__).resolve().parent
ARCHIVE=ROOT.parent/'conditional-selection20260928'
def canonical(value):
    return json.dumps(value,sort_keys=True,allow_nan=True,
                      default=lambda v:v.tolist() if isinstance(v,np.ndarray) else v.item())
def main():
    manifest=json.loads((ARCHIVE/'prior-strategy-code-manifest.json').read_text())
    archive=ARCHIVE/'prior-strategy-code.zip'
    assert hashlib.sha256(archive.read_bytes()).hexdigest()==manifest['archive_sha256']
    source_name='src/frontier/short_horizon_study.py'
    with zipfile.ZipFile(archive) as z:source=z.read(source_name)
    assert hashlib.sha256(source).hexdigest()==manifest['files'][source_name]
    namespace={'__name__':'archived_short_horizon_study'}
    exec(compile(source,'verified-archive/'+source_name,'exec'),namespace)
    old=namespace['_simulate_daily']
    helpers=runpy.run_path('tests/test_short_horizon_study.py')
    checked=[]
    for budget,horizon,cost_name in product((500,2000),(1,3,5),(None,'proportional','moomoo_ca_us')):
        data=helpers['market'](n=30,count=6,lag=3)
        for t in range(30):
            data['close'][t]=np.arange(6)*0.12+10+t*0.025
        data['close'][9,0]*=1.8
        data['adjusted']=data['close'].copy()
        data['counts']['momentum'][:]=5
        cost=None if cost_name is None else ExecutionCosts(cost_name,40)
        args=(data,'momentum',horizon,budget,40,0,29)
        kwargs=dict(audit=True,cost_model=cost)
        before=old(*args,**kwargs);after=_simulate_daily(*args,**kwargs)
        assert canonical(before)==canonical(after),(budget,horizon,cost_name,'whole')
        old_first=old(*args,**kwargs,process_through=9)
        new_first=_simulate_daily(*args,**kwargs,process_through=9)
        assert canonical(old_first)==canonical(new_first),(budget,horizon,cost_name,'first')
        next_args=(data,'momentum',horizon,budget,40,10,29)
        old_final=old(*next_args,**kwargs,process_through=29,state=old_first['state'])
        new_final=_simulate_daily(*next_args,**kwargs,process_through=29,state=new_first['state'])
        assert canonical(old_final)==canonical(new_final),(budget,horizon,cost_name,'resume')
        checked.append(dict(budget=budget,horizon=horizon,cost=cost_name,comparisons=3))
    report=dict(status='passed',archive_sha256=manifest['archive_sha256'],
                old_engine_sha256=hashlib.sha256(source).hexdigest(),
                new_engine_sha256=hashlib.sha256(Path(source_name).read_bytes()).hexdigest(),
                scenarios=checked,exact_complete_output_comparisons=54,
                includes='All arrays, trade records, activity, fees, tallies, cash/settlement state and streaming scope; no optional policy supplied.')
    (ROOT/'old-engine-comparison.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='scenarios'},indent=2))
if __name__=='__main__':main()

