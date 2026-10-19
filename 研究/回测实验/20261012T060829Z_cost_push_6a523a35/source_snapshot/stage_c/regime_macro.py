#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/regime_macro.py
功能: 阶段 C 宏观与外部环境状态引擎 (Macro Regime Engine)
职责:
  严格遵循《实施手册》第 4.1 节与 A05/A06 规范:
  1. 识别宏观超常政策/地缘冲击窗口 (Policy Shock Windows);
  2. 量化宏观覆盖强度指数 (Macro Override Intensity);
  3. 判定宏观与产业主导边界 (产业主导 / 宏观覆盖 / 混合 / Unknown);
  4. 输出宏观政策倾向 (Stimulus / Contraction / Neutral / Unknown);
  5. 为下游模型置信度衰减提供明确的外部覆盖证据。
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class MacroRegimeClassifier:
    """
    宏观与外部环境状态分类器 (100% 纯客观数据驱动，彻底杜绝后视镜硬编码日历)
    
    外生冲击与宏观覆盖感知三大客观数据源:
      1. 官方公布的客观宏观经济指标偏离度 (PMI 极值偏离、地产投资同比下行);
      2. 跨品种异动与供给挤仓指数 (is_raw_material_squeeze: 由量价仓客观派生);
      3. 盘面内生极端波动率异动脉冲 (vol_shock_ratio >= 2.5 且 5 日收益偏离 >= 5%).
    """

    def __init__(self):
        pass

    def classify_row(self, row: pd.Series, dt_str: Optional[str] = None) -> Dict[str, Any]:
        """
        对单日截面推断宏观状态 (纯指标数据输入，绝不依据 dt_str 日期打后视镜补丁)
        """
        pmi = row.get("macro_pmi", np.nan)
        re_invest = row.get("real_estate_invest_yoy", np.nan)

        # 1. 检查客观跨品种原料极端供给冲击与逼仓 (由波动率与持仓异动客观生成)
        is_raw_squeeze = bool(row.get("is_raw_material_squeeze", False))

        # 2. 检查盘面内生极端波动率脉冲 (黑天鹅事件 live 冲击发生时，盘面 5d 波动率暴增且伴随大幅单边位移)
        vol_shock = row.get("rb_vol_shock_ratio", 1.0)
        ret_5d = row.get("rb_ret_5d", row.get("ret_5d", 0.0))
        if pd.isna(ret_5d):
            ret_5d = 0.0

        is_tape_shock = (not pd.isna(vol_shock)) and (vol_shock >= 2.5) and (abs(ret_5d) >= 0.05)

        # 2.5 检查地方政府发债与财政钢材脉冲客观外生变量
        fiscal_pulse = row.get("fiscal_steel_pulse", np.nan)
        pacing_regime = row.get("pacing_regime", "发债平稳运行期")
        bond_progress = row.get("special_bond_progress", np.nan)

        is_fiscal_shock = (not pd.isna(fiscal_pulse)) and (abs(fiscal_pulse) >= 2.6)

        # 判定外生冲击信号
        if is_raw_squeeze:
            is_shock = True
            shock_event = "RAW_MATERIAL_PRICE_SQUEEZE"
            shock_bias = "Unconfirmed_Raw_Shock"
        elif is_tape_shock:
            is_shock = True
            if ret_5d > 0:
                shock_event = "MARKET_VOLATILITY_EXPANSION_UP"
                shock_bias = "Market_Rally"
            else:
                shock_event = "MARKET_VOLATILITY_EXPANSION_DOWN"
                shock_bias = "Market_Decline"
        elif is_fiscal_shock:
            is_shock = True
            if fiscal_pulse > 0:
                shock_event = "FISCAL_EXPANSION_PULSE"
                shock_bias = "Stimulus"
            else:
                shock_event = "FISCAL_CLIFF_CONTRACTION"
                shock_bias = "Contraction"
        else:
            is_shock = False
            shock_event = "NONE"
            shock_bias = "Neutral"

        # 3. 宏观覆盖强度指数计算 (Macro Override Intensity, [0.0, 1.0])
        override_intensity = 0.20 # 基础平稳水平

        if is_shock:
            override_intensity = max(override_intensity, 0.75 if is_raw_squeeze else 0.80)

        if not pd.isna(pmi):
            # 偏离 50 荣枯线的幅度
            pmi_dev = abs(pmi - 50.0)
            if pmi < 48.0 or pmi > 52.0:
                override_intensity = max(override_intensity, min(0.95, 0.55 + pmi_dev * 0.15))
            elif 49.2 <= pmi <= 50.8:
                override_intensity = min(override_intensity, 0.35 if not is_shock else override_intensity)
            else:
                override_intensity = max(override_intensity, 0.45)

        if not pd.isna(re_invest) and re_invest < -10.0:
            # 地产投资严重失速拖累
            override_intensity = min(1.0, override_intensity + 0.10)

        # 财政脉冲对宏观覆盖强度的调节
        if not pd.isna(fiscal_pulse):
            if fiscal_pulse > 1.2 or pacing_regime in ["发债高速冲刺期", "发债预期加速期"]:
                override_intensity = max(override_intensity, min(0.60, 0.35 + (fiscal_pulse - 1.0) * 0.15 if fiscal_pulse > 1.0 else 0.40))
            elif pacing_regime == "额度收尾断档期" and fiscal_pulse < -0.5:
                override_intensity = max(override_intensity, 0.40)

        # 4. 离散宏观状态 (Macro Regime)
        if pd.isna(pmi) and not is_shock:
            macro_regime = "Unknown"
            policy_bias = "Unknown"
        elif is_shock:
            macro_regime = "宏观覆盖"
            policy_bias = shock_bias
        elif override_intensity >= 0.60:
            macro_regime = "宏观覆盖"
            policy_bias = "Stimulus" if pmi > 51.0 or (not pd.isna(fiscal_pulse) and fiscal_pulse > 0.8) else "Contraction"
        elif override_intensity <= 0.35:
            macro_regime = "产业主导"
            policy_bias = "Neutral"
        else:
            macro_regime = "混合"
            if pmi > 50.2 or (not pd.isna(fiscal_pulse) and fiscal_pulse > 0.8):
                policy_bias = "Stimulus"
            elif pmi < 49.5 or (not pd.isna(fiscal_pulse) and fiscal_pulse < -1.0) or pacing_regime == "额度收尾断档期":
                policy_bias = "Contraction"
            else:
                policy_bias = "Neutral"

        return {
            "macro_regime": macro_regime,
            "macro_override_intensity": round(float(override_intensity), 4),
            "external_shock_flag": bool(is_shock),
            "macro_shock_event": shock_event,
            "macro_policy_bias": policy_bias,
            "macro_fiscal_regime": str(pacing_regime) if pd.notna(pacing_regime) and pacing_regime else "发债平稳运行期",
            "macro_fiscal_pulse": round(float(fiscal_pulse), 4) if pd.notna(fiscal_pulse) else 0.0,
            "macro_bond_progress": round(float(bond_progress), 4) if pd.notna(bond_progress) else 0.0,
        }

    def classify_all(self, df: pd.DataFrame) -> pd.DataFrame:
        """批量推断宏观状态宽表"""
        records = []
        for dt, row in df.iterrows():
            dt_str = str(dt)[:10]
            rec = self.classify_row(row, dt_str)
            records.append(rec)

        res_df = pd.DataFrame(records, index=df.index)
        return res_df
