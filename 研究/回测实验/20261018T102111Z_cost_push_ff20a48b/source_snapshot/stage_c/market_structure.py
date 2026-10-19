#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/market_structure.py
功能: 阶段 C 价格结构形态、波动率与同尺度背离积分引擎 (Market Structure & Divergence Engine)
职责:
  严格遵循《实施手册》第 4.5 节、第 8 节与 A05/A05.1 规范:
  1. 价格运动形态识别 (Bull Trend / Bear Trend / Range / Unknown);
  2. 波动率环境识别 (Volatility Regime: Expanding / Normal / Compressed);
  3. 同尺度产业-价格背离状态推断 (None / 产业价格背离 / 产业现货背离 / 多重背离 / Unknown);
  4. 累计背离面积与天数严重程度分级 (Divergence Severity: Severe / Moderate / Mild / None);
  5. 明确“基本面与价格背离是正式市场状态”，持续背离须触发下游信任惩罚。
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class MarketStructureClassifier:
    """
    价格结构与同尺度背离积分分类器
    """

    def __init__(self):
        pass

    def compute_volatility_regimes(self, df: pd.DataFrame, window: int = 20) -> pd.Series:
        """
        计算滚动 20 日已实现波动率及分位数状态
        """
        ret = df["rb_ret_1d"].fillna(0.0) if "rb_ret_1d" in df.columns else df["rb_close"].pct_change().fillna(0.0)
        roll_vol = ret.rolling(window=window, min_periods=5).std() * np.sqrt(250)

        # 扩展窗口分位数 (避免前向未来函数)
        vol_regimes = []
        for i in range(len(df)):
            if i < window:
                vol_regimes.append("Normal")
                continue

            hist_vol = roll_vol.iloc[: i + 1].dropna()
            cur_v = roll_vol.iloc[i]

            if pd.isna(cur_v) or len(hist_vol) < 20:
                vol_regimes.append("Normal")
                continue

            q25 = hist_vol.quantile(0.25)
            q75 = hist_vol.quantile(0.75)

            if cur_v > q75:
                vol_regimes.append("Expanding")
            elif cur_v < q25:
                vol_regimes.append("Compressed")
            else:
                vol_regimes.append("Normal")

        return pd.Series(vol_regimes, index=df.index, name="volatility_regime")

    def classify_row(
        self,
        row: pd.Series,
        spot_conf: str = "Mixed",
        vol_regime: str = "Normal"
    ) -> Dict[str, Any]:
        """
        对单日截面推断价格结构与背离状态
        """
        close_p = row.get("rb_close", np.nan)
        ma20 = row.get("ma_20", np.nan)
        ma60 = row.get("ma_60", np.nan)

        div_days = int(row.get("divergence_days", 0))
        div_area = float(row.get("divergence_area", 0.0))

        # ---------------------------------------------------------
        # 1. Market Structure (形态多空与通道)
        # ---------------------------------------------------------
        if pd.isna(close_p) or pd.isna(ma20) or pd.isna(ma60):
            mkt_struct = "Unknown"
        elif close_p > ma20 and ma20 > ma60 and close_p > ma60 * 1.01:
            mkt_struct = "Bull Trend"
        elif close_p < ma20 and ma20 < ma60 and close_p < ma60 * 0.99:
            mkt_struct = "Bear Trend"
        else:
            mkt_struct = "Range"

        # ---------------------------------------------------------
        # 2. Divergence State (同尺度背离状态)
        # ---------------------------------------------------------
        if div_days >= 3:
            if spot_conf == "Rejected":
                div_state = "多重背离"
            else:
                div_state = "产业价格背离"
        elif spot_conf == "Rejected":
            div_state = "产业现货背离"
        else:
            div_state = "None"

        # ---------------------------------------------------------
        # 3. Divergence Severity (背离严重程度分级)
        # ---------------------------------------------------------
        if div_days >= 8 or div_area >= 15.0:
            div_severity = "Severe"
        elif div_days >= 4 or div_area >= 6.0:
            div_severity = "Moderate"
        elif div_days >= 1 or div_area >= 1.0:
            div_severity = "Mild"
        else:
            div_severity = "None"

        return {
            "market_structure": mkt_struct,
            "volatility_regime": vol_regime,
            "divergence_state": div_state,
            "divergence_severity": div_severity,
            "divergence_days": div_days,
            "divergence_area": round(div_area, 4),
        }

    def classify_all(
        self,
        df: pd.DataFrame,
        spot_confirmations: Optional[pd.Series] = None
    ) -> pd.DataFrame:
        """批量推断价格结构宽表"""
        vol_series = self.compute_volatility_regimes(df)

        records = []
        for idx, row in df.iterrows():
            spot_c = spot_confirmations.loc[idx] if spot_confirmations is not None else "Mixed"
            vol_r = vol_series.loc[idx]
            rec = self.classify_row(row, spot_conf=spot_c, vol_regime=vol_r)
            records.append(rec)

        res_df = pd.DataFrame(records, index=df.index)
        return res_df
