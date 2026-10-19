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
    ):
        self.initial_capital = initial_capital
        self.contract_multiplier = contract_multiplier
        self.slippage = slippage_ticks
        self.commission_rate = commission_rate
        self.margin_rate = margin_rate
        self.rebalance_threshold_ratio = rebalance_threshold_ratio
        self.min_rebalance_lots = min_rebalance_lots

        # 账户实时状态
        self.current_contract: str = "rb2001"
        self.current_lots: int = 0  # +为多头, -为空头, 0为空仓
        self.avg_entry_price: float = 0.0
        self.entry_date: str = ""
        self.entry_prediction_id: str = ""
        self.entry_risk_plan: str = ""

        # 累计统计量
        self.cumulative_realized_pnl: float = 0.0
        self.cumulative_fees: float = 0.0
        self.cumulative_slippage_cost: float = 0.0
        self.trade_counter: int = 0
        self.open_entry_fees: float = 0.0

        # 历史记录流水
        self.trade_records: List[TradeRecord] = []
        self.daily_snapshots: List[Dict[str, Any]] = []

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
    ):
        """
        在 T+1 日开盘执行换月与仓位调整，并在收盘按结算价盯市
        """
        target_lots = target.target_lots
        lot_mult = self.contract_multiplier

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

        # 检查调仓缓冲带 (Deadband): 同向加减仓时，若手数变动过小则不频繁调仓，降低手续费与滑点磨损
        is_minor_rebalance = False
        if self.current_lots != 0 and abs(target_lots) > abs(self.current_lots) and (self.current_lots * target_lots > 0):
            if (
                abs(delta_lots) < self.min_rebalance_lots
                and abs(delta_lots) / abs(self.current_lots) < self.rebalance_threshold_ratio
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
        if self.current_lots != 0:
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
        }
        self.daily_snapshots.append(snapshot)
        return snapshot

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
