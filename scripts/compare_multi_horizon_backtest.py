#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/compare_multi_horizon_backtest.py
功能: 多尺度历史融合升级 vs 未融合版本（纯历年全景 / 纯近1年）全景回测与横向对照
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_e.backtest_engine import BacktestEngine, BacktestResult
from stage_e.signal_generator import SignalGenerator


def run_comparative_backtest():
    print("=" * 80)
    print("【开始运行】多尺度融合 vs 未融合版本（纯历年 / 纯近1年）历史回测对比")
    print("=" * 80)

    feat_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
    state_path = BASE_DIR / "数据" / "状态" / "阶段C_全景状态矩阵.parquet"

    feat_df = pd.read_parquet(feat_path)
    state_df = pd.read_parquet(state_path)

    modes = [
        ("未融合·纯历年全景 (Expanding)", "PURE_HISTORICAL"),
        ("未融合·纯近1年滚动 (Rolling 252)", "PURE_1Y"),
        ("多尺度融合升级版 (1Y + Hist 融合)", "MULTI_HORIZON"),
    ]

    results = {}

    for label, mode_key in modes:
        engine = BacktestEngine(
            features_df=feat_df,
            state_matrix=state_df,
            symbol="rb",
            initial_capital=10_000_000.0,
            slippage_ticks=1.0,
            commission_rate=0.0001,
            margin_rate=0.10,
            max_margin_utilization=0.50,
        )
        sig_gen = SignalGenerator(confidence_threshold=40.0, horizon_mode=mode_key)

        res = engine.run_backtest(
            strategy_mode="QUANT_CORE",
            enable_firewall=True,
            strategy_label=label,
            signal_generator=sig_gen,
        )
        results[label] = res

    # 1. 打印综合指标对照表
    print("\n" + "=" * 115)
    print("【三大版本全历史 2018-2026 (2,074 交易日) 综合绩效横向对照表】")
    print("=" * 115)
    headers = [
        "评估维度",
        "未融合·纯历年全景",
        "未融合·纯近1年滚动",
        "多尺度融合升级版",
        "融合改善 (vs 纯历年)",
        "融合改善 (vs 纯近1年)",
    ]
    fmt = f"{headers[0]:<18} | {headers[1]:<18} | {headers[2]:<18} | {headers[3]:<18} | {headers[4]:<18} | {headers[5]:<18}"
    print(fmt)
    print("-" * 115)

    p_h = results["未融合·纯历年全景 (Expanding)"].performance
    p_1 = results["未融合·纯近1年滚动 (Rolling 252)"].performance
    p_m = results["多尺度融合升级版 (1Y + Hist 融合)"].performance

    nav_h = p_h['final_equity'] / 1e7
    nav_1 = p_1['final_equity'] / 1e7
    nav_m = p_m['final_equity'] / 1e7

    metrics = [
        ("累计净值 (NAV)", f"{nav_h:.4f}", f"{nav_1:.4f}", f"{nav_m:.4f}", f"{nav_m - nav_h:+.4f}", f"{nav_m - nav_1:+.4f}"),
        ("累计纯利润 (万元)", f"{(p_h['final_equity']-1e7)/1e4:,.1f}", f"{(p_1['final_equity']-1e7)/1e4:,.1f}", f"{(p_m['final_equity']-1e7)/1e4:,.1f}", f"{(p_m['final_equity'] - p_h['final_equity'])/1e4:+,.1f} 万", f"{(p_m['final_equity'] - p_1['final_equity'])/1e4:+,.1f} 万"),
        ("年化收益率 (CAGR)", f"{p_h['cagr_pct']:.2f}%", f"{p_1['cagr_pct']:.2f}%", f"{p_m['cagr_pct']:.2f}%", f"{p_m['cagr_pct'] - p_h['cagr_pct']:+.2f}%", f"{p_m['cagr_pct'] - p_1['cagr_pct']:+.2f}%"),
        ("最大历史回撤 (MaxDD)", f"{p_h['max_drawdown_pct']:.2f}%", f"{p_1['max_drawdown_pct']:.2f}%", f"{p_m['max_drawdown_pct']:.2f}%", f"{abs(p_h['max_drawdown_pct']) - abs(p_m['max_drawdown_pct']):+.2f}%", f"{abs(p_1['max_drawdown_pct']) - abs(p_m['max_drawdown_pct']):+.2f}%"),
        ("年化夏普比率 (Sharpe)", f"{p_h['sharpe_ratio']:.2f}", f"{p_1['sharpe_ratio']:.2f}", f"{p_m['sharpe_ratio']:.2f}", f"{p_m['sharpe_ratio'] - p_h['sharpe_ratio']:+.2f}", f"{p_m['sharpe_ratio'] - p_1['sharpe_ratio']:+.2f}"),
        ("卡玛比率 (Calmar)", f"{p_h['calmar_ratio']:.2f}", f"{p_1['calmar_ratio']:.2f}", f"{p_m['calmar_ratio']:.2f}", f"{p_m['calmar_ratio'] - p_h['calmar_ratio']:+.2f}", f"{p_m['calmar_ratio'] - p_1['calmar_ratio']:+.2f}"),
        ("交易胜率 (Win Rate)", f"{p_h['win_rate_pct']:.1f}%", f"{p_1['win_rate_pct']:.1f}%", f"{p_m['win_rate_pct']:.1f}%", f"{p_m['win_rate_pct'] - p_h['win_rate_pct']:+.1f}%", f"{p_m['win_rate_pct'] - p_1['win_rate_pct']:+.1f}%"),
        ("盈亏比 (Profit Factor)", f"{p_h['profit_factor']:.2f}", f"{p_1['profit_factor']:.2f}", f"{p_m['profit_factor']:.2f}", f"{p_m['profit_factor'] - p_h['profit_factor']:+.2f}", f"{p_m['profit_factor'] - p_1['profit_factor']:+.2f}"),
        ("总交易笔数", f"{p_h['total_trades']} 笔", f"{p_1['total_trades']} 笔", f"{p_m['total_trades']} 笔", f"{p_m['total_trades'] - p_h['total_trades']:+d} 笔", f"{p_m['total_trades'] - p_1['total_trades']:+d} 笔"),
        ("交易总摩擦成本 (万元)", f"{p_h['total_fees_cny']/1e4:.1f}", f"{p_1['total_fees_cny']/1e4:.1f}", f"{p_m['total_fees_cny']/1e4:.1f}", f"{(p_m['total_fees_cny'] - p_h['total_fees_cny'])/1e4:+.1f} 万", f"{(p_m['total_fees_cny'] - p_1['total_fees_cny'])/1e4:+.1f} 万"),
    ]

    for m in metrics:
        print(f"{m[0]:<18} | {m[1]:<18} | {m[2]:<18} | {m[3]:<18} | {m[4]:<18} | {m[5]:<18}")
    print("=" * 115)

    # 2. 历年逐年净收益横向对比
    print("\n" + "=" * 90)
    print("【历年年度收益率横向对比 (2018 - 2026)】")
    print("=" * 90)
    print(f"{'年份':<8} | {'未融合·纯历年全景':<18} | {'未融合·纯近1年滚动':<18} | {'多尺度融合升级版':<18} | {'融合优势'}")
    print("-" * 90)

    years = ["2018", "2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026"]
    eq_h = results["未融合·纯历年全景 (Expanding)"].equity_df.set_index("date")["total_equity"]
    eq_1 = results["未融合·纯近1年滚动 (Rolling 252)"].equity_df.set_index("date")["total_equity"]
    eq_m = results["多尺度融合升级版 (1Y + Hist 融合)"].equity_df.set_index("date")["total_equity"]

    for yr in years:
        sub_h = eq_h.loc[eq_h.index.str.startswith(yr)]
        sub_1 = eq_1.loc[eq_1.index.str.startswith(yr)]
        sub_m = eq_m.loc[eq_m.index.str.startswith(yr)]

        ret_h = (sub_h.iloc[-1] / sub_h.iloc[0] - 1.0) * 100 if len(sub_h) > 1 else 0.0
        ret_1 = (sub_1.iloc[-1] / sub_1.iloc[0] - 1.0) * 100 if len(sub_1) > 1 else 0.0
        ret_m = (sub_m.iloc[-1] / sub_m.iloc[0] - 1.0) * 100 if len(sub_m) > 1 else 0.0

        diff_str = f"vs纯历年 {ret_m - ret_h:+.1f}%, vs纯1年 {ret_m - ret_1:+.1f}%"
        print(f"{yr:<8} | {ret_h:>+16.2f}% | {ret_1:>+16.2f}% | {ret_m:>+16.2f}% | {diff_str}")
    print("=" * 90)

    # 3. 计算 2022-2026 地产下行新常态区间累计倍数
    nav_2022_start_h = eq_h.loc[eq_h.index >= "2022-01-01"].iloc[0]
    nav_2026_end_h = eq_h.iloc[-1]
    gain_2022_2026_h = nav_2026_end_h / nav_2022_start_h

    nav_2022_start_1 = eq_1.loc[eq_1.index >= "2022-01-01"].iloc[0]
    nav_2026_end_1 = eq_1.iloc[-1]
    gain_2022_2026_1 = nav_2026_end_1 / nav_2022_start_1

    nav_2022_start_m = eq_m.loc[eq_m.index >= "2022-01-01"].iloc[0]
    nav_2026_end_m = eq_m.iloc[-1]
    gain_2022_2026_m = nav_2026_end_m / nav_2022_start_m

    print("\n" + "=" * 90)
    print("【黑色新常态区间 (2022-01-01 至 2026-09-21) 净值倍数】")
    print("=" * 90)
    print(f"未融合·纯历年全景:   起点 {nav_2022_start_h/1e7:.4f} -> 终点 {nav_2026_end_h/1e7:.4f} (累计净值扩张 {gain_2022_2026_h:.2f} 倍)")
    print(f"未融合·纯近1年滚动:   起点 {nav_2022_start_1/1e7:.4f} -> 终点 {nav_2026_end_1/1e7:.4f} (累计净值扩张 {gain_2022_2026_1:.2f} 倍)")
    print(f"多尺度融合升级版:   起点 {nav_2022_start_m/1e7:.4f} -> 终点 {nav_2026_end_m/1e7:.4f} (累计净值扩张 {gain_2022_2026_m:.2f} 倍)")
    print("=" * 90)


if __name__ == "__main__":
    run_comparative_backtest()
