#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/state_engine.py
功能: 阶段 C 统一状态合成高层门面引擎 (Unified State Synthesis Engine)
职责:
  整合阶段 C 六大子引擎:
  1. MacroRegimeClassifier (宏观政策与外部冲击);
  2. FundamentalStateClassifier (实物供需矛盾与成本下轨);
  3. SpotStateClassifier (现货确认与微观蓄水池流动性);
  4. SentimentStateClassifier (情绪生命周期与跨品种共振);
  5. MarketStructureClassifier (形态通道与同尺度背离积分);
  6. ModelConfidenceClassifier (模型信任机制、降级模式与持续期);
  产出格式统一、无未来函数、严格对齐 PIT 的全景状态矩阵。
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

from stage_c.regime_macro import MacroRegimeClassifier
from stage_c.state_fundamental import FundamentalStateClassifier
from stage_c.state_spot import SpotStateClassifier
from stage_c.state_sentiment import SentimentStateClassifier
from stage_c.market_structure import MarketStructureClassifier
from stage_c.model_confidence import ModelConfidenceClassifier
from stage_c.mechanism_engine import MechanismEngine

BASE_DIR = Path(__file__).resolve().parent.parent
STATE_DIR = BASE_DIR / "数据" / "状态"


class StageCStateEngine:
    """
    阶段 C 市场状态模型综合推断引擎门面
    """

    def __init__(self):
        self.macro_clf = MacroRegimeClassifier()
        self.fund_clf = FundamentalStateClassifier()
        self.spot_clf = SpotStateClassifier()
        self.sent_clf = SentimentStateClassifier()
        self.mkt_clf = MarketStructureClassifier()
        self.conf_clf = ModelConfidenceClassifier()

    def synthesize_states(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """
        对已计算好的连续特征宽表逐日推断并合成全景状态矩阵
        """
        df = features_df.copy()
        n = len(df)

        # 1. 批量运行宏观引擎
        macro_df = self.macro_clf.classify_all(df)

        # 2. 批量运行基本面引擎
        fund_df = self.fund_clf.classify_all(df)

        # 3. 运行现货引擎 (依赖基本面方向)
        spot_df = self.spot_clf.classify_all(df, fund_directions=fund_df["fundamental_direction"])

        # 4. 运行情绪与共振引擎
        sent_df = self.sent_clf.classify_all(df)

        # 5. 运行价格结构与背离引擎 (依赖现货确认)
        mkt_df = self.mkt_clf.classify_all(df, spot_confirmations=spot_df["spot_confirmation"])

        # 6. 综合各维度推断模型信任机制与生命周期
        conf_records = []
        for idx in df.index:
            m_dict = macro_df.loc[idx].to_dict()
            f_dict = fund_df.loc[idx].to_dict()
            s_dict = spot_df.loc[idx].to_dict()
            sent_dict = sent_df.loc[idx].to_dict()
            mkt_dict = mkt_df.loc[idx].to_dict()
            feat_row = df.loc[idx]

            conf_rec = self.conf_clf.classify_row(
                macro_dict=m_dict,
                fund_dict=f_dict,
                spot_dict=s_dict,
                sent_dict=sent_dict,
                mkt_dict=mkt_dict,
                features_row=feat_row,
            )
            conf_records.append(conf_rec)

        conf_df = pd.DataFrame(conf_records, index=df.index)

        # 7. 合成全景状态矩阵
        state_matrix = pd.concat([
            macro_df,
            fund_df,
            spot_df,
            sent_df,
            mkt_df,
            conf_df
        ], axis=1)

        # 附带核心标尺指标以供下游阶段 D/E 无缝查询
        state_matrix["fbs_score"] = df["fbs_score"]
        state_matrix["basis_tier3"] = df["basis_tier3"]
        state_matrix["rb_close"] = df["rb_close"]
        if "data_freshness_ratio" in df.columns:
            state_matrix["data_freshness_ratio"] = df["data_freshness_ratio"]

        mechanism_states, self.mechanism_events = MechanismEngine().evaluate(df)
        state_matrix = pd.concat([state_matrix, mechanism_states], axis=1)
        state_matrix["legacy_inventory_trajectory"] = state_matrix["inventory_trajectory"]
        state_matrix["inventory_trajectory"] = state_matrix["physical_inventory_trajectory"]
        state_matrix["observed_leader_type"] = df.get("dominant_leader_type", pd.Series("UNKNOWN", index=df.index)).replace({
            "RAW_MATERIAL_SHOCK":"RAW_MATERIAL_PRICE_LEAD",
            "FINISHED_STEEL_DEMAND":"FINISHED_STEEL_PRICE_LEAD"})
        state_matrix["confidence_score_meaning"] = "HEURISTIC_CONSISTENCY_NOT_PROBABILITY"
        # 旧字段保留用于兼容；候选不将经验持续期当成已验证持有期限。
        return state_matrix

    def save_state_matrix(self, state_matrix: pd.DataFrame) -> tuple[Path, Path]:
        """将状态矩阵双格式落盘"""
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        parquet_path = STATE_DIR / "阶段C_全景状态矩阵.parquet"
        csv_path = STATE_DIR / "阶段C_全景状态矩阵.csv"

        state_matrix.to_parquet(parquet_path, engine="pyarrow")
        state_matrix.to_csv(csv_path, encoding="utf-8-sig")

        return parquet_path, csv_path
