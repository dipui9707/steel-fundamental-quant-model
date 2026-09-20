#!/usr/bin/env python3
"""Independent synthetic arithmetic/edge checks, never imports the supplied collector.

This is an executable review worksheet, not a data pipeline or market backtest.
Run with Python 3; writes only research/architecture review result JSON.
"""
from datetime import datetime
from pathlib import Path
import hashlib
import json
import math
import statistics


RESULTS = []


def check(name, actual, expected):
    if isinstance(expected, float):
        ok = actual is not None and math.isclose(actual, expected, rel_tol=1e-9, abs_tol=1e-9)
    else:
        ok = actual == expected
    RESULTS.append({"check": name, "passed": ok, "actual": actual, "expected": expected})
    if not ok:
        raise AssertionError(name)


def dot(a, b):
    return sum(x*y for x, y in zip(a, b))


def score(s, w):
    if any(v is None and weight > 0 for v, weight in zip(s, w)):
        return None
    return 100 * sum(v*weight for v, weight in zip(s, w) if weight > 0)


def entropy(states):
    known = [v for v in states if v is not None]
    coverage = len(known)/len(states)
    if not known:
        return coverage, None, None, None
    p = [known.count(v)/len(known) for v in (-1, 0, 1)]
    h3 = -sum(v*math.log(v) for v in p if v)/math.log(3)
    q = 1-p[1]
    hd = -sum((v/q)*math.log(v/q) for v in (p[0], p[2]) if v)/math.log(2) if q else None
    return coverage, h3, hd, q


def select_version(records, at, mode="LIVE_RECORDED"):
    if mode not in {"LIVE_RECORDED", "RECONSTRUCTED_PIT"}:
        raise ValueError("UNKNOWN_INFORMATION_SET_MODE")
    cutoff = datetime.fromisoformat(at)
    valid = []
    for r in records:
        if not r.get("available_date"):
            continue
        if datetime.fromisoformat(r["available_date"]) > cutoff:
            continue
        if mode == "LIVE_RECORDED" and datetime.fromisoformat(r["recorded_at"]) > cutoff:
            continue
        if mode == "RECONSTRUCTED_PIT" and not r.get("archive_evidence"):
            continue
        valid.append(r)
    versions = {}
    for record in valid:
        seq = record["revision_sequence"]
        if seq in versions and versions[seq] != record:
            raise ValueError("CONFLICTING_REVISION")
        versions[seq] = record
    return max(valid, key=lambda r:r["revision_sequence"])["value"] if valid else None


def ranks(values):
    return [1 + sum(y < x for y in values) + (sum(y == x for y in values)-1)/2 for x in values]


def rank_ic(x, y):
    pairs = [(a, b) for a,b in zip(x,y) if a is not None and b is not None]
    if len(pairs) < 3:
        return None
    a, b = map(ranks, zip(*pairs))
    da = [v-statistics.mean(a) for v in a]
    db = [v-statistics.mean(b) for v in b]
    den = math.sqrt(dot(da,da)*dot(db,db))
    return dot(da,db)/den if den else None


def km_median(events):
    # Synthetic administrative censoring only. Ties: event before censor at same time.
    survival = 1.0
    for t in sorted({t for t,event in events}):
        at_risk = sum(t0 >= t for t0,event in events)
        failures = sum(t0 == t and event for t0,event in events)
        survival *= 1-failures/at_risk
        if survival <= .5:
            return t
    return None


