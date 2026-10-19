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
    term_structure_regime: str = "NORMAL_ROLL"


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
        self._by_date: Optional[Dict[str, pd.DataFrame]] = None
        self._spec_indexed: Optional[pd.DataFrame] = None
        self._spec_indexed_set: set = set()
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
        self._by_date = by_date
        self._spec_indexed = spec_df.set_index(["date", "code"])
        self._spec_indexed_set = set(self._spec_indexed.index)
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

    def _calc_dte(self, code_short: str, cur_date_str: str) -> int:
        """根据合约代码数字 (如 2410) 计算距离交割月15日剩余自然日 (DTE)"""
        try:
            clean_code = "".join(filter(str.isdigit, str(code_short))).zfill(4)
            yr = 2000 + int(clean_code[:2])
            mo = int(clean_code[2:])
            exp_dt = pd.Timestamp(year=yr, month=mo, day=15)
            cur_dt = pd.Timestamp(cur_date_str)
            return int((exp_dt - cur_dt).days)
        except Exception:
            return 999

    def get_contract_trio(self, date_str: str) -> Optional[Dict[str, Dict[str, Any]]]:
        """
        获取指定交易日的近月(near)、主力(main)、远月(far)合约三元组价格与DTE:
        - near: 临近交割月主力候选 (通常 DTE 较小，受仓单与虚实博弈压制)
        - main: 当前持仓量最大最活跃主力合约
        - far:  下一届远月主力合约 (通常 DTE 充裕，适于高基差深贴水规避近月仓单)
        """
        active_info = self.get_active_contract(date_str)
        if active_info is None:
            return None

        active_code = str(active_info.get("contract_code_short", "2001")).zfill(4)
        active_dict = dict(active_info)
        active_dict["dte"] = self._calc_dte(active_code, date_str)

        if self._by_date is None or date_str not in self._by_date:
            return {"near": active_dict, "main": active_dict, "far": active_dict}

        today_df = self._by_date[date_str]
        eligible = today_df[today_df.index.str[-2:].isin(self.main_months)].copy()
        if eligible.empty:
            return {"near": active_dict, "main": active_dict, "far": active_dict}

        unexpired_codes = []
        for c in eligible.index:
            dte = self._calc_dte(c, date_str)
            oi = float(eligible.loc[c, "open_interest"])
            if dte > 0 and oi > 0:
                unexpired_codes.append(c)

        if not unexpired_codes:
            return {"near": active_dict, "main": active_dict, "far": active_dict}

        sorted_codes = sorted(unexpired_codes, key=lambda c: (int(c[:2]), int(c[2:])))

        if active_code in sorted_codes:
            idx = sorted_codes.index(active_code)
        else:
            active_code = eligible.loc[sorted_codes].sort_values(["open_interest", "volume"], ascending=False).index[0]
            idx = sorted_codes.index(active_code)

        near_code = sorted_codes[idx - 1] if idx > 0 else active_code
        main_code = active_code
        far_code = sorted_codes[idx + 1] if idx + 1 < len(sorted_codes) else active_code

        def _make_contract_dict(code_s: str) -> Dict[str, Any]:
            row = today_df.loc[code_s]
            settle = float(row.settlement)
            valid_settle = np.isfinite(settle) and float(row.low) <= settle <= float(row.high)
            return {
                "contract_code": f"{self.symbol}{code_s}",
                "contract_code_short": code_s,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "settlement": settle if valid_settle else float(row.close),
                "marking_basis": "SETTLEMENT" if valid_settle else "CLOSE_PROXY",
                "volume": float(row.volume),
                "open_interest": float(row.open_interest),
                "dte": self._calc_dte(code_s, date_str),
            }

        return {
            "near": _make_contract_dict(near_code),
            "main": _make_contract_dict(main_code),
            "far": _make_contract_dict(far_code),
        }

    def get_contract_by_role(self, date_str: str, role: str = "MAIN") -> Optional[Dict[str, Any]]:
        """按角色获取对应合约 ('MAIN', 'NEAR', 'FAR')"""
        trio = self.get_contract_trio(date_str)
        if trio is None:
            return self.get_active_contract(date_str)
        r = role.strip().lower()
        if r in ("near", "far"):
            return trio.get(r, trio["main"])
        return trio.get("main", self.get_active_contract(date_str))

    def get_calendar_spread_pair(self, date_str: str) -> Optional[Dict[str, Any]]:
        """
        获取指定交易日的跨期套利合约对 (Front/Back) 及价差特征:
        - Front 合约: 靠近到期日的近端腿 (承担仓单压制或空配迁徙买平)
        - Back 合约:  较远到期日的远端腿 (承担新主力预期或空配抛压承接)

        配对法则:
        1. 若 near != main 且 near['dte'] <= 65:
           优先构建 NEAR-MAIN 价差对 (pair_type = 'NEAR_MAIN', front=near, back=main, front_role='NEAR', back_role='MAIN')
        2. 若 main != far:
           构建 MAIN-FAR 价差对 (pair_type = 'MAIN_FAR', front=main, back=far, front_role='MAIN', back_role='FAR')
        3. 否则:
           返回 None
        """
        trio = self.get_contract_trio(date_str)
        if trio is None:
            return None
        near = trio.get("near")
        main = trio.get("main")
        far = trio.get("far")
        if near is None or main is None or far is None:
            return None

        front = None
        back = None
        front_role = ""
        back_role = ""
        pair_type = ""

        if near["contract_code"] != main["contract_code"] and near.get("dte", 999) <= 65:
            front = near
            back = main
            front_role = "NEAR"
            back_role = "MAIN"
            pair_type = "NEAR_MAIN"
        elif main["contract_code"] != far["contract_code"]:
            front = main
            back = far
            front_role = "MAIN"
            back_role = "FAR"
            pair_type = "MAIN_FAR"
        else:
            return None

        # 校验双腿数据完整性
        for leg in (front, back):
            for k in ("open", "close", "settlement"):
                val = leg.get(k)
                if val is None or not np.isfinite(val) or val <= 0:
                    return None

        spread_open = float(front["open"]) - float(back["open"])
        spread_close = float(front["close"]) - float(back["close"])
        spread_settle = float(front["settlement"]) - float(back["settlement"])

        return {
            "pair_type": pair_type,
            "front": front,
            "back": back,
            "front_role": front_role,
            "back_role": back_role,
            "spread_open": spread_open,
            "spread_close": spread_close,
            "spread_settle": spread_settle,
            "front_dte": front.get("dte", 999),
            "back_dte": back.get("dte", 999),
        }

    def get_specific_contract(self, date_str: str, contract_code: str) -> Optional[Dict[str, Any]]:
        """获取指定日期的任意具体实约日线行情"""
        code_short = "".join(filter(str.isdigit, str(contract_code))).zfill(4)
        if self._spec_indexed is not None and (date_str, code_short) in getattr(self, "_spec_indexed_set", set()):
            row = self._spec_indexed.loc[(date_str, code_short)]
            settle = float(row.settlement)
            valid_settle = np.isfinite(settle) and float(row.low) <= settle <= float(row.high)
            return {
                "contract_code": f"{self.symbol}{code_short}",
                "contract_code_short": code_short,
                "open": float(row.open),
                "high": float(row.high),
                "low": float(row.low),
                "close": float(row.close),
                "settlement": settle if valid_settle else float(row.close),
                "marking_basis": "SETTLEMENT" if valid_settle else "CLOSE_PROXY",
                "volume": float(row.volume),
                "open_interest": float(row.open_interest),
                "dte": self._calc_dte(code_short, date_str),
            }
        return self.get_active_contract(date_str)

    def get_term_structure_regime(
        self, date_str: str, basis_rate: float, dte: float, pct_basis_1y: Optional[float] = None
    ) -> Dict[str, Any]:
        """
        基于真实微观博弈与交割规则的期限结构状态诊断器:
        1. HEDGING_MIGRATION (高基差/深贴水空配迁徙驱动):
           产业空头因限仓/发票约束无法交割，被迫买平近月、抛远月新主力；
           行为指引: 近月严禁追空，多头延后移仓享受买平溢价。
        2. RECEIPT_PRESSURE (低基差/升水实物仓单压制与虚实博弈):
           期现正套窗口打开，现货商在交割库注册大量仓单在近月交割，多头无接货能力踩踏砍仓；
           行为指引: 近月绝对禁多博收敛，多头紧急提前移仓远月。
        3. NORMAL_ROLL: 常规平稳换月。
        """
        is_contango = (basis_rate <= 0.005) or (pct_basis_1y is not None and pct_basis_1y <= 0.20)
        is_high_basis = (pct_basis_1y is not None and pct_basis_1y >= 0.40) or (basis_rate >= 0.035)

        if dte <= 45.0 and is_contango and not is_high_basis:
            return {
                "regime": "RECEIPT_PRESSURE",
                "rationale": f"低基差/升水(基差率={basis_rate*100:.2f}%)临近交割(DTE={dte:.0f})，实物仓单压制，绝对禁止近月做多，多头提前移仓",
                "recommended_action_long": "EARLY_ROLL_OR_EXIT",
                "recommended_action_short": "SAFE_TO_HOLD",
            }
        elif (30.0 <= dte <= 65.0) and (basis_rate >= 0.035 or (pct_basis_1y is not None and pct_basis_1y >= 0.70)):
            return {
                "regime": "HEDGING_MIGRATION",
                "rationale": f"高基差深贴水(基差率={basis_rate*100:.2f}%)换月窗口(DTE={dte:.0f})，空配迁徙买平潮，近月严禁追空，多头延后移仓",
                "recommended_action_long": "DELAY_ROLL_HARVEST_PREMIUM",
                "recommended_action_short": "VETO_NEAR_MONTH_SHORT",
            }
        else:
            return {
                "regime": "NORMAL_ROLL",
                "rationale": "期限结构平稳，按标准持仓量轮换规则执行移仓",
                "recommended_action_long": "NORMAL_ROLL",
                "recommended_action_short": "NORMAL_ROLL",
            }

    def check_rollover_event(
        self,
        date_str: str,
        basis_rate: Optional[float] = None,
        dte: Optional[float] = None,
        pct_basis_1y: float = 0.5,
    ) -> RolloverEvent:
        """检查指定交易日是否触发主力换月移仓事件，并附带期限结构微观诊断"""
        info = self.get_active_contract(date_str)
        regime_info = "NORMAL_ROLL"
        if basis_rate is not None and dte is not None:
            regime_diag = self.get_term_structure_regime(date_str, basis_rate, dte, pct_basis_1y)
            regime_info = regime_diag["regime"]

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
                term_structure_regime=regime_info,
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
            rationale=f"主力移仓: 由 {old_c} 换至 {new_c}, 跨期开盘价差={spread:+.1f}元/吨 [期限结构: {regime_info}]",
            term_structure_regime=regime_info,
        )

    def get_full_map(self) -> pd.DataFrame:
        """获取全历史活跃映射表"""
        return self._daily_active_map.copy()
