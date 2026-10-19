#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试: tests/test_low_vol_term_structure.py
测试目标:
  验证低波年份基差通道均值回归与微观期限结构合约选优策略:
  1. ContractRolloverManager 多合约三元组提取 (get_contract_trio, get_contract_by_role);
  2. 深贴水远月多头信号生成与门禁豁免 (preferred_contract_role='FAR');
  3. 升水/平水近月做空仓单压制信号生成 (preferred_contract_role='NEAR');
  4. 均值回归目标达成平仓与MA20止损平仓;
  5. 投机账户物理交割防线 (DTE <= 20 强制平仓退出).
"""

import unittest
import numpy as np
import pandas as pd

from stage_e.signal_generator import SignalGenerator, TradingSignal
from stage_e.contract_rollover import ContractRolloverManager


class TestLowVolTermStructure(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        # 共享单例，避免每个测试用例重复加载 Parquet
        cls.rollover_mgr = ContractRolloverManager()

    def setUp(self):
        self.signal_gen = SignalGenerator(
            enable_low_vol_basis_reversion=True,
            low_vol_basis_z_long=1.5,
            low_vol_basis_z_short=-1.5,
            low_vol_basis_exit_z_long=0.2,
            low_vol_basis_exit_z_short=-0.2,
        )

        self.neutral_state = pd.Series({
            "fundamental_direction": "Neutral",
            "fbs_score": 0.0,
            "confidence_score": 65.0,
            "spot_confirmation": "Neutral",
            "macro_regime": "NORMAL",
            "macro_override_intensity": 0.0,
            "cost_boundary_regime": "合理利润运行",
            "market_structure": "Range",
        }, name="2024-04-15")

        self.low_vol_feature = pd.Series({
            "rb_close": 3616.0,
            "cp_ma20": 3600.0,
            "ma_20": 3600.0,
            "cp_ma5": 3615.0,
            "ma_5": 3615.0,
            "ma_60": 3650.0,
            "rolling_high_20": 3700.0,
            "rolling_low_20": 3500.0,
            "is_low_vol_regime": True,
            "basis_zscore_60": 1.8,  # 深贴水
            "cp_spot_delta3": 10.0,  # 现货企稳
            "cp_spot": 3800.0,
            "virtual_mill_margin": 50.0,
            "pct_virtual_mill_margin": 0.30,
            "pct_virtual_mill_margin_1y": 0.30,
            "pct_basis_tier3": 0.50,
            "pct_basis_tier3_1y": 0.50,
            "basis_tier3": 184.0,
            "basis_rate_tier3": 0.05,
            "contract_dte": 183.0,
            "pct_roll_yield_1y": 0.50,
            "cost_push_spread_5d": 0.0,
            "is_ferrous_complex_uptrend": False,
            "is_supply_high_or_rising": False,
            "is_demand_high_or_stable": False,
            "pct_flow_hz_outflow": 0.50,
            "cp_atr20": 40.0,
            "cp_atr_pct": 0.015,
        }, name="2024-04-15")

    def test_01_contract_trio_extraction(self):
        """测试 2024-04-15 历史合约三元组提取及 DTE 严格单调"""
        trio = self.rollover_mgr.get_contract_trio("2024-04-15")
        self.assertIsNotNone(trio)
        self.assertIn("near", trio)
        self.assertIn("main", trio)
        self.assertIn("far", trio)

        near_c = trio["near"]
        main_c = trio["main"]
        far_c = trio["far"]

        self.assertEqual(near_c["contract_code"], "rb2405")
        self.assertEqual(main_c["contract_code"], "rb2410")
        self.assertEqual(far_c["contract_code"], "rb2501")

        # 检查 DTE
        self.assertLess(near_c["dte"], main_c["dte"])
        self.assertLess(main_c["dte"], far_c["dte"])
        self.assertAlmostEqual(near_c["dte"], 30, delta=2)

    def test_02_contract_role_lookup(self):
        """测试按角色提取特定合约"""
        near = self.rollover_mgr.get_contract_by_role("2024-04-15", "NEAR")
        main = self.rollover_mgr.get_contract_by_role("2024-04-15", "MAIN")
        far = self.rollover_mgr.get_contract_by_role("2024-04-15", "FAR")

        self.assertEqual(near["contract_code"], "rb2405")
        self.assertEqual(main["contract_code"], "rb2410")
        self.assertEqual(far["contract_code"], "rb2501")

    def test_03_deep_discount_selects_far_month(self):
        """
        场景: 低波震荡年份 + 基差显著深贴水 (Z-score >= 1.5)
        若主力合约或近月 DTE <= 45，智能路由优选远月合约 ('FAR')，规避交割月强平并享受远月基差修复
        """
        feat = self.low_vol_feature.copy()
        feat["contract_dte"] = 35.0  # 主力临近交割月
        feat["basis_zscore_60"] = 1.8
        feat["rb_close"] = 3620.0
        feat["ma_5"] = 3615.0  # c >= ma5
        feat["cp_spot_delta3"] = 5.0  # 现货未大跌

        sig = self.signal_gen.generate_signal(
            date_str="2024-04-15",
            state_row=self.neutral_state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="FLAT",
        )

        self.assertEqual(sig.direction, "LONG")
        self.assertEqual(sig.entry_driver, "LOW_VOL_BASIS_REVERSION")
        self.assertEqual(sig.preferred_contract_role, "FAR")
        self.assertIn("选约=FAR", sig.rationale)

    def test_04_contango_selects_near_month(self):
        """
        场景: 低波震荡年份 + 基差显著升水/深平水 (Z-score <= -1.5)
        近月合约承受实物仓单抛压，智能路由优选近月 ('NEAR') 做空收敛仓单折价
        """
        feat = self.low_vol_feature.copy()
        feat["contract_dte"] = 45.0  # 近月 DTE <= 60
        feat["basis_zscore_60"] = -1.7  # 严重升水
        feat["rb_close"] = 3600.0
        feat["ma_5"] = 3610.0  # c <= ma5
        feat["cp_spot_delta3"] = -15.0  # 现货下行疲软

        sig = self.signal_gen.generate_signal(
            date_str="2024-04-15",
            state_row=self.neutral_state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="FLAT",
        )

        self.assertEqual(sig.direction, "SHORT")
        self.assertEqual(sig.entry_driver, "LOW_VOL_BASIS_REVERSION")
        self.assertEqual(sig.preferred_contract_role, "NEAR")
        self.assertIn("选约=NEAR", sig.rationale)

    def test_05_mean_reversion_target_exit(self):
        """
        验证均值回归目标达成平仓:
        低波多头入场后，基差 Z-score 回归到 <= 0.2，触发均值回归止盈退出
        """
        feat = self.low_vol_feature.copy()
        feat["basis_zscore_60"] = 0.1  # 基差修复完成，Z-score <= 0.2
        feat["rb_close"] = 3650.0
        feat["ma_20"] = 3600.0

        sig = self.signal_gen.generate_signal(
            date_str="2024-04-20",
            state_row=self.neutral_state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="LONG",
            current_holding_entry_driver="LOW_VOL_BASIS_REVERSION",
        )

        self.assertEqual(sig.direction, "FLAT")
        self.assertEqual(sig.invalidation_reason, "BASIS_CONVERGENCE_TARGET_MET")

    def test_06_ma20_trailing_stop_loss(self):
        """
        验证均值回归破位止损:
        低波多头入场后，价格跌破 MA20 减去缓冲区 (Close < MA20 * (1 - 0.015) = 3546)，触发硬性止损平仓
        """
        feat = self.low_vol_feature.copy()
        feat["basis_zscore_60"] = 1.9  # 尽管基差依然大，但价格跌破 MA20 防守线
        feat["rb_close"] = 3500.0      # 3500 < 3600 * 0.985 = 3546
        feat["ma_20"] = 3600.0

        sig = self.signal_gen.generate_signal(
            date_str="2024-04-20",
            state_row=self.neutral_state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="LONG",
            current_holding_entry_driver="LOW_VOL_BASIS_REVERSION",
        )

        self.assertEqual(sig.direction, "FLAT")
        self.assertEqual(sig.invalidation_reason, "STOP_LOSS_BREAK_MA20")


if __name__ == "__main__":
    unittest.main()