def run():
    s = [[.6,-.2,.2],[.6,-.2,.2],[.4,-.1,.3],[.5,0,.2]]
    w = [[.4,.3,.3],[.2,.5,.3],[.2,.5,.3],[.3,.4,.3]]
    for i, expected in enumerate([24.,8.,12.,21.]):
        check(f"FBS_{i}",score(s[i],w[i]),expected)
    for i, expected in enumerate([(0.,-16.),(4.,0.),(4.,5.)],1):
        d=50*dot([a+b for a,b in zip(w[i],w[i-1])],[a-b for a,b in zip(s[i],s[i-1])])
        change=50*dot([a+b for a,b in zip(s[i],s[i-1])],[a-b for a,b in zip(w[i],w[i-1])])
        check(f"data_change_{i}",d,expected[0])
        check(f"weight_change_{i}",change,expected[1])
        check(f"exact_decomposition_{i}",d+change,score(s[i],w[i])-score(s[i-1],w[i-1]))
    check("missing_required_module",score([.6,None,.2],w[0]),None)
    increments=[0,4,4,-2,-2]
    fv=[None]+[sum(increments[i-1:i+1])/2 for i in range(1,5)]
    check("FV_path",fv,[None,2.,4.,1.,-2.])
    check("FA_4",(fv[3]-fv[1])/2,-.5)
    check("FA_5",(fv[4]-fv[2])/2,-3.)
    for label,states,h3,hd,q,coverage in [
        ("unanimous",[1]*4,0.,0.,1.,1.),
        ("conflict",[1,1,-1,-1],math.log(2)/math.log(3),1.,1.,1.),
        ("neutral",[0]*4,0.,None,0.,1.),
        ("sparse",[1,None,None,None],0.,0.,1.,.25),
        ("missing",[None]*4,None,None,None,0.),
    ]:
        a,b,c,d=entropy(states)
        for key,actual,expected in [("coverage",a,coverage),("H3",b,h3),("CDE",c,hd),("direction_share",d,q)]:
            check(label+"_"+key,actual,expected)
    check("mixed_neutral_H3",entropy([1,-1,0,0])[1],.946394630357186)
    check("ERR_down",dot([.8*.5*1,.6*.5*.5,.5*.4*1],[.5,.3,.2]),.285)
    check("ERR_up",dot([.9*.6*.5,.3*.4*.5,.8*.5*1],[.5,.3,.2]),.233)
    check("no_restart_capacity",dot([0,.6*.5*.5,.5*.4*1],[.5,.3,.2]),.085)
    cost=1.5*800+.4*2000+.1*2500+250+400+200-100
    check("cash_cost_arithmetic",cost,3000.)
    check("cost_gap_not_fair_value",(3300-cost)/cost,.1)
    records=[
        {"value":100,"available_date":"2026-01-08T18:00:00+08:00","recorded_at":"2026-01-08T18:05:00+08:00","revision_sequence":0,"archive_evidence":True},
        {"value":110,"available_date":"2026-01-12T10:00:00+08:00","recorded_at":"2026-01-12T10:02:00+08:00","revision_sequence":1,"archive_evidence":True},
        {"value":999,"available_date":None,"recorded_at":"2026-01-01T00:00:00+08:00","revision_sequence":2,"archive_evidence":False},
    ]
    for at,value in [("2026-01-08T15:00:00+08:00",None),("2026-01-08T18:03:00+08:00",None),("2026-01-08T18:05:00+08:00",100),("2026-01-09T15:00:00+08:00",100),("2026-01-12T10:01:00+08:00",100),("2026-01-12T10:02:00+08:00",110)]:
        check("PIT_"+at,select_version(records,at),value)
    check("reconstructed_archive_boundary",select_version(records,"2026-01-08T18:03:00+08:00","RECONSTRUCTED_PIT"),100)
    check("unknown_release_not_eligible",select_version([records[-1]],"2026-01-20T00:00:00+08:00"),None)
    for name, bad_records, bad_mode in [
        ("unknown_mode_rejected",records,"LIVE_RECORDDED"),
        ("conflicting_revision_rejected",[records[0],dict(records[0],value=999)],"LIVE_RECORDED"),
    ]:
        try:
            select_version(bad_records,"2026-01-20T00:00:00+08:00",bad_mode)
            rejected = False
        except ValueError:
            rejected = True
        check(name,rejected,True)
    area=0;days=0;path=[]
    for u,v in [(-1,.5),(-.5,.5),(.5,.5),(1,0),(None,.5),(-.5,.5)]:
        if u is None or v is None:
            path.append(None);area=0;days=0
        elif u*v<0:
            area+=abs(u-v);days+=1;path.append(area)
        else:
            area=0;days=0;path.append(area)
    check("DA_no_extra_day_and_missing_reset",path,[1.5,2.5,0,0,None,1.])
    pool=[1,2,2.5,4]
    check("midrank_percentile",(sum(v<2.5 for v in pool)+.5*sum(v==2.5 for v in pool))/len(pool),.625)
    history=[-1,1,3,5]
    check("seasonality_excludes_current",(6-statistics.mean(history))/statistics.stdev(history),1.5491933384829668)
    check("constant_rank_IC",rank_ic([1,1,1],[1,2,3]),None)
    check("average_ties_rank_IC",rank_ic([1,1,2,3],[3,3,2,1]),-1.)
    check("pairwise_missing_retained",rank_ic([1,None,2,3],[3,50,2,1]),-1.)
    check("rank_IC_too_short",rank_ic([1,2],[2,3]),None)
    check("administrative_censor_median",km_median([(2,True),(3,False),(4,True),(6,False)]),4)
    check("median_not_reached",km_median([(2,True),(3,False),(4,False),(6,False)]),None)
    # Frozen single-contract price path versus a naive switched main series.
    check("fixed_contract_5_session_log_return",math.log(105/100),.04879016416943205)
    check("roll_jump_is_not_fixed_contract_return",math.isclose(math.log(115/100),math.log(105/100)),False)
    train_intervals=[(1,5),(4,8),(7,11)]
    next_evaluation_start=8
    check("purge_overlapping_label_intervals",[x for x in train_intervals if x[1]<next_evaluation_start],[(1,5)])
    check("censored_event_not_success",sum(event for _,event in [(2,True),(3,False),(4,True),(6,False)]),2)
    phi=.5; intercept=4; mean=intercept/(1-phi); initial=10
    check("AR1_centered_half_life",-math.log(2)/math.log(phi),1.)
    check("AR1_halves_distance_to_mean",intercept+phi*initial-mean,(initial-mean)/2)
    check("AR1_does_not_halve_raw_level",intercept+phi*initial == initial/2,False)
    check("night_open_before_asof_rejected",datetime.fromisoformat("2026-01-09T21:00:00+08:00") > datetime.fromisoformat("2026-01-11T18:00:00+08:00"),False)
    check("inventory_apparent_demand_previous",100-(380-400),120)
    check("inventory_apparent_demand_current",80-(370-380),90)
    check("CS_TNB_not_independent",(600/1000-500/1000),(600-500)/1000)
    # A missing short-side top20 observation permits multiple true positions.
    check("unranked_is_not_zero",100-0 == 100-60,False)
    check("native_release_decay",(1+math.exp(-math.log(2)/2*2))/2,.75)
    posterior=math.exp(math.log(3))/(math.exp(math.log(3))+1)
    check("uncalibrated_softmax_support",posterior,.75)
    check("support_weight_smoothing",.5*.5+.5*posterior,.625)
    q0,q1,s0,s1=100,110,.4,.3
    check("allocation_identity",(s0+s1)/2*(q1-q0)+(q0+q1)/2*(s1-s0),q1*s1-q0*s0)
    p,net_in,use,loss,error=100,5,90,2,1
    inventory_change=p+net_in-use-loss+error
    check("apparent_demand_boundary",p-inventory_change,use+loss-net_in-error)
    root=Path(__file__).resolve().parent.parent
    contract_files=[p for p in (root/'阶段A').glob('A05.*.md')]
    result={"status":"PASS","data_mode":"SYNTHETIC","assertions":len(RESULTS),"checks":RESULTS,
            "limits":{"original_collector_runtime":"NOT_RUN","live_data":"NOT_RUN","market_backtest":"NOT_RUN","statistical_power":"NOT_TESTED"},
            "contract_sha256":{str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(contract_files)}}
    output=root/'研究/架构审查/synthetic_validation_results.json'
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    print(json.dumps({"status":result['status'],"assertions":len(RESULTS),"mode":"SYNTHETIC","live_backtest":"NOT_RUN"}))


if __name__ == '__main__':
    run()
