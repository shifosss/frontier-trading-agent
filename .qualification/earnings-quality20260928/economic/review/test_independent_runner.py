"""Independent generated-only runner boundaries; never original events or network."""
import copy
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import numpy as np

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location("earnings_runner_independent",HERE.parent/"run_study.py")
runner=importlib.util.module_from_spec(spec);sys.modules[spec.name]=runner;spec.loader.exec_module(runner)

def row(year, suffix="", end=None):
    return {"event_id":str(year)+suffix,"symbol":"SYN","cik":"0000000001","decision_timestamp":f"{year}-01-04T09:00:00-05:00","planned_label_end_session":end or f"{year}-01-11","model_input_status":"qualified","model_input_reasons":[],"model_inputs":[1,.1,0,1,.05],"entry_index":year*10,"planned_label_end_index":year*10+5}

class RunnerReview(unittest.TestCase):
    def test_lazy_labels_refuse_test_unavailable_and_boundary(self):
        rows=[row(y) for y in (2019,2020,2021)]
        rows += [dict(row(2019,"purged",end="2020-01-02")),dict(row(2019,"bad"),model_input_status="unavailable")]
        gate=runner.FoldLabels({},rows,{"fit_decision_years":[2017,2018,2019],"calibration_decision_year":2020,"test_decision_year":2021},["2020-01-02","2021-01-04"])
        with patch.object(runner.event_inputs,"extract_labels",side_effect=lambda m,rr:{r['event_id']:{'status':'qualified','targets':[.1,.02]} for r in rr}) as extract:
            self.assertEqual(gate.get("2019")["targets"],[.1,.02]);gate.get("2019");gate.get("2020")
            for key in ("2021","2019purged","2019bad"):
                with self.assertRaises(AssertionError):gate.get(key)
            self.assertEqual(extract.call_count,2)

    def test_exact_ten_attempts_and_both_durable_forecasts_before_test_labels(self):
        rows=[row(y) for y in range(2017,2026)]
        calendar={'sessions':[{'session':f'{y}-01-04'} for y in range(2017,2026)]}
        fits=[];saved={};extract_calls=[]
        with tempfile.TemporaryDirectory() as temp:
            dest=Path(temp)/'models'
            def fit(family, all_rows, labels, fold, sessions):
                self.assertEqual(all_rows,rows);year=fold['test_decision_year'];fits.append((family,year))
                labels.get(str(year-1))
                return SimpleNamespace(family=family,training_mean=np.array([.02,.01]),quantile_edges={'raw':[[.01],[.02]],'corrected':[[.01],[.02]]},audit={'status':'complete','attempt_id':f'{family}-{year}','fold':fold,'samples':{'fit':{'rows':256,'distinct_ciks':25},'calibration':{'rows':64,'distinct_ciks':16}},'reasons':[],'warnings':[]})
            def save(bundle,path):
                path.mkdir();runner.write(path/'manifest.json',{'id':bundle.audit['attempt_id']});saved[str(path)]=bundle
            def predict(bundle, rr):
                return {'model_attempt_id':bundle.audit['attempt_id'],'test_decision_year':bundle.audit['fold']['test_decision_year'],'forecasts':[{'event_id':r['event_id'],'status':'predicted','raw':[.02,.01],'corrected':[.02,.01]} for r in rr]}
            def extract(m, rr):
                current=fits[-1][1]
                for r in rr:
                    y=int(r['event_id'])
                    if y==current:
                        marker=runner.read(dest/str(y)/'forecasts-persisted.json')
                        for family in runner.models.FAMILIES:
                            p=dest/str(y)/family/'forecasts.json'
                            self.assertEqual(marker['forecast_sha256'][family],runner.sha(p))
                        self.assertEqual([f for f in fits if f[1]==y],[(f,y) for f in runner.models.FAMILIES])
                    else:self.assertLess(y,current)
                    extract_calls.append(y)
                return {r['event_id']:{'status':'qualified','targets':[.03,.02]} for r in rr}
            with patch.object(runner.models,'fit_family_fold',side_effect=fit),patch.object(runner.models,'save_bundle',side_effect=save),patch.object(runner.models,'load_bundle',side_effect=lambda p:saved[str(p)]),patch.object(runner.models,'predict_events',side_effect=predict),patch.object(runner.event_inputs,'extract_labels',side_effect=extract):
                forecasts,attempts,labels=runner.run_folds({},rows,calendar,dest)
            self.assertEqual(fits,[(f,y) for y in range(2021,2026) for f in runner.models.FAMILIES]);self.assertEqual(len(attempts),10)
            self.assertEqual(set(labels),{str(y) for y in range(2021,2026)})
            self.assertEqual([len(forecasts[f]) for f in runner.models.FAMILIES],[5,5])
            for path in dest.rglob('*.json'):json.loads(path.read_text())

    def test_all_twenty_accounts_keep_failures_and_shared_forecast_identity(self):
        calls=[];forecasts={f:[{'event_id':'generated','value':f}] for f in runner.models.FAMILIES}
        def account(m,rr,**kwargs):
            calls.append(kwargs)
            self.assertNotIn('first',kwargs);self.assertNotIn('last',kwargs)
            if len(calls)==3:raise ValueError('deliberate generated missing required mark')
            return {'recipe':kwargs['recipe'],'cost_profile':kwargs['cost_profile'],'starting_capital':kwargs['capital'],'status':'complete','weekly_objective':{'count':263}}
        with tempfile.TemporaryDirectory() as temp:
            parent=Path(temp);modeldir=parent/'model';modeldir.mkdir()
            for family in runner.models.FAMILIES:runner.write(modeldir/(family+'-all-forecasts.json'),forecasts[family])
            with patch.object(runner.accounts,'run_account',side_effect=account):reports=runner.run_accounts({},[],forecasts,modeldir,parent/'accounts')
            self.assertEqual(len(reports),20);self.assertEqual(len(calls),20);self.assertEqual(sum(r['status']=='failed' for r in reports),1)
            for family in runner.models.FAMILIES:
                entries=[c for c in calls if c['recipe']==family];self.assertEqual(len(entries),4);self.assertEqual(len({c['forecast_identity'] for c in entries}),1)
                for c in entries:self.assertEqual(c['forecasts'],{'generated':forecasts[family][0]})
            self.assertEqual(len(list((parent/'accounts').glob('*-failure.json'))),1)
            for path in (parent/'accounts').glob('*.json'):json.loads(path.read_text())

    def test_diagnostics_fixed_edges_errors_missing_and_no_mutation(self):
        bundle=SimpleNamespace(family='ridge',training_mean=np.array([.05,.02]),quantile_edges={'raw':[[.1],[]],'corrected':[[.15],[]]},audit={'status':'complete'})
        pred={'test_decision_year':2021,'forecasts':[{'event_id':'a','status':'predicted','raw':[.1,.02],'corrected':[.2,.03]},{'event_id':'b','status':'predicted','raw':[.3,.04],'corrected':[.4,.05]},{'event_id':'c','status':'unavailable','raw':None,'corrected':None}]}
        labels={'a':{'status':'qualified','targets':[.15,.01]},'b':{'status':'unavailable'},'c':{'status':'qualified','targets':[.05,.02]}}
        original=copy.deepcopy(pred);edges=copy.deepcopy(bundle.quantile_edges);r=runner.diagnostics(bundle,pred,labels)
        h=r['heads']['return_5'];self.assertAlmostEqual(h['raw']['mae'],.05);self.assertEqual(h['raw']['bins'][1]['count'],1);self.assertEqual(h['raw']['bins'][1]['missing_labels'],1)
        self.assertEqual(h['training_mean']['count'],1);self.assertEqual(h['training_mean']['missing_labels'],1)
        self.assertEqual(pred,original);self.assertEqual(bundle.quantile_edges,edges)

    def test_reference_period_and_idle_weeks(self):
        sessions=['2020-12-31','2021-01-04','2021-01-08','2025-12-31','2026-01-02','2026-01-16']
        market={'sessions':sessions,'benchmark':0,'adjusted':np.array([[100.],[110.],[110.],[120.],[115.],[125.]])}
        out=runner.references(market)
        for capital in ('10000','2000'):
            r=out[capital]['SPY'];self.assertEqual(r['first_session'],'2020-12-31');self.assertEqual(r['last_session'],'2026-01-16');self.assertAlmostEqual(r['total_return'],.25)
            self.assertEqual(out[capital]['cash']['total_return'],0)
        bad=copy.deepcopy(market);bad['adjusted'][2,0]=np.nan
        self.assertEqual(runner.references(bad)['10000']['SPY']['status'],'incomplete')
        self.assertIsNone(runner.references(bad)['10000']['SPY']['total_return'])

    def test_source_reader_blocks_writer_and_global_exclusive_guard(self):
        with tempfile.TemporaryDirectory() as temp:
            repo=Path(temp);source=repo/'study/source';source.mkdir(parents=True);(repo/'data/historical').mkdir(parents=True)
            paths=[source/'capture.lock.sqlite',source.parent/'sec-source.lock.sqlite',repo/'data/historical/worker.lock.sqlite']
            for path in paths:
                c=sqlite3.connect(path);c.execute('create table marker (x integer)');c.close()
            before={p:p.read_bytes() for p in paths}
            with patch.object(runner,'REPO',repo),runner.study_locks(source):
                for path in paths:
                    c=sqlite3.connect(path,timeout=0)
                    try:
                        with self.assertRaises(sqlite3.OperationalError):c.execute('BEGIN EXCLUSIVE')
                    finally:c.close()
            for path in paths:self.assertEqual(path.read_bytes(),before[path])


    def test_failed_attempt_is_durable_and_claim_prevents_unreviewed_repeat(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);definition_path=root/'definition.json';runner.write(definition_path,{'fixture':True})
            definition={'paths':{'source_root':str(root/'source')},'inputs':{},'dependencies':{}}
            with patch.object(runner,'HERE',root),patch.object(runner,'validate_definition',return_value=definition),patch.object(runner,'study_locks',return_value=nullcontext()),patch.object(runner,'validate_terminal',side_effect=ValueError('deliberate synthetic terminal mismatch')) as terminal:
                with self.assertRaisesRegex(ValueError,'synthetic terminal mismatch'):runner.run(definition_path)
                with self.assertRaises(FileExistsError):runner.run(definition_path)
            self.assertEqual(terminal.call_count,1)
            attempts=list((root/'attempts').iterdir());self.assertEqual(len(attempts),1)
            failure=runner.read(attempts[0]/'failure.json');self.assertEqual(failure['status'],'failed')
            declared=runner.read(attempts[0]/'declared-attempts.json')
            self.assertEqual(len(declared['models']),10);self.assertEqual(len(declared['accounts']),20)
            self.assertFalse((attempts[0]/'completion.json').exists())

    def test_definition_requires_source_binding_and_reviewed_rerun_reason(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);p=root/'definition.json'
            paths={key:str(root/key) for key in runner.PATH_KEYS}
            inputs={v:'a'*64 for key,v in paths.items() if key!='source_root'}
            inputs.update({str(Path(paths['source_root'])/name):'a'*64 for name in ('request.json','implementation.json','registry.json','completion.json')})
            d={'schema':1,'reviewed_for_execution':True,'paths':paths,'inputs':inputs,'dependencies':{}}
            p.write_text(json.dumps(d))
            with patch.object(runner,'required_code_paths',return_value=[]),patch.object(runner,'runtime_dependencies',return_value={}),patch.object(runner,'verify_identities') as verify,patch.object(runner,'sha',return_value=runner.models.SPEC_SHA256):
                runner.validate_definition(p);verify.assert_called_once_with(inputs)
                d['rerun_of']='previous';p.write_text(json.dumps(d))
                with self.assertRaisesRegex(ValueError,'reviewed reason'):runner.validate_definition(p)
                d['reviewed_rerun_reason']='generated fixture validation';del d['inputs'][str(Path(paths['source_root'])/'registry.json')];p.write_text(json.dumps(d))
                with self.assertRaisesRegex(ValueError,'mandatory code/source identities'):runner.validate_definition(p)

    def test_terminal_original_source_and_cohort_corruption_are_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp);source=root/'source';source.mkdir();raw=root/'original.bin';raw.write_bytes(b'generated original source')
            chosen=[{'symbol':f'SYN{i:03}','cik':str(i+1).zfill(10)} for i in range(100)]
            paths={k:root/(k+'.json') for k in runner.PATH_KEYS};paths['source_root']=source;paths['market_arrays']=root/'arrays.npz'
            runner.write(source/'completion.json',{'status':'captured'});runner.write(source/'registry.json',{'issuers':[{'issuer':r} for r in chosen]})
            runner.write(paths['cohort'],{'selected':chosen});runner.write(paths['qualification_definition'],{'fixture':True})
            qsha=runner.sha(paths['qualification_definition']);runner.write(paths['terminal_events'],[]);runner.write(paths['issuer_status'],chosen)
            runner.write(paths['qualification_source_inputs'],{'definition_sha256':qsha,'files':{str(raw):runner.sha(raw)}})
            summary={'status':'complete','definition_sha256':qsha,'events':0,'retained_original_records':0,'files':{filename:runner.sha(paths[key]) for key,filename in [('terminal_events','events.json'),('qualification_source_inputs','source-inputs.json'),('issuer_status','issuer-status.json')]}}
            runner.write(paths['qualification_summary'],summary)
            sessions=['2020-12-31','2021-01-04','2026-01-16'];runner.write(paths['calendar'],{'sessions':[{'session':s} for s in sessions]})
            np.savez(paths['market_arrays'],adjusted=np.ones((3,101)))
            meta={'arrays_sha256':runner.sha(paths['market_arrays']),'cohort_order':chosen,'source_inputs':{str(raw):runner.sha(raw)},'sessions':sessions,'symbols':[r['symbol'] for r in chosen]+['SPY'],'benchmark':100}
            runner.write(paths['market_inputs'],meta);runner.write(paths['market_completion'],{'status':'complete','outputs':{'market-inputs.json':runner.sha(paths['market_inputs']),'market-arrays.npz':runner.sha(paths['market_arrays'])}})
            definition={'paths':{k:str(v) for k,v in paths.items()}}
            with patch.object(runner.qualification,'verify_source',return_value={'issuers':chosen}):
                market,events,cohort,calendar,bound=runner.validate_terminal(definition);self.assertEqual(cohort['selected'],chosen);self.assertEqual(events,[]);self.assertIn(str(raw),bound)
                raw.write_bytes(b'generated source corrupted')
                with self.assertRaisesRegex(ValueError,'Bound source/code changed'):runner.validate_terminal(definition)
                raw.write_bytes(b'generated original source')
                (source/'registry.json').write_text(json.dumps({'issuers':[{'issuer':r} for r in reversed(chosen)]}))
                with self.assertRaisesRegex(ValueError,'cohort order differs'):runner.validate_terminal(definition)
                runner.write(source/'STOP.json',{'reason':'generated unresolved access stop'})
                with self.assertRaisesRegex(ValueError,'Unresolved source STOP'):runner.validate_terminal(definition)

if __name__=='__main__':unittest.main(verbosity=2)
