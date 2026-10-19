#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/execution_engine.py
功能: 阶段 E 真实期货撮合执行与账户盯市核算引擎 (Execution & Accounting Engine)
职责:
  1. 严格履行零未来函数 (Next-Bar Open) 撮合协议: T 日决策，T+1 日以真实开盘价加滑点撮合;
  2. 模拟真实交易所与期货公司摩擦:
     - 交易滑点: 1 tick (1.0 元/吨);
     - 手续费率: 成交额万分之一 (0.01%);
     - 保证金率: 10%;
  3. 严格遵循中国期货市场盯市会计准则 (Mark-to-Market Accounting):
     - 动态权益 = 初始资金 + 累计平仓盈亏 - 累计手续费 + 持仓浮动盈亏（滑点已含成交价）;
     - 占用保证金 = |持仓手数| × 合约乘数 × 当日结算价 × 保证金率;
     - 可用资金 = 动态权益 - 占用保证金;
     - 满足绝对恒等式: 动态权益 ≡ 可用资金 + 占用保证金;
  4. 支持主力换月移仓撮合 (平旧开新与移仓基差结转);
  5. 记录完整闭环交易流水。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd

from stage_e.contract_rollover import RolloverEvent
from stage_e.position_sizer import PositionTarget


@dataclass
class TradeRecord:
    trade_id: str
    prediction_id: str
    contract: str
    side: str  # "BUY_OPEN", "SELL_CLOSE", "SELL_OPEN", "BUY_CLOSE", "ROLL_SWAP"
    quantity: int  # 手数
    entry_time: str
    entry_price: float
    exit_time: str
    exit_price: float
    pnl: float  # 平仓净盈亏 (扣除手续费与滑点后)
    fees: float  # 本笔已平数量分摊的开仓与平仓手续费；滑点已含价格
    risk_plan: str
    execution_deviation: float  # 滑点偏差
    note: str


