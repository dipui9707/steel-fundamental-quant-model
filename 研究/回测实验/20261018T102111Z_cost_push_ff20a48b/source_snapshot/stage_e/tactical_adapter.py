#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/tactical_adapter.py
功能: 宏观日线产业系统与微观15分钟战术执行引擎跨周期联立适配器 (Tactical Execution Adapter)
定位与职责:
  1. 【资产范围硬约束】: 专门聚焦且仅对螺纹钢 (RB) 与热轧卷板 (HC) 激活战术护航，焦煤/焦炭等原料品种严格隔离直通;
  2. 【宏观-微观跨周期协同 (Macro-Tactical Handover)】:
     - 宏观产业日线层 (Stage A-D): 输出波段大方向 (LONG / SHORT / FLAT) 与安全仓位预算;
     - 战术执行层 (Tactical Engine): 负责在波段持仓期内进行 15 分钟级别微观动态风控与全平全回补;
  3. 【全天候守护机制】:
     - 趋势初期: 突破结构防守线 (Initial Structural Stop, 15点缓冲) 严防恶性假突破破位，同时容忍正常蓄势洗盘;
     - 趋势中后期: 15分钟级别动能衰竭与微观右侧拐点全平锁利 (PIVOT_EXIT);
     - 回调企稳: 充分洗盘后右侧企稳全额回补 (PIVOT_RE_ENTRY);
     - 跳空断头铡: 开盘20分钟内跳空未延续果断终止趋势 (GAP_EXHAUSTION_EXIT);
     - 震荡箱体: 假突破停滞敏捷识别并退出 (CHOPPY_REGIME_EXIT);
  4. 【双向状态互锁 (Bi-directional Sync)】:
     - 战术层触发退出时，主动向宏观系统报备 `is_tactical_terminated=True`，阻止日线机械重复追单;
     - 宏观系统基本面反转或防火墙否决时，下达 `force_macro_exit` 强制清仓重置。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from stage_e.tactical_exhaustion_engine import (
    TacticalConfig,
    TacticalTrade,
    TacticalExhaustionEngine,
    MicroFeatureEngineering
)


@dataclass
class TacticalExecutionStatus:
    """战术执行适配器当前实时状态"""
    symbol: str
    is_supported: bool
    is_active: bool
    macro_direction: str            # "LONG", "SHORT", "FLAT"
    current_position_lots: int      # 当前实际持仓手数 (+多, -空, 0平)
    is_tactical_terminated: bool    # 是否被战术层主动终止趋势交易
    termination_reason: str
    total_realized_pnl: float
    total_fees: float
    trade_count: int


