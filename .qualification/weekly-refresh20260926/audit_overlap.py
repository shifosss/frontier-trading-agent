"""Declared64-symbol raw provider overlap audit; no prices are repaired."""
import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parent
REPO=ROOT.parents[1]
WORKSPACE=ROOT/'capture-workspace'
verify=json.loads((ROOT/'verification.json').read_text('utf-8'))
assert verify['status']=='completed'
declaration=json.loads((ROOT/'overlap-audit-definition.json').read_text('utf-8'))
old_records=json.loads((REPO/'artifacts/historical-lab/runs/814780d48b4141b9a82a3fb917d1b85a/capture-index.json').read_text('utf-8'))
new_records=json.loads((WORKSPACE/'artifacts/historical-lab/runs'/verify['run_id']/'capture-index.json').read_text('utf-8'))
old={r['symbol']:r for r in old_records}
new={r['symbol']:r for r in new_records}

def values(workspace,record):
    content=(workspace/record['path']).read_bytes()
    assert hashlib.sha256(content).hexdigest()==record['sha256']
    result=json.loads(content)['chart']['result'][0]
    quote=result['indicators']['quote'][0]
    adjusted=result['indicators']['adjclose'][0]['adjclose']
    out={}
    for i,stamp in enumerate(result.get('timestamp',[])):
        day=datetime.fromtimestamp(stamp,timezone.utc).astimezone(ZoneInfo('America/Toronto')).date().isoformat()
        if declaration['overlap_start']<=day<=declaration['overlap_end']:
            assert day not in out
            out[day]={f:adjusted[i] if f=='adjusted_close' else quote[f][i] for f in declaration['fields']}
    return out

results=[]
changes=[]
summary=Counter()
for currency,symbols in declaration['sample'].items():
    for symbol in symbols:
        item={'symbol':symbol,'currency':currency}
        if symbol not in old or symbol not in new:
            item.update(status='unavailable',old_available=symbol in old,new_available=symbol in new)
            summary['unavailable_symbols']+=1
            results.append(item)
            continue
        a=values(REPO/'data/historical/capture-workspace',old[symbol])
        b=values(WORKSPACE/'data/historical/capture-workspace',new[symbol])
        item.update(status='compared',old_sha256=old[symbol]['sha256'],new_sha256=new[symbol]['sha256'],shared_sessions=sorted(a.keys()&b.keys()),old_only_sessions=sorted(a.keys()-b.keys()),new_only_sessions=sorted(b.keys()-a.keys()))
        item['changed_cells']=0
        for session in item['shared_sessions']:
            for field in declaration['fields']:
                x,y=a[session][field],b[session][field]
                summary['compared_cells']+=1
                if x!=y:
                    changes.append({'symbol':symbol,'session':session,'field':field,'old':x,'new':y,'delta':None if x is None or y is None else y-x})
                    item['changed_cells']+=1
                    summary['changed_cells']+=1
        summary['compared_symbols']+=1
        summary['changed_symbols']+=bool(item['changed_cells'])
        results.append(item)
result={'status':'completed','finished_at':datetime.now(timezone.utc).isoformat(),'definition':declaration,'summary':dict(summary),'symbols':results,'changed_values':changes,'conclusion':'Raw value differences or equality do not establish corporate-action or entity-history completeness. No source changes applied.'}
(ROOT/'overlap-audit.json').write_text(json.dumps(result,indent=2,allow_nan=False),encoding='utf-8')
print(json.dumps({'summary':dict(summary),'changed_fields':dict(Counter(x['field'] for x in changes))},indent=2))
