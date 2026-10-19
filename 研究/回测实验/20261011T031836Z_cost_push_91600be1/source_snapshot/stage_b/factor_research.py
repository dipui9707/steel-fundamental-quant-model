#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_b/factor_research.py
功能: 阶段 B 单变量与单因子有效性研究引擎
职责:
  1. 计算因子对未来 N 日收益 (5d, 10d, 20d) 的 Rank IC, Pearson IC, ICIR 与 T-stat;
  2. 执行五分位数分组检验 (Q1~Q5), 计算各组未来收益率、单调性得分与多空对冲收益;
  3. 检验各离散市场状态下的前瞻收益分布 P(Return | State);
  4. 输出严密的统计学评估与可解释性分析报告。
"""

from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np
from scipy import stats


class FactorResearcher:
    """
    阶段 B 单变量量化检验与收益分布研究引擎
    """

    def __init__(self, forward_horizons: List[int] = [5, 10, 20]):
        self.horizons = forward_horizons

    def prepare_forward_returns(self, features_df: pd.DataFrame) -> pd.DataFrame:
        """为特征宽表追加未来 N 个交易日的前瞻对数/百分比收益率"""
        df = features_df.copy()
        close = df["rb_close"]
        for h in self.horizons:
            # 严格前瞻收益: Close_{t+h} / Close_t - 1
            df[f"fwd_ret_{h}d"] = (close.shift(-h) / close - 1.0)
        return df

    def evaluate_factor_ic(
        self,
        df: pd.DataFrame,
        factor_cols: List[str]
    ) -> pd.DataFrame:
        """
        计算因子的 Rank IC (Spearman), Pearson IC, ICIR 与 T-stat
        """
        records = []
        for factor in factor_cols:
            if factor not in df.columns:
                continue
            
            s_factor = df[factor].dropna()
            for h in self.horizons:
                ret_col = f"fwd_ret_{h}d"
                valid = df[[factor, ret_col]].dropna()
                if len(valid) < 30:
                    continue

                if valid[factor].std() == 0 or valid[ret_col].std() == 0:
                    continue

                # Pearson IC
                pearson_ic, pearson_p = stats.pearsonr(valid[factor], valid[ret_col])
                # Rank IC (Spearman)
                rank_ic, rank_p = stats.spearmanr(valid[factor], valid[ret_col])

                if np.isnan(rank_ic):
                    rank_ic = 0.0
                    rank_p = 1.0
                if np.isnan(pearson_ic):
                    pearson_ic = 0.0

                # 滚动 60 日 IC 序列计算 ICIR
                roll_ic = valid[factor].rolling(60).corr(valid[ret_col]).dropna()
                if len(roll_ic) > 10 and roll_ic.std() > 0:
                    icir = roll_ic.mean() / roll_ic.std() * np.sqrt(250.0 / h)
                else:
                    icir = 0.0

                n = len(valid)
                t_stat = rank_ic * np.sqrt((n - 2) / max(1e-6, 1.0 - rank_ic ** 2))

                records.append({
                    "factor": factor,
                    "horizon": f"{h}d",
                    "rank_ic": round(rank_ic, 4),
                    "rank_pvalue": round(rank_p, 4),
                    "pearson_ic": round(pearson_ic, 4),
                    "icir": round(icir, 2),
                    "t_stat": round(t_stat, 2),
                    "n_samples": n
                })

        return pd.DataFrame(records)

    def evaluate_quantiles(
        self,
        df: pd.DataFrame,
        factor_col: str,
        horizon: int = 10,
        n_quantiles: int = 5
    ) -> Tuple[pd.DataFrame, float]:
        """
        五分位数分组检验 (Q1 为因子最低组，Q5 为因子最高组)
        返回各组年化收益、胜率、夏普、单调性得分
        """
        ret_col = f"fwd_ret_{horizon}d"
        valid = df[[factor_col, ret_col]].dropna().copy()
        if len(valid) < 50:
            return pd.DataFrame(), 0.0

        # 分组 (qcut)
        try:
            valid["quantile"] = pd.qcut(valid[factor_col], q=n_quantiles, labels=[f"Q{i+1}" for i in range(n_quantiles)], duplicates="drop")
        except Exception:
            return pd.DataFrame(), 0.0

        stats_records = []
        q_means = []
        for q in [f"Q{i+1}" for i in range(n_quantiles)]:
            sub = valid[valid["quantile"] == q][ret_col]
            if len(sub) == 0:
                continue
            mean_ret = sub.mean()
            q_means.append(mean_ret)
            ann_ret = mean_ret * (250.0 / horizon)
            vol = sub.std() * np.sqrt(250.0 / horizon)
            sharpe = (ann_ret / vol) if vol > 0 else 0.0
            win_rate = (sub > 0).mean()

            stats_records.append({
                "quantile": q,
                "count": len(sub),
                "mean_ret_pct": round(mean_ret * 100, 2),
                "annualized_ret_pct": round(ann_ret * 100, 2),
                "annualized_vol_pct": round(vol * 100, 2),
                "sharpe": round(sharpe, 2),
                "win_rate_pct": round(win_rate * 100, 1)
            })

        # 单调性得分 (Spearman corr between quantile index and mean return)
        if len(q_means) >= 3:
            mono_score, _ = stats.spearmanr(range(len(q_means)), q_means)
        else:
            mono_score = 0.0

        return pd.DataFrame(stats_records), round(mono_score, 3)

    def evaluate_state_conditional_returns(
        self,
        merged_df: pd.DataFrame,
        horizon: int = 10
    ) -> pd.DataFrame:
        """
        评估在不同离散市场状态下的前瞻收益分布 P(Return | State)
        """
        ret_col = f"fwd_ret_{horizon}d"
        if ret_col not in merged_df.columns:
            return pd.DataFrame()

        records = []
        dim_cols = [
            ("Fundamental Direction", "fundamental_direction"),
            ("Spot Confirmation", "spot_confirmation"),
            ("Market Structure", "market_structure"),
            ("Divergence State", "divergence_state"),
            ("Model Confidence", "model_confidence"),
            ("Lifecycle", "lifecycle")
        ]

        for dim_title, col in dim_cols:
            if col not in merged_df.columns:
                continue
            for val, group in merged_df.groupby(col):
                sub = group[ret_col].dropna()
                if len(sub) < 10:
                    continue
                mean_r = sub.mean()
                win_r = (sub > 0).mean()
                ann_r = mean_r * (250.0 / horizon)
                vol = sub.std() * np.sqrt(250.0 / horizon)
                sharpe = (ann_r / vol) if vol > 0 else 0.0

                records.append({
                    "state_dimension": dim_title,
                    "state_value": str(val),
                    "sample_days": len(sub),
                    f"mean_ret_{horizon}d_pct": round(mean_r * 100, 2),
                    "win_rate_pct": round(win_r * 100, 1),
                    "annualized_ret_pct": round(ann_r * 100, 2),
                    "annualized_vol_pct": round(vol * 100, 2),
                    "sharpe_ratio": round(sharpe, 2)
                })

        return pd.DataFrame(records)

    def evaluate_factor_decay_curve(
        self,
        features_df: pd.DataFrame,
        factor_col: str,
        decay_horizons: List[int] = [1, 2, 3, 5, 10, 15, 20, 30, 40, 60]
    ) -> pd.DataFrame:
        """
        计算因子在不同预测周期 (1d 至 60d) 的 Rank IC 衰减曲线
        测算信息半衰期 (Half-Life)
        """
        close = features_df["rb_close"]
        records = []
        for h in decay_horizons:
            fwd_ret = close.shift(-h) / close - 1.0
            valid = pd.DataFrame({"factor": features_df[factor_col], "ret": fwd_ret}).dropna()
            if len(valid) < 30 or valid["factor"].std() == 0 or valid["ret"].std() == 0:
                continue

            rank_ic, p_val = stats.spearmanr(valid["factor"], valid["ret"])
            t_stat = rank_ic * np.sqrt((len(valid) - 2) / max(1e-6, 1.0 - rank_ic ** 2))
            records.append({
                "factor": factor_col,
                "horizon_days": h,
                "rank_ic": round(rank_ic, 4),
                "p_value": round(p_val, 4),
                "t_stat": round(t_stat, 2),
                "sample_count": len(valid)
            })

        df_decay = pd.DataFrame(records)
        return df_decay

    def compute_quantile_cumulative_returns(
        self,
        features_df: pd.DataFrame,
        factor_col: str,
        horizon: int = 10,
        n_quantiles: int = 5
    ) -> pd.DataFrame:
        """
        计算各分位组的累积复合净值轨迹与多空对冲组合收益
        """
        close = features_df["rb_close"]
        ret_h = (close.shift(-horizon) / close - 1.0)
        valid = pd.DataFrame({"factor": features_df[factor_col], "ret": ret_h}, index=features_df.index).dropna()
        if len(valid) < 100:
            return pd.DataFrame()

        try:
            valid["quantile"] = pd.qcut(valid["factor"], q=n_quantiles, labels=[f"Q{i+1}" for i in range(n_quantiles)], duplicates="drop")
        except Exception:
            return pd.DataFrame()

        # 按交易日采样非重叠或平滑净值
        sample_indices = valid.index[::horizon]
        sampled = valid.loc[valid.index.intersection(sample_indices)].copy()

        cum_equity = pd.DataFrame(index=sampled.index)
        for q in [f"Q{i+1}" for i in range(n_quantiles)]:
            q_ret = sampled[sampled["quantile"] == q]["ret"]
            # 重新对齐到全时段填充 0
            q_ret_aligned = q_ret.reindex(sampled.index).fillna(0.0)
            cum_equity[q] = (1.0 + q_ret_aligned).cumprod().round(4)

        if "Q5" in cum_equity.columns and "Q1" in cum_equity.columns:
            cum_equity["Long_Short_Q5_Q1"] = (cum_equity["Q5"] / cum_equity["Q1"]).round(4)

        return cum_equity

    def evaluate_state_transitions(
        self,
        states_df: pd.DataFrame,
        state_col: str = "market_structure"
    ) -> Tuple[pd.DataFrame, Dict[str, float]]:
        """
        计算离散状态的一阶马尔可夫转移概率矩阵 P(S_{t+1} | S_t)
        以及各状态的平均持续交易日数 (Persistence)
        """
        s = states_df[state_col].dropna()
        curr_state = s.iloc[:-1].values
        next_state = s.iloc[1:].values

        cross_tab = pd.crosstab(
            pd.Series(curr_state, name="Current_State"),
            pd.Series(next_state, name="Next_State"),
            normalize="index"
        ).round(4)

        # 统计平均持续周期
        durations: Dict[str, List[int]] = {}
        cur = s.iloc[0]
        cur_len = 1
        for val in s.iloc[1:]:
            if val == cur:
                cur_len += 1
            else:
                durations.setdefault(cur, []).append(cur_len)
                cur = val
                cur_len = 1
        durations.setdefault(cur, []).append(cur_len)

        mean_durations = {k: round(float(np.mean(v)), 1) for k, v in durations.items()}

        return cross_tab, mean_durations

    def evaluate_state_mae_mfe(
        self,
        features_df: pd.DataFrame,
        states_df: pd.DataFrame,
        state_col: str = "fundamental_direction",
        horizon: int = 10
    ) -> pd.DataFrame:
        """
        评估各状态下的前瞻最大有利波动 (MFE) 与最大不利波动 (MAE)
        MFE = Max(High_{t+1:t+H} / Close_t - 1)
        MAE = Min(Low_{t+1:t+H} / Close_t - 1)
        """
        close = features_df["rb_close"]
        high = features_df.get("rb_high", close)
        low = features_df.get("rb_low", close)

        # 计算滚动未来 H 日最高与最低
        fwd_high_max = high.iloc[::-1].rolling(horizon).max().iloc[::-1].shift(-horizon)
        fwd_low_min = low.iloc[::-1].rolling(horizon).min().iloc[::-1].shift(-horizon)

        mfe = (fwd_high_max - close) / close
        mae = (fwd_low_min - close) / close

        df_risk = pd.DataFrame({
            "state": states_df[state_col],
            "mfe": mfe,
            "mae": mae
        }).dropna()

        records = []
        for state_val, grp in df_risk.groupby("state"):
            records.append({
                "state_dimension": state_col,
                "state_value": str(state_val),
                "sample_count": len(grp),
                f"avg_mfe_{horizon}d_pct": round(grp["mfe"].mean() * 100, 2),
                f"avg_mae_{horizon}d_pct": round(grp["mae"].mean() * 100, 2),
                "mfe_mae_ratio": round(abs(grp["mfe"].mean() / grp["mae"].mean()), 2) if grp["mae"].mean() != 0 else np.nan,
                f"mfe_75pct_{horizon}d": round(grp["mfe"].quantile(0.75) * 100, 2),
                f"mae_25pct_{horizon}d": round(grp["mae"].quantile(0.25) * 100, 2)
            })

        return pd.DataFrame(records)

