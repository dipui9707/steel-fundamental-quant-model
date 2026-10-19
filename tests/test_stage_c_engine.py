#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试: tests/test_stage_c_engine.py
功能: 阶段 C 状态模型系统高严密自动化单元测试
验证范围:
  1. 六大子模块取值规范与枚举合规性 (严格契合 A05/A05.1/A05.2/A06);
  2. 宏观政策冲击与外生变量识别准确性;
  3. 边际成本下轨与原料负反馈边界识别;
  4. 现货真实确认与双轨基差形态逻辑;
  5. 情绪拥挤度与五品种跨品种共振逻辑;
  6. 价格形态与同尺度背离严重度分级;
  7. 模型信任机制有界性与降级断路器逻辑;
  8. 端到端状态矩阵合成契约与坚决贯彻 State != Position。
"""

import sys
import unittest
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_c.regime_macro import MacroRegimeClassifier
from stage_c.state_fundamental import FundamentalStateClassifier
from stage_c.state_spot import SpotStateClassifier
from stage_c.state_sentiment import SentimentStateClassifier
from stage_c.market_structure import MarketStructureClassifier
from stage_c.model_confidence import ModelConfidenceClassifier
from stage_c.state_engine import StageCStateEngine
from stage_c.state_evaluator import StateEvaluator


class TestStageCEngine(unittest.TestCase):
    """阶段 C 核心状态引擎测试套件"""

    @classmethod
    def setUpClass(cls):
        # 加载 2024 年真实历史特征作为集成测试样本 (覆盖 2024Q1 负反馈与 924 宏观大转向)
        feat_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
        if feat_path.exists():
            full_df = pd.read_parquet(feat_path)
            cls.test_panel = full_df.loc["2024-01-02":"2024-10-31"].copy()
        else:
            # 备用合成数据以防脱机测试
            idx = pd.date_range("2024-01-02", "2024-06-30", freq="B")
            cls.test_panel = pd.DataFrame(index=idx)
            cls.test_panel["rb_close"] = 3600.0
            cls.test_panel["fbs_score"] = 20.0
            cls.test_panel["basis_tier3"] = 40.0
            cls.test_panel["rb_voi"] = 0.85
            cls.test_panel["macro_pmi"] = 50.1

    def test_macro_regime_classifier(self):
        """1. 检验宏观引擎对纯客观数据驱动(内生波动率脉冲/极端PMI/常态平稳)的识别，零后视镜硬编码"""
        clf = MacroRegimeClassifier()

        # A. 盘面内生极端波动率爆发脉冲 (如突发重磅刺激导致 5 日波动率暴增 2.8 倍且大涨 6%)
        row_shock = pd.Series({
            "macro_pmi": 49.8,
            "real_estate_invest_yoy": -10.1,
            "rb_vol_shock_ratio": 2.8,
            "rb_ret_5d": 0.06
        })
        res_shock = clf.classify_row(row_shock)
        self.assertEqual(res_shock["macro_regime"], "宏观覆盖")
        self.assertTrue(res_shock["external_shock_flag"])
        self.assertEqual(res_shock["macro_shock_event"], "MARKET_VOLATILITY_EXPANSION_UP")
        self.assertEqual(res_shock["macro_policy_bias"], "Market_Rally")
        self.assertGreaterEqual(res_shock["macro_override_intensity"], 0.80)

        # B. 极端宏观数据断崖 (如 PMI 跌至 35.7 深度收缩)
        row_extreme_pmi = pd.Series({"macro_pmi": 35.7, "real_estate_invest_yoy": -12.0})
        res_pmi = clf.classify_row(row_extreme_pmi)
        self.assertEqual(res_pmi["macro_regime"], "宏观覆盖")
        self.assertGreaterEqual(res_pmi["macro_override_intensity"], 0.85)

        # C. 常态产业主导期 (PMI 接近 50 荣枯线，无内生冲击)
        row_normal = pd.Series({"macro_pmi": 50.2, "real_estate_invest_yoy": -5.0, "rb_vol_shock_ratio": 1.0})
        res_normal = clf.classify_row(row_normal)
        self.assertEqual(res_normal["macro_regime"], "产业主导")
        self.assertFalse(res_normal["external_shock_flag"])
        self.assertLessEqual(res_normal["macro_override_intensity"], 0.35)

    def test_fundamental_state_classifier(self):
        """2. 检验基本面方向、成本边界与原料反馈"""
        clf = FundamentalStateClassifier()

        # A. 产业偏多 + 强动量
        row_bull = pd.Series({
            "fbs_score": 45.0,
            "fv_10d": 0.6,
            "fa_10d": 0.2,
            "cost_gap_ratio": 0.05,
            "profit_bf": 150.0,
            "virtual_mill_margin": 100.0,
            "score_supply": -0.4,
            "score_demand": 0.5,
            "score_inventory": 0.6,
        })
        res_bull = clf.classify_row(row_bull)
        self.assertEqual(res_bull["fundamental_direction"], "Bullish")
        self.assertEqual(res_bull["fundamental_strength"], "High")
        self.assertEqual(res_bull["cost_boundary_regime"], "合理利润运行")
        self.assertEqual(res_bull["supply_pressure"], "High")
        self.assertEqual(res_bull["demand_resilience"], "Strong")
        self.assertEqual(res_bull["inventory_trajectory"], "Accelerating Destock")

        # B. 深度亏损下轨 + 原料负反馈踩踏 (2024Q1 场景)
        row_bear = pd.Series({
            "fbs_score": -35.0,
            "fv_10d": -0.8,
            "cost_gap_ratio": -0.08,
            "profit_bf": -220.0,
            "virtual_mill_margin": -180.0,
        })
        res_bear = clf.classify_row(row_bear)
        self.assertEqual(res_bear["fundamental_direction"], "Bearish")
        self.assertEqual(res_bear["cost_boundary_regime"], "深度亏损下轨支撑")
        self.assertEqual(res_bear["raw_feedback_regime"], "原料负反馈踩踏")

    def test_spot_state_classifier(self):
        """3. 检验现货物理确认、基差形态与套利利润"""
        clf = SpotStateClassifier()

        # A. 现货确认偏多 (升水 + 库销比健康)
        row_conf = pd.Series({
            "basis_tier3": 65.0,
            "hz_stock_to_sales": 15.0,
            "flow_hz_outflow": 3.8,
            "net_cash_carry": 25.0,
        })
        res_conf = clf.classify_row(row_conf, fund_dir="Bullish")
        self.assertEqual(res_conf["spot_confirmation"], "Confirmed")
        self.assertEqual(res_conf["basis_regime"], "常规升水(Back结构)")
        self.assertEqual(res_conf["spot_inventory_liquidity"], "真去库强消化")
        self.assertEqual(res_conf["cash_carry_arbitrage"], "正套套利有利润")

        # B. 现货否认偏多 (深度贴水Contango，现货不跟涨)
        row_rej = pd.Series({"basis_tier3": -75.0})
        res_rej = clf.classify_row(row_rej, fund_dir="Bullish")
        self.assertEqual(res_rej["spot_confirmation"], "Rejected")
        self.assertEqual(res_rej["basis_regime"], "显著贴水(Contango结构)")

    def test_sentiment_state_classifier(self):
        """4. 检验情绪拥挤、量价仓强化与跨品种共振"""
        clf = SentimentStateClassifier()

        # A. 极端换手拥挤
        row_crowd = pd.Series({
            "rb_voi": 1.55,
            "rb_ret_1d": 0.01,
            "micro_pv_state": "增仓上涨",
            "virtual_margin_zscore": 2.4,
        })
        res_crowd = clf.classify_row(row_crowd)
        self.assertEqual(res_crowd["sentiment_state"], "拥挤")
        self.assertEqual(res_crowd["crowding_risk"], "Extreme")

        # B. 跨品种共振计算
        res_df = clf.classify_all(self.test_panel)
        self.assertIn("cross_commodity_resonance", res_df.columns)
        allowed_res = {"板块多头共振", "板块空头共振", "品种分化博弈"}
        self.assertTrue(set(res_df["cross_commodity_resonance"].unique()).issubset(allowed_res))

    def test_market_structure_classifier(self):
        """5. 检验价格通道与同尺度背离严重度分级"""
        clf = MarketStructureClassifier()

        # A. 牛头通道与无背离
        row_bull = pd.Series({
            "rb_close": 3800.0,
            "ma_20": 3700.0,
            "ma_60": 3600.0,
            "divergence_days": 0,
            "divergence_area": 0.0,
        })
        res_bull = clf.classify_row(row_bull, spot_conf="Confirmed")
        self.assertEqual(res_bull["market_structure"], "Bull Trend")
        self.assertEqual(res_bull["divergence_state"], "None")
        self.assertEqual(res_bull["divergence_severity"], "None")

        # B. 严重同尺度背离 (持续 9 天，累计面积 18.5)
        row_div = pd.Series({
            "rb_close": 3500.0,
            "ma_20": 3550.0,
            "ma_60": 3600.0,
            "divergence_days": 9,
            "divergence_area": 18.5,
        })
        res_div = clf.classify_row(row_div, spot_conf="Rejected")
        self.assertEqual(res_div["market_structure"], "Bear Trend")
        self.assertEqual(res_div["divergence_state"], "多重背离")
        self.assertEqual(res_div["divergence_severity"], "Severe")

    def test_model_confidence_and_fallback(self):
        """6. 检验信任评分有界性、降级模式与惩罚逻辑"""
        clf = ModelConfidenceClassifier()

        # A. 优良环境 -> 高置信度
        m_good = {"macro_regime": "产业主导", "external_shock_flag": False}
        f_good = {"fundamental_direction": "Bullish", "fundamental_strength": "High"}
        s_good = {"spot_confirmation": "Confirmed"}
        sent_good = {"sentiment_state": "强化", "crowding_risk": "Normal"}
        mkt_good = {"market_structure": "Bull Trend", "divergence_state": "None", "divergence_severity": "None"}
        feat_good = pd.Series({"data_freshness_ratio": 0.95, "evidence_entropy": 0.40, "fa_10d": 0.2})

        res_good = clf.classify_row(m_good, f_good, s_good, sent_good, mkt_good, feat_good)
        self.assertEqual(res_good["model_confidence"], "High")
        self.assertGreaterEqual(res_good["confidence_score"], 70.0)
        self.assertEqual(res_good["fallback_regime"], "FULL_RESEARCH")
        self.assertEqual(res_good["lifecycle"], "强化")
        self.assertEqual(res_good["persistence"], "High")

        # B. 严重背离 + 宏观覆盖 -> 触发降级 MARKET_ONLY
        m_bad = {"macro_regime": "宏观覆盖", "external_shock_flag": True}
        f_bad = {"fundamental_direction": "Bullish", "fundamental_strength": "Low"}
        s_bad = {"spot_confirmation": "Rejected"}
        sent_bad = {"sentiment_state": "拥挤", "crowding_risk": "Extreme"}
        mkt_bad = {"market_structure": "Bear Trend", "divergence_state": "多重背离", "divergence_severity": "Severe"}
        feat_bad = pd.Series({"data_freshness_ratio": 0.70, "evidence_entropy": 0.80, "fa_10d": -0.3})

        res_bad = clf.classify_row(m_bad, f_bad, s_bad, sent_bad, mkt_bad, feat_bad)
        self.assertEqual(res_bad["model_confidence"], "Low")
        self.assertLess(res_bad["confidence_score"], 45.0)
        self.assertEqual(res_bad["fallback_regime"], "MARKET_ONLY")

    def test_state_engine_end_to_end_synthesis(self):
        """7. 检验端到端全景状态矩阵合成与契约合规"""
        engine = StageCStateEngine()
        matrix = engine.synthesize_states(self.test_panel)

        self.assertEqual(len(matrix), len(self.test_panel))
        self.assertTrue(matrix.index.is_monotonic_increasing)

        # 检验核心状态列存在且无非法缺失
        required_cols = [
            "macro_regime", "macro_override_intensity", "external_shock_flag",
            "fundamental_direction", "fundamental_strength", "cost_boundary_regime", "raw_feedback_regime",
            "spot_confirmation", "basis_regime", "spot_inventory_liquidity",
            "sentiment_state", "crowding_risk", "cross_commodity_resonance",
            "market_structure", "volatility_regime", "divergence_state", "divergence_severity",
            "model_confidence", "confidence_score", "fallback_regime", "lifecycle", "persistence"
        ]
        for col in required_cols:
            self.assertIn(col, matrix.columns, f"Missing state column: {col}")
            self.assertFalse(matrix[col].isnull().all(), f"Column {col} is all null")

        # 严格检验契约: 绝不包含任何仓位或交易订单列 (State != Position)
        forbidden_terms = ["position", "order", "target_weight", "buy_signal", "sell_signal"]
        for col in matrix.columns:
            for term in forbidden_terms:
                self.assertNotIn(term, col.lower(), f"State matrix must not contain position/trading column: {col}")

    def test_state_evaluator_and_returns(self):
        """8. 检验实证评估引擎计算"""
        engine = StageCStateEngine()
        matrix = engine.synthesize_states(self.test_panel)

        evaluator = StateEvaluator(self.test_panel, matrix, horizons=[5, 10])
        comp_df = evaluator.evaluate_composite_strategy_regimes()
        self.assertFalse(comp_df.empty)
        self.assertIn("composite_regime", comp_df.columns)
        self.assertIn("ret_10d_mean_pct", comp_df.columns)

        div_res = evaluator.evaluate_divergence_resolution()
        self.assertIn("price_reversion_rate_pct", div_res)


    def test_adaptive_percentile_state_classification(self):
        """9. 检验自适应历史分位数对跨周期演进（高价高利 vs 低价低利）的判定有效性"""
        fund_clf = FundamentalStateClassifier()
        spot_clf = SpotStateClassifier()
        sent_clf = SentimentStateClassifier()

        # A. 2024-2026 低价低利时代场景:
        # 即期盘面虚拟毛利为 -60 元 (未跌破老旧常数 -100 元，但在本轮微利周期中已处于历史 8% 极低分位)
        # 传统静态系统会错失原料负反馈踩踏，而自适应分位数系统能灵敏捕捉！
        row_new_era = pd.Series({
            "virtual_mill_margin": -60.0,
            "pct_virtual_mill_margin": 0.08,
            "fbs_score": -20.0,
            "fv_10d": -0.4,
            "cost_gap_ratio": -0.03,
            "pct_cost_gap_ratio": 0.06,
            "profit_bf": -80.0,
            "pct_profit_bf": 0.07,
        })
        res_fund = fund_clf.classify_row(row_new_era)
        self.assertEqual(res_fund["cost_boundary_regime"], "深度亏损下轨支撑")
        self.assertEqual(res_fund["raw_feedback_regime"], "原料负反馈踩踏")

        # B. 现货微观确认: 基差 10 元 (未达到老旧绝对常数 25 元，但处于历史 65% 分位，且库销比处于历史 20% 最健康去库区)
        row_spot = pd.Series({
            "basis_tier3": 10.0,
            "pct_basis_tier3": 0.65,
            "pct_hz_stock_to_sales": 0.20,
            "pct_flow_hz_outflow": 0.80,
        })
        res_spot = spot_clf.classify_row(row_spot, fund_dir="Bullish")
        self.assertEqual(res_spot["spot_confirmation"], "Confirmed")
        self.assertEqual(res_spot["basis_regime"], "常规升水(Back结构)")
        self.assertEqual(res_spot["spot_inventory_liquidity"], "真去库强消化")

        # C. 筹码换手拥挤: VOI 为 1.15 (未达到老旧绝对常数 1.40，但在降频博弈新常态下位于历史 95% 极端拥挤区)
        row_sent = pd.Series({
            "rb_voi": 1.15,
            "pct_rb_voi": 0.95,
            "rb_ret_1d": 0.005,
            "micro_pv_state": "增仓上涨",
        })
        res_sent = sent_clf.classify_row(row_sent)
        self.assertEqual(res_sent["sentiment_state"], "拥挤")
        self.assertEqual(res_sent["crowding_risk"], "Extreme")

    def test_raw_material_squeeze_shock_and_crowding(self):
        """10. 检验突发大波动/原料逼仓(如焦煤矿难)触发宏观外部冲击覆盖与情绪极端拥挤联动"""
        macro_clf = MacroRegimeClassifier()
        sent_clf = SentimentStateClassifier()

        # 构造遭遇原料逼仓冲击的一行特征
        row_squeeze = pd.Series({
            "is_raw_material_squeeze": True,
            "cost_push_spread_5d": 0.045,
            "jm_squeeze_index": 3.8,
            "dominant_leader_sym": "JM",
            "dominant_leader_type": "RAW_MATERIAL_SHOCK",
            "macro_pmi": 50.0,
            "rb_voi": 0.85,
        })

        # A. 宏观引擎应立即识别外部供给逼仓冲击并启动高强度覆盖 (0.75)
        res_macro = macro_clf.classify_row(row_squeeze, dt_str="2024-05-15")
        self.assertEqual(res_macro["macro_regime"], "宏观覆盖")
        self.assertTrue(res_macro["external_shock_flag"])
        self.assertEqual(res_macro["macro_shock_event"], "RAW_MATERIAL_PRICE_SQUEEZE")
        self.assertEqual(res_macro["macro_policy_bias"], "Unconfirmed_Raw_Shock")
        self.assertEqual(res_macro["macro_override_intensity"], 0.75)

        # B. 情绪引擎应识别原料外溢导致的极端拥挤风险
        res_sent = sent_clf.classify_row(row_squeeze)
        self.assertEqual(res_sent["sentiment_state"], "拥挤")
        self.assertEqual(res_sent["crowding_risk"], "Extreme")


if __name__ == "__main__":
    unittest.main()
