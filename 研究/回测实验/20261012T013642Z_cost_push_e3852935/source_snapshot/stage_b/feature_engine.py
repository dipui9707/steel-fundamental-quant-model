#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_b/feature_engine.py
功能: 阶段 B 量化特征与状态变量计算引擎
职责:
  实现 A05.1、A04、A05.2 数学规范：
  1. 实物供需核心 (FBS): Level, ΔLevel, Δ²Level, 历史分位, S_supply, S_demand, S_inventory;
  2. 动态权重自适应与 D_t / W_t 精确恒等分解;
  3. 供需动量速度 FV^(k) 与加速度 FA^(k);
  4. 估值与成本底线 (长流程BF成本, 现金成本下轨, EAF平/谷电成本, 扣减1200元杂费虚拟毛利IMM);
  5. 现货基差与期限结构 (中天基差, CTD三类交割品基差, 6%利息持有成本与正套净利, 跨期价差);
  6. 资金与微观结构 (成交持仓比 VOI, 五类量价仓微观打标);
  7. 价格背离度量 (无量纲动量差, 连续背离天数, 累计背离面积与Z-score);
  8. 证据熵与模型置信度 (方向证据熵 CDE, 数据新鲜度比率).
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd
import numpy as np

from stage_b.seasonality import get_seasonal_tags, compute_pit_seasonal_metrics
from stage_b.cross_commodity_shock import CrossCommodityShockDetector


