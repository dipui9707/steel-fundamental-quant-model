#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试: tests/test_stage_e_engine.py
功能: 阶段 E 回测与模拟交易系统全组件白盒与集成测试
覆盖:
  1. 信号生成与多维前置过滤 (SignalGenerator);
  2. 风控防火墙绝对否决权与冷却期 (RiskFilterAdapter);
  3. 仓位预算与置信度动态缩放 (PositionSizer);
  4. 螺纹主力 01-05-10 换月移仓机制 (ContractRolloverManager);
  5. 期货盯市撮合与会计恒等式 (ExecutionEngine);
  6. 量化绩效与风险归因数学准确性 (PerformanceAnalyzer);
  7. 交易台账 CSV 导出规范性 (TradeRecorder);
  8. 端到端多策略回测调度 (BacktestEngine);
  9. 极端危机场景 (2024-0924 暴涨) 防火墙截断断言。
"""

import unittest
import os
import sys
import dataclasses
import pandas as pd
import numpy as np
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_e.signal_generator import SignalGenerator, TradingSignal
from stage_e.risk_filter import RiskFilterAdapter, VettedSignal
from stage_e.position_sizer import PositionSizer, PositionTarget
from stage_e.contract_rollover import ContractRolloverManager, RolloverEvent
from stage_e.execution_engine import ExecutionEngine, TradeRecord
from stage_e.performance_analyzer import PerformanceAnalyzer
from stage_e.trade_recorder import TradeRecorder, CSV_COLUMNS
from stage_e.backtest_engine import BacktestEngine, BacktestResult


class TestStageEEngine(unittest.TestCase):

    def setUp(self):
        # 构造测试用的点时数据行
        self.state_bull = pd.Series({
            "fundamental_direction": "Bullish",
            "fundamental_score": 35.0,
            "confidence_score": 75.0,
            "spot_confirmation": "Confirmed",
            "macro_regime": "NORMAL",
            "macro_override_intensity": 0.0,
            "divergence_status": "None",
            "divergence_accumulated_area": 0.0,
            "consecutive_divergence_days": 0,
        })
        self.state_bear = pd.Series({
            "fundamental_direction": "Bearish",
            "fundamental_score": -40.0,
            "confidence_score": 68.0,
            "spot_confirmation": "Divergent",
            "macro_regime": "NORMAL",
            "macro_override_intensity": 0.0,
            "divergence_status": "None",
            "divergence_accumulated_area": 0.0,
            "consecutive_divergence_days": 0,
        })
        self.feature_bull = pd.Series({
            "rb_open": 3500.0,
            "rb_high": 3550.0,
            "rb_low": 3490.0,
            "rb_close": 3540.0,
            "ma_20": 3480.0,
            "ma_5": 3520.0,
            "pct_basis_tier3": 0.65,
            "vol_shock_ratio": 1.1,
            "squeeze_index": 0.5,
            "dominant_leader_type": "FINISHED_STEEL_DEMAND",
            "cost_push_spread_5d": 0.005,
            "data_freshness_ratio": 0.95,
        })
        self.feature_bear = pd.Series({
            "rb_open": 3500.0,
            "rb_high": 3510.0,
            "rb_low": 3440.0,
            "rb_close": 3450.0,
            "ma_20": 3520.0,
            "ma_5": 3470.0,
            "pct_basis_tier3": 0.30,
            "vol_shock_ratio": 1.2,
            "squeeze_index": 0.2,
            "dominant_leader_type": "FINISHED_STEEL_WEAK",
            "cost_push_spread_5d": -0.005,
            "data_freshness_ratio": 0.95,
        })

    def test_01_signal_generator_logic(self):
        """测试策略信号生成与前置过滤器"""
        gen = SignalGenerator(confidence_threshold=40.0)

        # 1. 基准买入持有
        sig_bench = gen.generate_signal("2024-03-15", self.state_bear, self.feature_bear, strategy_mode="BENCHMARK_BUY_HOLD")
        self.assertEqual(sig_bench.direction, "LONG")
        self.assertEqual(sig_bench.strength, 1.0)

        # 2. 纯基本面 (无动量与现货确认)
        sig_raw = gen.generate_signal("2024-03-15", self.state_bull, self.feature_bull, strategy_mode="RAW_FUNDAMENTAL")
        self.assertEqual(sig_raw.direction, "LONG")

        # 3. 核心量化策略多头触发
        sig_core_long = gen.generate_signal("2024-03-15", self.state_bull, self.feature_bull, strategy_mode="QUANT_CORE")
        self.assertEqual(sig_core_long.direction, "LONG")
        self.assertTrue(sig_core_long.spot_confirmed)
        self.assertTrue(sig_core_long.momentum_confirmed)

        # 4. 核心量化策略空头触发
        sig_core_short = gen.generate_signal("2024-03-15", self.state_bear, self.feature_bear, strategy_mode="QUANT_CORE")
        self.assertEqual(sig_core_short.direction, "SHORT")

        # 5. 置信度不足降级过滤
        low_conf_state = self.state_bull.copy()
        low_conf_state["confidence_score"] = 30.0
        sig_low_conf = gen.generate_signal("2024-03-15", low_conf_state, self.feature_bull, strategy_mode="QUANT_CORE")
        self.assertEqual(sig_low_conf.direction, "FLAT")
        self.assertIn("模型置信度不足", sig_low_conf.rationale)

    def test_02_risk_filter_veto_power(self):
        """测试风控防火墙的绝对否决权"""
        adapter = RiskFilterAdapter(cooling_days_after_liquidation=2)
        gen = SignalGenerator()
        raw_sig = gen.generate_signal("2024-03-15", self.state_bear, self.feature_bear, strategy_mode="QUANT_CORE")
        self.assertEqual(raw_sig.direction, "SHORT")

        # 场景 A: 原料逼仓传染 (squeeze_index=3.5, leader=RAW_MATERIAL_SHOCK) -> 必须被拦截禁止做空
        squeeze_feat = self.feature_bear.copy()
        squeeze_feat["squeeze_index"] = 3.5
        squeeze_feat["cost_push_spread_5d"] = 0.025
        squeeze_feat["dominant_leader_type"] = "RAW_MATERIAL_SHOCK"

        vetted = adapter.vet_signal("2024-03-15", raw_sig, self.state_bear, squeeze_feat, current_holding_direction="FLAT")
        self.assertEqual(vetted.vetted_direction, "FLAT")
        self.assertTrue(vetted.is_vetoed)
        self.assertEqual(vetted.firewall_status, "RESTRICT_CLOSE_ONLY")

        # 场景 B: 极端反向波动率脉冲 (vol_shock_ratio=3.0, ret_1d=+3.5%) -> 触发 FORCED_LIQUIDATION 并进入冷却期
        spike_feat = self.feature_bear.copy()
        spike_feat["vol_shock_ratio"] = 3.0
        spike_feat["rb_ret_1d"] = 0.035
        spike_feat["rb_close"] = 3600.0
        spike_feat["ma_20"] = 3450.0  # 突破 MA20 超过 1.5%

        vetted_spike = adapter.vet_signal("2024-09-24", raw_sig, self.state_bear, spike_feat, current_holding_direction="SHORT")
        self.assertEqual(vetted_spike.vetted_direction, "FLAT")
        self.assertEqual(vetted_spike.firewall_status, "FORCED_LIQUIDATION")

        # 验证次日自动进入冷却期
        vetted_next_day = adapter.vet_signal("2024-09-25", raw_sig, self.state_bear, self.feature_bear, current_holding_direction="FLAT")
        self.assertEqual(vetted_next_day.vetted_direction, "FLAT")
        self.assertIn("冷却期", vetted_next_day.veto_reason)

    def test_03_position_sizer_math(self):
        """测试仓位管理、置信度动态加权与可用资金安全垫"""
        sizer = PositionSizer(contract_multiplier=10, default_margin_rate=0.10, max_base_leverage=1.0, cash_buffer_ratio=0.20)
        raw_sig = TradingSignal(
            trade_date="2024-03-15",
            symbol="RB",
            direction="LONG",
            strength=0.8,
            confidence_score=80.0,
            spot_confirmed=True,
            momentum_confirmed=True,
            strategy_name="QUANT_CORE",
            rationale="多头顺势",
        )
        vetted = VettedSignal(
            trade_date="2024-03-15",
            vetted_direction="LONG",
            target_leverage_cap=1.0,
            firewall_status="PASS",
            is_vetoed=False,
            veto_reason="",
            raw_signal=raw_sig,
            firewall_decision=None,
        )

        equity = 10_000_000.0  # 1000 万元
        price = 3500.0  # 3500 元/吨, 每手 10 吨 = 35,000 元/手
        target = sizer.calculate_position_target(vetted, current_equity=equity, current_price=price)

        self.assertEqual(target.target_direction, "LONG")
        self.assertGreater(target.target_lots, 0)
        # 杠杆必须 <= 1.0
        self.assertLessEqual(target.effective_leverage, 1.0)
        # 保证金占用不可突破 80% (现金缓冲 20%)
        self.assertLessEqual(target.margin_utilization, 0.80)

        # 当防火墙输出 CAUTION 时 (cap=0.70)
        vetted_caution = VettedSignal(
            trade_date="2024-03-15",
            vetted_direction="LONG",
            target_leverage_cap=0.70,
            firewall_status="CAUTION",
            is_vetoed=True,
            veto_reason="轻度背离",
            raw_signal=raw_sig,
            firewall_decision=None,
        )
        target_caution = sizer.calculate_position_target(vetted_caution, current_equity=equity, current_price=price)
        self.assertLessEqual(target_caution.effective_leverage, 0.70)

    def test_04_contract_rollover_manager(self):
        """测试螺纹主力 01-05-10 换月识别"""
        mgr = ContractRolloverManager(symbol="rb")
        full_map = mgr.get_full_map()
        self.assertFalse(full_map.empty)
        self.assertIn("contract_code", full_map.columns)
        self.assertIn("is_rollover", full_map.columns)

        # 换月由上一日实际持仓量决定，不固定历史日历。
        day = full_map[full_map.is_rollover].index[-1]
        event = mgr.check_rollover_event(day)
        self.assertTrue(event.is_rollover)
        self.assertNotEqual(event.old_contract, event.new_contract)
        self.assertAlmostEqual(event.roll_spread, event.new_open_price-event.old_open_price)
        self.assertLess(full_map.loc[day, 'selection_date'], day)

    def test_05_execution_engine_accounting_identity(self):
        """测试期货撮合与账户盯市会计恒等式"""
        exec_eng = ExecutionEngine(initial_capital=10_000_000.0, contract_multiplier=10, slippage_ticks=1.0, commission_rate=0.0001, margin_rate=0.10)
        target_buy = PositionTarget(
            trade_date="2024-03-15",
            target_direction="LONG",
            target_weight=0.5,
            target_lots=100,
            target_nominal_value=3_500_000.0,
            estimated_margin=350_000.0,
            margin_utilization=0.035,
            effective_leverage=0.35,
            rationale="开多 100 手",
        )
        no_roll = RolloverEvent("2024-03-15", False, "rb2405", "rb2405", 3500.0, 3500.0, 0.0, "")

        # T+1 日开盘买入 100 手
        snap1 = exec_eng.execute_next_bar(
            date_str="2024-03-15",
            target=target_buy,
            open_price=3500.0,
            settlement_price=3520.0,
            close_price=3525.0,
            rollover_event=no_roll,
            active_contract_code="rb2405",
        )

        self.assertEqual(exec_eng.current_lots, 100)
        # 买入成交价含 1 tick 滑点: 3500 + 1.0 = 3501.0
        self.assertEqual(exec_eng.avg_entry_price, 3501.0)
        # 验证盯市会计恒等式: 动态权益 == 可用资金 + 占用保证金
        self.assertAlmostEqual(snap1["total_equity"], snap1["available_cash"] + snap1["margin_occupied"], places=2)

        # 次日清仓平多
        target_flat = PositionTarget(
            trade_date="2024-03-18",
            target_direction="FLAT",
            target_weight=0.0,
            target_lots=0,
            target_nominal_value=0.0,
            estimated_margin=0.0,
            margin_utilization=0.0,
            effective_leverage=0.0,
            rationale="平仓",
        )
        snap2 = exec_eng.execute_next_bar(
            date_str="2024-03-18",
            target=target_flat,
            open_price=3550.0,
            settlement_price=3550.0,
            close_price=3550.0,
            rollover_event=no_roll,
            active_contract_code="rb2405",
        )

        self.assertEqual(exec_eng.current_lots, 0)
        self.assertAlmostEqual(snap2["total_equity"], snap2["available_cash"], places=2)
        # 验证生成了交易流水记录
        trades = exec_eng.get_trade_records_df()
        self.assertEqual(len(trades), 1)
        self.assertEqual(trades.iloc[0]["side"], "SELL_CLOSE")
        self.assertGreater(trades.iloc[0]["pnl"], 0)

    def test_06_performance_analyzer_math(self):
        """测试绩效指标计算准确性"""
        analyzer = PerformanceAnalyzer(risk_free_rate=0.02, trading_days_per_year=250)
        # 构造一个 250 天的模拟净值序列
        dates = pd.date_range("2024-01-01", periods=250, freq="B").strftime("%Y-%m-%d").tolist()
        np.random.seed(42)
        daily_returns = np.random.normal(0.0005, 0.01, 250)
        cum_nav = np.cumprod(1.0 + daily_returns)
        equity = 10_000_000.0 * cum_nav

        eq_df = pd.DataFrame({
            "date": dates,
            "total_equity": equity,
            "daily_return": daily_returns,
            "net_asset_value": cum_nav,
            "cumulative_fees": np.linspace(100, 5000, 250),
            "cumulative_slippage": np.linspace(50, 2500, 250),
            "effective_leverage": np.ones(250) * 0.5,
        })
        trades_df = pd.DataFrame({
            "trade_id": ["T1", "T2", "T3"],
            "pnl": [50000.0, -20000.0, 30000.0],
        })

        metrics = analyzer.analyze_equity_and_trades(eq_df, trades_df, "Test_Strategy")
        self.assertIn("cagr_pct", metrics)
        self.assertIn("sharpe_ratio", metrics)
        self.assertIn("max_drawdown_pct", metrics)
        self.assertIn("win_rate_pct", metrics)
        self.assertAlmostEqual(metrics["win_rate_pct"], 66.67, places=1)
        self.assertGreater(metrics["profit_factor"], 1.0)

    def test_07_trade_recorder_csv_schema(self):
        """测试交易台账输出结构符合项目规范"""
        test_csv = BASE_DIR / "交易" / "test_sim_trades.csv"
        recorder = TradeRecorder(target_csv_path=str(test_csv))
        sample_trades = pd.DataFrame([{
            "trade_id": "TRD_20240315_001",
            "prediction_id": "PRED_20240315_RB",
            "contract": "rb2405",
            "side": "SELL_CLOSE",
            "quantity": 100,
            "entry_time": "2024-03-10",
            "entry_price": 3450.0,
            "exit_time": "2024-03-15",
            "exit_price": 3520.0,
            "fees": 1200.0,
            "risk_plan": "TEST",
            "execution_deviation": 1.0,
            "note": "测试单",
        }])

        p = recorder.export_trade_records(sample_trades, overwrite=True)
        self.assertTrue(os.path.exists(p))
        df_read = pd.read_csv(p)
        for col in CSV_COLUMNS:
            self.assertIn(col, df_read.columns)
        # 清理测试文件
        if os.path.exists(p):
            os.remove(p)

    def test_08_backtest_slice_end_to_end(self):
        """端到端切片回测验证 (抽样 40 个交易日)"""
        feat_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
        state_path = BASE_DIR / "数据" / "状态" / "阶段C_全景状态矩阵.parquet"

        self.assertTrue(feat_path.exists())
        self.assertTrue(state_path.exists())

        feat_df = pd.read_parquet(feat_path).iloc[-50:].copy()
        state_df = pd.read_parquet(state_path).iloc[-50:].copy()

        engine = BacktestEngine(
            features_df=feat_df,
            state_matrix=state_df,
            symbol="rb",
            initial_capital=10_000_000.0,
        )

        res = engine.run_backtest(strategy_mode="QUANT_CORE", enable_firewall=True)
        self.assertIsInstance(res, BacktestResult)
        self.assertEqual(len(res.equity_df), len(feat_df))
        self.assertFalse(res.vetted_signals_df.empty)
        self.assertGreater(res.performance["final_equity"], 0)

    def test_09_extreme_crisis_2024_0924_interception(self):
        """测试 2024-0924 真实历史极端暴涨日被防火墙斩仓熔断"""
        feat_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
        state_path = BASE_DIR / "数据" / "状态" / "阶段C_全景状态矩阵.parquet"

        feat_df = pd.read_parquet(feat_path)
        state_df = pd.read_parquet(state_path)

        # 检查 2024-09-24 当天
        dt = "2024-09-24"
        self.assertIn(dt, feat_df.index)
        self.assertIn(dt, state_df.index)

        s_row = state_df.loc[dt]
        f_row = feat_df.loc[dt]

        # 模拟模型此前看空
        from stage_c.risk_firewall import RiskControlFirewall
        firewall = RiskControlFirewall()
        decision = firewall.evaluate(s_row, f_row, position_intent="short")
        self.assertEqual(decision.status, "FORCED_LIQUIDATION")
        self.assertEqual(decision.action, "LIQUIDATE_IMMEDIATELY")
        self.assertEqual(decision.max_allowable_leverage, 0.0)

    def test_10_accounting_identity_throughout_backtest(self):
        """全流程验证动态权益 ≡ 可用资金 + 占用保证金"""
        feat_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
        state_path = BASE_DIR / "数据" / "状态" / "阶段C_全景状态矩阵.parquet"

        feat_df = pd.read_parquet(feat_path).iloc[-30:].copy()
        state_df = pd.read_parquet(state_path).iloc[-30:].copy()

        engine = BacktestEngine(features_df=feat_df, state_matrix=state_df, initial_capital=10_000_000.0)
        res = engine.run_backtest(strategy_mode="QUANT_CORE", enable_firewall=True)

        eq_df = res.equity_df
        for _, row in eq_df.iterrows():
            total = float(row["total_equity"])
            cash = float(row["available_cash"])
            margin = float(row["margin_occupied"])
            self.assertAlmostEqual(total, cash + margin, places=2)

    def test_11_max_capital_utilization_50pct(self):
        """测试将最高资金利用率提升至 50% 时的手数、保证金占用与上限控制"""
        sizer = PositionSizer(
            contract_multiplier=10,
            default_margin_rate=0.10,
            max_margin_utilization=0.50,
        )
        raw_sig = TradingSignal(
            trade_date="2024-03-15",
            symbol="RB",
            direction="LONG",
            strength=1.0,
            confidence_score=90.0,
            spot_confirmed=True,
            momentum_confirmed=True,
            strategy_name="QUANT_CORE",
            rationale="强烈看多",
        )
        vetted = VettedSignal(
            trade_date="2024-03-15",
            vetted_direction="LONG",
            target_leverage_cap=1.0,
            firewall_status="PASS",
            is_vetoed=False,
            veto_reason="",
            raw_signal=raw_sig,
            firewall_decision=None,
        )
        equity = 10_000_000.0
        price = 3500.0  # lot_margin = 3500 * 10 * 0.10 = 3500 元
        target = sizer.calculate_position_target(vetted, current_equity=equity, current_price=price)

        self.assertEqual(target.target_direction, "LONG")
        # 验证最高资金利用率在 50% 左右 (45% ~ 50%)
        self.assertAlmostEqual(target.margin_utilization, 0.50, delta=0.05)
        # 验证保证金占用在 500 万左右
        self.assertAlmostEqual(target.estimated_margin, 5_000_000.0, delta=500_000.0)
        self.assertLessEqual(target.margin_utilization, 0.5001)

    def test_12_anti_chasing_valuation_safety_gate(self):
        """测试基差与估值安全垫门禁: 升水且钢厂暴利时一票否决追高"""
        sig_gen = SignalGenerator(confidence_threshold=40.0)
        state_row = pd.Series({
            "fundamental_direction": "Bullish",
            "fbs_score": 35.0,
            "confidence_score": 75.0,
            "spot_confirmation": "Confirmed",
            "macro_regime": "NORMAL",
            "macro_override_intensity": 0.0,
            "cost_boundary_regime": "合理利润运行",
        })
        # 构造高升水 (Contango, pct_basis=0.20) 且 钢厂暴利 (pct_vmm=0.85) 的高位盘面
        feature_row = pd.Series({
            "rb_close": 4000.0,
            "ma_20": 3800.0,  # 涨离均线超过 5%
            "ma_5": 3950.0,
            "pct_basis_tier3": 0.20,  # 严重升水
            "pct_virtual_mill_margin": 0.85,  # 暴利
            "profit_bf": 500.0,
        })
        sig = sig_gen.generate_signal("2024-05-10", state_row, feature_row, strategy_mode="QUANT_CORE")
        self.assertEqual(sig.direction, "FLAT")
        self.assertIn("安全垫一票否决追多", sig.rationale)

    def test_13_clean_slippage_accounting(self):
        """测试滑点单次计入成本，绝不发生双重扣除"""
        engine = ExecutionEngine(initial_capital=100_000.0, slippage_ticks=1.0, commission_rate=0.0)
        target_long = PositionTarget("2024-01-02", "LONG", 1.0, 10, 300000.0, 30000.0, 0.3, 3.0, "test")
        dummy_roll = RolloverEvent("2024-01-02", False, "", "", 0.0, 0.0, 0.0, "")
        # 开多 10 手于 3000 (成交价 3001)
        engine.execute_next_bar("2024-01-02", target_long, open_price=3000.0, settlement_price=3000.0, close_price=3000.0,
                                rollover_event=dummy_roll, active_contract_code="rb2405")
        snap1 = engine.daily_snapshots[-1]
        self.assertEqual(snap1["total_equity"], 99900.0)  # 仅亏 1 tick 开仓滑点 (100元)

        # 平仓 10 手于 3000 (成交价 2999)
        target_flat = PositionTarget("2024-01-03", "FLAT", 0.0, 0, 0.0, 0.0, 0.0, 0.0, "test")
        dummy_roll2 = RolloverEvent("2024-01-03", False, "", "", 0.0, 0.0, 0.0, "")
        engine.execute_next_bar("2024-01-03", target_flat, open_price=3000.0, settlement_price=3000.0, close_price=3000.0,
                                rollover_event=dummy_roll2, active_contract_code="rb2405")
        snap2 = engine.daily_snapshots[-1]
        self.assertEqual(snap2["total_equity"], 99800.0)  # 仅亏 2 tick 双边滑点 (200元)
        self.assertEqual(snap2["cumulative_realized_pnl"], -200.0)
        self.assertEqual(snap2["cumulative_fees"], 0.0)  # 佣金为0，手续费未重复包含滑点
        self.assertEqual(snap2["cumulative_slippage"], 200.0)

    def test_14_cost_push_sustained_long_activation(self):
        """测试持续型成本推升顺势做多: 原料大涨+现货跟涨(基差坚挺)+出库正常时，激活做多"""
        sig_gen = SignalGenerator(confidence_threshold=40.0)
        state_row = pd.Series({
            "fundamental_direction": "Neutral",
            "fbs_score": -5.0,
            "confidence_score": 50.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "RAW_MATERIAL_SHOCK",
            "cost_boundary_regime": "合理利润运行",
        })
        feature_row = pd.Series({
            "rb_close": 3700.0,
            "ma_20": 3680.0,
            "ma_5": 3695.0,
            "pct_basis_tier3_1y": 0.65,  # 现货跟涨坚挺
            "pct_flow_hz_outflow": 0.50,  # 出库健康
            "cost_push_spread_5d": 0.025,  # 原料推升
            "dominant_leader_type": "RAW_MATERIAL_SHOCK",
            "cost_bf": 3750.0,
            "cost_cash_floor": 3500.0,
        })
        sig = sig_gen.generate_signal("2023-11-06", state_row, feature_row, strategy_mode="QUANT_CORE")
        self.assertEqual(sig.direction, "LONG")
        self.assertIn("成本推升顺势买入", sig.rationale)

    def test_15_cost_push_false_breakout_veto(self):
        """测试假突破型成本推升一票否决: 原料暴涨但现货拒绝买账(深贴水)时，一票否决追多"""
        sig_gen = SignalGenerator(confidence_threshold=40.0)
        state_row = pd.Series({
            "fundamental_direction": "Bullish",
            "fbs_score": 20.0,
            "confidence_score": 50.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "RAW_MATERIAL_SHOCK",
            "cost_boundary_regime": "合理利润运行",
        })
        feature_row = pd.Series({
            "rb_close": 3800.0,
            "ma_20": 3780.0,
            "ma_5": 3790.0,
            "pct_basis_tier3_1y": 0.15,  # 现货严重贴水拒绝买单
            "pct_flow_hz_outflow": 0.20,
            "cost_push_spread_5d": 0.035,  # 原料暴涨
            "dominant_leader_type": "RAW_MATERIAL_SHOCK",
            "cost_bf": 3750.0,
            "cost_cash_floor": 3500.0,
        })
        sig = sig_gen.generate_signal("2024-05-22", state_row, feature_row, strategy_mode="QUANT_CORE")
        self.assertEqual(sig.direction, "FLAT")
        self.assertIn("一票否决追多", sig.rationale)

    def test_16_raw_material_squeeze_short_veto(self):
        """测试原料挤仓禁空保护: 成材表需虽弱，但遭遇原料强力推升时一票否决做空"""
        sig_gen = SignalGenerator(confidence_threshold=40.0)
        state_row = pd.Series({
            "fundamental_direction": "Bearish",
            "fbs_score": -25.0,
            "confidence_score": 60.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "RAW_MATERIAL_SHOCK",
            "cost_boundary_regime": "合理利润运行",
        })
        feature_row = pd.Series({
            "rb_close": 3650.0,
            "ma_20": 3660.0,
            "ma_5": 3655.0,
            "pct_basis_tier3_1y": 0.35,  # 现货未达 0.40 顺势买入阈值，但处于原料强推升期
            "cost_push_spread_5d": 0.022,  # 原料推升
            "dominant_leader_type": "RAW_MATERIAL_SHOCK",
        })
        sig = sig_gen.generate_signal("2019-03-01", state_row, feature_row, strategy_mode="QUANT_CORE")
        self.assertEqual(sig.direction, "FLAT")
        self.assertIn("禁空保护", sig.rationale)

    def test_17_cost_floor_short_veto(self):
        """测试钢厂深度亏损下轨支撑一票否决做空杀跌"""
        sig_gen = SignalGenerator(confidence_threshold=40.0)
        state_row = pd.Series({
            "fundamental_direction": "Bearish",
            "fbs_score": -35.0,
            "confidence_score": 65.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "SUPPLY_OVERHANG",
            "cost_boundary_regime": "深度亏损下轨支撑",
        })
        feature_row = pd.Series({
            "rb_close": 4150.0,
            "ma_20": 4180.0,
            "ma_5": 4160.0,
            "pct_basis_tier3_1y": 0.45,
            "pct_virtual_mill_margin_1y": 0.08,  # 严重亏损分位
            "profit_bf": -220.0,  # 高炉深度亏损 -220 元/吨
            "cost_push_spread_5d": 0.0,
            "dominant_leader_type": "SUPPLY_OVERHANG",
        })

        # 1. 空仓时企图做空: 一票否决
        sig_flat = sig_gen.generate_signal("2021-02-05", state_row, feature_row, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_flat.direction, "FLAT")
        self.assertIn("安全垫一票否决杀跌做空", sig_flat.rationale)

        # 2. 持多时企图翻空: 一票否决翻空，转为平仓观望
        sig_long = sig_gen.generate_signal("2021-02-05", state_row, feature_row, strategy_mode="QUANT_CORE", current_holding_direction="LONG")
        self.assertEqual(sig_long.direction, "FLAT")
        self.assertIn("安全垫一票否决杀跌做空", sig_long.rationale)

        # 3. 高位持空顺势跟踪: 允许继续在持大波段
        sig_short = sig_gen.generate_signal("2021-02-05", state_row, feature_row, strategy_mode="QUANT_CORE", current_holding_direction="SHORT")
        self.assertEqual(sig_short.direction, "SHORT")
        self.assertIn("空头大波段在持延续", sig_short.rationale)

    def test_18_high_vol_pilot_sizing(self):
        """测试高波动脱困区首笔试仓爬坡制: 波动冲击 >= 1.40 时严格限制杠杆 <= 2.0x"""
        sig_gen = SignalGenerator(confidence_threshold=40.0)
        pos_sizer = PositionSizer(
            contract_multiplier=10,
            default_margin_rate=0.10,
            max_base_leverage=5.0,
            max_margin_utilization=0.50,
        )
        state_row = pd.Series({
            "fundamental_direction": "Bullish",
            "fbs_score": 30.0,
            "confidence_score": 70.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "DEMAND_SURGE",
            "cost_boundary_regime": "合理利润运行",
        })
        feature_row = pd.Series({
            "rb_close": 4200.0,
            "ma_20": 4200.0,
            "ma_5": 4200.0,
            "pct_basis_tier3_1y": 0.55,
            "pct_virtual_mill_margin_1y": 0.50,
            "profit_bf": 200.0,
            "rb_vol_shock_ratio": 1.65,  # 波动突增
            "cost_push_spread_5d": 0.0,
            "dominant_leader_type": "DEMAND_SURGE",
        })

        # 从 FLAT 状态入场
        sig = sig_gen.generate_signal("2021-11-26", state_row, feature_row, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig.direction, "LONG")
        self.assertTrue(sig.is_high_vol_pilot)

        # 封装风控审核信号
        from stage_e.risk_filter import VettedSignal
        from stage_c.risk_firewall import FirewallDecision
        dummy_decision = FirewallDecision(
            trade_date="2021-11-26",
            status="PASS",
            max_allowable_leverage=1.0,
            action="HOLD",
            breached_layers=[],
            detailed_reasons=["正常放行"],
            dominant_risk_factor="NONE",
        )
        vetted_sig = VettedSignal(
            trade_date="2021-11-26",
            vetted_direction="LONG",
            target_leverage_cap=1.0,
            firewall_status="PASS",
            is_vetoed=False,
            veto_reason="",
            raw_signal=sig,
            firewall_decision=dummy_decision,
        )

        target = pos_sizer.calculate_position_target(vetted_sig, current_equity=10_000_000.0, current_price=4200.0)
        self.assertLessEqual(target.effective_leverage, 2.00)
        self.assertLessEqual(target.margin_utilization, 0.20)
        self.assertIn("高波动防跳空试仓", target.rationale)

    def test_19_box_space_filter_veto(self):
        """测试箱体空间与盈亏比不对称门禁: 处于箱体底部透支区做空一票否决，有效跌破不拦截"""
        sig_gen = SignalGenerator(confidence_threshold=40.0, space_thresh=0.012)
        state_row = pd.Series({
            "fundamental_direction": "Bearish",
            "fbs_score": -25.0,
            "confidence_score": 65.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "SUPPLY_OVERHANG",
            "cost_boundary_regime": "合理利润运行",
        })
        feature_row = pd.Series({
            "rb_close": 3110.0,
            "ma_20": 3130.0,
            "ma_5": 3120.0,
            "rolling_high_20": 3180.0,  # 箱顶 3180 (向上反弹风险 70点 = 2.25%)
            "rolling_low_20": 3090.0,   # 箱底 3090 (向下空间仅 20点 = 0.64%)
            "pct_basis_tier3_1y": 0.45,
            "pct_virtual_mill_margin_1y": 0.30,
            "profit_bf": 50.0,
        })

        # 1. 处于箱体下沿 0.64% 透支区，反弹风险是下行空间 3 倍: 一票否决新开空
        sig_vetoed = sig_gen.generate_signal("2025-09-02", state_row, feature_row, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_vetoed.direction, "FLAT")
        self.assertIn("箱体底部空间透支一票否决做空", sig_vetoed.rationale)

        # 2. 真突破测试: 若收盘价跌破箱底 3090 (如 3085), downside_space < 0, 必须放行做空
        feature_breakdown = feature_row.copy()
        feature_breakdown["rb_close"] = 3085.0
        sig_breakout = sig_gen.generate_signal("2025-09-02", state_row, feature_breakdown, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_breakout.direction, "SHORT")

    def test_20_physical_liquidity_gate_veto(self):
        """测试微观实物流动性冰封门禁: 农历春节前后全国建材成交量处于历史最低 10% 分位时一票否决开仓"""
        sig_gen = SignalGenerator(confidence_threshold=40.0, liquidity_thresh=0.10)
        state_row = pd.Series({
            "fundamental_direction": "Bearish",
            "fbs_score": -30.0,
            "confidence_score": 70.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "SUPPLY_OVERHANG",
            "cost_boundary_regime": "合理利润运行",
        })
        feature_row = pd.Series({
            "rb_close": 3250.0,
            "ma_20": 3300.0,
            "ma_5": 3280.0,
            "rolling_high_20": 3400.0,
            "rolling_low_20": 3150.0,
            "pct_building_deal_volume_1y": 0.07,  # 全国建材日成交量仅 7% 分位 (极度冰封)
            "cny_relative_week": -2,  # 春节前 2 周
            "pct_basis_tier3_1y": 0.45,
            "pct_virtual_mill_margin_1y": 0.30,
            "profit_bf": 50.0,
        })

        sig = sig_gen.generate_signal("2025-01-16", state_row, feature_row, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig.direction, "FLAT")
        self.assertIn("微观实物流动性冰封一票否决新开仓", sig.rationale)

    def test_21_carry_headwind_veto_backwardation_short(self):
        """测试期限结构强Backwardation负Carry一票否决做空及真突破破位豁免"""
        sig_gen = SignalGenerator(carry_headwind_thresh_high=0.85, enable_carry_gate=True)
        state_row = pd.Series({
            "fundamental_direction": "Bearish",
            "fbs_score": -25.0,
            "confidence_score": 65.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "SUPPLY_OVERHANG",
            "cost_boundary_regime": "合理利润运行",
        })
        feature_row = pd.Series({
            "rb_close": 3500.0,
            "ma_20": 3520.0,
            "ma_5": 3510.0,
            "rolling_high_20": 3600.0,
            "rolling_low_20": 3450.0,
            "pct_roll_yield_1y": 0.90,  # 极端强 Backwardation (90% 分位)
            "pct_basis_tier3_1y": 0.50,
            "pct_virtual_mill_margin_1y": 0.50,
            "profit_bf": 50.0,
        })

        # 1. 箱体内未破位: 强 Backwardation 负 Carry 严禁做空
        sig_vetoed = sig_gen.generate_signal("2021-08-10", state_row, feature_row, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_vetoed.direction, "FLAT")
        self.assertIn("期限结构强Backwardation负Carry一票否决做空", sig_vetoed.rationale)

        # 2. 真实破位主跌浪 (close < rolling_low_20): 门禁必须放行
        feature_breakdown = feature_row.copy()
        feature_breakdown["rb_close"] = 3440.0
        sig_breakout = sig_gen.generate_signal("2021-08-10", state_row, feature_breakdown, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_breakout.direction, "SHORT")

    def test_22_carry_headwind_veto_contango_long(self):
        """测试期限结构强Contango负Carry一票否决追多及真突破豁免"""
        sig_gen = SignalGenerator(carry_headwind_thresh_low=0.15, enable_carry_gate=True)
        state_row = pd.Series({
            "fundamental_direction": "Bullish",
            "fbs_score": 25.0,
            "confidence_score": 65.0,
            "spot_confirmation": "Confirmed",
            "dominant_leader_type": "MACRO_DEMAND_BOOM",
            "cost_boundary_regime": "合理利润运行",
        })
        feature_row = pd.Series({
            "rb_close": 3450.0,
            "ma_20": 3430.0,
            "ma_5": 3440.0,
            "rolling_high_20": 3500.0,
            "rolling_low_20": 3350.0,
            "pct_roll_yield_1y": 0.08,  # 极端强 Contango (8% 分位)
            "pct_basis_tier3_1y": 0.50,
            "pct_virtual_mill_margin_1y": 0.50,
            "profit_bf": 50.0,
        })

        # 1. 箱体内未突破: 强 Contango 负 Carry 严禁追多
        sig_vetoed = sig_gen.generate_signal("2024-04-10", state_row, feature_row, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_vetoed.direction, "FLAT")
        self.assertIn("期限结构强Contango负Carry一票否决做多", sig_vetoed.rationale)

        # 2. 真实向上突破 (close > rolling_high_20): 门禁放行
        feature_breakout = feature_row.copy()
        feature_breakout["rb_close"] = 3520.0
        feature_breakout["ma_20"] = 3480.0
        feature_breakout["ma_5"] = 3500.0
        sig_breakout = sig_gen.generate_signal("2024-04-10", state_row, feature_breakout, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_breakout.direction, "LONG")

    def test_23_carry_adaptive_position_sizing(self):
        """测试 Carry 自适应仓位调节与高波动硬隔离约束"""
        sizer = PositionSizer(max_margin_utilization=0.50)

        # 1. 基准仓位 (carry_multiplier = 1.0)
        sig_base = TradingSignal(
            trade_date="2024-05-10", symbol="RB", direction="LONG", strength=0.8, confidence_score=70.0,
            spot_confirmed=True, momentum_confirmed=True, strategy_name="QUANT_CORE", rationale="常规多头",
            carry_regime="NEUTRAL", carry_multiplier=1.0
        )
        vetted_base = VettedSignal(
            trade_date="2024-05-10", vetted_direction="LONG", target_leverage_cap=1.0,
            firewall_status="PASS", is_vetoed=False, veto_reason="", raw_signal=sig_base, firewall_decision=None
        )
        target_base = sizer.calculate_position_target(vetted_base, current_equity=10_000_000.0, current_price=3500.0)

        # 2. 顺风放大 (carry_multiplier = 1.05)
        sig_tailwind = dataclasses.replace(sig_base, carry_regime="TAILWIND_BACKWARDATION", carry_multiplier=1.05)
        vetted_tailwind = dataclasses.replace(vetted_base, raw_signal=sig_tailwind)
        target_tailwind = sizer.calculate_position_target(vetted_tailwind, current_equity=10_000_000.0, current_price=3500.0)
        self.assertGreaterEqual(target_tailwind.target_lots, target_base.target_lots)
        self.assertIn("TAILWIND_BACKWARDATION", target_tailwind.rationale)

        # 3. 逆风轻仓 (carry_multiplier = 0.85)
        sig_headwind = dataclasses.replace(sig_base, carry_regime="MILD_HEADWIND_CONTANGO", carry_multiplier=0.85)
        vetted_headwind = dataclasses.replace(vetted_base, raw_signal=sig_headwind)
        target_headwind = sizer.calculate_position_target(vetted_headwind, current_equity=10_000_000.0, current_price=3500.0)
        self.assertLess(target_headwind.target_lots, target_base.target_lots)
        self.assertIn("MILD_HEADWIND_CONTANGO", target_headwind.rationale)

        # 4. 高波动脱困区硬隔离 (即使 carry_multiplier = 1.05 也禁止顺风加码)
        sig_high_vol = dataclasses.replace(sig_tailwind, is_high_vol_pilot=True)
        vetted_high_vol = dataclasses.replace(vetted_base, raw_signal=sig_high_vol)
        target_high_vol = sizer.calculate_position_target(vetted_high_vol, current_equity=10_000_000.0, current_price=3500.0)
        # 高波动脱困区首笔试仓杠杆严格 <= 2.0x (资金利用率 <= 20%)
        self.assertLessEqual(target_high_vol.effective_leverage, 2.0)

    def test_24_mismatch_governance_rules(self):
        """测试弱需求与期现错配治理机制 (Far-Month Gate, Bottom Reversal, Margin Ceiling, Spot Capitulation)"""
        gen = SignalGenerator(enable_mismatch_governance=True)

        # 1. 远月换月初期高基差弱预期接飞刀门禁
        # 条件: DTE=90, 期价处于MA20/MA60破位通道, 虽然基差分位高达0.80且基本面看多，依然必须一票否决做多
        state_mismatch_drop = pd.Series({
            "fundamental_direction": "Bullish",
            "fundamental_score": 30.0,
            "confidence_score": 75.0,
            "spot_confirmation": "Confirmed",
            "macro_regime": "NORMAL",
            "macro_override_intensity": 0.0,
            "cost_boundary_regime": "合理利润运行",
        })
        feat_far_month_trap = pd.Series({
            "rb_close": 3530.0,
            "ma_20": 3650.0,
            "ma_60": 3700.0,
            "ma_5": 3520.0,
            "rolling_low_20": 3400.0,
            "pct_basis_tier3_1y": 0.80,
            "contract_dte": 95.0,
            "is_ferrous_complex_uptrend": False,
            "virtual_mill_margin": 50.0,
            "cost_push_spread_5d": -0.010,
        })
        sig_trap = gen.generate_signal("2024-09-01", state_mismatch_drop, feat_far_month_trap, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_trap.direction, "FLAT")
        self.assertIn("远月换月初期", sig_trap.rationale)

        # 临近交割 (DTE=40) 时，该门禁完全豁免，允许正常高基差期现收敛
        feat_near_month = feat_far_month_trap.copy()
        feat_near_month["contract_dte"] = 40.0
        feat_near_month["rb_close"] = 3530.0
        feat_near_month["ma_20"] = 3510.0
        feat_near_month["ma_5"] = 3510.0
        feat_near_month["ma_5"] = 3510.0
        sig_near = gen.generate_signal("2024-12-05", state_mismatch_drop, feat_near_month, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_near.direction, "LONG")

        # 2. 期现错配利空出尽筑底企稳试仓买入 (Bottom Absorption Reversal)
        # 条件: 现实极差 (fdir=Bearish, 钢厂深度亏损 profit_bf=-180), 盘面深度贴水且在现金成本附近止跌右侧站上MA5/MA20
        state_depressed = pd.Series({
            "fundamental_direction": "Bearish",
            "fundamental_score": -35.0,
            "confidence_score": 70.0,
            "spot_confirmation": "Rejected",
            "macro_regime": "NORMAL",
            "macro_override_intensity": 0.0,
            "cost_boundary_regime": "深度亏损下轨支撑",
        })
        feat_bottom = pd.Series({
            "rb_close": 3320.0,
            "ma_20": 3310.0,
            "ma_60": 3500.0,
            "ma_5": 3315.0,
            "rolling_low_20": 3300.0,
            "cost_bf": 3550.0,
            "cost_cash_floor": 3300.0,
            "profit_bf": -180.0,
            "pct_basis_tier3_1y": 0.65,
            "pct_virtual_mill_margin_1y": 0.05,
            "contract_dte": 80.0,
            "is_ferrous_complex_uptrend": False,
            "cost_push_spread_5d": 0.000,
        })
        sig_bottom = gen.generate_signal("2024-04-02", state_depressed, feat_bottom, strategy_mode="QUANT_CORE", current_holding_direction="FLAT")
        self.assertEqual(sig_bottom.direction, "LONG")
        self.assertEqual(sig_bottom.entry_driver, "MISMATCH_BOTTOM_REVERSAL")
        self.assertIn("利空出尽筑底企稳", sig_bottom.rationale)


if __name__ == "__main__":
    unittest.main()



