#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_b/cross_commodity_shock.py
功能: 黑色五大品种 (RB, HC, I, J, JM) 跨品种极端异动、领头羊排位与成本推升剪刀差检测引擎
设计标准: 依据阶段 A《A05.2 黑色五品种期货资金投机度与量化对比规范》

核心检测能力:
  1. 异动源头捕获:
     - 5日短期已实现波动率 / 60日基准波动率比值 (vol_shock_ratio)
     - 持仓异动与逼仓挤仓压力指数 (squeeze_index: 结合动量、波动率与持仓异常扩张)
  2. 截面领头羊识别 (Cross-Sectional Dominance):
     - 每日识别板块带头大哥 (dominant_leader_sym: RB, HC, I, J, JM)
     - 领头羊属性分级 (RAW_MATERIAL_SHOCK vs FINISHED_STEEL_DEMAND vs BALANCED_ROTATION)
  3. 跨品种溢出与成本推升剪刀差:
     - 螺纹与原料 (JM, J, I) 的 10 日动态滚动相关性 (rolling correlation)
     - 成本推升剪刀差 (cost_push_spread_5d = ret_raw - ret_steel)
     - 识别“输入型成本推升 / 假繁荣”与“内生需求驱动”
"""

from typing import Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


class CrossCommodityShockDetector:
    """
    跨品种极端异动与领头羊检测器
    """

    def __init__(self):
        self.symbols = ["rb", "hc", "i", "j", "jm"]

    def compute_volatility_shock(
        self, series: pd.Series, short_window: int = 5, long_window: int = 60
    ) -> pd.Series:
        """
        计算短期已实现波动率与长期基准波动率之比
        """
        ret = series.pct_change()
        vol_short = ret.rolling(short_window, min_periods=3).std() * np.sqrt(250)
        vol_long = ret.rolling(long_window, min_periods=15).std() * np.sqrt(250)
        vol_long_safe = vol_long.replace(0.0, np.nan)
        ratio = vol_short / vol_long_safe
        return ratio.fillna(1.0).clip(0.1, 8.0).round(4)

    def compute_squeeze_index(
        self,
        price_series: pd.Series,
        oi_series: pd.Series,
        ret_window: int = 5,
        oi_ma_window: int = 20,
    ) -> pd.Series:
        """
        计算持仓逆势扩张与逼仓压力指数
        逼仓特征: 价格显著上涨 (相对历史标准差) + 持仓逆势激增 (空头被套不退，多头逼仓)
        """
        ret = price_series.pct_change(ret_window).fillna(0.0)
        oi_ma = oi_series.rolling(oi_ma_window, min_periods=5).mean().replace(0.0, np.nan)
        oi_expansion = (oi_series / oi_ma).fillna(1.0)

        daily_std_60 = price_series.pct_change().rolling(60, min_periods=15).std()
        std_window = (daily_std_60 * np.sqrt(ret_window)).replace(0.0, np.nan).fillna(0.02)

        # 归一化收益异动 Z-Score
        z_ret = ret / std_window
        squeeze = z_ret * oi_expansion
        return squeeze.clip(-6.0, 6.0).round(4)

    def compute_all_shock_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        基于 PIT 宽表计算全套跨品种异动与领头羊特征矩阵
        """
        res = pd.DataFrame(index=df.index)

        # 1. 各品种 5 日收益率、波动率异动比与逼仓指数
        rets_5d = {}
        shock_ratios = {}
        squeeze_indices = {}

        for sym in self.symbols:
            c_col = f"{sym}_close"
            oi_col = f"{sym}_oi"
            if c_col in df.columns:
                p_s = df[c_col]
                rets_5d[sym] = p_s.pct_change(5).fillna(0.0)
                shock_ratios[sym] = self.compute_volatility_shock(p_s)
                res[f"{sym}_vol_shock_ratio"] = shock_ratios[sym]

                if oi_col in df.columns:
                    squeeze_indices[sym] = self.compute_squeeze_index(p_s, df[oi_col])
                    res[f"{sym}_squeeze_index"] = squeeze_indices[sym]
                else:
                    squeeze_indices[sym] = pd.Series(0.0, index=df.index)
                    res[f"{sym}_squeeze_index"] = 0.0

        # 2. 螺纹与各联动品种的 10 日滚动相关性
        if "rb_close" in df.columns:
            rb_ret = df["rb_close"].pct_change()
            for raw_sym in ["jm", "j", "i", "hc"]:
                raw_c = f"{raw_sym}_close"
                if raw_c in df.columns:
                    raw_ret = df[raw_c].pct_change()
                    corr = rb_ret.rolling(10, min_periods=5).corr(raw_ret).fillna(0.5).clip(-1.0, 1.0)
                    res[f"rb_{raw_sym}_rolling_corr_10d"] = corr.round(4)

        # 3. 成本推升剪刀差 (原料加权涨幅 - 成材加权涨幅)
        ret_raw_5d = (
            0.50 * rets_5d.get("i", 0.0) +
            0.30 * rets_5d.get("j", 0.0) +
            0.20 * rets_5d.get("jm", 0.0)
        )
        ret_steel_5d = (
            0.60 * rets_5d.get("rb", 0.0) +
            0.40 * rets_5d.get("hc", 0.0)
        )
        res["cost_push_spread_5d"] = (ret_raw_5d - ret_steel_5d).round(4)

        # 4. 每日截面领头羊识别与分类
        n = len(df)
        leaders = []
        leader_types = []
        is_raw_squeeze_flags = []

        for t in range(n):
            scores = {}
            for sym in self.symbols:
                r5 = rets_5d[sym].iloc[t] if sym in rets_5d else 0.0
                vs = shock_ratios[sym].iloc[t] if sym in shock_ratios else 1.0
                sq = squeeze_indices[sym].iloc[t] if sym in squeeze_indices else 0.0
                # 综合冲击强度 = 动量(40%) + 波动率爆发(30%) + 逼仓压力(30%)
                comp_score = 0.40 * r5 * 10.0 + 0.30 * (vs - 1.0) + 0.30 * sq
                scores[sym.upper()] = comp_score

            best_sym = max(scores, key=scores.get)
            best_score = scores[best_sym]
            leaders.append(best_sym)

            # 判定领头羊属性
            if best_score > 1.2:
                if best_sym in ["JM", "J", "I"]:
                    l_type = "RAW_MATERIAL_SHOCK"
                else:
                    l_type = "FINISHED_STEEL_DEMAND"
            elif best_score < -1.2:
                if best_sym in ["JM", "J", "I"]:
                    l_type = "RAW_MATERIAL_DRAG"
                else:
                    l_type = "FINISHED_STEEL_WEAK"
            else:
                l_type = "BALANCED_ROTATION"
            leader_types.append(l_type)

            # 逼仓触发条件: 焦煤/焦炭/铁矿逼仓指数 > 2.0 且 成本剪刀差 > 0.02
            cp_spread = res["cost_push_spread_5d"].iloc[t]
            jm_sq = squeeze_indices["jm"].iloc[t] if "jm" in squeeze_indices else 0.0
            j_sq = squeeze_indices["j"].iloc[t] if "j" in squeeze_indices else 0.0
            i_sq = squeeze_indices["i"].iloc[t] if "i" in squeeze_indices else 0.0

            is_squeeze = (jm_sq > 2.0 or j_sq > 2.0 or i_sq > 2.0) and (cp_spread > 0.02)
            is_raw_squeeze_flags.append(is_squeeze)

        res["dominant_leader_sym"] = leaders
        res["dominant_leader_type"] = leader_types
        res["is_raw_material_squeeze"] = is_raw_squeeze_flags

        return res
