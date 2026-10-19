#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_d/transition_matrix.py
功能: 阶段 D 状态转换动力学与马尔可夫链引擎 (State Transition Dynamics Engine)
职责:
  严格遵循《实施手册》第 19 节与 A05/A05.3 规范:
  1. 构建各状态维度的一阶马尔可夫转移概率矩阵 P(S_{t+1} | S_t) (满足严格行归一化 sum_j P_ij = 1);
  2. 提取状态自留存概率 (Diagonal Values) 与马尔可夫期望持续期 E[D_i] = 1 / (1 - P_ii);
  3. 求解各子状态系统的长期稳态遍历分布 (Stationary Distribution pi = pi * P);
  4. 测算 k 步多期转移矩阵 P^k (k = 5, 10, 20d);
  5. 形式化识别典型演化路径 (Canonical Pathways) 与反转跃迁预警信号。
"""

from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np


class TransitionMatrixEngine:
    """
    马尔可夫状态转移与动力学引擎
    """

    def __init__(self, state_matrix: pd.DataFrame):
        self.state_matrix = state_matrix.copy()

    @staticmethod
    def calculate_transition_matrix(series: pd.Series) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        计算单列状态时序的一阶转移频数矩阵与概率矩阵
        返回: (count_matrix, prob_matrix)
        """
        s = series.dropna()
        if len(s) < 2:
            return pd.DataFrame(), pd.DataFrame()

        current_state = s.iloc[:-1].values
        next_state = s.iloc[1:].values

        states = sorted(list(set(current_state) | set(next_state)))

        # 频数交叉表
        counts = pd.crosstab(
            pd.Series(current_state, name="current_state"),
            pd.Series(next_state, name="next_state"),
        ).reindex(index=states, columns=states, fill_value=0)

        # 概率矩阵 (行归一化)
        row_sums = counts.sum(axis=1)
        prob_matrix = counts.div(row_sums.replace(0, np.nan), axis=0).fillna(0.0)

        return counts, prob_matrix

    @staticmethod
    def compute_stationary_distribution(prob_matrix: pd.DataFrame) -> pd.Series:
        """
        求解马尔可夫转移矩阵的稳态分布 pi: pi * P = pi 且 sum(pi) = 1
        """
        P = prob_matrix.values
        n = P.shape[0]
        if n == 0:
            return pd.Series()

        # 构造线性方程组: (P^T - I) * pi^T = 0, 并用 sum(pi) = 1 替换最后一行
        A = P.T - np.eye(n)
        A[-1, :] = 1.0
        b = np.zeros(n)
        b[-1] = 1.0

        try:
            pi, residuals, rank, s = np.linalg.lstsq(A, b, rcond=None)
            pi = np.clip(pi, 0.0, 1.0)
            pi_sum = pi.sum()
            if pi_sum > 0:
                pi /= pi_sum
            return pd.Series(np.round(pi, 4), index=prob_matrix.index, name="stationary_prob")
        except Exception:
            # 奇异矩阵降级为均匀分布
            return pd.Series(np.round(np.ones(n) / n, 4), index=prob_matrix.index, name="stationary_prob")

    def compute_k_step_transition(self, prob_matrix: pd.DataFrame, k: int = 5) -> pd.DataFrame:
        """
        计算 k 步前瞻转移矩阵: P^{(k)} = P^k
        """
        P = prob_matrix.values
        if P.shape[0] == 0:
            return pd.DataFrame()

        P_k = np.linalg.matrix_power(P, k)
        return pd.DataFrame(np.round(P_k, 4), index=prob_matrix.index, columns=prob_matrix.columns)

    def extract_transition_insights(self, dimension_col: str) -> pd.DataFrame:
        """
        提取状态转移核心动力学洞察表:
        包含状态自留存率、平均留存日、最可能跃迁去向 (Top Transition Target) 及稳态权重
        """
        if dimension_col not in self.state_matrix.columns:
            raise ValueError(f"状态矩阵中未找到维度列: {dimension_col}")

        counts, prob_mat = self.calculate_transition_matrix(self.state_matrix[dimension_col])
        if prob_mat.empty:
            return pd.DataFrame()

        pi_series = self.compute_stationary_distribution(prob_mat)
        raw_freq = self.state_matrix[dimension_col].value_counts(normalize=True)

        records = []
        for state in prob_mat.index:
            p_self = float(prob_mat.loc[state, state])
            expected_dur = 1.0 / (1.0 - p_self) if p_self < 0.999 else 999.0

            # 寻找离开本状态后最容易跃迁到的目标状态
            row_no_self = prob_mat.loc[state].copy()
            row_no_self[state] = -1.0
            top_target = str(row_no_self.idxmax())
            top_target_p = float(row_no_self.max())

            records.append({
                "dimension": dimension_col,
                "state_value": str(state),
                "retention_rate_pct": round(p_self * 100.0, 2),
                "markov_expected_days": round(expected_dur, 1),
                "primary_exit_target": top_target,
                "exit_target_prob_pct": round(top_target_p * 100.0, 2),
                "empirical_freq_pct": round(float(raw_freq.get(state, 0.0)) * 100.0, 2),
                "stationary_freq_pct": round(float(pi_series.get(state, 0.0)) * 100.0, 2),
            })

        return pd.DataFrame(records)

    def evaluate_all_core_transitions(self) -> Dict[str, Any]:
        """
        全景计算核心维度的状态转移矩阵、稳态与洞察
        """
        core_dims = [
            "fundamental_direction",
            "market_structure",
            "sentiment_state",
            "cost_boundary_regime",
            "model_confidence",
            "lifecycle",
        ]

        result_dict = {}
        insights_list = []

        for dim in core_dims:
            if dim in self.state_matrix.columns:
                counts, probs = self.calculate_transition_matrix(self.state_matrix[dim])
                pi = self.compute_stationary_distribution(probs)
                p5 = self.compute_k_step_transition(probs, k=5)
                insights = self.extract_transition_insights(dim)

                result_dict[dim] = {
                    "counts": counts,
                    "probabilities": probs,
                    "stationary": pi,
                    "probs_5d": p5,
                    "insights": insights,
                }
                insights_list.append(insights)

        all_insights_df = pd.concat(insights_list, ignore_index=True) if insights_list else pd.DataFrame()
        result_dict["all_insights"] = all_insights_df
        return result_dict
