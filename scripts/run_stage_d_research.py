#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/run_stage_d_research.py
功能: 阶段 D 收益与交易研究 (Stage-D-0.1) 一键自动化调度流水线
职责:
  1. 加载阶段 B 连续特征宽表与阶段 C 全景状态矩阵;
  2. 调度 StageDResearchEngine 执行全套实证计算 (条件收益分布、持续期生存、MFE/MAE风险曲面、马尔可夫动力学、入场退出机制);
  3. 双格式落盘阶段 D 研究特征矩阵 (Parquet & CSV);
  4. 自动生成学术级全景实证研报 (.md);
  5. 自动渲染独立交互式 HTML 全景看板 (.html);
  6. 输出日终量化控制台摘要。
"""

import sys
import time
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_d.research_engine import StageDResearchEngine
from stage_d.dashboard import StageDDashboardGenerator


def run_stage_d_pipeline():
    start_time = time.time()
    print("=" * 80)
    print("🚀 启动【阶段 D 收益与交易研究系统 (Stage-D-0.1)】自动化实证流水线...")
    print("=" * 80)

    # 1. 加载阶段 B 与阶段 C 资产
    feature_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
    state_path = BASE_DIR / "数据" / "状态" / "阶段C_全景状态矩阵.parquet"

    if not feature_path.exists():
        raise FileNotFoundError(f"未找到输入宽表: {feature_path}，请先确保阶段 B 数据资产就绪。")
    if not state_path.exists():
        raise FileNotFoundError(f"未找到输入状态矩阵: {state_path}，请先确保阶段 C 状态矩阵已生成。")

    print(f"📖 正在加载阶段 B 特征宽表: {feature_path} ...")
    features_df = pd.read_parquet(feature_path)
    print(f"   ✓ 成功加载宽表: {len(features_df)} 交易日 × {len(features_df.columns)} 特征")

    print(f"📖 正在加载阶段 C 全景状态矩阵: {state_path} ...")
    state_matrix = pd.read_parquet(state_path)
    print(f"   ✓ 成功加载状态矩阵: {len(state_matrix)} 交易日 × {len(state_matrix.columns)} 状态维度")

    # 2. 调度 StageDResearchEngine
    print("\n🔬 调度 StageDResearchEngine 执行五大核心量化实证...")
    engine = StageDResearchEngine(features_df, state_matrix)
    results = engine.run_full_research_suite()

    # 3. 落盘特征矩阵数据资产
    print("\n💾 正在合成并落盘阶段 D 特征矩阵...")
    df_d, pq_path, csv_path = engine.build_and_save_research_matrix()
    print(f"   ✓ 阶段 D 数据资产已保存:")
    print(f"     - {pq_path} ({pq_path.stat().st_size / 1024:.1f} KB, {df_d.shape[0]} 行 × {df_d.shape[1]} 列)")
    print(f"     - {csv_path} ({csv_path.stat().st_size / 1024:.1f} KB)")

    # 4. 生成学术级全景研报
    print("\n📝 正在生成阶段 D 学术级实证研报...")
    report_path = engine.generate_full_research_report(results)
    print(f"   ✓ 研报生成成功: {report_path} ({report_path.stat().st_size / 1024:.1f} KB)")

    # 5. 生成交互式 HTML 看板
    print("\n🎨 正在渲染阶段 D 独立交互式 HTML 全景看板...")
    dash_gen = StageDDashboardGenerator(results)
    dash_path = dash_gen.generate_html_dashboard()
    print(f"   ✓ 交互看板生成成功: {dash_path} ({dash_path.stat().st_size / 1024:.1f} KB)")

    # 6. 控制台格式化核心指标报告
    elapsed = time.time() - start_time
    comp_ret = results["comp_ret"]
    comp_20d = comp_ret[comp_ret["horizon_days"] == 20].set_index("regime_name") if not comp_ret.empty else pd.DataFrame()

    print("\n" + "=" * 80)
    print(f"📋 【阶段 D 收益与交易研究】全流程执行完毕 (耗时: {elapsed:.2f}s)")
    print("=" * 80)
    print("【核心复合策略状态 20 交易日前瞻绩效全景】:")

    alpha_bull = comp_20d.loc["Alpha Bull (多头+高信任+现货确认)"] if "Alpha Bull (多头+高信任+现货确认)" in comp_20d.index else None
    alpha_bear = comp_20d.loc["Alpha Bear (空头+高信任+现货确认)"] if "Alpha Bear (空头+高信任+现货确认)" in comp_20d.index else None
    cost_floor = comp_20d.loc["Cost Floor Rebound (深度亏损成本下轨支撑)"] if "Cost Floor Rebound (深度亏损成本下轨支撑)" in comp_20d.index else None
    severe_div = comp_20d.loc["Severe Divergence (同尺度严重产业-价格背离)"] if "Severe Divergence (同尺度严重产业-价格背离)" in comp_20d.index else None

    if alpha_bull is not None:
        print(f"  • Alpha Bull (高确定性多头)     : 20d 均收益 {alpha_bull['mean_pct']:+.2f}% | 胜率 {alpha_bull['win_rate_pct']:.1f}% | 夏普 {alpha_bull['sharpe_ratio']:.2f} | 盈亏比 {alpha_bull['profit_loss_ratio']:.2f}")
    if alpha_bear is not None:
        print(f"  • Alpha Bear (高确定性空头)     : 20d 均收益 {alpha_bear['mean_pct']:+.2f}% | 胜率 {alpha_bear['win_rate_pct']:.1f}% | 夏普 {alpha_bear['sharpe_ratio']:.2f} | 盈亏比 {alpha_bear['profit_loss_ratio']:.2f}")
    if cost_floor is not None:
        print(f"  • Cost Floor Rebound (下轨筑底) : 20d 均收益 {cost_floor['mean_pct']:+.2f}% | 胜率 {cost_floor['win_rate_pct']:.1f}% | 夏普 {cost_floor['sharpe_ratio']:.2f} (强非对称反弹)")
    if severe_div is not None:
        print(f"  • Severe Divergence (严重背离)  : 20d 均收益 {severe_div['mean_pct']:+.2f}% | 胜率 {severe_div['win_rate_pct']:.1f}% | 偏度 {severe_div['skewness']:.2f}")

    print("-" * 80)
    entry_comp = results["entry_comparison_bull"]
    if not entry_comp.empty:
        print("【入场确认机制比较 (多头 20d)】:")
        for _, row in entry_comp.iterrows():
            print(f"  - {row['entry_mode']:<32}: 均收益 {row['mean_return_pct']:+.2f}% | 胜率 {row['win_rate_pct']:.1f}% | 弹性比 {row['elasticity_ratio']:.2f} | 夏普 {row['sharpe_ratio']:.2f}")

    print("-" * 80)
    exit_comp = results["exit_comparison_bull"]
    if not exit_comp.empty:
        print("【平仓退出规则比较 (最大 30d)】:")
        for _, row in exit_comp.iterrows():
            print(f"  - {row['exit_rule']:<32}: 平均 PnL {row['mean_pnl_pct']:+.2f}% | 持仓 {row['mean_holding_days']:.1f}天 | 胜率 {row['win_rate_pct']:.1f}% | 年化 {row['annualized_pnl_pct']:+.1f}%")

    print("=" * 80)


if __name__ == "__main__":
    run_stage_d_pipeline()
