#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试: tests/test_term_structure_micro_arbitrage.py
测试目标:
  验证基于知识库提炼的真实期限结构微观博弈与期现状态机:
  1. 低基差/升水(Contango)临近交割实物仓单压制门禁 (RECEIPT_PRESSURE_NEAR_MONTH 绝对禁多);
  2. 高基差/深贴水临近换月产业空配迁徙门禁 (HEDGING_MIGRATION_NEAR_MONTH 绝对禁空);
  3. 现货挺价瓦解与两阶段下跌加速做空 (TWO_STAGE_BREAKDOWN 触发);
  4. ContractRolloverManager 期限结构状态诊断器 (get_term_structure_regime).
"""

import unittest
import numpy as np
import pandas as pd

from stage_e.signal_generator import SignalGenerator, TradingSignal
from stage_e.contract_rollover import ContractRolloverManager, RolloverEvent


class TestTermStructureMicroArbitrage(unittest.TestCase):

    def setUp(self):
        self.signal_gen = SignalGenerator(
            enable_receipt_pressure_gate=True,
            enable_hedging_migration_gate=True,
            enable_two_stage_breakdown=True,
        )

        self.base_state = pd.Series({
            "fundamental_direction": "Bullish",
            "fbs_score": 25.0,
            "confidence_score": 75.0,
            "spot_confirmation": "Confirmed",
            "macro_regime": "NORMAL",
            "macro_override_intensity": 0.0,
            "cost_boundary_regime": "合理利润运行",
            "market_structure": "Range",
        }, name="2026-04-01")

        self.base_feature = pd.Series({
            "rb_close": 3120.0,
            "cp_ma20": 3115.0,
            "ma_20": 3115.0,
            "cp_ma5": 3122.0,
            "ma_5": 3122.0,
            "ma_60": 3100.0,
            "rolling_high_20": 3200.0,
            "rolling_low_20": 3050.0,
            "virtual_mill_margin": 100.0,
            "pct_virtual_mill_margin": 0.40,
            "pct_virtual_mill_margin_1y": 0.40,
            "pct_basis_tier3": 0.50,
            "pct_basis_tier3_1y": 0.50,
            "basis_tier3": 50.0,
            "basis_rate_tier3": 0.015,
            "contract_dte": 90.0,
            "pct_roll_yield_1y": 0.50,
            "cost_push_spread_5d": 0.0,
            "is_ferrous_complex_uptrend": False,
            "is_supply_high_or_rising": False,
            "is_demand_high_or_stable": False,
            "pct_flow_hz_outflow": 0.50,
            "cp_atr20": 35.0,
        }, name="2026-04-01")

    def test_01_receipt_pressure_vetoes_near_month_long(self):
        """
        场景 1: 低基差/升水(Contango) + 临近交割(DTE<=45)
        实物仓单压制与虚实博弈门禁必须一票否决做多，严禁盲目博期现收敛被仓单砸死
        """
        feat = self.base_feature.copy()
        feat["contract_dte"] = 42.0
        feat["basis_rate_tier3"] = -0.008  # 期货升水 Contango
        feat["basis_tier3"] = -25.0
        feat["pct_basis_tier3_1y"] = 0.12

        sig = self.signal_gen.generate_signal(
            date_str="2026-04-01",
            state_row=self.base_state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="FLAT",
        )

        self.assertEqual(sig.direction, "FLAT")
        self.assertEqual(sig.invalidation_reason, "RECEIPT_PRESSURE_NEAR_MONTH")
        self.assertIn("实物仓单压顶与虚实博弈", sig.rationale)

    def test_02_receipt_pressure_exempts_high_margin_bull(self):
        """
        验证高利润大牛市下实物需求火爆，豁免仓单压制一票否决
        """
        feat = self.base_feature.copy()
        feat["contract_dte"] = 42.0
        feat["basis_rate_tier3"] = -0.005
        feat["pct_basis_tier3_1y"] = 0.15
        feat["virtual_mill_margin"] = 500.0  # 高利润
        feat["pct_virtual_mill_margin"] = 0.85
        feat["pct_virtual_mill_margin_1y"] = 0.85
        feat["is_ferrous_complex_uptrend"] = True
        feat["is_supply_high_or_rising"] = True
        feat["is_demand_high_or_stable"] = True

        sig = self.signal_gen.generate_signal(
            date_str="2026-04-01",
            state_row=self.base_state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="FLAT",
        )

        # 高利润牛市不被仓单门禁否决
        self.assertNotEqual(sig.invalidation_reason, "RECEIPT_PRESSURE_NEAR_MONTH")

    def test_03_hedging_migration_vetoes_near_month_short(self):
        """
        场景 2: 高基差/深贴水(Backwardation) + 临近换月交割(30<=DTE<=65)
        产业空保买平迁徙潮，近月旧主力严禁追空防踩踏打损
        """
        state = self.base_state.copy()
        state["fundamental_direction"] = "Bearish"
        state["fbs_score"] = -30.0

        feat = self.base_feature.copy()
        feat["rb_close"] = 3080.0
        feat["cp_ma20"] = 3100.0
        feat["ma_20"] = 3100.0
        feat["cp_ma5"] = 3085.0
        feat["ma_5"] = 3085.0
        feat["contract_dte"] = 52.0
        feat["basis_rate_tier3"] = 0.042  # 深度贴水 > 3.5%
        feat["basis_tier3"] = 135.0
        feat["pct_basis_tier3_1y"] = 0.82

        sig = self.signal_gen.generate_signal(
            date_str="2025-08-25",
            state_row=state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="FLAT",
        )

        self.assertEqual(sig.direction, "FLAT")
        self.assertEqual(sig.invalidation_reason, "HEDGING_MIGRATION_NEAR_MONTH")
        self.assertIn("产业空保买平迁徙潮", sig.rationale)

    def test_04_two_stage_breakdown_short_trigger(self):
        """
        场景 3: 现货挺价瓦解与两阶段下跌加速做空 (Two-Stage Breakdown)
        现货挺价瓦解补跌 + 基差拐头断崖走弱 + 均线空头排列 -> 触发加速顶格做空
        """
        state = self.base_state.copy()
        state["fundamental_direction"] = "Neutral"  # 即使基本面原先中性
        state["fbs_score"] = -10.0

        feat = self.base_feature.copy()
        feat["rb_close"] = 3050.0
        feat["cp_ma20"] = 3100.0
        feat["ma_20"] = 3100.0
        feat["cp_ma5"] = 3060.0
        feat["ma_5"] = 3060.0
        feat["cp_basis_max5"] = 55.0      # 之前基差曾高企(挺价)
        feat["cp_basis_delta3"] = -35.0   # 近3日基差断崖暴跌
        feat["cp_spot_delta3"] = -40.0    # 现货挺价彻底瓦解补跌
        feat["contract_dte"] = 90.0
        feat["basis_rate_tier3"] = 0.005
        feat["basis_tier3"] = 15.0
        feat["pct_basis_tier3_1y"] = 0.35

        sig = self.signal_gen.generate_signal(
            date_str="2024-03-20",
            state_row=state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="FLAT",
        )

        self.assertEqual(sig.direction, "SHORT")
        self.assertEqual(sig.entry_driver, "TWO_STAGE_BREAKDOWN")
        self.assertTrue(sig.is_right_side_trigger)
        self.assertIn("现货挺价瓦解与两阶段下跌加速决杀", sig.rationale)

    def test_05_contract_rollover_regime_diagnostics(self):
        """测试 ContractRolloverManager 期限结构微观诊断器"""
        mgr = ContractRolloverManager(symbol="rb")

        # 仓单压制
        res_receipt = mgr.get_term_structure_regime("2026-04-01", basis_rate=-0.010, dte=40.0)
        self.assertEqual(res_receipt["regime"], "RECEIPT_PRESSURE")
        self.assertEqual(res_receipt["recommended_action_long"], "EARLY_ROLL_OR_EXIT")

        # 空配迁徙
        res_hedging = mgr.get_term_structure_regime("2025-08-25", basis_rate=0.045, dte=50.0)
        self.assertEqual(res_hedging["regime"], "HEDGING_MIGRATION")
        self.assertEqual(res_hedging["recommended_action_short"], "VETO_NEAR_MONTH_SHORT")

        # 常规换月
        res_normal = mgr.get_term_structure_regime("2024-02-15", basis_rate=0.015, dte=80.0)
        self.assertEqual(res_normal["regime"], "NORMAL_ROLL")


if __name__ == "__main__":
    unittest.main()
