#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/backtest_engine.py
功能: 阶段 E 回测总调度与事件驱动模拟引擎 (Backtest Simulation Engine)
职责:
  1. 完整串接 State -> Signal -> Risk Firewall -> Position -> Execution 全链路;
  2. 严格按时间步推进 2018-2026 全历史 2,074 交易日连续回测;
  3. 零未来函数时间单向性: T 日决策，T+1 日以真实开盘价加滑点与手续费撮合;
  4. 支持三大对比策略并行或独立运行 (QUANT_CORE vs RAW_FUNDAMENTAL vs BENCHMARK);
  5. 自动集成螺纹主力 01-05-10 换月移仓机制与风控防火墙绝对否决权。
"""

from dataclasses import dataclass, replace
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np

from stage_e.signal_generator import SignalGenerator, TradingSignal
from stage_e.risk_filter import RiskFilterAdapter, VettedSignal
from stage_e.position_sizer import PositionSizer, PositionTarget
from stage_e.contract_rollover import ContractRolloverManager, RolloverEvent
from stage_e.execution_engine import ExecutionEngine
from stage_e.performance_analyzer import PerformanceAnalyzer
from framework_rules import HIGH_VOL_THRESHOLD, RISK_DISTANCE_FLOOR


@dataclass
class BacktestResult:
    strategy_name: str
    equity_df: pd.DataFrame
    trades_df: pd.DataFrame
    performance: Dict[str, Any]
    vetted_signals_df: pd.DataFrame


class BacktestEngine:
    """
    阶段 E 回测总调度引擎
    """

    def __init__(
        self,
        features_df: pd.DataFrame,
        state_matrix: pd.DataFrame,
        symbol: str = "rb",
        initial_capital: float = 10_000_000.0,
        slippage_ticks: float = 1.0,
        commission_rate: float = 0.0001,
        margin_rate: float = 0.10,
        max_base_leverage: Optional[float] = None,
        max_margin_utilization: float = 0.50,
        risk_budget_fraction: Optional[float] = None,
        scale_by_confidence: bool = True,
        common_risk_controls: bool = False,
    ):
        self.features_df = features_df.copy()
        self.state_matrix = state_matrix.copy()
        self.symbol = symbol.lower()
        self.initial_capital = initial_capital
        self.slippage = slippage_ticks
        self.commission_rate = commission_rate
        self.margin_rate = margin_rate
        self.max_base_leverage = max_base_leverage
        self.max_margin_utilization = max_margin_utilization
        self.risk_budget_fraction = risk_budget_fraction
        self.scale_by_confidence = scale_by_confidence
        self.common_risk_controls = common_risk_controls

        # 确保日期索引为对齐的字符串
        self.features_df.index = self.features_df.index.astype(str)
        self.state_matrix.index = self.state_matrix.index.astype(str)
        common_idx = self.features_df.index.intersection(self.state_matrix.index).sort_values()
        self.features_df = self.features_df.loc[common_idx]
        self.state_matrix = self.state_matrix.loc[common_idx]

        # 补齐技术指标与空间箱体指标 (严格 shift(1) 零未来函数)
        if "ma_20" not in self.features_df.columns:
            self.features_df["ma_20"] = self.features_df["rb_close"].rolling(20).mean()
        if "ma_5" not in self.features_df.columns and "ma5" not in self.features_df.columns:
            self.features_df["ma_5"] = self.features_df["rb_close"].rolling(5).mean()
        if "rolling_high_20" not in self.features_df.columns:
            high_col = "rb_high" if "rb_high" in self.features_df.columns else ("close" if "close" in self.features_df.columns else "rb_close")
            self.features_df["rolling_high_20"] = self.features_df[high_col].shift(1).rolling(20).max()
        if "rolling_low_20" not in self.features_df.columns:
            low_col = "rb_low" if "rb_low" in self.features_df.columns else ("close" if "close" in self.features_df.columns else "rb_close")
            self.features_df["rolling_low_20"] = self.features_df[low_col].shift(1).rolling(20).min()

        # 初始化主力换月管理器
        self.rollover_mgr = ContractRolloverManager(symbol=self.symbol)
        self.analyzer = PerformanceAnalyzer()
        close = self.features_df["rb_close"]
        high = self.features_df.get("rb_high", close)
        low = self.features_df.get("rb_low", close)
        tr = pd.concat([high-low, (high-close.shift()).abs(), (low-close.shift()).abs()], axis=1).max(axis=1)
        self.features_df["risk_distance_pct"] = (2 * tr.rolling(20, min_periods=20).mean() / close).clip(lower=RISK_DISTANCE_FLOOR)


    def run_backtest(
        self,
        strategy_mode: str = "QUANT_CORE",
        enable_firewall: bool = True,
        strategy_label: Optional[str] = None,
        signal_generator: Optional[SignalGenerator] = None,
        verbose: bool = True,
    ) -> BacktestResult:
        """
        运行指定策略的全历史连续回测
        """
        strat_label = (
            strategy_label
            if strategy_label
            else (
                f"{strategy_mode}_with_Firewall"
                if enable_firewall
                else f"{strategy_mode}_No_Firewall"
            )
        )
        if verbose:
            print(f"[*] 开始回测运行: {strat_label} (模式: {strategy_mode}, 防火墙: {enable_firewall})")

        signal_gen = signal_generator if signal_generator is not None else SignalGenerator()
        risk_filter = RiskFilterAdapter()
        pos_sizer = PositionSizer(
            contract_multiplier=10,
            default_margin_rate=self.margin_rate,
            max_base_leverage=self.max_base_leverage,
            max_margin_utilization=self.max_margin_utilization,
        )
        exec_engine = ExecutionEngine(
            initial_capital=self.initial_capital,
            contract_multiplier=10,
            slippage_ticks=self.slippage,
            commission_rate=self.commission_rate,
            margin_rate=self.margin_rate,
        )

        dates = list(self.features_df.index)
        n_days = len(dates)
        pending_target: Optional[PositionTarget] = None
        pending_prediction_id: str = ""
        vetted_signals_records = []

        for i, dt in enumerate(dates):
            s_row = self.state_matrix.loc[dt]
            f_row = self.features_df.loc[dt]

            # 获取当日盘面及主力实约事实
            active_info = self.rollover_mgr.get_active_contract(dt)
            if active_info is not None:
                cur_open = active_info["open"]
                cur_close = active_info["close"]
                cur_settle = active_info["settlement"]
                cur_code = active_info["contract_code"]
            else:
                raise ValueError(f"{dt}: 缺实约映射，请显式限定验证区间，禁止 MAIN 替代成交")

            roll_event = self.rollover_mgr.check_rollover_event(dt)

            # 1. 晨间开盘撮合: 执行上一交易日收盘生成的 pending_target
            if pending_target is not None:
                exec_engine.execute_next_bar(
                    date_str=dt,
                    target=pending_target,
                    open_price=cur_open,
                    settlement_price=cur_settle,
                    close_price=cur_close,
                    rollover_event=roll_event,
                    active_contract_code=cur_code,
                    prediction_id=pending_prediction_id,
                )
            else:
                # 首日建立默认零持仓快照
                default_target = PositionTarget(
                    trade_date=dt,
                    target_direction="FLAT",
                    target_weight=0.0,
                    target_lots=0,
                    target_nominal_value=0.0,
                    estimated_margin=0.0,
                    margin_utilization=0.0,
                    effective_leverage=0.0,
                    rationale="首日初始空仓",
                )
                exec_engine.execute_next_bar(
                    date_str=dt,
                    target=default_target,
                    open_price=cur_open,
                    settlement_price=cur_settle,
                    close_price=cur_close,
                    rollover_event=roll_event,
                    active_contract_code=cur_code,
                    prediction_id=f"PRED_{dt.replace('-', '')}_INIT",
                )

            exec_engine.daily_snapshots[-1]["marking_basis"] = active_info["marking_basis"]

            # 2. 日盘收盘决策: 基于截至今日收盘的全部 PIT 状态与特征，为明日开盘制定计划
            latest_equity = exec_engine.daily_snapshots[-1]["total_equity"]
            cur_lots = exec_engine.current_lots
            cur_holding_dir = "LONG" if cur_lots > 0 else ("SHORT" if cur_lots < 0 else "FLAT")

            # 生成原始信号 (传入当前持仓方向以激活在持/入场迟滞回线机制)
            raw_sig = signal_gen.generate_signal(
                date_str=dt,
                state_row=s_row,
                feature_row=f_row,
                strategy_mode=strategy_mode,
                current_holding_direction=cur_holding_dir,
            )

            # 波动风险对所有策略及持有期间持续生效。
            vol = float(f_row.get("vol_shock_ratio", f_row.get("rb_vol_shock_ratio", 1.0)))
            raw_sig = replace(raw_sig, is_high_vol_pilot=bool(vol >= HIGH_VOL_THRESHOLD))

            risk_features, risk_states = f_row, s_row
            if self.common_risk_controls:
                # 对照组只共用价格破位/波动风险，不能偷偷读取基本面或背离特征。
                keys = ['rb_close','ma_20','ma20','ma_60','ma60','rb_ret_1d','rb_ret_5d','vol_shock_ratio','rb_vol_shock_ratio']
                risk_features = f_row.reindex([k for k in keys if k in f_row]).copy()
                risk_features['data_freshness_ratio'] = 1.0
                risk_states = pd.Series({'fundamental_direction':'Neutral', 'divergence_area':0.0})
                raw_sig = replace(raw_sig, is_pilot_squeeze=False)

            # 风控防火墙终审
            if enable_firewall:
                vetted_sig = risk_filter.vet_signal(
                    date_str=dt,
                    raw_signal=raw_sig,
                    state_row=risk_states,
                    feature_row=risk_features,
                    current_holding_direction=cur_holding_dir,
                )
            else:
                # 裸奔无防火墙对照组
                vetted_sig = VettedSignal(
                    trade_date=dt,
                    vetted_direction=raw_sig.direction,
                    target_leverage_cap=1.00,
                    firewall_status="BYPASS",
                    is_vetoed=False,
                    veto_reason="无风控裸奔对照",
                    raw_signal=raw_sig,
                    firewall_decision=None,
                )

            # 仓位预算与目标手数计算
            pos_target = pos_sizer.calculate_position_target(
                vetted_signal=vetted_sig,
                current_equity=latest_equity,
                current_price=cur_close,
                current_lots=cur_lots,
                risk_distance=cur_close * float(f_row["risk_distance_pct"]),
                risk_budget_fraction=self.risk_budget_fraction,
                scale_by_confidence=self.scale_by_confidence,
            )

            # 暂存为明日开盘的执行计划
            pending_target = pos_target
            pending_prediction_id = f"PRED_{dt.replace('-', '')}_{self.symbol.upper()}"

            vetted_signals_records.append({
                "date": dt,
                "strategy": strat_label,
                "raw_direction": raw_sig.direction,
                "raw_strength": raw_sig.strength,
                "confidence_score": raw_sig.confidence_score,
                "spot_confirmed": raw_sig.spot_confirmed,
                "momentum_confirmed": raw_sig.momentum_confirmed,
                "vetted_direction": vetted_sig.vetted_direction,
                "firewall_status": vetted_sig.firewall_status,
                "firewall_cap": vetted_sig.target_leverage_cap,
                "is_vetoed": vetted_sig.is_vetoed,
                "veto_reason": vetted_sig.veto_reason,
                "target_weight": pos_target.target_weight,
                "target_lots": pos_target.target_lots,
                "rationale": pos_target.rationale,
                "signal_rationale": raw_sig.rationale,
                "mechanism_demand": s_row.get("mechanism_demand", "UNKNOWN"),
                "mechanism_supply": s_row.get("mechanism_supply", "UNKNOWN"),
                "mechanism_cost": s_row.get("mechanism_cost", "UNKNOWN"),
                "hypothesis_ids": ";".join(str(s_row.get(f"hypothesis_{f}_id", "")) for f in ("demand", "supply", "cost")),
                "data_quality_status": s_row.get("data_quality_status", "UNKNOWN"),
            })

        # 整理输出
        equity_df = exec_engine.get_snapshots_df()
        trades_df = exec_engine.get_trade_records_df()
        vetted_signals_df = pd.DataFrame(vetted_signals_records)

        # 绩效分析
        perf = self.analyzer.analyze_equity_and_trades(
            equity_df=equity_df,
            trades_df=trades_df,
            strategy_name=strat_label,
        )

        if verbose:
            print(
                f"[+] {strat_label} 回测完成! 最终净值: {perf['final_equity']/self.initial_capital:.4f}, "
                f"年化: {perf['cagr_pct']:.2f}%, 最大回撤: {perf['max_drawdown_pct']:.2f}%, "
                f"夏普: {perf['sharpe_ratio']:.2f}, 胜率: {perf['win_rate_pct']:.1f}% ({perf['total_trades']}笔)"
            )

        return BacktestResult(
            strategy_name=strat_label,
            equity_df=equity_df,
            trades_df=trades_df,
            performance=perf,
            vetted_signals_df=vetted_signals_df,
        )
