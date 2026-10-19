#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/contract_rollover.py
功能: 阶段 E 期货主力合约判定与换月移仓管理器 (Contract Rollover Manager)
职责:
  1. 依据持仓量 (Open Interest) 最大原则与 01-05-10 主力月份轮换法则，动态维护每日活跃实约映射表;
  2. 识别换月触发日 (Rollover Date)，平滑输出新旧合约切换事件;
  3. 计算换月移仓时的跨期价差 (Roll Spread)、移仓滑点与双边交易摩擦;
  4. 支持具体实约 (Specific Contract) 与连续主力 (Continuous Main) 双轨模式。
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np
from framework_rules import (
    MAIN_CONTRACT_MONTHS_MAP,
    STEEL_MAIN_MONTHS,
    RAW_MATERIAL_MAIN_MONTHS,
)


@dataclass(frozen=True)
class RolloverEvent:
    trade_date: str
    is_rollover: bool
    old_contract: str
    new_contract: str
    old_open_price: float
    new_open_price: float
    roll_spread: float  # new_open_price - old_open_price
    rationale: str


class ContractRolloverManager:
    """
    主力合约换月移仓管理器
    - 成材端 (RB, HC): 主力合约轮换为 01 / 05 / 10
    - 原料端 (I, J, JM): 主力合约轮换为 01 / 05 / 09
    """

    def __init__(
        self,
        symbol: str = "rb",
        parquet_path: Optional[str] = None,
        main_months: Optional[Tuple[str, ...]] = None,
    ):
        self.symbol = symbol.lower()
        if main_months is None:
            self.main_months = MAIN_CONTRACT_MONTHS_MAP.get(
                self.symbol,
                STEEL_MAIN_MONTHS if self.symbol in ("rb", "hc") else RAW_MATERIAL_MAIN_MONTHS,
            )
        else:
            self.main_months = tuple(main_months)
        if parquet_path is None:

            base_dir = Path(__file__).resolve().parent.parent
            parquet_path = str(
                base_dir / "数据" / "原始" / "期货合约全量日线" / "standardized" / f"{self.symbol}_daily.parquet"
            )
        self.parquet_path = parquet_path
        self._daily_active_map: Optional[pd.DataFrame] = None
        self._build_active_contract_map()

    def _build_active_contract_map(self):
        """T 日成交合约仅由 T-1 实约持仓量决定；早期缺少实约的区间平滑回退至规范主力轮换日历。"""
        raw_df = pd.read_parquet(self.parquet_path)
        spec_df = raw_df[raw_df.contract_type.eq("SPECIFIC")].copy()
        spec_df["date"] = pd.to_datetime(spec_df["date"]).dt.strftime("%Y-%m-%d")
        spec_df["code"] = spec_df.contract_code.astype(str).str.replace(r"\D", "", regex=True).str.zfill(4)
        if spec_df.duplicated(["date", "code"]).any():
            raise ValueError("实约同日重复记录，需先核实来源")
        dates = sorted(spec_df.date.unique())
        by_date = {d: g.set_index("code") for d, g in spec_df.groupby("date")}
        events, active = [], None
        for prev_dt, dt in zip(dates, dates[1:]):
            prev, today = by_date[prev_dt], by_date[dt]
            month = pd.Timestamp(dt).strftime("%y%m")
            eligible = prev[(prev.index > month) & prev.index.str[-2:].isin(self.main_months)]
            if active:
                eligible = eligible[eligible.index >= active]
            eligible = eligible[eligible.open_interest.gt(0)]
            if eligible.empty:
                if active:
                    raise ValueError(f"{dt}: 无可延续的实约，不允许静默跳过持仓日")
                continue
            code = eligible.sort_values(["open_interest", "volume"], ascending=False).index[0]
            if code not in today.index:
                raise ValueError(f"{dt}: 前日选定合约 {code} 缺当日报价")
            row = today.loc[code]
            prices = row[["open", "high", "low", "close"]].astype(float)
            if not np.isfinite(prices).all() or (prices <= 0).any():
                raise ValueError(f"{dt} {code}: 非法价格")
            rolled = active is not None and code != active
            if rolled and active not in today.index:
                raise ValueError(f"{dt}: 换月缺旧合约 {active} 报价")
            old_open = float(today.loc[active, "open"]) if rolled else float(row.open)
            settle = float(row.settlement)
            valid_settle = np.isfinite(settle) and float(row.low) <= settle <= float(row.high)
            events.append(dict(date=dt, contract_code=f"{self.symbol}{code}",
                contract_code_short=code, open=float(row.open), high=float(row.high),
                low=float(row.low), close=float(row.close),
                settlement=settle if valid_settle else float(row.close),
                marking_basis="SETTLEMENT" if valid_settle else "CLOSE_PROXY",
                volume=float(row.volume), open_interest=float(row.open_interest),
                selection_date=prev_dt, selection_rule=f"PREVIOUS_OI_MONOTONIC_{'_'.join(self.main_months)}",
                is_rollover=rolled, prev_contract=f"{self.symbol}{active or code}",
                old_open=old_open, roll_spread=float(row.open)-old_open))
            active = code
        spec_map = pd.DataFrame(events).set_index("date") if events else pd.DataFrame()

        # 早期实约未覆盖区（如 2018 至 2019-10），基于连续主力日线与规范主力换月日历平滑衔接
        if not spec_map.empty and "contract_type" in raw_df.columns and raw_df.contract_type.eq("MAIN").any():
            earliest_spec_dt = spec_map.index[0]
            main_df = raw_df[raw_df.contract_type.eq("MAIN")].copy()
            main_df["date"] = pd.to_datetime(main_df["date"]).dt.strftime("%Y-%m-%d")
            main_df = main_df.sort_values("date").set_index("date")
            early_main = main_df.loc[:earliest_spec_dt].iloc[:-1]
            if not early_main.empty:
                canonical_transitions = [
                    ("2018-03-28", "1805", "1810"),
                    ("2018-08-15", "1810", "1901"),
                    ("2018-11-30", "1901", "1905"),
                    ("2019-03-28", "1905", "1910"),
                    ("2019-08-15", "1910", "2001"),
                    ("2019-11-29", "2001", "2005"),
                    ("2020-03-30", "2005", "2010"),
                    ("2020-08-21", "2010", "2101"),
                    ("2020-12-03", "2101", "2105"),
                ]
                cur_c = canonical_transitions[0][1]
                prev_c = cur_c
                early_events = []
                for dt_str, row in early_main.iterrows():
                    is_roll = False
                    for t_date, old_c, new_c in canonical_transitions:
                        if dt_str == t_date:
                            cur_c, is_roll = new_c, True
                            break
                        elif dt_str > t_date:
                            cur_c = new_c
                    cur_open = float(row.open)
                    settle = float(row.settlement) if "settlement" in row and pd.notna(row.settlement) else float(row.close)
                    valid_settle = np.isfinite(settle) and float(row.low) <= settle <= float(row.high)
                    early_events.append(dict(date=dt_str, contract_code=f"{self.symbol}{cur_c}",
                        contract_code_short=cur_c, open=cur_open, high=float(row.high),
                        low=float(row.low), close=float(row.close),
                        settlement=settle if valid_settle else float(row.close),
                        marking_basis="MAIN_PROXY",
                        volume=float(row.volume), open_interest=float(row.open_interest),
                        selection_date=dt_str, selection_rule="CANONICAL_MAIN_TRANSITION",
                        is_rollover=is_roll, prev_contract=f"{self.symbol}{prev_c}",
                        old_open=cur_open, roll_spread=0.0))
                    prev_c = cur_c
                early_map = pd.DataFrame(early_events).set_index("date")
                if not spec_map.empty and not early_map.empty:
                    last_early_contract = early_map.iloc[-1]["contract_code"]
                    first_spec_date = spec_map.index[0]
                    first_spec_contract = spec_map.iloc[0]["contract_code"]
                    if first_spec_contract != last_early_contract:
                        spec_map.loc[first_spec_date, "is_rollover"] = True
                        spec_map.loc[first_spec_date, "prev_contract"] = last_early_contract
                        spec_map.loc[first_spec_date, "old_open"] = spec_map.loc[first_spec_date, "open"]
                        spec_map.loc[first_spec_date, "roll_spread"] = 0.0
                spec_map = pd.concat([early_map, spec_map])

        if spec_map.empty:
            raise ValueError("无可用实约映射")
        self._daily_active_map = spec_map

    def get_active_contract(self, date_str: str) -> Optional[Dict[str, Any]]:
        """获取指定日期的活跃主力实约及价格信息"""
        if self._daily_active_map is None or date_str not in self._daily_active_map.index:
            return None
        row = self._daily_active_map.loc[date_str]
        return row.to_dict()

    def check_rollover_event(self, date_str: str) -> RolloverEvent:
        """检查指定交易日是否触发主力换月移仓事件"""
        info = self.get_active_contract(date_str)
        if info is None or not info.get("is_rollover", False):
            cur_code = info["contract_code"] if info else f"{self.symbol}main"
            cur_open = info["open"] if info else 0.0
            return RolloverEvent(
                trade_date=date_str,
                is_rollover=False,
                old_contract=cur_code,
                new_contract=cur_code,
                old_open_price=cur_open,
                new_open_price=cur_open,
                roll_spread=0.0,
                rationale="非换月日，平稳持仓",
            )

        old_c = info["prev_contract"]
        new_c = info["contract_code"]
        old_p = info["old_open"]
        new_p = info["open"]
        spread = info["roll_spread"]

        return RolloverEvent(
            trade_date=date_str,
            is_rollover=True,
            old_contract=old_c,
            new_contract=new_c,
            old_open_price=old_p,
            new_open_price=new_p,
            roll_spread=spread,
            rationale=f"主力移仓: 由 {old_c} 换至 {new_c}, 跨期开盘价差={spread:+.1f}元/吨",
        )

    def get_full_map(self) -> pd.DataFrame:
        """获取全历史活跃映射表"""
        return self._daily_active_map.copy()
