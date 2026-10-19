#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/risk_firewall.py
功能: 阶段 C 五重风控防火墙与背离熔断引擎 (Risk Control Firewall & Breaker Engine)
职责:
  严格遵循《实施手册》第 4.6 节、第 19 节与 A06.1 规范:
  1. 恪守 State != Position 铁律，在状态层与执行层之间构筑绝对否决权防火墙;
  2. 实现五重不可逾越的防御墙:
     - 第一重: 数据新鲜度与信息真空降级防火墙 (Data Freshness Firewall)
     - 第二重: 跨品种挤仓传染隔离墙 (Cross-Commodity Contagion Quarantine)
     - 第三重: 内生极端波动率与脉冲熔断器 (Volatility Impulse Circuit Breaker)
     - 第四重: 技术通道破位硬止损铁律 (Technical Hard Stop Boundary)
     - 第五重: 同尺度背离阶梯惩罚与强制防守 (Divergence Ladder)
  3. 输出白盒实体 FirewallDecision，确定当前是否允许交易、允许最大杠杆率与紧急平仓动作。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np
from framework_rules import MA_STOP_BUFFER


@dataclass(frozen=True)
class FirewallDecision:
    """风控防火墙不可篡改判决结果实体"""
    trade_date: str
    status: str  # PASS / CAUTION / RESTRICT_CLOSE_ONLY / FORCED_LIQUIDATION / TRADING_HALT
    max_allowable_leverage: float  # 0.0 ~ 1.0 允许最大杠杆上限
    action: str  # HOLD / DE_RISK_50 / LIQUIDATE_IMMEDIATELY / HALT
    breached_layers: List[str]  # 触发违规的防火墙层级
    detailed_reasons: List[str]  # 触发原因与白盒指标数值
    dominant_risk_factor: str  # 主导风险因子类别


