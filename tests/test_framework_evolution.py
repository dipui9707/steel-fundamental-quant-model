"""审查反例：测试约束的经济含义，不用历史盈利证明工程正确。"""
from dataclasses import replace
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import numpy as np
import pandas as pd
import pytest
from stage_c.mechanism_engine import MechanismEngine
from stage_c.regime_macro import MacroRegimeClassifier
from stage_c.risk_firewall import RiskControlFirewall
from stage_e.contract_rollover import ContractRolloverManager, RolloverEvent
from stage_e.execution_engine import ExecutionEngine
from stage_e.position_sizer import PositionSizer, PositionTarget
from stage_e.risk_filter import VettedSignal
from stage_e.signal_generator import TradingSignal, SignalGenerator
from stage_e.trade_recorder import TradeRecorder
from stage_e.performance_analyzer import PerformanceAnalyzer


def sig(direction='LONG'):
    return TradingSignal('2024-01-01','RB',direction,1,100,True,True,'TEST','test')


def vetted(status='PASS',direction='LONG'):
    return VettedSignal('2024-01-01',direction,1,status,False,'',sig(direction),None)


def target(lots):
    return PositionTarget('2024-01-01','LONG' if lots>0 else 'SHORT' if lots<0 else 'FLAT',0,lots,0,0,0,0,'test')


def no_roll(date='2024-01-01',code='rb2405'):
    return RolloverEvent(date,False,code,code,100,100,0,'test')


@pytest.mark.parametrize('lots',[1,-1,4,-4])
def test_close_only_never_increases(lots):
    t=PositionSizer().calculate_position_target(vetted('RESTRICT_CLOSE_ONLY','LONG' if lots>0 else 'SHORT'),1e7,3500,current_lots=lots)
    assert abs(t.target_lots)<=abs(lots)
    assert PositionSizer().calculate_position_target(vetted('RESTRICT_CLOSE_ONLY'),1e7,3500,current_lots=-lots if lots>0 else 0).target_lots==0


def test_risk_budget_distance_and_unknown():
    s=PositionSizer(max_base_leverage=5)
    a=s.calculate_position_target(vetted(),1e6,4000,risk_distance=100,risk_budget_fraction=.01)
    b=s.calculate_position_target(vetted(),1e6,4000,risk_distance=200,risk_budget_fraction=.01)
    assert a.target_lots==10 and b.target_lots==5
    assert s.calculate_position_target(vetted(),1e6,4000,risk_distance=np.nan,risk_budget_fraction=.01).target_lots==0


def test_high_vol_holding_still_limited():
    s=pd.Series(dict(fundamental_direction='Bullish',fbs_score=25,confidence_score=80,spot_confirmation='Confirmed'))
    f=pd.Series(dict(rb_close=3500,ma_20=3480,ma_5=3490,rb_vol_shock_ratio=1.5,vol_shock_ratio=1.5,profit_bf=50))
    x=SignalGenerator().generate_signal('2024-04-01',s,f,current_holding_direction='LONG')
    assert x.is_high_vol_pilot
    v=replace(vetted(),raw_signal=x)
    assert PositionSizer(max_base_leverage=5).calculate_position_target(v,1e7,3500).effective_leverage<=2


def test_duplicate_proxy_default_off():
    g=SignalGenerator()
    assert not g.enable_carry_gate and not g.enable_carry_sizer


def fixture_contracts():
    rows=[]
    for date,oi1,oi2 in [('2024-03-01',100,90),('2024-03-04',50,120),('2024-03-05',200,100)]:
        for c,op,oi in [('2405',100,oi1),('2410',130,oi2)]:
            rows.append(dict(date=date,contract_code=c,contract_type='SPECIFIC',open=op,close=op,high=op+5,low=op-5,settlement=op,volume=1,open_interest=oi))
    return pd.DataFrame(rows)


def test_roll_uses_previous_oi_and_two_actual_prices(tmp_path):
    p=tmp_path/'contracts.parquet';fixture_contracts().to_parquet(p)
    m=ContractRolloverManager(parquet_path=str(p))
    assert m.get_active_contract('2024-03-04')['contract_code']=='rb2405'
    e=m.check_rollover_event('2024-03-05')
    assert e.new_contract=='rb2410' and e.old_open_price==100 and e.new_open_price==130 and e.roll_spread==30


def test_missing_selected_quote_fails_instead_of_main(tmp_path):
    df=fixture_contracts();df=df[~((df.date=='2024-03-04')&(df.contract_code=='2405'))]
    p=tmp_path/'bad.parquet';df.to_parquet(p)
    with pytest.raises(ValueError,match='缺当日报价'):ContractRolloverManager(parquet_path=str(p))


