#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: compute_hangzhou_spot_features.py
用途:
  基于 `数据/原始/每日现货_清洗规范版.csv` 计算 12 项高频微观衍生特征，
  并按照项目血缘追溯契约增量写入 `数据/加工/加工指标.csv`。
"""

import os
import sys
import datetime
import pandas as pd
import numpy as np

PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
CLEAN_WIDE_CSV_PATH = os.path.join(PROJECT_ROOT, "数据/原始/每日现货_清洗规范版.csv")
PROCESSED_CSV_PATH = os.path.join(PROJECT_ROOT, "数据/加工/加工指标.csv")

def compute_features(target_date: str = None, start_date: str = None):
    mode_str = f"增量模式 (目标日: {target_date})" if target_date else (f"区间模式 (>={start_date})" if start_date else "全量模式")
    print(f"[1/4] 读取清洗宽表 [{mode_str}]: {CLEAN_WIDE_CSV_PATH}")
    df = pd.read_csv(CLEAN_WIDE_CSV_PATH)
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date').reset_index(drop=True)
    df['date_str'] = df['date'].dt.strftime('%Y-%m-%d')

    print("[2/4] 正在计算 12 项微观现货衍生特征...")

    # 1. 品牌溢价: 中天 - 三类
    df['SPREAD_BRAND_1_3'] = df['spot_hz_zhongtian'] - df['spot_hz_tier3']

    # 2. 华东现货卷螺差: 上海热卷 - 杭州中天螺纹
    df['SPREAD_REBAR_COIL_HZ'] = df['spot_reg_sh_hc'] - df['spot_hz_zhongtian']

    # 3. 杭州日出库 7 日均值
    df['HZ_OUTFLOW_MA7'] = df['flow_hz_outflow'].rolling(window=7, min_periods=3).mean()

    # 4. 杭州日度库销比天数 (库存 / 7日出库均值)
    df['HZ_DAYS_TO_CLEAR'] = np.where(
        (df['HZ_OUTFLOW_MA7'] > 0) & (df['inv_hz_stock'] > 0),
        df['inv_hz_stock'] / df['HZ_OUTFLOW_MA7'],
        np.nan
    )

    # 5. 电炉谷电硬底支撑缓冲垫 (中天现货 - 华东电炉谷电成本)
    df['EAF_VALLEY_BUFFER'] = df['spot_hz_zhongtian'] - df['cost_east_eaf_valley']

    # 6. 北材南下套利价差 (杭州螺纹 - 沈阳螺纹)
    df['SPREAD_NORTH_SOUTH'] = df['spot_reg_hz_rb'] - df['spot_reg_sy_rb']

    # 7. 西南电炉出川价差 (成都螺纹 - 杭州螺纹)
    df['SPREAD_EAST_WEST'] = df['spot_reg_cd_rb'] - df['spot_reg_hz_rb']

    # 8. 华南分流天平价差 (广州螺纹 - 杭州螺纹)
    df['SPREAD_SOUTH_EAST'] = df['spot_reg_gz_rb'] - df['spot_reg_hz_rb']

    # 9. 铁废差 (华东铁水成本 - 华东废钢≥6mm)
    df['FE_SCRAP_DIFF'] = df['cost_east_hot_metal'] - df['scrap_east_6mm']

    # 10. 废钢到耗供需剪刀差 (320样本到货 - 周度日耗)
    df['SCRAP_SUPPLY_DEMAND_GAP'] = df['scrap_320_arrival'] - df['scrap_weekly_daily_consumption']

    # 11. 螺坯差 (中天螺纹 - 唐山方坯)
    df['BILLET_REBAR_SPREAD'] = df['spot_hz_zhongtian'] - df['spot_ts_billet']

    # 12. 杭惠码头倒运毛价差 (杭州螺纹 - 惠龙港螺纹)
    df['HLG_PORT_SPREAD'] = df['spot_reg_hz_rb'] - df['spot_port_hlg_rb']

    # 13. 杭惠内河水运净套利利润 (价差扣除 50 元/吨内河船运与入库仓储费)
    df['HLG_NET_ARBITRAGE'] = df['HLG_PORT_SPREAD'] - 50.0

    # 14-16. 期现持有成本模型 (Cost of Carry Model, 6% 资金利率 + 0.15 元/天仓储 + 20 元杂费)
    # 加载期货行情以匹配最近交割月合约
    fut_path = os.path.join(PROJECT_ROOT, "数据/原始/01_期货行情.csv")
    if os.path.exists(fut_path):
        fut_df = pd.read_csv(fut_path)
        fut_rb = fut_df[fut_df['variable_id'] == 'F06'].copy()
        fut_rb['data_date'] = pd.to_datetime(fut_rb['data_date'])
        
        # 合并期货收盘与合约
        merged_fut = pd.merge(df[['date', 'spot_hz_tier3', 'spot_hz_zhongtian']], fut_rb[['data_date', 'contract', 'value']], left_on='date', right_on='data_date', how='left')
        
        # 提取交割年月 (如 SHFE.rb2405 -> 2024-05-15, rb2510 -> 2025-10-15)
        def get_delivery_date(c_str):
            if not isinstance(c_str, str) or len(c_str) < 4:
                return pd.NaT
            digits = ''.join(filter(str.isdigit, c_str))
            if len(digits) == 4:
                yy = int('20' + digits[:2])
                mm = int(digits[2:])
                return pd.Timestamp(year=yy, month=mm, day=15)
            return pd.NaT

        merged_fut['delivery_date'] = merged_fut['contract'].apply(get_delivery_date)
        merged_fut['days_to_delivery'] = (merged_fut['delivery_date'] - merged_fut['date']).dt.days
        # 只保留合理倒计时 (0 到 180 天)
        merged_fut['days_to_delivery'] = merged_fut['days_to_delivery'].apply(lambda x: x if 0 <= x <= 180 else np.nan)
        
        # 计算资金利息成本 (6% 年化)，按用户指示：只计算资金利息，仓储与杂费不计入此项
        merged_fut['interest_cost_tier3'] = merged_fut['spot_hz_tier3'] * (0.06 / 365.0) * merged_fut['days_to_delivery']
        merged_fut['full_carry_cost'] = merged_fut['interest_cost_tier3']
        
        # 净正套空间 (期货收盘 - CTD现货 - 资金利息成本)
        merged_fut['net_cash_carry_margin'] = merged_fut['value'] - merged_fut['spot_hz_tier3'] - merged_fut['full_carry_cost']
        
        df['DAYS_TO_DELIVERY'] = merged_fut['days_to_delivery']
        df['CARRY_TOTAL_COST'] = merged_fut['full_carry_cost']
        df['NET_CASH_CARRY_MARGIN'] = merged_fut['net_cash_carry_margin']
    else:
        df['DAYS_TO_DELIVERY'] = np.nan
        df['CARRY_TOTAL_COST'] = np.nan
        df['NET_CASH_CARRY_MARGIN'] = np.nan

    feature_meta = {
        'SPREAD_BRAND_1_3': {'unit': '元/吨', 'freq': '日频', 'desc': '一三类品牌价差(中天-三类,现货恐慌与流动性折价)'},
        'SPREAD_REBAR_COIL_HZ': {'unit': '元/吨', 'freq': '日频', 'desc': '华东现货卷螺差(上海热卷-杭州螺纹)'},
        'HZ_OUTFLOW_MA7': {'unit': '万吨/天', 'freq': '日频', 'desc': '杭州螺纹每日出库量7日均线'},
        'HZ_DAYS_TO_CLEAR': {'unit': '天', 'freq': '日频', 'desc': '杭州螺纹日度库销比(杭州库存/7日均出库)'},
        'EAF_VALLEY_BUFFER': {'unit': '元/吨', 'freq': '日频', 'desc': '电炉谷电成本底线缓冲垫(中天-谷电成本)'},
        'SPREAD_NORTH_SOUTH': {'unit': '元/吨', 'freq': '日频', 'desc': '北材南下套利价差(杭州-沈阳)'},
        'SPREAD_EAST_WEST': {'unit': '元/吨', 'freq': '日频', 'desc': '西南电炉出川价差(成都-杭州)'},
        'SPREAD_SOUTH_EAST': {'unit': '元/吨', 'freq': '日频', 'desc': '华南南北分流天平价差(广州-杭州)'},
        'FE_SCRAP_DIFF': {'unit': '元/吨', 'freq': '日频', 'desc': '华东铁废差(铁水成本-废钢价格)'},
        'SCRAP_SUPPLY_DEMAND_GAP': {'unit': '万吨/天', 'freq': '日频', 'desc': '全国废钢到耗供需剪刀差(320到货-日耗)'},
        'BILLET_REBAR_SPREAD': {'unit': '元/吨', 'freq': '日频', 'desc': '螺坯差(中天螺纹-唐山方坯,轧材利润)'},
        'HLG_PORT_SPREAD': {'unit': '元/吨', 'freq': '日频', 'desc': '杭惠码头倒运毛价差(杭州现货-惠龙港码头)'},
        'HLG_NET_ARBITRAGE': {'unit': '元/吨', 'freq': '日频', 'desc': '杭惠内河水运净套利利润(扣减50元内河船运与仓储费)'},
        'DAYS_TO_DELIVERY': {'unit': '天', 'freq': '日频', 'desc': '期货主力合约交割剩余天数'},
        'CARRY_TOTAL_COST': {'unit': '元/吨', 'freq': '日频', 'desc': '期现资金利息成本(6%年化资金利息)'},
        'NET_CASH_CARRY_MARGIN': {'unit': '元/吨', 'freq': '日频', 'desc': '无风险期现正套净利润(期货-CTD三类-资金利息)'}
    }

    # 读取已有加工特征库
    existing_processed = pd.read_csv(PROCESSED_CSV_PATH) if os.path.exists(PROCESSED_CSV_PATH) else pd.DataFrame()

    print(f"[3/4] 已有加工特征库记录数: {len(existing_processed)}")

    now_iso = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    new_rows = []

    for feat_id, meta in feature_meta.items():
        s = df[['date_str', feat_id]].dropna()
        if target_date:
            s = s[s['date_str'] == str(target_date)]
        elif start_date:
            s = s[s['date_str'] >= str(start_date)]

        for _, r in s.iterrows():
            d_str = r['date_str']
            val = float(r[feat_id])
            
            # 血缘追溯
            input_obs = f"OBS_PROPRIETARY_*_{d_str.replace('-', '')}"
            calc_id = f"CALC_{feat_id}_{d_str.replace('-', '')}"
            
            new_rows.append({
                'feature_id': feat_id,
                'calc_id': calc_id,
                'data_date': d_str,
                'value': round(val, 4),
                'unit': meta['unit'],
                'frequency': meta['freq'],
                'input_observation_ids': input_obs,
                'calc_rule_version': 'V1.0_PROPRIETARY_SPOT_DERIVED',
                'calculated_at': now_iso,
                'note': meta['desc']
            })

    new_df = pd.DataFrame(new_rows)
    print(f"  - 新增计算加工特征: {len(new_df)} 条")

    # 合并去重与快速增量写入
    if len(existing_processed) > 0 and len(new_df) > 0:
        if target_date:
            mask = (existing_processed['data_date'] == str(target_date)) & (existing_processed['feature_id'].isin(new_df['feature_id']))
            existing_processed = existing_processed[~mask]
            combined_df = pd.concat([existing_processed, new_df], ignore_index=True)
        else:
            combined_df = pd.concat([existing_processed, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=['feature_id', 'data_date'], keep='last')
    elif len(new_df) > 0:
        combined_df = new_df
    else:
        combined_df = existing_processed

    combined_df.to_csv(PROCESSED_CSV_PATH, index=False, encoding='utf-8')
    print(f"[4/4] 成功落盘更新加工指标库: {PROCESSED_CSV_PATH}，总记录数: {len(combined_df)}")

    # 打印部分最新特征抽样
    print("\n=== 2026年9月最新交易日高频衍生特征抽样 ===")
    recent_dates = df['date_str'].tail(5).tolist()
    for d in recent_dates:
        row = df[df['date_str'] == d].iloc[0]
        print(f"[{d}] 一三类差: {row['SPREAD_BRAND_1_3']} | 卷螺差: {row['SPREAD_REBAR_COIL_HZ']} | 库销比: {row['HZ_DAYS_TO_CLEAR']:.1f}天 | 谷电缓冲: {row['EAF_VALLEY_BUFFER']} | 杭沈差: {row['SPREAD_NORTH_SOUTH']} | 铁废差: {row['FE_SCRAP_DIFF']} | 到耗差: {row['SCRAP_SUPPLY_DEMAND_GAP']}")

if __name__ == "__main__":
    compute_features()
