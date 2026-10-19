#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/state_sentiment.py
功能: 阶段 C 市场情绪、持仓微观结构与跨品种共振引擎 (Sentiment & Microstructure Engine)
职责:
  严格遵循《实施手册》第 4.4 节、第 10 节与 A05.2 规范:
  1. 情绪生命周期判定 (启动 / 强化 / 拥挤 / 钝化 / 反转 / 平稳 / Unknown);
  2. 极端拥挤度与换手风险识别 (Crowding Risk: Extreme / Elevated / Normal);
  3. 黑色五品种截面广度与共振识别 (Cross Commodity Resonance: 板块多头共振 / 板块空头共振 / 品种分化博弈);
  4. 坚持 State != Position，不把情绪状态当作单纯买卖扳机。
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class SentimentStateClassifier:
    """
    市场情绪与微观博弈分类器
    """

    def __init__(self):
        pass

    def classify_row(self, row: pd.Series, prev_pv: str = "平衡震荡") -> Dict[str, Any]:
        """
        对单日截面推断情绪与微观博弈状态
        """
        voi = row.get("rb_voi", 0.8)
        pct_voi = row.get("pct_rb_voi", np.nan)
        ret_1d = row.get("rb_ret_1d", 0.0)
        pv_state = row.get("micro_pv_state", "平衡震荡")
        margin_z = row.get("virtual_margin_zscore", 0.0)

        # ---------------------------------------------------------
        # 1. Sentiment State (情绪生命周期阶段: 历史分位数自适应 + 原料逼仓联动)
        # ---------------------------------------------------------
        is_raw_squeeze = bool(row.get("is_raw_material_squeeze", False))
        is_crowded = is_raw_squeeze or ((pct_voi >= 0.88 or voi > 1.40) if not pd.isna(pct_voi) else (voi > 1.40))

        if pd.isna(ret_1d):
            sent_state = "Unknown"
        elif is_crowded:
            sent_state = "拥挤" # 极端换手与博弈白热化
        elif abs(ret_1d) > 0.028:
            sent_state = "反转" # 情绪剧烈转向与日内踩踏
        elif pv_state in ["增仓上涨", "增仓下跌"]:
            if prev_pv == pv_state:
                sent_state = "强化" # 连续增仓驱动
            else:
                sent_state = "启动" # 资金首日大举建仓
        elif pv_state in ["减仓上涨", "减仓下跌"]:
            sent_state = "钝化" # 止盈平仓，动能衰竭
        else:
            sent_state = "平稳"

        # ---------------------------------------------------------
        # 2. Crowding Risk (微观筹码拥挤度: 历史分位数自适应 + 原料逼仓溢出)
        # ---------------------------------------------------------
        is_raw_squeeze = bool(row.get("is_raw_material_squeeze", False))

        if is_raw_squeeze:
            crowding = "Extreme"
        elif not pd.isna(pct_voi):
            if pct_voi >= 0.92 or voi > 1.50 or abs(margin_z) > 2.2:
                crowding = "Extreme"
            elif pct_voi >= 0.80 or voi > 1.25 or abs(margin_z) > 1.6:
                crowding = "Elevated"
            else:
                crowding = "Normal"
        else:
            if voi > 1.50 or abs(margin_z) > 2.2:
                crowding = "Extreme"
            elif voi > 1.25 or abs(margin_z) > 1.6:
                crowding = "Elevated"
            else:
                crowding = "Normal"

        return {
            "sentiment_state": sent_state,
            "crowding_risk": crowding,
        }

    def compute_commodity_resonance(self, df: pd.DataFrame) -> pd.Series:
        """
        计算黑色系 5 大品种 (螺纹 RB、热卷 HC、铁矿 I、焦炭 J、焦煤 JM) 截面协同共振
        """
        rets = {}
        for sym in ["rb", "hc", "i", "j", "jm"]:
            c_col = f"{sym}_close"
            if c_col in df.columns:
                rets[sym] = df[c_col].pct_change().fillna(0.0)

        rets_df = pd.DataFrame(rets, index=df.index)
        n_syms = len(rets_df.columns)

        resonances = []
        for _, row in rets_df.iterrows():
            pos_count = (row > 0.006).sum()
            neg_count = (row < -0.006).sum()

            if pos_count >= 4:
                resonances.append("板块多头共振")
            elif neg_count >= 4:
                resonances.append("板块空头共振")
            else:
                resonances.append("品种分化博弈")

        return pd.Series(resonances, index=df.index, name="cross_commodity_resonance")

    def classify_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """批量推断情绪宽表"""
        records = []
        prev_pv = "平衡震荡"
        for _, row in df.iterrows():
            rec = self.classify_row(row, prev_pv=prev_pv)
            records.append(rec)
            prev_pv = row.get("micro_pv_state", "平衡震荡")

        res_df = pd.DataFrame(records, index=df.index)
        res_df["cross_commodity_resonance"] = self.compute_commodity_resonance(df)
        if "dominant_leader_sym" in df.columns:
            res_df["dominant_leader_sym"] = df["dominant_leader_sym"]
        if "dominant_leader_type" in df.columns:
            res_df["dominant_leader_type"] = df["dominant_leader_type"]
        return res_df
