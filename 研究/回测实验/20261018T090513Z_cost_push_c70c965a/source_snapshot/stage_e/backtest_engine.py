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
        enable_tactical_execution: bool = False,
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
        self.enable_tactical_execution = enable_tactical_execution

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
            self.features_df["rolling_high_20"] = self.features_df[high_col].shift(1).rolling(20, min_periods=10).max()
        if "rolling_low_20" not in self.features_df.columns:
            low_col = "rb_low" if "rb_low" in self.features_df.columns else ("close" if "close" in self.features_df.columns else "rb_close")
            self.features_df["rolling_low_20"] = self.features_df[low_col].shift(1).rolling(20, min_periods=10).min()
        if "rolling_high_60" not in self.features_df.columns:
            high_col = "rb_high" if "rb_high" in self.features_df.columns else ("close" if "close" in self.features_df.columns else "rb_close")
            self.features_df["rolling_high_60"] = self.features_df[high_col].shift(1).rolling(60, min_periods=20).max()
        if "rolling_low_60" not in self.features_df.columns:
            low_col = "rb_low" if "rb_low" in self.features_df.columns else ("close" if "close" in self.features_df.columns else "rb_close")
            self.features_df["rolling_low_60"] = self.features_df[low_col].shift(1).rolling(60, min_periods=20).min()
        if "rolling_high_120" not in self.features_df.columns:
            high_col = "rb_high" if "rb_high" in self.features_df.columns else ("close" if "close" in self.features_df.columns else "rb_close")
            self.features_df["rolling_high_120"] = self.features_df[high_col].shift(1).rolling(120, min_periods=20).max()
        if "rolling_max_spread_30" not in self.features_df.columns:
            spread_series = self.features_df["cost_push_spread_5d"] if "cost_push_spread_5d" in self.features_df.columns else pd.Series(0.0, index=self.features_df.index)
            self.features_df["rolling_max_spread_30"] = spread_series.shift(1).rolling(30, min_periods=5).max()

        if "cp_basis_delta3" not in self.features_df.columns or "cp_spot_delta3" not in self.features_df.columns:
            spot_s = self.features_df.get("spot_hz_zhongtian", self.features_df.get("spot_hz_tier3", pd.Series(float("nan"), index=self.features_df.index)))
            c_s = self.features_df["rb_close"]
            basis_s = spot_s - c_s
            if "cp_spot" not in self.features_df.columns:
                self.features_df["cp_spot"] = spot_s
            if "cp_spot_delta3" not in self.features_df.columns:
                self.features_df["cp_spot_delta3"] = spot_s.diff(3)
            if "cp_spot_ret5" not in self.features_df.columns:
                self.features_df["cp_spot_ret5"] = spot_s.pct_change(5, fill_method=None)
            if "cp_basis_delta3" not in self.features_df.columns:
                self.features_df["cp_basis_delta3"] = basis_s.diff(3)
            if "cp_basis_delta5" not in self.features_df.columns:
                self.features_df["cp_basis_delta5"] = basis_s.diff(5)
            if "cp_basis_max5" not in self.features_df.columns:
                self.features_df["cp_basis_max5"] = basis_s.shift(1).rolling(5, min_periods=2).max()
            if "basis_zscore_60" not in self.features_df.columns:
                b_mean_60 = basis_s.shift(1).rolling(60, min_periods=20).mean()
                b_std_60 = basis_s.shift(1).rolling(60, min_periods=20).std().replace(0, float('nan'))
                self.features_df["basis_rolling_mean_60"] = b_mean_60
                self.features_df["basis_rolling_std_60"] = b_std_60
                self.features_df["basis_zscore_60"] = (basis_s - b_mean_60) / b_std_60
            if "is_low_vol_regime" not in self.features_df.columns:
                if "cp_atr20" in self.features_df.columns:
                    atr_s = self.features_df["cp_atr20"]
                else:
                    h_s = self.features_df.get("rb_high", c_s)
                    l_s = self.features_df.get("rb_low", c_s)
                    tr_s = pd.concat([h_s - l_s, (h_s - c_s.shift()).abs(), (l_s - c_s.shift()).abs()], axis=1).max(axis=1)
                    atr_s = tr_s.rolling(20, min_periods=20).mean()
                atr_pct_s = atr_s / c_s
                self.features_df["cp_atr_pct"] = atr_pct_s
                self.features_df["is_low_vol_regime"] = atr_pct_s <= 0.022

        # 4大支柱高利润牛市前置特征 (Ferrous Complex, Supply, Demand)
        if "is_ferrous_complex_uptrend" not in self.features_df.columns:
            commodities = ["rb", "hc", "i", "j", "jm"]
            rising_count = pd.Series(0, index=self.features_df.index)
            rising_dict = {}
            for com in commodities:
                col_close = f"{com}_close" if f"{com}_close" in self.features_df.columns else None
                if col_close:
                    cc = self.features_df[col_close]
                    ma20_c = cc.rolling(20, min_periods=5).mean()
                    ma5_c = cc.rolling(5, min_periods=2).mean()
                    c_rising = (cc >= ma20_c * 0.99) | (ma5_c >= ma20_c) | (cc > cc.shift(5))
                    rising_count += c_rising.astype(int)
                    rising_dict[com] = c_rising
                else:
                    rising_dict[com] = pd.Series(False, index=self.features_df.index)
            rising_rb = rising_dict.get("rb", pd.Series(False, index=self.features_df.index))
            rising_hc = rising_dict.get("hc", pd.Series(False, index=self.features_df.index))
            self.features_df["is_ferrous_complex_uptrend"] = (rising_count >= 3) | (rising_rb & rising_hc)

        if "is_supply_high_or_rising" not in self.features_df.columns:
            if "hot_metal_247" in self.features_df.columns:
                hm = self.features_df["hot_metal_247"]
                hm_rising = (hm >= hm.shift(10) * 0.99) | (hm >= hm.shift(5))
                hm_stable_high = (hm >= 220.0) & (hm >= hm.shift(20) * 0.92)
                hm_ok = hm_rising | hm_stable_high
            else:
                hm_ok = pd.Series(True, index=self.features_df.index)

            if "rebar_weekly_prod" in self.features_df.columns:
                sp = self.features_df["rebar_weekly_prod"]
                sp_rising = (sp >= sp.shift(10) * 0.99) | (sp >= sp.shift(5))
                sp_stable_high = (sp >= 240.0) & (sp >= sp.shift(20) * 0.90)
                sp_ok = sp_rising | sp_stable_high
            else:
                sp_ok = pd.Series(True, index=self.features_df.index)

            self.features_df["is_supply_high_or_rising"] = hm_ok & sp_ok

        if "is_demand_high_or_stable" not in self.features_df.columns:
            if "rebar_apparent_demand" in self.features_df.columns:
                dem = self.features_df["rebar_apparent_demand"]
                dem_max_20 = dem.shift(1).rolling(20, min_periods=5).max()
                outflow_pct = self.features_df.get("pct_flow_hz_outflow", pd.Series(0.5, index=self.features_df.index))
                dem_healthy_level = (dem >= 230.0) | (outflow_pct >= 0.30)
                dem_not_collapsing = (dem >= dem_max_20 * 0.78) | (dem >= 270.0)
                self.features_df["is_demand_high_or_stable"] = dem_healthy_level & dem_not_collapsing
            else:
                self.features_df["is_demand_high_or_stable"] = pd.Series(True, index=self.features_df.index)

        # 初始化主力换月管理器
        self.rollover_mgr = ContractRolloverManager(symbol=self.symbol)
        if "contract_dte" not in self.features_df.columns and "dte" not in self.features_df.columns:
            if hasattr(self.rollover_mgr, "get_full_map"):
                full_map = self.rollover_mgr.get_full_map()
                dtes = {}
                for d, c in zip(full_map.index, full_map["contract_code_short"]):
                    try:
                        yr = 2000 + int(str(c)[:2])
                        mo = int(str(c)[2:])
                        exp_dt = pd.Timestamp(year=yr, month=mo, day=15)
                        cur_dt = pd.Timestamp(d)
                        dtes[d] = (exp_dt - cur_dt).days
                    except Exception:
                        dtes[d] = 999
                self.features_df["contract_dte"] = pd.Series(dtes).reindex(self.features_df.index).fillna(999)
            else:
                self.features_df["contract_dte"] = 999
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
        enable_tactical_execution: Optional[bool] = None,
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
        if hasattr(signal_gen, "reset"):
            signal_gen.reset()
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

        is_tactical = (
            enable_tactical_execution
            if enable_tactical_execution is not None
            else self.enable_tactical_execution
        ) and (self.symbol in ("rb", "hc"))

        dates = list(self.features_df.index)
        n_days = len(dates)
        pending_target: Optional[PositionTarget] = None
        pending_prediction_id: str = ""
        pending_signal = None
        vetted_signals_records = []

        # 战术执行状态机 (跨周期护航仅作用于螺纹与热卷)
        tactical_locked = False
        tactical_locked_dir = ""
        cooldown_counter = 0
        holding_days = 0
        peak_favorable = 0.0
        entry_structural_stop = 0.0
        in_pivot_pause = False
        pivot_pause_dir = ""
        current_holding_driver = ""

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
                cur_high = active_info.get("high", cur_close)
                cur_low = active_info.get("low", cur_close)
            else:
                raise ValueError(f"{dt}: 缺实约映射，请显式限定验证区间，禁止 MAIN 替代成交")

            dte_val = float(f_row.get("contract_dte", f_row.get("dte", 999.0)))
            br_val = float(f_row.get("basis_rate_tier3", f_row.get("basis_rate", 0.0)))
            pct_b1y = float(f_row.get("pct_basis_tier3_1y", 0.5))
            try:
                roll_event = self.rollover_mgr.check_rollover_event(
                    dt, basis_rate=br_val, dte=dte_val, pct_basis_1y=pct_b1y
                )
            except TypeError:
                roll_event = self.rollover_mgr.check_rollover_event(dt)

            previous_lots = exec_engine.current_lots

            # 确定当日撮合价格与对应实约 (支持主力 MAIN, 近月 NEAR, 远月 FAR)
            trade_open = cur_open
            trade_close = cur_close
            trade_settle = cur_settle
            trade_code = cur_code
            trade_high = cur_high
            trade_low = cur_low
            trade_dte = dte_val

            # 1. 若当前持有非主力实约，获取其真实行情与DTE
            if exec_engine.current_lots != 0 and exec_engine.current_contract != cur_code:
                held_info = self.rollover_mgr.get_specific_contract(dt, exec_engine.current_contract)
                if held_info is not None:
                    trade_open = held_info["open"]
                    trade_close = held_info["close"]
                    trade_settle = held_info["settlement"]
                    trade_code = held_info["contract_code"]
                    trade_high = held_info.get("high", trade_close)
                    trade_low = held_info.get("low", trade_close)
                    trade_dte = held_info.get("dte", dte_val)
                # 若持仓合约非本次主力换月中的旧主力，屏蔽主力换月
                if roll_event.is_rollover and roll_event.old_contract != exec_engine.current_contract:
                    roll_event = replace(roll_event, is_rollover=False)

            # 2. 若当前无持仓但即将以非主力角色建仓 (NEAR / FAR)
            elif exec_engine.current_lots == 0 and pending_signal is not None and getattr(pending_signal, "preferred_contract_role", "MAIN") != "MAIN":
                target_role = getattr(pending_signal, "preferred_contract_role", "MAIN")
                role_info = self.rollover_mgr.get_contract_by_role(dt, target_role)
                if role_info is not None:
                    trade_open = role_info["open"]
                    trade_close = role_info["close"]
                    trade_settle = role_info["settlement"]
                    trade_code = role_info["contract_code"]
                    trade_high = role_info.get("high", trade_close)
                    trade_low = role_info.get("low", trade_close)
                    trade_dte = role_info.get("dte", dte_val)
                    if roll_event.is_rollover:
                        roll_event = replace(roll_event, is_rollover=False)

            # 战术锁与冷却期互锁检查: 若战术层已因假突破/耗尽锁定，阻断同向盲目追单
            if is_tactical:
                if tactical_locked:
                    cooldown_counter -= 1
                    if cooldown_counter <= 0:
                        tactical_locked = False
                        tactical_locked_dir = ""
                if pending_target is not None:
                    if tactical_locked and pending_target.target_direction == tactical_locked_dir:
                        pending_target = PositionTarget(
                            trade_date=dt,
                            target_direction="FLAT",
                            target_weight=0.0,
                            target_lots=0,
                            target_nominal_value=0.0,
                            estimated_margin=0.0,
                            margin_utilization=0.0,
                            effective_leverage=0.0,
                            rationale=f"战术假突破冷静期 [{tactical_locked_dir}]",
                        )
                    elif in_pivot_pause and pending_target.target_direction == pivot_pause_dir:
                        pending_target = PositionTarget(
                            trade_date=dt,
                            target_direction="FLAT",
                            target_weight=0.0,
                            target_lots=0,
                            target_nominal_value=0.0,
                            estimated_margin=0.0,
                            margin_utilization=0.0,
                            effective_leverage=0.0,
                            rationale=f"动能衰竭波段全平观望期 [{pivot_pause_dir}]",
                        )
                    elif pending_target.target_direction != tactical_locked_dir:
                        tactical_locked = False
                        tactical_locked_dir = ""

            # 1. 晨间开盘撮合: 执行上一交易日收盘生成的 pending_target
            if pending_target is not None:
                exec_engine.execute_next_bar(
                    date_str=dt,
                    target=pending_target,
                    open_price=trade_open,
                    settlement_price=trade_settle,
                    close_price=trade_close,
                    rollover_event=roll_event,
                    active_contract_code=trade_code,
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
                    open_price=trade_open,
                    settlement_price=trade_settle,
                    close_price=trade_close,
                    rollover_event=roll_event,
                    active_contract_code=trade_code,
                    prediction_id=f"PRED_{dt.replace('-', '')}_INIT",
                )

            # 更新持仓跟踪与战术执行判定
            if is_tactical:
                if exec_engine.current_lots == 0:
                    holding_days = 0
                    peak_favorable = 0.0
                    entry_structural_stop = 0.0
                    current_holding_driver = ""
                else:
                    if previous_lots == 0:
                        holding_days = 1
                        peak_favorable = 0.0
                        in_pivot_pause = False
                        pivot_pause_dir = ""
                        current_holding_driver = pending_signal.entry_driver if pending_signal else ""
                        is_long = exec_engine.current_lots > 0
                        prev_lows = [cur_low]
                        prev_highs = [cur_high]
                        for lookback in [1, 2]:
                            if i >= lookback:
                                p_info = self.rollover_mgr.get_active_contract(dates[i - lookback])
                                if p_info:
                                    prev_lows.append(p_info.get("low", cur_low))
                                    prev_highs.append(p_info.get("high", cur_high))
                        if is_long:
                            entry_structural_stop = min(prev_lows) - 15.0
                        else:
                            entry_structural_stop = max(prev_highs) + 15.0
                    else:
                        holding_days += 1

                # 战术执行规则检测 (开平仓当日及持仓期内)
                # 均值回归策略(LOW_VOL_BASIS_REVERSION)非趋势突破，豁免15点初始假突破止损
                if exec_engine.current_lots != 0 and current_holding_driver != "LOW_VOL_BASIS_REVERSION":
                    is_long = exec_engine.current_lots > 0
                    entry_p = exec_engine.avg_entry_price
                    ma5 = float(f_row.get("ma_5", f_row.get("ma5", cur_close)))
                    ma20 = float(f_row.get("ma_20", f_row.get("ma20", cur_close)))

                    fav = (cur_high - entry_p) if is_long else (entry_p - cur_low)
                    peak_favorable = max(peak_favorable, fav)

                    prev_c = cur_open
                    if i > 0:
                        prev_active = self.rollover_mgr.get_active_contract(dates[i - 1])
                        if prev_active:
                            prev_c = prev_active["close"]

                    tactical_exit_trigger = False
                    tactical_exit_price = cur_close
                    tactical_exit_reason = ""
                    lock_next = False
                    is_pivot_exit = False

                    # 规则 1: 初期突破结构防守线 (15点缓冲，防恶性假突破)
                    if holding_days <= 3 and entry_structural_stop > 0:
                        if is_long and cur_low <= entry_structural_stop:
                            tactical_exit_trigger = True
                            tactical_exit_price = entry_structural_stop
                            tactical_exit_reason = "INITIAL_BREAKOUT_FAILED"
                            lock_next = True
                        elif (not is_long) and cur_high >= entry_structural_stop:
                            tactical_exit_trigger = True
                            tactical_exit_price = entry_structural_stop
                            tactical_exit_reason = "INITIAL_BREAKOUT_FAILED"
                            lock_next = True

                    # 规则 2: 跳空断头铡退出 (隔夜跳空未延续反向砸破)
                    if not tactical_exit_trigger and holding_days >= 1:
                        gap = cur_open - prev_c
                        if is_long and gap >= 25.0 and cur_close < cur_open - 8.0:
                            tactical_exit_trigger = True
                            tactical_exit_price = cur_close
                            tactical_exit_reason = "GAP_EXHAUSTION_EXIT"
                            lock_next = True
                        elif (not is_long) and gap <= -25.0 and cur_close > cur_open + 8.0:
                            tactical_exit_trigger = True
                            tactical_exit_price = cur_close
                            tactical_exit_reason = "GAP_EXHAUSTION_EXIT"
                            lock_next = True

                    # 规则 3: 震荡停滞退出 (持仓4-8天无利破位)
                    if not tactical_exit_trigger and 4 <= holding_days <= 8:
                        if peak_favorable < 20.0:
                            if is_long and cur_close < entry_p - 5.0:
                                tactical_exit_trigger = True
                                tactical_exit_price = cur_close
                                tactical_exit_reason = "CHOPPY_REGIME_EXIT"
                                lock_next = True
                            elif (not is_long) and cur_close > entry_p + 5.0:
                                tactical_exit_trigger = True
                                tactical_exit_price = cur_close
                                tactical_exit_reason = "CHOPPY_REGIME_EXIT"
                                lock_next = True

                    # 规则 4: 中后期动能衰竭波段全平 (大波段利润保护)
                    if not tactical_exit_trigger and peak_favorable >= 120.0:
                        if is_long:
                            has_long_shadow = (cur_high - max(cur_open, cur_close)) >= 28.0 and cur_close < cur_open
                            broken_ma5 = cur_close < ma5 and prev_c >= ma5
                            pullback_loss = cur_close < (entry_p + peak_favorable * 0.80)
                            if (has_long_shadow or broken_ma5) and pullback_loss:
                                tactical_exit_trigger = True
                                tactical_exit_price = cur_close
                                tactical_exit_reason = "PIVOT_EXHAUSTION_EXIT"
                                is_pivot_exit = True
                        else:
                            has_long_shadow = (min(cur_open, cur_close) - cur_low) >= 28.0 and cur_close > cur_open
                            broken_ma5 = cur_close > ma5 and prev_c <= ma5
                            pullback_loss = cur_close > (entry_p - peak_favorable * 0.80)
                            if (has_long_shadow or broken_ma5) and pullback_loss:
                                tactical_exit_trigger = True
                                tactical_exit_price = cur_close
                                tactical_exit_reason = "PIVOT_EXHAUSTION_EXIT"
                                is_pivot_exit = True

                    if tactical_exit_trigger:
                        exec_engine.execute_tactical_exit(dt, tactical_exit_price, tactical_exit_reason)
                        if lock_next:
                            tactical_locked = True
                            tactical_locked_dir = "LONG" if is_long else "SHORT"
                            cooldown_counter = 3
                        if is_pivot_exit:
                            in_pivot_pause = True
                            pivot_pause_dir = "LONG" if is_long else "SHORT"
                        holding_days = 0
                        peak_favorable = 0.0

                elif in_pivot_pause:
                    ma20 = float(f_row.get("ma_20", f_row.get("ma20", cur_close)))
                    ma5 = float(f_row.get("ma_5", f_row.get("ma5", cur_close)))
                    if pivot_pause_dir == "LONG":
                        if (cur_low <= ma20 * 1.01 and cur_close >= ma20) or (cur_close > ma5 and cur_close > cur_open):
                            in_pivot_pause = False
                            pivot_pause_dir = ""
                    elif pivot_pause_dir == "SHORT":
                        if (cur_high >= ma20 * 0.99 and cur_close <= ma20) or (cur_close < ma5 and cur_close < cur_open):
                            in_pivot_pause = False
                            pivot_pause_dir = ""

            exec_engine.daily_snapshots[-1]["marking_basis"] = active_info["marking_basis"]
            if hasattr(signal_gen, "on_execution"):
                signal_gen.on_execution(previous_lots, exec_engine.current_lots, pending_signal)
            snapshot = exec_engine.daily_snapshots[-1]
            snapshot["execution_signal_date"] = pending_signal.trade_date if pending_signal else ""
            snapshot["execution_driver"] = pending_signal.entry_driver if pending_signal else ""
            snapshot["execution_stage"] = pending_signal.participation_stage if pending_signal else ""
            snapshot["execution_exit_reason"] = pending_signal.invalidation_reason if pending_signal else ""
            snapshot["cost_position_active"] = bool(getattr(signal_gen, "position", None))

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
                current_holding_entry_driver=current_holding_driver,
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

            # 物理交割月硬防线门禁: 任何持仓合约若自然日 DTE <= 20，投机账户必须强制清盘 (零进入交割月风险)
            if cur_lots != 0:
                held_contract_info = self.rollover_mgr.get_specific_contract(dt, exec_engine.current_contract)
                held_dte_now = held_contract_info.get("dte", 999.0) if held_contract_info else dte_val
                if held_dte_now <= 20.0:
                    pos_target = PositionTarget(
                        trade_date=dt,
                        target_direction="FLAT",
                        target_weight=0.0,
                        target_lots=0,
                        target_nominal_value=0.0,
                        estimated_margin=0.0,
                        margin_utilization=0.0,
                        effective_leverage=0.0,
                        rationale=f"FORCED_DELIVERY_EXIT: 合约{exec_engine.current_contract} DTE={held_dte_now:.0f}天<=20，投机账户临近交割月强制平仓",
                    )
                    vetted_sig = replace(vetted_sig, vetted_direction="FLAT", veto_reason="FORCED_DELIVERY_EXIT")
                    raw_sig = replace(raw_sig, direction="FLAT", invalidation_reason="FORCED_DELIVERY_EXIT")

            # 暂存为明日开盘的执行计划
            pending_target = pos_target
            pending_signal = raw_sig
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
                "entry_driver": raw_sig.entry_driver,
                "participation_stage": raw_sig.participation_stage,
                "entry_trigger": raw_sig.entry_trigger,
                "invalidation_reason": raw_sig.invalidation_reason,
                "route_risk_budget_fraction": raw_sig.risk_budget_fraction,
                "route_leverage_cap": raw_sig.strategy_leverage_cap,
                "route_margin_utilization": raw_sig.strategy_margin_utilization,
                "target_margin_utilization": pos_target.margin_utilization,
                "estimated_distance_loss_fraction": (abs(pos_target.target_nominal_value) / latest_equity * raw_sig.risk_distance_pct
                    if raw_sig.risk_distance_pct is not None and latest_equity > 0 else None),
                "route_risk_distance_pct": raw_sig.risk_distance_pct,
                "entry_stop_level": raw_sig.entry_stop_level,
                "allow_position_increase": raw_sig.allow_position_increase,
                "gate_diagnostics": raw_sig.gate_diagnostics,
                "entry_thesis": raw_sig.entry_thesis,
                "last_new_evidence_date": raw_sig.last_new_evidence_date,
                "current_lots": cur_lots,
                "decision_outcome": ("NO_INTENT" if raw_sig.direction == "FLAT" else
                                     "RISK_BLOCKED" if vetted_sig.vetted_direction == "FLAT" else
                                     "ZERO_SIZE" if pos_target.target_lots == 0 else "TARGET_PENDING"),
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
