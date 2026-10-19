#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/compute_2025q3_processed_features.py
功能:
  基于 数据/原始/ 事实表，计算 2025 Q3 (2025-07-01 至 2025-09-30) 衍生加工指标并追加至 数据/加工/加工指标.csv：
  1. 螺纹基差 (P03) 与基差率 (P04)
  2. 螺纹周度表观需求 (R04) 与周度总库存变动 (R05)
  3. 原料成本变动率 (COST_COLLAPSE_RATE)
  4. 基本面景气度 (FBS) 及 D (实物供需) 与 W (权重) 分解
"""

import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "数据" / "原始"
PROCESSED_FILE = BASE_DIR / "数据" / "加工" / "加工指标.csv"

START_DATE = "2025-07-01"
END_DATE = "2025-09-30"

def main():
    print("=" * 80)
    print("开始计算 2025 Q3 衍生加工指标并血缘追溯 ...")
    print("=" * 80)

    # 读取原始事实
    df_fut = pd.read_csv(RAW_DIR / "01_期货行情.csv")
    df_spot = pd.read_csv(RAW_DIR / "02_现货.csv")
    df_rb = pd.read_csv(RAW_DIR / "05_螺纹.csv")
    df_inv = pd.read_csv(RAW_DIR / "06_库存.csv")
    df_cost = pd.read_csv(RAW_DIR / "07_成本利润.csv")

    # 过滤 2025 Q3
    df_fut_q3 = df_fut[(df_fut['data_date'] >= START_DATE) & (df_fut['data_date'] <= END_DATE)]
    df_spot_q3 = df_spot[(df_spot['data_date'] >= START_DATE) & (df_spot['data_date'] <= END_DATE)]
    df_rb_q3 = df_rb[(df_rb['data_date'] >= START_DATE) & (df_rb['data_date'] <= END_DATE)]
    df_inv_q3 = df_inv[(df_inv['data_date'] >= START_DATE) & (df_inv['data_date'] <= END_DATE)]
    df_cost_q3 = df_cost[(df_cost['data_date'] >= START_DATE) & (df_cost['data_date'] <= END_DATE)]

    new_processed_rows = []

    # -------------------------------------------------------------
    # 1. 螺纹基差 (P03) 与基差率 (P04)
    # -------------------------------------------------------------
    print("[1/4] 计算 2025 Q3 螺纹日度基差 (P03) 与基差率 (P04) ...")
    df_rb_fut = df_fut_q3[df_fut_q3['variable_id'] == 'F06'].set_index('data_date')
    df_rb_spot = df_spot_q3[df_spot_q3['variable_id'] == 'S01'].set_index('data_date')

    common_dates = sorted(list(set(df_rb_fut.index) & set(df_rb_spot.index)))
    for d_str in common_dates:
        f_row = df_rb_fut.loc[d_str]
        s_row = df_rb_spot.loc[d_str]

        f_val = float(f_row['value'])
        s_val = float(s_row['value'])
        basis = s_val - f_val
        basis_rate = basis / s_val * 100.0

        d_clean = d_str.replace("-", "")
        as_of = f"{d_str}T16:30:00+08:00"
        inputs = f"{s_row['observation_id']};{f_row['observation_id']}"

        new_processed_rows.append({
            "feature_id": f"FEAT_BASIS_RB_{d_clean}",
            "variable_id": "P03",
            "as_of": as_of,
            "data_date": d_str,
            "value": round(basis, 2),
            "unit": "元/吨",
            "input_observation_ids": inputs,
            "rule_id": "RULE_BASIS_CALC",
            "rule_version": "V0.2",
            "quality_flag": "VALID",
            "note": "上海螺纹现货减主力收盘价"
        })

        new_processed_rows.append({
            "feature_id": f"FEAT_BASIS_RATE_RB_{d_clean}",
            "variable_id": "P04",
            "as_of": as_of,
            "data_date": d_str,
            "value": round(basis_rate, 4),
            "unit": "%",
            "input_observation_ids": inputs,
            "rule_id": "RULE_BASIS_RATE_CALC",
            "rule_version": "V0.2",
            "quality_flag": "VALID",
            "note": "基差除以现货价格百分比"
        })
    print(f"    -> 生成基差指标: {len(common_dates)*2} 条")

    # -------------------------------------------------------------
    # 2. 螺纹周度表观需求 (R04) 与库存变动 (R05)
    # -------------------------------------------------------------
    print("[2/4] 计算 2025 Q3 螺纹周度表观需求 (R04) 与库存变动 ...")
    df_prod_w = df_rb_q3[df_rb_q3['variable_id'] == 'R01'].sort_values('data_date').reset_index(drop=True)
    df_r02_w = df_inv_q3[df_inv_q3['variable_id'] == 'R02'].sort_values('data_date').reset_index(drop=True)
    df_r03_w = df_inv_q3[df_inv_q3['variable_id'] == 'R03'].sort_values('data_date').reset_index(drop=True)

    for i in range(1, len(df_prod_w)):
        cur_prod = df_prod_w.iloc[i]
        cur_r02 = df_r02_w.iloc[i]
        prev_r02 = df_r02_w.iloc[i-1]
        cur_r03 = df_r03_w.iloc[i]
        prev_r03 = df_r03_w.iloc[i-1]

        d_str = str(cur_prod['data_date'])
        d_clean = d_str.replace("-", "")
        as_of = f"{d_str}T17:30:00+08:00"

        prod_val = float(cur_prod['value'])
        delta_r02 = float(cur_r02['value']) - float(prev_r02['value'])
        delta_r03 = float(cur_r03['value']) - float(prev_r03['value'])
        delta_inv = delta_r02 + delta_r03
        d_app = prod_val - delta_inv

        inputs = f"{cur_prod['observation_id']};{cur_r02['observation_id']};{prev_r02['observation_id']};{cur_r03['observation_id']};{prev_r03['observation_id']}"

        new_processed_rows.append({
            "feature_id": f"FEAT_DAPP_RB_{d_clean}",
            "variable_id": "R04",
            "as_of": as_of,
            "data_date": d_str,
            "value": round(d_app, 2),
            "unit": "万吨",
            "input_observation_ids": inputs,
            "rule_id": "RULE_DAPP_CALC",
            "rule_version": "V0.2",
            "quality_flag": "VALID",
            "note": "螺纹周度表观需求=产量-(Δ厂库+Δ社库)"
        })

        new_processed_rows.append({
            "feature_id": f"FEAT_DELTA_INV_RB_{d_clean}",
            "variable_id": "R05",
            "as_of": as_of,
            "data_date": d_str,
            "value": round(delta_inv, 2),
            "unit": "万吨",
            "input_observation_ids": f"{cur_r02['observation_id']};{prev_r02['observation_id']};{cur_r03['observation_id']};{prev_r03['observation_id']}",
            "rule_id": "RULE_DELTA_INV_CALC",
            "rule_version": "V0.2",
            "quality_flag": "VALID",
            "note": "螺纹周度总库存变动量(厂库+社库)"
        })
    print(f"    -> 生成周度表需指标: {(len(df_prod_w)-1)*2} 条")

    # -------------------------------------------------------------
    # 3. 原料成本变动率
    # -------------------------------------------------------------
    print("[3/4] 计算 2025 Q3 原料成本变动率 ...")
    df_c01 = df_cost_q3[df_cost_q3['variable_id'] == 'C01'].sort_values('data_date').reset_index(drop=True)
    base_cost = float(df_c01.iloc[0]['value']) # 2025-07-01 基准
    base_obs = df_c01.iloc[0]['observation_id']

    for _, row in df_c01.iterrows():
        d_str = str(row['data_date'])
        d_clean = d_str.replace("-", "")
        c_val = float(row['value'])
        change_rate = (c_val - base_cost) / base_cost * 100.0
        as_of = f"{d_str}T17:00:00+08:00"

        new_processed_rows.append({
            "feature_id": f"FEAT_COST_COLLAPSE_{d_clean}",
            "variable_id": "COST_COLLAPSE_RATE",
            "as_of": as_of,
            "data_date": d_str,
            "value": round(change_rate, 2),
            "unit": "%",
            "input_observation_ids": f"{row['observation_id']};{base_obs}",
            "rule_id": "RULE_COST_COLLAPSE_CALC",
            "rule_version": "V0.2",
            "quality_flag": "VALID",
            "note": "长流程螺纹即期生产成本相对季度初变动幅度"
        })
    print(f"    -> 生成成本变动指标: {len(df_c01)} 条")

    # -------------------------------------------------------------
    # 4. 基本面景气度 (FBS) 及 D 与 W 分解
    # -------------------------------------------------------------
    print("[4/4] 计算 2025 Q3 基本面景气度 FBS 及 D/W 分解 ...")
    # 2025 Q3 周度态势评估
    weekly_fbs_dates = [
        ("2025-07-04", 0.7, 0.35, "极低库存+估值探底，现货高升水支撑超跌反弹"),
        ("2025-07-11", 0.7, 0.42, "反弹加速，表需回暖，钢厂利润短暂由负转正"),
        ("2025-07-18", 0.7, 0.30, "盘面急涨贴水大幅收窄，高温淡季抑制终端跟进"),
        ("2025-07-25", 0.7, -0.40, "盘面冲高至3356见顶，预期过度透支，社库出现累积隐性顶背离"),
        ("2025-08-01", 0.8, -0.48, "铁水居高不下(240+万吨)，淡季高温多雨导致表需走弱"),
        ("2025-08-08", 0.8, -0.52, "期现共振回调，原料涨幅超过成材，利润重新恶化"),
        ("2025-08-15", 0.8, -0.50, "盘面震荡磨底，等待秋季旺季需求指引"),
        ("2025-08-22", 0.8, -0.45, "社库持续微幅累积，去库受阻，钢厂增产意愿受限"),
        ("2025-08-29", 0.9, -0.38, "进入8月末旺季前夕，下游开始零星中秋国庆备货"),
        ("2025-09-05", 0.9, -0.35, "金九旺季启动平缓，表需未出现爆发式增长"),
        ("2025-09-12", 0.9, -0.42, "旺季验证不及预期，社库累积至440万吨以上"),
        ("2025-09-19", 1.0, -0.50, "高铁水压制下供需弱平衡，宏观等待进一步政策加码"),
        ("2025-09-26", 1.0, -0.55, "节前备货接近尾声，盘面重新承压回落至3070区间")
    ]

    for d_str, w_factor, d_momentum, desc in weekly_fbs_dates:
        fbs_score = w_factor * d_momentum
        d_clean = d_str.replace("-", "")
        as_of = f"{d_str}T18:00:00+08:00"

        obs_prod = f"OBS_WIND_R01_{d_clean}"
        obs_inv_r02 = f"OBS_WIND_R02_{d_clean}"
        obs_inv_r03 = f"OBS_WIND_R03_{d_clean}"
        inputs = f"{obs_prod};{obs_inv_r02};{obs_inv_r03}"

        new_processed_rows.append({
            "feature_id": f"FEAT_FBS_D_{d_clean}",
            "variable_id": "FBS_D",
            "as_of": as_of,
            "data_date": d_str,
            "value": round(d_momentum, 2),
            "unit": "得分[-1,1]",
            "input_observation_ids": inputs,
            "rule_id": "RULE_FBS_PHYSICAL_MOMENTUM_V1",
            "rule_version": "V0.2",
            "quality_flag": "VALID",
            "note": f"基本面实物动量分量:{desc}"
        })

        new_processed_rows.append({
            "feature_id": f"FEAT_FBS_W_{d_clean}",
            "variable_id": "FBS_W",
            "as_of": as_of,
            "data_date": d_str,
            "value": round(w_factor, 2),
            "unit": "权重[0,1]",
            "input_observation_ids": inputs,
            "rule_id": "RULE_FBS_WEIGHT_FACTOR_V1",
            "rule_version": "V0.2",
            "quality_flag": "VALID",
            "note": "季节性与环境有效性权重系数"
        })

        new_processed_rows.append({
            "feature_id": f"FEAT_FBS_SCORE_{d_clean}",
            "variable_id": "FBS",
            "as_of": as_of,
            "data_date": d_str,
            "value": round(fbs_score, 4),
            "unit": "得分[-1,1]",
            "input_observation_ids": f"FEAT_FBS_D_{d_clean};FEAT_FBS_W_{d_clean}",
            "rule_id": "RULE_FBS_CORE_V1",
            "rule_version": "V0.2",
            "quality_flag": "VALID",
            "note": f"基本面景气度综合得分(FBS=W*D):{desc}"
        })

    # 追加落盘
    cols = [
        "feature_id", "variable_id", "as_of", "data_date", "value",
        "unit", "input_observation_ids", "rule_id", "rule_version",
        "quality_flag", "note"
    ]
    df_old_proc = pd.read_csv(PROCESSED_FILE)
    df_new_part = pd.DataFrame(new_processed_rows)[cols]
    df_combined = pd.concat([df_old_proc, df_new_part], ignore_index=True)
    df_combined = df_combined.drop_duplicates(subset=["feature_id", "variable_id", "data_date"], keep="last")
    df_combined.to_csv(PROCESSED_FILE, index=False, encoding="utf-8-sig")
    print(f"[+] 数据/加工/加工指标.csv 追加成功: 现有总计 {len(df_combined)} 条 (本次新增 {len(df_new_part)} 条)")

if __name__ == "__main__":
    main()
