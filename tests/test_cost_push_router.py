"""成本路径反例与实际成交生命周期；不以历史盈利作为测试断言。"""
from dataclasses import replace
import json
import numpy as np
import pandas as pd
import pytest
from stage_e.cost_push_router import CostPushRouter, prepare_cost_push_features, DRIVER
from stage_e.signal_generator import TradingSignal
from stage_e.position_sizer import PositionSizer
from stage_e.risk_filter import RiskFilterAdapter, VettedSignal
from stage_c.risk_firewall import RiskControlFirewall


class FlatCore:
    def generate_signal(self, date_str, *args, **kwargs):
        return TradingSignal(date_str,'RB','FLAT',0,20,False,False,'BASE','low confidence')


def features(**updates):
    vals = dict(rb_close=4100.,rb_low=4070.,cp_ma20=4000.,cp_atr20=50.,cp_high20=4080.,
                cp_prev_high20=4080.,cp_prev_close=4060.,cp_ret5=.03,
                cp_spot=4000.,cp_spot_ret5=0.,cp_flow5=100.,cp_flow_ratio=1.,
                cost_push_spread_5d=.03,profit_bf=-50.,ma_20=4000.)
    vals.update(updates)
    return pd.Series(vals)


def state(**updates):
    vals=dict(dominant_leader_type='RAW_MATERIAL_SHOCK',fundamental_direction='Bearish',divergence_severity='Moderate')
    vals.update(updates)
    return pd.Series(vals)


def generate(router, f=None, holding='FLAT', date='2024-01-01'):
    return router.generate_signal(date,state(),features() if f is None else f,current_holding_direction=holding)


def filled():
    r=CostPushRouter(FlatCore()); s=generate(r);r.on_execution(0,5,s)
    return r,s


def test_low_profit_low_confidence_can_pilot_but_never_fake_confirmation():
    r=CostPushRouter(FlatCore());s=generate(r)
    assert s.direction=='LONG' and s.confidence_score==20 and not s.spot_confirmed
    assert s.risk_budget_fraction is None and s.strategy_margin_utilization==.10 and s.participation_stage=='PILOT'
    assert json.loads(s.gate_diagnostics)['baseline_direction']=='FLAT'
    assert r.position is None
    r.on_execution(0,0,s)
    assert r.position is None


@pytest.mark.parametrize('key,value', [('cp_spot',np.nan),('cp_flow_ratio',np.nan),('cp_atr20',0),
    ('rb_close',4200.),('cp_spot_ret5',-.02),('cp_flow_ratio',.6),('cost_push_spread_5d',0.)])
def test_no_blind_chasing_or_missing_as_neutral(key,value):
    assert generate(CostPushRouter(FlatCore()),features(**{key:value})).direction=='FLAT'


def test_legacy_position_never_relabelled_or_stacked():
    r=CostPushRouter(FlatCore())
    assert generate(r,holding='LONG').entry_driver=='FUNDAMENTAL'
    r.on_execution(5,5,None)
    assert r.position is None


def test_confirmation_requires_new_spot_and_flow_and_profit_limits_budget():
    r,_=filled()
    a=generate(r,holding='LONG');assert a.participation_stage=='PILOT' and not a.allow_position_increase
    b=generate(r,features(cp_spot=4020.,cp_flow5=90.,profit_bf=200),holding='LONG')
    assert b.participation_stage=='PILOT'
    c=generate(r,features(cp_spot=4020.,cp_flow5=100.,profit_bf=np.nan),holding='LONG')
    assert c.participation_stage=='TRANSMISSION_CONFIRMED' and c.risk_budget_fraction is None and c.strategy_margin_utilization==.10
    assert c.spot_confirmed


def test_confirmed_budget_and_no_daily_pyramiding():
    r,_=filled()
    a=generate(r,features(cp_spot=4020.,profit_bf=200),holding='LONG')
    assert a.risk_budget_fraction is None and a.strategy_margin_utilization==.25 and a.allow_position_increase
    b=generate(r,features(cp_spot=4020.,profit_bf=200),holding='LONG')
    assert not b.allow_position_increase


def test_no_new_evidence_times_out_then_cools_down():
    r,_=filled()
    for _ in range(4): assert generate(r,holding='LONG').direction=='LONG'
    exit_signal=generate(r,holding='LONG')
    assert exit_signal.invalidation_reason=='CONFIRMATION_TIMEOUT'
    r.on_execution(5,0,exit_signal)
    for _ in range(3): assert generate(r).direction=='FLAT'
    assert generate(r).direction=='LONG'


def test_breakout_failure_and_raw_slowdown_not_automatic_exit():
    r,_=filled()
    assert generate(r,features(cost_push_spread_5d=.001),holding='LONG').direction=='LONG'
    e=generate(r,features(rb_close=4020),holding='LONG')
    assert e.invalidation_reason=='BREAKOUT_OR_MA_FAILURE'


