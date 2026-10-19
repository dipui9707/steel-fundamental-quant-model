#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试: tests/test_calendar_spread_arbitrage.py
测试目标:
  验证第二阶段 (Phase 2) 螺纹钢跨期双腿套利 (Calendar Spread Arbitrage: Bull & Bear Spread):
  1. ContractRolloverManager 跨期合约对抽取 (NEAR_MAIN, MAIN_FAR) 与 DTE 单调性;
  2. 低波区间交割换月窗口 (25 <= DTE <= 65) 跨期正套 (Bull Spread) 信号生成;
  3. 低波区间交割换月窗口 (25 <= DTE <= 65) 跨期反套 (Bear Spread) 信号生成;
  4. ExecutionEngine 双腿撮合执行、上期所大边保证金占用与会计盯市核算;
  5. 跨期正套目标达成 (+35点) 止盈平仓与双腿闭环流水记录;
  6. 跨期反套反向走强 (+30点) 止损平仓;
  7. 投机账户物理交割防线 (DTE <= 20 强制双腿平仓退出).
"""

import unittest
import numpy as np
import pandas as pd

from stage_e.signal_generator import SignalGenerator, TradingSignal
from stage_e.contract_rollover import ContractRolloverManager, RolloverEvent
from stage_e.execution_engine import ExecutionEngine, TradeRecord
from stage_e.position_sizer import PositionTarget


class TestCalendarSpreadArbitrage(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.rollover_mgr = ContractRolloverManager(symbol="rb")

    def setUp(self):
        self.signal_gen = SignalGenerator(
            enable_calendar_spread=True,
            calendar_spread_z_bull=1.5,
            calendar_spread_z_bear=-1.5,
            calendar_spread_target_bull=35.0,
            calendar_spread_target_bear=-35.0,
            calendar_spread_stop_bull=-30.0,
            calendar_spread_stop_bear=30.0,
            calendar_spread_min_dte=25.0,
            calendar_spread_max_dte=65.0,
            calendar_spread_force_exit_dte=20.0,
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
            "cp_spot_delta3": 10.0,  # 现货抗跌企稳
            "cp_spot_ret5": 0.002,
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

    def test_01_calendar_spread_pair_extraction(self):
        """测试 2024 年 4 月与 8 月真实跨期合约对提取"""
        pair_apr = self.rollover_mgr.get_calendar_spread_pair("2024-04-15")
        self.assertIsNotNone(pair_apr)
        self.assertEqual(pair_apr["pair_type"], "NEAR_MAIN")
        self.assertEqual(pair_apr["front"]["contract_code"], "rb2405")
        self.assertEqual(pair_apr["back"]["contract_code"], "rb2410")
        self.assertEqual(pair_apr["front_role"], "NEAR")
        self.assertEqual(pair_apr["back_role"], "MAIN")
        self.assertLess(pair_apr["front_dte"], pair_apr["back_dte"])
        self.assertTrue(25 <= pair_apr["front_dte"] <= 65)

        pair_aug = self.rollover_mgr.get_calendar_spread_pair("2024-08-14")
        self.assertIsNotNone(pair_aug)
        self.assertEqual(pair_aug["pair_type"], "MAIN_FAR")
        self.assertEqual(pair_aug["front"]["contract_code"], "rb2410")
        self.assertEqual(pair_aug["back"]["contract_code"], "rb2501")
        self.assertEqual(pair_aug["front_role"], "MAIN")
        self.assertEqual(pair_aug["back_role"], "FAR")
        self.assertLess(pair_aug["front_dte"], pair_aug["back_dte"])
        self.assertTrue(25 <= pair_aug["front_dte"] <= 65)

    def test_02_bull_spread_signal_generation(self):
        """测试低波深贴水触发跨期正套信号 (买近月+卖远月)"""
        pair_info = {
            "pair_type": "NEAR_MAIN",
            "front_role": "NEAR",
            "back_role": "MAIN",
            "front_dte": 30.0,
            "back_dte": 183.0,
        }
        feat = self.low_vol_feature.copy()
        feat["basis_zscore_60"] = 1.8  # 深贴水
        feat["cp_spot_delta3"] = 10.0  # 现货抗跌

        sig = self.signal_gen.generate_signal(
            date_str="2024-04-15",
            state_row=self.neutral_state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="FLAT",
            front_dte=30.0,
            calendar_pair_info=pair_info,
        )

        self.assertEqual(sig.direction, "LONG")
        self.assertEqual(sig.spread_type, "BULL_SPREAD")
        self.assertEqual(sig.entry_driver, "CALENDAR_BULL_SPREAD")
        self.assertEqual(sig.preferred_contract_role, "NEAR")
        self.assertEqual(sig.secondary_contract_role, "MAIN")
        self.assertIn("跨期正套", sig.rationale)

    def test_03_bear_spread_signal_generation(self):
        """测试低波高升水触发跨期反套信号 (卖近月+买远月)"""
        pair_info = {
            "pair_type": "NEAR_MAIN",
            "front_role": "NEAR",
            "back_role": "MAIN",
            "front_dte": 40.0,
            "back_dte": 193.0,
        }
        feat = self.low_vol_feature.copy()
        feat["basis_zscore_60"] = -1.8  # 显著升水
        feat["cp_spot_delta3"] = -10.0  # 现货走弱
        feat["cp_spot_ret5"] = -0.005

        sig = self.signal_gen.generate_signal(
            date_str="2024-04-15",
            state_row=self.neutral_state,
            feature_row=feat,
            strategy_mode="QUANT_CORE",
            current_holding_direction="FLAT",
            front_dte=40.0,
            calendar_pair_info=pair_info,
        )

        self.assertEqual(sig.direction, "SHORT")
        self.assertEqual(sig.spread_type, "BEAR_SPREAD")
        self.assertEqual(sig.entry_driver, "CALENDAR_BEAR_SPREAD")
        self.assertEqual(sig.preferred_contract_role, "NEAR")
        self.assertEqual(sig.secondary_contract_role, "MAIN")
        self.assertIn("跨期反套", sig.rationale)

    def test_04_bull_spread_execution_and_mtm(self):
        """测试 ExecutionEngine 跨期正套双腿撮合、大边保证金与会计核算"""
        engine = ExecutionEngine(initial_capital=10_000_000.0)
        target = PositionTarget(
            trade_date="2024-04-15",
            target_direction="LONG",
            target_weight=0.20,
            target_lots=50,
            target_nominal_value=1_800_000.0,
            estimated_margin=180_000.0,
            margin_utilization=0.20,
            effective_leverage=0.18,
            rationale="低波跨期正套",
        )
        dummy_roll = RolloverEvent("2024-04-16", False, "rb2405", "rb2405", 3600.0, 3600.0, 0.0, "保持")

        snap = engine.execute_next_bar(
            date_str="2024-04-16",
            target=target,
            open_price=3600.0,
            settlement_price=3620.0,
            close_price=3620.0,
            rollover_event=dummy_roll,
            active_contract_code="rb2405",
            prediction_id="PRED_TEST_01",
            secondary_open_price=3660.0,
            secondary_settlement_price=3650.0,
            secondary_close_price=3650.0,
            secondary_contract_code="rb2410",
            spread_type="BULL_SPREAD",
        )

        # 校验双腿持仓
        self.assertTrue(engine.is_spread_position)
        self.assertEqual(engine.spread_type, "BULL_SPREAD")
        self.assertEqual(engine.current_contract, "rb2405")
        self.assertEqual(engine.current_lots, 50)
        self.assertEqual(engine.secondary_contract, "rb2410")
        self.assertEqual(engine.secondary_lots, -50)

        # 检验开仓成交价格 (含 1 tick 滑点)
        self.assertEqual(engine.avg_entry_price, 3601.0)  # 买入: 3600 + 1
        self.assertEqual(engine.secondary_avg_entry_price, 3659.0)  # 卖出: 3660 - 1

        # 检验大边保证金: max(3620, 3650) * 50 * 10 * 0.10 = 182,500
        expected_margin = 50 * 10 * 3650.0 * 0.10
        self.assertAlmostEqual(snap["margin_occupied"], expected_margin, places=2)

        # 检验浮动盈亏:
        # 前腿(多): (3620 - 3601) * 50 * 10 = +9,500
        # 后腿(空): (3659 - 3650) * 50 * 10 = +4,500
        # 总浮盈 = 9500 + 4500 = 14,000
        self.assertAlmostEqual(snap["unrealized_pnl"], 14000.0, places=2)

        # 校验会计绝对恒等式
        self.assertAlmostEqual(snap["total_equity"], snap["available_cash"] + snap["margin_occupied"], places=2)

    def test_05_bull_spread_target_exit(self):
        """测试跨期正套价差走扩达成 (+35点) 止盈全平与双腿闭环流水"""
        engine = ExecutionEngine(initial_capital=10_000_000.0)
        open_target = PositionTarget(
            trade_date="2024-04-15",
            target_direction="LONG",
            target_weight=0.20,
            target_lots=50,
            target_nominal_value=1_800_000.0,
            estimated_margin=180_000.0,
            margin_utilization=0.20,
            effective_leverage=0.18,
            rationale="低波跨期正套开仓",
        )
        dummy_roll = RolloverEvent("2024-04-16", False, "rb2405", "rb2405", 3600.0, 3600.0, 0.0, "保持")

        # 1. T+1 开仓: Spread_entry = 3601 - 3659 = -58 点
        engine.execute_next_bar(
            date_str="2024-04-16",
            target=open_target,
            open_price=3600.0,
            settlement_price=3600.0,
            close_price=3600.0,
            rollover_event=dummy_roll,
            active_contract_code="rb2405",
            secondary_open_price=3660.0,
            secondary_settlement_price=3660.0,
            secondary_close_price=3660.0,
            secondary_contract_code="rb2410",
            spread_type="BULL_SPREAD",
        )

        # 2. 持仓期间价差由 -58 走扩至 -18 (+40 点，达成 >= 35 点止盈)
        sig = self.signal_gen.generate_signal(
            date_str="2024-04-20",
            state_row=self.neutral_state,
            feature_row=self.low_vol_feature,
            strategy_mode="QUANT_CORE",
            current_holding_direction="LONG",
            current_holding_entry_driver="CALENDAR_BULL_SPREAD",
            current_spread_pts=-18.0,
            spread_entry_pts=-58.0,
            front_dte=26.0,
        )
        self.assertEqual(sig.direction, "FLAT")
        self.assertEqual(sig.invalidation_reason, "CALENDAR_SPREAD_TARGET_MET")

        # 3. T+2 开盘平仓双腿退出
        close_target = PositionTarget(
            trade_date="2024-04-20",
            target_direction="FLAT",
            target_weight=0.0,
            target_lots=0,
            target_nominal_value=0.0,
            estimated_margin=0.0,
            margin_utilization=0.0,
            effective_leverage=0.0,
            rationale=sig.rationale,
        )
        snap_exit = engine.execute_next_bar(
            date_str="2024-04-21",
            target=close_target,
            open_price=3650.0,
            settlement_price=3650.0,
            close_price=3650.0,
            rollover_event=dummy_roll,
            active_contract_code="rb2405",
            secondary_open_price=3668.0,
            secondary_settlement_price=3668.0,
            secondary_close_price=3668.0,
            secondary_contract_code="rb2410",
            spread_type="BULL_SPREAD",
        )

        # 校验双腿已完全平仓归零
        self.assertFalse(engine.is_spread_position)
        self.assertEqual(engine.current_lots, 0)
        self.assertEqual(engine.secondary_lots, 0)
        self.assertEqual(len(engine.trade_records), 2)

        # 校验两笔交易记录分别归属前腿与后腿
        recs = engine.trade_records
        self.assertEqual(recs[0].contract, "rb2405")
        self.assertEqual(recs[0].side, "SELL_CLOSE")
        self.assertEqual(recs[1].contract, "rb2410")
        self.assertEqual(recs[1].side, "BUY_CLOSE")

        # 校验总净资产增值与净利润为正
        self.assertGreater(snap_exit["total_equity"], 10_000_000.0)
        self.assertGreater(engine.cumulative_realized_pnl, 0.0)

    def test_06_bear_spread_stop_loss(self):
        """测试跨期反套价差反向走强 (+30点) 触发止损"""
        sig = self.signal_gen.generate_signal(
            date_str="2024-04-20",
            state_row=self.neutral_state,
            feature_row=self.low_vol_feature,
            strategy_mode="QUANT_CORE",
            current_holding_direction="SHORT",
            current_holding_entry_driver="CALENDAR_BEAR_SPREAD",
            current_spread_pts=-10.0,
            spread_entry_pts=-42.0,  # 价差从 -42 涨到 -10 (变动 +32 >= 30 止损)
            front_dte=35.0,
        )
        self.assertEqual(sig.direction, "FLAT")
        self.assertEqual(sig.invalidation_reason, "CALENDAR_SPREAD_STOP_LOSS")

    def test_07_physical_delivery_forced_exit(self):
        """测试临近交割月 (Front DTE <= 20) 触发投机账户强制平仓双腿"""
        sig = self.signal_gen.generate_signal(
            date_str="2024-04-25",
            state_row=self.neutral_state,
            feature_row=self.low_vol_feature,
            strategy_mode="QUANT_CORE",
            current_holding_direction="LONG",
            current_holding_entry_driver="CALENDAR_BULL_SPREAD",
            current_spread_pts=-30.0,
            spread_entry_pts=-40.0,
            front_dte=19.0,  # DTE <= 20
        )
        self.assertEqual(sig.direction, "FLAT")
        self.assertEqual(sig.invalidation_reason, "FORCED_DELIVERY_EXIT")
        self.assertIn("交割保护", sig.rationale)


if __name__ == "__main__":
    unittest.main()
