#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试: tests/test_tactical_adapter.py
测试目标:
  验证 stage_e/tactical_adapter.py 及 ExecutionEngine 跨周期战术接入功能:
  1. 品种白名单限制 (严格仅对 rb, hc 激活，原料品种隔离直通);
  2. 战术多头/空头波段处理与 PnL 汇总;
  3. 战术终止 (GAP_EXHAUSTION_EXIT / INITIAL_BREAKOUT_FAILED) 联动 ExecutionEngine 拦截被动开仓;
  4. 宏观系统指令强制平仓 (force_macro_exit);
  5. 状态机重置与双向互锁完整性。
"""

import unittest
import pandas as pd
import numpy as np

from stage_e.tactical_adapter import TacticalExecutionAdapter, TacticalExecutionStatus
from stage_e.tactical_exhaustion_engine import TacticalConfig
from stage_e.execution_engine import ExecutionEngine, TradeRecord
from stage_e.position_sizer import PositionTarget
from stage_e.contract_rollover import RolloverEvent


class TestTacticalAdapter(unittest.TestCase):

    def _generate_synthetic_bars(self, prices, lows=None, highs=None, dates=None):
        n = len(prices)
        if dates is None:
            dates = ["2026-10-14"] * n
        rows = []
        for i in range(n):
            p = prices[i]
            prev_p = prices[i-1] if i > 0 else p
            op = p - 2.0 if p >= prev_p else p + 2.0
            hi = highs[i] if highs is not None else max(op, p) + 2.0
            lo = lows[i] if lows is not None else min(op, p) - 2.0
            rows.append({
                "open": op,
                "high": hi,
                "low": lo,
                "close": p,
                "volume": 1000.0,
                "open_interest": 50000.0,
                "trade_date": dates[i],
                "datetime_str": f"{dates[i]} 09:{i*5:02d}:00"
            })
        return pd.DataFrame(rows)

    def test_01_supported_symbol_whitelist(self):
        """测试品种白名单约束: 仅 rb 与 hc 激活，其余品种严格直通隔离"""
        adapter_rb = TacticalExecutionAdapter(symbol="rb")
        adapter_hc = TacticalExecutionAdapter(symbol="hc")
        adapter_jm = TacticalExecutionAdapter(symbol="jm")  # 焦煤
        adapter_i = TacticalExecutionAdapter(symbol="i")    # 铁矿

        self.assertTrue(adapter_rb.is_supported)
        self.assertTrue(adapter_hc.is_supported)
        self.assertFalse(adapter_jm.is_supported)
        self.assertFalse(adapter_i.is_supported)

        # 验证类方法对长代码前缀的识别
        self.assertTrue(TacticalExecutionAdapter.is_symbol_supported("SHFE.rb2410"))
        self.assertTrue(TacticalExecutionAdapter.is_symbol_supported("SHFE.hc2501"))
        self.assertFalse(TacticalExecutionAdapter.is_symbol_supported("DCE.jm2501"))

        # 非支持品种调用 process_intraday_episode 直接直通跳过
        df = self._generate_synthetic_bars([3000.0] * 10)
        res_jm = adapter_jm.process_intraday_episode(df, "LONG", allocated_lots=10)
        self.assertEqual(res_jm["status"], "SKIPPED_UNSUPPORTED_SYMBOL")

    def test_02_process_trend_episode_rebar(self):
        """测试螺纹钢波段行情战术护航与 PnL 汇总"""
        prices = [3000.0] * 12 + [3050.0, 3100.0, 3150.0, 3200.0] + [3180.0, 3160.0, 3140.0]
        df = self._generate_synthetic_bars(prices)

        adapter = TacticalExecutionAdapter(symbol="rb")
        res = adapter.process_intraday_episode(df, macro_direction="LONG", allocated_lots=10, start_idx=5)

        self.assertIn("tactical_status", res)
        status = adapter.get_status()
        self.assertEqual(status.symbol, "rb")
        self.assertTrue(status.is_supported)
        self.assertGreater(len(adapter.tactical_trades), 0)

    def test_03_initial_breakout_failed_interlock(self):
        """测试恶性假突破触发 INITIAL_BREAKOUT_FAILED 时向 ExecutionEngine 联动拦截"""
        # 开仓后第 3 根 Bar 暴跌破位打穿平台低点
        prices = [3000.0] * 5 + [3002.0, 2995.0, 2965.0, 2950.0]
        lows = [2998.0] * 5 + [3000.0, 2990.0, 2960.0, 2945.0]
        df = self._generate_synthetic_bars(prices, lows=lows)

        cfg = TacticalConfig(initial_stop_buffer_ticks=15.0)
        adapter = TacticalExecutionAdapter(symbol="rb", config=cfg)
        res = adapter.process_intraday_episode(df, macro_direction="LONG", allocated_lots=10, start_idx=4)

        status = adapter.get_status()
        self.assertTrue(status.is_tactical_terminated)
        self.assertIn("INITIAL_BREAKOUT_FAILED", status.termination_reason)

        # 挂载至 ExecutionEngine，验证当日线继续给出 LONG 时被战术层拦截
        exec_engine = ExecutionEngine(initial_capital=1_000_000.0)
        exec_engine.attach_tactical_adapter(adapter)

        roll_dummy = RolloverEvent(
            trade_date="2026-10-15",
            is_rollover=False,
            old_contract="",
            new_contract="",
            old_open_price=0.0,
            new_open_price=0.0,
            roll_spread=0.0,
            rationale=""
        )
        target = PositionTarget(
            trade_date="2026-10-15",
            target_direction="LONG",
            target_weight=0.2,
            target_lots=10,
            target_nominal_value=300000.0,
            estimated_margin=30000.0,
            margin_utilization=0.03,
            effective_leverage=0.3,
            rationale="宏观日线盲目多头信号"
        )

        exec_engine.execute_next_bar(
            date_str="2026-10-15",
            target=target,
            open_price=2950.0,
            settlement_price=2950.0,
            close_price=2950.0,
            rollover_event=roll_dummy,
            active_contract_code="rb2501"
        )

        # 验证持仓被强制拦截为 0 手，成功守住本金
        self.assertEqual(exec_engine.current_lots, 0)

    def test_04_macro_force_exit(self):
        """测试宏观大系统发生大级别方向逆转时，下达 force_macro_exit 强制清盘重置"""
        adapter = TacticalExecutionAdapter(symbol="hc")
        adapter.current_position_lots = 20
        adapter.macro_direction = "LONG"
        adapter.active_entry_price = 3300.0

        trade = adapter.force_macro_exit(exit_price=3350.0, exit_time="2026-10-16 15:00:00", reason="MACRO_FUNDAMENTALS_TURNED_BEARISH")

        self.assertIsNotNone(trade)
        self.assertEqual(trade.trade_type, "MACRO_FORCE_EXIT")
        self.assertEqual(trade.direction, "FLAT")
        self.assertGreater(trade.pnl, 0.0)
        self.assertEqual(adapter.current_position_lots, 0)
        self.assertEqual(adapter.macro_direction, "FLAT")

    def test_05_execution_engine_tactical_exit(self):
        """测试 ExecutionEngine.execute_tactical_exit 执行日内战术退出与快照修正"""
        exec_engine = ExecutionEngine(initial_capital=10_000_000.0)
        roll_dummy = RolloverEvent(
            trade_date="2026-10-15",
            is_rollover=False,
            old_contract="rb2501",
            new_contract="rb2501",
            old_open_price=3500.0,
            new_open_price=3500.0,
            roll_spread=0.0,
            rationale=""
        )
        target = PositionTarget(
            trade_date="2026-10-15",
            target_direction="LONG",
            target_weight=0.2,
            target_lots=50,
            target_nominal_value=1750000.0,
            estimated_margin=175000.0,
            margin_utilization=0.175,
            effective_leverage=0.175,
            rationale="多头试单"
        )
        snap = exec_engine.execute_next_bar(
            date_str="2026-10-15",
            target=target,
            open_price=3500.0,
            settlement_price=3500.0,
            close_price=3500.0,
            rollover_event=roll_dummy,
            active_contract_code="rb2501"
        )
        self.assertEqual(exec_engine.current_lots, 50)

        # 触发战术退出
        rec = exec_engine.execute_tactical_exit(
            date_str="2026-10-15",
            exit_price=3485.0,
            reason="INITIAL_BREAKOUT_FAILED"
        )
        self.assertIsNotNone(rec)
        self.assertEqual(exec_engine.current_lots, 0)
        self.assertEqual(exec_engine.avg_entry_price, 0.0)
        self.assertEqual(rec.side, "SELL_CLOSE")
        self.assertEqual(rec.quantity, 50)
        
        # 校验快照已被修正
        updated_snap = exec_engine.daily_snapshots[-1]
        self.assertEqual(updated_snap["lots"], 0)
        self.assertEqual(updated_snap["unrealized_pnl"], 0.0)
        self.assertEqual(updated_snap["margin_occupied"], 0.0)
        self.assertEqual(updated_snap["tactical_exit_reason"], "INITIAL_BREAKOUT_FAILED")
        self.assertAlmostEqual(updated_snap["total_equity"], updated_snap["available_cash"])


if __name__ == "__main__":
    unittest.main()