class ExecutionEngine:
    """
    期货撮合与账户记账引擎
    """

    def __init__(
        self,
        initial_capital: float = 10_000_000.0,
        contract_multiplier: int = 10,  # 螺纹 10 吨/手
        slippage_ticks: float = 1.0,  # 1 tick = 1.0 元/吨
        commission_rate: float = 0.0001,  # 万分之一 (0.01%)
        margin_rate: float = 0.10,  # 保证金率 10%
        rebalance_threshold_ratio: float = 0.10,  # 调仓死区比例 10%
        min_rebalance_lots: int = 5,  # 最小调仓手数死区 5手
        tactical_adapter: Optional[Any] = None,   # 跨周期战术执行适配器 (可选)
    ):
        self.initial_capital = initial_capital
        self.contract_multiplier = contract_multiplier
        self.slippage = slippage_ticks
        self.commission_rate = commission_rate
        self.margin_rate = margin_rate
        self.rebalance_threshold_ratio = rebalance_threshold_ratio
        self.min_rebalance_lots = min_rebalance_lots
        self.tactical_adapter = tactical_adapter

        # 账户实时状态
        self.current_contract: str = "rb2001"
        self.current_lots: int = 0  # +为多头, -为空头, 0为空仓
        self.avg_entry_price: float = 0.0
        self.entry_date: str = ""
        self.entry_prediction_id: str = ""
        self.entry_risk_plan: str = ""

        # 跨期双腿套利实时状态 (Calendar Spread Multi-Leg State)
        self.is_spread_position: bool = False
        self.spread_type: str = ""  # "BULL_SPREAD" or "BEAR_SPREAD"
        self.secondary_contract: str = ""
        self.secondary_lots: int = 0
        self.secondary_avg_entry_price: float = 0.0
        self.secondary_open_fees: float = 0.0
        self.spread_entry_diff: float = 0.0

        # 累计统计量
        self.cumulative_realized_pnl: float = 0.0
        self.cumulative_fees: float = 0.0
        self.cumulative_slippage_cost: float = 0.0
        self.trade_counter: int = 0
        self.open_entry_fees: float = 0.0

        # 历史记录流水
        self.trade_records: List[TradeRecord] = []
        self.daily_snapshots: List[Dict[str, Any]] = []

    def attach_tactical_adapter(self, adapter: Any):
        """挂载跨周期战术执行适配器 (专用于螺纹与热卷)"""
        self.tactical_adapter = adapter

    def get_tactical_status(self) -> Optional[Any]:
        """获取挂载的战术适配器状态快照"""
        if self.tactical_adapter is not None:
            return self.tactical_adapter.get_status()
        return None

    def execute_next_bar(
        self,
        date_str: str,
        target: PositionTarget,
        open_price: float,
        settlement_price: float,
        close_price: float,
        rollover_event: RolloverEvent,
        active_contract_code: str,
        prediction_id: str = "",
        secondary_open_price: Optional[float] = None,
        secondary_settlement_price: Optional[float] = None,
        secondary_close_price: Optional[float] = None,
        secondary_contract_code: Optional[str] = None,
        spread_type: str = "",
    ):
        """
        在 T+1 日开盘执行换月与仓位调整，并在收盘按结算价盯市
        支持跨期双腿套利 (Calendar Spread: Bull & Bear Spread)
        """
        target_lots = target.target_lots
        lot_mult = self.contract_multiplier

        # 0. 跨期双腿套利专属撮合分支
        if self.is_spread_position:
            if target_lots == 0:
                # 跨期双腿全平退出
                # 1) 平前腿 (Primary Leg)
                front_lots = self.current_lots
                sign_front = 1 if front_lots > 0 else -1
                exec_front = open_price - sign_front * self.slippage
                trade_qty_front = abs(front_lots)
                pnl_gross_front = sign_front * (exec_front - self.avg_entry_price) * trade_qty_front * lot_mult
                comm_front = trade_qty_front * lot_mult * exec_front * self.commission_rate
                slip_front = trade_qty_front * lot_mult * self.slippage
                closed_fees_front = comm_front + self.open_entry_fees

                self.cumulative_realized_pnl += pnl_gross_front
                self.cumulative_fees += comm_front
                self.cumulative_slippage_cost += slip_front

                self.trade_counter += 1
                rec_front = TradeRecord(
                    trade_id=f"TRD_{date_str.replace('-', '')}_{self.trade_counter:03d}",
                    prediction_id=self.entry_prediction_id,
                    contract=self.current_contract,
                    side="SELL_CLOSE" if front_lots > 0 else "BUY_CLOSE",
                    quantity=trade_qty_front,
                    entry_time=self.entry_date,
                    entry_price=self.avg_entry_price,
                    exit_time=date_str,
                    exit_price=exec_front,
                    pnl=round(pnl_gross_front - closed_fees_front, 2),
                    fees=round(closed_fees_front, 2),
                    risk_plan=self.entry_risk_plan,
                    execution_deviation=self.slippage,
                    note=f"跨期套利平前腿 [{self.spread_type}]: {target.rationale}",
                )
                self.trade_records.append(rec_front)

                # 2) 平后腿 (Secondary Leg)
                sec_lots = self.secondary_lots
                sign_sec = 1 if sec_lots > 0 else -1
                sec_open = secondary_open_price if (secondary_open_price is not None and secondary_open_price > 0) else open_price
                exec_sec = sec_open - sign_sec * self.slippage
                trade_qty_sec = abs(sec_lots)
                pnl_gross_sec = sign_sec * (exec_sec - self.secondary_avg_entry_price) * trade_qty_sec * lot_mult
                comm_sec = trade_qty_sec * lot_mult * exec_sec * self.commission_rate
                slip_sec = trade_qty_sec * lot_mult * self.slippage
                closed_fees_sec = comm_sec + self.secondary_open_fees

                self.cumulative_realized_pnl += pnl_gross_sec
                self.cumulative_fees += comm_sec
                self.cumulative_slippage_cost += slip_sec

                self.trade_counter += 1
                rec_sec = TradeRecord(
                    trade_id=f"TRD_{date_str.replace('-', '')}_{self.trade_counter:03d}",
                    prediction_id=self.entry_prediction_id,
                    contract=self.secondary_contract,
                    side="SELL_CLOSE" if sec_lots > 0 else "BUY_CLOSE",
                    quantity=trade_qty_sec,
                    entry_time=self.entry_date,
                    entry_price=self.secondary_avg_entry_price,
                    exit_time=date_str,
                    exit_price=exec_sec,
                    pnl=round(pnl_gross_sec - closed_fees_sec, 2),
                    fees=round(closed_fees_sec, 2),
                    risk_plan=self.entry_risk_plan,
                    execution_deviation=self.slippage,
                    note=f"跨期套利平后腿 [{self.spread_type}]: {target.rationale}",
                )
                self.trade_records.append(rec_sec)

                # 重置状态
                self.is_spread_position = False
                self.spread_type = ""
                self.current_lots = 0
                self.avg_entry_price = 0.0
                self.open_entry_fees = 0.0
                self.secondary_contract = ""
                self.secondary_lots = 0
                self.secondary_avg_entry_price = 0.0
                self.secondary_open_fees = 0.0
                self.spread_entry_diff = 0.0
                self.entry_date = ""

        elif not self.is_spread_position and spread_type in ("BULL_SPREAD", "BEAR_SPREAD") and target_lots != 0:
            # 跨期双腿全新开仓 (1:1 严格对冲)
            # 1) 开前腿 (Primary Leg)
            front_lots = target_lots
            sign_front = 1 if front_lots > 0 else -1
            exec_front = open_price + sign_front * self.slippage
            trade_qty_front = abs(front_lots)
            comm_front = trade_qty_front * lot_mult * exec_front * self.commission_rate
            slip_front = trade_qty_front * lot_mult * self.slippage

            self.cumulative_fees += comm_front
            self.cumulative_slippage_cost += slip_front
            self.open_entry_fees = comm_front
            self.current_lots = front_lots
            self.current_contract = active_contract_code
            self.avg_entry_price = exec_front
            self.entry_date = date_str
            self.entry_prediction_id = prediction_id
            self.entry_risk_plan = target.rationale

            # 2) 开后腿 (Secondary Leg: 与前腿严格 1:1 反向对冲)
            sec_lots = -front_lots
            sign_sec = 1 if sec_lots > 0 else -1
            sec_open = secondary_open_price if (secondary_open_price is not None and secondary_open_price > 0) else open_price
            exec_sec = sec_open + sign_sec * self.slippage
            trade_qty_sec = abs(sec_lots)
            comm_sec = trade_qty_sec * lot_mult * exec_sec * self.commission_rate
            slip_sec = trade_qty_sec * lot_mult * self.slippage

            self.cumulative_fees += comm_sec
            self.cumulative_slippage_cost += slip_sec

            self.is_spread_position = True
            self.spread_type = spread_type
            self.secondary_contract = secondary_contract_code or active_contract_code
            self.secondary_lots = sec_lots
            self.secondary_avg_entry_price = exec_sec
            self.secondary_open_fees = comm_sec
            self.spread_entry_diff = exec_front - exec_sec

        else:
            # 0. 战术适配器跨周期双向互锁检查 (专为螺纹与热卷设计)
            if self.tactical_adapter is not None and getattr(self.tactical_adapter, "is_supported", False):
                macro_dir = target.target_direction
                # 若宏观方向改变或清平，通知战术适配器清盘重置
                if macro_dir == "FLAT" or (self.tactical_adapter.macro_direction != "FLAT" and macro_dir != self.tactical_adapter.macro_direction):
                    if self.tactical_adapter.current_position_lots != 0:
                        self.tactical_adapter.force_macro_exit(
                            exit_price=open_price,
                            exit_time=date_str,
                            reason="MACRO_TARGET_FLAT_OR_REVERSED"
                        )
                
                # 若战术层已触发动能耗尽/假突破终止且宏观方向未变，锁定空仓防磨损
                if self.tactical_adapter.is_tactical_terminated and self.tactical_adapter.macro_direction == macro_dir:
                    target_lots = 0

            # 1. 处理主力换月移仓 (Rollover)
            if rollover_event.is_rollover and self.current_lots != 0:
                old_c = rollover_event.old_contract
                new_c = rollover_event.new_contract
                old_open = rollover_event.old_open_price
                new_open = rollover_event.new_open_price

                # 平掉旧合约
                old_lots = self.current_lots
                sign_old = 1 if old_lots > 0 else -1
                exec_old_close = old_open - sign_old * self.slippage

                pnl_gross_old = sign_old * (exec_old_close - self.avg_entry_price) * abs(old_lots) * lot_mult
                fee_old = abs(old_lots) * lot_mult * exec_old_close * self.commission_rate
                slip_old = abs(old_lots) * lot_mult * self.slippage

                self.cumulative_realized_pnl += pnl_gross_old
                self.cumulative_fees += fee_old
                self.cumulative_slippage_cost += slip_old

                self.trade_counter += 1
                rec_old = TradeRecord(
                    trade_id=f"TRD_{date_str.replace('-', '')}_{self.trade_counter:03d}",
                    prediction_id=self.entry_prediction_id,
                    contract=old_c,
                    side="SELL_CLOSE" if old_lots > 0 else "BUY_CLOSE",
                    quantity=abs(old_lots),
                    entry_time=self.entry_date,
                    entry_price=self.avg_entry_price,
                    exit_time=date_str,
                    exit_price=exec_old_close,
                    pnl=round(pnl_gross_old - fee_old - self.open_entry_fees, 2),
                    fees=round(fee_old + self.open_entry_fees, 2),
                    risk_plan=self.entry_risk_plan,
                    execution_deviation=self.slippage,
                    note=f"主力换月平旧仓: {rollover_event.rationale}",
                )
                self.trade_records.append(rec_old)

                self.current_lots = 0
                self.avg_entry_price = 0.0
                self.open_entry_fees = 0.0
                self.current_contract = new_c
            else:
                if self.current_lots and self.current_contract != active_contract_code:
                    raise ValueError("持仓合约改变却没有换月事件")
                self.current_contract = active_contract_code

            # 2. 调仓至目标手数 (target_lots)
            delta_lots = target_lots - self.current_lots

            # 检查调仓缓冲带 (Deadband): 同向加仓时，若手数变动过小则不频繁调仓，降低手续费与滑点磨损；减仓不受阻挡(契约A05.5)
            is_minor_rebalance = False
            if self.current_lots != 0 and abs(target_lots) > abs(self.current_lots) and (self.current_lots * target_lots > 0):
                if (
                    abs(delta_lots) < self.min_rebalance_lots
                    or abs(delta_lots) / abs(self.current_lots) < self.rebalance_threshold_ratio
                ):
                    is_minor_rebalance = True

            if delta_lots != 0 and not is_minor_rebalance:
                sign_trade = 1 if delta_lots > 0 else -1
                exec_price = open_price + sign_trade * self.slippage
                trade_qty = abs(delta_lots)
                trade_turnover = trade_qty * lot_mult * exec_price
                comm = trade_turnover * self.commission_rate
                slip = trade_qty * lot_mult * self.slippage

                self.cumulative_fees += comm
                self.cumulative_slippage_cost += slip

                # 判断是开仓、加仓、减仓还是反手
                if self.current_lots == 0:
                    # 全新开仓
                    self.open_entry_fees = comm
                    self.current_lots = target_lots
                    self.avg_entry_price = exec_price
                    self.entry_date = date_str
                    self.entry_prediction_id = prediction_id
                    self.entry_risk_plan = target.rationale
                elif (self.current_lots > 0 and target_lots > self.current_lots) or (
                    self.current_lots < 0 and target_lots < self.current_lots
                ):
                    self.open_entry_fees += comm
                    # 同向加仓: 更新加权平均开仓价
                    prev_nominal = abs(self.current_lots) * lot_mult * self.avg_entry_price
                    add_nominal = trade_qty * lot_mult * exec_price
                    self.current_lots = target_lots
                    self.avg_entry_price = (prev_nominal + add_nominal) / (
                        abs(self.current_lots) * lot_mult
                    )
                elif (self.current_lots > 0 and target_lots >= 0) or (
                    self.current_lots < 0 and target_lots <= 0
                ):
                    # 同向减仓或清仓
                    close_qty = trade_qty
                    closed_fees = comm + self.open_entry_fees * close_qty / abs(self.current_lots)
                    self.open_entry_fees *= 1 - close_qty / abs(self.current_lots)
                    sign_pos = 1 if self.current_lots > 0 else -1
                    pnl_gross = sign_pos * (exec_price - self.avg_entry_price) * close_qty * lot_mult
                    self.cumulative_realized_pnl += pnl_gross

                    self.trade_counter += 1
                    rec = TradeRecord(
                        trade_id=f"TRD_{date_str.replace('-', '')}_{self.trade_counter:03d}",
                        prediction_id=self.entry_prediction_id,
                        contract=self.current_contract,
                        side="SELL_CLOSE" if self.current_lots > 0 else "BUY_CLOSE",
                        quantity=close_qty,
                        entry_time=self.entry_date,
                        entry_price=self.avg_entry_price,
                        exit_time=date_str,
                        exit_price=exec_price,
                        pnl=round(pnl_gross - closed_fees, 2),
                        fees=round(closed_fees, 2),
                        risk_plan=self.entry_risk_plan,
                        execution_deviation=self.slippage,
                        note=f"主动减仓/止盈止损: {target.rationale}",
                    )
                    self.trade_records.append(rec)

                    self.current_lots = target_lots
                    if self.current_lots == 0:
                        self.avg_entry_price = 0.0
                        self.entry_date = ""
                else:
                    # 反手操作 (例如从多转空，或从空转多): 分解为先全平再开新
                    close_qty = abs(self.current_lots)
                    closed_fees = self.open_entry_fees + comm * close_qty / trade_qty
                    self.open_entry_fees = comm * abs(target_lots) / trade_qty
                    sign_pos = 1 if self.current_lots > 0 else -1
                    pnl_gross = sign_pos * (exec_price - self.avg_entry_price) * close_qty * lot_mult
                    self.cumulative_realized_pnl += pnl_gross

                    self.trade_counter += 1
                    rec = TradeRecord(
                        trade_id=f"TRD_{date_str.replace('-', '')}_{self.trade_counter:03d}",
                        prediction_id=self.entry_prediction_id,
                        contract=self.current_contract,
                        side="SELL_CLOSE" if self.current_lots > 0 else "BUY_CLOSE",
                        quantity=close_qty,
                        entry_time=self.entry_date,
                        entry_price=self.avg_entry_price,
                        exit_time=date_str,
                        exit_price=exec_price,
                        pnl=round(pnl_gross - closed_fees, 2),
                        fees=round(closed_fees, 2),
                        risk_plan=self.entry_risk_plan,
                        execution_deviation=self.slippage,
                        note=f"反手平原仓: {target.rationale}",
                    )
                    self.trade_records.append(rec)

                    # 开立新反向仓位
                    self.current_lots = target_lots
                    self.avg_entry_price = exec_price
                    self.entry_date = date_str
                    self.entry_prediction_id = prediction_id
                    self.entry_risk_plan = target.rationale

        # 3. 日终盯市核算 (Mark-to-Market)
        settle_p = settlement_price if settlement_price > 0 else close_price
        if self.is_spread_position:
            # 跨期套利双腿盯市
            sign_front = 1 if self.current_lots > 0 else -1
            unrealized_pnl_front = (
                sign_front * (settle_p - self.avg_entry_price) * abs(self.current_lots) * lot_mult
            )
            sec_settle = secondary_settlement_price if (secondary_settlement_price is not None and secondary_settlement_price > 0) else (secondary_close_price or settle_p)
            sign_sec = 1 if self.secondary_lots > 0 else -1
            unrealized_pnl_sec = (
                sign_sec * (sec_settle - self.secondary_avg_entry_price) * abs(self.secondary_lots) * lot_mult
            )
            unrealized_pnl = unrealized_pnl_front + unrealized_pnl_sec

            # 上期所同品种跨期套利大边保证金规则: 保证金按持仓大边单边收取
            max_settle = max(settle_p, sec_settle)
            margin_occupied = abs(self.current_lots) * lot_mult * max_settle * self.margin_rate
            nominal_exposure = abs(self.current_lots) * lot_mult * max_settle

        elif self.current_lots != 0:
            sign_cur = 1 if self.current_lots > 0 else -1
            unrealized_pnl = (
                sign_cur * (settle_p - self.avg_entry_price) * abs(self.current_lots) * lot_mult
            )
            margin_occupied = abs(self.current_lots) * lot_mult * settle_p * self.margin_rate
            nominal_exposure = abs(self.current_lots) * lot_mult * settle_p
        else:
            unrealized_pnl = 0.0
            margin_occupied = 0.0
            nominal_exposure = 0.0

        # 动态权益 = 初始资金 + 累计平仓盈亏 - 累计手续费 + 持仓浮动盈亏（滑点已含成交价）
        total_equity = (
            self.initial_capital
            + self.cumulative_realized_pnl
            - self.cumulative_fees
            + unrealized_pnl
        )
        available_cash = total_equity - margin_occupied
        effective_leverage = nominal_exposure / total_equity if total_equity > 0 else 0.0

        # 保存当日快照
        snapshot = {
            "date": date_str,
            "contract": self.current_contract,
            "lots": self.current_lots,
            "avg_entry_price": round(self.avg_entry_price, 2),
            "open_price": open_price,
            "close_price": close_price,
            "settlement_price": settle_p,
            "nominal_exposure": round(nominal_exposure, 2),
            "margin_occupied": round(margin_occupied, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "cumulative_realized_pnl": round(self.cumulative_realized_pnl, 2),
            "cumulative_fees": round(self.cumulative_fees, 2),
            "cumulative_slippage": round(self.cumulative_slippage_cost, 2),
            "total_equity": round(total_equity, 2),
            "available_cash": round(available_cash, 2),
            "effective_leverage": round(effective_leverage, 4),
            "net_asset_value": round(total_equity / self.initial_capital, 6),
            "is_spread_position": self.is_spread_position,
            "spread_type": self.spread_type,
            "secondary_contract": self.secondary_contract,
            "secondary_lots": self.secondary_lots,
        }
        self.daily_snapshots.append(snapshot)
        return snapshot

    def execute_tactical_exit(
        self,
        date_str: str,
        exit_price: float,
        reason: str = "TACTICAL_EXIT",
    ) -> Optional[TradeRecord]:
        """
        在交易日内触发战术退出（初始结构防守止损、跳空断头铡、震荡停滞退出、动能衰竭波段全平）
        按真实滑点和手续费全平当前持仓，并修正当日盯市快照与累计权益
        """
        if self.current_lots == 0:
            return None

        lot_mult = self.contract_multiplier
        close_qty = abs(self.current_lots)
        sign_pos = 1 if self.current_lots > 0 else -1

        # 计算滑点后的成交价格: 平多为卖出(价减滑点)，平空为买入(价加滑点)
        exec_price = exit_price - sign_pos * self.slippage
        trade_turnover = close_qty * lot_mult * exec_price
        comm = trade_turnover * self.commission_rate
        slip = close_qty * lot_mult * self.slippage

        # 累计手续费与滑点成本
        self.cumulative_fees += comm
        self.cumulative_slippage_cost += slip

        # 累计平仓毛盈亏
        pnl_gross = sign_pos * (exec_price - self.avg_entry_price) * close_qty * lot_mult
        self.cumulative_realized_pnl += pnl_gross

        # 闭环手续费分摊: 本次平仓手续费 + 开仓时记录的 open_entry_fees
        closed_fees = comm + self.open_entry_fees
        self.open_entry_fees = 0.0

        self.trade_counter += 1
        rec = TradeRecord(
            trade_id=f"TRD_{date_str.replace('-', '')}_{self.trade_counter:03d}",
            prediction_id=self.entry_prediction_id,
            contract=self.current_contract,
            side="SELL_CLOSE" if self.current_lots > 0 else "BUY_CLOSE",
            quantity=close_qty,
            entry_time=self.entry_date,
            entry_price=self.avg_entry_price,
            exit_time=date_str,
            exit_price=exec_price,
            pnl=round(pnl_gross - closed_fees, 2),
            fees=round(closed_fees, 2),
            risk_plan=f"战术退出: {reason}",
            execution_deviation=self.slippage,
            note=f"战术退出 [{reason}] 成交价={exec_price:.1f}",
        )
        self.trade_records.append(rec)

        # 清空当前持仓状态
        self.current_lots = 0
        self.avg_entry_price = 0.0
        self.entry_date = ""

        # 修正当日日终盯市快照 (动态权益 ≡ 可用资金 + 占用保证金)
        if self.daily_snapshots and self.daily_snapshots[-1]["date"] == date_str:
            snap = self.daily_snapshots[-1]
            snap["lots"] = 0
            snap["avg_entry_price"] = 0.0
            snap["nominal_exposure"] = 0.0
            snap["margin_occupied"] = 0.0
            snap["unrealized_pnl"] = 0.0
            snap["cumulative_realized_pnl"] = round(self.cumulative_realized_pnl, 2)
            snap["cumulative_fees"] = round(self.cumulative_fees, 2)
            snap["cumulative_slippage"] = round(self.cumulative_slippage_cost, 2)

            total_equity = self.initial_capital + self.cumulative_realized_pnl - self.cumulative_fees
            snap["total_equity"] = round(total_equity, 2)
            snap["available_cash"] = round(total_equity, 2)
            snap["effective_leverage"] = 0.0
            snap["net_asset_value"] = round(total_equity / self.initial_capital, 6)
            snap["tactical_exit_reason"] = reason

        return rec

    def get_snapshots_df(self) -> pd.DataFrame:
        """获取每日账户净值明细时序表"""
        df = pd.DataFrame(self.daily_snapshots)
        if not df.empty:
            df["daily_return"] = df["total_equity"].pct_change().fillna(0.0)
            df["peak_equity"] = df["total_equity"].cummax()
            df["drawdown"] = (df["total_equity"] - df["peak_equity"]) / df["peak_equity"]
        return df

    def get_trade_records_df(self) -> pd.DataFrame:
        """获取交易流水表"""
        records = [r.__dict__ for r in self.trade_records]
        return pd.DataFrame(records)
