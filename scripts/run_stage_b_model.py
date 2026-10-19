#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/run_stage_b_model.py
功能: 阶段 B 产业基本面量化模型统一运行调度入口
执行内容:
  1. 严格 PIT 对齐 2018-2026 全量期货、微观现货与 Wind EDB 产业主库数据;
  2. 运行 FeatureEngine 全量计算状态特征宽表 (FBS、动态分解、基差、估值、微观打标、背离度量、证据熵);
  3. 运行 StateClassifier 全量推断每日离散市场状态时序 (A05 八大状态维度);
  4. 持久化落盘特征宽表与状态时序 (Parquet & CSV);
  5. 运行 FactorResearcher 执行单变量 Rank IC / ICIR 与状态前瞻收益分布检验，生成研究报告。
"""

import sys
import argparse
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_b.model import StageBModel


def main():
    parser = argparse.ArgumentParser(description="运行钢材产业量化系统 - 阶段 B 模型流水线")
    parser.add_argument("--start", type=str, default="2018-03-09", help="起始交易日期 (默认: 2018-03-09)")
    parser.add_argument("--end", type=str, default=None, help="截止交易日期 (默认: 最新)")
    parser.add_argument("--skip-research", action="store_true", help="跳过单因子有效性研究")
    args = parser.parse_args()

    print("=" * 80)
    print("【钢材产业基本面量化系统】 阶段 B：数据与低代码研究模型启动")
    print(f"数据区间: {args.start} ~ {args.end or '最新'}")
    print("=" * 80)

    model = StageBModel()

    # 1. 运行流水线
    features_df, states_df = model.run_pipeline(start_date=args.start, end_date=args.end)

    # 2. 持久化落盘
    print("\n[*] 正在将阶段 B 核心数据资产落盘...")
    model.save_outputs()

    # 3. 单因子与状态收益分布研究
    if not args.skip_research:
        print("\n[*] 正在启动阶段 B 单因子有效性与状态收益分布量化评估...")
        ic_df, q_df, state_df = model.run_factor_research()
        print(f"    -> 单因子 IC 评估项: {len(ic_df)} 条")
        print(f"    -> 离散状态收益分布样本数: {len(state_df)} 项")

    print("\n" + "=" * 80)
    print("✅ 阶段 B 模型全流程执行完毕！")
    print("   1. 特征宽表: 数据/加工/阶段B_特征宽表.parquet & csv")
    print("   2. 状态时序: 数据/状态/阶段B_全景状态时间序列.parquet & csv")
    print("   3. 因子研报: 研究/阶段B_单变量与状态研究/阶段B_单因子预测能力研究报告.md")
    print("   4. 状态研报: 研究/阶段B_单变量与状态研究/阶段B_全历史市场状态全景报告.md")
    print("=" * 80)


if __name__ == "__main__":
    main()
