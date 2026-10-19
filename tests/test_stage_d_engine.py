#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试套件: tests/test_stage_d_engine.py
功能: 阶段 D 收益与交易研究 (Stage-D-0.1) 自动化单元与架构契约测试
覆盖:
  1. 特征矩阵数据资产完整性与 PIT 索引对齐检验;
  2. 条件收益分布高阶矩 (偏度/峰度/分位/胜率) 数学严密性检验;
  3. 游程切分与 Kaplan-Meier 生存函数单调非增性检验;
  4. MFE / MAE 极端路径数学有界性检验 (MFE >= 0, MAE <= 0, 止损单调性);
  5. 马尔可夫转移矩阵严格行归一化 (sum_j P_ij = 1) 与稳态平衡检验;
  6. 入场与退出机制模拟无未来函数与持仓周期有界性检验;
  7. State != Position 架构红线检验。
"""

import unittest
from pathlib import Path
import pandas as pd
import numpy as np

from stage_d.return_distribution import ReturnDistributionEngine
from stage_d.duration_survival import DurationSurvivalEngine
from stage_d.mfe_mae_profile import MfeMaeProfileEngine
from stage_d.transition_matrix import TransitionMatrixEngine
from stage_d.entry_exit_research import EntryExitResearchEngine

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = BASE_DIR / "数据" / "状态"
FEATURE_DIR = BASE_DIR / "数据" / "加工"


class TestStageDEngine(unittest.TestCase):
    """
    阶段 D 核心量化引擎单元与架构测试
    """

    @classmethod
    def setUpClass(cls):
        # 加载全历史特征宽表与状态矩阵
        feat_path = FEATURE_DIR / "阶段B_特征宽表.parquet"
        state_path = STATE_DIR / "阶段C_全景状态矩阵.parquet"

        assert feat_path.exists(), f"未找到阶段 B 宽表: {feat_path}"
        assert state_path.exists(), f"未找到阶段 C 状态矩阵: {state_path}"

        cls.features_df = pd.read_parquet(feat_path)
        cls.state_matrix = pd.read_parquet(state_path)

        # 实例化五大子引擎
        cls.ret_engine = ReturnDistributionEngine(cls.features_df, cls.state_matrix)
        cls.dur_engine = DurationSurvivalEngine(cls.state_matrix)
        cls.mfe_engine = MfeMaeProfileEngine(cls.features_df, cls.state_matrix)
        cls.trans_engine = TransitionMatrixEngine(cls.state_matrix)
        cls.entry_exit_engine = EntryExitResearchEngine(cls.features_df, cls.state_matrix)

    # --------------------------------------------------------------------------
    # 1. 数据资产与特征矩阵测试
    # --------------------------------------------------------------------------
    def test_01_matrix_asset_integrity(self):
        """验证阶段 D 落盘数据资产的完整性、维度与索引单调性"""
        pq_path = STATE_DIR / "阶段D_收益与交易研究特征矩阵.parquet"
        csv_path = STATE_DIR / "阶段D_收益与交易研究特征矩阵.csv"

        self.assertTrue(pq_path.exists(), "阶段 D 特征矩阵 Parquet 文件必须存在")
        self.assertTrue(csv_path.exists(), "阶段 D 特征矩阵 CSV 文件必须存在")

        df_d = pd.read_parquet(pq_path)
        self.assertGreaterEqual(len(df_d), 2074, "样本总行数必须在 2074 交易日以上")
        self.assertGreaterEqual(len(df_d.columns), 80, "特征矩阵列数必须在 80 列以上")
        self.assertTrue(df_d.index.is_monotonic_increasing, "时间序列索引必须严格单调递增")

        # 检查核心派生标签列
        expected_cols = [
            "fwd_ret_rb_5d", "fwd_ret_rb_20d", "mfe_long_20d", "mae_long_20d",
            "mfe_short_20d", "mae_short_20d", "ma5", "ma20", "atr14"
        ]
        for col in expected_cols:
            self.assertIn(col, df_d.columns, f"特征矩阵必须包含关键列: {col}")

    # --------------------------------------------------------------------------
    # 2. 条件收益分布引擎测试
    # --------------------------------------------------------------------------
    def test_02_distribution_stats_math(self):
        """测试分布统计量函数 (均值、中位数、偏度、峰度、分位数) 的数学严密性"""
        # 构造已知对称分布
        symmetric_series = pd.Series([-0.05, -0.02, 0.0, 0.02, 0.05])
        stats = self.ret_engine.calculate_distribution_stats(symmetric_series, horizon=20)

        self.assertEqual(stats["sample_count"], 5)
        self.assertAlmostEqual(stats["mean_pct"], 0.0, delta=0.01)
        self.assertAlmostEqual(stats["median_pct"], 0.0, delta=0.01)
        self.assertAlmostEqual(stats["skewness"], 0.0, delta=0.05)  # 对称分布偏度接近 0
        self.assertEqual(stats["win_rate_pct"], 40.0)  # 2 / 5 > 0

        # 测试右偏 (长右尾) 分布
        right_skewed = pd.Series([0.01, 0.01, 0.02, 0.02, 0.15])
        stats_skew = self.ret_engine.calculate_distribution_stats(right_skewed, horizon=20)
        self.assertGreater(stats_skew["skewness"], 0.5, "长右尾分布的偏度必须显著大于 0")

    def test_03_forward_return_no_lookahead(self):
        """验证前瞻收益 shift(-h) 的末端保留 NaN，未发生向过去泄露"""
        h = 20
        col = f"fwd_ret_rb_{h}d"
        tail_vals = self.ret_engine.state_matrix[col].iloc[-h:]
        self.assertTrue(tail_vals.isna().all(), f"最后 {h} 个交易日的前瞻收益必须全部为 NaN，杜绝未来函数泄露")

    def test_04_composite_regimes_separation(self):
        """验证核心复合状态的区分度与合理性 (多头期望收益显著高于空头)"""
        comp_df = self.ret_engine.evaluate_composite_regimes(horizons=[20])
        self.assertFalse(comp_df.empty, "复合状态收益评估表不得为空")

        alpha_bull = comp_df[comp_df["regime_name"].str.contains("Alpha Bull")].iloc[0]
        alpha_bear = comp_df[comp_df["regime_name"].str.contains("Alpha Bear")].iloc[0]

        # 核心断言: 多头期望收益必须高于空头期望收益
        self.assertGreater(alpha_bull["mean_pct"], alpha_bear["mean_pct"], "Alpha Bull 收益率必须显著高于 Alpha Bear")
        self.assertGreater(alpha_bull["win_rate_pct"], alpha_bear["win_rate_pct"], "Alpha Bull 胜率必须高于 Alpha Bear")

    # --------------------------------------------------------------------------
    # 3. 持续期与生存分析引擎测试
    # --------------------------------------------------------------------------
    def test_05_episode_extraction_conservation(self):
        """验证游程切分的封闭守恒性: 各连续游程天数之和必须严格等于原时序长度"""
        s = self.state_matrix["fundamental_direction"]
        episodes_df = self.dur_engine.extract_episodes(s)

        self.assertFalse(episodes_df.empty, "游程切分结果不得为空")
        self.assertEqual(episodes_df["duration_days"].sum(), len(s), "游程持续天数之和必须等于原序列总长度")
        # 检验仅有最后一个游程可能被标记为截断
        non_tail_censored = episodes_df.iloc[:-1]["censored"]
        self.assertFalse(non_tail_censored.any(), "非末尾游程不得被标记为截断")

    def test_06_kaplan_meier_monotonicity(self):
        """验证 Kaplan-Meier 生存函数单调非增性 S(t) <= S(t-1) 与风险率有界性"""
        km_df = self.dur_engine.compute_kaplan_meier_survival("market_structure", "Bull Trend", max_t=30)
        self.assertFalse(km_df.empty, "生存分析结果不得为空")

        surv_probs = km_df["survival_prob"].values
        # 验证单调非增
        diffs = np.diff(surv_probs)
        self.assertTrue((diffs <= 1e-6).all(), "生存概率 S(t) 随时间必须单调非增")

        # 验证概率在 [0, 1] 区间
        self.assertTrue((surv_probs >= 0.0).all() and (surv_probs <= 1.0).all(), "生存概率必须在 [0, 1] 闭区间内")

        # 验证风险率在 [0, 1] 区间
        hazards = km_df["hazard_rate"].values
        self.assertTrue((hazards >= 0.0).all() and (hazards <= 1.0).all(), "风险率必须在 [0, 1] 闭区间内")

    # --------------------------------------------------------------------------
    # 4. MFE / MAE 极端路径与止损曲面测试
    # --------------------------------------------------------------------------
    def test_07_mfe_mae_boundedness(self):
        """验证 MFE 与 MAE 的严格符号与极值约束 (MFE >= 0, MAE <= 0)"""
        mfe_long = self.mfe_engine.state_matrix["mfe_long_20d"].dropna()
        mae_long = self.mfe_engine.state_matrix["mae_long_20d"].dropna()

        self.assertTrue((mfe_long >= -1e-6).all(), "多头 MFE 必须恒大于等于 0")
        self.assertTrue((mae_long <= 1e-6).all(), "多头 MAE 必须恒小于等于 0")

        mfe_short = self.mfe_engine.state_matrix["mfe_short_20d"].dropna()
        mae_short = self.mfe_engine.state_matrix["mae_short_20d"].dropna()

        self.assertTrue((mfe_short >= -1e-6).all(), "空头 MFE 必须恒大于等于 0")
        self.assertTrue((mae_short <= 1e-6).all(), "空头 MAE 必须恒小于等于 0")

    def test_08_stop_loss_surface_monotonicity(self):
        """验证止损曲面的单调性: 止损阈值放宽时，被止损的交易比例单调非增"""
        stop_df = self.mfe_engine.analyze_stop_loss_surface(
            dimension_col="fundamental_direction",
            state_value="Bullish",
            horizon=20,
            direction="long",
        )
        self.assertFalse(stop_df.empty, "止损曲面分析表不得为空")

        triggered_rates = stop_df["stop_triggered_pct"].values
        diffs = np.diff(triggered_rates)
        self.assertTrue((diffs <= 1e-6).all(), "随止损阈值放宽，触发止损的比例必须单调非增")

    # --------------------------------------------------------------------------
    # 5. 马尔可夫状态转移矩阵测试
    # --------------------------------------------------------------------------
    def test_09_transition_matrix_row_sum_unity(self):
        """验证状态转移概率矩阵的严格行归一化: 每一行概率之和恒等于 1.0"""
        for dim in ["fundamental_direction", "market_structure", "sentiment_state"]:
            counts, prob_mat = self.trans_engine.calculate_transition_matrix(self.state_matrix[dim])
            self.assertFalse(prob_mat.empty)

            row_sums = prob_mat.sum(axis=1)
            for state, r_sum in row_sums.items():
                self.assertAlmostEqual(r_sum, 1.0, delta=1e-5, msg=f"{dim}:{state} 的转移概率行和必须为 1.0")

    def test_10_stationary_distribution_validity(self):
        """验证稳态分布 pi 的性质: sum(pi) = 1.0 且各元素非负"""
        for dim in ["fundamental_direction", "market_structure"]:
            counts, prob_mat = self.trans_engine.calculate_transition_matrix(self.state_matrix[dim])
            pi = self.trans_engine.compute_stationary_distribution(prob_mat)

            self.assertFalse(pi.empty)
            self.assertAlmostEqual(pi.sum(), 1.0, delta=1e-4, msg=f"{dim} 的稳态概率之和必须为 1.0")
            self.assertTrue((pi >= -1e-6).all(), f"{dim} 的稳态概率必须全部非负")

    # --------------------------------------------------------------------------
    # 6. 入场与退出机制实证测试
    # --------------------------------------------------------------------------
    def test_11_entry_timing_comparison_validity(self):
        """验证入场确认机制评估结果的合理性与无空崩溃"""
        bull_mask = self.state_matrix["fundamental_direction"] == "Bullish"
        entry_df = self.entry_exit_engine.evaluate_entry_timing_comparison(
            base_state_filter=bull_mask,
            direction="long",
            horizon=20,
        )
        self.assertFalse(entry_df.empty, "入场时机对比表不得为空")
        self.assertGreaterEqual(len(entry_df), 3, "至少包含 3 类入场模式对比")

        # 检查各模式均值与胜率在合理范围
        for _, row in entry_df.iterrows():
            self.assertGreaterEqual(row["win_rate_pct"], 0.0)
            self.assertLessEqual(row["win_rate_pct"], 100.0)
            self.assertGreater(row["sample_count"], 0)

    def test_12_exit_mechanisms_bounded_holding(self):
        """验证退出机制模拟的持仓天数有界性 (平均持仓天数 <= 最大设定天数 30)"""
        bull_mask = self.state_matrix["fundamental_direction"] == "Bullish"
        exit_df = self.entry_exit_engine.evaluate_exit_mechanisms_comparison(
            base_state_filter=bull_mask,
            direction="long",
            max_holding_days=30,
        )
        self.assertFalse(exit_df.empty, "退出规则对比表不得为空")

        for _, row in exit_df.iterrows():
            self.assertLessEqual(row["mean_holding_days"], 30.0, f"退出规则 {row['exit_rule']} 持仓周期不得超过上限 30 天")
            self.assertGreaterEqual(row["trades_count"], 5, "交易模拟样本量必须充足")

    def test_13_friction_sensitivity_decay(self):
        """验证摩擦成本敏感性: 随着滑点增加，净收益率与胜率单调递减"""
        s = self.ret_engine.state_matrix["fwd_ret_rb_20d"].dropna()
        fric_df = self.entry_exit_engine.evaluate_friction_sensitivity(s)

        self.assertFalse(fric_df.empty)
        net_rets = fric_df["net_mean_return_pct"].values
        diffs = np.diff(net_rets)
        self.assertTrue((diffs <= 0.0).all(), "随着滑点扩大，净均值收益率必须单调递减")

    # --------------------------------------------------------------------------
    # 7. State != Position 架构断言
    # --------------------------------------------------------------------------
    def test_14_state_not_position_boundary_contract(self):
        """
        断言: 阶段 D 必须严格遵守 State != Position 契约。
        检查 stage_d 模块代码中不存在自动下单、实盘 API、持仓直接变更等越界行为。
        """
        import stage_d.return_distribution
        import stage_d.duration_survival
        import stage_d.mfe_mae_profile
        import stage_d.transition_matrix
        import stage_d.entry_exit_research

        forbidden_keywords = ["execute_order", "insert_order", "send_order", "account_balance", "real_trade"]
        for mod in [stage_d.return_distribution, stage_d.duration_survival, stage_d.mfe_mae_profile, stage_d.transition_matrix, stage_d.entry_exit_research]:
            source_code = Path(mod.__file__).read_text(encoding="utf-8")
            for kw in forbidden_keywords:
                self.assertNotIn(kw, source_code, f"阶段 D 模块 {mod.__name__} 严禁包含实盘下单关键词: {kw}")


if __name__ == "__main__":
    unittest.main()
