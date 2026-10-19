#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/run_stage_c_model.py
功能: 阶段 C 状态模型系统一键自动化调度流水线
职责:
  1. 加载阶段 B 连续特征宽表资产 (数据/加工/阶段B_特征宽表.parquet);
  2. 调度 StageCStateEngine 推断全景状态矩阵 (六大子状态系统);
  3. 双格式落盘状态矩阵资产 (数据/状态/阶段C_全景状态矩阵.parquet & .csv);
  4. 调度 StateEvaluator 开展状态条件收益检验与背离消解实证，输出研报;
  5. 调度 StageCDashboardGenerator 生成独立交互式 HTML 全景看板;
  6. 输出格式化日终控制台摘要报告。
"""

import sys
import time
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_c.state_engine import StageCStateEngine
from stage_c.state_evaluator import StateEvaluator
from stage_c.dashboard import StageCDashboardGenerator


def run_stage_c_pipeline():
    start_time = time.time()
    print("=" * 80)
    print("🚀 启动【阶段 C 状态模型系统 (Stage-C-0.1)】端到端自动化推断流水线...")
    print("=" * 80)

    # 1. 加载阶段 B 特征宽表
    feature_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
    if not feature_path.exists():
        raise FileNotFoundError(f"未找到输入特征宽表: {feature_path}，请先确保阶段 B 特征宽表已生成。")

    print(f"📖 正在加载特征宽表: {feature_path} ...")
    features_df = pd.read_parquet(feature_path)
    print(f"   ✓ 成功加载宽表: {len(features_df)} 交易日 × {len(features_df.columns)} 特征")
    print(f"   ✓ 历史区间: {features_df.index[0]} 至 {features_df.index[-1]}")

    # 2. 调度 StateEngine 推断全景状态矩阵
    print("\n🧠 正在调度 StageCStateEngine 推断六大子状态系统...")
    engine = StageCStateEngine()
    state_matrix = engine.synthesize_states(features_df)
    print(f"   ✓ 状态矩阵推断完成: {len(state_matrix)} 行 × {len(state_matrix.columns)} 维状态属性")

    # 3. 落盘状态矩阵
    pq_path, csv_path = engine.save_state_matrix(state_matrix)
    print(f"   💾 状态矩阵已落盘至:")
    print(f"      - {pq_path} ({pq_path.stat().st_size / 1024:.1f} KB)")
    print(f"      - {csv_path} ({csv_path.stat().st_size / 1024:.1f} KB)")

    # 4. 调度 StateEvaluator 开展实证评估
    print("\n📊 正在调度 StateEvaluator 计算状态条件收益分布与实证指标...")
    evaluator = StateEvaluator(features_df, state_matrix)
    comp_eval = evaluator.evaluate_composite_strategy_regimes()
    div_res = evaluator.evaluate_divergence_resolution()
    report_path = evaluator.generate_full_research_report()
    print(f"   ✓ 实证研报生成成功: {report_path}")

    # 5. 调度 DashboardGenerator 生成全景看板
    print("\n🎨 正在调度 StageCDashboardGenerator 渲染自包含 HTML 交互看板...")
    dashboard_gen = StageCDashboardGenerator(features_df, state_matrix, comp_eval, div_res)
    dashboard_path = dashboard_gen.generate_html_dashboard()
    print(f"   ✓ 交互看板生成成功: {dashboard_path} ({dashboard_path.stat().st_size / 1024:.1f} KB)")

    # 6. 控制台格式化输出最新状态快照
    elapsed = time.time() - start_time
    latest_dt = str(state_matrix.index[-1])[:10]
    row = state_matrix.iloc[-1]

    print("\n" + "=" * 80)
    print(f"📋 【阶段 C 状态模型系统】推断完成 (耗时: {elapsed:.2f}s)")
    print("=" * 80)
    print(f"【最新交易日市场状态全景快照】: {latest_dt}")
    print(f"  1. 宏观环境 (Macro Regime)       : {row['macro_regime']} (覆盖强度: {row['macro_override_intensity']:.2f}, 偏向: {row['macro_policy_bias']})")
    print(f"  2. 基本面供需 (Fundamental State) : {row['fundamental_direction']} ({row['fundamental_strength']}) | 成本: {row['cost_boundary_regime']} | 原料: {row['raw_feedback_regime']}")
    print(f"  3. 现货确认 (Spot Confirmation)  : {row['spot_confirmation']} | 基差: {row['basis_regime']} | 流动性: {row['spot_inventory_liquidity']}")
    print(f"  4. 市场情绪 (Sentiment State)    : {row['sentiment_state']} | 拥挤度: {row['crowding_risk']} | 共振: {row['cross_commodity_resonance']}")
    print(f"  5. 价格结构 (Market Structure)   : {row['market_structure']} | 波动率: {row['volatility_regime']} | 背离: {row['divergence_state']} ({row['divergence_severity']})")
    print(f"  6. 模型信任 (Model Confidence)   : {row['model_confidence']} ({row['confidence_score']:.1f}分) | 降级: {row['fallback_regime']} | 生命周期: {row['lifecycle']}")
    print("-" * 80)
    print(f"【背离消解实证】: 价格向基本面均值回归率: {div_res.get('price_reversion_rate_pct', 0)}% (基准牵引长期有效)")
    print("=" * 80)


if __name__ == "__main__":
    run_stage_c_pipeline()