def test_roll_to_flat_does_not_reopen_and_allocates_all_fees():
    e=ExecutionEngine(initial_capital=1e6,slippage_ticks=0,commission_rate=.001)
    e.execute_next_bar('2024-03-01',target(2),100,100,100,no_roll(), 'rb2405')
    ev=RolloverEvent('2024-03-05',True,'rb2405','rb2410',110,140,30,'test')
    e.execute_next_bar('2024-03-05',target(0),140,140,140,ev,'rb2410')
    assert e.current_lots==0 and e.cumulative_fees==pytest.approx(4.2)
    assert e.trade_records[0].pnl==pytest.approx(195.8)
    assert e.daily_snapshots[-1]['total_equity']-1e6==pytest.approx(e.trade_records[0].pnl)


def test_roll_gap_is_not_price_profit():
    e=ExecutionEngine(initial_capital=1e6,slippage_ticks=0,commission_rate=0)
    e.execute_next_bar('2024-03-01',target(2),100,100,100,no_roll(),'rb2405')
    ev=RolloverEvent('2024-03-05',True,'rb2405','rb2410',110,140,30,'test')
    r=e.execute_next_bar('2024-03-05',target(2),140,140,140,ev,'rb2410')
    assert r['total_equity']==1e6+200 and e.avg_entry_price==140


def test_small_required_reduction_not_ignored():
    e=ExecutionEngine(slippage_ticks=0,commission_rate=0)
    e.execute_next_bar('2024-01-01',target(100),100,100,100,no_roll(),'rb2405')
    e.execute_next_bar('2024-01-02',target(99),100,100,100,no_roll(),'rb2405')
    assert e.current_lots==99


def mechanism_frame():
    dates=pd.bdate_range('2024-01-01',periods=50)
    n=np.arange(50)//5
    return pd.DataFrame(dict(building_deal_volume=100+n,rebar_total_inv=1000-10*n,rebar_weekly_prod=200-n,profit_bf=-50,hot_metal_247=250-n,rb_close=3500,ma_20=3490),index=dates.strftime('%Y-%m-%d'))


def test_mechanism_prefix_invariance_and_separate_reviews():
    f=mechanism_frame();s,e=MechanismEngine().evaluate(f);p,pe=MechanismEngine().evaluate(f.iloc[:28])
    pd.testing.assert_frame_equal(s.iloc[:28],p)
    pd.testing.assert_frame_equal(e.iloc[:len(pe)].reset_index(drop=True),pe.reset_index(drop=True))
    pred=e[e.event_type.eq('PREDICTION')];reviews=e[e.event_type.eq('REVIEW')]
    assert pred.hypothesis_id.is_unique
    dates=pred.set_index('hypothesis_id').issued_at
    assert all(row.observed_at>dates[row.hypothesis_id] for row in reviews.itertuples())
    assert set(reviews.status)=={'CONFIRMED'}


def test_unknown_not_neutral():
    f=mechanism_frame();f['rebar_total_inv']=np.nan
    s,e=MechanismEngine().evaluate(f)
    assert set(s.mechanism_demand)=={'UNKNOWN'}
    assert set(s.mechanism_external)=={'UNKNOWN'}
    assert not e.get('family',pd.Series(dtype=str)).eq('DEMAND').any()


def test_inventory_acceleration_does_not_imply_destock():
    f=mechanism_frame();n=np.arange(50)//5;f['rebar_total_inv']=1000+20*n-n*n
    s,_=MechanismEngine().evaluate(f)
    assert s.iloc[20].observed_week_inventory_change>0
    assert s.iloc[20].observed_week_inventory_acceleration<0
    assert s.iloc[20].physical_inventory_trajectory=='Accumulating'


def test_mechanism_can_fail_and_expire():
    f=mechanism_frame();f.rebar_total_inv=np.arange(50)//5+1000
    _,e=MechanismEngine().evaluate(f)
    assert 'FAILED' in set(e.status.dropna())
    f.rebar_total_inv=1000
    _,e=MechanismEngine().evaluate(f)
    assert 'EXPIRED' in set(e.status.dropna())


def test_price_spike_not_policy_stimulus():
    r=MacroRegimeClassifier().classify_row(pd.Series(dict(rb_vol_shock_ratio=3,vol_shock_ratio=3,rb_ret_5d=.08)))
    assert r['macro_policy_bias']=='Market_Rally'