def test_only_first_pullback_and_raw_push_still_required():
    r=CostPushRouter(FlatCore())
    generate(r,features(cp_ma20=3900))  # 延伸过远，记录突破但不成交。
    r.on_execution(0,0,None)
    s=generate(r,features(cp_high20=4120,cp_prev_close=4085,rb_low=4080))
    assert s.entry_trigger=='FIRST_PULLBACK'
    r.on_execution(0,0,s)
    assert generate(r,features(cp_high20=4120,cp_prev_close=4085,rb_low=4080)).direction=='FLAT'


def test_driver_changes_only_medium_divergence_not_hard_stop_or_halt():
    fw=RiskControlFirewall()
    assert fw.evaluate(state(),features(),position_intent='long').status=='RESTRICT_CLOSE_ONLY'
    assert fw.evaluate(state(),features(),position_intent='long',entry_driver=DRIVER).status=='CAUTION'
    assert fw.evaluate(state(),features(data_freshness_ratio=.1),position_intent='long',entry_driver=DRIVER).status=='TRADING_HALT'
    assert fw.evaluate(state(),features(rb_close=3800),position_intent='long',entry_driver=DRIVER).status=='FORCED_LIQUIDATION'
    r,_=filled();s=generate(r,holding='LONG')
    vetted=RiskFilterAdapter().vet_signal('t',s,state(),features(rb_close=3800),'LONG')
    assert vetted.vetted_direction=='FLAT'


def test_route_risk_budget_firewall_and_existing_lots_all_bind():
    r=CostPushRouter(FlatCore());s=generate(r)
    v=VettedSignal('t','LONG',.5,'CAUTION',False,'',s,None)
    p=PositionSizer().calculate_position_target(v,1_000_000,4100,risk_distance=100)
    assert p.target_lots==12  # 10%使用率对应24手，中度背离容量乘数50%
    p=PositionSizer().calculate_position_target(replace(v,firewall_status='RESTRICT_CLOSE_ONLY'),1e6,4100,current_lots=0,risk_distance=100)
    assert p.target_lots==0
    missing=replace(v,raw_signal=replace(s,risk_distance_pct=None))
    assert PositionSizer().calculate_position_target(missing,1e6,4100,risk_distance=100).target_lots==0


def test_feature_generation_prefix_invariant_and_no_fill():
    f=pd.DataFrame(dict(rb_close=np.arange(40)+4000.,spot_hz_zhongtian=np.arange(40)+3900.,flow_hz_outflow=np.arange(40)+100))
    a=prepare_cost_push_features(f)
    pd.testing.assert_frame_equal(a.iloc[:30],prepare_cost_push_features(f.iloc[:30]))
    f.loc[30,'spot_hz_zhongtian']=np.nan
    assert pd.isna(prepare_cost_push_features(f).loc[35,'cp_spot_ret5'])


def test_above_old_distance_can_enter_when_atr_distance_bounded():
    s=generate(CostPushRouter(FlatCore()),features(rb_close=4120,cp_atr20=60,cp_high20=4100))
    assert s.direction=='LONG'
    assert json.loads(s.gate_diagnostics)['entry_ma_distance_pct']>.025


def test_execution_feedback_t_plus_one_and_episode_accounting(monkeypatch):
    from stage_e import backtest_engine as module
    from stage_e.contract_rollover import RolloverEvent
    from stage_e.cost_push_diagnostics import cost_position_episodes
    dates=pd.bdate_range('2024-01-02',periods=7).strftime('%Y-%m-%d')
    prices=[4100.,4105.,4020.,4010.,4000.,4000.,4000.]
    class Map:
        def __init__(self, **kwargs): pass
        def get_active_contract(self,dt):
            p=prices[list(dates).index(dt)]
            return dict(open=p,close=p,settlement=p,contract_code='rb2405',marking_basis='SETTLEMENT')
        def check_rollover_event(self,dt):
            return RolloverEvent(dt,False,'rb2405','rb2405',4000.,4000.,0.,'test')
    monkeypatch.setattr(module,'ContractRolloverManager',Map)
    f=pd.DataFrame([features(rb_close=p) for p in prices],index=dates)
    states=pd.DataFrame([state() for _ in prices],index=dates)
    engine=module.BacktestEngine(f,states,initial_capital=1e6)
    baseline=engine.run_backtest(signal_generator=FlatCore(),verbose=False)
    candidate=engine.run_backtest(signal_generator=CostPushRouter(FlatCore()),verbose=False)
    eq=candidate.equity_df
    assert eq.iloc[0].lots==0 and eq.iloc[1].lots>0
    assert bool(eq.iloc[1].cost_position_active) and not bool(eq.iloc[3].cost_position_active)
    ep=cost_position_episodes(candidate,baseline,1e6)
    assert len(ep)==1 and ep.iloc[0].closed
    assert ep.iloc[0].entry_date==dates[1] and ep.iloc[0].end_date==dates[3]
    assert ep.iloc[0].exit_reason=='BREAKOUT_OR_MA_FAILURE'
    assert ep.iloc[0].net_account_pnl==pytest.approx(eq.iloc[3].total_equity-1e6)
    assert ep.iloc[0].net_account_pnl<0
    # 同一对象重跑必须清空上次上下文。
    router=CostPushRouter(FlatCore())
    a=engine.run_backtest(signal_generator=router,verbose=False)
    b=engine.run_backtest(signal_generator=router,verbose=False)
    pd.testing.assert_frame_equal(a.equity_df,b.equity_df)


