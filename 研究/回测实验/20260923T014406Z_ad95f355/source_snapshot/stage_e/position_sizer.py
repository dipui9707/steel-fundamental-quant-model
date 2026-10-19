#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/position_sizer.py
功能: 阶段 E 仓位管理与风险预算器 (Position Sizer & Risk Budgeter)
职责:
  1. 结合模型置信度 (Confidence Score) 与信号强度实施动态连续缩放;
  2. 严格受制于风控防火墙赋权的最大杠杆上限 (Firewall Leverage Cap);
  3. 计算目标手数 (Target Lots)、名义敞口、保证金占用与有效杠杆率;
  4. 按决策时价格约束仓位；不保证跳空或无法成交时的损失上限。
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional
import numpy as np
from framework_rules import HIGH_VOL_LEVERAGE_CAP

from stage_e.risk_filter import VettedSignal


@dataclass(frozen=True)
class PositionTarget:
    trade_date: str
    target_direction: str  # "LONG", "SHORT", "FLAT"
    target_weight: float  # 带符号的名义持仓权重 (-1.0 ~ 1.0)
    target_lots: int  # 带符号的目标手数 (+做多, -做空, 0空仓)
    target_nominal_value: float  # 名义货值 (元)
    estimated_margin: float  # 预估占用保证金 (元)
    margin_utilization: float  # 保证金占用率 (0.0 ~ 1.0)
    effective_leverage: float  # 有效名义杠杆 (0.0 ~ 1.0)
    rationale: str


