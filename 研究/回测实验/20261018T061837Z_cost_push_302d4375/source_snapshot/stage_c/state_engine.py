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

        # 8. 综合宏观与产业行情状态分类 (Market Regime Classification)
        state_matrix["market_regime"] = self._classify_market_regimes(df, state_matrix)
        # 旧字段保留用于兼容；候选不将经验持续期当成已验证持有期限。
        return state_matrix

    def _classify_market_regimes(self, features_df: pd.DataFrame, state_matrix: pd.DataFrame) -> pd.Series:
        """批量合成客观综合行情状态"""
        regimes = []
        for dt in features_df.index:
            f_row = features_df.loc[dt]
            s_row = state_matrix.loc[dt] if dt in state_matrix.index else pd.Series()
            c = float(f_row.get("rb_close", 0.0))
            ma20 = float(f_row.get("cp_ma20", f_row.get("ma_20", c)))
            ma60 = float(f_row.get("ma_60", np.nan))
            pacing_reg = str(s_row.get("macro_fiscal_regime", f_row.get("pacing_regime", "发债平稳运行期")))
            macro_bias = str(s_row.get("macro_policy_bias", "Neutral"))
            is_complex = bool(f_row.get("is_ferrous_complex_uptrend", True))
            cost_push = float(f_row.get("cost_push_spread_5d", 0.0))
            pct_basis_1y = float(f_row.get("pct_basis_tier3_1y", f_row.get("pct_basis_tier3", 0.5)))
            mkt_struct = str(s_row.get("market_structure", "Range"))
            cost_reg = str(s_row.get("cost_boundary_regime", "合理利润运行"))
            profit_bf = float(f_row.get("profit_bf", np.nan))
            vmm = float(f_row.get("virtual_mill_margin", 0.0))
            pct_vmm = float(f_row.get("pct_virtual_mill_margin", 0.5))
            pct_vmm_1y = float(f_row.get("pct_virtual_mill_margin_1y", pct_vmm))
            is_supply_high = bool(f_row.get("is_supply_high_or_rising", True))
            is_demand_high = bool(f_row.get("is_demand_high_or_stable", True))
            r_high20 = float(f_row.get("rolling_high_20", c))
            r_high120 = float(f_row.get("rolling_high_120", r_high20))
            max_cost_spread = float(f_row.get("rolling_max_spread_30", cost_push))
            is_secondary_peak = (r_high20 < r_high120 * 0.98) and (max_cost_spread >= 0.04)

            if (pacing_reg in ["发债高速冲刺期", "发债预期加速期"]) and (macro_bias == "Stimulus") and is_complex and (not np.isnan(ma60) and c >= ma60):
                regimes.append("MACRO_STIMULUS_UPTREND")
            elif (
                (vmm >= 450.0 or (pct_vmm >= 0.70 and vmm >= 200.0) or (pct_vmm_1y >= 0.70 and vmm >= 200.0) or (not np.isnan(profit_bf) and profit_bf >= 350.0))
                and (np.isnan(ma60) or c >= ma60 or ma20 >= ma60)
                and is_complex and is_supply_high and is_demand_high and cost_push >= -0.015 and pct_basis_1y >= 0.25
            ):
                regimes.append("HIGH_MARGIN_BULL")
            elif is_complex and (c >= ma20 * 0.99) and (not np.isnan(ma60) and c >= ma60 * 0.98) and (cost_push > 0.015) and (pct_basis_1y >= 0.25):
                regimes.append("COST_PUSH_BULL")
            elif is_secondary_peak and (c < ma20 * 0.995) and (np.isnan(ma60) or c < ma60) and (cost_push <= 0.005) and not (cost_reg == "深度亏损下轨支撑" or profit_bf <= -150.0):
                regimes.append("COST_COLLAPSE_BEAR")
            elif (s_row.get("macro_regime") == "宏观覆盖" and float(s_row.get("macro_override_intensity", 0.0)) >= 0.65) or (cost_push < -0.02 and pct_basis_1y < 0.25 and mkt_struct == "Range"):
                regimes.append("POLICY_INTERVENTION_CHOP")
            elif cost_reg == "深度亏损下轨支撑" or (not np.isnan(profit_bf) and profit_bf <= -150.0):
                regimes.append("DEEP_COST_FLOOR_SUPPORT")
            else:
                regimes.append("BALANCED_RANGE")
        return pd.Series(regimes, index=features_df.index)

    def save_state_matrix(self, state_matrix: pd.DataFrame) -> tuple[Path, Path]:
        """将状态矩阵双格式落盘"""
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        parquet_path = STATE_DIR / "阶段C_全景状态矩阵.parquet"
        csv_path = STATE_DIR / "阶段C_全景状态矩阵.csv"

        state_matrix.to_parquet(parquet_path, engine="pyarrow")
        state_matrix.to_csv(csv_path, encoding="utf-8-sig")

        return parquet_path, csv_path
