#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/risk_filter.py
功能: 阶段 E 风控防火墙绝对否决适配器 (Risk Firewall Veto Adapter)
职责:
  严格履行《A06.1 风控防火墙与背离熔断设计规范》:
  1. 将 stage_c.risk_firewall.RiskControlFirewall 嵌入策略信号执行流水线;
  2. 确立“绝对否决权法则”:
     - 当防火墙输出 FORCED_LIQUIDATION 时，强制清空持仓并启动 3 日冷却期;
     - 当防火墙输出 TRADING_HALT 时，强制平仓停机;
     - 当防火墙输出 RESTRICT_CLOSE_ONLY 时，严禁新开仓，严禁原料逼仓时做空成材;
     - 当防火墙输出 CAUTION 时，杠杆上限压制至 70%;
  3. 输出不可篡改的 VettedSignal 实体。
"""

from dataclasses import dataclass
from typing import Dict, Any, Optional, List
import pandas as pd

from stage_c.risk_firewall import RiskControlFirewall, FirewallDecision
from stage_e.signal_generator import TradingSignal


@dataclass(frozen=True)
class VettedSignal:
    trade_date: str
    vetted_direction: str  # "LONG", "SHORT", "FLAT"
    target_leverage_cap: float  # 0.0 ~ 1.0
    firewall_status: str  # PASS / CAUTION / RESTRICT_CLOSE_ONLY / FORCED_LIQUIDATION / TRADING_HALT
    is_vetoed: bool
    veto_reason: str
    raw_signal: TradingSignal
    firewall_decision: FirewallDecision


class RiskFilterAdapter:
    """
    风控防火墙终审过滤器
    """

    def __init__(self, cooling_days_after_liquidation: int = 3):
        self.firewall = RiskControlFirewall()
        self.cooling_days_after_liquidation = cooling_days_after_liquidation
        self._cooling_counter = 0
        self._cooling_reason = ""

    def vet_signal(
        self,
        date_str: str,
        raw_signal: TradingSignal,
        state_row: pd.Series,
        feature_row: pd.Series,
        current_holding_direction: str = "FLAT",  # 当前实际持仓方向
    ) -> VettedSignal:
        """
        对策略原始信号进行风控防火墙终审
        """
        # 将原始意图映射为防火墙接口入参
        intent_map = {"LONG": "long", "SHORT": "short", "FLAT": "flat"}
        pos_intent = intent_map.get(raw_signal.direction, "flat")

        # 若当前正持有头寸且意图反向或平仓，先以当前持仓评估防火墙
        current_intent = intent_map.get(current_holding_direction, "flat")
        eval_intent = pos_intent if pos_intent != "flat" else current_intent

        is_pilot = bool(getattr(raw_signal, "is_pilot_squeeze", False))
        decision: FirewallDecision = self.firewall.evaluate(
            state_row=state_row,
            feature_row=feature_row,
            position_intent=eval_intent,
            is_pilot_squeeze=is_pilot,
        )

        # 反手必须同时审查已有风险与新意图，不能靠更换方向绕过旧仓止损。
        if current_intent != "flat" and current_intent != eval_intent:
            held_decision = self.firewall.evaluate(state_row=state_row, feature_row=feature_row,
                position_intent=current_intent, is_pilot_squeeze=is_pilot)
            priority = {"PASS":0, "CAUTION":1, "RESTRICT_CLOSE_ONLY":2,
                        "FORCED_LIQUIDATION":3, "TRADING_HALT":4}
            decision = max((decision, held_decision), key=lambda d:(priority[d.status], -d.max_allowable_leverage))

        # 检查是否处于强制斩仓后的冷却期
        if self._cooling_counter > 0:
            self._cooling_counter -= 1
            veto_msg = (
                f"处于极端脉冲/破位强制斩仓后的冷却期 (剩余 {self._cooling_counter + 1} 天): "
                f"{self._cooling_reason}"
            )
            return VettedSignal(
                trade_date=date_str,
                vetted_direction="FLAT",
                target_leverage_cap=0.0,
                firewall_status="FORCED_LIQUIDATION",
                is_vetoed=True,
                veto_reason=veto_msg,
                raw_signal=raw_signal,
                firewall_decision=decision,
            )

        # 1. 第一重与第三/四重: 熔断与停机
        if decision.status == "TRADING_HALT":
            return VettedSignal(
                trade_date=date_str,
                vetted_direction="FLAT",
                target_leverage_cap=0.0,
                firewall_status="TRADING_HALT",
                is_vetoed=True,
                veto_reason="触发数据真空/时滞中断停机防火墙 (TRADING_HALT)",
                raw_signal=raw_signal,
                firewall_decision=decision,
            )

        if decision.status == "FORCED_LIQUIDATION":
            # 启动冷却期
            self._cooling_counter = self.cooling_days_after_liquidation
            self._cooling_reason = " | ".join(decision.detailed_reasons)
            return VettedSignal(
                trade_date=date_str,
                vetted_direction="FLAT",
                target_leverage_cap=0.0,
                firewall_status="FORCED_LIQUIDATION",
                is_vetoed=True,
                veto_reason=f"触发强制斩仓熔断/技术硬止损: {self._cooling_reason}",
                raw_signal=raw_signal,
                firewall_decision=decision,
            )

        # 2. 第二重: 跨品种逼仓挤仓隔离墙 或 中度背离
        if decision.status == "RESTRICT_CLOSE_ONLY":
            # 仅允许平仓，禁止新开仓与加仓
            # 若信号与当前持仓同向，说明试图加仓或新开仓 -> 否决
            # 若当前为空仓且信号开仓 -> 否决
            if current_holding_direction == "FLAT" and raw_signal.direction != "FLAT":
                return VettedSignal(
                    trade_date=date_str,
                    vetted_direction="FLAT",
                    target_leverage_cap=0.0,
                    firewall_status="RESTRICT_CLOSE_ONLY",
                    is_vetoed=True,
                    veto_reason=f"防火墙锁定仅平仓 (RESTRICT_CLOSE_ONLY)，严禁新开仓: {' | '.join(decision.detailed_reasons)}",
                    raw_signal=raw_signal,
                    firewall_decision=decision,
                )
            elif (
                current_holding_direction != "FLAT"
                and raw_signal.direction == current_holding_direction
            ):
                # 试图同向加仓，依据风险预算且不高于当前手数
                return VettedSignal(
                    trade_date=date_str,
                    vetted_direction=current_holding_direction,
                    target_leverage_cap=min(0.50, decision.max_allowable_leverage),
                    firewall_status="RESTRICT_CLOSE_ONLY",
                    is_vetoed=True,
                    veto_reason=f"防火墙限仓仅平仓，目标不得超过当前持仓或预算上限: {' | '.join(decision.detailed_reasons)}",
                    raw_signal=raw_signal,
                    firewall_decision=decision,
                )
            elif (
                current_holding_direction != "FLAT"
                and raw_signal.direction != current_holding_direction
            ):
                # 信号指示平仓或反转，允许平仓
                return VettedSignal(
                    trade_date=date_str,
                    vetted_direction="FLAT",  # 仅允许平仓，不允许反手开新仓
                    target_leverage_cap=0.0,
                    firewall_status="RESTRICT_CLOSE_ONLY",
                    is_vetoed=True,
                    veto_reason=f"防火墙限仓仅平仓，允许平仓离场，禁止反向开新仓",
                    raw_signal=raw_signal,
                    firewall_decision=decision,
                )

        # 3. 第五重: 轻度背离与警戒
        if decision.status == "CAUTION":
            cap = min(0.70, decision.max_allowable_leverage)
            return VettedSignal(
                trade_date=date_str,
                vetted_direction=raw_signal.direction,
                target_leverage_cap=cap,
                firewall_status="CAUTION",
                is_vetoed=(raw_signal.direction != "FLAT"),
                veto_reason=f"轻度背离/波动率预警，杠杆上限限缩至 {cap*100:.0f}%",
                raw_signal=raw_signal,
                firewall_decision=decision,
            )

        # 4. 全通放行
        return VettedSignal(
            trade_date=date_str,
            vetted_direction=raw_signal.direction,
            target_leverage_cap=1.00,
            firewall_status="PASS",
            is_vetoed=False,
            veto_reason="无风险阻碍，完全通过",
            raw_signal=raw_signal,
            firewall_decision=decision,
        )
