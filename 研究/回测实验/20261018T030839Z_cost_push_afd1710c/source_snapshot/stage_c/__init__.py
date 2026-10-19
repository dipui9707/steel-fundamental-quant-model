#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
包: stage_c
功能: 钢材产业基本面量化系统 - 阶段 C 状态模型系统 (Market State Model)
版本: Stage-C-0.1
职责:
  严格遵循《实施手册》第 4 节、第 7-11 节与 A05/A05.1/A05.2/A06 规范:
  1. 宏观与外部环境状态引擎 (Macro Regime);
  2. 产业基本面供需矛盾与成本支撑引擎 (Fundamental State);
  3. 现货微观确认与蓄水池流动性引擎 (Spot State);
  4. 市场情绪、持仓微观结构与跨品种共振引擎 (Sentiment & Microstructure);
  5. 价格结构形态与同尺度产业背离积分引擎 (Market Structure & Divergence);
  6. 模型信任机制、生命周期与信息真空降级引擎 (Model Confidence & Fallback);
  7. 统一状态合成高层门面 (StateEngine);
  8. 状态条件收益评估引擎 (StateEvaluator);
  9. 全景交互可视化看板生成器 (StageCDashboardGenerator);
  10. 坚决执行 State != Position，不产生任何自动化交易仓位。
"""

__version__ = "Stage-C-0.1"

from stage_c.regime_macro import MacroRegimeClassifier
from stage_c.state_fundamental import FundamentalStateClassifier
from stage_c.state_spot import SpotStateClassifier
from stage_c.state_sentiment import SentimentStateClassifier
from stage_c.market_structure import MarketStructureClassifier
from stage_c.model_confidence import ModelConfidenceClassifier
from stage_c.risk_firewall import RiskControlFirewall, FirewallDecision
from stage_c.state_engine import StageCStateEngine
from stage_c.state_evaluator import StateEvaluator
from stage_c.dashboard import StageCDashboardGenerator

__all__ = [
    "__version__",
    "MacroRegimeClassifier",
    "FundamentalStateClassifier",
    "SpotStateClassifier",
    "SentimentStateClassifier",
    "MarketStructureClassifier",
    "ModelConfidenceClassifier",
    "RiskControlFirewall",
    "FirewallDecision",
    "StageCStateEngine",
    "StateEvaluator",
    "StageCDashboardGenerator",
]