class PositionSizer:
    """
    仓位管理与手数映射器
    """

    def __init__(
        self,
        contract_multiplier: int = 10,  # 螺纹钢 10 吨/手
        default_margin_rate: float = 0.10,  # 交易所+期货公司保证金率 10%
        max_base_leverage: Optional[float] = None,  # 基准名义杠杆 (可选，若不指定则由最高资金利用率自动推导)
        max_margin_utilization: float = 0.50,  # 最高资金利用率上限 (默认 50% 左右)
        cash_buffer_ratio: Optional[float] = None,  # 最低留存现金安全垫
    ):
        self.contract_multiplier = contract_multiplier
        self.default_margin_rate = default_margin_rate
        self.max_margin_utilization = max_margin_utilization
        if max_base_leverage is not None:
            self.max_base_leverage = max_base_leverage
        else:
            self.max_base_leverage = max_margin_utilization / default_margin_rate
        self.cash_buffer_ratio = (
            cash_buffer_ratio if cash_buffer_ratio is not None else max(0.10, 1.0 - self.max_margin_utilization)
        )

    def calculate_position_target(
        self,
        vetted_signal: VettedSignal,
        current_equity: float,
        current_price: float,
        current_lots: int = 0,
        risk_distance: Optional[float] = None,
        risk_budget_fraction: Optional[float] = None,
        scale_by_confidence: bool = True,
    ) -> PositionTarget:
        """
        根据终审信号、当前账户净值与最新盘面价格计算目标手数
        """
        date_str = vetted_signal.trade_date

        if vetted_signal.vetted_direction == "FLAT" or current_equity <= 0 or current_price <= 0:
            return PositionTarget(
                trade_date=date_str,
                target_direction="FLAT",
                target_weight=0.0,
                target_lots=0,
                target_nominal_value=0.0,
                estimated_margin=0.0,
                margin_utilization=0.0,
                effective_leverage=0.0,
                rationale=(
                    f"空仓指令 (防火墙={vetted_signal.firewall_status}: {vetted_signal.veto_reason})"
                    if vetted_signal.is_vetoed
                    else "策略保持空仓观望"
                ),
            )

        sign = 1.0 if vetted_signal.vetted_direction == "LONG" else -1.0

        # 1. 动态置信度缩放系数: 将 [40, 100] 平滑映射至 [0.75, 1.00]
        conf = vetted_signal.raw_signal.confidence_score
        conf_multiplier = float(np.clip(0.75 + 0.25 * ((conf - 40.0) / 40.0), 0.75, 1.00))

        # 2. 产业确定性系数: 将 [0.3, 1.0] 平滑映射至 [0.70, 1.00]
        strength = vetted_signal.raw_signal.strength
        conviction_factor = float(np.clip(0.70 + 0.30 * strength, 0.70, 1.00))

        if not scale_by_confidence:
            conf_multiplier = conviction_factor = 1.0

        # 3. 风控防火墙容量乘数 (PASS=1.0, CAUTION=0.70, RESTRICT=0.35, FORCED=0.0)
        firewall_ratio = vetted_signal.target_leverage_cap

        # 4. 根据最高资金利用率上限 (如 50%) 与基准杠杆上限计算最大允许手数与名义敞口
        lot_value = current_price * self.contract_multiplier
        lot_margin = lot_value * self.default_margin_rate
        eff_max_leverage = min(self.max_base_leverage, self.max_margin_utilization / self.default_margin_rate)

        # 机制 2 落地: 成本逼空战略侦察轻仓 (Asymmetric Pilot Sizing) 与高波动脱困试仓
        is_pilot = bool(getattr(vetted_signal.raw_signal, "is_pilot_squeeze", False))
        is_high_vol = bool(getattr(vetted_signal.raw_signal, "is_high_vol_pilot", False))
        if is_pilot:
            eff_max_leverage = min(eff_max_leverage, 0.80)  # 严格将杠杆压制在 0.80x (资金利用率 <= 8%)
        elif is_high_vol:
            eff_max_leverage = min(eff_max_leverage, HIGH_VOL_LEVERAGE_CAP)  # 高波动脱困区首笔试仓爬坡制 (杠杆 <= 2.00x, 保证金利用率 <= 20%)

        max_allowed_margin = current_equity * eff_max_leverage * self.default_margin_rate

        if lot_margin > 0:
            max_lots = int(np.floor(max_allowed_margin / lot_margin))
        else:
            max_lots = 0

        # 5. 目标手数缩放 (含 Carry 顺逆风自适应调节与高波动硬隔离)
        carry_mult = float(getattr(vetted_signal.raw_signal, "carry_multiplier", 1.0))
        carry_regime = str(getattr(vetted_signal.raw_signal, "carry_regime", "NEUTRAL"))
        # 高波动脱困区或成本逼空侦察底仓严格禁止顺风放大仓位，杜绝极端行情下的杠杆放大风险
        if is_high_vol or is_pilot:
            carry_mult = min(1.0, carry_mult)

        target_lots_count = int(
            np.floor(max_lots * conviction_factor * conf_multiplier * firewall_ratio * carry_mult)
        )

        # 风险预算是损失距离约束，不把置信度当胜率。缺风险距离时禁止风险预算开仓。
        if risk_budget_fraction is not None:
            if risk_distance is None or not np.isfinite(risk_distance) or risk_distance <= 0:
                target_lots_count = 0
            else:
                risk_lots = int(current_equity * risk_budget_fraction / (risk_distance * self.contract_multiplier))
                target_lots_count = min(target_lots_count, max(0, risk_lots))
        if vetted_signal.firewall_status == "RESTRICT_CLOSE_ONLY":
            target_lots_count = min(target_lots_count, abs(current_lots)) if current_lots * sign > 0 else 0
        signed_lots = int(sign * target_lots_count)
        actual_nominal = abs(signed_lots) * lot_value
        margin_required = actual_nominal * self.default_margin_rate

        # 严格边界保护: 保证保证金占用不超过最高资金利用率
        if margin_required > max_allowed_margin and lot_margin > 0:
            signed_lots = int(sign * max_lots)
            actual_nominal = abs(signed_lots) * lot_value
            margin_required = actual_nominal * self.default_margin_rate

        effective_lev = actual_nominal / current_equity if current_equity > 0 else 0.0
        margin_util = margin_required / current_equity if current_equity > 0 else 0.0

        pilot_tag = " [成本逼空战略侦察底仓]" if is_pilot else (" [高波动防跳空试仓]" if is_high_vol else "")
        carry_tag = f" [Carry({carry_regime})={carry_mult:.2f}x]" if carry_mult != 1.0 else ""
        rationale = (
            f"目标仓位: {vetted_signal.vetted_direction} {abs(signed_lots)}手{pilot_tag}{carry_tag} "
            f"(资金利用率={margin_util*100:.1f}%, 杠杆={effective_lev:.2f}x, 置信度={conf:.0f}, 强度={strength:.2f}, "
            f"防火墙={vetted_signal.firewall_status})"
        )


        return PositionTarget(
            trade_date=date_str,
            target_direction=vetted_signal.vetted_direction,
            target_weight=round(sign * effective_lev, 4),
            target_lots=signed_lots,
            target_nominal_value=round(actual_nominal, 2),
            estimated_margin=round(margin_required, 2),
            margin_utilization=round(margin_util, 4),
            effective_leverage=round(effective_lev, 4),
            rationale=rationale,
        )
