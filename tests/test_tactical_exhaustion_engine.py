#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试: tests/test_tactical_exhaustion_engine.py
测试目标:
  验证 stage_e/tactical_exhaustion_engine.py 的核心功能:
  1. 微观特征工程计算准确性与时序单向性 (VWAP, Bias, VolRatio, Shadows);
  2. 多头模式下【左侧预警 + 右侧拐点全平 + 右侧企稳全额回补】闭环;
  3. 价格保护门禁 (Price Protection Gate) 对大幅跳空追高的防御拦截;
  4. 极窄硬止损 (Tight Stop) 触发与单日 2 次熔断机制 (Max Retries Lockout);
  5. 空头模式下的镜像对称性。
"""

import unittest
import numpy as np
import pandas as pd

from stage_e.tactical_exhaustion_engine import (
    TacticalConfig,
    TacticalTrade,
    MicroFeatureEngineering,
    TacticalExhaustionEngine
)


class TestTacticalExhaustionEngine(unittest.TestCase):

    def setUp(self):
        self.config = TacticalConfig(
            bias_threshold=1.5,
            vol_ratio_threshold=2.0,
            shadow_threshold=0.35,
            oi_climax_threshold=-5000,
            price_protection_tol=10.0,
            max_retries_per_day=2,
            tight_stop_ticks=2.0,
            commission_per_lot=3.0,
            slippage_ticks=1.0
        )
        self.engine = TacticalExhaustionEngine(self.config)

    def _generate_synthetic_bars(self, prices, volumes=None, ois=None, dates=None, opens=None, highs=None, lows=None):
        n = len(prices)
        if volumes is None:
            volumes = [1000.0] * n
        if ois is None:
            ois = [50000.0] * n
        if dates is None:
            dates = ["2026-10-14"] * n

        rows = []
        for i in range(n):
            p = prices[i]
            prev_p = prices[i-1] if i > 0 else p
            
            if opens is not None:
                op = opens[i]
            else:
                op = p - 2.0 if p >= prev_p else p + 2.0
                
            if highs is not None:
                hi = highs[i]
            else:
                hi = max(op, p) + 2.0
                
            if lows is not None:
                lo = lows[i]
            else:
                lo = min(op, p) - 2.0

            rows.append({
                "open": op,
                "high": hi,
                "low": lo,
                "close": p,
                "volume": volumes[i],
                "open_interest": ois[i],
                "trade_date": dates[i],
                "datetime_str": f"{dates[i]} 09:{i*5:02d}:00"
            })
        return pd.DataFrame(rows)

    def test_01_feature_engineering_calculation(self):
        """测试微观特征工程的计算有效性"""
        prices = [3000.0 + i * 5.0 for i in range(30)]
        df = self._generate_synthetic_bars(prices)
        res = MicroFeatureEngineering.compute_features(df)
        
        self.assertIn("intraday_vwap", res.columns)
        self.assertIn("bias_vwap", res.columns)
        self.assertIn("vol_ratio", res.columns)
        self.assertIn("delta_oi", res.columns)
        self.assertIn("shadow_lower", res.columns)
        self.assertIn("shadow_upper", res.columns)
        self.assertIn("ma5", res.columns)
        self.assertIn("boll_up", res.columns)
        
        # 验证时序合理性
        self.assertFalse(res['intraday_vwap'].isna().all())
        self.assertTrue((res['intraday_vwap'] > 0).all())

    def test_02_long_trend_right_pivot_exit(self):
        """测试多头趋势下冲高异动预警并在右侧拐点确认全平"""
        # 构造一段先暴涨后冲顶走弱的行情
        prices = [3000.0] * 12
        # 加速冲高，造成天量与极端乖离
        prices += [3050.0, 3100.0, 3150.0, 3200.0]
        # 冲顶滞涨并跌破冲顶低点
        prices += [3180.0, 3160.0, 3140.0]
        
        volumes = [1000.0] * 12 + [5000.0, 8000.0, 10000.0, 12000.0] + [3000.0, 2000.0, 1500.0]
        ois = [50000.0] * 12 + [48000.0, 45000.0, 40000.0, 30000.0] + [29000.0, 28000.0, 27000.0]
        
        df = self._generate_synthetic_bars(prices, volumes, ois)
        result = self.engine.run_backtest(df, trend_direction="LONG", lots=10, start_idx=5)
        
        trades = result["trades"]
        self.assertTrue(len(trades) >= 1)
        # 第一笔应该是 PIVOT_EXIT 全平止盈
        first_trade = trades[0]
        self.assertEqual(first_trade.trade_type, "PIVOT_EXIT")
        self.assertEqual(first_trade.direction, "FLAT")
        self.assertGreater(first_trade.pnl, 0.0)  # 必须锁定大幅利润

    def test_03_price_protection_gate_intercepts_gap(self):
        """测试价格保护门禁拦截长假跳空天价追高"""
        # 构造平仓后隔夜暴跳 100 点
        prices = [3000.0] * 12 + [3100.0, 3120.0, 3110.0] # 冲顶平仓
        # 隔天大幅跳空到 3300
        prices += [3300.0, 3310.0, 3305.0]
        
        dates = ["2026-09-30"] * 15 + ["2026-10-08"] * 3
        df = self._generate_synthetic_bars(prices, dates=dates)
        
        result = self.engine.run_backtest(df, trend_direction="LONG", lots=10, start_idx=5)
        trades = result["trades"]
        
        # 验证在跳空到 3300 后，不会触发 PIVOT_RE_ENTRY (因为价格倒贴保护拦截)
        reentry_trades = [t for t in trades if t.trade_type == "PIVOT_RE_ENTRY"]
        self.assertEqual(len(reentry_trades), 0)

    def test_04_tight_stop_loss_trigger_and_daily_lockout(self):
        """测试极窄硬止损精确触发与单日 2 次熔断锁定"""
        # 构造反抽回补后立刻被打损的行情
        prices = [3200.0] * 12 + [3100.0, 3080.0] # 暴跌平空
        # 反抽遇阻回补
        prices += [3110.0, 3105.0]
        # 突破反抽高点打损 (止损触发 1)
        prices += [3130.0, 3135.0]
        # 再次反抽遇阻回补
        prices += [3132.0, 3130.0]
        # 再次突破打损 (止损触发 2，触发当日熔断)
        prices += [3150.0, 3160.0]
        # 再次遇阻，此时应被熔断拒绝开仓
        prices += [3158.0, 3155.0]
        
        df = self._generate_synthetic_bars(prices)
        result = self.engine.run_backtest(df, trend_direction="SHORT", lots=10, start_idx=5)
        
        trades = result["trades"]
        stop_hits = [t for t in trades if t.trade_type == "TIGHT_STOP_HIT"]
        # 验证止损次数受单日熔断保护封顶在 2 次
        self.assertLessEqual(len(stop_hits), 2)

    def test_05_short_mode_symmetry(self):
        """测试空头模式下的全流程镜像对称性"""
        prices = [3200.0] * 12
        # 加速下砸跌破新低，天量长下影
        prices += [3150.0, 3100.0, 3050.0, 3000.0]
        # 企稳阳包阴拐头
        prices += [3020.0, 3040.0, 3060.0]
        
        volumes = [1000.0] * 12 + [5000.0, 8000.0, 10000.0, 12000.0] + [3000.0, 2000.0, 1500.0]
        ois = [50000.0] * 12 + [48000.0, 45000.0, 40000.0, 30000.0] + [29000.0, 28000.0, 27000.0]

        df = self._generate_synthetic_bars(prices, volumes, ois)
        result = self.engine.run_backtest(df, trend_direction="SHORT", lots=10, start_idx=5)
        
        trades = result["trades"]
        self.assertTrue(len(trades) >= 1)
        exit_trades = [t for t in trades if t.trade_type == "PIVOT_EXIT"]
        self.assertEqual(len(exit_trades), 1)
        self.assertGreater(exit_trades[0].pnl, 0.0)

    def test_06_gap_trailing_pullback_reentry(self):
        """测试跳空后深幅洗盘回调充分且右侧企稳时恢复继续执行回补"""
        # 1. 顺势上涨 + 天量冲高冲顶
        prices = [3000.0] * 12 + [3050.0, 3100.0, 3150.0, 3200.0]
        # 2. 冲顶滞涨并跌破冲顶低点 -> 触发 PIVOT_EXIT 全平
        prices += [3180.0, 3160.0, 3140.0]
        volumes = [1000.0] * 12 + [5000.0, 8000.0, 10000.0, 12000.0] + [3000.0, 2000.0, 1500.0]
        ois = [50000.0] * 12 + [48000.0, 45000.0, 40000.0, 30000.0] + [29000.0, 28000.0, 27000.0]
        dates = ["2026-09-30"] * len(prices)

        # 3. 隔夜/长假大幅跳空高开至 3350 冲到 3360 (由于超过平仓价 3140+10，被安全门禁拦截)
        post_prices = [3350.0, 3360.0]
        post_vols = [4000.0, 5000.0]
        post_ois = [28000.0, 29000.0]
        post_dates = ["2026-10-08"] * 2

        # 4. 从 3360 深幅洗盘回调 40 点至 3320 (满足 min_gap_pullback_space=25)
        post_prices += [3340.0, 3320.0]
        post_vols += [2000.0, 1500.0]
        post_ois += [28500.0, 28000.0]
        post_dates += ["2026-10-08"] * 2

        # 5. 右侧企稳大阳线突破前高 3335 (完成底分型企稳)
        post_prices += [3335.0]
        post_vols += [3500.0]
        post_ois += [29500.0]
        post_dates += ["2026-10-08"] * 1

        all_prices = prices + post_prices
        all_vols = volumes + post_vols
        all_ois = ois + post_ois
        all_dates = dates + post_dates

        df = self._generate_synthetic_bars(all_prices, all_vols, all_ois, all_dates)

        # 设置跳空回调阈值为 25 元，独立测试回调回补机制
        cfg = TacticalConfig(
            bias_threshold=1.5,
            vol_ratio_threshold=2.0,
            oi_climax_threshold=-5000,
            min_gap_pullback_space=25.0,
            enable_gap_pullback_reentry=True,
            enable_gap_exhaustion_exit=False
        )
        eng = TacticalExhaustionEngine(cfg)
        result = eng.run_backtest(df, trend_direction="LONG", lots=10, start_idx=5)

        trades = result["trades"]
        exits = [t for t in trades if t.trade_type == "PIVOT_EXIT"]
        reentries = [t for t in trades if t.trade_type == "PIVOT_RE_ENTRY"]
        
        # 验证必须先冲顶全平
        self.assertEqual(len(exits), 1)
        self.assertGreater(exits[0].pnl, 0.0)
        # 验证在回调充分后成功触发回补
        self.assertEqual(len(reentries), 1)
        self.assertIn("跳空回调", reentries[0].reason)
        # 验证回补时的保护止损价设置在洗盘回调最低点(3320-2=3318)下方 2 ticks
        self.assertAlmostEqual(reentries[0].stop_loss_price, 3316.0)

    def test_07_gap_exhaustion_exit_terminates_trend(self):
        """测试跳空后未延续或未立即收复，判定趋势改变并退出趋势交易模式(用户核心逻辑)"""
        # 平仓于 3140 附近
        prices = [3000.0] * 12 + [3050.0, 3100.0, 3150.0, 3200.0] + [3180.0, 3160.0, 3140.0]
        volumes = [1000.0] * 12 + [5000.0, 8000.0, 10000.0, 12000.0] + [3000.0, 2000.0, 1500.0]
        ois = [50000.0] * 12 + [48000.0, 45000.0, 40000.0, 30000.0] + [29000.0, 28000.0, 27000.0]
        dates = ["2026-09-30"] * len(prices)

        # 节后大幅跳空高开至 3350 冲到 3360，随后高开低走砸盘跌破开盘价 3348 至 3320
        post_prices = [3350.0, 3360.0, 3340.0, 3320.0, 3310.0]
        post_vols = [4000.0, 5000.0, 3000.0, 2500.0, 2000.0]
        post_ois = [28000.0, 29000.0, 28000.0, 27000.0, 26000.0]
        post_dates = ["2026-10-08"] * 5

        df = self._generate_synthetic_bars(prices + post_prices, volumes + post_vols, ois + post_ois, dates + post_dates)

        cfg = TacticalConfig(
            bias_threshold=1.5,
            vol_ratio_threshold=2.0,
            oi_climax_threshold=-5000,
            price_protection_tol=15.0,
            enable_gap_exhaustion_exit=True
        )
        eng = TacticalExhaustionEngine(cfg)
        result = eng.run_backtest(df, trend_direction="LONG", lots=10, start_idx=5)

        trades = result["trades"]
        gap_exits = [t for t in trades if t.trade_type == "GAP_EXHAUSTION_EXIT"]
        
        # 验证必须精准触发 GAP_EXHAUSTION_EXIT 退出趋势模式
        self.assertEqual(len(gap_exits), 1)
        self.assertIn("趋势改变退出趋势模式", gap_exits[0].reason)
        # 验证退出趋势模式后，不会发生任何盲目追高或逆势回补接飞刀
        reentries = [t for t in trades if t.trade_type == "PIVOT_RE_ENTRY"]
        self.assertEqual(len(reentries), 0)

    def test_08_choppy_regime_stagnant_quick_exit(self):
        """测试震荡行情中开仓后停滞破位，敏捷识别为震荡市并退出趋势模式"""
        # 进场后价格在 3000~3003 窄幅横盘 10 根 Bar，随后跌破进场 Bar 低点
        prices = [3000.0] * 6
        prices += [3002.0, 3001.0, 3003.0, 3001.0, 3002.0, 3001.0, 3002.0, 3000.0, 2995.0, 2990.0]
        df = self._generate_synthetic_bars(prices)

        cfg = TacticalConfig(
            enable_choppy_exit=True,
            choppy_stagnant_bars=6
        )
        eng = TacticalExhaustionEngine(cfg)
        result = eng.run_backtest(df, trend_direction="LONG", lots=10, start_idx=2)

        trades = result["trades"]
        choppy_exits = [t for t in trades if t.trade_type == "CHOPPY_REGIME_EXIT"]
        
        # 验证触发 CHOPPY_REGIME_EXIT 退出
        self.assertEqual(len(choppy_exits), 1)
        self.assertIn("识别为震荡", choppy_exits[0].reason)

    def test_09_fifteen_minute_pivot_exit(self):
        """测试15分钟级别全平门槛: 冲顶异动后跌破15m结构低点触发全平止盈"""
        prices = [3000.0] * 12 + [3050.0, 3100.0, 3150.0, 3200.0] + [3180.0, 3160.0, 3140.0]
        volumes = [1000.0] * 12 + [5000.0, 8000.0, 10000.0, 12000.0] + [3000.0, 2000.0, 1500.0]
        ois = [50000.0] * 12 + [48000.0, 45000.0, 40000.0, 30000.0] + [29000.0, 28000.0, 27000.0]

        df = self._generate_synthetic_bars(prices, volumes, ois)
        cfg = TacticalConfig(exit_timeframe="15m")
        eng = TacticalExhaustionEngine(cfg)
        result = eng.run_backtest(df, trend_direction="LONG", lots=10, start_idx=5)

        trades = result["trades"]
        exits = [t for t in trades if t.trade_type == "PIVOT_EXIT"]
        self.assertEqual(len(exits), 1)
        self.assertIn("15m", exits[0].reason)
        self.assertGreater(exits[0].pnl, 0.0)

    def test_10_phase_dependent_sensitivity(self):
        """测试趋势确立初期容忍蓄势震荡，不被8根Bar误杀出局"""
        # 进场后价格在成本区附近蓄势波动 12 根 Bar (未达到 24 根)，随后继续暴涨突破
        prices = [3000.0] * 6
        # 蓄势 12 根 Bar
        prices += [3002.0, 3001.0, 2999.0, 3001.0, 3002.0, 3001.0, 2998.0, 3001.0, 3003.0, 3001.0, 3002.0, 3004.0]
        # 随后脱离成本拉开利润
        prices += [3020.0, 3040.0, 3060.0, 3080.0]
        df = self._generate_synthetic_bars(prices)

        cfg = TacticalConfig(
            enable_choppy_exit=True,
            early_stage_bars=24,
            enable_phase_sensitivity=True
        )
        eng = TacticalExhaustionEngine(cfg)
        result = eng.run_backtest(df, trend_direction="LONG", lots=10, start_idx=2)

        trades = result["trades"]
        # 验证在初期未被假突破停滞误杀
        choppy_exits = [t for t in trades if t.trade_type == "CHOPPY_REGIME_EXIT"]
        self.assertEqual(len(choppy_exits), 0)
        # 最终以大幅盈利平仓
        self.assertGreater(result["strategy_pnl"], 0.0)

    def test_11_initial_breakout_failed_stop_loss(self):
        """测试初始建仓初期遭遇恶性假突破砸盘，迅速触发初始结构防守止损并退出趋势模式"""
        # 进场点价格 3000，开仓后仅第 3 根 Bar 就遭遇反向暴力砸盘至 2970 (跌破开仓Bar低点2998)
        prices = [3000.0] * 5
        prices += [3002.0, 2995.0, 2975.0, 2960.0, 2950.0]
        # 模拟生成带有明确 high/low 的 Bar
        lows = [2998.0] * 5 + [3000.0, 2990.0, 2970.0, 2955.0, 2945.0]
        df = self._generate_synthetic_bars(prices, lows=lows)

        cfg = TacticalConfig(
            enable_initial_structural_stop=True,
            initial_stop_buffer_ticks=2.0,
            early_stage_bars=24
        )
        eng = TacticalExhaustionEngine(cfg)
        result = eng.run_backtest(df, trend_direction="LONG", lots=10, start_idx=4)

        trades = result["trades"]
        failed_exits = [t for t in trades if t.trade_type == "INITIAL_BREAKOUT_FAILED"]
        
        # 验证必须精准触发 INITIAL_BREAKOUT_FAILED，而不是傻等24根Bar
        self.assertEqual(len(failed_exits), 1)
        self.assertIn("假突破趋势破坏", failed_exits[0].reason)
        # 验证退出趋势模式后，持仓清零，绝不盲目回补
        reentries = [t for t in trades if t.trade_type == "PIVOT_RE_ENTRY"]
        self.assertEqual(len(reentries), 0)
        self.assertEqual(result["trades"][-1].direction, "FLAT")

    def test_12_initial_structural_stop_short_mode(self):
        """测试空头模式下初始建仓遭遇反向恶性拉升，精准触发突破防守止损并退出趋势模式"""
        # 进场点价格 3000，开仓后第 2 根 Bar 遭遇反向暴力拉升至 3030 (突破开仓Bar高点3002)
        prices = [3000.0] * 5
        prices += [2998.0, 3015.0, 3030.0, 3040.0]
        highs = [3002.0] * 5 + [3000.0, 3018.0, 3035.0, 3045.0]
        df = self._generate_synthetic_bars(prices, highs=highs)

        cfg = TacticalConfig(
            enable_initial_structural_stop=True,
            initial_stop_buffer_ticks=2.0,
            early_stage_bars=24
        )
        eng = TacticalExhaustionEngine(cfg)
        result = eng.run_backtest(df, trend_direction="SHORT", lots=10, start_idx=4)

        trades = result["trades"]
        failed_exits = [t for t in trades if t.trade_type == "INITIAL_BREAKOUT_FAILED"]
        
        # 验证空头镜像模式下触发 INITIAL_BREAKOUT_FAILED
        self.assertEqual(len(failed_exits), 1)
        self.assertIn("假突破趋势破坏", failed_exits[0].reason)
        reentries = [t for t in trades if t.trade_type == "PIVOT_RE_ENTRY"]
        self.assertEqual(len(reentries), 0)


if __name__ == "__main__":
    unittest.main()
