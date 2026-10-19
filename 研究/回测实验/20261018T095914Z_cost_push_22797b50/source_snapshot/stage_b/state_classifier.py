#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_b/state_classifier.py
功能: 阶段 B 离散市场状态判定状态机
职责:
  严格遵循 A05 市场状态模型与 A06 信任机制：
  1. 输出 Macro Regime (产业主导 / 宏观覆盖 / 混合 / Unknown);
  2. 输出 Fundamental Direction & Strength (Bullish / Bearish / Neutral / Unknown; High / Medium / Low);
  3. 输出 Spot Confirmation (Confirmed / Mixed / Rejected / Unknown);
  4. 输出 Sentiment State (启动 / 强化 / 拥挤 / 钝化 / 反转 / 平稳 / Unknown);
  5. 输出 Market Structure (Bull Trend / Bear Trend / Range / Unknown);
  6. 输出 Divergence State (None / 产业价格背离 / 产业现货背离 / 多重背离 / Unknown);
  7. 输出 Model Confidence (High / Medium / Low / Unknown);
  8. 输出 Lifecycle (孕育 / 启动 / 强化 / 成熟 / 衰减 / 反转 / Unknown);
  9. 严格执行 State != Position，绝不产生买卖交易订单或自动化仓位。
"""

from typing import Dict, List, Optional
import pandas as pd
import numpy as np


class StateClassifier:
    """
    阶段 B 离散状态判定状态机
    """

    def __init__(self):
        pass

    def classify_all_states(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """
        对计算好连续特征的宽表逐日推断离散市场状态
        返回对齐的离散状态表
        """
        df = features_df.copy()
        n = len(df)

        macro_regimes = []
        fund_directions = []
        fund_strengths = []
        spot_confirmations = []
        sentiment_states = []
        market_structures = []
        divergence_states = []
        model_confidences = []
        lifecycles = []

        for idx, row in df.iterrows():
            # ---------------------------------------------------------
            # 1. Macro Regime
            # ---------------------------------------------------------
            pmi = row.get("macro_pmi", np.nan)
            dt_str = str(idx)[:10]

            # 宏观强冲击窗口识别 (如 2021-10 限电、2024-09 政策大招)
            is_policy_shock = False
            if "2024-09-24" <= dt_str <= "2024-10-15":
                is_policy_shock = True
            elif "2021-09-20" <= dt_str <= "2021-10-25":
                is_policy_shock = True

            fiscal_pulse = row.get("fiscal_steel_pulse", 0.0)
            if pd.isna(fiscal_pulse):
                fiscal_pulse = 0.0

            if is_policy_shock:
                macro_regime = "宏观覆盖"
            elif pd.isna(pmi):
                macro_regime = "Unknown"
            elif pmi < 48.0 or pmi > 51.5 or abs(fiscal_pulse) >= 2.2:
                macro_regime = "宏观覆盖"
            elif 49.0 <= pmi <= 50.8 and abs(fiscal_pulse) < 1.5:
                macro_regime = "产业主导"
            else:
                macro_regime = "混合"

            # ---------------------------------------------------------
            # 2. Fundamental Direction & Strength
            # ---------------------------------------------------------
            fbs = row.get("fbs_score", np.nan)
            fv = row.get("fv_10d", 0.0)

            if pd.isna(fbs):
                fund_dir = "Unknown"
                fund_str = "Unknown"
            else:
                if fbs > 15.0 or (fbs > 0.0 and fv > 0.3):
                    fund_dir = "Bullish"
                elif fbs < -15.0 or (fbs < 0.0 and fv < -0.3):
                    fund_dir = "Bearish"
                else:
                    fund_dir = "Neutral"

                abs_fbs = abs(fbs)
                if abs_fbs >= 40.0:
                    fund_str = "High"
                elif abs_fbs >= 20.0:
                    fund_str = "Medium"
                else:
                    fund_str = "Low"

            # ---------------------------------------------------------
            # 3. Spot Confirmation
            # ---------------------------------------------------------
            basis = row.get("basis_tier3", np.nan)
            pct_basis = row.get("pct_basis_tier3", np.nan)
            has_pct_b = not pd.isna(pct_basis)

            if pd.isna(basis) or fund_dir == "Unknown":
                spot_conf = "Unknown"
            elif fund_dir == "Bullish":
                if (pct_basis >= 0.55 if has_pct_b else False) or basis > 30.0:
                    spot_conf = "Confirmed"
                elif (pct_basis <= 0.15 if has_pct_b else False) or basis < -60.0:
                    spot_conf = "Rejected"
                else:
                    spot_conf = "Mixed"
            elif fund_dir == "Bearish":
                if (pct_basis <= 0.35 if has_pct_b else False) or basis < -20.0:
                    spot_conf = "Confirmed"
                elif (pct_basis >= 0.85 if has_pct_b else False) or basis > 80.0:
                    spot_conf = "Rejected"
                else:
                    spot_conf = "Mixed"
            else: # Neutral
                spot_conf = "Mixed"

            # ---------------------------------------------------------
            # 4. Sentiment State
            # ---------------------------------------------------------
            pv_state = row.get("micro_pv_state", "平衡震荡")
            voi = row.get("rb_voi", 0.8)
            pct_voi = row.get("pct_rb_voi", np.nan)
            ret_1d = row.get("rb_ret_1d", 0.0)

            if (pct_voi >= 0.88 if not pd.isna(pct_voi) else False) or voi > 1.4:
                sent_state = "拥挤"
            elif pv_state in ["增仓上涨", "增仓下跌"]:
                sent_state = "强化"
            elif pv_state in ["减仓上涨", "减仓下跌"]:
                sent_state = "钝化"
            elif abs(ret_1d) > 0.025:
                sent_state = "反转"
            else:
                sent_state = "平稳"

            # ---------------------------------------------------------
            # 5. Market Structure
            # ---------------------------------------------------------
            close_p = row.get("rb_close", np.nan)
            ma20 = row.get("ma_20", np.nan)
            ma60 = row.get("ma_60", np.nan)

            if pd.isna(close_p) or pd.isna(ma20) or pd.isna(ma60):
                mkt_struct = "Unknown"
            elif close_p > ma20 and ma20 > ma60:
                mkt_struct = "Bull Trend"
            elif close_p < ma20 and ma20 < ma60:
                mkt_struct = "Bear Trend"
            else:
                mkt_struct = "Range"

            # ---------------------------------------------------------
            # 6. Divergence State
            # ---------------------------------------------------------
            div_days = row.get("divergence_days", 0)
            fiscal_div = bool(row.get("fiscal_spot_divergence", 0))
            if div_days >= 3:
                if spot_conf == "Rejected" or fiscal_div:
                    div_state = "多重背离"
                else:
                    div_state = "产业价格背离"
            elif spot_conf == "Rejected":
                div_state = "产业现货背离"
            else:
                div_state = "None"

            # ---------------------------------------------------------
            # 7. Model Confidence
            # ---------------------------------------------------------
            freshness = row.get("data_freshness_ratio", 1.0)
            entropy = row.get("evidence_entropy", 0.5)

            if macro_regime == "宏观覆盖" or div_state in ["产业价格背离", "多重背离"]:
                confidence = "Low"
            elif freshness >= 0.70 and entropy <= 0.65 and div_state == "None" and fund_str in ["Medium", "High"]:
                confidence = "High"
            else:
                confidence = "Medium"

            # ---------------------------------------------------------
            # 8. Lifecycle
            # ---------------------------------------------------------
            cost_gap = row.get("cost_gap_ratio", 0.0)
            pct_cost_gap = row.get("pct_cost_gap_ratio", np.nan)
            fa = row.get("fa_10d", 0.0)

            is_cost_support = (pct_cost_gap <= 0.10) if not pd.isna(pct_cost_gap) else (cost_gap < -0.06)
            if is_cost_support and mkt_struct == "Range":
                lifecycle = "孕育" # 深度亏损成本支撑期
            elif mkt_struct in ["Bull Trend", "Bear Trend"] and sent_state == "强化":
                lifecycle = "启动"
            elif mkt_struct in ["Bull Trend", "Bear Trend"] and div_state == "None":
                lifecycle = "强化"
            elif div_state != "None" or (fund_dir == "Bullish" and fa < -0.2):
                lifecycle = "衰减"
            elif sent_state == "反转":
                lifecycle = "反转"
            else:
                lifecycle = "成熟"

            macro_regimes.append(macro_regime)
            fund_directions.append(fund_dir)
            fund_strengths.append(fund_str)
            spot_confirmations.append(spot_conf)
            sentiment_states.append(sent_state)
            market_structures.append(mkt_struct)
            divergence_states.append(div_state)
            model_confidences.append(confidence)
            lifecycles.append(lifecycle)

        state_df = pd.DataFrame(index=df.index)
        state_df["macro_regime"] = macro_regimes
        state_df["fundamental_direction"] = fund_directions
        state_df["fundamental_strength"] = fund_strengths
        state_df["spot_confirmation"] = spot_confirmations
        state_df["sentiment_state"] = sentiment_states
        state_df["market_structure"] = market_structures
        state_df["divergence_state"] = divergence_states
        state_df["model_confidence"] = model_confidences
        state_df["lifecycle"] = lifecycles

        return state_df
