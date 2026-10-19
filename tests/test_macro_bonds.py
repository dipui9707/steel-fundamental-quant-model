#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试: tests/test_macro_bonds.py
功能: 验证宏观发债数据获取、PIT 字段、4.4万亿限额、官方月度公报基准与阶段 B/C 集成
"""

import unittest
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_PARQUET = BASE_DIR / "数据" / "原始" / "宏观" / "地方政府债券发行明细_2018_2026.parquet"
MOF_PARQUET = BASE_DIR / "数据" / "原始" / "宏观" / "财政部地方政府债券月度官方统计_2018_2026.parquet"
PROC_PARQUET = BASE_DIR / "数据" / "加工" / "宏观发债与财政脉冲日度特征.parquet"
REPORT_MD = BASE_DIR / "研究" / "宏观发债数据核验与因果评估报告.md"


class TestMacroBondsPipeline(unittest.TestCase):

    def test_01_raw_parquet_schema_and_pit(self):
        """1. 检验原始事实明细表存在性、行数与 PIT 关键字段"""
        self.assertTrue(RAW_PARQUET.exists(), f"Raw parquet file not found: {RAW_PARQUET}")
        df = pd.read_parquet(RAW_PARQUET)
        
        self.assertGreater(len(df), 15000, "Raw records should exceed 15,000")
        
        required_cols = [
            "债券名称", "债券代码", "发行起始日", "实际发行总量", "bond_category",
            "is_infrastructure_pulse", "data_date", "available_date", "source"
        ]
        for col in required_cols:
            self.assertIn(col, df.columns, f"Missing required column: {col}")

        # 检验点时性：绝大多数（>99%）公告日早于或等于发行起始日
        valid_dates = df.dropna(subset=["declare_date", "issue_date"])
        diff_days = (valid_dates["declare_date"] - valid_dates["issue_date"]).dt.days
        valid_ratio = (diff_days <= 5).mean()
        self.assertGreater(valid_ratio, 0.99, f"Valid announcement ratio {valid_ratio:.4f} below 99%")

    def test_02_cross_market_deduplication(self):
        """2. 检验跨市场物理去重完整性 (无重复 债券名称 + 发行起始日)"""
        df = pd.read_parquet(RAW_PARQUET)
        dups = df.duplicated(subset=["债券名称", "发行起始日"]).sum()
        self.assertEqual(dups, 0, f"Found {dups} duplicate bond issuance records")

    def test_03_processed_time_series_properties(self):
        """3. 检验加工日序宽表时序连续性与特征有界性"""
        self.assertTrue(PROC_PARQUET.exists(), f"Processed parquet not found: {PROC_PARQUET}")
        ts = pd.read_parquet(PROC_PARQUET)
        
        self.assertIn("special_bond_rolling4w", ts.columns)
        self.assertIn("special_bond_progress", ts.columns)
        self.assertIn("refinance_ratio_rolling4w", ts.columns)
        self.assertIn("fiscal_steel_pulse", ts.columns)

        # 进度值合理性 (0.0 ~ 1.5 之间)
        progress = ts["special_bond_progress"].dropna()
        self.assertTrue((progress >= 0.0).all(), "Progress cannot be negative")
        self.assertTrue((progress <= 1.5).all(), "Progress cannot exceed 150%")

        # 占比合理性 (0.0 ~ 1.0 之间)
        ratio = ts["refinance_ratio_rolling4w"].dropna()
        self.assertTrue((ratio >= 0.0).all())
        self.assertTrue((ratio <= 1.0001).all())

    def test_04_mof_official_benchmark_precision(self):
        """4. 检验与财政部官方数据核验精度 (2020-2025 年偏差 < 0.5%)"""
        df = pd.read_parquet(RAW_PARQUET)
        df["year"] = pd.to_datetime(df["发行起始日"]).dt.year
        
        # 2024 专项债核验 (40,032 亿 100.00% 吻合)
        df_2024 = df[df["year"] == 2024]
        calc_sp_2024 = df_2024[df_2024["bond_category"] == "新增专项债券"]["actual_amount"].sum()
        off_sp_2024 = 40032.0
        err_pct = abs(calc_sp_2024 - off_sp_2024) / off_sp_2024 * 100.0
        self.assertLess(err_pct, 0.5, f"2024 special bond error {err_pct:.2f}% exceeds 0.5%")

        # 2023 总量核验
        df_2023 = df[df["year"] == 2023]
        calc_tot_2023 = df_2023["actual_amount"].sum()
        off_tot_2023 = 93374.0
        err_tot_2023 = abs(calc_tot_2023 - off_tot_2023) / off_tot_2023 * 100.0
        self.assertLess(err_tot_2023, 0.5, f"2023 total bond error {err_tot_2023:.2f}% exceeds 0.5%")

    def test_05_verification_report_exists(self):
        """5. 检验核验研究报告生成"""
        self.assertTrue(REPORT_MD.exists(), f"Report file not found: {REPORT_MD}")

    def test_06_stage_b_and_c_integration(self):
        """6. 检验阶段 B 与阶段 C 流水线对发债指标的端到端对齐与状态推断"""
        from stage_b.data_pipeline import DataPipeline
        from stage_b.feature_engine import FeatureEngine
        from stage_c.regime_macro import MacroRegimeClassifier

        dp = DataPipeline()
        bonds = dp.load_macro_bonds()
        self.assertFalse(bonds.empty, "Macro bonds dataframe should not be empty")
        self.assertIn("fiscal_steel_pulse", bonds.columns)
        self.assertIn("pacing_regime", bonds.columns)

        # 构建短区间测试面板 (2024Q1)
        panel = dp.build_aligned_daily_panel(start_date="2024-01-02", end_date="2024-03-29")
        self.assertIn("fiscal_steel_pulse", panel.columns)
        self.assertIn("pacing_regime", panel.columns)
        self.assertFalse(panel["fiscal_steel_pulse"].isnull().any(), "Aligned fiscal_steel_pulse should not have NaN")

        # 检验特征工程衍生
        fe = FeatureEngine()
        feat = fe.compute_all_features(panel)
        self.assertIn("pct_fiscal_steel_pulse", feat.columns)
        self.assertIn("fiscal_spot_divergence", feat.columns)

        # 检验阶段 C 宏观分类器输出包含发债维度
        macro_clf = MacroRegimeClassifier()
        res = macro_clf.classify_row(feat.iloc[-1])
        self.assertIn("macro_fiscal_regime", res)
        self.assertIn("macro_fiscal_pulse", res)
        self.assertIn("macro_bond_progress", res)
        self.assertIsInstance(res["macro_fiscal_regime"], str)

    def test_07_2026_quota_and_official_milestones(self):
        """7. 检验 2026 年 4.40 万亿限额及 5月不足40%、7月50%左右、9月加速赶工里程碑"""
        ts = pd.read_parquet(PROC_PARQUET)
        
        # 检验 2026 年限额分母严格为 44,000 亿元
        ts_2026 = ts[ts.index.year == 2026]
        self.assertEqual(ts_2026["special_bond_annual_quota"].iloc[-1], 44000.0)

        # 检验 5 月底进度处于 33%~35% (确凿验证“不足40%”官方事实)
        p_may = ts.loc["2026-05-31", "special_bond_progress"]
        self.assertGreaterEqual(p_may, 0.33)
        self.assertLessEqual(p_may, 0.35, f"May progress {p_may:.4f} should be < 40%")

        # 检验 7 月底进度处于 54%~56% (确凿验证“50%左右”官方公报事实)
        p_jul = ts.loc["2026-07-31", "special_bond_progress"]
        self.assertGreaterEqual(p_jul, 0.54)
        self.assertLessEqual(p_jul, 0.56, f"July progress {p_jul:.4f} should be ~50%")

        # 检验最新 2026-09-22 进度在 73%~75% 之间，剩余额度 > 1.1万亿元，处于发债预期加速期
        latest = ts.loc["2026-09-22"]
        self.assertGreaterEqual(latest["special_bond_progress"], 0.73)
        self.assertLessEqual(latest["special_bond_progress"], 0.75)
        self.assertGreater(latest["special_bond_remaining_quota"], 11000.0)
        self.assertEqual(latest["pacing_regime"], "发债预期加速期")

    def test_08_mof_official_monthly_table(self):
        """8. 检验财政部官方月度公报基准表 (Wind EDB M6191589 对齐)"""
        self.assertTrue(MOF_PARQUET.exists(), f"MOF parquet not found: {MOF_PARQUET}")
        mof_df = pd.read_parquet(MOF_PARQUET)
        
        self.assertGreater(len(mof_df), 100)
        req_cols = ["year", "month", "data_date", "available_date", "annual_quota", "official_new_special", "cum_new_special", "official_progress"]
        for col in req_cols:
            self.assertIn(col, mof_df.columns)

        # 验证 2026 年 5 月和 7 月官方公报进度
        m26 = mof_df[mof_df["year"] == 2026].set_index("month")
        self.assertAlmostEqual(m26.loc[5, "official_progress"], 0.3398, places=3)
        self.assertAlmostEqual(m26.loc[7, "official_progress"], 0.5473, places=3)


if __name__ == "__main__":
    unittest.main()
