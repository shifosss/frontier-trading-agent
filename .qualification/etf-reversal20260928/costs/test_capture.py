import importlib.util,json,math,shutil
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import exchange_calendars as xc
import httpx,pandas as pd,pytest
ROOT=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('etf_cost_capture',ROOT/'run_capture.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
def definition():return json.loads((ROOT/'cost-definition.json').read_text())
def params(d):
    w=d['windows'][0]
    return {'symbols':','.join(d['symbols']),'start':w['start'],'end':w['end'],'feed':'sip','sort':'asc','limit':10000,'asof':w['id'][:10]}
def test_fixed_calendar_scope_and_end_exclusion():
    d=definition();assert len(d['symbols'])==11 and len(d['windows'])==3
    c=xc.get_calendar('XNYS',start='2015-12-31',end='2024-01-03')
    for w in d['windows']:
        day=w['id'][:10]
        assert str(c.date_to_session(day[:4]+'-01-01',direction='next').date())==day
        assert pd.Timestamp(w['end'])==c.session_close(day)
        assert pd.Timestamp(w['end'])-pd.Timestamp(w['start'])==pd.Timedelta(minutes=1)
def test_fixed_data_scope_calls_bytes_and_pacing(tmp_path):
    d=definition();d.update(max_response_bytes=4,max_total_raw_bytes=8,max_total_request_starts=1)
    calls=[]
    def handle(req):calls.append(req);return httpx.Response(200,content=b'123456789',request=req)
    with patch.object(m.time,'sleep') as sleep, m.BoundedClient(d,tmp_path,transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(ValueError):client.get('https://paper-api.alpaca.markets/v2/account',params=params(d))
        with pytest.raises(ValueError):client.get(m.ENDPOINT,params=params(d)|{'feed':'iex'})
        response=client.get(m.ENDPOINT,params=params(d))
        assert response.content==b'12345' and client.limit_error and client.bytes==5
        with pytest.raises(RuntimeError):client.get(m.ENDPOINT,params=params(d))
        assert len(calls)==1 and sleep.call_count==1
    rows=(tmp_path/'request-starts.jsonl').read_text();assert 'APCA-API' not in rows
def test_all_33_cells_incomplete_and_invalid_raw_preserved(tmp_path):
    d=definition();(tmp_path/'cost-definition.json').write_text(json.dumps(d))
    name='cost-'+d['windows'][0]['id']+'-page-1.capture.json'
    (tmp_path/'bad.json').write_bytes(b'{truncated')
    (tmp_path/name).write_text(json.dumps({'status_code':200,'raw_file':'bad.json','sha256':m.sha(tmp_path/'bad.json'),'error':'Raw response/total ceiling'}))
    summary=m.complete_denominator(tmp_path,d)
    assert len(summary)==3 and not any(r['complete'] for r in summary)
    assert summary[0]['request_attempts']==[name] and summary[0]['pages']==[]
    analyzer=m.load('empty_etf_analyzer',ROOT/'cost-analyze.py');analyzer.ROOT=tmp_path;analyzer.main()
    assert len(json.loads((tmp_path/'cost-analysis.json').read_text())['cells'])==33
def test_full_denominator_max_rule_and_failure_without_substitution(tmp_path):
    d=definition();(tmp_path/'cost-definition.json').write_text(json.dumps(d))
    cells=[{'window':w['id'],'symbol':s,'pagination_complete':True,'valid_observed_seconds':59.5,'duration_weighted_spread_bps':{'mean':.4}} for w in d['windows'] for s in d['symbols']]
    cells[-1]['duration_weighted_spread_bps']['mean']=2.1
    (tmp_path/'cost-analysis.json').write_text(json.dumps({'cells':cells}))
    assert m.qualify_costs(tmp_path,d)['round_trip_bps']==13
    cells[0]['valid_observed_seconds']=58.999
    (tmp_path/'cost-analysis.json').write_text(json.dumps({'cells':cells}))
    result=m.qualify_costs(tmp_path,d)
    assert result['status']=='unqualified' and len(result['invalid_cells'])==1 and 'round_trip_bps' not in result
    assert len(json.loads((tmp_path/'cost-analysis.json').read_text())['cells'])==33
def test_original_probe_follows_continuation_not_short_page(tmp_path):
    d=definition();d['windows']=d['windows'][:1];(tmp_path/'cost-definition.json').write_text(json.dumps(d))
    probe=m.load('probe_pagination_fixture',ROOT/'cost-probe.py');probe.ROOT=tmp_path;probe.DEF=tmp_path/'cost-definition.json'
    probe._paper_credentials=lambda:('offline','offline');seen=[]
    def handle(req):
        seen.append(dict(req.url.params))
        return httpx.Response(200,json={'quotes':{},'next_page_token':'continue' if len(seen)==1 else None},request=req)
    probe.httpx=SimpleNamespace(Client=lambda **kw:m.BoundedClient(d,tmp_path,transport=httpx.MockTransport(handle),**kw),TransportError=httpx.TransportError)
    with patch.object(m.time,'sleep'):probe.capture()
    assert len(seen)==2 and seen[1]['page_token']=='continue'
    assert m.complete_denominator(tmp_path,d)[0]['complete']
def test_403_stops_all_further_gets_and_reexecution(tmp_path,monkeypatch):
    d=definition();(tmp_path/'cost-definition.json').write_text(json.dumps(d));(tmp_path/'implementation.json').write_text(json.dumps({'files':{},'external_files':{}}))
    for name in ['cost-probe.py','cost-analyze.py']:shutil.copyfile(ROOT/name,tmp_path/name)
    monkeypatch.setattr(m,'ROOT',tmp_path);real_load=m.load;real_client=m.BoundedClient;seen=[]
    def loader(name,path):
        out=real_load(name,path)
        if path.name=='cost-probe.py':out._paper_credentials=lambda:('offline','offline')
        return out
    monkeypatch.setattr(m,'load',loader)
    def handle(req):seen.append(req);return httpx.Response(403,content=b'{"message":"fixture denied"}',request=req)
    monkeypatch.setattr(m,'BoundedClient',lambda *a,**kw:real_client(*a,transport=httpx.MockTransport(handle),**kw))
    with patch.object(m.time,'sleep'),pytest.raises(SystemExit):m.main()
    assert len(seen)==1
    summary=json.loads((tmp_path/'cost-capture-summary.json').read_text());assert len(summary)==3 and not any(r['complete'] for r in summary)
    assert json.loads(next(tmp_path.glob('cost-*-page-*.capture.json')).read_text())['status_code']==403
    with pytest.raises(ValueError):m.main()
    assert len(seen)==1