class TacticalExecutionAdapter:
    """
    跨周期战术执行适配器
    """

    SUPPORTED_SYMBOLS: Tuple[str, ...] = ("rb", "hc")

    def __init__(
        self,
        symbol: str = "rb",
        config: Optional[TacticalConfig] = None,
        contract_multiplier: int = 10,
        tick_size: float = 1.0,
    ):
        self.raw_symbol = symbol
        self.symbol = symbol.lower()
        self.is_supported = self.symbol in self.SUPPORTED_SYMBOLS
        self.contract_multiplier = contract_multiplier
        self.tick_size = tick_size

        self.config = config or TacticalConfig()
        # 针对螺纹热卷自动校准参数
        if self.is_supported:
            self.config.exit_timeframe = "15m"
            self.config.enable_phase_sensitivity = True
            self.config.enable_initial_structural_stop = True
            self.config.initial_stop_buffer_ticks = 15.0

        self.engine = TacticalExhaustionEngine(self.config)

        # 运行期状态追踪
        self.macro_direction: str = "FLAT"
        self.current_position_lots: int = 0
        self.is_tactical_terminated: bool = False
        self.termination_reason: str = ""
        self.active_entry_price: float = 0.0

        self.tactical_trades: List[TacticalTrade] = []
        self.total_realized_pnl: float = 0.0
        self.total_fees: float = 0.0

    @classmethod
    def is_symbol_supported(cls, symbol: str) -> bool:
        """检查品种是否在战术执行适配器支持白名单中 (仅支持螺纹与热卷)"""
        sym = symbol.lower()
        # 处理可能带有的前缀或后缀，如 SHFE.rb2410 -> rb
        for s in cls.SUPPORTED_SYMBOLS:
            if s in sym:
                return True
        return False

    def reset(self):
        """重置适配器内部状态机"""
        self.macro_direction = "FLAT"
        self.current_position_lots = 0
        self.is_tactical_terminated = False
        self.termination_reason = ""
        self.active_entry_price = 0.0
        self.tactical_trades.clear()
        self.total_realized_pnl = 0.0
        self.total_fees = 0.0

    def get_status(self) -> TacticalExecutionStatus:
        """获取当前适配器状态快照"""
        return TacticalExecutionStatus(
            symbol=self.symbol,
            is_supported=self.is_supported,
            is_active=(self.current_position_lots != 0),
            macro_direction=self.macro_direction,
            current_position_lots=self.current_position_lots,
            is_tactical_terminated=self.is_tactical_terminated,
            termination_reason=self.termination_reason,
            total_realized_pnl=self.total_realized_pnl,
            total_fees=self.total_fees,
            trade_count=len(self.tactical_trades),
        )

    def process_intraday_episode(
        self,
        df_intraday_5m: pd.DataFrame,
        macro_direction: str,
        allocated_lots: int,
        initial_capital: float = 1_000_000.0,
        start_idx: int = 10,
    ) -> Dict[str, Any]:
        """
        处理单波段行情或连续分时流
        
        参数:
            df_intraday_5m: 5分钟分时 K 线数据
            macro_direction: 宏观系统给出的波段大方向 ("LONG" 或 "SHORT")
            allocated_lots: 分配的最大风控手数
            initial_capital: 初始分配资金
            start_idx: 开仓起始 Bar 索引
        """
        if not self.is_supported:
            return {
                "status": "SKIPPED_UNSUPPORTED_SYMBOL",
                "symbol": self.symbol,
                "message": f"品种 {self.symbol} 不在战术执行白名单 (仅限 rb/hc)，执行直通 pass-through",
                "final_position": allocated_lots if macro_direction == "LONG" else (-allocated_lots if macro_direction == "SHORT" else 0),
                "strategy_pnl": 0.0
            }

        if macro_direction not in ("LONG", "SHORT"):
            # 宏观中性或空仓
            self.reset()
            return {
                "status": "FLAT",
                "symbol": self.symbol,
                "final_position": 0,
                "strategy_pnl": 0.0,
                "trades": []
            }

        # 检查是否此前已被战术终止且尚未收到宏观重置
        if self.is_tactical_terminated and self.macro_direction == macro_direction:
            return {
                "status": "TACTICAL_TERMINATED_LOCKED",
                "symbol": self.symbol,
                "message": f"战术层已终止趋势交易 ({self.termination_reason})，锁定空仓防磨损",
                "final_position": 0,
                "strategy_pnl": 0.0,
                "trades": []
            }

        self.macro_direction = macro_direction
        self.is_tactical_terminated = False
        self.termination_reason = ""

        # 启动战术执行引擎进行分时精细化模拟
        result = self.engine.run_backtest(
            df_5m=df_intraday_5m,
            trend_direction=macro_direction,
            initial_capital=initial_capital,
            lots=allocated_lots,
            contract_multiplier=self.contract_multiplier,
            start_idx=start_idx
        )

        # 同步交易记录与终盘状态
        trades: List[TacticalTrade] = result.get("trades", [])
        self.tactical_trades.extend(trades)
        self.total_realized_pnl += result.get("strategy_pnl", 0.0)
        self.current_position_lots = result.get("final_position", 0)

        # 检查是否以战术终止退出
        if trades:
            last_trade = trades[-1]
            if last_trade.trade_type in ("GAP_EXHAUSTION_EXIT", "CHOPPY_REGIME_EXIT", "INITIAL_BREAKOUT_FAILED"):
                self.is_tactical_terminated = True
                self.termination_reason = f"{last_trade.trade_type}: {last_trade.reason}"
                self.current_position_lots = 0

        result["tactical_status"] = self.get_status()
        return result

    def force_macro_exit(
        self,
        exit_price: float,
        exit_time: str,
        reason: str = "MACRO_SIGNAL_INVERSION"
    ) -> Optional[TacticalTrade]:
        """
        当宏观大系统发生大级别方向逆转或防火墙一票否决时，强制执行战术平仓清盘
        """
        if self.current_position_lots == 0:
            self.macro_direction = "FLAT"
            return None

        lots = abs(self.current_position_lots)
        slippage_val = self.config.slippage_ticks * self.tick_size
        fee = self.config.commission_per_lot * lots

        if self.current_position_lots > 0:
            exec_p = exit_price - slippage_val
            pnl = (exec_p - self.active_entry_price) * lots * self.contract_multiplier - fee
        else:
            exec_p = exit_price + slippage_val
            pnl = (self.active_entry_price - exec_p) * lots * self.contract_multiplier - fee

        self.total_realized_pnl += pnl
        self.total_fees += fee

        force_trade = TacticalTrade(
            trade_id=f"FORCE_{len(self.tactical_trades)+1:03d}",
            trade_type="MACRO_FORCE_EXIT",
            time=exit_time,
            price=exec_p,
            direction="FLAT",
            lots=lots,
            pnl=pnl,
            fees=fee,
            reason=f"宏观日线大系统指令强制清盘 [{reason}]"
        )
        self.tactical_trades.append(force_trade)
        self.current_position_lots = 0
        self.macro_direction = "FLAT"
        self.is_tactical_terminated = False
        self.termination_reason = ""

        return force_trade
