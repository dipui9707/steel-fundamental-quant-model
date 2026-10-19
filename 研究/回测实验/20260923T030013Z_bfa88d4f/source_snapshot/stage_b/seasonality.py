#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_b/seasonality.py
功能: 钢材产业双日历季节性对齐与严格无未来函数 (PIT) 季节性特征引擎
规范依照: 阶段 A《A05.1 模型量化输出与指标设计规范》第 7 节“季节性标准化”

核心设计:
  1. 双日历对齐机制:
     - 春节农历轴 (Lunar CNY Axis): 针对冬春季 (除夕前 6 周至除夕后 16 周, w in [-6, 16]),
       按农历除夕相对周 (cny_relative_week) 对齐历史同期;
     - 公历自然周 (Calendar ISO Week): 针对夏秋季 (梅雨高温、金九银十、采暖限产),
       按公历自然周 (1~52 周) 对齐历史同期。
  2. 严格点时 (PIT) 因果性:
     - 比较池 H 仅包含当前观测所属年份之前的历史同期数据 (Y_hist < Y_cur);
     - 当前年份及未来的数据绝不进入当期比较池 (杜绝未来函数);
     - 历史同期样本数不足 (n < min_years) 时安全回退至中性默认值。
  3. 核心输出指标:
     - Seasonal Z-Score: (x - μ_season) / σ_season, 截断至 [-3.0, 3.0];
     - Seasonal Rank: 历史同期经验分位, 严格处于 [0.0, 1.0]。
"""

from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


# 2017 - 2027 年农历除夕 (即大年三十或廿九，初一前一天) 基准锚点
CNY_EVE_MAP: Dict[int, pd.Timestamp] = {
    2017: pd.Timestamp("2017-01-27"),
    2018: pd.Timestamp("2018-02-15"),
    2019: pd.Timestamp("2019-02-04"),
    2020: pd.Timestamp("2020-01-24"),
    2021: pd.Timestamp("2021-02-11"),
    2022: pd.Timestamp("2022-01-31"),
    2023: pd.Timestamp("2023-01-21"),
    2024: pd.Timestamp("2024-02-09"),
    2025: pd.Timestamp("2025-01-28"),
    2026: pd.Timestamp("2026-02-16"),
    2027: pd.Timestamp("2027-02-05"),
}


def get_seasonal_tags(dt: Union[pd.Timestamp, datetime, str]) -> Tuple[int, int, str, bool]:
    """
    为指定日期计算双日历季节性标签

    返回:
      (cny_relative_week, calendar_week, season_code, is_cny_window)
    """
    ts = pd.Timestamp(dt)
    year = ts.year

    # 农历除夕基准
    cny_eve = CNY_EVE_MAP.get(year)
    if cny_eve is None:
        # 兜底推算
        cny_eve = pd.Timestamp(f"{year}-02-01")

    diff_days = (ts - cny_eve).days
    cny_rel_week = int(np.floor(diff_days / 7.0))
    cal_week = int(ts.isocalendar().week)

    # 规范 A05.1: 春节事件窗 [-6, +16] 周
    if -6 <= cny_rel_week <= 16:
        season_code = f"CNY_{cny_rel_week}"
        is_cny_window = True
    else:
        season_code = f"CAL_{cal_week}"
        is_cny_window = False

    return cny_rel_week, cal_week, season_code, is_cny_window


def compute_pit_seasonal_metrics(
    df: pd.DataFrame,
    col_name: str,
    min_years: int = 2,
    clip_z: float = 3.0,
    reference_history: Optional[pd.DataFrame] = None,
) -> Tuple[pd.Series, pd.Series]:
    """
    为时间序列按双日历季节对齐，严格基于 PIT 计算超季节性偏离度与历史同期百分位。

    参数:
      df: 输入数据框，索引必须为 DatetimeIndex 或可转换为日期的索引
      col_name: 待计算季节性的列名
      min_years: 历史同季节所需最小历年样本数 (默认 2 年)
      clip_z: Z-score 截断极值 (默认 [-3.0, 3.0])
      reference_history: 可选的全量历史特征宽表，用于在处理局部时间切片时补充前期年份基准

    返回:
      (seasonal_zscore, seasonal_rank): 两个与 df.index 严格对齐的 pd.Series
    """
    dates = pd.to_datetime(df.index)
    n = len(df)
    if n == 0 or col_name not in df.columns:
        empty_s = pd.Series(index=df.index, dtype=float)
        return empty_s, empty_s

    vals = df[col_name].values
    years = dates.year.values

    # 生成季节编码
    season_codes = []
    for d in dates:
        _, _, code, _ = get_seasonal_tags(d)
        season_codes.append(code)
    season_codes = np.array(season_codes)

    # 构建历史字典: season_code -> list of past values
    history_by_code = defaultdict(list)

    # 若传入了参考全量历史，且当前首年之前有可用年份，先装填参考历史
    if reference_history is not None and col_name in reference_history.columns:
        ref_dates = pd.to_datetime(reference_history.index)
        ref_years = ref_dates.year.values
        ref_vals = reference_history[col_name].values
        start_year = years[0]

        for j in range(len(reference_history)):
            r_y = ref_years[j]
            if r_y < start_year:
                _, _, r_code, _ = get_seasonal_tags(ref_dates[j])
                v = ref_vals[j]
                if not np.isnan(v):
                    history_by_code[r_code].append(v)

    z_scores = np.zeros(n, dtype=float)
    ranks = np.full(n, 0.5, dtype=float)

    curr_year = years[0]
    temp_year_cache = defaultdict(list)

    for i in range(n):
        y = years[i]
        code = season_codes[i]
        v = vals[i]

        # 跨年时，将上一年暂存数据安全移入历史基准池
        if y > curr_year:
            for k, v_list in temp_year_cache.items():
                history_by_code[k].extend(v_list)
            temp_year_cache.clear()
            curr_year = y

        # 暂存当前年份的有效值 (严格当前年份内部不自测)
        if not np.isnan(v):
            temp_year_cache[code].append(v)

        # 提取历史池 (严格 Y_hist < y)
        hist = history_by_code.get(code, [])
        if len(hist) >= min_years and not np.isnan(v):
            arr = np.array(hist)
            m = float(np.mean(arr))
            s = float(np.std(arr, ddof=1))
            if s > 1e-6:
                z = (v - m) / s
                z_scores[i] = float(np.clip(z, -clip_z, clip_z))
            else:
                z_scores[i] = 0.0

            # 经验百分位 Rank in [0, 1]
            rank = (arr < v).mean() + 0.5 * (arr == v).mean()
            ranks[i] = float(rank)
        else:
            z_scores[i] = 0.0
            ranks[i] = 0.5

    s_z = pd.Series(z_scores, index=df.index, name=f"{col_name}_seasonal_zscore")
    s_rk = pd.Series(ranks, index=df.index, name=f"{col_name}_seasonal_rank")
    return s_z, s_rk