class RiskControlFirewall:
    """
    五重风控防火墙核心引擎
    """

    def __init__(
        self,
        vol_shock_threshold: float = 2.5,
        extreme_ret_1d_threshold: float = 0.030,
        extreme_ret_5d_threshold: float = 0.050,
        ma_stop_buffer_pct: float = MA_STOP_BUFFER,
        severe_div_days: int = 8,
        severe_div_area: float = 15.0,
        moderate_div_days: int = 4,
        moderate_div_area: float = 6.0,
    ):
        self.vol_shock_threshold = vol_shock_threshold
        self.extreme_ret_1d_threshold = extreme_ret_1d_threshold
        self.extreme_ret_5d_threshold = extreme_ret_5d_threshold
        self.ma_stop_buffer_pct = ma_stop_buffer_pct
        self.severe_div_days = severe_div_days
        self.severe_div_area = severe_div_area
        self.moderate_div_days = moderate_div_days
        self.moderate_div_area = moderate_div_area

    def evaluate(
        self,
        state_row: pd.Series,
        feature_row: pd.Series,
        position_intent: str = "flat",  # "long" / "short" / "flat"
        is_pilot_squeeze: bool = False,
        entry_driver: str = "FUNDAMENTAL",
    ) -> FirewallDecision:
        """
        单日截面风控防火墙全量评估

        Parameters:
        -----------
        state_row: 状态矩阵当前行
        feature_row: 特征宽表当前行
        position_intent: 当前持仓意图或持仓方向 ("long", "short", "flat")
        """
        trade_date = str(feature_row.name if hasattr(feature_row, "name") else state_row.get("date", "Unknown"))
        
        breached_layers: List[str] = []
        detailed_reasons: List[str] = []
        dominant_risk = "Normal"
        
        # 初始状态
        status = "PASS"
        max_leverage = 1.00
        action = "HOLD"

        # ---------------------------------------------------------
        # 第一重: 数据新鲜度与信息真空降级防火墙
        # ---------------------------------------------------------
        freshness = float(feature_row.get("data_freshness_ratio", 1.0))
        if freshness < 0.40:
            breached_layers.append("Layer 1: Data Freshness Vacuum")
            detailed_reasons.append(f"数据新鲜度比率过低 ({freshness:.2f} < 0.40)，触发信息真空保护")
            status = "TRADING_HALT"
            max_leverage = 0.0
            action = "HALT"
            dominant_risk = "Data_Vacuum"
            return FirewallDecision(
                trade_date=trade_date,
                status=status,
                max_allowable_leverage=max_leverage,
                action=action,
                breached_layers=breached_layers,
                detailed_reasons=detailed_reasons,
                dominant_risk_factor=dominant_risk,
            )

        # ---------------------------------------------------------
        # 第二重: 跨品种挤仓传染隔离墙
        # ---------------------------------------------------------
        squeeze_idx = max(
            float(feature_row.get("squeeze_index", 0.0)),
            float(feature_row.get("i_squeeze_index", 0.0)),
            float(feature_row.get("jm_squeeze_index", 0.0)),
            float(feature_row.get("j_squeeze_index", 0.0)),
        )
        is_raw_sq = bool(feature_row.get("is_raw_material_squeeze", False))
        cost_push = float(feature_row.get("cost_push_spread_5d", 0.0))
        leader_type = str(state_row.get("dominant_leader_type", feature_row.get("dominant_leader_type", "")))
        
        if (squeeze_idx >= 3.0 or (is_raw_sq and squeeze_idx >= 2.0)) and cost_push > 0.015 and leader_type == "RAW_MATERIAL_SHOCK":
            if position_intent == "short":
                breached_layers.append("Layer 2: Cross-Commodity Contagion")
                if is_pilot_squeeze:
                    detailed_reasons.append(
                        f"原料极端逼仓传染 (squeeze_idx={squeeze_idx:.2f}>=3.0, cost_push={cost_push:.3f}>0.015)，启动限仓侦察模式 (CAUTION)"
                    )
                    if status != "FORCED_LIQUIDATION":
                        status = "CAUTION"
                    max_leverage = min(max_leverage, 0.70)
                    action = "DE_RISK_50"
                    dominant_risk = "Raw_Material_Squeeze"
                else:
                    detailed_reasons.append(
                        f"原料极端逼仓传染 (squeeze_idx={squeeze_idx:.2f}>=3.0, cost_push={cost_push:.3f}>0.015)，严禁做空成材"
                    )
                    if status != "FORCED_LIQUIDATION":
                        status = "RESTRICT_CLOSE_ONLY"
                    max_leverage = min(max_leverage, 0.50)
                    action = "DE_RISK_50"
                    dominant_risk = "Raw_Material_Squeeze"


        # ---------------------------------------------------------
        # 第三重: 内生极端波动率与脉冲熔断器
        # ---------------------------------------------------------
        vol_ratio = float(feature_row.get("vol_shock_ratio", feature_row.get("rb_vol_shock_ratio", 1.0)))
        ret_1d = float(feature_row.get("rb_ret_1d", 0.0))
        ret_5d = float(feature_row.get("rb_ret_5d", feature_row.get("ret_5d", 0.0)))
        
        is_vol_shock = (vol_ratio >= self.vol_shock_threshold) and (
            abs(ret_1d) >= self.extreme_ret_1d_threshold or abs(ret_5d) >= self.extreme_ret_5d_threshold
        )

        if is_vol_shock:
            dominant_risk = "Volatility_Shock"
            # 判断脉冲方向与持仓意图是否冲突
            upward_shock = (ret_1d >= self.extreme_ret_1d_threshold) or (ret_5d >= self.extreme_ret_5d_threshold)
            downward_shock = (ret_1d <= -self.extreme_ret_1d_threshold) or (ret_5d <= -self.extreme_ret_5d_threshold)

            if position_intent == "short" and upward_shock:
                breached_layers.append("Layer 3: Volatility Impulse Circuit Breaker")
                detailed_reasons.append(
                    f"盘面爆发极端向上脉冲 (vol_ratio={vol_ratio:.2f}, ret_1d={ret_1d:.3f}, ret_5d={ret_5d:.3f})，逆势空头强制斩仓熔断"
                )
                status = "FORCED_LIQUIDATION"
                max_leverage = 0.0
                action = "LIQUIDATE_IMMEDIATELY"
            elif position_intent == "long" and downward_shock:
                breached_layers.append("Layer 3: Volatility Impulse Circuit Breaker")
                detailed_reasons.append(
                    f"盘面爆发极端向下脉冲 (vol_ratio={vol_ratio:.2f}, ret_1d={ret_1d:.3f}, ret_5d={ret_5d:.3f})，逆势多头强制斩仓熔断"
                )
                status = "FORCED_LIQUIDATION"
                max_leverage = 0.0
                action = "LIQUIDATE_IMMEDIATELY"
            else:
                # 顺势或观望，但市场极度动荡，压降杠杆上限
                breached_layers.append("Layer 3: Volatility Shock Alert")
                detailed_reasons.append(f"市场处于极端波动率状态 (vol_ratio={vol_ratio:.2f})，限制杠杆")
                if status != "FORCED_LIQUIDATION":
                    status = "CAUTION" if status == "PASS" else status
                    max_leverage = min(max_leverage, 0.50)

        # ---------------------------------------------------------
        # 第四重: 技术通道破位硬止损铁律
        # ---------------------------------------------------------
        close_p = float(feature_row.get("rb_close", np.nan))
        ma20 = float(feature_row.get("ma_20", feature_row.get("ma20", np.nan)))
        ma60 = float(feature_row.get("ma_60", feature_row.get("ma60", np.nan)))

        if not np.isnan(close_p) and not np.isnan(ma20):
            buffer_pct = self.ma_stop_buffer_pct
            if position_intent == "long":
                # 多头破位: 跌破 MA20 超过 1.5% 缓冲，或在多头均线顺势排列 (MA20 >= MA60) 时彻底跌破 MA60
                is_break_ma20 = close_p < ma20 * (1.0 - self.ma_stop_buffer_pct)
                is_break_ma60 = not np.isnan(ma60) and (ma20 >= ma60) and (close_p < ma60)
                if is_break_ma20 or is_break_ma60:
                    breached_layers.append("Layer 4: Technical Hard Stop Boundary")
                    break_reason = f"跌破MA20 1.5%缓冲 (Close={close_p:.1f}, MA20={ma20:.1f})" if is_break_ma20 else f"跌破MA60生命线 (Close={close_p:.1f}, MA60={ma60:.1f})"
                    detailed_reasons.append(f"多头持仓发生技术破位: {break_reason}，强制止损")
                    status = "FORCED_LIQUIDATION"
                    max_leverage = 0.0
                    action = "LIQUIDATE_IMMEDIATELY"
                    dominant_risk = "Technical_Breakdown"
            elif position_intent == "short":
                # 空头破位: 突破 MA20 超过缓冲 (常规 1.5%，逼空侦察轻仓放宽至 3.5% 防震仓)
                is_break_ma20 = close_p > ma20 * (1.0 + buffer_pct)
                is_break_ma60 = not np.isnan(ma60) and (ma20 <= ma60) and (close_p > ma60)
                if is_break_ma20 or is_break_ma60:
                    breached_layers.append("Layer 4: Technical Hard Stop Boundary")
                    break_reason = f"突破MA20 {buffer_pct*100:.1f}%缓冲 (Close={close_p:.1f}, MA20={ma20:.1f})" if is_break_ma20 else f"突破MA60生命线 (Close={close_p:.1f}, MA60={ma60:.1f})"
                    detailed_reasons.append(f"空头持仓发生技术破位: {break_reason}，强制止损")
                    status = "FORCED_LIQUIDATION"
                    max_leverage = 0.0
                    action = "LIQUIDATE_IMMEDIATELY"
                    dominant_risk = "Technical_Breakdown"


        # ---------------------------------------------------------
        # 第五重: 同尺度背离阶梯惩罚与强制防守
        # ---------------------------------------------------------
        div_days = int(state_row.get("divergence_days", feature_row.get("divergence_days", 0)))
        div_area = abs(float(state_row.get("divergence_area", feature_row.get("divergence_area", 0.0))))
        div_sev = str(state_row.get("divergence_severity", "None"))

        # 判断持仓是否正是导致背离的方向 (例如基本面看空但价格上涨，若持有空头则属于背离死扛；基本面看多但价格下跌，若持有多头则属于背离死扛)
        fund_dir = str(state_row.get("fundamental_direction", "Neutral"))
        div_gap = float(feature_row.get("divergence_gap", 0.0))
        z_price = float(feature_row.get("z_price_10d", 0.0))
        ret_5d = float(feature_row.get("rb_ret_5d", feature_row.get("ret_5d", 0.0)))
        close_p = float(feature_row.get("rb_close", np.nan))
        ma20_val = float(feature_row.get("ma_20", feature_row.get("cp_ma20", np.nan)))

        is_price_rising = (div_gap > 0) or (z_price > 0.2) or (ret_5d > 0.01) or (not np.isnan(close_p) and not np.isnan(ma20_val) and close_p >= ma20_val)
        is_price_falling = (div_gap < 0) or (z_price < -0.2) or (ret_5d < -0.01) or (not np.isnan(close_p) and not np.isnan(ma20_val) and close_p <= ma20_val)

        is_holding_divergent_position = (
            (position_intent == "short" and fund_dir == "Bearish" and is_price_rising) or
            (position_intent == "long" and fund_dir == "Bullish" and is_price_falling)
        )

        if div_days >= self.severe_div_days or div_area >= self.severe_div_area or div_sev == "Severe":
            if is_holding_divergent_position:
                breached_layers.append("Layer 5: Divergence Ladder (Severe)")
                detailed_reasons.append(
                    f"同尺度重度背离 (div_days={div_days}>={self.severe_div_days}, div_area={div_area:.2f}>={self.severe_div_area})，禁止死扛基本面，强制平仓离场"
                )
                status = "FORCED_LIQUIDATION"
                max_leverage = 0.0
                action = "LIQUIDATE_IMMEDIATELY"
                dominant_risk = "Severe_Divergence"
            else:
                max_leverage = min(max_leverage, 0.30)
                if status == "PASS":
                    status = "CAUTION"
        elif div_days >= self.moderate_div_days or div_area >= self.moderate_div_area or div_sev == "Moderate":
            # 成本顺势通道及高利润牛市通道不依赖旧看空基本面；只改变本层判定，绝不覆盖前层硬否决。
            cost_trend_long = (
                entry_driver in ("COST_EXPECTATION", "HIGH_MARGIN_BULL")
                and position_intent == "long"
                and fund_dir == "Bearish"
            )
            breached_layers.append("Layer 5: Divergence Ladder (Moderate)")
            detailed_reasons.append(
                f"同尺度中度背离 (div_days={div_days}, div_area={div_area:.2f})，"
                + ("成本/产业顺势多头小预算警戒" if cost_trend_long else "限制仓位并锁定仅允许平仓")
            )
            if status != "FORCED_LIQUIDATION":
                status = ("CAUTION" if status == "PASS" else status) if cost_trend_long else "RESTRICT_CLOSE_ONLY"
                action = "DE_RISK_50"
            max_leverage = min(max_leverage, 0.50)
            dominant_risk = "Moderate_Divergence"
        elif div_days >= 1 or div_area >= 1.0 or div_sev == "Mild":
            breached_layers.append("Layer 5: Divergence Ladder (Mild)")
            detailed_reasons.append(f"同尺度轻度背离 (div_days={div_days}, div_area={div_area:.2f})，提示风控预警")
            if status == "PASS":
                status = "CAUTION"
            max_leverage = min(max_leverage, 0.70)
            if dominant_risk == "Normal":
                dominant_risk = "Mild_Divergence"

        return FirewallDecision(
            trade_date=trade_date,
            status=status,
            max_allowable_leverage=round(max_leverage, 2),
            action=action,
            breached_layers=breached_layers,
            detailed_reasons=detailed_reasons,
            dominant_risk_factor=dominant_risk,
        )

    def evaluate_batch(
        self,
        state_matrix: pd.DataFrame,
        features_df: pd.DataFrame,
        position_intents: Optional[pd.Series] = None,
    ) -> pd.DataFrame:
        """
        批量回溯评估历史数据集
        """
        assert (state_matrix.index == features_df.index).all(), "状态矩阵与特征宽表索引必须一致"

        records = []
        for idx in state_matrix.index:
            s_row = state_matrix.loc[idx]
            f_row = features_df.loc[idx]
            p_intent = position_intents.loc[idx] if position_intents is not None else "flat"
            
            decision = self.evaluate(s_row, f_row, position_intent=p_intent)
            records.append({
                "date": decision.trade_date,
                "firewall_status": decision.status,
                "max_allowable_leverage": decision.max_allowable_leverage,
                "firewall_action": decision.action,
                "breached_layers_count": len(decision.breached_layers),
                "breached_layers": "; ".join(decision.breached_layers),
                "dominant_risk_factor": decision.dominant_risk_factor,
                "detailed_reasons": " | ".join(decision.detailed_reasons),
            })

        res_df = pd.DataFrame(records, index=state_matrix.index)
        return res_df
