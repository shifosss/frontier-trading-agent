"""Independent uncached economic-ranking check; no account replay or fitting."""
from pathlib import Path
from math import floor
import hashlib,json
import numpy as np
from frontier.conditional_policy import ConditionalPolicy
from frontier.execution_costs import ExecutionCosts
ROOT=Path(__file__).resolve().parent

def main():
    rng=np.random.default_rng(1729)
    cases=0
    for profile in ('proportional','moomoo_ca_us'):
        cost=ExecutionCosts(profile,40)
        for mode in ('fraction','dollars'):
            for trial in range(40):
                symbols=[f'S{i:02}' for i in range(12)]
                prices=np.exp(rng.uniform(np.log(.2),np.log(250),12))
                atrs=prices*rng.uniform(.002,.08,12)
                mu=rng.uniform(-.02,.2,12);down=rng.uniform(0,.08,12)
                cash=float(rng.uniform(20,2000));slots=int(rng.integers(1,6))
                ranking=rng.permutation(12)
                forecasts=list(zip(mu,down))
                selector=ConditionalPolicy(lambda t,j:forecasts[j],mode,'fixed-fixture')
                actual=selector.plan_entries(signal_index=0,symbols=symbols,ranking=ranking,
                    prices=prices,atrs=atrs,nav=2000,available_cash=cash,slots=slots,
                    cost_bps=40,cost_model=cost,audit=False)
                available=cash;remaining=set(range(12));expected=[]
                while remaining and len(expected)<slots:
                    candidates=[]
                    for j in remaining:
                        risk=floor(10/(2*float(atrs[j])))
                        bounded=cost.maximum_quantity(risk,float(prices[j]),400)
                        q=cost.maximum_quantity(bounded,float(prices[j]),available)
                        if not q:continue
                        n=q*float(prices[j]);buy=cost.fee(q,n,'buy')
                        sell=cost.fee(q,n*(1+float(mu[j])),'sell')
                        utility=n*float(mu[j])-buy-sell-.5*n*float(down[j])
                        if utility>0:candidates.append((utility/n if mode=='fraction' else utility,symbols[j],j,q,n+buy,utility))
                    if not candidates:break
                    score,symbol,j,q,reservation,utility=min(candidates,key=lambda c:(-c[0],c[1]))
                    expected.append((symbol,q,utility));available-=reservation;remaining.remove(j)
                assert [(o['symbol'],o['quantity']) for o in actual['orders']]==[(s,q) for s,q,u in expected]
                assert abs(actual['remaining_cash']-available)<1e-9
                for order,(_,_,utility) in zip(actual['orders'],expected,strict=True):
                    assert order['projection']['utility']==utility
                cases+=1
    paths=['src/frontier/conditional_policy.py','src/frontier/short_horizon_study.py','tests/test_conditional_policy.py']
    result=dict(status='passed',economic_cases=cases,profiles=['proportional40','moomoo_ca_us40'],modes=['fraction','dollars'],
        method='Independent uncached all-candidate reselection after every reservation, original risk/cap/cash formulas and separately computed projected fees/utility.',
        code_hashes={p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths},
        declaration_sha256=hashlib.sha256(Path('.qualification/conditional-selection20260928/request.draft.json').read_bytes()).hexdigest(),
        existing_tests='515 passed;96 dependency/pandas deprecation warnings;15 new behavioral tests included',
        scope='No model fitting, broker operation, source edit, account rerun or economic-result selection.')
    (ROOT/'economic-invariants.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
if __name__=='__main__':main()

