#!/usr/bin/env python3
"""原策略/成本路径成对对照，冻结输入/代码，单独导出实际持仓段追高损失。"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import shutil
import sys
import uuid
import numpy as np
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from stage_c.state_engine import StageCStateEngine
from stage_e.backtest_engine import BacktestEngine
from stage_e.signal_generator import SignalGenerator
from stage_e.cost_push_router import CostPushRouter, CostPushConfig, prepare_cost_push_features, VERSION
from stage_e.cost_push_diagnostics import cost_position_episodes


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def run(start='2021-01-04',end=None,output=None,carry=True,risk_mode='full',max_margin_utilization=.5,enable_tactical=False):
    config = CostPushConfig(full_margin_utilization=max_margin_utilization)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=Path(output) if output else ROOT/'研究/回测实验'/f'{stamp}_cost_push_{uuid.uuid4().hex[:8]}'
    out.mkdir(parents=True,exist_ok=False)
    paths=[ROOT/'数据/加工/阶段B_特征宽表.parquet',ROOT/'数据/原始/期货合约全量日线/standardized/rb_daily.parquet']
    codes=sorted([*ROOT.glob('stage_[b-e]/*.py'),ROOT/'framework_rules.py',Path(__file__)])
    for p in codes:
        target=out/'source_snapshot'/p.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,target)
    features=pd.read_parquet(paths[0]).sort_index()
    features.index=features.index.astype(str)
    features=prepare_cost_push_features(features)
    features['ma_20']=features.cp_ma20
    states=StageCStateEngine().synthesize_states(features)
    f=features.loc[start:end].copy();s=states.loc[f.index].copy()
    if f.empty: raise ValueError('实验区间为空')
    common=dict(initial_capital=10_000_000,slippage_ticks=1.,commission_rate=.0001,
                margin_rate=.1,max_margin_utilization=max_margin_utilization,scale_by_confidence=True,
                common_risk_controls=risk_mode=='price-only',enable_tactical_execution=enable_tactical)
    signal_settings=dict(enable_carry_gate=carry,enable_carry_sizer=carry)
    version_label = 'framework-0.10-candidate' if enable_tactical else VERSION
    manifest=dict(version=version_label,created_at=stamp,start=str(f.index[0]),end=str(f.index[-1]),
        validation_status='EXPLORATORY_CURRENT_VINTAGE_NOT_OUT_OF_SAMPLE',
        tactical_execution=enable_tactical,
        data_hashes={str(p.relative_to(ROOT)):sha(p) for p in paths},
        code_hashes={str(p.relative_to(ROOT)):sha(p) for p in codes},
        runtime=dict(python=platform.python_version(),pandas=pd.__version__,numpy=np.__version__),
        common_settings=common,baseline_settings=signal_settings,candidate_settings=asdict(config),risk_mode=risk_mode,
        limitations=['原始PIT发布时间与版本尚未逐条核实；本次是当前版本探索性回放',
        '成本推升由价格代理识别，不证明政策或原料供需因果；现货/出库确认不等同产业全面改善',
        '成本试单/确认仓使用满仓资金利用率的20%/50%；取消原固定损失预算，距离损失另行估算，不是最大亏损保证',
        '连续价格生成触发/止损，实际合约成交；连续价格换月跳变可能产生伪突破',
        '不模拟涨跌停排队/冲击成本/盘中追加保证金；成本通道不支持只靠宏观分数入场',
        '2019-10-17以前可能使用已有MAIN日历代理；默认从2021开始',
        '追高表的最差浮动为账户日终结算/收盘代理口径，不是盘中价格MAE',
        '新通道改变后续持仓路径；两策略总收益差不是新增成本交易的纯因果贡献'])
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    f.to_parquet(out/'features.parquet');s.to_parquet(out/'states.parquet')
    results={}
    for label, generator in [('BASELINE',SignalGenerator(**signal_settings)),
                              ('COST_PUSH',CostPushRouter(SignalGenerator(**signal_settings),config))]:
        engine=BacktestEngine(f,s,**common)
        if label=='BASELINE': engine.rollover_mgr.get_full_map().loc[start:end].to_csv(out/'contracts.csv')
        result=engine.run_backtest(signal_generator=generator,strategy_label=label,verbose=False)
        eq=result.equity_df
        assert np.isfinite(eq.total_equity).all()
        assert np.allclose(eq.total_equity,eq.available_cash+eq.margin_occupied,atol=.02)
        result.equity_df.to_parquet(out/f'{label}_equity.parquet')
        result.trades_df.to_csv(out/f'{label}_trades.csv',index=False)
        result.vetted_signals_df.to_parquet(out/f'{label}_decisions.parquet')
        result.vetted_signals_df.to_csv(out/f'{label}_decisions.csv',index=False)
        results[label]=result
    episodes=cost_position_episodes(results['COST_PUSH'],results['BASELINE'],common['initial_capital'])
    episodes.to_csv(out/'cost_episodes.csv',index=False)
    metrics=pd.DataFrame([{k:v for k,v in r.performance.items() if k!='monthly_returns_table'} for r in results.values()])
    metrics.to_csv(out/'comparison.csv',index=False)
    rows=[]
    for label,r in results.items():
        for year,g in r.equity_df.groupby(r.equity_df.date.str[:4]):
            rows.append(dict(strategy=label,year=year,return_pct=((1+g.daily_return).prod()-1)*100,days=len(g)))
    pd.DataFrame(rows).to_csv(out/'year_blocks.csv',index=False)
    closed=episodes[episodes.closed.astype(bool)]
    chase=closed[closed.above_old_2_5pct_gate.astype(bool)]
    summary=dict(actual_cost_episodes=len(episodes),closed_cost_episodes=len(closed),
                 closed_loss_episodes=int((closed.net_account_pnl<0).sum()),
                 old_gate_exceeding_closed_episodes=len(chase),
                 old_gate_exceeding_loss_episodes=int((chase.net_account_pnl<0).sum()),
                 old_gate_exceeding_net_pnl=float(chase.net_account_pnl.sum()) if len(chase) else None,
                 confirmation_timeouts=int(closed.exit_reason.eq('CONFIRMATION_TIMEOUT').sum()),
                 price_failure_exits=int(closed.exit_reason.eq('BREAKOUT_OR_MA_FAILURE').sum()),
                 note='零样本的损益为null；未平仓不计胜负。2.5%仅作原入场上限对照标签。')
    (out/'chasing_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    lines=['# 成本推升候选对照','',f'{VERSION}，{f.index[0]} 至 {f.index[-1]}；风控模式 {risk_mode}，Carry={carry}。',
           '', '查看 comparison.csv 比较全账户风险收益；cost_episodes.csv 按实际成交持仓段检查追高、超时和破位损失；year_blocks.csv 分年查看。',
           '两组共同设定一致，成本通道按满仓资金使用率的20%/50%分配，仍接受风控降档。full 模式保留原防火墙，并对成本顺势多头的中度背离单独限仓；price-only 与上一轮共同价格风控实验口径对应。',
           '',f'实际成本持仓段 {len(episodes)}；已平仓 {len(closed)}，其中亏损 {summary["closed_loss_episodes"]}；超过旧2.5%距离的已平仓段 {len(chase)}。',
           '以上为程序输出，不构成有效性通过；少量或零新增交易时不能判断追高风险变化。','']
    lines += ['- '+x for x in manifest['limitations']]
    (out/'使用与限制.md').write_text('\n'.join(lines)+'\n')
    hashes={str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'artifact_hashes.json').write_text(json.dumps(hashes,ensure_ascii=False,indent=2))
    print('OUTPUT',out,flush=True)
    return out


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--start',default='2021-01-04');p.add_argument('--end');p.add_argument('--output')
    p.add_argument('--without-carry',action='store_true')
    p.add_argument('--risk-mode',choices=['full','price-only'],default='full')
    p.add_argument('--max-margin-utilization',type=float,default=.5)
    p.add_argument('--enable-tactical',action='store_true',help='激活跨周期战术执行护航 (v0.10)')
    a=p.parse_args()
    run(a.start,a.end,a.output,not a.without_carry,a.risk_mode,a.max_margin_utilization,a.enable_tactical)
