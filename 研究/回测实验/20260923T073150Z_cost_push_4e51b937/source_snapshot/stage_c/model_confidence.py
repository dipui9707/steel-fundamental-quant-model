#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/model_confidence.py
功能: 阶段 C 模型信任机制、生命周期与信息真空降级引擎 (Model Confidence & Fallback Engine)
职责:
  严格遵循《实施手册》第 4.6 节、第 9 节与 A06 信任机制规范:
  1. 计算模型综合信任评分 (Confidence Score: 0 ~ 100);
  2. 离散模型可信度分级 (Model Confidence: High / Medium / Low / Unknown);
  3. 信息真空与外部覆盖降级模式 (Fallback Regime: FULL_RESEARCH / MARKET_ONLY / INSUFFICIENT_DATA);
  4. 行情生命周期识别 (Lifecycle: 孕育 / 启动 / 强化 / 成熟 / 衰减 / 反转 / Unknown);
  5. 状态预期持续期推断 (Persistence: High / Medium / Low / Unknown 与预估交易日跨度);
  6. 绝不把持续背离视作加仓机会，背离必须导致模型信任度降低。
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class ModelConfidenceClassifier:
    """
    模型信任机制与降级分类器
    """

    def __init__(self):
        pass

    def classify_row(
        self,
        macro_dict: Dict[str, Any],
        fund_dict: Dict[str, Any],
        spot_dict: Dict[str, Any],
        sent_dict: Dict[str, Any],
        mkt_dict: Dict[str, Any],
        features_row: pd.Series,
    ) -> Dict[str, Any]:
        """
        综合单日各维度状态判定模型信任度与生命周期
        """
        macro_reg = macro_dict.get("macro_regime", "Unknown")
        is_shock = macro_dict.get("external_shock_flag", False)

        fund_dir = fund_dict.get("fundamental_direction", "Unknown")
        fund_str = fund_dict.get("fundamental_strength", "Low")
        cost_reg = fund_dict.get("cost_boundary_regime", "合理利润运行")

        spot_conf = spot_dict.get("spot_confirmation", "Unknown")

        sent_st = sent_dict.get("sentiment_state", "平稳")
        crowd_rk = sent_dict.get("crowding_risk", "Normal")

        mkt_struct = mkt_dict.get("market_structure", "Range")
        div_st = mkt_dict.get("divergence_state", "None")
        div_sev = mkt_dict.get("divergence_severity", "None")

        freshness = float(features_row.get("data_freshness_ratio", 1.0))
        entropy = float(features_row.get("evidence_entropy", 0.5))
        fa_10d = float(features_row.get("fa_10d", 0.0))

        # ---------------------------------------------------------
        # 1. Continuous Confidence Score (基础满分 85 分)
        # ---------------------------------------------------------
        score = 85.0

        # A. 宏观覆盖惩罚
        if macro_reg == "宏观覆盖" or is_shock:
            score -= 35.0
        elif macro_reg == "混合":
            score -= 10.0

        # B. 同尺度背离惩罚
        if div_sev == "Severe":
            score -= 30.0
        elif div_sev == "Moderate":
            score -= 18.0
        elif div_sev == "Mild":
            score -= 6.0

        # C. 现货否认惩罚
        if spot_conf == "Rejected":
            score -= 22.0
        elif spot_conf == "Mixed":
            score -= 6.0

        # D. 情绪极端拥挤惩罚
        if crowd_rk == "Extreme":
            score -= 15.0
        elif crowd_rk == "Elevated":
            score -= 8.0

        # E. 数据新鲜度衰减惩罚
        if freshness < 0.60:
            score -= 20.0
        elif freshness < 0.75:
            score -= 10.0

        # F. 证据熵 (分歧度) 惩罚
        if entropy > 0.75:
            score -= 15.0
        elif entropy > 0.65:
            score -= 8.0

        # G. 确认奖励
        if spot_conf == "Confirmed" and div_st == "None":
            score += 12.0
        if freshness >= 0.85 and entropy <= 0.50:
            score += 8.0
        if fund_str == "High":
            score += 8.0

        # 有界截断 [10.0, 95.0]
        score = float(np.clip(score, 10.0, 95.0))

        # ---------------------------------------------------------
        # 2. Discrete Model Confidence
        # ---------------------------------------------------------
        if fund_dir == "Unknown" or macro_reg == "Unknown":
            confidence = "Unknown"
        elif score >= 70.0:
            confidence = "High"
        elif score >= 45.0:
            confidence = "Medium"
        else:
            confidence = "Low"

        # ---------------------------------------------------------
        # 3. Fallback Regime (信息降级模式)
        # ---------------------------------------------------------
        if freshness < 0.40:
            fallback = "INSUFFICIENT_DATA"
        elif confidence == "Low" and (macro_reg == "宏观覆盖" or div_sev in ["Severe", "Moderate"]):
            fallback = "MARKET_ONLY"
        else:
            fallback = "FULL_RESEARCH"

        # ---------------------------------------------------------
        # 4. Lifecycle (行情生命周期阶段)
        # ---------------------------------------------------------
        if cost_reg == "深度亏损下轨支撑" and mkt_struct == "Range":
            lifecycle = "孕育"
        elif mkt_struct in ["Bull Trend", "Bear Trend"] and sent_st == "启动":
            lifecycle = "启动"
        elif mkt_struct in ["Bull Trend", "Bear Trend"] and sent_st == "强化" and div_st == "None":
            lifecycle = "强化"
        elif sent_st == "反转" or div_sev == "Severe":
            lifecycle = "反转"
        elif sent_st == "钝化" or fa_10d < -0.25:
            lifecycle = "衰减"
        else:
            lifecycle = "成熟"

        # ---------------------------------------------------------
        # 5. Persistence (预期持续期与预估交易日跨度)
        # ---------------------------------------------------------
        if confidence == "High" and mkt_struct in ["Bull Trend", "Bear Trend"] and div_st == "None":
            persistence = "High"
            expected_span = "15-30天"
        elif confidence in ["High", "Medium"] and mkt_struct != "Range":
            persistence = "Medium"
            expected_span = "5-15天"
        elif confidence == "Low" or mkt_struct == "Range" or div_sev == "Severe":
            persistence = "Low"
            expected_span = "1-5天"
        else:
            persistence = "Unknown"
            expected_span = "未知"

        return {
            "model_confidence": confidence,
            "confidence_score": round(score, 2),
            "fallback_regime": fallback,
            "lifecycle": lifecycle,
            "persistence": persistence,
            "expected_persistence_span": expected_span,
        }
