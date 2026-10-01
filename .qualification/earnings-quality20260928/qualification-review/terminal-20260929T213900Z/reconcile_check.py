from pathlib import Path
from datetime import datetime,timezone
import hashlib,json
root=Path.cwd().resolve(); source=root/'.qualification/earnings-quality20260928/source'; out=root/'.qualification/earnings-quality20260928/qualification-review/terminal-20260929T213900Z'
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
read=lambda p:json.loads(Path(p).read_text(encoding='utf-8'))
old=read(out/'terminal-review.json')
url='https://www.sec.gov/Archives/edgar/data/1061219/000106121925000025/0001061219-25-000025-index.html'
resource_path=source/'resources'/(hashlib.sha256(url.encode()).hexdigest()+'.json'); resource=read(resource_path)
journal=[x for line in (source/'requests.jsonl').read_text().splitlines() if (x:=json.loads(line)).get('url')==url]
assert old['blockers']==['request outcome '+url]
assert len(journal)==2 and [x['event'] for x in journal]==['request_started','request_finished']
assert journal[1]['status']==resource.get('status') is None
assert journal[1]['error']==resource['error']=='TimeoutError: The read operation timed out'
assert 'bytes' not in resource and 'path' not in resource and 'sha256' not in resource
assert journal[1]['bytes']==resource.get('bytes',0)==0
capture=root/'.qualification/filing-source20260928/capture.py'
assert "bytes=meta.get('bytes',0)" in capture.read_text(encoding='utf-8')
assert sha(capture)==read(source/'implementation.json')['external_files'][capture.relative_to(root).as_posix()]
definition=root/'.qualification/earnings-quality20260928/qualification/terminal-definition-20260929.json'; d=read(definition)
required={Path(p).as_posix():h for p,h in old['root_definition_required_inputs'].items()}
assert all(d['inputs'].get(p)==h for p,h in required.items())
assert all(sha(root/p)==h for p,h in d['inputs'].items())
report={'schema':1,'at_utc':datetime.now(timezone.utc).isoformat(),
'initial_review':{'path':str(out/'terminal-review.json'),'sha256':sha(out/'terminal-review.json'),'checks':len(old['checks']),'initial_passed_checks':sum(x['passed'] for x in old['checks']),'initial_checker_findings':old['blockers']},
'finding_reconciliation':{'classification':'Checker compared an absent resource bytes field directly with the intentional journal zero. The completed timeout outcome is consistent; no raw body was received.','resource_path':str(resource_path),'resource_sha256':sha(resource_path),'resource_status':None,'resource_error':resource['error'],'resource_bytes_key_absent':True,'resource_path_and_sha256_keys_absent':True,'journal_finished_bytes':0,'implementation_recording_rule':"bytes=meta.get('bytes',0)",'implementation_path':str(capture),'implementation_sha256':sha(capture),'retry_observed':False,'source_change_required':False},
'root_definition':{'path':str(definition),'sha256':sha(definition),'all_43_inputs_reverified':True,'required_collector_inputs_verified':len(required)},
'checker_execution_note':'First reconciliation command stopped before writing because Windows backslash paths did not compare textually to POSIX declaration paths. Resolving their Path.as_posix representation confirms every required identity; no source or definition changed.',
'final_material_blockers':[],'terminal_qualification_permitted_with_unavailable_failures_retained':True,'summary':old['summary'],'failure_categories':old['failure_categories'],'network_requests':0,'source_mutations':0}
p=out/'terminal-review-reconciliation.json'
with p.open('x',encoding='utf-8') as f:json.dump(report,f,indent=2)
print(json.dumps({'path':str(p),'sha256':sha(p),'material_blockers':[],'qualification_permitted':True},indent=2))
