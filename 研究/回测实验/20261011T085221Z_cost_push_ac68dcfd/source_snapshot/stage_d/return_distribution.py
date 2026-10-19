#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_d/return_distribution.py
功能: 阶段 D 条件收益分布研究引擎 (Conditional Return Distribution Engine)
职责:
  严格遵循《实施手册》第 19 节与 A05/A05.3 规范:
  1. 系统化解构 P(Return_{t+h} | State) 在不同时间跨度 (h = 1, 3, 5, 10, 15, 20, 40, 60 天) 的分布;
  2. 提供完整的分布形态统计量: 均值、中位数、标准差、IQR、偏度 (Skewness)、峰度 (Kurtosis)、10/25/50/75/90分位数;
  3. 计算胜率 (Win Rate)、盈亏比 (Profit/Loss Ratio) 与年化夏普/收益比;
  4. 支持单一状态维度与多维复合策略状态 (Composite Regimes) 的切片实证;
  5. 扩展成材 (RB/HC) 与原料 (I/J) 跨品种响应对比。
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class ReturnDistributionEngine:
    """
    条件前瞻收益分布研究引擎
    """

    DEFAULT_HORIZONS = [1, 3, 5, 10, 15, 20, 40, 60]

    def __init__(
        self,
        features_df: pd.DataFrame,
        state_matrix: pd.DataFrame,
        horizons: Optional[List[int]] = None,
    ):
        self.features_df = features_df.copy()
        self.state_matrix = state_matrix.copy()
        self.horizons = horizons or self.DEFAULT_HORIZONS

        # 确保时序索引对齐
        assert (self.features_df.index == self.state_matrix.index).all(), "特征宽表与状态矩阵时序索引必须完全一致"

        # 预计算前瞻收益
        self._calculate_forward_returns()

    def _calculate_forward_returns(self):
        """计算各个窗口的前瞻收益 (无未来信息回填特征，仅用于评估标签)"""
        # 主标的螺纹钢
        close_rb = self.features_df["rb_close"]
        for h in self.horizons:
            self.state_matrix[f"fwd_ret_rb_{h}d"] = close_rb.shift(-h) / close_rb - 1.0

        # 热卷与铁矿石 (用于跨品种响应对比)
        if "hc_close" in self.features_df.columns:
            close_hc = self.features_df["hc_close"]
            for h in self.horizons:
                self.state_matrix[f"fwd_ret_hc_{h}d"] = close_hc.shift(-h) / close_hc - 1.0

        if "i_close" in self.features_df.columns:
            close_i = self.features_df["i_close"]
            for h in self.horizons:
                self.state_matrix[f"fwd_ret_i_{h}d"] = close_i.shift(-h) / close_i - 1.0

    @staticmethod
    def calculate_distribution_stats(returns: pd.Series, horizon: int = 20) -> Dict[str, Any]:
        """
        计算单序列收益的完整分布统计量
        """
        clean_ret = returns.dropna()
        n = len(clean_ret)
        if n < 3:
            return {
                "sample_count": n,
                "mean_pct": 0.0,
                "median_pct": 0.0,
                "std_pct": 0.0,
                "iqr_pct": 0.0,
                "skewness": 0.0,
                "kurtosis": 0.0,
                "q10_pct": 0.0,
                "q25_pct": 0.0,
                "q75_pct": 0.0,
                "q90_pct": 0.0,
                "win_rate_pct": 0.0,
                "profit_loss_ratio": 0.0,
                "ann_return_pct": 0.0,
                "sharpe_ratio": 0.0,
            }

        mean_val = float(clean_ret.mean())
        median_val = float(clean_ret.median())
        std_val = float(clean_ret.std(ddof=1)) if n > 1 else 0.0

        q10 = float(clean_ret.quantile(0.10))
        q25 = float(clean_ret.quantile(0.25))
        q75 = float(clean_ret.quantile(0.75))
        q90 = float(clean_ret.quantile(0.90))
        iqr = q75 - q25

        # 偏度与峰度
        if n >= 3 and std_val > 1e-8:
            diffs = clean_ret - mean_val
            m3 = float((diffs ** 3).mean())
            m4 = float((diffs ** 4).mean())
            skew = m3 / (std_val ** 3)
            kurt = (m4 / (std_val ** 4)) - 3.0  # 超额峰度
        else:
            skew = 0.0
            kurt = 0.0

        # 胜率与盈亏比
        wins = clean_ret[clean_ret > 0]
        losses = clean_ret[clean_ret < 0]
        win_rate = len(wins) / n * 100.0

        avg_win = float(wins.mean()) if len(wins) > 0 else 0.0
        avg_loss = abs(float(losses.mean())) if len(losses) > 0 else 1e-6
        pl_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

        # 年化指标
        ann_factor = 250.0 / horizon
        ann_ret = mean_val * ann_factor * 100.0
        sharpe = (mean_val / (std_val + 1e-8)) * np.sqrt(ann_factor) if std_val > 0 else 0.0

        return {
            "sample_count": n,
            "mean_pct": round(mean_val * 100.0, 2),
            "median_pct": round(median_val * 100.0, 2),
            "std_pct": round(std_val * 100.0, 2),
            "iqr_pct": round(iqr * 100.0, 2),
            "skewness": round(skew, 3),
            "kurtosis": round(kurt, 3),
            "q10_pct": round(q10 * 100.0, 2),
            "q25_pct": round(q25 * 100.0, 2),
            "q75_pct": round(q75 * 100.0, 2),
            "q90_pct": round(q90 * 100.0, 2),
            "win_rate_pct": round(win_rate, 2),
            "profit_loss_ratio": round(pl_ratio, 2),
            "ann_return_pct": round(ann_ret, 2),
            "sharpe_ratio": round(sharpe, 2),
        }

    def evaluate_single_dimension(
        self,
        dimension_col: str,
        target_symbol: str = "rb",
        horizons: Optional[List[int]] = None,
    ) -> pd.DataFrame:
        """
        评估单一状态维度在各时间尺度下的条件收益分布
        """
        eval_horizons = horizons or self.horizons
        records = []
        df = self.state_matrix

        if dimension_col not in df.columns:
            raise ValueError(f"状态矩阵中未找到维度列: {dimension_col}")

        # 遍历该维度的所有非空离散状态取值
        state_values = df[dimension_col].dropna().unique()

        for s_val in sorted(state_values):
            mask = df[dimension_col] == s_val
            grp_len = mask.sum()
            if grp_len < 5:
                continue

            for h in eval_horizons:
                ret_col = f"fwd_ret_{target_symbol}_{h}d"
                if ret_col not in df.columns:
                    continue

                rets = df.loc[mask, ret_col]
                stats = self.calculate_distribution_stats(rets, horizon=h)

                rec = {
                    "dimension": dimension_col,
                    "state_value": str(s_val),
                    "target_symbol": target_symbol.upper(),
                    "horizon_days": h,
                    "sample_share_pct": round(grp_len / len(df) * 100.0, 2),
                    **stats,
                }
                records.append(rec)

        return pd.DataFrame(records)

    def evaluate_all_core_dimensions(
        self,
        target_symbol: str = "rb",
        horizon: int = 20,
    ) -> pd.DataFrame:
        """
        评估所有核心维度的条件收益分布 (统一指定窗口，如 20d)
        """
        core_dims = [
            "fundamental_direction",
            "cost_boundary_regime",
            "raw_feedback_regime",
            "spot_confirmation",
            "basis_regime",
            "sentiment_state",
            "crowding_risk",
            "market_structure",
            "divergence_severity",
            "model_confidence",
            "macro_regime",
        ]

        dfs = []
        for dim in core_dims:
            if dim in self.state_matrix.columns:
                sub_df = self.evaluate_single_dimension(dim, target_symbol=target_symbol, horizons=[horizon])
                dfs.append(sub_df)

        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()

    def evaluate_composite_regimes(
        self,
        horizons: Optional[List[int]] = None,
    ) -> pd.DataFrame:
        """
        评估高阶复合策略状态 (Composite Regimes) 的收益分布
        """
        eval_horizons = horizons or self.horizons
        df = self.state_matrix.copy()

        # 定义典型复合状态
        regimes = {
            "Alpha Bull (多头+高信任+现货确认)": (
                (df["fundamental_direction"] == "Bullish") &
                (df["model_confidence"] == "High") &
                (df["spot_confirmation"] == "Confirmed")
            ),
            "Alpha Bear (空头+高信任+现货确认)": (
                (df["fundamental_direction"] == "Bearish") &
                (df["model_confidence"] == "High") &
                (df["spot_confirmation"] == "Confirmed")
            ),
            "Cost Floor Rebound (深度亏损成本下轨支撑)": (
                df["cost_boundary_regime"] == "Deep Cost Support"
            ),
            "High Margin Expansion Risk (高利润承压)": (
                df["cost_boundary_regime"] == "High Margin Resistance"
            ),
            "Severe Divergence (同尺度严重产业-价格背离)": (
                df["divergence_severity"] == "Severe"
            ),
            "Negative Feedback Crash (原料负反馈踩踏)": (
                df["raw_feedback_regime"] == "Negative Feedback Crash"
            ),
            "Macro Override Window (宏观外生冲击覆盖期)": (
                (df["macro_regime"] == "Macro Override") | (df["external_shock_flag"] == True)
            ),
            "Crowded Climax Risk (筹码极端拥挤见顶/见底风险)": (
                (df["crowding_risk"] == "Extreme") & (df["sentiment_state"].isin(["Crowded", "Stagnant"]))
            ),
        }

        records = []
        for reg_name, mask in regimes.items():
            grp_len = mask.sum()
            if grp_len < 5:
                continue

            for h in eval_horizons:
                ret_col = f"fwd_ret_rb_{h}d"
                rets = df.loc[mask, ret_col]
                stats = self.calculate_distribution_stats(rets, horizon=h)

                rec = {
                    "regime_name": reg_name,
                    "horizon_days": h,
                    "sample_share_pct": round(grp_len / len(df) * 100.0, 2),
                    **stats,
                }
                records.append(rec)

        return pd.DataFrame(records)

    def evaluate_cross_commodity_response(self, horizon: int = 20) -> pd.DataFrame:
        """
        跨品种响应比较: 检验在螺纹钢核心状态下，热卷 (HC) 与铁矿石 (I) 的收益分布差异
        """
        symbols = ["rb", "hc", "i"]
        core_dims = ["fundamental_direction", "cost_boundary_regime", "raw_feedback_regime"]

        records = []
        for dim in core_dims:
            for s_val in sorted(self.state_matrix[dim].dropna().unique()):
                mask = self.state_matrix[dim] == s_val
                if mask.sum() < 5:
                    continue

                for sym in symbols:
                    ret_col = f"fwd_ret_{sym}_{horizon}d"
                    if ret_col not in self.state_matrix.columns:
                        continue

                    rets = self.state_matrix.loc[mask, ret_col]
                    stats = self.calculate_distribution_stats(rets, horizon=horizon)

                    rec = {
                        "dimension": dim,
                        "state_value": str(s_val),
                        "symbol": sym.upper(),
                        "horizon_days": horizon,
                        "sample_count": stats["sample_count"],
                        "mean_pct": stats["mean_pct"],
                        "win_rate_pct": stats["win_rate_pct"],
                        "profit_loss_ratio": stats["profit_loss_ratio"],
                        "sharpe_ratio": stats["sharpe_ratio"],
                        "skewness": stats["skewness"],
                    }
                    records.append(rec)

        return pd.DataFrame(records)
