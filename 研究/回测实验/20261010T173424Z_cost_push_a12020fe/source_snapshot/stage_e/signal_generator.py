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

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np
from framework_rules import HIGH_VOL_THRESHOLD, MA_STOP_BUFFER


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
        ma20 = float(feature_row.get("ma_20", close))
        ma5 = float(feature_row.get("ma_5", feature_row.get("ma5", close)))

        pct_basis = float(feature_row.get("pct_basis_tier3", 0.5))
        pct_basis_1y = float(feature_row.get("pct_basis_tier3_1y", pct_basis))
        pct_basis_hist = float(feature_row.get("pct_basis_tier3_hist", pct_basis))
        pct_vmm = float(feature_row.get("pct_virtual_mill_margin", 0.5))
        pct_vmm_1y = float(feature_row.get("pct_virtual_mill_margin_1y", pct_vmm))
        pct_vmm_hist = float(feature_row.get("pct_virtual_mill_margin_hist", pct_vmm))
        profit_bf = float(feature_row.get("profit_bf", 0.0))
        cost_bf = float(feature_row.get("cost_bf", close))
        cost_cash_floor = float(feature_row.get("cost_cash_floor", cost_bf - 250.0))
        outflow_pct = float(feature_row.get("pct_flow_hz_outflow", 0.5))
        vol_ratio = float(feature_row.get("rb_vol_shock_ratio", feature_row.get("vol_shock_ratio", 1.0)))
        is_high_vol_pilot = vol_ratio >= HIGH_VOL_THRESHOLD

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
            # 持续型成本推升: 原料推升 + 现货承接坚挺 (近1年基差不低于0.40) + 出库正常 (>=0.30) + 价格在现金成本之上
            is_sustained_cost_push = (
                is_raw_cost_pushing
                and (pct_basis_1y >= 0.40)
                and (outflow_pct >= 0.30)
                and (close >= cost_cash_floor)
            )
            # 假突破型成本推升: 原料暴涨发散 + 现货拒绝买账 (深贴水 < 0.25)
            is_false_breakout_cost_push = is_raw_cost_pushing and (pct_basis_1y < 0.25)

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
        elif self.horizon_mode == "PURE_1Y":
            # 模式 B: 未融合·纯近1年滚动 (Rolling 252)
            cost_floor_support = is_spot_loss and ((cost_regime == "深度亏损下轨支撑") or (pct_vmm_1y <= 0.15) or (profit_bf <= -150))
            is_extended_rally = (close > ma20 * 1.025) or (pct_basis_1y < 0.35 and pct_vmm_1y > 0.70) or is_false_breakout_cost_push
            is_extended_plunge = (close < ma20 * 0.975) or (pct_basis_1y > 0.75 and (pct_vmm_1y < 0.20 or profit_bf < -150)) or is_raw_cost_pushing or cost_floor_support
            is_spot_confirmed_long = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and pct_basis_1y >= 0.40) or cost_floor_support or is_sustained_cost_push
            is_spot_confirmed_short = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and pct_basis_1y <= 0.60)
        else:
            # 模式 C: 多尺度融合升级版 (1Y 微观敏锐 + Hist 宏观大底支撑)
            # 动态相对波动率与自适应阈值计算 (Dynamic Relative Volatility & Adaptive Bounds)
            atr_val = float(feature_row.get("cp_atr20", feature_row.get("atr_20", np.nan)))
            if np.isnan(atr_val) or atr_val <= 0:
                risk_dist = float(feature_row.get("risk_distance_pct", 0.04))
                atr_val = (risk_dist * close / 2.0) if close > 0 else 50.0
            atr_pct = (atr_val / close) if close > 0 else 0.02

            # 自适应均线启动容忍度 (高波放宽至3.8%，低波收敛至1.8%，基准常态保持2.5%)
            entry_bound_pct = float(np.clip(1.25 * atr_pct, 0.018, 0.038))
            upper_ma_bound = ma20 * (1.0 + entry_bound_pct)
            lower_ma_bound = ma20 * (1.0 - entry_bound_pct)
            ma_entry_inner_long = (ma20 * 0.995) if current_holding_direction == "FLAT" else (ma20 * (1.0 - entry_bound_pct * 0.6))
            ma_entry_inner_short = ma20 * (1.0 + entry_bound_pct * 0.6)

            cost_floor_support = is_spot_loss and (
                (cost_regime == "深度亏损下轨支撑") or (pct_vmm <= 0.15) or (pct_vmm_hist <= 0.12) or (pct_vmm_1y <= 0.15) or (profit_bf <= -150)
            )
            is_extended_rally = (close > upper_ma_bound) or (pct_basis_1y < 0.35 and (pct_vmm_1y > 0.70 or pct_vmm_hist > 0.80 or pct_vmm > 0.70)) or is_false_breakout_cost_push
            is_extended_plunge = (close < lower_ma_bound) or (pct_basis_1y > 0.75 and (pct_vmm_1y < 0.20 or pct_vmm_hist < 0.12 or pct_vmm < 0.20 or profit_bf < -150)) or is_raw_cost_pushing or cost_floor_support
            is_spot_confirmed_long = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and (pct_basis_1y >= 0.40 or pct_basis >= 0.40)) or cost_floor_support or is_sustained_cost_push
            is_spot_confirmed_short = (spot_conf_val == "Confirmed") or (spot_conf_val != "Rejected" and (pct_basis_1y <= 0.60 or pct_basis <= 0.60))

        # 2. 入场启动时机判定 (靠近MA20且未被透支)
        is_entry_timing_long = (close >= ma_entry_inner_long) and (close <= upper_ma_bound) and (ma5 >= ma_entry_inner_long) and not is_extended_rally
        is_entry_timing_short = (close <= ma_entry_inner_short) and (close >= lower_ma_bound) and (ma5 <= ma_entry_inner_short) and not is_extended_plunge and not cost_floor_support

        # 3. 宽幅波段在持保护带: 基于动态波动率自适应防震仓容忍带
        holding_buffer = float(np.clip(1.2 * atr_pct, 0.015, 0.035))
        is_holding_valid_long = close >= ma20 * (1 - holding_buffer)
        is_holding_valid_short = close <= ma20 * (1 + holding_buffer)

        # 4. 高利润强趋势解耦与防逆势做空门禁 (High-Margin Bull Protection Gate)
        # 当盘面利润极度丰厚 (虚拟毛利 >= 450元 或 毛利分位数 >= 0.70 或 高炉利润 >= 350元) 且中长期均线向上 (Close>=MA60 或 MA20>=MA60):
        # 供给绝对值高是需求旺盛拉动的被动供求两旺，解除机械看空，严禁逆势做空
        vmm = float(feature_row.get("virtual_mill_margin", 0.0))
        ma60 = float(feature_row.get("ma_60", feature_row.get("ma60", np.nan)))
        is_high_margin_bull_trend = (
            (vmm >= 450.0 or (pct_vmm >= 0.70 and vmm >= 200.0) or (pct_vmm_1y >= 0.70 and vmm >= 200.0) or (not np.isnan(profit_bf) and profit_bf >= 350.0))
            and (np.isnan(ma60) or close >= ma60 or ma20 >= ma60)
        )
        if is_high_margin_bull_trend:
            if fdir == "Bearish":
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

        # 5. 置信度底线: 在强确定性产业驱动下 (持续型成本推升或高利润牛市) 予以豁免
        min_conf = self.confidence_threshold if current_holding_direction == "FLAT" else (self.confidence_threshold - 5.0)
        if conf < min_conf and not is_sustained_cost_push and not is_high_margin_bull_trend:
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
        # 仅当价格处于高位透支区 (Close >= MA20 * 1.015) 且 钢厂即期毛利双低 (<= 15%) 且 遭遇原料成本推升时，严防泡沫顶峰追多接盘
        is_low_margin = (pct_vmm_1y <= 0.15 and pct_vmm_hist <= 0.20) and (np.isnan(profit_bf) or profit_bf <= 100.0)
        is_bullish_locked = is_low_margin and (close >= ma20 * 1.015) and (is_raw_cost_pushing or cost_push_spread > 0.015)


        # 信号路由: 需求拉动 (Bullish) vs 持续型成本推升 (Sustained Cost-Push) vs 做空 (Bearish)
        if fdir == "Bullish" or is_sustained_cost_push:
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

            if current_holding_direction == "LONG" and is_holding_valid_long:
                direction = "LONG"
                strength = min(1.0, max(0.4, abs(fscore) / 35.0 if fdir == "Bullish" else 0.50))
                tag = "成本推升" if is_sustained_cost_push else "需求拉动"
                rationale_parts.append(f"多头大波段在持延续({tag}, Close={close:.0f}满足统一MA20边界)")
            elif is_spot_confirmed_long and is_entry_timing_long:
                direction = "LONG"
                strength = min(1.0, max(0.4, abs(fscore) / 35.0 if fdir == "Bullish" else 0.50))
                tag = "成本推升顺势买入" if is_sustained_cost_push else "供需看多买入"
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

        elif fdir == "Bearish":
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
            if current_holding_direction != "SHORT" and cost_floor_support:
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

            # 机制 2 & 3: 成本逼空右侧破位重仓决杀触发器 vs 左侧禁空保护
            is_right_side_breakdown = (close < ma20 * 0.995) and (ma5 <= ma20 * 1.005) and (cost_push_spread <= 0.005)

            if is_raw_cost_pushing:
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

            elif current_holding_direction == "SHORT" and is_holding_valid_short:
                direction = "SHORT"
                strength = min(1.0, max(0.4, abs(fscore) / 35.0))
                rationale_parts.append(f"空头大波段在持延续(FBS={fscore:.1f}, Close={close:.0f}满足统一MA20边界)")
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

            # 门禁 B: 箱体空间与盈亏比不对称门禁 (Box Space & Reward-to-Risk Gate: 动态ATR自适应)
            dynamic_space_thresh = float(np.clip(0.60 * atr_pct, 0.007, 0.020))
            r_high = float(feature_row.get("rolling_high_20", 0.0))
            r_low = float(feature_row.get("rolling_low_20", 0.0))
            r_box = r_high - r_low

            if r_box > 0 and close > 0:
                if direction == "SHORT":
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
            if self.enable_carry_gate:
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
        )