@pytest.mark.parametrize('margin_rate',[.08,.10,.15])
def test_margin_sizing_uses_actual_margin_rate(margin_rate):
    r=CostPushRouter(FlatCore());s=generate(r)
    v=VettedSignal('t','LONG',1.,'PASS',False,'',s,None)
    size=PositionSizer(default_margin_rate=margin_rate)
    a=size.calculate_position_target(v,1e6,4000,risk_distance=100)
    assert a.target_lots==int(100000/(4000*10*margin_rate))
    assert a.estimated_margin<=100000
    confirmed=replace(v,raw_signal=replace(s,strategy_margin_utilization=.25))
    b=size.calculate_position_target(confirmed,1e6,4000,risk_distance=100)
    assert b.target_lots==int(250000/(4000*10*margin_rate))
    assert b.estimated_margin<=250000


def test_explicit_smaller_account_budget_and_high_vol_still_bind():
    s=generate(CostPushRouter(FlatCore()))
    v=VettedSignal('t','LONG',1.,'PASS',False,'',s,None)
    size=PositionSizer()
    # 用户另行传入的损失预算仍有效，区别于已撤销的通道固定小预算。
    a=size.calculate_position_target(v,1e6,4000,risk_distance=100,risk_budget_fraction=.005)
    assert a.target_lots==5
    v=replace(v,raw_signal=replace(s,strategy_margin_utilization=.25,is_high_vol_pilot=True))
    b=size.calculate_position_target(v,1e6,4000,risk_distance=100)
    assert b.margin_utilization==.20
    limited=PositionSizer(max_margin_utilization=.08).calculate_position_target(v,1e6,4000,risk_distance=100)
    assert limited.margin_utilization==.08


def test_config_tracks_full_allocation_and_rejects_above_user_ceiling():
    from stage_e.cost_push_router import CostPushConfig
    with pytest.raises(ValueError): CostPushConfig(full_margin_utilization=.6)
    with pytest.raises(ValueError): CostPushConfig(pilot_fraction_of_full=.7)
    r=CostPushRouter(FlatCore(),CostPushConfig(full_margin_utilization=.3))
    assert generate(r).strategy_margin_utilization==.06


def test_same_signal_margin_sizing_increases_real_lots_vs_old_budget():
    s=generate(CostPushRouter(FlatCore()))
    v=VettedSignal('t','LONG',1.,'PASS',False,'',s,None)
    old=replace(v,raw_signal=replace(s,strategy_margin_utilization=None,risk_budget_fraction=.0025,strategy_leverage_cap=.5))
    size=PositionSizer()
    a=size.calculate_position_target(old,1e6,4000,risk_distance=100)
    b=size.calculate_position_target(v,1e6,4000,risk_distance=100)
    assert a.target_lots==2 and b.target_lots==25


def test_overbought_breakout_blocked_until_pullback():
    r = CostPushRouter(FlatCore())
    # 偏离 MA20 超过 3.5% (4160 vs 4000 = 4.0%)，突破但判定高位透支禁追
    s1 = generate(r, features(rb_close=4160, cp_high20=4150, cp_prev_high20=4150, cp_prev_close=4140))
    assert s1.direction == 'FLAT'
    diagnostics = json.loads(s1.gate_diagnostics)
    assert diagnostics['fresh_breakout'] and diagnostics['is_overbought'] and not diagnostics['can_early_breakout']
    assert r.setup is not None
    # 随后回踩至 MA20 均线带企稳反弹 (4015)
    s2 = generate(r, features(rb_close=4015, cp_high20=4180, cp_prev_close=4005, rb_low=4000))
    assert s2.direction == 'LONG' and s2.entry_trigger == 'FIRST_PULLBACK'
    assert s2.strategy_margin_utilization == .20  # 40% of 50% = 20%


def test_second_leg_reentry_after_flush():
    r, s = filled()
    # 模拟止损退出
    exit_signal = generate(r, features(rb_close=3900), holding='LONG')
    assert exit_signal.invalidation_reason == 'BREAKOUT_OR_MA_FAILURE'
    r.on_execution(5, 0, exit_signal)
    assert r.reentry_watch is not None
    # 冷却3天
    for _ in range(3):
        assert generate(r).direction == 'FLAT'
    # 洗盘企稳，重上MA20并突破前5日高点 (4020 > cp_high5=4010)
    s_reentry = generate(r, features(rb_close=4020, cp_prev_close=4005, cp_high5=4010, cost_push_spread_5d=0.02))
    assert s_reentry.direction == 'LONG' and s_reentry.entry_trigger == 'SECOND_LEG_RE_ENTRY'
    assert s_reentry.strategy_margin_utilization == .20