def test_divergence_severity_symmetric():
    firewall=RiskControlFirewall()
    f=pd.Series(dict(rb_close=3500,ma_20=3500,data_freshness_ratio=1))
    a=firewall.evaluate(pd.Series(dict(divergence_area=16,fundamental_direction='Bullish')),f,'long')
    b=firewall.evaluate(pd.Series(dict(divergence_area=-16,fundamental_direction='Bullish')),f,'long')
    assert a.status==b.status=='FORCED_LIQUIDATION'


def test_simulation_cannot_write_real_ledger():
    with pytest.raises(ValueError):TradeRecorder(str(Path(__file__).resolve().parents[1]/'交易/交易记录.csv'))


def test_sharpe_uses_mean_daily_excess():
    ret=pd.Series([0,.1,-.05,.02,-.01]);eq=1e6*(1+ret).cumprod()
    df=pd.DataFrame(dict(date=pd.date_range('2024-01-01',periods=5).strftime('%Y-%m-%d'),total_equity=eq,daily_return=ret,net_asset_value=eq/1e6))
    p=PerformanceAnalyzer().analyze_equity_and_trades(df,pd.DataFrame())
    assert p['sharpe_ratio']==pytest.approx(round((ret.mean()*250-.02)/(ret.std()*np.sqrt(250)),2))


def test_reverse_intent_cannot_bypass_current_position_stop():
    from stage_e.risk_filter import RiskFilterAdapter
    v=RiskFilterAdapter().vet_signal('2024-01-02',sig('SHORT'),
        pd.Series(dict(fundamental_direction='Neutral')),
        pd.Series(dict(rb_close=3400,ma_20=3500,data_freshness_ratio=1)),
        current_holding_direction='LONG')
    assert v.vetted_direction=='FLAT' and v.firewall_status=='FORCED_LIQUIDATION'


def test_reversal_closed_pnl_includes_only_allocated_fees():
    e=ExecutionEngine(initial_capital=1e6,slippage_ticks=0,commission_rate=.001)
    e.execute_next_bar('2024-01-01',target(2),100,100,100,no_roll(),'rb2405')
    e.execute_next_bar('2024-01-02',target(-3),110,110,110,no_roll(),'rb2405')
    e.execute_next_bar('2024-01-03',target(0),105,105,105,no_roll(),'rb2405')
    assert sum(x.pnl for x in e.trade_records)==pytest.approx(e.daily_snapshots[-1]['total_equity']-1e6)


def test_dominant_contract_months_steel_vs_raw():
    from framework_rules import MAIN_CONTRACT_MONTHS_MAP, STEEL_MAIN_MONTHS, RAW_MATERIAL_MAIN_MONTHS
    assert MAIN_CONTRACT_MONTHS_MAP['rb'] == ('01', '05', '10') == STEEL_MAIN_MONTHS
    assert MAIN_CONTRACT_MONTHS_MAP['hc'] == ('01', '05', '10') == STEEL_MAIN_MONTHS
    assert MAIN_CONTRACT_MONTHS_MAP['i'] == ('01', '05', '09') == RAW_MATERIAL_MAIN_MONTHS
    assert MAIN_CONTRACT_MONTHS_MAP['j'] == ('01', '05', '09') == RAW_MATERIAL_MAIN_MONTHS
    assert MAIN_CONTRACT_MONTHS_MAP['jm'] == ('01', '05', '09') == RAW_MATERIAL_MAIN_MONTHS


def test_contract_rollover_manager_defaults_by_symbol(tmp_path):
    # 成材端默认 01/05/10，原料端默认 01/05/09
    rows_raw = []
    for date, oi1, oi2 in [('2024-03-01', 100, 90), ('2024-03-04', 50, 120), ('2024-03-05', 200, 100)]:
        for c, op, oi in [('2405', 800, oi1), ('2409', 820, oi2)]:
            rows_raw.append(dict(date=date, contract_code=c, contract_type='SPECIFIC',
                                open=op, close=op, high=op+5, low=op-5, settlement=op,
                                volume=1, open_interest=oi))
    p_raw = tmp_path / 'raw_contracts.parquet'
    pd.DataFrame(rows_raw).to_parquet(p_raw)

    mgr_iron = ContractRolloverManager(symbol='i', parquet_path=str(p_raw))
    assert mgr_iron.main_months == ('01', '05', '09')
    assert mgr_iron.get_active_contract('2024-03-04')['contract_code'] == 'i2405'
    ev = mgr_iron.check_rollover_event('2024-03-05')
    assert ev.new_contract == 'i2409'
    assert ev.roll_spread == 20.0
