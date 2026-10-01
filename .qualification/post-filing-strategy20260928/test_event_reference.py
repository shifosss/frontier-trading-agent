"""Synthetic descriptive event returns; no historical price outcomes are read."""
import importlib.util
from pathlib import Path
import numpy as np
import pytest


def module():
    path=Path(__file__).with_name('event_reference.py')
    assert path.exists(), 'event reference not implemented'
    spec=importlib.util.spec_from_file_location('event_reference_test',path)
    result=importlib.util.module_from_spec(spec);spec.loader.exec_module(result);return result


def market():
    return {'sessions':['2017-03-01','2017-03-02','2017-03-03','2017-03-06','2017-03-07','2017-03-08','2017-03-09'],
            'symbols':['A','B','SPY'],'benchmark':2,
            'adjusted':np.array([[100,200,100],[110,201,102],[120,202,104],[130,203,106],
                                 [140,204,108],[150,220,110],[154,225,112]],dtype=float)}


def event(symbol='A',accession='a',entry='2017-03-01',exit_='2017-03-08',selected=True):
    return {'symbol':symbol,'accession':accession,'filing_date':'2017-02-28',
            'feature_status':'qualified','execution_status':'qualified','entry_session':entry,
            'exit_session':exit_,'selected':selected}


def test_paired_means_equal_event_vs_equal_entry_date_and_groups():
    m=module();events=[event(),event('B','b',selected=False),
                       event(accession='a2',entry='2017-03-02',exit_='2017-03-09')]
    result=m.build_event_reference(market(),events)
    whole=result['all_eligible']
    assert whole['eligible_events']==whole['matched_events']==3 and whole['matched_entry_dates']==2
    assert whole['equal_event_mean']['stock_gross_return']==pytest.approx((.5+.1+.4)/3)
    assert whole['equal_entry_date_mean']['stock_gross_return']==pytest.approx((.3+.4)/2)
    assert result['selected']['equal_event_mean']['stock_gross_return']==pytest.approx(.45)
    assert result['rows'][0]['stock_minus_benchmark']==pytest.approx(.4)
    assert result['by_issuer']['A']['all_eligible']['eligible_events']==2
    assert result['by_entry_year']['2017']['all_eligible']['eligible_events']==3


def test_future_missing_prices_do_not_change_population_and_endpoints_stay_visible():
    m=module();data=market();events=[event(),event('B','b',selected=False)]
    before=m.build_event_reference(data,events)
    data['adjusted'][5,0]=np.nan
    after=m.build_event_reference(data,events)
    assert [(r['symbol'],r['accession'],r['selected']) for r in before['rows']]==[(r['symbol'],r['accession'],r['selected']) for r in after['rows']]
    assert after['all_eligible']['eligible_events']==2 and after['all_eligible']['matched_events']==1
    row=after['rows'][0]
    assert row['stock_gross_return'] is None and row['benchmark_gross_return']==pytest.approx(.1)
    assert row['unavailable_endpoints']==['stock_exit']
    assert after['selected']['unmatched_events']==1 and after['selected']['equal_event_mean']['stock_gross_return'] is None
    data['adjusted'][0,2]=0
    result=m.build_event_reference(data,events)
    assert result['all_eligible']['matched_events']==0
    assert result['all_eligible']['unavailable_endpoint_counts']=={'stock_exit':1,'benchmark_entry':2}


def test_scope_and_bad_session_or_horizon_remain_explicit():
    m=module();events=[event(),dict(event(accession='old'),filing_date='2016-12-31'),
        dict(event(accession='bad_feature'),feature_status='unavailable'),
        dict(event(accession='bad_clock'),execution_status='exit_outside_calendar'),
        event(accession='missing_exit',exit_='2017-03-10'),
        event(accession='wrong_hold',exit_='2017-03-09')]
    result=m.build_event_reference(market(),events)
    assert result['scope_counts']=={'input_events':6,'filed_in_2017_2025':5,'outside_filing_period':1,
                                    'structurally_eligible':3,'structurally_ineligible_in_period':2}
    assert result['all_eligible']['eligible_events']==3 and result['all_eligible']['matched_events']==1
    assert result['rows'][1]['identity_issues']==['exit_session_missing']
    assert result['rows'][2]['identity_issues']==['not_five_market_sessions']
    assert len(result['exclusions'])==3


def test_support_gate_uses_matched_selected_issuers_and_entry_years():
    m=module();sessions=[f'{year}-01-{day:02}' for year in range(2017,2022) for day in range(1,7)]
    data={'sessions':sessions,'symbols':['A','B','C','D','SPY'],'benchmark':4,
          'adjusted':np.ones((len(sessions),5))*100}
    events=[event(symbol='ABCD'[i%4],accession=str(i),entry=sessions[(i%5)*6],exit_=sessions[(i%5)*6+5]) for i in range(30)]
    for e in events:e['filing_date']=e['entry_session']
    result=m.build_event_reference(data,events)
    assert result['sample_support']['sufficient_descriptive_sample'] is True
    assert result['sample_support']['matched_selected_events']==30
    assert result['sample_support']['matched_selected_issuers']==4
    assert result['sample_support']['matched_selected_entry_years']==5
    assert result['sample_support']['establishes_profitability'] is False
    events[-1]['selected']=False
    fewer=m.build_event_reference(data,events)
    assert fewer['sample_support']['failed_gates']==['fewer_than_30_matched_selected_events']
