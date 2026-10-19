#!/usr/bin/env python3
"""候选框架验证入口：冻结设定、同条件对照、新建实验目录、不写真实交易台账。"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import uuid
import shutil
import platform
import pandas as pd
import numpy as np
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from framework_rules import FRAMEWORK_VERSION, DEFAULT_RISK_FRACTION
from stage_c.state_engine import StageCStateEngine
from stage_e.backtest_engine import BacktestEngine
from stage_e.comparison_signals import ComparisonSignals


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(start='2021-01-04', end=None, output=None):
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = Path(output) if output else ROOT/'研究'/'回测实验'/f'{stamp}_{uuid.uuid4().hex[:8]}'
    out.mkdir(parents=True, exist_ok=False)
    paths = [ROOT/'数据/加工/阶段B_特征宽表.parquet', ROOT/'数据/原始/期货合约全量日线/standardized/rb_daily.parquet']
    source = {str(p.relative_to(ROOT)): sha(p) for p in paths}
    code_paths = sorted([*ROOT.glob('stage_[b-e]/*.py'),ROOT/'framework_rules.py',Path(__file__)])
    code = {str(p.relative_to(ROOT)):sha(p) for p in code_paths}
    for path in code_paths:
        destination = out/'source_snapshot'/path.relative_to(ROOT)
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(path,destination)
    features = pd.read_parquet(paths[0]).sort_index()
    features.index = features.index.astype(str)
    features['ma_20'] = features.rb_close.rolling(20).mean()
    state_engine = StageCStateEngine()
    states = state_engine.synthesize_states(features)
    experiment_features = features.loc[start:end].copy()
    experiment_states = states.loc[experiment_features.index].copy()
    if experiment_features.empty:
        raise ValueError('实验区间为空')
    states.to_parquet(out/'candidate_states.parquet')
    events = state_engine.mechanism_events
    predictions = events[events.event_type.eq('PREDICTION')].dropna(axis=1,how='all')
    reviews = events[events.event_type.eq('REVIEW')].dropna(axis=1,how='all')
    for name, data in [('predictions', predictions), ('reviews', reviews)]:
        # 单次实验独立冻结；复核另存，禁止回写最初预测。
        with (out/f'{name}.jsonl').open('x') as fh:
            for rec in data.to_dict('records'):
                clean = {k:v for k,v in rec.items() if not isinstance(v,float) or np.isfinite(v)}
                fh.write(json.dumps(clean, ensure_ascii=False)+'\n')
    common = dict(initial_capital=10_000_000,slippage_ticks=1.0,commission_rate=.0001,
                  margin_rate=.10,max_base_leverage=1.0,max_margin_utilization=.50,
                  scale_by_confidence=False,common_risk_controls=True)
    manifest = dict(version=FRAMEWORK_VERSION, created_at=stamp,
        experiment_start=str(experiment_features.index[0]),experiment_end=str(experiment_features.index[-1]),
        data_hashes=source,code_hashes=code,git_head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        runtime={'python':platform.python_version(),'pandas':pd.__version__,'numpy':np.__version__},
        settings=common, signal_settings=vars(ComparisonSignals('FULL').core), risk_budgets={'fixed_1x':None, 'risk_1pct':DEFAULT_RISK_FRACTION},
        validation_status='EXPLORATORY_CURRENT_VINTAGE_NOT_OUT_OF_SAMPLE',
        limitations=['历史已用于研发，不能重新命名为独立样本外','宽表发布时间与历史版本尚未逐条核实',
                    '01/05/10候选池内按前日持仓量选约，早期实约覆盖不全；本次从2021年开始',
                    '收盘信号下一日开盘撮合；没有涨跌停排队、盘中追加保证金及冲击成本模型',
                    '不合格结算价使用收盘估值代理且逐日标注','连续主力仅用于信号特征，成交使用实约',
                    '机制兑现率不代表因果识别；需求/供给候选仅覆盖多头，与双向策略范围不同'])
    (out/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
    metrics, years = [], []
    for budget, fraction in manifest['risk_budgets'].items():
        engine = BacktestEngine(experiment_features,experiment_states, risk_budget_fraction=fraction, **common)
        engine.rollover_mgr.get_full_map().loc[start:end].to_csv(out/f'{budget}_contracts.csv')
        for mode in ['PRICE','SUPPLY','PRICE_FUNDAMENTAL','FULL','FULL_WITH_DUPLICATE_PROXY','MECHANISM_CANDIDATE']:
            label = budget+'_'+mode
            result = engine.run_backtest(signal_generator=ComparisonSignals(mode), strategy_label=label, verbose=False)
            result.equity_df.to_parquet(out/f'{label}_equity.parquet')
            result.trades_df.to_csv(out/f'{label}_trades.csv',index=False)
            result.vetted_signals_df.to_parquet(out/f'{label}_decisions.parquet')
            eq = result.equity_df
            if not np.allclose(eq.total_equity,eq.available_cash+eq.margin_occupied,atol=.02):
                raise AssertionError(f'{label}: 权益恒等式未通过')
            if not np.isfinite(eq.total_equity).all():
                raise AssertionError(f'{label}: 权益非有限值')
            p = {k:v for k,v in result.performance.items() if k != 'monthly_returns_table'}
            signs = np.sign(eq.lots)
            p['position_episodes'] = int(((signs != signs.shift(1).fillna(0)) & (signs != 0)).sum())
            p['marking_close_proxy_days'] = int(eq.marking_basis.eq('CLOSE_PROXY').sum())
            p['budget'] = budget
            p['mode'] = mode
            metrics.append(p)
            for year,g in eq.groupby(eq.date.str[:4]):
                years.append(dict(strategy=label,year=year,return_pct=((1+g.daily_return).prod()-1)*100,
                                  days=len(g)))
            print(label, 'CAGR',p['cagr_pct'],'MDD',p['max_drawdown_pct'],'Sharpe',p['sharpe_ratio'],flush=True)
    pd.DataFrame(metrics).to_csv(out/'comparison.csv',index=False)
    pd.DataFrame(years).to_csv(out/'year_blocks.csv',index=False)
    # 无论盈亏方向如何，都由本次记录生成；不填写预设成功叙事。
    lines = ['# 框架候选版本验证', '', f'版本：{FRAMEWORK_VERSION}。期间：{manifest["experiment_start"]} 至 {manifest["experiment_end"]}。',
        '', '这是当前数据版本上的历史探索性比较，不能证明实盘收益或样本外有效性。', '',
        '所有组共用初始资金、实约映射、价格风险过滤、手续费、滑点、最高1倍名义杠杆。第二组再加1%权益风险预算，距离为20日ATR的2倍、最低价格的1.5%。这些是固定研究设定，未作收益寻优。', '',
        '|预算|策略|年化收益%|最大回撤%|夏普|平均杠杆|持仓段数|', '|---|---|---:|---:|---:|---:|---:|']
    for p in metrics:
        lines.append(f'|{p["budget"]}|{p["mode"]}|{p["cagr_pct"]:.2f}|{p["max_drawdown_pct"]:.2f}|{p["sharpe_ratio"]:.2f}|{p["average_leverage"]:.3f}|{p["position_episodes"]}|')
    lines += ['', 'PRICE=价格趋势；SUPPLY=供给评分；PRICE_FUNDAMENTAL=价格与原基本面同向；FULL=现有完整规则；FULL_WITH_DUPLICATE_PROXY=恢复基差衍生Carry重复门禁/乘数；MECHANISM_CANDIDATE=需求或减产后库存预测兑现并且价格向上。', '',
              '三类产业假设分别登记预测与复核。以下是全历史机制账本（含比较区间之前的预热观察），按独立预测编号计数，不把每日前值填充计为新增样本。', '']
    if not reviews.empty:
        for (family,status),n in reviews.groupby(['family','status']).size().items():
            lines.append(f'- {family} / {status}：{n} 个已结束预测。')
    lines += ['', '限制：'] + [f'- {x}。' for x in manifest['limitations']]
    lines += ['', '通过工程核对：逐日权益恒等式、有限值；具体逻辑反例见 tests/test_framework_evolution.py。',
              '下一步按冻结规则积累新增周度观察；不能依据本表挑最赚钱的参数后宣称独立验证。']
    (out/'验证报告.md').write_text('\n'.join(lines)+'\n')
    artifacts = {str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()}
    (out/'artifact_hashes.json').write_text(json.dumps(artifacts,ensure_ascii=False,indent=2))
    print('OUTPUT', out,flush=True)
    return out

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--start',default='2021-01-04')
    parser.add_argument('--end')
    parser.add_argument('--output')
    args=parser.parse_args()
    run(args.start,args.end,args.output)
