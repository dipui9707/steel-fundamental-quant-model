#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/state_fundamental.py
功能: 阶段 C 产业基本面供需矛盾与成本状态引擎 (Fundamental State Engine)
职责:
  严格遵循《实施手册》第 4.2 节、第 7 节与 A05/A05.1 规范:
  1. 纯实物供需矛盾方向与强度识别 (Fundamental Direction & Strength);
  2. 边际成本边界判定 (高炉完全成本、现金成本下轨与短流程电炉谷电缓冲);
  3. 虚拟钢厂毛利与原料端正负反馈机制 (IMM 扣减 1200 元制造杂费后的临界线);
  4. 供需分项深入刻画 (供给压力、需求韧性与库存演进轨迹);
  5. 严格坚持 State != Position，绝不产生买卖交易订单。
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class FundamentalStateClassifier:
    """
    产业基本面供需状态分类器
    """

    def __init__(self):
        pass

    def classify_row(self, row: pd.Series) -> Dict[str, Any]:
        """
        对单日截面推断产业基本面状态
        """
        fbs = row.get("fbs_score", np.nan)
        fv_10d = row.get("fv_10d", 0.0)
        fa_10d = row.get("fa_10d", 0.0)
        s_sup = row.get("score_supply", 0.0)
        s_dem = row.get("score_demand", 0.0)
        s_inv = row.get("score_inventory", 0.0)

        cost_gap = row.get("cost_gap_ratio", 0.0)
        profit_bf = row.get("profit_bf", 0.0)
        virtual_margin = row.get("virtual_mill_margin", 0.0)

        # ---------------------------------------------------------
        # 1. Fundamental Direction & Strength
        # ---------------------------------------------------------
        if pd.isna(fbs):
            fund_dir = "Unknown"
            fund_str = "Unknown"
        else:
            # 基础景气度得分与 10 日速度双重判定
            if fbs > 15.0 or (fbs > 0.0 and fv_10d > 0.25):
                fund_dir = "Bullish"
            elif fbs < -15.0 or (fbs < 0.0 and fv_10d < -0.25):
                fund_dir = "Bearish"
            else:
                fund_dir = "Neutral"

            abs_fbs = abs(fbs)
            if abs_fbs >= 35.0 or (abs_fbs >= 20.0 and abs(fv_10d) >= 0.5):
                fund_str = "High"
            elif abs_fbs >= 15.0:
                fund_str = "Medium"
            else:
                fund_str = "Low"

        # ---------------------------------------------------------
        # 2. Cost Boundary Regime (成本边界运行状态: 历史分位数自适应 + 现货真实利润校验)
        # ---------------------------------------------------------
        pct_cost_gap = row.get("pct_cost_gap_ratio", np.nan)
        pct_profit_bf = row.get("pct_profit_bf", np.nan)

        is_deep_loss = False
        is_high_margin = False

        if not pd.isna(profit_bf):
            # 当 profit_bf 有真实现货高炉利润时: 必须经由实物现货真实亏损校验!
            # 现货高升水/盘面深贴水时，盘面毛利压缩而钢厂实际仍有盈利(profit_bf > 0)，
            # 生产不会减产停炉，库存压力将持续累积，绝不能误判为深度亏损下轨支撑!
            is_spot_loss = (profit_bf <= 0.0)
            p_low = (not pd.isna(pct_profit_bf)) and (pct_profit_bf <= 0.10) and is_spot_loss
            cg_low = (not pd.isna(pct_cost_gap)) and (pct_cost_gap <= 0.10) and (cost_gap <= 0.05) and is_spot_loss
            cg_high = (not pd.isna(pct_cost_gap)) and (pct_cost_gap >= 0.90) and (cost_gap >= 0.10)
            p_high = (not pd.isna(pct_profit_bf)) and (pct_profit_bf >= 0.90) and (profit_bf >= 200.0)

            if p_low or cg_low or (cost_gap < -0.05 and profit_bf < -100.0):
                is_deep_loss = True
            elif cg_high or p_high or profit_bf > 400.0:
                is_high_margin = True
        elif not pd.isna(pct_cost_gap) or not pd.isna(pct_profit_bf):
            # 缺失实物利润数据时(历史早期)，回退到盘面估值分位数
            cg_low = (not pd.isna(pct_cost_gap)) and (pct_cost_gap <= 0.10) and (cost_gap <= 0.05)
            p_low = (not pd.isna(pct_profit_bf)) and (pct_profit_bf <= 0.10)
            cg_high = (not pd.isna(pct_cost_gap)) and (pct_cost_gap >= 0.90) and (cost_gap >= 0.10)
            p_high = (not pd.isna(pct_profit_bf)) and (pct_profit_bf >= 0.90)

            if cg_low or p_low or (cost_gap < -0.05):
                is_deep_loss = True
            elif cg_high or p_high or (cost_gap > 0.15):
                is_high_margin = True
        else:
            # 缺失回退到常数阈值
            if cost_gap < -0.05:
                is_deep_loss = True
            elif cost_gap > 0.15:
                is_high_margin = True

        if is_deep_loss:
            cost_regime = "深度亏损下轨支撑"
        elif is_high_margin:
            cost_regime = "高毛利扩张承压"
        else:
            cost_regime = "合理利润运行"

        # ---------------------------------------------------------
        # 3. Raw Material Feedback & Cost-Push Regime (原料正负反馈与成本推升机制)
        # ---------------------------------------------------------
        pct_vmm = row.get("pct_virtual_mill_margin", np.nan)
        cost_push = float(row.get("cost_push_spread_5d", 0.0))
        leader_type = str(row.get("dominant_leader_type", ""))
        is_raw_sq = bool(row.get("is_raw_material_squeeze", False))
        max_raw_sq = max(
            float(row.get("squeeze_index", 0.0)),
            float(row.get("i_squeeze_index", 0.0)),
            float(row.get("jm_squeeze_index", 0.0)),
            float(row.get("j_squeeze_index", 0.0)),
        )

        is_cost_pushing = (cost_push > 0.015) and (leader_type == "RAW_MATERIAL_SHOCK" or is_raw_sq or max_raw_sq >= 2.0)

        if not pd.isna(pct_vmm):
            is_neg_feedback = (pct_vmm <= 0.15 or virtual_margin < -100.0) and (fv_10d < 0 or fbs < 0)
            is_pos_feedback = (pct_vmm >= 0.85 or virtual_margin > 200.0) and (fbs > 0)
        else:
            is_neg_feedback = (virtual_margin < -100.0) and (fv_10d < 0 or fbs < 0)
            is_pos_feedback = (virtual_margin > 200.0) and (fbs > 0)

        # 核心区分: 若原料强力推升成本，不归为负反馈踩踏，而归为成本被动挤压推升
        if is_cost_pushing and (virtual_margin < 100.0 or (not pd.isna(pct_vmm) and pct_vmm <= 0.35)):
            raw_feedback = "成本被动挤压推升"
        elif is_neg_feedback:
            raw_feedback = "原料负反馈踩踏"
        elif is_pos_feedback:
            raw_feedback = "原料正反馈推升"
        else:
            raw_feedback = "中性平衡"

        # 成本推升三态识别: 持续型 (现货承接) vs 假突破型 (现货深贴水)
        pct_basis_1y = float(row.get("pct_basis_tier3_1y", row.get("pct_basis_tier3", 0.5)))
        outflow_pct = float(row.get("pct_flow_hz_outflow", 0.5))
        cost_cash_floor = float(row.get("cost_cash_floor", row.get("cost_bf", 0.0) - 250.0))
        close = float(row.get("rb_close", 0.0))

        if is_cost_pushing:
            if pct_basis_1y >= 0.40 and outflow_pct >= 0.30 and close >= cost_cash_floor:
                cost_push_regime = "SUSTAINED_COST_PUSH"
            elif pct_basis_1y < 0.25:
                cost_push_regime = "FALSE_BREAKOUT_COST_PUSH"
            else:
                cost_push_regime = "OBSERVE_COST_PUSH"
        else:
            cost_push_regime = "NORMAL_DEMAND_DRIVEN"

        # ---------------------------------------------------------
        # 4. Supply Pressure & Demand Resilience & Inventory Trajectory
        # ---------------------------------------------------------
        # S_supply 为价格支持分，越高代表供应压力越低。
        if s_sup < -0.30:
            supply_pressure = "High"
        elif s_sup > 0.30:
            supply_pressure = "Low"
        else:
            supply_pressure = "Moderate"

        # 需求端韧性 (S_demand 越高代表表需强劲)
        if s_dem > 0.25:
            demand_resilience = "Strong"
        elif s_dem < -0.25:
            demand_resilience = "Weak"
        else:
            demand_resilience = "Moderate"

        # 库存变动轨迹 (融合 S_inventory 与 inv_diff1_seasonal_zscore 超季节性去库指标)
        inv_z = row.get("inv_diff1_seasonal_zscore", 0.0)
        if pd.isna(inv_z):
            inv_z = 0.0

        if (s_inv > 0.40 and fa_10d > 0.10) or (inv_z < -1.0 and fa_10d > 0.0):
            inv_trajectory = "Accelerating Destock"
        elif s_inv > 0.10 or inv_z < -0.30:
            inv_trajectory = "Normal Destock"
        elif (s_inv < -0.40 and fa_10d < -0.10) or (inv_z > 1.0 and fa_10d < 0.0):
            inv_trajectory = "Accelerating Accumulate"
        elif s_inv < -0.10 or inv_z > 0.30:
            inv_trajectory = "Accumulating"
        else:
            inv_trajectory = "Balanced"

        return {
            "fundamental_direction": fund_dir,
            "fundamental_strength": fund_str,
            "cost_boundary_regime": cost_regime,
            "raw_feedback_regime": raw_feedback,
            "cost_push_regime": cost_push_regime,
            "supply_pressure": supply_pressure,
            "demand_resilience": demand_resilience,
            "inventory_trajectory": inv_trajectory,
        }

    def classify_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """批量推断基本面状态宽表"""
        records = []
        for _, row in df.iterrows():
            rec = self.classify_row(row)
            records.append(rec)

        res_df = pd.DataFrame(records, index=df.index)
        return res_df
