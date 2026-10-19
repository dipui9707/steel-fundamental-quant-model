#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试: tests/test_risk_firewall.py
测试目标: 验证 A06.1 五重风控防火墙核心算子与绝对否决权逻辑 (基于 unittest)
"""

import unittest
import pandas as pd
import numpy as np

from stage_c.risk_firewall import RiskControlFirewall, FirewallDecision


class TestRiskControlFirewall(unittest.TestCase):
    """五重风控防火墙单元测试套件"""

    def setUp(self):
        self.firewall = RiskControlFirewall()
        self.state_row = pd.Series({
            "macro_regime": "产业主导",
            "macro_override_intensity": 0.0,
            "fundamental_direction": "Bullish",
            "fundamental_strength": "High",
            "spot_confirmation": "Confirmed",
            "market_structure": "Bull Trend",
            "divergence_state": "None",
            "divergence_severity": "None",
            "divergence_days": 0,
            "divergence_area": 0.0,
            "model_confidence": "High",
            "confidence_score": 85.0,
            "dominant_leader_sym": "RB",
            "dominant_leader_type": "FINISHED_STEEL_DEMAND",
        }, name="2024-05-15")

        self.feature_row = pd.Series({
            "rb_close": 3700.0,
            "ma_20": 3650.0,
            "ma_60": 3600.0,
            "vol_shock_ratio": 1.05,
            "rb_ret_1d": 0.008,
            "rb_ret_5d": 0.015,
            "squeeze_index": 0.5,
            "cost_push_spread_5d": 0.002,
            "data_freshness_ratio": 0.95,
            "evidence_entropy": 0.35,
        }, name="2024-05-15")

    def test_baseline_pass(self):
        """1. 基准正常状态: 所有指标健康，应输出 PASS，允许 100% 杠杆"""
        decision = self.firewall.evaluate(self.state_row, self.feature_row, position_intent="long")
        self.assertEqual(decision.status, "PASS")
        self.assertEqual(decision.max_allowable_leverage, 1.00)
        self.assertEqual(decision.action, "HOLD")
        self.assertEqual(len(decision.breached_layers), 0)

    def test_layer1_data_freshness_vacuum(self):
        """2. 第一重: 数据新鲜度过低触发全系统停机降级"""
        feat = self.feature_row.copy()
        feat["data_freshness_ratio"] = 0.35  # 低于 0.40 阈值

        decision = self.firewall.evaluate(self.state_row, feat, position_intent="long")
        self.assertEqual(decision.status, "TRADING_HALT")
        self.assertEqual(decision.max_allowable_leverage, 0.0)
        self.assertEqual(decision.action, "HALT")
        self.assertIn("Layer 1: Data Freshness Vacuum", decision.breached_layers[0])

    def test_layer2_cross_commodity_contagion(self):
        """3. 第二重: 原料极端挤仓逼仓时，严禁做空成材"""
        feat = self.feature_row.copy()
        state = self.state_row.copy()
        feat["squeeze_index"] = 3.5
        feat["cost_push_spread_5d"] = 0.025
        state["dominant_leader_type"] = "RAW_MATERIAL_SHOCK"

        # 若意图做多成材，不被禁止做空限制阻断
        decision_long = self.firewall.evaluate(state, feat, position_intent="long")
        self.assertEqual(decision_long.status, "PASS")

        # 若意图做空成材，触发隔离墙 (设定空头技术顺势，避免触发第四重硬止损)
        feat_short = feat.copy()
        feat_short["rb_close"] = 3500.0
        feat_short["ma_20"] = 3550.0
        feat_short["ma_60"] = 3600.0
        decision_short = self.firewall.evaluate(state, feat_short, position_intent="short")
        self.assertEqual(decision_short.status, "RESTRICT_CLOSE_ONLY")
        self.assertLessEqual(decision_short.max_allowable_leverage, 0.50)
        self.assertEqual(decision_short.action, "DE_RISK_50")
        self.assertTrue(any("Layer 2: Cross-Commodity Contagion" in layer for layer in decision_short.breached_layers))

    def test_layer3_volatility_impulse_circuit_breaker(self):
        """4. 第三重: 内生波动率爆发 + 极端反向脉冲，必须无条件触发强制斩仓熔断"""
        feat = self.feature_row.copy()
        state = self.state_row.copy()
        feat["vol_shock_ratio"] = 2.8  # 超过 2.5
        feat["rb_ret_1d"] = 0.038     # 单日大涨 +3.8% (如 2024-0924)
        feat["rb_ret_5d"] = 0.065

        # 如果持仓为空头，遭遇向上极端脉冲 -> 必须无条件强制斩仓
        decision_short = self.firewall.evaluate(state, feat, position_intent="short")
        self.assertEqual(decision_short.status, "FORCED_LIQUIDATION")
        self.assertEqual(decision_short.max_allowable_leverage, 0.0)
        self.assertEqual(decision_short.action, "LIQUIDATE_IMMEDIATELY")
        self.assertTrue(any("Layer 3: Volatility Impulse Circuit Breaker" in layer for layer in decision_short.breached_layers))

        # 如果持仓为多头，脉冲与持仓一致 -> 警示但无需斩仓
        decision_long = self.firewall.evaluate(state, feat, position_intent="long")
        self.assertEqual(decision_long.status, "CAUTION")
        self.assertLessEqual(decision_long.max_allowable_leverage, 0.50)

    def test_layer4_technical_hard_stop_boundary(self):
        """5. 第四重: 技术破位硬止损 (跌破 MA20 超过 1.5% 或跌破 MA60)"""
        feat = self.feature_row.copy()
        feat["rb_close"] = 3580.0  # MA20 为 3650, 3580 跌破幅度 > 1.5%
        feat["ma_20"] = 3650.0
        feat["ma_60"] = 3600.0

        # 即使基本面是 Bullish，多头发生技术破位，必须硬止损
        decision_long = self.firewall.evaluate(self.state_row, feat, position_intent="long")
        self.assertEqual(decision_long.status, "FORCED_LIQUIDATION")
        self.assertEqual(decision_long.max_allowable_leverage, 0.0)
        self.assertEqual(decision_long.action, "LIQUIDATE_IMMEDIATELY")
        self.assertTrue(any("Layer 4: Technical Hard Stop Boundary" in layer for layer in decision_long.breached_layers))

    def test_layer5_divergence_ladder(self):
        """6. 第五重: 同尺度背离阶梯惩罚"""
        state = self.state_row.copy()
        feat = self.feature_row.copy()
        state["fundamental_direction"] = "Bearish"
        # 设为空头持仓技术顺势（低于均线），以便纯粹测试背离阶梯反应
        feat["rb_close"] = 3500.0
        feat["ma_20"] = 3550.0
        feat["ma_60"] = 3600.0

        # Case A: Mild (1~3d)
        state["divergence_days"] = 2
        state["divergence_area"] = 2.5
        state["divergence_severity"] = "Mild"
        dec_mild = self.firewall.evaluate(state, feat, position_intent="short")
        self.assertEqual(dec_mild.status, "CAUTION")
        self.assertEqual(dec_mild.max_allowable_leverage, 0.70)

        # Case B: Moderate (4~7d)
        state["divergence_days"] = 5
        state["divergence_area"] = 8.0
        state["divergence_severity"] = "Moderate"
        dec_mod = self.firewall.evaluate(state, feat, position_intent="short")
        self.assertEqual(dec_mod.status, "RESTRICT_CLOSE_ONLY")
        self.assertEqual(dec_mod.max_allowable_leverage, 0.50)
        self.assertEqual(dec_mod.action, "DE_RISK_50")

        # Case C: Severe (>=8d or Area >= 15.0)
        state["divergence_days"] = 9
        state["divergence_area"] = 16.5
        state["divergence_severity"] = "Severe"
        dec_sev = self.firewall.evaluate(state, feat, position_intent="short")
        self.assertEqual(dec_sev.status, "FORCED_LIQUIDATION")
        self.assertEqual(dec_sev.max_allowable_leverage, 0.0)
        self.assertEqual(dec_sev.action, "LIQUIDATE_IMMEDIATELY")

    def test_batch_evaluation(self):
        """7. 批量评估矩阵接口测试"""
        state_df = pd.DataFrame([self.state_row, self.state_row], index=["2024-05-15", "2024-05-16"])
        feature_df = pd.DataFrame([self.feature_row, self.feature_row], index=["2024-05-15", "2024-05-16"])

        res = self.firewall.evaluate_batch(state_df, feature_df)
        self.assertEqual(len(res), 2)
        self.assertIn("firewall_status", res.columns)
        self.assertIn("max_allowable_leverage", res.columns)
        self.assertEqual(res.iloc[0]["firewall_status"], "PASS")


if __name__ == "__main__":
    unittest.main()
