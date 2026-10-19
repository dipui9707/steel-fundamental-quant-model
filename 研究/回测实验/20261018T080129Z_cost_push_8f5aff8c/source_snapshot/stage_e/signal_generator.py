#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/signal_generator.py
功能: 阶段 E 策略交易信号生成器 (Trading Signal Generator)
职责:
  严格恪守 State != Position 铁律:
  1. 将阶段 C 产业状态矩阵与阶段 B 微观量价特征转换为策略交易信号;
  2. 落地多维度前置过滤器:
     - 产业基本面方向 (Fundamental Direction);
     - 现货微观确认 (Spot Micro Confirmation / Basis Percentile);
     - 价格均线顺势动量 (Momentum & MA Confirmation);
     - 模型置信度底线 (Confidence Score Threshold >= 40);
     - 宏观冲击单向过滤器 (Macro Shock Direction Filter);
  3. 支持三大策略模式:
     - QUANT_CORE: 阶段 E 核心量化基本面策略 (带现货与动量过滤);
     - RAW_FUNDAMENTAL: 纯基本面方向对照策略;
     - BENCHMARK_BUY_HOLD: 基准买入持有策略。
"""

from dataclasses import dataclass, replace
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np
from framework_rules import HIGH_VOL_THRESHOLD, MA_STOP_BUFFER
from stage_c.state_fundamental import is_winter_restocking_season


@dataclass(frozen=True)
class TradingSignal:
    trade_date: str
    symbol: str
    direction: str  # "LONG", "SHORT", "FLAT"
    strength: float  # 0.0 ~ 1.0
    confidence_score: float  # 0 ~ 100
    spot_confirmed: bool
    momentum_confirmed: bool
    strategy_name: str
    rationale: str
    is_pilot_squeeze: bool = False
    is_right_side_trigger: bool = False
    is_high_vol_pilot: bool = False
    carry_regime: str = "NEUTRAL"
    carry_multiplier: float = 1.0
    entry_driver: str = "FUNDAMENTAL"
    participation_stage: str = "NONE"
    entry_trigger: str = ""
    invalidation_reason: str = ""
    risk_budget_fraction: Optional[float] = None
    strategy_leverage_cap: Optional[float] = None
    risk_distance_pct: Optional[float] = None
    allow_position_increase: bool = True
    entry_stop_level: Optional[float] = None
    gate_diagnostics: str = ""
    entry_thesis: str = ""
    last_new_evidence_date: str = ""
    strategy_margin_utilization: Optional[float] = None


class SignalGenerator:
    """
    策略信号生成器
    """

    def __init__(
        self,
        confidence_threshold: float = 40.0,
        horizon_mode: str = "MULTI_HORIZON",
        enable_cost_push_dual_drive: bool = True,
        space_thresh: float = 0.012,
        risk_reward_ratio: float = 2.0,
        liquidity_thresh: float = 0.10,
        cny_week_window: Tuple[int, int] = (-4, 3),
        carry_headwind_thresh_high: float = 0.85,
        carry_headwind_thresh_low: float = 0.15,
        carry_mult_up: float = 1.05,
        carry_mult_down: float = 0.85,
        carry_tailwind_long_thresh: float = 0.60,
        carry_headwind_long_thresh: float = 0.35,
        carry_tailwind_short_thresh: float = 0.40,
        carry_headwind_short_thresh: float = 0.65,
        enable_carry_gate: bool = False,
        enable_carry_sizer: bool = False,
        enable_mismatch_governance: bool = True,
        mismatch_far_month_dte: float = 65.0,
        mismatch_near_month_dte: float = 50.0,
        mismatch_margin_ceiling: float = 100.0,
        enable_receipt_pressure_gate: bool = True,
        receipt_pressure_dte: float = 45.0,
        receipt_pressure_basis_rate: float = 0.005,
        receipt_pressure_basis_val: float = 15.0,
        enable_hedging_migration_gate: bool = True,
        hedging_migration_min_dte: float = 30.0,
        hedging_migration_max_dte: float = 65.0,
        hedging_migration_basis_rate: float = 0.035,
        hedging_migration_basis_val: float = 120.0,
        enable_two_stage_breakdown: bool = True,
    ):
        self.confidence_threshold = confidence_threshold
        self.horizon_mode = horizon_mode
        self.enable_cost_push_dual_drive = enable_cost_push_dual_drive
        self.space_thresh = space_thresh
        self.risk_reward_ratio = risk_reward_ratio
        self.liquidity_thresh = liquidity_thresh
        self.cny_week_window = cny_week_window
        self.carry_headwind_thresh_high = carry_headwind_thresh_high
        self.carry_headwind_thresh_low = carry_headwind_thresh_low
        self.carry_mult_up = carry_mult_up
        self.carry_mult_down = carry_mult_down
        self.carry_tailwind_long_thresh = carry_tailwind_long_thresh
        self.carry_headwind_long_thresh = carry_headwind_long_thresh
        self.carry_tailwind_short_thresh = carry_tailwind_short_thresh
        self.carry_headwind_short_thresh = carry_headwind_short_thresh
        self.enable_carry_gate = enable_carry_gate
        self.enable_carry_sizer = enable_carry_sizer
        self.enable_mismatch_governance = enable_mismatch_governance
        self.mismatch_far_month_dte = mismatch_far_month_dte
        self.mismatch_near_month_dte = mismatch_near_month_dte
        self.mismatch_margin_ceiling = mismatch_margin_ceiling
        self.enable_receipt_pressure_gate = enable_receipt_pressure_gate
        self.receipt_pressure_dte = receipt_pressure_dte
        self.receipt_pressure_basis_rate = receipt_pressure_basis_rate
        self.receipt_pressure_basis_val = receipt_pressure_basis_val
        self.enable_hedging_migration_gate = enable_hedging_migration_gate
        self.hedging_migration_min_dte = hedging_migration_min_dte
        self.hedging_migration_max_dte = hedging_migration_max_dte
        self.hedging_migration_basis_rate = hedging_migration_basis_rate
        self.hedging_migration_basis_val = hedging_migration_basis_val
        self.enable_two_stage_breakdown = enable_two_stage_breakdown

    def generate_signal(
        self,
        date_str: str,
        state_row: pd.Series,
        feature_row: pd.Series,
        strategy_mode: str = "QUANT_CORE",
        current_holding_direction: str = "FLAT",
    ) -> TradingSignal:
        """
        根据指定模式生成单日交易信号
        """
        if strategy_mode == "BENCHMARK_BUY_HOLD":
            return self._generate_benchmark_signal(date_str, state_row, feature_row)
        elif strategy_mode == "RAW_FUNDAMENTAL":
            return self._generate_raw_fundamental_signal(date_str, state_row, feature_row)
        elif strategy_mode == "QUANT_CORE":
            return self._generate_quant_core_signal(
                date_str, state_row, feature_row, current_holding_direction=current_holding_direction
            )
        else:
            raise ValueError(f"Unknown strategy_mode: {strategy_mode}")

    def _generate_benchmark_signal(
        self, date_str: str, state_row: pd.Series, feature_row: pd.Series
    ) -> TradingSignal:
        """基准策略: 始终看多持仓"""
        return TradingSignal(
            trade_date=date_str,
            symbol="RB",
            direction="LONG",
            strength=1.0,
            confidence_score=100.0,
            spot_confirmed=True,
            momentum_confirmed=True,
            strategy_name="BENCHMARK_BUY_HOLD",
            rationale="基准长期持有螺纹主力多头",
        )

    def _generate_raw_fundamental_signal(
        self, date_str: str, state_row: pd.Series, feature_row: pd.Series
    ) -> TradingSignal:
        """纯基本面策略: 仅看供需方向，无现货确认与均线时机"""
        fdir = str(state_row.get("fundamental_direction", "Neutral"))
        fscore = float(state_row.get("fbs_score", state_row.get("fundamental_score", 0.0)))
        conf = float(state_row.get("confidence_score", 50.0))

        if fdir == "Bullish":
            direction = "LONG"
            strength = min(1.0, max(0.3, abs(fscore) / 40.0))
            rationale = f"纯基本面看多 (FBS={fscore:.1f})"
        elif fdir == "Bearish":
            direction = "SHORT"
            strength = min(1.0, max(0.3, abs(fscore) / 40.0))
            rationale = f"纯基本面看空 (FBS={fscore:.1f})"
        else:
            direction = "FLAT"
            strength = 0.0
            rationale = f"纯基本面中性 (FBS={fscore:.1f})"

        return TradingSignal(
            trade_date=date_str,
            symbol="RB",
            direction=direction,
            strength=strength,
            confidence_score=conf,
            spot_confirmed=False,
            momentum_confirmed=False,
            strategy_name="RAW_FUNDAMENTAL",
            rationale=rationale,
        )

    def _generate_quant_core_signal(
        self,
        date_str: str,
        state_row: pd.Series,
        feature_row: pd.Series,
        current_holding_direction: str = "FLAT",
    ) -> TradingSignal:
        """
        Stage E 核心量化基本面策略:
        先生成基础量化基本面信号，再由行情状态治理层 (Regime Governance) 对特定宏观与产业状态执行权威门禁与专属赋能。
        """
        base_sig = self._generate_quant_core_base_signal(
            date_str, state_row, feature_row, current_holding_direction=current_holding_direction
        )
        return self._apply_regime_governance(
            base_sig, date_str, state_row, feature_row, current_holding_direction=current_holding_direction
        )

    def _apply_regime_governance(
        self,
        sig: TradingSignal,
        date_str: str,
        state_row: pd.Series,
        feature_row: pd.Series,
        current_holding_direction: str = "FLAT",
    ) -> TradingSignal:
        """
        行情状态治理层 (Regime Governance):
        针对特定宏观与产业行情状态实施结构化策略调度:
        1. 宏观发债强刺激上升通道防逆势做空门禁 (杜绝 2020-07 梅雨淡季累库逆势做空 -229万);
        2. 成本推升牛市解耦低毛利禁多锁与低置信度门禁 (捕获 2020 Q4 原料逼挤推升 800 点大浪);
        3. 强 Backwardation 负 Carry 极限地板主动平空止盈 (杜绝 2021-11-17 换月到 3,811 极限地板打损 -147万);
        4. 箱体震荡叠加原料暴跌与深贴水防追多门禁 (杜绝 2021-08-13 假突破追多 -133万)。
        """
        c = float(feature_row.get("rb_close", 0.0))
        ma20 = float(feature_row.get("cp_ma20", feature_row.get("ma_20", c)))
        ma60 = float(feature_row.get("ma_60", np.nan))
        ma5 = float(feature_row.get("cp_ma5", feature_row.get("ma_5", c)))
        pacing_reg = str(state_row.get("macro_fiscal_regime", feature_row.get("pacing_regime", "发债平稳运行期")))
        macro_bias = str(state_row.get("macro_policy_bias", "Neutral"))
        is_complex_uptrend = bool(feature_row.get("is_ferrous_complex_uptrend", True))
        cost_push_spread = float(feature_row.get("cost_push_spread_5d", 0.0))
        pct_basis_1y = float(feature_row.get("pct_basis_tier3_1y", feature_row.get("pct_basis_tier3", 0.5)))
        mkt_struct = str(state_row.get("market_structure", "Range"))
        pct_ry = float(feature_row.get("pct_roll_yield_1y", feature_row.get("pct_roll_yield", 0.5)))
        r_low = float(feature_row.get("rolling_low_20", 0.0))
        conf = float(state_row.get("confidence_score", 50.0))
        vmm = float(feature_row.get("virtual_mill_margin", 0.0))
        pct_vmm = float(feature_row.get("pct_virtual_mill_margin", 0.5))
        pct_vmm_1y = float(feature_row.get("pct_virtual_mill_margin_1y", pct_vmm))
        profit_bf = float(feature_row.get("profit_bf", np.nan))
        cost_bf = float(feature_row.get("cost_bf", c))
        cost_cash_floor = float(feature_row.get("cost_cash_floor", cost_bf - 250.0))
        cost_regime = str(state_row.get("cost_boundary_regime", "合理利润运行"))
        r_high60 = float(feature_row.get("rolling_high_60", np.nan))
        outflow_pct = float(feature_row.get("pct_flow_hz_outflow", 0.5))

        # 产业四支柱法则与高利润大牛市判定 (与base_signal对齐，避免反弹止盈误伤主升浪大牛市)
        is_board_high_margin_trend = (
            (vmm >= 450.0 or (pct_vmm >= 0.70 and vmm >= 200.0) or (pct_vmm_1y >= 0.70 and vmm >= 200.0) or (not np.isnan(profit_bf) and profit_bf >= 350.0))
            and (np.isnan(ma60) or c >= ma60 or ma20 >= ma60)
        )
        is_supply_high_or_rising = bool(feature_row.get("is_supply_high_or_rising", True))
        is_demand_high_or_stable = bool(feature_row.get("is_demand_high_or_stable", True))
        is_high_margin_bull_trend = (
            is_board_high_margin_trend
            and is_complex_uptrend
            and is_supply_high_or_rising
            and is_demand_high_or_stable
        )

        leader_type = str(feature_row.get("dominant_leader_type", state_row.get("dominant_leader_type", "")))
        is_raw_sq = bool(feature_row.get("is_raw_material_squeeze", False))
        max_raw_sq = max(
            float(feature_row.get("squeeze_index", 0.0)),
            float(feature_row.get("i_squeeze_index", 0.0)),
            float(feature_row.get("jm_squeeze_index", 0.0)),
            float(feature_row.get("j_squeeze_index", 0.0)),
        )
        is_raw_cost_pushing = (cost_push_spread > 0.015) and (
            leader_type == "RAW_MATERIAL_SHOCK" or is_raw_sq or max_raw_sq >= 2.0
        )
        is_sustained_cost_push = (
            is_raw_cost_pushing
            and (pct_basis_1y >= 0.40)
            and (outflow_pct >= 0.30)
            and (c >= cost_cash_floor)
        )

        # 1. 宏观发债强刺激上升通道防逆势做空门禁 (2020-07)
        is_macro_uptrend = (
            (pacing_reg in ["发债高速冲刺期", "发债预期加速期"])
            and (macro_bias == "Stimulus")
            and is_complex_uptrend
            and (not np.isnan(ma60) and c >= ma60)
        )
        if is_macro_uptrend and sig.direction == "SHORT" and current_holding_direction == "FLAT":
            return replace(
                sig,
                direction="FLAT",
                strength=0.0,
                rationale="宏观强刺激上升通道防逆势做空 (2020-07梅雨淡季累库一票否决开空)",
            )

        # 2. 成本推升牛市解耦低毛利禁多锁 (2020 Q4)
        is_cost_push_bull = (
            is_complex_uptrend
            and (c >= ma20 * 0.99)
            and (not np.isnan(ma60) and c >= ma60 * 0.98)
            and (cost_push_spread > 0.015)
            and (pct_basis_1y >= 0.25)
        )
        if is_cost_push_bull and current_holding_direction == "FLAT" and sig.direction == "FLAT":
            if (c >= ma20 * 0.99) and (c <= ma20 * 1.035) and (ma5 >= ma20 * 0.99):
                stop_lvl = ma20 * 0.985
                dist_pct = max(0.02, (c - stop_lvl) / c) if c > 0 else float(feature_row.get("risk_distance_pct", 0.035))
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="LONG",
                    strength=0.55,
                    confidence_score=conf,
                    spot_confirmed=True,
                    momentum_confirmed=True,
                    strategy_name="QUANT_CORE",
                    rationale="成本推升牛市回踩MA20企稳，解耦低毛利禁多锁做多",
                    entry_driver="COST_EXPECTATION",
                    strategy_margin_utilization=0.30,
                    risk_distance_pct=float(dist_pct),
                    entry_stop_level=float(stop_lvl),
                )

        # 3. 强 Backwardation 极限地板负 Carry 止盈 (2021-11-17): 仅在右侧企稳反弹(c >= ma5 或反弹脱离大底)时止盈，单边破位探底过程中不提前离场
        if current_holding_direction == "SHORT" and pct_ry >= 0.85:
            downside_space = (c - r_low) / c if (r_low > 0 and c > 0) else 0.0
            is_stabilized_rebound = (c >= ma5) or (c >= r_low * 1.025)
            if downside_space < 0.02 and is_stabilized_rebound and (c < ma60 if not np.isnan(ma60) else True):
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="FLAT",
                    strength=0.0,
                    confidence_score=conf,
                    spot_confirmed=True,
                    momentum_confirmed=True,
                    strategy_name="QUANT_CORE",
                    rationale=f"强Backwardation极限地板负Carry(RollYield={pct_ry:.2f})企稳反弹，平空止盈",
                    entry_driver="CARRY_FLOOR_EXIT",
                    invalidation_reason="STRONG_BACKWARDATION_FLOOR",
                )

        # 4. 原料暴跌且深贴水期防追多 (2021-08-13)
        if sig.direction == "LONG" and current_holding_direction == "FLAT":
            if cost_push_spread < -0.02 and pct_basis_1y < 0.25 and mkt_struct == "Range":
                return replace(
                    sig,
                    direction="FLAT",
                    strength=0.0,
                    rationale="箱体震荡叠加原料暴跌与深贴水，一票否决追多",
                )

        # 5. 极值深度贴水极限地板防盲目追空 (RY>=0.90 且 0 <= downside_space < 0.015)
        # 杜绝在深贴水极值地板盲目开空被动砍损 (例如 2021-11-17 换月到 3811 极值地板被动砍损 -318万)
        if current_holding_direction == "FLAT" and sig.direction == "SHORT":
            downside_space = (c - r_low) / c if (r_low > 0 and c > 0) else 0.0
            if pct_ry >= 0.90 and (0.0 <= downside_space < 0.015):
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="FLAT",
                    strength=0.0,
                    confidence_score=conf,
                    spot_confirmed=False,
                    momentum_confirmed=False,
                    strategy_name="QUANT_CORE",
                    rationale=f"极值深度贴水地板区(RY分位={pct_ry:.2f}, 空间={downside_space*100:.1f}%)一票否决追空，严防超跌反抽打损",
                )

        # 6. 实物仓单压制与虚实博弈门禁 (Receipt Pressure Gate - 用户核心真实期限结构机理)
        # 物理事实: 当期现平水甚至升水(Contango, basis_rate <= 0.005 或 pct_basis_1y <= 0.20)，且临近交割月(DTE <= 45天)
        # 期现正套无风险窗口打开，现货商在交割库注册天量标准仓单并在近月做空锁定交割利润。
        # 临近交割投机多头无接货能力踩踏砍仓，近月旧主力面临巨大仓单压制与虚实博弈挤仓风险。
        # 铁律: 绝对禁止在近月旧主力上盲目做多“博期现收敛”，严防被天量交割仓单砸死!
        basis_rate = float(feature_row.get("basis_rate_tier3", feature_row.get("basis_rate", 0.0)))
        dte = float(feature_row.get("contract_dte", feature_row.get("dte", 999.0)))
        basis_val = float(feature_row.get("basis_tier3", feature_row.get("basis_zhongtian", feature_row.get("basis", 0.0))))

        if self.enable_receipt_pressure_gate:
            is_receipt_pressure_window = (
                (dte <= self.receipt_pressure_dte)
                and (pct_basis_1y <= 0.35)
                and (basis_rate <= self.receipt_pressure_basis_rate or basis_val <= self.receipt_pressure_basis_val or pct_basis_1y <= 0.20)
                and not is_high_margin_bull_trend
            )
            if is_receipt_pressure_window and sig.direction == "LONG" and current_holding_direction == "FLAT":
                return replace(
                    sig,
                    direction="FLAT",
                    strength=0.0,
                    rationale=f"低基差/升水临近交割(DTE={dte:.0f}天, 基差率={basis_rate*100:.2f}%)，实物仓单压顶与虚实博弈，绝对禁止近月做多博期现收敛",
                    invalidation_reason="RECEIPT_PRESSURE_NEAR_MONTH",
                )

        # 7. 套保空配迁徙驱动防踩踏门禁 (Hedging Migration Gate - 用户核心真实期限结构机理)
        # 物理事实: 当现货坚挺、期货深度贴水(basis_rate >= 0.035 或 pct_basis_1y >= 0.70 或 basis_val >= 120.0)，
        # 且主力合约临近交割/换月窗口(30 <= DTE <= 65天)，持仓量见顶回落。
        # 产业空保受制于限仓与增值税发票无法进入交割月，被迫在近月买入平仓并向远月新主力转移开空。
        # 近月旧主力在空头买平践踏下表现坚挺(价差走正套)，严禁在近月旧主力上新开空单，避免被产业空头买平潮打损!
        if self.enable_hedging_migration_gate:
            is_hedging_migration_window = (
                (self.hedging_migration_min_dte <= dte <= self.hedging_migration_max_dte)
                and (pct_basis_1y >= 0.50)
                and (basis_rate >= self.hedging_migration_basis_rate or pct_basis_1y >= 0.70 or basis_val >= self.hedging_migration_basis_val)
            )
            if is_hedging_migration_window and sig.direction == "SHORT" and current_holding_direction == "FLAT":
                return replace(
                    sig,
                    direction="FLAT",
                    strength=0.0,
                    rationale=f"高基差深贴水临近换月(DTE={dte:.0f}天, 基差率={basis_rate*100:.2f}%)，产业空保买平迁徙潮，近月严禁追空防踩踏",
                    invalidation_reason="HEDGING_MIGRATION_NEAR_MONTH",
                )

        return sig

    def _generate_quant_core_base_signal(
        self,
        date_str: str,
        state_row: pd.Series,
        feature_row: pd.Series,
        current_holding_direction: str = "FLAT",
    ) -> TradingSignal:
        """
        Stage E 核心量化基本面策略 (机制升级版):
        1. 供需方向驱动 + 估值硬底支撑豁免;
        2. 基差与估值不对称安全垫 (防追高、防杀跌一票否决);
        3. 启动区间时机过滤 (远离MA20透支涨跌时不追，靠近MA20启动时入场);
        4. 中长周期大波段宽幅在持保护 (5%均线防震仓容忍带);
        5. 置信度门禁与宏观冲击单向限行。
        """
        fdir = str(state_row.get("fundamental_direction", "Neutral"))
        fscore = float(state_row.get("fbs_score", state_row.get("fundamental_score", 0.0)))
        conf = float(state_row.get("confidence_score", 50.0))
        spot_conf_val = str(state_row.get("spot_confirmation", "Unconfirmed"))
        macro_regime = str(state_row.get("macro_regime", "NORMAL"))
        macro_override = float(state_row.get("macro_override_intensity", 0.0))
        cost_regime = str(state_row.get("cost_boundary_regime", "合理利润运行"))

        close = float(feature_row.get("rb_close", 0.0))
        ma20 = float(feature_row.get("cp_ma20", feature_row.get("ma_20", close)))
        ma5 = float(feature_row.get("cp_ma5", feature_row.get("ma_5", feature_row.get("ma5", close))))
        ma60 = float(feature_row.get("ma_60", feature_row.get("ma60", np.nan)))
        vmm = float(feature_row.get("virtual_mill_margin", 0.0))

        is_winter_season = bool(state_row.get("is_winter_restocking", is_winter_restocking_season(date_str)))

        pct_basis = float(feature_row.get("pct_basis_tier3", 0.5))
        pct_basis_1y = float(feature_row.get("pct_basis_tier3_1y", pct_basis))
        pct_basis_hist = float(feature_row.get("pct_basis_tier3_hist", pct_basis))
        pct_vmm = float(feature_row.get("pct_virtual_mill_margin", 0.5))
        pct_vmm_1y = float(feature_row.get("pct_virtual_mill_margin_1y", pct_vmm))
        pct_vmm_hist = float(feature_row.get("pct_virtual_mill_margin_hist", pct_vmm))
        profit_bf = float(feature_row.get("profit_bf", np.nan))
        cost_bf = float(feature_row.get("cost_bf", close))
        cost_cash_floor = float(feature_row.get("cost_cash_floor", cost_bf - 250.0))
        outflow_pct = float(feature_row.get("pct_flow_hz_outflow", 0.5))
        vol_ratio = float(feature_row.get("rb_vol_shock_ratio", feature_row.get("vol_shock_ratio", 1.0)))
        is_high_vol_pilot = vol_ratio >= HIGH_VOL_THRESHOLD

        # 高利润牛市判定: 价格与基本面必须同时满足 (产业四支柱法则)
        # 支柱 4 (盘面端): 盘面虚拟毛利极高或真实高炉利润极高，且中长期趋势向上
        is_board_high_margin_trend = (
            (vmm >= 450.0 or (pct_vmm >= 0.70 and vmm >= 200.0) or (pct_vmm_1y >= 0.70 and vmm >= 200.0) or (not np.isnan(profit_bf) and profit_bf >= 350.0))
            and (np.isnan(ma60) or close >= ma60 or ma20 >= ma60)
        )
        # 支柱 1 (价格端): 黑色系整体价格处于上升趋势或拐头进入上升趋势
        is_complex_uptrend = bool(feature_row.get("is_ferrous_complex_uptrend", True))
        # 支柱 2 (供应端): 铁水和钢厂产量整体处于稳定高位或持续升高
        is_supply_high_or_rising = bool(feature_row.get("is_supply_high_or_rising", True))
        # 支柱 3 (需求端): 需求保持高位稳定 (可以由于价格上涨小幅下跌，但是整体要是处于稳定阶段)
        is_demand_high_or_stable = bool(feature_row.get("is_demand_high_or_stable", True))

        is_high_margin_bull_trend = (
            is_board_high_margin_trend
            and is_complex_uptrend
            and is_supply_high_or_rising
            and is_demand_high_or_stable
        )

        # 跨品种成本推升指标
        cost_push_spread = float(feature_row.get("cost_push_spread_5d", 0.0))
        if not self.enable_cost_push_dual_drive:
            is_raw_cost_pushing = False
            is_sustained_cost_push = False
            is_false_breakout_cost_push = False
        else:
            leader_type = str(feature_row.get("dominant_leader_type", state_row.get("dominant_leader_type", "")))
            is_raw_sq = bool(feature_row.get("is_raw_material_squeeze", False))
            max_raw_sq = max(
                float(feature_row.get("squeeze_index", 0.0)),
                float(feature_row.get("i_squeeze_index", 0.0)),
                float(feature_row.get("jm_squeeze_index", 0.0)),
                float(feature_row.get("j_squeeze_index", 0.0)),
            )
            is_raw_cost_pushing = (cost_push_spread > 0.015) and (
                leader_type == "RAW_MATERIAL_SHOCK" or is_raw_sq or max_raw_sq >= 2.0
            )

            # 成本推升三态识别
            # 持续型成本推升: 原料推升 + 现货承接坚挺 + 出库正常 + 价格在现金成本之上
            # 在冬储季节，期货适度升水为客观淡季规律，基差与出库要求适度宽容
            min_basis_for_cost_push = 0.15 if is_winter_season else 0.40
            min_outflow_for_cost_push = 0.15 if is_winter_season else 0.30
            is_sustained_cost_push = (
                is_raw_cost_pushing
                and (pct_basis_1y >= min_basis_for_cost_push)
                and (outflow_pct >= min_outflow_for_cost_push)
                and (close >= cost_cash_floor)
            )
            # 假突破型成本推升: 原料暴涨发散 + 现货拒绝买账 (深贴水)
            # 冬储季节极度贴水 (< 0.10) 判定为假突破；常规月份贴水 < 0.25 判定为假突破
            min_false_basis = 0.10 if is_winter_season else 0.25
            is_false_breakout_cost_push = is_raw_cost_pushing and (pct_basis_1y < min_false_basis) and not is_high_margin_bull_trend

        # 1. 严格防追高/防杀跌安全垫门禁 (Anti-Chasing & Valuation Safety Gate)
        # 现货真实利润校验: 钢厂减产与硬底支撑源自实物端亏损。若现货利润仍为正 (profit_bf > 0)，
        # 即使盘面深贴水导致盘面虚拟毛利压缩，钢厂实际仍有盈利且不会减产停炉，绝不能一票否决做空!
        # 当 profit_bf 缺失(早期历史)时，回退到原有估值百分位判断。
        is_spot_loss = (profit_bf <= 0.0) if not pd.isna(profit_bf) else True

        if self.horizon_mode == "PURE_HISTORICAL":
            # 模式 A: 未融合·纯历年全景 (Expanding)
            cost_floor_support = is_spot_loss and ((cost_regime == "深度亏损下轨支撑") or (pct_vmm_hist <= 0.15) or (profit_bf <= -150))
            is_extended_rally = (close > ma20 * 1.025) or (pct_basis_hist < 0.35 and pct_vmm_hist > 0.70) or is_false_breakout_cost_push
            is_extended_plunge = (close < ma20 * 0.975) or (pct_basis_hist > 0.75 and (pct_vmm_hist < 0.20 or profit_bf < -150)) or is_raw_cost_pushing or cost_floor_support
            is_spot_confirmed_long = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and pct_basis_hist >= 0.40) or cost_floor_support or is_sustained_cost_push
            is_spot_confirmed_short = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and pct_basis_hist <= 0.60)
            entry_bound_pct = 0.025
            upper_ma_bound = ma20 * 1.025
            lower_ma_bound = ma20 * 0.975
            ma_entry_inner_long = ma20 * 0.985
            ma_entry_inner_short = ma20 * 1.015
            atr_pct = 0.02
        elif self.horizon_mode == "PURE_1Y":
            # 模式 B: 未融合·纯近1年滚动 (Rolling 252)
            cost_floor_support = is_spot_loss and ((cost_regime == "深度亏损下轨支撑") or (pct_vmm_1y <= 0.15) or (profit_bf <= -150))
            is_extended_rally = (close > ma20 * 1.025) or (pct_basis_1y < 0.35 and pct_vmm_1y > 0.70) or is_false_breakout_cost_push
            is_extended_plunge = (close < ma20 * 0.975) or (pct_basis_1y > 0.75 and (pct_vmm_1y < 0.20 or profit_bf < -150)) or is_raw_cost_pushing or cost_floor_support
            is_spot_confirmed_long = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and pct_basis_1y >= 0.40) or cost_floor_support or is_sustained_cost_push
            is_spot_confirmed_short = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and pct_basis_1y <= 0.60)
            entry_bound_pct = 0.025
            upper_ma_bound = ma20 * 1.025
            lower_ma_bound = ma20 * 0.975
            ma_entry_inner_long = ma20 * 0.985
            ma_entry_inner_short = ma20 * 1.015
            atr_pct = 0.02
        else:
            # 模式 C: 多尺度融合升级版 (1Y 微观敏锐 + Hist 宏观大底支撑)
            # 动态相对波动率与自适应阈值计算 (Dynamic Relative Volatility & Adaptive Bounds)
            atr_val = float(feature_row.get("cp_atr20", feature_row.get("atr_20", np.nan)))
            if np.isnan(atr_val) or atr_val <= 0:
                risk_dist = float(feature_row.get("risk_distance_pct", 0.04))
                atr_val = (risk_dist * close / 2.0) if close > 0 else 50.0
            atr_pct = (atr_val / close) if close > 0 else 0.02

            # 自适应均线启动容忍度 (高波/成本推升放宽至3.5%~5.2%，低波收敛至1.8%，基准常态保持2.5%)
            if is_sustained_cost_push or is_raw_cost_pushing or is_winter_season:
                entry_bound_pct = float(np.clip(max(0.035, 1.5 * atr_pct), 0.020, 0.052))
            else:
                entry_bound_pct = float(np.clip(1.25 * atr_pct, 0.018, 0.038))
            upper_ma_bound = ma20 * (1.0 + entry_bound_pct)
            lower_ma_bound = ma20 * (1.0 - entry_bound_pct)
            ma_entry_inner_long = ma20 * (1.0 - entry_bound_pct * 0.6)
            ma_entry_inner_short = ma20 * (1.0 + entry_bound_pct * 0.6)

            cost_floor_support = is_spot_loss and (
                (cost_regime == "深度亏损下轨支撑") or (pct_vmm <= 0.15) or (pct_vmm_hist <= 0.12) or (pct_vmm_1y <= 0.15) or (profit_bf <= -150)
            )
            # 扩展透支判定: 高利润牛市或持续成本推升中贴水为远期预期，在MA20支撑带不视作透支
            if is_high_margin_bull_trend or is_sustained_cost_push or (is_raw_cost_pushing and close >= ma20):
                is_extended_rally = (close > upper_ma_bound) or is_false_breakout_cost_push
            else:
                is_extended_rally = (close > upper_ma_bound) or (pct_basis_1y < 0.35 and (pct_vmm_1y > 0.70 or pct_vmm_hist > 0.80 or pct_vmm > 0.70)) or is_false_breakout_cost_push

            is_extended_plunge = (close < lower_ma_bound) or (pct_basis_1y > 0.75 and (pct_vmm_1y < 0.20 or pct_vmm_hist < 0.12 or pct_vmm < 0.20 or profit_bf < -150)) or is_raw_cost_pushing or cost_floor_support

            # 现货确认: 高利润牛市与冬储成本推升在MA20支撑带豁免升水贴水否决
            is_spot_confirmed_long = (
                (spot_conf_val == "Confirmed")
                or (spot_conf_val != "Rejected" and (pct_basis_1y >= 0.40 or pct_basis >= 0.40))
                or cost_floor_support
                or is_sustained_cost_push
                or (is_high_margin_bull_trend and close >= ma_entry_inner_long)
                or (is_winter_season and (is_raw_cost_pushing or is_sustained_cost_push) and close >= ma_entry_inner_long)
            )
            is_spot_confirmed_short = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and (pct_basis_1y <= 0.60 or pct_basis <= 0.60))

        # 成本坍塌与次高点破位下行浪判定 (Cost Collapse Downtrend)
        # 需满足: 1) 次高点受阻 (近20日高点低于前120日大顶至少2%); 2) 曾经历显著成本推升但已衰竭至<=0.005; 3) 跌破MA20与MA60生命线; 4) 钢厂未深度亏损
        r_high20 = float(feature_row.get("rolling_high_20", close))
        r_high120 = float(feature_row.get("rolling_high_120", r_high20))
        max_cost_spread = float(feature_row.get("rolling_max_spread_30", cost_push_spread))
        
        is_secondary_peak = (r_high20 < r_high120 * 0.98) and (max_cost_spread >= 0.04)

        is_cost_collapse_breakdown = (
            is_secondary_peak
            and (close < ma20 * (1.0 - entry_bound_pct * 0.4))
            and (close < ma60 if not np.isnan(ma60) else True)
            and (ma5 <= ma20 * 1.005)
            and (cost_push_spread <= 0.005)
            and not is_high_margin_bull_trend
        )

        # 现货挺价瓦解与两阶段下跌策略 (Two-Stage Breakdown Strategy - 知识库与DeepSeek 13问Q8-Q12提炼)
        # 第一阶段: 盘面先跌，现货商挺价(有价无市)，基差被动走扩或维持高位(max_basis_5d >= 30.0 或 pct_basis_1y >= 0.45)
        # 第二阶段: 下游不承接，现货贸易商挺价瓦解补跌，基差拐头断崖走弱(delta_basis_3d <= -20.0 且 delta_spot_3d <= -15.0)，期现商双亏平仓引发踩踏暴跌
        delta_basis_3d = float(feature_row.get("cp_basis_delta3", feature_row.get("delta_basis_3d", np.nan)))
        delta_spot_3d = float(feature_row.get("cp_spot_delta3", feature_row.get("delta_spot_3d", np.nan)))
        max_basis_5d = float(feature_row.get("cp_basis_max5", feature_row.get("max_basis_5d", np.nan)))
        if np.isnan(delta_basis_3d):
            delta_basis_3d = float(feature_row.get("cp_basis_delta5", 0.0))
        if np.isnan(delta_spot_3d):
            delta_spot_3d = float(feature_row.get("cp_spot_ret5", 0.0)) * close

        is_two_stage_breakdown = (
            self.enable_two_stage_breakdown
            and (not np.isnan(max_basis_5d) and max_basis_5d >= 30.0 or pct_basis_1y >= 0.45)
            and (delta_spot_3d <= -15.0 or float(feature_row.get("cp_spot_ret5", 0.0)) <= -0.005)
            and (delta_basis_3d <= -20.0)
            and (close < ma20)
            and (close < ma5)
            and not is_high_margin_bull_trend
            and not is_sustained_cost_push
        )

        if is_cost_collapse_breakdown or is_two_stage_breakdown:
            fdir = "Bearish"

        is_spot_confirmed_short = (
            (spot_conf_val == "Confirmed")
            or (spot_conf_val != "Rejected" and (pct_basis_1y <= 0.60 or pct_basis <= 0.60))
            or is_cost_collapse_breakdown
            or is_two_stage_breakdown
        )

        # 2. 入场启动时机判定 (靠近MA20且未被透支)
        is_entry_timing_long = (close >= ma_entry_inner_long) and (close <= upper_ma_bound) and (ma5 >= ma_entry_inner_long) and not is_extended_rally
        is_entry_timing_short = (
            ((close <= ma_entry_inner_short) and (close >= lower_ma_bound) and (ma5 <= ma_entry_inner_short))
            or ((is_cost_collapse_breakdown or is_two_stage_breakdown) and (close >= lower_ma_bound))
        ) and not is_extended_plunge and not cost_floor_support

        # 3. 宽幅波段在持保护带: 基于动态波动率自适应防震仓容忍带
        # 结构性强趋势中，允许 1.8*ATR (2.2%~4.2%) 正常回调防震仓容忍
        is_structural_trend = is_high_margin_bull_trend or is_sustained_cost_push or is_cost_collapse_breakdown or is_two_stage_breakdown
        if is_structural_trend:
            holding_buffer = float(np.clip(1.8 * atr_pct, 0.022, 0.042))
        else:
            holding_buffer = float(np.clip(1.2 * atr_pct, 0.015, 0.035))
        is_holding_valid_long = close >= ma20 * (1 - holding_buffer)
        is_holding_valid_short = close <= ma20 * (1 + holding_buffer)

        # 4. 高利润强趋势解耦与防逆势做空门禁 (High-Margin Bull Protection Gate)
        if is_high_margin_bull_trend:
            if fdir in ["Bearish", "Neutral"]:
                fdir = "Bullish" if (close >= ma20 * 0.985 and ma5 >= ma20 * 0.985) else "Neutral"
            is_entry_timing_short = False
            is_holding_valid_short = False

        # 低波动均线纠缠震荡降噪门禁 (Low-Vol MA Convergence Noise Filter)
        # 当日度波动率处于低波极值区 (atr_pct < 0.016, 如 2025 年 ATR~40 点)
        # 且 MA20 与 MA60 粘合纠缠 (< 1.2% 价差) 且价格处于二者之间狭窄箱体时，观望等待破局
        is_ma_entwined = (not np.isnan(ma60)) and (atr_pct < 0.016) and (abs(ma20 - ma60) / close < 0.012)
        if is_ma_entwined and current_holding_direction == "FLAT" and (min(ma20, ma60) <= close <= max(ma20, ma60)):
            return TradingSignal(
                trade_date=date_str,
                symbol="RB",
                direction="FLAT",
                strength=0.0,
                confidence_score=conf,
                spot_confirmed=False,
                momentum_confirmed=False,
                strategy_name="QUANT_CORE",
                rationale="低波均线揉搓震荡压缩区: 观望等待破局",
                is_high_vol_pilot=is_high_vol_pilot,
            )

        # 5. 置信度底线: 在强确定性产业驱动下 (持续型成本推升、高利润牛市或成本坍塌右侧破位) 予以豁免
        # 对在持波段单，防范短期噪声下车，底线放宽至 20.0
        min_conf = self.confidence_threshold if current_holding_direction == "FLAT" else (self.confidence_threshold - 20.0)
        is_cost_push_trend_active = (is_raw_cost_pushing or is_sustained_cost_push) and (close >= ma20 * 0.985)
        is_winter_trend_active = is_winter_season and (close >= ma20 * 0.985) and (ma5 >= ma20 * 0.985)
        if (
            conf < min_conf
            and not is_sustained_cost_push
            and not is_high_margin_bull_trend
            and not is_cost_collapse_breakdown
            and not is_cost_push_trend_active
            and not is_winter_trend_active
        ):
            return TradingSignal(
                trade_date=date_str,
                symbol="RB",
                direction="FLAT",
                strength=0.0,
                confidence_score=conf,
                spot_confirmed=False,
                momentum_confirmed=False,
                strategy_name="QUANT_CORE",
                rationale=f"模型置信度不足 ({conf:.1f} < {min_conf:.1f})，降级观望",
                is_high_vol_pilot=is_high_vol_pilot,
            )

        direction = "FLAT"
        strength = 0.0
        rationale_parts = []
        is_pilot_squeeze = False
        is_right_side_trigger = False

        # 机制 1: 低毛利禁多锁 (Low-Margin Bubble Lockout)
        # 物理事实: 低毛利正是原料逼空的结果；当遭遇原料成本推升时，成本倒逼成材抬升中枢，绝不能误判为禁多接盘!
        # 仅当价格处于高位透支区 (Close >= MA20 * 1.015) 且 钢厂即期毛利双低 (<= 15%) 且 原料成本推升已衰竭滞涨 (CostPush <= 0.005 且非原料逼空) 时，严防泡沫顶峰追多接盘
        is_low_margin = (pct_vmm_1y <= 0.15 and pct_vmm_hist <= 0.20) and (np.isnan(profit_bf) or profit_bf <= 100.0)
        is_bullish_locked = is_low_margin and (close >= ma20 * 1.015) and not is_raw_cost_pushing and not is_sustained_cost_push and (cost_push_spread <= 0.005)

        # 机制 2: 下跌破位现货跟跌滞后判定 (Spot Lag in Breakdown Channel)
        # 物理事实: 期货快速破位下挫，现货成交冰冻跟跌滞后(有价无市)，导致基差被动拉大(极值升水)。
        # 严格判定条件: 必须处于主跌浪新鲜破位过程中(Close < MA5且距20日低点不足4.5%)，
        # 若期价已右侧企稳站上MA5或反弹远离大底(如2022-07 V型反弹)，则属于真实超跌反抽，不可强行视作现货滞后。
        r_low20 = float(feature_row.get("rolling_low_20", close))
        if np.isnan(r_low20) or r_low20 <= 0:
            r_low20 = close
        dist_from_low = (close - r_low20) / close if close > 0 else 0.0

        is_spot_lag_illusion = (
            (fdir == "Bullish")
            and (close < ma20 * 0.985)
            and (np.isnan(ma60) or close < ma60 * 0.985)
            and (close < ma5)
            and (dist_from_low < 0.045)
            and not is_high_margin_bull_trend
        )

        # 机制 3: 期现错配利空出尽筑底企稳与逻辑切换买入 (Bottom Absorption & Narrative Switch Reversal)
        # 物理事实: 弱需求/淡季现实极端悲观(钢厂深度亏损，现货大跌兑现完毕)，但期货盘面已充分price in并在现金成本底附近抗跌筑底。
        # 当右侧站上MA5且靠近MA20启动带时，切换为“基差修复+补库预期”逻辑，允许试仓买入。
        # 先决条件: 1) 现货深度亏损现实落地 (cost_floor_support); 2) 深度贴水具备修复动能 (pct_basis_1y >= 0.45 或 pct_basis >= 0.45);
        # 3) 价格处于20日大底筑底带 (dist_from_low <= 0.040 且 close >= cost_cash_floor * 0.98);
        # 4) 右侧启动企稳 (close >= ma5 且 close >= ma_entry_inner_long 且 close <= upper_ma_bound 且 not is_extended_rally);
        # 5) 无极端宏观衰退悬崖
        is_mismatch_bottom_reversal = (
            self.enable_mismatch_governance
            and cost_floor_support
            and (pct_basis_1y >= 0.45 or pct_basis >= 0.45)
            and (dist_from_low <= 0.040)
            and ((cost_cash_floor <= 0) or (cost_cash_floor * 0.95 <= close <= cost_cash_floor * 1.05))
            and (close >= ma5)
            and (close >= ma_entry_inner_long)
            and (close <= upper_ma_bound)
            and not is_extended_rally
            and not (macro_override >= 0.75 and macro_regime in ["PANDEMIC_CLIFF", "SEVERE_RECESSION"])
        )

        is_winter_cost_push_entry = is_winter_season and (is_raw_cost_pushing or is_sustained_cost_push) and (close >= ma_entry_inner_long)

        # 0. 宽幅波段在持保护与状态延续 (Trend Holding Continuity)
        # 只要未触发均线破位容忍带、且未遭遇对向硬否决/宏观冲击，保持持仓延续，避免日度中性噪声导致被动下车
        is_fund_valid_for_long_hold = (fdir != "Bearish") or is_sustained_cost_push
        if current_holding_direction == "LONG" and is_holding_valid_long and is_fund_valid_for_long_hold and not (macro_override >= 0.75 and macro_regime in ["PANDEMIC_CLIFF", "SEVERE_RECESSION"]):
            direction = "LONG"
            base_str = abs(fscore) / 35.0 if fdir == "Bullish" else 0.50
            strength = min(1.0, max(0.65 if is_structural_trend else 0.40, base_str))
            tag = "高利润牛市" if is_high_margin_bull_trend else ("成本推升" if (is_sustained_cost_push or is_raw_cost_pushing) else ("冬储顺势" if is_winter_season else "顺势多头"))
            rationale_parts.append(f"多头大波段在持延续({tag}, Close={close:.0f}满足在持保护带)")
        elif current_holding_direction == "SHORT" and is_holding_valid_short and (fdir != "Bullish" or is_spot_lag_illusion) and not (macro_override >= 0.75 and macro_regime in ["POLICY_STIMULUS", "WAR_CRISIS_EXPANSION"]):
            direction = "SHORT"
            base_str = abs(fscore) / 35.0 if fdir == "Bearish" else 0.50
            strength = min(1.0, max(0.65 if is_structural_trend else 0.40, base_str))
            tag = "成本坍塌" if is_cost_collapse_breakdown else "顺势空头"
            rat_tag = "现货滞后防误平, " if is_spot_lag_illusion else ""
            rationale_parts.append(f"空头大波段在持延续({rat_tag}FBS={fscore:.1f}, Close={close:.0f}满足在持保护带)")
        elif (fdir == "Bullish" and not is_spot_lag_illusion) or is_sustained_cost_push or is_mismatch_bottom_reversal or is_winter_cost_push_entry:
            # 宏观极端利空冲击下不许做多
            if macro_override >= 0.75 and macro_regime in ["PANDEMIC_CLIFF", "SEVERE_RECESSION"]:
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="FLAT",
                    strength=0.0,
                    confidence_score=conf,
                    spot_confirmed=is_spot_confirmed_long,
                    momentum_confirmed=is_entry_timing_long,
                    strategy_name="QUANT_CORE",
                    rationale=f"基本面看多但遭遇极端宏观利空冲击 ({macro_regime})，禁止做多",
                    is_high_vol_pilot=is_high_vol_pilot,
                )

            # 低毛利禁多锁触发: 彻底封死做多空间，严防泡沫顶峰追多接盘 (仅对新开仓生效，在持多头按统一MA20管理)
            if is_bullish_locked and current_holding_direction != "LONG":
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="FLAT",
                    strength=0.0,
                    confidence_score=conf,
                    spot_confirmed=is_spot_confirmed_long,
                    momentum_confirmed=is_entry_timing_long,
                    strategy_name="QUANT_CORE",
                    rationale=f"钢厂即期毛利极度低迷(VMM分位<=15%)且成本推升，触发低毛利禁多锁(Lockout LONG)，严禁高位追多接盘",
                    is_high_vol_pilot=is_high_vol_pilot,
                )

            # 机制: 远月换月初期高基差弱预期接飞刀门禁 (Far-Month High-Basis Mismatch Gate)
            # 物理事实: 换月初期(DTE>65)市场由远期弱预期主导，期价大幅贴水破位，现货跟跌滞后导致基差被动走强。
            # 严禁因“高基差/大贴水”在均线空头排列通道内盲目左侧抄底接飞刀!
            # 先决条件: 1) 远月合约 (dte > 65); 2) 价格处于均线压制破位通道 (Close < MA20*0.99 且 (Close < MA60*0.99 或 Close < MA5)); 3) 非高利润牛市与非持续成本推升
            # 豁免先决条件: 临近交割 (dte <= 50) 时，现货交割收敛逻辑生效，本门禁完全豁免!
            dte = float(feature_row.get("contract_dte", feature_row.get("dte", 999)))
            is_far_month_downtrend = (
                self.enable_mismatch_governance
                and (dte > self.mismatch_far_month_dte)
                and (close < ma20 * 0.99)
                and (np.isnan(ma60) or close < ma60 * 0.99)
                and not is_high_margin_bull_trend
                and not is_sustained_cost_push
            )
            if is_far_month_downtrend and current_holding_direction != "LONG":
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="FLAT",
                    strength=0.0,
                    confidence_score=conf,
                    spot_confirmed=is_spot_confirmed_long,
                    momentum_confirmed=is_entry_timing_long,
                    strategy_name="QUANT_CORE",
                    rationale=f"远月换月初期(DTE={dte:.0f}天)弱预期主导破位，高基差为贴水惯性陷阱，严禁左侧接飞刀",
                    is_high_vol_pilot=is_high_vol_pilot,
                )

            if is_mismatch_bottom_reversal and current_holding_direction == "FLAT":
                direction = "LONG"
                strength = 0.50
                is_right_side_trigger = True
                rationale_parts.append(
                    f"期现错配利空出尽筑底企稳(现实深度亏损Price-In完毕，右侧站上MA5/MA20，启动基差修复与补库试仓)"
                )
            elif is_spot_confirmed_long and is_entry_timing_long:
                direction = "LONG"
                strength = min(1.0, max(0.4, abs(fscore) / 35.0 if fdir == "Bullish" else 0.50))
                tag = "高利润牛市回踩买入" if is_high_margin_bull_trend else ("成本推升顺势买入" if (is_sustained_cost_push or is_raw_cost_pushing) else ("冬储成本推升买入" if is_winter_season else "供需看多买入"))
                rationale_parts.append(f"{tag}(BasisPct={pct_basis_1y:.2f}, CostPush={cost_push_spread:.3f})")
            elif is_extended_rally:
                rationale_parts.append(f"盘面透支涨幅或假突破推升，安全垫一票否决追多")
            else:
                missing = []
                if not is_spot_confirmed_long:
                    missing.append("现货未确认")
                if not is_entry_timing_long:
                    missing.append("未在安全启动均线区间")
                rationale_parts.append(f"看多但准入门槛未满足 ({', '.join(missing)})")

        elif fdir == "Bearish" or is_cost_collapse_breakdown:
            # 宏观极端利多或政策大刺激下不许做空
            if macro_override >= 0.75 and macro_regime in ["POLICY_STIMULUS", "WAR_CRISIS_EXPANSION"]:
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="FLAT",
                    strength=0.0,
                    confidence_score=conf,
                    spot_confirmed=is_spot_confirmed_short,
                    momentum_confirmed=is_entry_timing_short,
                    strategy_name="QUANT_CORE",
                    rationale=f"基本面看空但遭遇重磅宏观政策刺激 ({macro_regime})，禁止做空",
                    is_high_vol_pilot=is_high_vol_pilot,
                )

            # 钢厂深度亏损现金成本硬底一票否决做空杀跌门禁 (Cost Floor Short Veto Gate)
            # 唯独成本坍塌与负反馈右侧破位(is_cost_collapse_breakdown)发生时，成本中枢向下崩塌，豁免禁空一票否决!
            if current_holding_direction != "SHORT" and cost_floor_support and not is_cost_collapse_breakdown:
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="FLAT",
                    strength=0.0,
                    confidence_score=conf,
                    spot_confirmed=is_spot_confirmed_short,
                    momentum_confirmed=is_entry_timing_short,
                    strategy_name="QUANT_CORE",
                    rationale=f"真实钢厂现货深度亏损下轨支撑(ProfitBF={profit_bf:.0f}, VMM分位={pct_vmm_1y:.2f})，安全垫一票否决杀跌做空",
                    is_pilot_squeeze=False,
                    is_right_side_trigger=False,
                    is_high_vol_pilot=is_high_vol_pilot,
                )

            # 机制 2 & 3: 成本坍塌右侧破位 / 成本逼空右侧破位重仓决杀触发器 vs 左侧禁空保护
            is_right_side_breakdown = (close < ma20 * 0.995) and (ma5 <= ma20 * 1.005) and (cost_push_spread <= 0.005)

            if is_cost_collapse_breakdown:
                direction = "SHORT"
                strength = min(1.0, max(0.65, abs(fscore) / 30.0 if fscore < 0 else 0.65))
                is_right_side_trigger = True
                rationale_parts.append(
                    f"成本坍塌与负反馈右侧破位决杀出击! (Close={close:.0f}<MA20/MA60, CostPush={cost_push_spread:.3f}耗尽)"
                )
            elif is_two_stage_breakdown:
                direction = "SHORT"
                strength = min(1.0, max(0.65, abs(fscore) / 30.0 if fscore < 0 else 0.65))
                is_right_side_trigger = True
                rationale_parts.append(
                    f"现货挺价瓦解与两阶段下跌加速决杀! (DeltaBasis3d={delta_basis_3d:.1f}, DeltaSpot3d={delta_spot_3d:.1f}, 期现商双亏平仓破位加速做空)"
                )
            elif is_raw_cost_pushing:
                if is_right_side_breakdown:
                    # 右侧破位触发: 逼空终结，解除禁空顶格进攻出击!
                    direction = "SHORT"
                    strength = min(1.0, max(0.65, abs(fscore) / 30.0))
                    is_right_side_trigger = True
                    is_pilot_squeeze = False
                    rationale_parts.append(
                        f"成本逼空右侧破位决杀触发! (Close={close:.0f}<MA20, CostPush={cost_push_spread:.3f}衰竭，解除禁空顶格进攻)"
                    )
                else:
                    # 左侧逼空拉锯期: 一票否决盲目做空，禁空保护防消耗，保持空仓观望并等待右侧哨声
                    direction = "FLAT"
                    strength = 0.0
                    is_pilot_squeeze = False
                    is_right_side_trigger = False
                    rationale_parts.append(
                        f"成材表需虽弱但遭遇原料强力推升(CostPush={cost_push_spread:.3f})，禁空保护(等待右侧破位决杀)"
                    )

            elif is_spot_confirmed_short and is_entry_timing_short:
                direction = "SHORT"
                strength = min(1.0, max(0.4, abs(fscore) / 35.0))
                rationale_parts.append(f"供需看空+估值未见底确认做空(FBS={fscore:.1f}, BasisPct={pct_basis_1y:.2f})")
            elif is_extended_plunge:
                rationale_parts.append(f"盘面超跌或钢厂深度亏损，一票否决杀跌")
            else:
                missing = []
                if not is_spot_confirmed_short:
                    missing.append("现货未确认弱势")
                if not is_entry_timing_short:
                    missing.append("未在安全做空均线区间")
                rationale_parts.append(f"基本面看空但准入门槛未满足 ({', '.join(missing)})")

        else:
            if is_spot_lag_illusion:
                rationale_parts.append(f"下跌破位现货跟跌滞后假象(FBS={fscore:.1f})，一票否决做多")
            else:
                rationale_parts.append(f"基本面中性震荡 (FBS={fscore:.1f})")

        # 机制 4: 震荡期绞杀双重防御门禁 (Anti-Chop Defense Gates: 方法1箱体空间 + 方法2微观流动性)
        # 仅当处于空仓 (FLAT) 考虑新开仓、且当前信号意图建立单边仓位时启动核验
        if current_holding_direction == "FLAT" and direction in ("LONG", "SHORT"):
            # 门禁 A: 微观实物流动性冰封门禁 (Physical Liquidity Gate)
            pct_deal = float(feature_row.get("pct_building_deal_volume_1y", np.nan))
            if pd.isna(pct_deal):
                pct_deal = float(feature_row.get("pct_building_deal_volume", 0.5))
            cny_week = feature_row.get("cny_relative_week", 99)
            if pd.isna(cny_week):
                cny_week = 99

            is_frozen_liquidity = (pct_deal <= self.liquidity_thresh) and (self.cny_week_window[0] <= cny_week <= self.cny_week_window[1])
            if is_frozen_liquidity:
                return TradingSignal(
                    trade_date=date_str,
                    symbol="RB",
                    direction="FLAT",
                    strength=0.0,
                    confidence_score=conf,
                    spot_confirmed=(is_spot_confirmed_long if direction == "LONG" else is_spot_confirmed_short),
                    momentum_confirmed=(is_entry_timing_long if direction == "LONG" else is_entry_timing_short),
                    strategy_name="QUANT_CORE",
                    rationale=f"微观实物流动性冰封一票否决新开仓 (全国建材成交分位={pct_deal:.2f}<={self.liquidity_thresh:.2f}, 农历周={cny_week})",
                    is_pilot_squeeze=False,
                    is_right_side_trigger=False,
                    is_high_vol_pilot=is_high_vol_pilot,
                )

            # 优化 1: 门禁 B 绝不对结构性做空豁免! (箱体底部空间透支一票否决做空)
            # 无论是否属于结构性趋势，只要新开做空时距离20日箱体下轨不足阈值，且反弹风险为下行空间规定倍数以上，绝不盲目追空杀跌!
            dynamic_space_thresh = float(np.clip(0.60 * atr_pct, 0.007, 0.020))
            r_high = float(feature_row.get("rolling_high_20", 0.0))
            r_low = float(feature_row.get("rolling_low_20", 0.0))
            r_box = r_high - r_low

            if r_box > 0 and close > 0:
                if direction == "SHORT":
                    # 突破与顺势破位下行浪豁免箱底否决 (Symmetric Box Gate B Exemption)
                    is_downtrend_breakdown = is_cost_collapse_breakdown or (
                        (close < ma20 * 0.985) and (np.isnan(ma60) or close < ma60 * 0.985)
                    )
                    if not is_downtrend_breakdown:
                        downside_space = (close - r_low) / close
                        upside_risk = (r_high - close) / close
                        # 处于箱体内部、距离下轨不足空间阈值，且反弹风险为下行空间规定倍数以上
                        if 0.0 <= downside_space < dynamic_space_thresh and upside_risk > self.risk_reward_ratio * downside_space:
                            return TradingSignal(
                                trade_date=date_str,
                                symbol="RB",
                                direction="FLAT",
                                strength=0.0,
                                confidence_score=conf,
                                spot_confirmed=is_spot_confirmed_short,
                                momentum_confirmed=is_entry_timing_short,
                                strategy_name="QUANT_CORE",
                                rationale=f"箱体底部空间透支一票否决做空 (下行空间={downside_space*100:.1f}%, 反弹阻力风险={upside_risk*100:.1f}%)",
                                is_pilot_squeeze=False,
                                is_right_side_trigger=False,
                                is_high_vol_pilot=is_high_vol_pilot,
                            )
                elif direction == "LONG":
                    # 高利润牛市/成本推升顺势突破不被旧箱体顶压制
                    if not (is_high_margin_bull_trend or is_sustained_cost_push):
                        downside_risk = (close - r_low) / close
                        upside_space = (r_high - close) / close
                        # 处于箱体内部、距离上轨不足空间阈值，且回撤风险为上行空间规定倍数以上
                        if 0.0 <= upside_space < dynamic_space_thresh and downside_risk > self.risk_reward_ratio * upside_space:
                            return TradingSignal(
                                trade_date=date_str,
                                symbol="RB",
                                direction="FLAT",
                                strength=0.0,
                                confidence_score=conf,
                                spot_confirmed=is_spot_confirmed_long,
                                momentum_confirmed=is_entry_timing_long,
                                strategy_name="QUANT_CORE",
                                rationale=f"箱体顶部空间透支一票否决做多 (上行空间={upside_space*100:.1f}%, 回撤风险={downside_risk*100:.1f}%)",
                                is_pilot_squeeze=False,
                                is_right_side_trigger=False,
                                is_high_vol_pilot=is_high_vol_pilot,
                            )

            # 门禁 C: 期限结构 Carry 极端逆风一票否决门禁 (Carry Headwind Veto Gate)
            is_structural_trend_flag = (
                (direction == "LONG" and (is_high_margin_bull_trend or is_sustained_cost_push)) or
                (direction == "SHORT" and (is_cost_collapse_breakdown or is_right_side_trigger))
            )
            if self.enable_carry_gate and not is_structural_trend_flag:
                pct_ry = float(feature_row.get("pct_roll_yield_1y", np.nan))
                if pd.isna(pct_ry):
                    pct_ry = float(feature_row.get("pct_roll_yield", 0.5))

                # 空头防强 Backwardation 负 Carry 逆风
                if direction == "SHORT" and pct_ry >= self.carry_headwind_thresh_high:
                    downside_space = (close - r_low) / close if (r_low > 0 and close > 0) else 1.0
                    # 仅在未发生跌破20日新低的真突破时执行一票否决
                    if downside_space >= 0.0:
                        return TradingSignal(
                            trade_date=date_str,
                            symbol="RB",
                            direction="FLAT",
                            strength=0.0,
                            confidence_score=conf,
                            spot_confirmed=is_spot_confirmed_short,
                            momentum_confirmed=is_entry_timing_short,
                            strategy_name="QUANT_CORE",
                            rationale=f"期限结构强Backwardation负Carry一票否决做空 (展期分位={pct_ry:.2f}>={self.carry_headwind_thresh_high:.2f})",
                            is_pilot_squeeze=False,
                            is_right_side_trigger=False,
                            is_high_vol_pilot=is_high_vol_pilot,
                            carry_regime="STRONG_BACKWARDATION",
                            carry_multiplier=0.0,
                        )
                # 多头防强 Contango 负 Carry 逆风
                elif direction == "LONG" and pct_ry <= self.carry_headwind_thresh_low:
                    upside_space = (r_high - close) / close if (r_high > 0 and close > 0) else 1.0
                    # 仅在未发生突破20日新高的真突破时执行一票否决
                    if upside_space >= 0.0:
                        return TradingSignal(
                            trade_date=date_str,
                            symbol="RB",
                            direction="FLAT",
                            strength=0.0,
                            confidence_score=conf,
                            spot_confirmed=is_spot_confirmed_long,
                            momentum_confirmed=is_entry_timing_long,
                            strategy_name="QUANT_CORE",
                            rationale=f"期限结构强Contango负Carry一票否决做多 (展期分位={pct_ry:.2f}<={self.carry_headwind_thresh_low:.2f})",
                            is_pilot_squeeze=False,
                            is_right_side_trigger=False,
                            is_high_vol_pilot=is_high_vol_pilot,
                            carry_regime="STRONG_CONTANGO",
                            carry_multiplier=0.0,
                        )

        # 机制 5: 期限结构 Carry 顺逆风状态与自适应仓位乘数判定 (Carry Adaptive Sizing)
        carry_regime = "NEUTRAL"
        carry_multiplier = 1.0
        if self.enable_carry_sizer and direction in ("LONG", "SHORT"):
            pct_ry = float(feature_row.get("pct_roll_yield_1y", np.nan))
            if pd.isna(pct_ry):
                pct_ry = float(feature_row.get("pct_roll_yield", 0.5))

            if direction == "LONG":
                if pct_ry >= self.carry_tailwind_long_thresh:
                    carry_regime = "TAILWIND_BACKWARDATION"
                    carry_multiplier = self.carry_mult_up
                elif pct_ry <= self.carry_headwind_long_thresh:
                    carry_regime = "MILD_HEADWIND_CONTANGO"
                    carry_multiplier = self.carry_mult_down
            elif direction == "SHORT":
                if pct_ry <= self.carry_tailwind_short_thresh:
                    carry_regime = "TAILWIND_CONTANGO"
                    carry_multiplier = self.carry_mult_up
                elif pct_ry >= self.carry_headwind_short_thresh:
                    carry_regime = "MILD_HEADWIND_BACKWARDATION"
                    carry_multiplier = self.carry_mult_down

        return TradingSignal(
            trade_date=date_str,
            symbol="RB",
            direction=direction,
            strength=strength,
            confidence_score=conf,
            spot_confirmed=(is_spot_confirmed_long if direction == "LONG" else is_spot_confirmed_short),
            momentum_confirmed=(
                (is_entry_timing_long if current_holding_direction != "LONG" else is_holding_valid_long)
                if direction == "LONG"
                else (is_entry_timing_short if current_holding_direction != "SHORT" else is_holding_valid_short)
            ),
            strategy_name="QUANT_CORE",
            rationale=" | ".join(rationale_parts),
            is_pilot_squeeze=is_pilot_squeeze,
            is_right_side_trigger=is_right_side_trigger,
            is_high_vol_pilot=is_high_vol_pilot,
            carry_regime=carry_regime,
            carry_multiplier=carry_multiplier,
            entry_driver=(
                "MISMATCH_BOTTOM_REVERSAL"
                if is_mismatch_bottom_reversal and direction == "LONG"
                else (
                    "TWO_STAGE_BREAKDOWN"
                    if is_two_stage_breakdown and direction == "SHORT"
                    else (
                        "HIGH_MARGIN_BULL"
                        if is_high_margin_bull_trend
                        else ("COST_EXPECTATION" if is_sustained_cost_push else "FUNDAMENTAL")
                    )
                )
            ),
            strategy_margin_utilization=(
                0.25 if (is_mismatch_bottom_reversal and direction == "LONG") else None
            ),
            risk_distance_pct=(
                float(feature_row.get("risk_distance_pct", 0.035))
                if (is_mismatch_bottom_reversal and direction == "LONG")
                else None
            ),
            entry_stop_level=(
                (close * (1.0 - float(feature_row.get("risk_distance_pct", 0.035))))
                if (is_mismatch_bottom_reversal and direction == "LONG")
                else None
            ),
        )
