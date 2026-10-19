#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
包: stage_e
功能: 阶段 E 回测与模拟交易系统 (Backtesting and Simulated Trading System)
架构: State -> Signal -> Risk Firewall -> Position & Execution -> Performance
"""

from stage_e.signal_generator import TradingSignal, SignalGenerator
from stage_e.risk_filter import VettedSignal, RiskFilterAdapter
from stage_e.position_sizer import PositionTarget, PositionSizer
from stage_e.contract_rollover import RolloverEvent, ContractRolloverManager
from stage_e.execution_engine import TradeRecord, ExecutionEngine
from stage_e.performance_analyzer import PerformanceAnalyzer
from stage_e.trade_recorder import TradeRecorder
from stage_e.backtest_engine import BacktestResult, BacktestEngine
from stage_e.dashboard import StageEDashboardGenerator
from stage_e.tactical_exhaustion_engine import (
    TacticalConfig,
    TacticalTrade,
    TacticalExhaustionEngine,
    MicroFeatureEngineering,
)
from stage_e.tactical_adapter import TacticalExecutionAdapter, TacticalExecutionStatus

__all__ = [
    "TradingSignal",
    "SignalGenerator",
    "VettedSignal",
    "RiskFilterAdapter",
    "PositionTarget",
    "PositionSizer",
    "RolloverEvent",
    "ContractRolloverManager",
    "TradeRecord",
    "ExecutionEngine",
    "PerformanceAnalyzer",
    "TradeRecorder",
    "BacktestResult",
    "BacktestEngine",
    "StageEDashboardGenerator",
    "TacticalConfig",
    "TacticalTrade",
    "TacticalExhaustionEngine",
    "MicroFeatureEngineering",
    "TacticalExecutionAdapter",
    "TacticalExecutionStatus",
]
