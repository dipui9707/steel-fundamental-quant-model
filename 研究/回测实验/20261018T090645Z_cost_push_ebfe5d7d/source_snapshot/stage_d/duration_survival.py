#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_d/duration_survival.py
功能: 阶段 D 状态持续期与生存分析引擎 (Duration & Survival Analysis Engine)
职责:
  严格遵循《实施手册》第 19 节与 A05/A05.3 规范:
  1. 状态游程切分 (Run Length Encoding / Episode Detection): 准确切分连续状态运行区间并处理右截断;
  2. 持续期描述统计: 计算各状态的平均持续天数、中位数、标准差与极值分布;
  3. 非参数生存分析 (Kaplan-Meier Survival Estimation): 估计状态存续概率曲线 S(t) 与半衰期 (Half-life);
  4. 风险率分析 (Hazard Function h(t)): 检验状态是否具备“老化衰减效应”与临界反转窗口;
  5. 形式化导出结构化生存统计表与数据字典。
"""

from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np


class DurationSurvivalEngine:
    """
    状态持续期与生存分析引擎
    """

    def __init__(self, state_matrix: pd.DataFrame):
        self.state_matrix = state_matrix.copy()

    @staticmethod
    def extract_episodes(series: pd.Series) -> pd.DataFrame:
        """
        对单列时序状态进行连续游程 (Episodes) 切分
        """
        s = series.dropna()
        if len(s) == 0:
            return pd.DataFrame(columns=["state_value", "start_date", "end_date", "duration_days", "censored"])

        # 变点标记: 当前值与前一值不同即为新游程
        is_change = (s != s.shift(1))
        episode_ids = is_change.cumsum()

        episodes = []
        for ep_id, grp in s.groupby(episode_ids):
            state_val = grp.iloc[0]
            start_dt = grp.index[0]
            end_dt = grp.index[-1]
            dur = len(grp)
            # 若游程结束于原序列最后一日，标记为右截断 (censored)
            censored = (end_dt == s.index[-1])

            episodes.append({
                "episode_id": ep_id,
                "state_value": str(state_val),
                "start_date": str(start_dt)[:10],
                "end_date": str(end_dt)[:10],
                "duration_days": int(dur),
                "censored": bool(censored),
            })

        return pd.DataFrame(episodes)

    def calculate_duration_summary(self, dimension_col: str) -> pd.DataFrame:
        """
        计算特定状态维度的持续期汇总描述统计
        """
        if dimension_col not in self.state_matrix.columns:
            raise ValueError(f"状态矩阵中未找到维度列: {dimension_col}")

        episodes_df = self.extract_episodes(self.state_matrix[dimension_col])
        if episodes_df.empty:
            return pd.DataFrame()

        records = []
        total_episodes = len(episodes_df)

        for s_val, grp in episodes_df.groupby("state_value"):
            durs = grp["duration_days"]
            n_ep = len(grp)
            total_days = int(durs.sum())

            mean_dur = float(durs.mean())
            median_dur = float(durs.median())
            std_dur = float(durs.std(ddof=1)) if n_ep > 1 else 0.0

            records.append({
                "dimension": dimension_col,
                "state_value": s_val,
                "episode_count": n_ep,
                "episode_share_pct": round(n_ep / total_episodes * 100.0, 2),
                "total_days": total_days,
                "mean_days": round(mean_dur, 2),
                "median_days": round(median_dur, 1),
                "std_days": round(std_dur, 2),
                "min_days": int(durs.min()),
                "q25_days": round(float(durs.quantile(0.25)), 1),
                "q75_days": round(float(durs.quantile(0.75)), 1),
                "max_days": int(durs.max()),
            })

        res_df = pd.DataFrame(records).sort_values("total_days", ascending=False).reset_index(drop=True)
        return res_df

    def compute_kaplan_meier_survival(
        self,
        dimension_col: str,
        state_value: str,
        max_t: int = 60,
    ) -> pd.DataFrame:
        """
        对特定状态的特定取值计算 Kaplan-Meier 生存曲线与风险率
        """
        episodes_df = self.extract_episodes(self.state_matrix[dimension_col])
        grp = episodes_df[episodes_df["state_value"] == str(state_value)]

        if grp.empty:
            return pd.DataFrame(columns=["t_days", "at_risk", "events", "censored", "survival_prob", "hazard_rate"])

        durs = grp["duration_days"].values
        censored = grp["censored"].values
        total_n = len(durs)

        surv_prob = 1.0
        records = []

        for t in range(1, max_t + 1):
            # 持续至少 t 天的风险集 (at risk)
            at_risk = np.sum(durs >= t)
            if at_risk == 0:
                break

            # 恰好在第 t 天退出的事件数 (events, 非截断)
            events = np.sum((durs == t) & (censored == False))
            # 恰好在第 t 天被截断的样本数
            n_censored = np.sum((durs == t) & (censored))

            hazard = events / at_risk if at_risk > 0 else 0.0
            surv_prob *= (1.0 - hazard)

            records.append({
                "t_days": t,
                "at_risk": int(at_risk),
                "events": int(events),
                "censored": int(n_censored),
                "survival_prob": round(float(surv_prob), 4),
                "hazard_rate": round(float(hazard), 4),
            })

        return pd.DataFrame(records)

    def calculate_state_half_lives(self, dimension_col: str) -> pd.DataFrame:
        """
        测算指定维度下所有状态的留存半衰期 (Half-life, S(t) <= 0.50)
        """
        episodes_df = self.extract_episodes(self.state_matrix[dimension_col])
        records = []

        for s_val in sorted(episodes_df["state_value"].unique()):
            km_df = self.compute_kaplan_meier_survival(dimension_col, s_val, max_t=100)
            if km_df.empty:
                continue

            # 找到生存率跌破 50% 的首个 t
            sub_50 = km_df[km_df["survival_prob"] <= 0.50]
            if not sub_50.empty:
                half_life = int(sub_50.iloc[0]["t_days"])
            else:
                half_life = int(km_df.iloc[-1]["t_days"])

            # 找到生存率跌破 20% 的首个 t
            sub_20 = km_df[km_df["survival_prob"] <= 0.20]
            dur_20 = int(sub_20.iloc[0]["t_days"]) if not sub_20.empty else int(km_df.iloc[-1]["t_days"])

            # 提取最大风险率所在的特征时间
            max_hazard_row = km_df.sort_values("hazard_rate", ascending=False).iloc[0]

            records.append({
                "dimension": dimension_col,
                "state_value": s_val,
                "half_life_days": half_life,
                "p20_survival_days": dur_20,
                "peak_hazard_day": int(max_hazard_row["t_days"]),
                "peak_hazard_rate": round(float(max_hazard_row["hazard_rate"]), 3),
            })

        return pd.DataFrame(records)

    def calculate_all_core_durations(self) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        全景测算核心状态维度的持续期分布与半衰期
        """
        core_dims = [
            "fundamental_direction",
            "cost_boundary_regime",
            "spot_confirmation",
            "sentiment_state",
            "market_structure",
            "divergence_severity",
            "model_confidence",
            "lifecycle",
        ]

        summary_dfs = []
        half_life_dfs = []

        for dim in core_dims:
            if dim in self.state_matrix.columns:
                sum_df = self.calculate_duration_summary(dim)
                hl_df = self.calculate_state_half_lives(dim)
                summary_dfs.append(sum_df)
                half_life_dfs.append(hl_df)

        full_summary = pd.concat(summary_dfs, ignore_index=True) if summary_dfs else pd.DataFrame()
        full_half_life = pd.concat(half_life_dfs, ignore_index=True) if half_life_dfs else pd.DataFrame()

        return full_summary, full_half_life
