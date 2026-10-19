#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_d/__init__.py
功能: 阶段 D (收益与交易研究 - Returns & Trading Dynamics Research) 核心模块库
定位:
  严格遵循《实施手册》第 19 节与 A05/A05.3 规范:
  解构 P(Future Return | Market State)，
  提供条件收益分布、状态持续期与生存分析、MFE/MAE 风险曲面、
  状态转移马尔可夫动力学、入场与退出机制对比实证五大引擎，
  以及统一高层门面与交互式可视化看板。
"""

from stage_d.return_distribution import ReturnDistributionEngine
from stage_d.duration_survival import DurationSurvivalEngine
from stage_d.mfe_mae_profile import MfeMaeProfileEngine
from stage_d.transition_matrix import TransitionMatrixEngine
from stage_d.entry_exit_research import EntryExitResearchEngine
from stage_d.research_engine import StageDResearchEngine
from stage_d.dashboard import StageDDashboardGenerator

__all__ = [
    "ReturnDistributionEngine",
    "DurationSurvivalEngine",
    "MfeMaeProfileEngine",
    "TransitionMatrixEngine",
    "EntryExitResearchEngine",
    "StageDResearchEngine",
    "StageDDashboardGenerator",
]
