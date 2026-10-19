#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试: tests/test_stage_b_engine.py
功能: 阶段 B 模型系统高严密自动化单元测试
验证范围:
  1. PIT 契约与时间单向性 (无前向信息泄漏);
  2. 数学恒等式检验: D_t + W_t == ΔFBS_t, 权重归一化 sum(w) == 1, 评分有界 [-100, 100];
  3. 特征有界性与合理性: S_supply/demand/inv in [-1, 1], Entropy in [0, 1];
  4. 离散状态分类完备性与分类字典一致性 (严格符合 A05 规范);
  5. 单因子评估逻辑与分位数单调性计算正确性。
"""

import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_b.data_pipeline import DataPipeline
from stage_b.feature_engine import FeatureEngine
from stage_b.state_classifier import StateClassifier
from stage_b.factor_research import FactorResearcher


class TestStageBEngine(unittest.TestCase):
    """阶段 B 核心引擎测试用例"""

    @classmethod
    def setUpClass(cls):
        # 截取 2024 年上半年样本做高效率端到端校验 (含 2024Q1 案例)
        cls.dp = DataPipeline()
        cls.panel = cls.dp.build_aligned_daily_panel(start_date="2024-01-02", end_date="2024-06-30")
        cls.fe = FeatureEngine()
        cls.features = cls.fe.compute_all_features(cls.panel)
        cls.sc = StateClassifier()
        cls.states = cls.sc.classify_all_states(cls.features)
        cls.fr = FactorResearcher(forward_horizons=[5, 10])

    def test_pit_alignment_and_monotonicity(self):
        """1. 检验 PIT 时间对齐与索引单调性"""
        self.assertFalse(self.panel.empty, "Aligned panel should not be empty")
        self.assertTrue(self.panel.index.is_monotonic_increasing, "Trade dates must be strictly monotonic increasing")
        
        # 检验核心事实字段非空存在
        for col in ["rb_close", "hot_metal_247", "spot_hz_tier3", "cost_east_bf", "data_age"]:
            self.assertIn(col, self.panel.columns, f"Missing key column: {col}")
            self.assertFalse(self.panel[col].isnull().all(), f"Column {col} is all null")

    def test_mathematical_identities_and_bounds(self):
        """2. 检验 A05.1 数学恒等式与评分有界性"""
        # A. 评分有界性: [-100, 100]
        fbs = self.features["fbs_score"]
        self.assertTrue((fbs >= -100.0).all() and (fbs <= 100.0).all(), "FBS score out of bounds [-100, 100]")

        # B. 动态权重非负且归一: sum(w) == 1
        w_sum = self.features["w_supply"] + self.features["w_demand"] + self.features["w_inventory"]
        np.testing.assert_allclose(w_sum.values, 1.0, atol=1e-4, err_msg="Dynamic weights must sum to 1.0")

        # C. 模块得分有界性: S_j in [-1, 1]
        for mod in ["score_supply", "score_demand", "score_inventory"]:
            s = self.features[mod]
            self.assertTrue((s >= -1.0).all() and (s <= 1.0).all(), f"Module score {mod} out of bounds [-1, 1]")

        # D. 精确恒等分解: D_t + W_t == ΔFBS_t (从第2个点开始)
        d = self.features["d_contrib"].iloc[1:]
        w = self.features["w_contrib"].iloc[1:]
        delta_fbs = self.features["fbs_score"].diff().iloc[1:]
        dw_sum = d + w
        # 允许微小数值浮点与舍入容差
        np.testing.assert_allclose(dw_sum.values, delta_fbs.values, atol=0.05, err_msg="D_t + W_t must equal ΔFBS_t")

        # E. 证据熵有界性: in [0, 1]
        entropy = self.features["evidence_entropy"]
        self.assertTrue((entropy >= 0.0).all() and (entropy <= 1.0).all(), "Evidence entropy out of bounds [0, 1]")

        # F. 数据新鲜度有界性: in [0, 1]
        freshness = self.features["data_freshness_ratio"]
        self.assertTrue((freshness >= 0.0).all() and (freshness <= 1.0).all(), "Freshness ratio out of bounds [0, 1]")

    def test_state_taxonomy_completeness(self):
        """3. 检验离散状态分类完备性与契约合规 (A05)"""
        # A. 行数一致性
        self.assertEqual(len(self.states), len(self.features), "States row count must match features")

        # B. 离散取值合规校验
        allowed_macro = {"产业主导", "宏观覆盖", "混合", "Unknown"}
        allowed_fund_dir = {"Bullish", "Bearish", "Neutral", "Unknown"}
        allowed_fund_str = {"High", "Medium", "Low", "Unknown"}
        allowed_spot = {"Confirmed", "Mixed", "Rejected", "Unknown"}
        allowed_div = {"None", "产业价格背离", "产业现货背离", "多重背离", "Unknown"}
        allowed_conf = {"High", "Medium", "Low", "Unknown"}
        allowed_struct = {"Bull Trend", "Bear Trend", "Range", "Unknown"}

        self.assertTrue(set(self.states["macro_regime"].unique()).issubset(allowed_macro))
        self.assertTrue(set(self.states["fundamental_direction"].unique()).issubset(allowed_fund_dir))
        self.assertTrue(set(self.states["fundamental_strength"].unique()).issubset(allowed_fund_str))
        self.assertTrue(set(self.states["spot_confirmation"].unique()).issubset(allowed_spot))
        self.assertTrue(set(self.states["divergence_state"].unique()).issubset(allowed_div))
        self.assertTrue(set(self.states["model_confidence"].unique()).issubset(allowed_conf))
        self.assertTrue(set(self.states["market_structure"].unique()).issubset(allowed_struct))

    def test_factor_research_computation(self):
        """4. 检验单因子有效性评估算法"""
        fwd_df = self.fr.prepare_forward_returns(self.features)
        self.assertIn("fwd_ret_5d", fwd_df.columns)
        self.assertIn("fwd_ret_10d", fwd_df.columns)

        # 检验 IC 计算
        ic_df = self.fr.evaluate_factor_ic(fwd_df, ["fbs_score", "basis_tier3"])
        self.assertFalse(ic_df.empty, "IC dataframe should not be empty")
        for rank_ic in ic_df["rank_ic"]:
            self.assertTrue(-1.0 <= rank_ic <= 1.0, "Rank IC must be within [-1, 1]")

        # 检验五分位数计算
        q_df, mono = self.fr.evaluate_quantiles(fwd_df, "fbs_score", horizon=10, n_quantiles=3)
        self.assertFalse(q_df.empty, "Quantile dataframe should not be empty")
        self.assertTrue(-1.0 <= mono <= 1.0, "Monotonicity score must be within [-1, 1]")

    def test_micro_features_and_decay_analytics(self):
        """5. 检验新增微观产业特征与 IC 衰减曲线算法"""
        # 检验微观指标列存在且非空
        micro_cols = [
            "iron_scrap_spread", "hz_stock_to_sales", "eaf_valley_buffer",
            "north_south_spread", "billet_rebar_spread", "hc_virtual_margin",
            "roll_yield_annual"
        ]
        for col in micro_cols:
            self.assertIn(col, self.features.columns, f"Missing micro feature: {col}")
            self.assertFalse(self.features[col].isnull().all(), f"Micro feature {col} is all null")

        # 检验 IC 衰减曲线
        decay_df = self.fr.evaluate_factor_decay_curve(self.features, "fbs_score", [1, 3, 5, 10])
        self.assertFalse(decay_df.empty, "Decay curve dataframe should not be empty")
        for ic in decay_df["rank_ic"]:
            self.assertTrue(-1.0 <= ic <= 1.0, "Decay Rank IC must be in [-1, 1]")

    def test_state_transitions_and_mae_mfe(self):
        """6. 检验一阶状态转移矩阵与 MAE/MFE 风险弹性度量"""
        trans_df, durations = self.fr.evaluate_state_transitions(self.states, "market_structure")
        self.assertFalse(trans_df.empty, "Transition matrix should not be empty")
        # 验证行和为 1
        np.testing.assert_allclose(trans_df.sum(axis=1).values, 1.0, atol=1e-4, err_msg="Transition probabilities row sum must be 1.0")

        # 检验 MAE/MFE 风险弹性计算
        mae_mfe_df = self.fr.evaluate_state_mae_mfe(self.features, self.states, "fundamental_direction", horizon=10)
        self.assertFalse(mae_mfe_df.empty, "MAE/MFE dataframe should not be empty")
        self.assertIn("avg_mfe_10d_pct", mae_mfe_df.columns)
        self.assertIn("avg_mae_10d_pct", mae_mfe_df.columns)

    def test_hypothesis_verifier(self):
        """7. 检验 A09 假设库自动化核验引擎"""
        from stage_b.hypothesis_verifier import HypothesisVerifier
        hv = HypothesisVerifier(self.features, self.states)
        results = hv.verify_all_hypotheses()
        self.assertIn("ARCH-H-001", results)
        self.assertIn("ARCH-H-003", results)
        self.assertIn("ARCH-H-010", results)
        self.assertIn("ARCH-H-014", results)
        self.assertIn("ARCH-H-017", results)
        self.assertIn("ARCH-H-018", results)
        for hid, r in results.items():
            self.assertIn(r["status"], ["历史验证通过", "历史验证未通过"])


    def test_historical_percentiles_and_pit_causality(self):
        """8. 检验历史自适应分位数指标有界性与无未来函数因果性"""
        pct_cols = [c for c in self.features.columns if c.startswith("pct_")]
        self.assertGreaterEqual(len(pct_cols), 15, "Should compute at least 15 percentile features")

        # A. 有界性检验: 严格属于 [0.0, 1.0]
        for col in pct_cols:
            s = self.features[col]
            self.assertTrue((s >= 0.0).all() and (s <= 1.0).all(), f"Percentile {col} out of bounds [0.0, 1.0]")
            self.assertFalse(s.isnull().any(), f"Percentile {col} contains unexpected nulls")

        # B. 严格因果性检验 (PIT Causality): 未来的数据修改绝不影响过去的百分位数值
        synthetic_df = pd.DataFrame({
            "virtual_mill_margin": [10.0, 20.0, 30.0, 40.0, 50.0, 60.0] * 10
        })
        pct_res_orig = self.fe.compute_historical_percentiles(synthetic_df, min_periods=5)
        val_at_t20 = pct_res_orig["pct_virtual_mill_margin"].iloc[20]

        # 剧烈修改未来的值 (如第 50 项由 60 改为 999999)
        synthetic_df_mod = synthetic_df.copy()
        synthetic_df_mod.iloc[50, 0] = 999999.0
        pct_res_mod = self.fe.compute_historical_percentiles(synthetic_df_mod, min_periods=5)
        val_at_t20_mod = pct_res_mod["pct_virtual_mill_margin"].iloc[20]

        # 过去点位分位数必须完全一致
        self.assertEqual(val_at_t20, val_at_t20_mod, "Future data must not affect past historical percentile (PIT violation)!")

    def test_seasonality_and_pit_causality(self):
        """9. 检验双日历季节性对齐、特征有界性与严格 PIT 无未来泄露因果性"""
        from stage_b.seasonality import compute_pit_seasonal_metrics, get_seasonal_tags

        # A. 字段存在性检验
        seasonal_cols = [
            "cny_relative_week", "calendar_week", "season_code", "is_cny_window",
            "inv_diff1_seasonal_zscore", "inv_diff1_seasonal_rank",
            "inv_level_seasonal_rank", "demand_seasonal_zscore", "demand_seasonal_rank",
            "rb_prod_seasonal_zscore", "rb_prod_seasonal_rank",
            "hm_seasonal_zscore", "hm_seasonal_rank"
        ]
        for col in seasonal_cols:
            self.assertIn(col, self.features.columns, f"Missing seasonal feature column: {col}")

        # B. 有界性检验: z-score in [-3.0, 3.0], rank in [0.0, 1.0]
        z_cols = [c for c in seasonal_cols if c.endswith("_zscore")]
        rk_cols = [c for c in seasonal_cols if c.endswith("_rank")]
        for z_col in z_cols:
            s = self.features[z_col]
            self.assertTrue((s >= -3.0).all() and (s <= 3.0).all(), f"Z-score {z_col} out of bounds [-3.0, 3.0]")
        for rk_col in rk_cols:
            s = self.features[rk_col]
            self.assertTrue((s >= 0.0).all() and (s <= 1.0).all(), f"Rank {rk_col} out of bounds [0.0, 1.0]")

        # C. 严格 PIT 无未来泄露检验
        # 构造 2021-2024 年合成日历时序 (每日一个点)
        dates = pd.date_range("2021-01-01", "2024-12-31", freq="D")
        np.random.seed(42)
        syn_df = pd.DataFrame({"inv_diff1": np.random.randn(len(dates)) * 20.0}, index=dates)

        z_orig, rk_orig = compute_pit_seasonal_metrics(syn_df, "inv_diff1")
        # 截取 2023 年第 800 天的数值
        val_t800_z = z_orig.iloc[800]
        val_t800_rk = rk_orig.iloc[800]

        # 剧烈修改 2024 年末的数值 (例如第 1200 天篡改为 888888.0)
        syn_df_mod = syn_df.copy()
        syn_df_mod.iloc[1200, 0] = 888888.0
        z_mod, rk_mod = compute_pit_seasonal_metrics(syn_df_mod, "inv_diff1")
        val_t800_z_mod = z_mod.iloc[800]
        val_t800_rk_mod = rk_mod.iloc[800]

        # 过去截面的季节性统计必须完全一致
        self.assertEqual(val_t800_z, val_t800_z_mod, "Future data modification leaked into past seasonal z-score!")
        self.assertEqual(val_t800_rk, val_t800_rk_mod, "Future data modification leaked into past seasonal rank!")

    def test_cross_commodity_shock_and_leader(self):
        """10. 检验黑色五品种异动源头捕获、领头羊识别与逼仓压力指数"""
        # A. 字段存在性检验 (18 维特征)
        shock_cols = [
            "rb_vol_shock_ratio", "hc_vol_shock_ratio", "i_vol_shock_ratio", "j_vol_shock_ratio", "jm_vol_shock_ratio",
            "rb_squeeze_index", "hc_squeeze_index", "i_squeeze_index", "j_squeeze_index", "jm_squeeze_index",
            "rb_jm_rolling_corr_10d", "rb_j_rolling_corr_10d", "rb_i_rolling_corr_10d", "rb_hc_rolling_corr_10d",
            "cost_push_spread_5d", "dominant_leader_sym", "dominant_leader_type", "is_raw_material_squeeze"
        ]
        for col in shock_cols:
            self.assertIn(col, self.features.columns, f"Missing shock feature column: {col}")

        # B. 波动率异动比有界性 [0.1, 8.0]
        for sym in ["rb", "hc", "i", "j", "jm"]:
            vs = self.features[f"{sym}_vol_shock_ratio"]
            self.assertTrue((vs >= 0.1).all() and (vs <= 8.0).all(), f"Vol shock ratio {sym} out of bounds")

        # C. 逼仓压力指数有界性 [-6.0, 6.0]
        for sym in ["rb", "hc", "i", "j", "jm"]:
            sq = self.features[f"{sym}_squeeze_index"]
            self.assertTrue((sq >= -6.0).all() and (sq <= 6.0).all(), f"Squeeze index {sym} out of bounds")

        # D. 滚动相关性有界性 [-1.0, 1.0]
        for sym in ["jm", "j", "i", "hc"]:
            corr = self.features[f"rb_{sym}_rolling_corr_10d"]
            self.assertTrue((corr >= -1.0).all() and (corr <= 1.0).all(), f"Rolling corr rb_{sym} out of bounds")

        # E. 领头羊符号属于五大品种
        valid_leaders = {"RB", "HC", "I", "J", "JM"}
        self.assertTrue(set(self.features["dominant_leader_sym"].unique()).issubset(valid_leaders))

        valid_types = {"RAW_MATERIAL_SHOCK", "FINISHED_STEEL_DEMAND", "RAW_MATERIAL_DRAG", "FINISHED_STEEL_WEAK", "BALANCED_ROTATION"}
        self.assertTrue(set(self.features["dominant_leader_type"].unique()).issubset(valid_types))

        # F. 严格 PIT 无未来泄露检验
        from stage_b.cross_commodity_shock import CrossCommodityShockDetector
        detector = CrossCommodityShockDetector()
        syn_df = pd.DataFrame({
            "rb_close": [3500 + i * 5 for i in range(100)],
            "hc_close": [3600 + i * 5 for i in range(100)],
            "i_close": [800 + i * 2 for i in range(100)],
            "j_close": [2200 + i * 3 for i in range(100)],
            "jm_close": [1600 + i * 4 for i in range(100)],
            "rb_oi": [1000000 + i * 1000 for i in range(100)],
            "hc_oi": [800000 + i * 800 for i in range(100)],
            "i_oi": [600000 + i * 600 for i in range(100)],
            "j_oi": [200000 + i * 200 for i in range(100)],
            "jm_oi": [300000 + i * 300 for i in range(100)],
        })
        res_orig = detector.compute_all_shock_features(syn_df)
        val_t50_sq = res_orig["jm_squeeze_index"].iloc[50]
        val_t50_lead = res_orig["dominant_leader_sym"].iloc[50]

        # 剧烈修改未来 (第 90 天)
        syn_df_mod = syn_df.copy()
        syn_df_mod.iloc[90, 4] = 999999.0  # jm_close
        syn_df_mod.iloc[90, 9] = 88888888.0 # jm_oi
        res_mod = detector.compute_all_shock_features(syn_df_mod)
        val_t50_sq_mod = res_mod["jm_squeeze_index"].iloc[50]
        val_t50_lead_mod = res_mod["dominant_leader_sym"].iloc[50]

        self.assertEqual(val_t50_sq, val_t50_sq_mod, "Future data modification leaked into past squeeze index!")
        self.assertEqual(val_t50_lead, val_t50_lead_mod, "Future data modification leaked into past dominant leader!")


if __name__ == "__main__":
    unittest.main()


