#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_d/mfe_mae_profile.py
功能: 阶段 D 最大有利波动 (MFE) 与最大不利波动 (MAE) 风险曲面引擎
职责:
  严格遵循《实施手册》第 19 节与 A05/A05.3 规范:
  1. 计算前瞻窗口 h (5, 10, 20, 40d) 内的真实极值路径 (基于 High/Low/Close 真实日线);
  2. 多头与空头双向 MFE / MAE 解构与不对称弹性比 (Elasticity Ratio = E[MFE] / E[|MAE|]);
  3. 极值时序偏序 (MAE First vs MFE First): 检验先套牢后反弹与直接爆发的概率分布;
  4. 止损耐受度曲面 (Stop-Loss Tolerance Surface): 模拟 1%~5% 阶梯止损下的“震仓洗出率”与“有效减亏率”;
  5. 形式化导出各状态维度的极端风险轮廓表。
"""

from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np


class MfeMaeProfileEngine:
    """
    MFE / MAE 极端路径与风险轮廓研究引擎
    """

    DEFAULT_HORIZONS = [5, 10, 20, 40]
    DEFAULT_STOP_LEVELS = [0.01, 0.015, 0.02, 0.025, 0.03, 0.04, 0.05]

    def __init__(
        self,
        features_df: pd.DataFrame,
        state_matrix: pd.DataFrame,
        horizons: Optional[List[int]] = None,
    ):
        self.features_df = features_df.copy()
        self.state_matrix = state_matrix.copy()
        self.horizons = horizons or self.DEFAULT_HORIZONS

        assert (self.features_df.index == self.state_matrix.index).all(), "特征宽表与状态矩阵时序索引必须对齐"

        # 检查价格数据
        for col in ["rb_close", "rb_high", "rb_low"]:
            if col not in self.features_df.columns:
                raise ValueError(f"宽表中缺少必要的螺纹日线价格列: {col}")

        # 预计算全时段 MFE 与 MAE 向量矩阵
        self._precompute_excursions()

    def _precompute_excursions(self):
        """
        基于前瞻窗口的高低价计算多空 MFE / MAE
        注意: 严格按 t+1 至 t+h 的最高价与最低价，无当下 t 信息泄露
        """
        high = self.features_df["rb_high"]
        low = self.features_df["rb_low"]
        close = self.features_df["rb_close"]
        n = len(close)

        for h in self.horizons:
            # 滚动前瞻高点与低点 (shift(-h) 窗口内的 max/min)
            # 采用反向滚动窗口构建
            fwd_high_max = high.iloc[::-1].rolling(window=h, min_periods=h).max().iloc[::-1].shift(-1)
            fwd_low_min = low.iloc[::-1].rolling(window=h, min_periods=h).min().iloc[::-1].shift(-1)
            fwd_close = close.shift(-h)

            # 多头视角
            mfe_long = (fwd_high_max - close) / close
            mae_long = (fwd_low_min - close) / close
            # 空头视角
            mfe_short = (close - fwd_low_min) / close
            mae_short = (close - fwd_high_max) / close

            # 约束: MFE 理论 >= 0, MAE 理论 <= 0
            self.state_matrix[f"mfe_long_{h}d"] = mfe_long.clip(lower=0.0)
            self.state_matrix[f"mae_long_{h}d"] = mae_long.clip(upper=0.0)
            self.state_matrix[f"mfe_short_{h}d"] = mfe_short.clip(lower=0.0)
            self.state_matrix[f"mae_short_{h}d"] = mae_short.clip(upper=0.0)
            self.state_matrix[f"ret_{h}d"] = (fwd_close - close) / close

    def evaluate_state_mfe_mae(
        self,
        dimension_col: str,
        horizon: int = 20,
        direction: str = "long",
    ) -> pd.DataFrame:
        """
        计算特定状态维度在指定窗口的 MFE / MAE 轮廓
        """
        df = self.state_matrix
        mfe_col = f"mfe_{direction}_{horizon}d"
        mae_col = f"mae_{direction}_{horizon}d"
        ret_col = f"ret_{horizon}d"

        records = []
        for s_val in sorted(df[dimension_col].dropna().unique()):
            mask = (df[dimension_col] == s_val) & df[mfe_col].notna() & df[mae_col].notna()
            grp_mfe = df.loc[mask, mfe_col]
            grp_mae = df.loc[mask, mae_col]
            grp_ret = df.loc[mask, ret_col]
            n = len(grp_mfe)

            if n < 5:
                continue

            mean_mfe = float(grp_mfe.mean()) * 100.0
            mean_mae = float(grp_mae.mean()) * 100.0
            median_mfe = float(grp_mfe.median()) * 100.0
            median_mae = float(grp_mae.median()) * 100.0
            abs_mean_mae = abs(mean_mae) if abs(mean_mae) > 1e-4 else 1e-4
            elasticity = mean_mfe / abs_mean_mae

            # 达到 MFE >= 3% 与 5% 的比例
            reach_3pct = (grp_mfe >= 0.03).mean() * 100.0
            reach_5pct = (grp_mfe >= 0.05).mean() * 100.0
            # 跌破 MAE <= -2% 与 -3% 的比例
            drop_2pct = (grp_mae <= -0.02).mean() * 100.0
            drop_3pct = (grp_mae <= -0.03).mean() * 100.0

            records.append({
                "dimension": dimension_col,
                "state_value": str(s_val),
                "direction": direction.upper(),
                "horizon_days": horizon,
                "sample_count": n,
                "mean_mfe_pct": round(mean_mfe, 2),
                "mean_mae_pct": round(mean_mae, 2),
                "median_mfe_pct": round(median_mfe, 2),
                "median_mae_pct": round(median_mae, 2),
                "elasticity_ratio": round(elasticity, 2),
                "reach_3pct_mfe_rate": round(reach_3pct, 1),
                "reach_5pct_mfe_rate": round(reach_5pct, 1),
                "drop_2pct_mae_rate": round(drop_2pct, 1),
                "drop_3pct_mae_rate": round(drop_3pct, 1),
            })

        return pd.DataFrame(records)

    def analyze_stop_loss_surface(
        self,
        dimension_col: str,
        state_value: str,
        horizon: int = 20,
        direction: str = "long",
        stop_levels: Optional[List[float]] = None,
    ) -> pd.DataFrame:
        """
        止损耐受度曲面分析:
        评估不同止损阈值下的震仓洗出率 (Shakeout Rate) 与实际保全效应
        """
        stops = stop_levels or self.DEFAULT_STOP_LEVELS
        df = self.state_matrix
        mfe_col = f"mfe_{direction}_{horizon}d"
        mae_col = f"mae_{direction}_{horizon}d"
        ret_col = f"ret_{horizon}d"

        mask = (df[dimension_col] == str(state_value)) & df[mfe_col].notna() & df[mae_col].notna()
        sub_df = df.loc[mask]
        n = len(sub_df)
        if n < 5:
            return pd.DataFrame()

        mfe = sub_df[mfe_col].values
        mae = sub_df[mae_col].values  # <= 0
        raw_ret = sub_df[ret_col].values if direction == "long" else -sub_df[ret_col].values

        is_raw_win = (raw_ret > 0)
        is_raw_loss = (raw_ret <= 0)

        records = []
        for s_lvl in stops:
            # 触发止损的样本: |mae| >= s_lvl  (即 mae <= -s_lvl)
            is_stopped = (mae <= -s_lvl)
            stop_count = np.sum(is_stopped)
            stop_rate = stop_count / n * 100.0

            # 震仓洗出率: 本来是盈利交易，但中途被止损洗出
            shakeout_count = np.sum(is_stopped & is_raw_win)
            total_wins = np.sum(is_raw_win)
            shakeout_rate = (shakeout_count / total_wins * 100.0) if total_wins > 0 else 0.0

            # 有效防守率: 本来是亏损交易，被成功止损保护
            protected_count = np.sum(is_stopped & is_raw_loss)
            total_losses = np.sum(is_raw_loss)
            protection_rate = (protected_count / total_losses * 100.0) if total_losses > 0 else 0.0

            # 止损后的策略收益率模拟 (被止损的按 -s_lvl 计，未被止损的保留 raw_ret)
            stopped_returns = np.where(is_stopped, -s_lvl, raw_ret)
            sim_mean_ret = float(stopped_returns.mean()) * 100.0
            sim_std_ret = float(stopped_returns.std(ddof=1)) * 100.0 if n > 1 else 1.0
            sim_win_rate = float(np.mean(stopped_returns > 0)) * 100.0
            ann_factor = 250.0 / horizon
            sim_sharpe = (sim_mean_ret / sim_std_ret) * np.sqrt(ann_factor) if sim_std_ret > 0 else 0.0

            records.append({
                "dimension": dimension_col,
                "state_value": str(state_value),
                "horizon_days": horizon,
                "stop_threshold_pct": round(s_lvl * 100.0, 1),
                "stop_triggered_pct": round(stop_rate, 2),
                "shakeout_rate_pct": round(shakeout_rate, 2),
                "protection_rate_pct": round(protection_rate, 2),
                "simulated_mean_ret_pct": round(sim_mean_ret, 2),
                "simulated_win_rate_pct": round(sim_win_rate, 2),
                "simulated_sharpe": round(sim_sharpe, 2),
            })

        return pd.DataFrame(records)

    def evaluate_all_core_mfe_mae(self, horizon: int = 20) -> pd.DataFrame:
        """
        全景评估核心维度的多空 MFE / MAE 轮廓与弹性比
        """
        core_dims = [
            ("fundamental_direction", "long"),
            ("fundamental_direction", "short"),
            ("cost_boundary_regime", "long"),
            ("market_structure", "long"),
            ("market_structure", "short"),
            ("model_confidence", "long"),
            ("divergence_severity", "long"),
            ("sentiment_state", "long"),
        ]

        dfs = []
        for dim, direction in core_dims:
            if dim in self.state_matrix.columns:
                sub_df = self.evaluate_state_mfe_mae(dim, horizon=horizon, direction=direction)
                dfs.append(sub_df)

        return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()
