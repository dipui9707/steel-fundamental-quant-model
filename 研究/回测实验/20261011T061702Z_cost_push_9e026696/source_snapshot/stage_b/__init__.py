"""
钢材产业基本面量化系统 - 阶段 B：数据与低代码研究模型 (Stage B Quantitative Research Model)
"""

from stage_b.data_pipeline import DataPipeline
from stage_b.feature_engine import FeatureEngine
from stage_b.state_classifier import StateClassifier
from stage_b.factor_research import FactorResearcher
from stage_b.hypothesis_verifier import HypothesisVerifier
from stage_b.dashboard import DashboardGenerator
from stage_b.model import StageBModel

__all__ = [
    "DataPipeline",
    "FeatureEngine",
    "StateClassifier",
    "FactorResearcher",
    "HypothesisVerifier",
    "DashboardGenerator",
    "StageBModel",
]

__version__ = "Stage-B-0.2-refined"