class FeatureEngine:
    """
    阶段 B 状态变量与量化特征计算引擎
    """

    def __init__(self):
        # 预设基准固定权重 (Supply, Demand, Inventory)
        self.w0 = np.array([0.35, 0.35, 0.30])
        self.modules = ["supply", "demand", "inventory"]

    def compute_all_features(self, panel_df: pd.DataFrame, rolling_window: int = 252) -> pd.DataFrame:
        """
        对已对齐的 PIT 事实宽表执行全套特征衍生计算
        严格保证时间序列单向向前计算，无未来函数
        """
        df = panel_df.copy()

        # -------------------------------------------------------------
        # 1. 基础差分与加速度计算 (Level, ΔLevel, Δ²Level)
        # -------------------------------------------------------------
        # 247 铁水日均产量
        df["hm_diff1"] = df["hot_metal_247"].diff()
        df["hm_diff2"] = df["hm_diff1"].diff()

        # 螺纹主要钢厂产量
        df["rb_prod_diff1"] = df["rebar_weekly_prod"].diff()
        df["rb_prod_diff2"] = df["rb_prod_diff1"].diff()

        # 螺纹总库存 = 厂库 + 社库
        df["rebar_total_inv"] = df["rebar_soc_inv"] + df["rebar_mill_inv"]
        df["inv_diff1"] = df["rebar_total_inv"].diff()
        df["inv_diff2"] = df["inv_diff1"].diff()

        # 螺纹表观需求
        df["demand_diff1"] = df["rebar_apparent_demand"].diff()

        # -------------------------------------------------------------
        # 2. 多尺度历史分位 (近期1年 + 历年全景 + 双尺度综合，无未来信息)
        # -------------------------------------------------------------
        def compute_dual_percentile(
            s: pd.Series, window: int = 252, min_periods: int = 15, w_1y: float = 0.50
        ) -> Tuple[pd.Series, pd.Series, pd.Series]:
            p_1y = (
                s.rolling(window=window, min_periods=min_periods)
                .rank(pct=True)
                .fillna(0.5)
                .clip(0.0, 1.0)
                .round(4)
            )
            p_hist = (
                s.expanding(min_periods=min_periods)
                .rank(pct=True)
                .fillna(0.5)
                .clip(0.0, 1.0)
                .round(4)
            )
            p_blend = (w_1y * p_1y + (1.0 - w_1y) * p_hist).round(4)
            return p_1y, p_hist, p_blend

        df["inv_pct_1y"], df["inv_pct_hist"], df["inv_pct"] = compute_dual_percentile(
            df["rebar_total_inv"], window=rolling_window, min_periods=15
        )
        df["hm_pct_1y"], df["hm_pct_hist"], df["hm_pct"] = compute_dual_percentile(
            df["hot_metal_247"], window=rolling_window, min_periods=15
        )

        # -------------------------------------------------------------
        # 2.5 双日历季节性对齐与 PIT 季节性特征计算 (A05.1 Section 7)
        # -------------------------------------------------------------
        dates = pd.to_datetime(df.index)
        cny_rel_weeks = []
        cal_weeks = []
        season_codes = []
        is_cny_windows = []
        for d in dates:
            crw, cw, sc, icw = get_seasonal_tags(d)
            cny_rel_weeks.append(crw)
            cal_weeks.append(cw)
            season_codes.append(sc)
            is_cny_windows.append(icw)

        df["cny_relative_week"] = cny_rel_weeks
        df["calendar_week"] = cal_weeks
        df["season_code"] = season_codes
        df["is_cny_window"] = is_cny_windows

        # 检查是否需要参考全量历史 (针对短区间切片测试)
        ref_history = None
        if len(dates) > 0 and (dates.max().year - dates.min().year < 1):
            cache_pq = Path(__file__).resolve().parent.parent / "数据" / "加工" / "阶段B_特征宽表.parquet"
            if cache_pq.exists():
                try:
                    ref_history = pd.read_parquet(cache_pq)
                except Exception:
                    ref_history = None

        # 针对 4 大强季节性核心指标计算 PIT 季节性特征
        for col in ["inv_diff1", "rebar_total_inv", "rebar_apparent_demand", "rebar_weekly_prod", "hot_metal_247"]:
            if col in df.columns:
                s_z, s_rk = compute_pit_seasonal_metrics(df, col, min_years=2, reference_history=ref_history)
                df[f"{col}_seasonal_zscore"] = s_z
                df[f"{col}_seasonal_rank"] = s_rk

        # 核心便捷指标别名对齐
        df["inv_level_seasonal_rank"] = df["rebar_total_inv_seasonal_rank"]
        df["demand_seasonal_zscore"] = df["rebar_apparent_demand_seasonal_zscore"]
        df["demand_seasonal_rank"] = df["rebar_apparent_demand_seasonal_rank"]
        df["rb_prod_seasonal_zscore"] = df["rebar_weekly_prod_seasonal_zscore"]
        df["rb_prod_seasonal_rank"] = df["rebar_weekly_prod_seasonal_rank"]
        df["hm_seasonal_zscore"] = df["hot_metal_247_seasonal_zscore"]
        df["hm_seasonal_rank"] = df["hot_metal_247_seasonal_rank"]

        # -------------------------------------------------------------
        # 3. 供需模块得分 (S_supply, S_demand, S_inventory)
        # 规范: [-1, 1], 高供给为负分, 高需求为正分, 去库为正分
        # -------------------------------------------------------------
        # 滚动标准化工具 (避免未来泄露，使用扩展/前向窗口)
        def rolling_zscore(s: pd.Series, window: int = 250, min_periods: int = 15) -> pd.Series:
            mean = s.shift(1).rolling(window, min_periods=min_periods).mean()
            std = s.shift(1).rolling(window, min_periods=min_periods).std()
            z = (s - mean) / std.replace(0, np.nan)
            return z.fillna(0.0)

        # 供给端: 铁水高、产量高对成材价格不利 (d = -1)
        z_hm_roll = rolling_zscore(df["hot_metal_247"])
        q_hm_roll = np.clip(-z_hm_roll / 2.0, -1.0, 1.0)
        q_hm_season = np.clip(-df["hm_seasonal_zscore"] / 2.0, -1.0, 1.0)
        q_hm = np.where(df["hm_seasonal_zscore"] != 0.0, 0.6 * q_hm_season + 0.4 * q_hm_roll, q_hm_roll)

        z_rb_roll = rolling_zscore(df["rebar_weekly_prod"])
        q_rb_roll = np.clip(-z_rb_roll / 2.0, -1.0, 1.0)
        q_rb_season = np.clip(-df["rb_prod_seasonal_zscore"] / 2.0, -1.0, 1.0)
        q_rb_prod = np.where(df["rb_prod_seasonal_zscore"] != 0.0, 0.6 * q_rb_season + 0.4 * q_rb_roll, q_rb_roll)

        df["score_supply"] = pd.Series(0.6 * q_hm + 0.4 * q_rb_prod, index=df.index).fillna(0.0).round(4)

        # 需求端: 表需超季节性强劲 (demand_seasonal_zscore > 0) 与成交量活跃为正 (d = +1)
        z_app_demand_roll = rolling_zscore(df["rebar_apparent_demand"])
        q_app_roll = np.clip(z_app_demand_roll / 2.0, -1.0, 1.0)
        q_app_season = np.clip(df["demand_seasonal_zscore"] / 2.0, -1.0, 1.0)
        q_app_demand = np.where(df["demand_seasonal_zscore"] != 0.0, 0.7 * q_app_season + 0.3 * q_app_roll, q_app_roll)

        z_deal = rolling_zscore(df["building_deal_volume"])
        q_deal = np.clip(z_deal / 2.0, -1.0, 1.0)
        df["score_demand"] = pd.Series(0.7 * q_app_demand + 0.3 * q_deal, index=df.index).fillna(0.0).round(4)

        # 库存端:
        # 1. 历年同期库存水平高为负 (d = -1)
        q_inv_level_season = np.clip(-(df["inv_level_seasonal_rank"] - 0.5) * 2.0, -1.0, 1.0)
        q_inv_level_exp = np.clip(-(df["inv_pct"] - 0.5) * 2.0, -1.0, 1.0)
        q_inv_level = np.where(df["inv_level_seasonal_rank"] != 0.5, 0.7 * q_inv_level_season + 0.3 * q_inv_level_exp, q_inv_level_exp)

        # 2. 超季节性去库 (inv_diff1_seasonal_zscore < 0) 为利多
        q_inv_slope_season = np.clip(-df["inv_diff1_seasonal_zscore"] / 2.0, -1.0, 1.0)
        z_inv_diff1_roll = rolling_zscore(df["inv_diff1"])
        q_inv_slope_roll = np.clip(-z_inv_diff1_roll / 2.0, -1.0, 1.0)
        q_inv_slope = np.where(df["inv_diff1_seasonal_zscore"] != 0.0, 0.7 * q_inv_slope_season + 0.3 * q_inv_slope_roll, q_inv_slope_roll)

        # 3. 去库加速 (diff2 < 0) 为利多
        z_inv_diff2 = rolling_zscore(df["inv_diff2"])
        q_inv_accel = np.clip(-z_inv_diff2 / 2.0, -1.0, 1.0)

        df["score_inventory"] = pd.Series(0.4 * q_inv_level + 0.4 * q_inv_slope + 0.2 * q_inv_accel, index=df.index).fillna(0.0).round(4)

        # -------------------------------------------------------------
        # 4. FBS 评分、动态权重与精确 D_t / W_t 分解
        # -------------------------------------------------------------
        # 固定基准 FBS_ref
        df["fbs_ref"] = (100.0 * (
            self.w0[0] * df["score_supply"] +
            self.w0[1] * df["score_demand"] +
            self.w0[2] * df["score_inventory"]
        )).round(2)

        # 动态权重自适应 (基于幅度路由算法)
        n = len(df)
        w_dyn = np.zeros((n, 3))
        w_dyn[0] = self.w0
        fbs_dyn = np.zeros(n)
        d_contrib = np.zeros(n)
        w_contrib = np.zeros(n)

        scores = df[["score_supply", "score_demand", "score_inventory"]].fillna(0.0).values

        for t in range(n):
            if t == 0:
                fbs_dyn[0] = np.dot(w_dyn[0], scores[0]) * 100.0
                continue

            # 路由判定 (基于 t-1 得分幅度)
            prev_s = scores[t - 1]
            abs_s = np.abs(prev_s)
            max_idx = np.argmax(abs_s)
            sorted_abs = np.sort(abs_s)

            # 若最大模块显著突出 (|S| > 0.3 且比第二名大 0.1)
            target_w = self.w0.copy()
            if sorted_abs[2] > 0.30 and (sorted_abs[2] - sorted_abs[1]) > 0.10:
                # 给主导模块增加权重 (η = 0.5)
                eta = 0.5
                target_w = self.w0.copy()
                target_w[max_idx] *= (1.0 + eta)
                target_w /= target_w.sum()

            # 平滑过渡 (λ = 0.2)
            lam = 0.20
            w_dyn[t] = (1.0 - lam) * w_dyn[t - 1] + lam * target_w

            # 当期动态 FBS
            fbs_dyn[t] = np.dot(w_dyn[t], scores[t]) * 100.0

            # 精确恒等分解: D_t 与 W_t
            # D_t = 50 * sum (w_t + w_{t-1}) * (S_t - S_{t-1})
            # W_t = 50 * sum (S_t + S_{t-1}) * (w_t - w_{t-1})
            delta_s = scores[t] - scores[t - 1]
            delta_w = w_dyn[t] - w_dyn[t - 1]
            sum_w = w_dyn[t] + w_dyn[t - 1]
            sum_s = scores[t] + scores[t - 1]

            d_contrib[t] = 50.0 * np.dot(sum_w, delta_s)
            w_contrib[t] = 50.0 * np.dot(sum_s, delta_w)

        df["w_supply"] = w_dyn[:, 0].round(4)
        df["w_demand"] = w_dyn[:, 1].round(4)
        df["w_inventory"] = w_dyn[:, 2].round(4)
        df["fbs_score"] = np.clip(fbs_dyn, -100.0, 100.0).round(2)
        df["d_contrib"] = d_contrib.round(4)
        df["w_contrib"] = w_contrib.round(4)

        # 供需动量速度 FV 与加速度 FA (以 5d 和 10d 为主)
        df["fv_5d"] = df["d_contrib"].rolling(5).mean().round(4)
        df["fv_10d"] = df["d_contrib"].rolling(10).mean().round(4)
        df["fa_10d"] = ((df["fv_10d"] - df["fv_10d"].shift(10)) / 10.0).round(4)

        # -------------------------------------------------------------
        # 5. 估值与成本底线层
        # -------------------------------------------------------------
        # 长流程 BF 成本与毛利
        df["cost_bf"] = df["cost_east_bf"]
        df["profit_bf"] = df["profit_east_bf"]

        # 现金成本下轨 (BF成本减去折旧与固定制造开销约250元)
        df["cost_cash_floor"] = df["cost_bf"] - 250.0

        # 估值偏离度比率 CostGap = (RB_close - Cost_bf) / Cost_bf
        df["cost_gap_ratio"] = ((df["rb_close"] - df["cost_bf"]) / df["cost_bf"]).round(4)

        # 盘面虚拟钢厂毛利 IMM = RB - 1.6*I - 0.5*J - 1200
        df["virtual_mill_margin"] = (df["rb_close"] - 1.6 * df["i_close"] - 0.5 * df["j_close"] - 1200.0).round(2)
        df["virtual_margin_zscore"] = rolling_zscore(df["virtual_mill_margin"]).round(4)

        # 热卷盘面虚拟毛利与卷螺利润剪刀差
        df["hc_virtual_margin"] = (df["hc_close"] - 1.6 * df["i_close"] - 0.5 * df["j_close"] - 1200.0).round(2)
        df["spread_hc_rb_profit"] = (df["hc_virtual_margin"] - df["virtual_mill_margin"]).round(2)

        # 铁废差 (华东铁水成本 - 华东废钢)
        hot_metal_cost = df["cost_east_hot_metal"].copy()
        hot_metal_cost = hot_metal_cost.combine_first(df["cost_bf"] - 550.0) # 铁水加工费折让
        scrap_cost = df["scrap_east_6mm"].copy()
        scrap_cost = scrap_cost.combine_first(df["scrap_ts_price"])
        df["iron_scrap_spread"] = (hot_metal_cost - scrap_cost).round(2)

        # 电炉谷电缓冲空间 (三类交割品现货 - 谷电成本)
        eaf_cost = df["cost_east_eaf_valley"].copy()
        eaf_cost = eaf_cost.combine_first(scrap_cost * 1.15 + 400.0) # 废钢折算电炉成本
        df["eaf_valley_buffer"] = (df["spot_hz_tier3"] - eaf_cost).round(2)

        # 螺坯加工价差 (杭州三类螺纹 - 唐山方坯)
        df["billet_rebar_spread"] = (df["spot_hz_tier3"] - df["spot_ts_billet"]).round(2)

        # -------------------------------------------------------------
        # 6. 现货基差与期限结构
        # -------------------------------------------------------------
        # 中天流动性基差与 CTD 三类交割品基差
        df["basis_zhongtian"] = (df["spot_hz_zhongtian"] - df["rb_close"]).round(2)
        df["basis_tier3"] = (df["spot_hz_tier3"] - df["rb_close"]).round(2)

        # 基差率 (以现货为分母)
        df["basis_rate_tier3"] = (df["basis_tier3"] / df["spot_hz_tier3"]).round(4)

        # 年化展期收益率代理 (Roll Yield)
        df["roll_yield_annual"] = ((df["basis_tier3"] / df["rb_close"].replace(0, np.nan)) * (365.0 / 90.0)).round(4)

        # 资金持有成本与无风险正套净利 (按 6% 年化资金成本 + 0.15元/天仓储，设定 90 天标准交割周期)
        holding_days = 90.0
        carry_cost = df["rb_close"] * 0.06 * (holding_days / 365.0) + 0.15 * holding_days
        df["net_cash_carry"] = (df["basis_tier3"] - carry_cost).round(2)

        # 跨品种与比价
        df["spread_hc_rb"] = (df["hc_close"] - df["rb_close"]).round(2)
        df["spread_hc_rb_spot"] = (df["spot_sh_hc"] - df["spot_hz_zhongtian"]).round(2)
        df["ratio_rb_i"] = (df["rb_close"] / df["i_close"].replace(0, np.nan)).round(4)
        df["ratio_j_i"] = (df["j_close"] / df["i_close"].replace(0, np.nan)).round(4)

        # 杭州微观库销比 (库存 / 日出库，单位: 天)
        df["hz_stock_to_sales"] = (df["inv_hz_stock"] / df["flow_hz_outflow"].replace(0, np.nan)).rolling(5, min_periods=1).mean().round(2)

        # 北材南下沈杭价差 (杭州中天螺纹 - 沈阳螺纹)
        spot_sy = df["spot_reg_sy_rb"].copy()
        df["north_south_spread"] = (df["spot_hz_zhongtian"] - spot_sy).round(2)

        # -------------------------------------------------------------
        # 7. 资金情绪与微观结构 (A05.2)
        # -------------------------------------------------------------
        # 成交持仓比 VOI
        df["rb_voi"] = (df["rb_volume"] / df["rb_oi"].replace(0, np.nan)).round(4)

        # 价格收益率与持仓变动
        df["rb_ret_1d"] = df["rb_close"].pct_change().fillna(0)
        df["rb_oi_diff1"] = df["rb_oi"].diff().fillna(0)

        # 五类量价仓微观打标
        pv_states = []
        for _, row in df.iterrows():
            ret = row["rb_ret_1d"]
            d_oi = row["rb_oi_diff1"]
            if abs(ret) < 0.002:
                pv_states.append("平衡震荡")
            elif ret > 0 and d_oi > 0:
                pv_states.append("增仓上涨")
            elif ret > 0 and d_oi <= 0:
                pv_states.append("减仓上涨")
            elif ret < 0 and d_oi > 0:
                pv_states.append("增仓下跌")
            else:
                pv_states.append("减仓下跌")
        df["micro_pv_state"] = pv_states

        # 技术结构均线
        df["ma_20"] = df["rb_close"].rolling(20, min_periods=5).mean().round(2)
        df["ma_60"] = df["rb_close"].rolling(60, min_periods=10).mean().round(2)

        # -------------------------------------------------------------
        # 8. 价格背离度量层
        # -------------------------------------------------------------
        # 价格 10 日动量 vs 基本面 10 日动量 (标准化对比)
        ret_10d = df["rb_close"].pct_change(10).fillna(0)
        df["z_price_10d"] = rolling_zscore(ret_10d)
        df["z_fund_10d"] = rolling_zscore(df["fv_10d"])

        # 背离判定条件: 价格动量与基本面动量符号相反，且二者乘积 < -0.5
        divergence_signal = (df["z_price_10d"] * df["z_fund_10d"] < -0.5)

        div_days = []
        cur_streak = 0
        for is_div in divergence_signal:
            if is_div:
                cur_streak += 1
            else:
                cur_streak = 0
            div_days.append(cur_streak)
        df["divergence_days"] = div_days

        # 累计背离面积 (无量纲动量差的积分)
        df["divergence_gap"] = (df["z_price_10d"] - df["z_fund_10d"]).where(divergence_signal, 0.0)
        df["divergence_area"] = df["divergence_gap"].rolling(10).sum().round(4)
        df["divergence_zscore"] = rolling_zscore(df["divergence_area"]).round(4)

        # 财政发债预期 vs 现货微观现实背离: 财政脉冲高涨但杭州现货出库疲弱
        fiscal_pulse = df["fiscal_steel_pulse"] if "fiscal_steel_pulse" in df.columns else pd.Series(0.0, index=df.index)
        flow_hz = df["flow_hz_outflow"] if "flow_hz_outflow" in df.columns else pd.Series(0.0, index=df.index)
        flow_pct = flow_hz.rolling(252, min_periods=20).rank(pct=True).fillna(0.5)
        df["fiscal_spot_divergence"] = ((fiscal_pulse > 0.8) & (flow_pct < 0.35)).astype(int)

        # -------------------------------------------------------------
        # 9. 证据熵与模型置信度指标 (A06)
        # -------------------------------------------------------------
        # 方向证据熵 CDE (衡量各模块方向的一致性/分歧度)
        signals = []
        signals.append((df["score_supply"] > 0.1).astype(int) - (df["score_supply"] < -0.1).astype(int))
        signals.append((df["score_demand"] > 0.1).astype(int) - (df["score_demand"] < -0.1).astype(int))
        signals.append((df["score_inventory"] > 0.1).astype(int) - (df["score_inventory"] < -0.1).astype(int))
        signals.append((df["basis_tier3"] > 30).astype(int) - (df["basis_tier3"] < -30).astype(int))
        sig_matrix = np.array(signals) # (4, n)

        entropies = []
        neutral_shares = []
        for t in range(n):
            col = sig_matrix[:, t]
            pos = (col == 1).sum()
            neg = (col == -1).sum()
            neu = (col == 0).sum()
            total = len(col)
            neutral_shares.append(round(neu / total, 4))
            
            p = np.array([pos, neg, neu]) / total
            p = p[p > 0]
            ent = -np.sum(p * np.log2(p)) / np.log2(3) # 归一化至 [0, 1]
            entropies.append(round(ent, 4))

        df["evidence_entropy"] = entropies
        df["neutral_share"] = neutral_shares
        df["data_freshness_ratio"] = np.clip(1.0 - df["data_age"] / 14.0, 0.0, 1.0).round(4)

        # -------------------------------------------------------------
        # 10. 多尺度历史分位数对比指标层 (Multi-Horizon Percentile Ranks, PIT 无未来信息)
        # 架构兼备两端：
        #   1) 近期 1 年滚动分位 (pct_*_1y): 滚动 252 交易日，反映当前宏观与产业微观新常态下的边际松紧；
        #   2) 历年全景扩展分位 (pct_*_hist): 全历史 PIT expanding 累积，反映跨越数年大周期的绝对历史极值；
        #   3) 双尺度综合自适应分位 (pct_*): 融合 50% 近期 + 50% 历年，兼具近期敏锐度与历年大局观！
        # -------------------------------------------------------------
        pct_df = self.compute_historical_percentiles(
            df, window=rolling_window, min_periods=20, blend_weight_1y=0.50
        )

        # -------------------------------------------------------------
        # 11. 跨品种极端异动与领头羊检测层 (A05.2)
        # 涵盖五品种短期波动率异动比、逼仓挤仓压力、截面领头羊与成本推升剪刀差
        # -------------------------------------------------------------
        shock_det = CrossCommodityShockDetector()
        shock_df = shock_det.compute_all_shock_features(df)

        df = pd.concat([df, pct_df, shock_df], axis=1)

        return df

    def compute_historical_percentiles(
        self,
        df: pd.DataFrame,
        window: int = 252,
        min_periods: int = 20,
        blend_weight_1y: float = 0.50,
    ) -> pd.DataFrame:
        """
        计算无未来函数 (PIT) 的多尺度自适应历史分位数对比指标 (Multi-Horizon Percentile Ranks)
        架构兼备两端：
          1. 近期 1 年滚动分位 (pct_*_1y): 滚动 252 交易日，反映当前宏观与产业微观新常态下的边际松紧；
          2. 历年全景扩展分位 (pct_*_hist): 全历史 PIT expanding 累积，反映跨越数年大周期的绝对历史极值；
          3. 双尺度综合分位 (pct_*): 融合 50% 近 1 年 + 50% 历年全景，既有近期敏锐度，又有历年大局观！
        严格保证每个截面 t 仅使用历史观测，PIT 无未来函数。
        分位数值域严格位于 [0.0, 1.0]，冷启动/缺失值填充 0.5 (中性历史中位数)。
        """
        res = pd.DataFrame(index=df.index)
        percentile_cols = {
            "virtual_mill_margin": "pct_virtual_mill_margin",
            "cost_gap_ratio": "pct_cost_gap_ratio",
            "profit_bf": "pct_profit_bf",
            "hc_virtual_margin": "pct_hc_virtual_margin",
            "spread_hc_rb": "pct_spread_hc_rb",
            "spread_hc_rb_profit": "pct_spread_hc_rb_profit",
            "ratio_rb_i": "pct_ratio_rb_i",
            "ratio_j_i": "pct_ratio_j_i",
            "iron_scrap_spread": "pct_iron_scrap_spread",
            "billet_rebar_spread": "pct_billet_rebar_spread",
            "north_south_spread": "pct_north_south_spread",
            "roll_yield_annual": "pct_roll_yield",
            "basis_tier3": "pct_basis_tier3",
            "basis_zhongtian": "pct_basis_zhongtian",
            "flow_hz_outflow": "pct_flow_hz_outflow",
            "hz_stock_to_sales": "pct_hz_stock_to_sales",
            "building_deal_volume": "pct_building_deal_volume",
            "rb_voi": "pct_rb_voi",
            "special_bond_rolling4w": "pct_special_bond_rolling4w",
            "fiscal_steel_pulse": "pct_fiscal_steel_pulse",
            "pacing_acceleration_ratio": "pct_pacing_acceleration_ratio",
        }
        for src_col, target_col in percentile_cols.items():
            if src_col in df.columns:
                p_1y = (
                    df[src_col]
                    .rolling(window=window, min_periods=min_periods)
                    .rank(pct=True)
                    .fillna(0.5)
                    .clip(0.0, 1.0)
                    .round(4)
                )
                p_hist = (
                    df[src_col]
                    .expanding(min_periods=min_periods)
                    .rank(pct=True)
                    .fillna(0.5)
                    .clip(0.0, 1.0)
                    .round(4)
                )
                # 分别输出近期 1 年与历年全景特征
                res[f"{target_col}_1y"] = p_1y
                res[f"{target_col}_hist"] = p_hist
                # 输出双尺度综合自适应特征
                res[target_col] = (blend_weight_1y * p_1y + (1.0 - blend_weight_1y) * p_hist).round(4)
        return res
