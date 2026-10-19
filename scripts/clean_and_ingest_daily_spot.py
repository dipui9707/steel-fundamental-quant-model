#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: clean_and_ingest_daily_spot.py
用途:
  1. 读取用户自有原始文件 `数据/原始/每日现货.xlsx` (保持该文件只读，不修改原文件)
  2. 修复已识别的 4 处微观人工录入笔误并强校验数据类型
  3. 导出标准化清洗宽表 `数据/原始/每日现货_清洗规范版.csv`
  4. 按照项目统一 PIT 契约，将 52 项指标转换为标准点时长表并落盘至 `数据/原始/每日现货_PIT明细.csv`
  5. 记录清洗日志与各字段统计特征
"""

import os
import sys
import datetime
import pandas as pd
import numpy as np

# 路径配置
PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
RAW_EXCEL_PATH = os.path.join(PROJECT_ROOT, "数据/原始/每日现货.xlsx")
CLEAN_WIDE_CSV_PATH = os.path.join(PROJECT_ROOT, "数据/原始/每日现货_清洗规范版.csv")
PIT_LONG_CSV_PATH = os.path.join(PROJECT_ROOT, "数据/原始/每日现货_PIT明细.csv")

# 52 个列名对应的标准英文标识、变量ID、单位、分类、频度与口径说明字典
COLUMN_SPEC_MAP = {
    '中天螺纹': {
        'col_en': 'spot_hz_zhongtian', 'variable_id': 'S_HZ_ZT', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/市场采集',
        'scope': '杭州中天螺纹HRB400E 20mm理计现货价(主流贸易流动性基准)'
    },
    '中心库中天': {
        'col_en': 'spot_hz_zhongtian_warehouse', 'variable_id': 'S_HZ_ZT_WH', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/中心库报价',
        'scope': '杭州中天中心库自提价'
    },
    '萍钢螺纹': {
        'col_en': 'spot_hz_pinggang', 'variable_id': 'S_HZ_PG', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/市场采集',
        'scope': '杭州萍钢螺纹HRB400E 20mm现货价(二类主流)'
    },
    '富鑫螺纹': {
        'col_en': 'spot_hz_fuxin', 'variable_id': 'S_HZ_FX', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/市场采集',
        'scope': '杭州富鑫螺纹HRB400E现货价(民营调坯)'
    },
    '三类螺纹': {
        'col_en': 'spot_hz_tier3', 'variable_id': 'S_HZ_TIER3', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/市场采集',
        'scope': '杭州三类螺纹现货价(期货最便宜交割品CTD基准)'
    },
    '镔鑫195线材': {
        'col_en': 'spot_hz_binxin_wire', 'variable_id': 'S_HZ_BX_WIRE', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/市场采集',
        'scope': '杭州镔鑫Q195高线现货价'
    },
    '杭州中天盘螺': {
        'col_en': 'spot_hz_zhongtian_coil', 'variable_id': 'S_HZ_ZT_COIL', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/市场采集',
        'scope': '杭州中天盘螺HRB400E 8-10mm现货价'
    },
    '武钢盘螺': {
        'col_en': 'spot_hz_wugang_coil', 'variable_id': 'S_HZ_WG_COIL', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/市场采集',
        'scope': '杭州武钢盘螺现货价'
    },
    '三类盘螺': {
        'col_en': 'spot_hz_tier3_coil', 'variable_id': 'S_HZ_TIER3_COIL', 'unit': '元/吨',
        'category': '现货', 'freq': '日频', 'source': '用户现货记录/市场采集',
        'scope': '杭州三类盘螺现货价'
    },
    '全国成交量': {
        'col_en': 'flow_national_volume', 'variable_id': 'FLOW_NAT_VOL', 'unit': '万吨',
        'category': '微观流通', 'freq': '日频', 'source': '钢银/Mysteel主流贸易商样本',
        'scope': '全国主流贸易商建筑钢材日成交量'
    },
    '杭州出库': {
        'col_en': 'flow_hz_outflow', 'variable_id': 'FLOW_HZ_OUTFLOW', 'unit': '万吨',
        'category': '微观流通', 'freq': '日频', 'source': '杭州主要仓库统计',
        'scope': '杭州螺纹钢每日出库量(终端拉料与拿货高频指标)'
    },
    '杭州库存': {
        'col_en': 'inv_hz_stock', 'variable_id': 'INV_HZ_STOCK', 'unit': '万吨',
        'category': '库存', 'freq': '日频', 'source': '杭州主要仓库统计',
        'scope': '杭州螺纹钢仓库总库存'
    },
    '螺纹仓单(吨)': {
        'col_en': 'wh_receipt_rb', 'variable_id': 'WH_RB', 'unit': '吨',
        'category': '仓单', 'freq': '日频', 'source': '上期所官方发布',
        'scope': '上期所螺纹钢期货注册仓单'
    },
    '热卷仓单(吨)': {
        'col_en': 'wh_receipt_hc', 'variable_id': 'WH_HC', 'unit': '吨',
        'category': '仓单', 'freq': '日频', 'source': '上期所官方发布',
        'scope': '上期所热轧卷板期货注册仓单'
    },
    '铁矿仓单(吨)': {
        'col_en': 'wh_receipt_i', 'variable_id': 'WH_I', 'unit': '吨',
        'category': '仓单', 'freq': '日频', 'source': '大商所官方发布',
        'scope': '大商所铁矿石期货注册仓单'
    },
    '焦炭仓单(吨)': {
        'col_en': 'wh_receipt_j', 'variable_id': 'WH_J', 'unit': '吨',
        'category': '仓单', 'freq': '日频', 'source': '大商所官方发布',
        'scope': '大商所焦炭期货注册仓单'
    },
    '焦煤仓单(吨)': {
        'col_en': 'wh_receipt_jm', 'variable_id': 'WH_JM', 'unit': '吨',
        'category': '仓单', 'freq': '日频', 'source': '大商所官方发布',
        'scope': '大商所焦煤期货注册仓单'
    },
    '北京螺纹': {
        'col_en': 'spot_reg_bj_rb', 'variable_id': 'S_REG_BJ_RB', 'unit': '元/吨',
        'category': '跨区现货', 'freq': '日频', 'source': '市场采集',
        'scope': '北京螺纹钢HRB400E 20mm现货价'
    },
    '沈阳螺纹': {
        'col_en': 'spot_reg_sy_rb', 'variable_id': 'S_REG_SY_RB', 'unit': '元/吨',
        'category': '跨区现货', 'freq': '日频', 'source': '市场采集',
        'scope': '沈阳螺纹钢HRB400E 20mm现货价(北材南下核心源头)'
    },
    '山东螺纹': {
        'col_en': 'spot_reg_sd_rb', 'variable_id': 'S_REG_SD_RB', 'unit': '元/吨',
        'category': '跨区现货', 'freq': '日频', 'source': '市场采集',
        'scope': '山东济南螺纹钢HRB400E现货价'
    },
    '杭州螺纹': {
        'col_en': 'spot_reg_hz_rb', 'variable_id': 'S_REG_HZ_RB', 'unit': '元/吨',
        'category': '跨区现货', 'freq': '日频', 'source': '市场采集',
        'scope': '杭州螺纹钢HRB400E综合现货基准价'
    },
    '广州螺纹': {
        'col_en': 'spot_reg_gz_rb', 'variable_id': 'S_REG_GZ_RB', 'unit': '元/吨',
        'category': '跨区现货', 'freq': '日频', 'source': '市场采集',
        'scope': '广州螺纹钢HRB400E现货价(华南短流程密集区)'
    },
    '成都螺纹': {
        'col_en': 'spot_reg_cd_rb', 'variable_id': 'S_REG_CD_RB', 'unit': '元/吨',
        'category': '跨区现货', 'freq': '日频', 'source': '市场采集',
        'scope': '成都螺纹钢HRB400E现货价(西南水电短流程集聚区)'
    },
    '惠龙港螺纹': {
        'col_en': 'spot_port_hlg_rb', 'variable_id': 'S_PORT_HLG_RB', 'unit': '元/吨',
        'category': '码头现货', 'freq': '日频', 'source': '江苏惠龙港自提报价',
        'scope': '江苏惠龙港螺纹钢码头自提价(江海转运枢纽)'
    },
    '上海热卷': {
        'col_en': 'spot_reg_sh_hc', 'variable_id': 'S_REG_SH_HC', 'unit': '元/吨',
        'category': '跨区热卷', 'freq': '日频', 'source': '上海主流市场',
        'scope': '上海热轧卷板4.75mm普碳现货价'
    },
    '无锡热卷': {
        'col_en': 'spot_reg_wx_hc', 'variable_id': 'S_REG_WX_HC', 'unit': '元/吨',
        'category': '跨区热卷', 'freq': '日频', 'source': '无锡主流市场',
        'scope': '无锡热轧卷板4.75mm普碳现货价'
    },
    '乐从热卷': {
        'col_en': 'spot_reg_lc_hc', 'variable_id': 'S_REG_LC_HC', 'unit': '元/吨',
        'category': '跨区热卷', 'freq': '日频', 'source': '佛山乐从主流市场',
        'scope': '佛山乐从热轧卷板4.75mm现货价(华南制造集散地)'
    },
    '天津热卷': {
        'col_en': 'spot_reg_tj_hc', 'variable_id': 'S_REG_TJ_HC', 'unit': '元/吨',
        'category': '跨区热卷', 'freq': '日频', 'source': '天津主流市场',
        'scope': '天津热轧卷板4.75mm现货价(华北板材枢纽)'
    },
    '武汉热卷': {
        'col_en': 'spot_reg_wh_hc', 'variable_id': 'S_REG_WH_HC', 'unit': '元/吨',
        'category': '跨区热卷', 'freq': '日频', 'source': '武汉主流市场',
        'scope': '武汉热轧卷板4.75mm现货价(华中集散地)'
    },
    '沈阳热卷': {
        'col_en': 'spot_reg_sy_hc', 'variable_id': 'S_REG_SY_HC', 'unit': '元/吨',
        'category': '跨区热卷', 'freq': '日频', 'source': '沈阳主流市场',
        'scope': '沈阳热轧卷板4.75mm现货价(鞍本钢产地)'
    },
    '成都热卷': {
        'col_en': 'spot_reg_cd_hc', 'variable_id': 'S_REG_CD_HC', 'unit': '元/吨',
        'category': '跨区热卷', 'freq': '日频', 'source': '成都主流市场',
        'scope': '成都热轧卷板4.75mm现货价(西南板材枢纽)'
    },
    '重庆热卷': {
        'col_en': 'spot_reg_cq_hc', 'variable_id': 'S_REG_CQ_HC', 'unit': '元/吨',
        'category': '跨区热卷', 'freq': '日频', 'source': '重庆主流市场',
        'scope': '重庆热轧卷板4.75mm现货价(西南制造集散地)'
    },
    '华东长流程利润': {
        'col_en': 'profit_east_bf', 'variable_id': 'PROFIT_EAST_BF', 'unit': '元/吨',
        'category': '成本利润', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-华东长流程螺纹即期毛利'
    },
    '华东平电利润': {
        'col_en': 'profit_east_eaf_peak', 'variable_id': 'PROFIT_EAST_EAF_PEAK', 'unit': '元/吨',
        'category': '成本利润', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-华东独立电炉平电即期毛利(全天开工盈亏)'
    },
    '华东谷电利润': {
        'col_en': 'profit_east_eaf_valley', 'variable_id': 'PROFIT_EAST_EAF_VALLEY', 'unit': '元/吨',
        'category': '成本利润', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-华东独立电炉谷电即期毛利(夜间生产底线盈亏)'
    },
    '华东长流程成本': {
        'col_en': 'cost_east_bf', 'variable_id': 'COST_EAST_BF', 'unit': '元/吨',
        'category': '成本利润', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-华东长流程螺纹即期生产完全成本'
    },
    '华东平电成本': {
        'col_en': 'cost_east_eaf_peak', 'variable_id': 'COST_EAST_EAF_PEAK', 'unit': '元/吨',
        'category': '成本利润', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-华东短流程电炉平电生产成本(反弹压力位)'
    },
    '华东谷电成本': {
        'col_en': 'cost_east_eaf_valley', 'variable_id': 'COST_EAST_EAF_VALLEY', 'unit': '元/吨',
        'category': '成本利润', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-华东短流程电炉谷电生产成本(绝对铁底支撑位)'
    },
    '唐山方坯（含税）': {
        'col_en': 'spot_ts_billet', 'variable_id': 'S_TS_BILLET', 'unit': '元/吨',
        'category': '粗钢原料', 'freq': '日频', 'source': '唐山钢坯出厂价',
        'scope': '唐山普碳方坯含税出厂价(粗钢即期风向标)'
    },
    '青岛港61%PB粉湿吨': {
        'col_en': 'io_qd_pb_wet', 'variable_id': 'IO_QD_PB_WET', 'unit': '元/湿吨',
        'category': '铁矿现货', 'freq': '日频', 'source': '青岛港车板现货',
        'scope': '青岛港61%PB粉湿吨现货车板价'
    },
    '青岛港61%PB粉折干吨(扣水分8%)': {
        'col_en': 'io_qd_pb_dry', 'variable_id': 'IO_QD_PB_DRY', 'unit': '元/干吨',
        'category': '铁矿折干', 'freq': '日频', 'source': '大商所交割折算',
        'scope': '青岛港61%PB粉折干吨(扣水8%标准交割基准)'
    },
    '河北一级冶金焦湿熄': {
        'col_en': 'coke_hebei_wet', 'variable_id': 'J_HEBEI_WET', 'unit': '元/吨',
        'category': '焦炭现货', 'freq': '日频', 'source': '河北主流钢企采购价',
        'scope': '河北一级冶金焦湿熄出厂含税价'
    },
    '预期河北一级冶金焦湿熄': {
        'col_en': 'coke_hebei_wet_expected', 'variable_id': 'J_HEBEI_WET_EXP', 'unit': '元/吨',
        'category': '焦炭预期', 'freq': '日频', 'source': '市场提涨提降函预期',
        'scope': '预期河北一级冶金焦湿熄出厂价(提涨提降前导)'
    },
    '河北一级冶金焦折干熄(扣水分6%+30性能溢价)': {
        'col_en': 'coke_hebei_dry_equiv', 'variable_id': 'J_HEBEI_DRY_EQUIV', 'unit': '元/干吨',
        'category': '焦炭折干', 'freq': '日频', 'source': '大商所交割折算',
        'scope': '河北一级焦折干熄(扣水6%+30元溢价标准交割基准)'
    },
    '动力煤CCI5500': {
        'col_en': 'thermal_coal_cci5500', 'variable_id': 'TC_CCI5500', 'unit': '元/吨',
        'category': '煤焦原料', 'freq': '日频', 'source': '易煤网/CCI指数',
        'scope': '动力煤CCI5500北港平仓价'
    },
    '华东铁水成本': {
        'col_en': 'cost_east_hot_metal', 'variable_id': 'COST_EAST_HOT_METAL', 'unit': '元/吨',
        'category': '原料成本', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-华东高炉即期铁水成本(铁水全链条母体)'
    },
    '华东废钢≥6mm': {
        'col_en': 'scrap_east_6mm', 'variable_id': 'SCRAP_EAST_6MM', 'unit': '元/吨',
        'category': '废钢现货', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-华东重废≥6mm到厂含税/不含税基准'
    },
    '冷热轧打包料': {
        'col_en': 'scrap_packing_material', 'variable_id': 'SCRAP_PACKING', 'unit': '元/吨',
        'category': '废钢细分', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-冷热轧打包料到厂价'
    },
    '成品钢板料': {
        'col_en': 'scrap_plate_material', 'variable_id': 'SCRAP_PLATE', 'unit': '元/吨',
        'category': '废钢细分', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '富宝-成品钢板料到厂价'
    },
    '320样本钢厂废钢到货': {
        'col_en': 'scrap_320_arrival', 'variable_id': 'SCRAP_320_ARRIVAL', 'unit': '万吨/天',
        'category': '废钢供需', 'freq': '日频', 'source': '富宝资讯(FB)',
        'scope': '全国320家样本钢厂废钢日到货量'
    },
    '周度废钢日耗': {
        'col_en': 'scrap_weekly_daily_consumption', 'variable_id': 'SCRAP_WEEKLY_CONSUMPTION', 'unit': '万吨/天',
        'category': '废钢供需', 'freq': '周频', 'source': '富宝资讯(FB)',
        'scope': '全国重点钢厂废钢日耗周度跟踪'
    },
    '周度废钢库存': {
        'col_en': 'scrap_weekly_inventory', 'variable_id': 'SCRAP_WEEKLY_INVENTORY', 'unit': '万吨',
        'category': '废钢库存', 'freq': '周频', 'source': '富宝资讯(FB)',
        'scope': '全国重点钢厂废钢库存周度跟踪'
    }
}

def clean_and_ingest():
    print(f"[1/5] 读取原始数据文件: {RAW_EXCEL_PATH}")
    df = pd.read_excel(RAW_EXCEL_PATH)
    total_rows = len(df)
    print(f"  - 原始记录总行数: {total_rows}")

    # 1. 严格检查日期
    df['data_date'] = pd.to_datetime(df['日期'], errors='coerce')
    assert df['data_date'].isnull().sum() == 0, "存在无法解析的日期！"
    assert df['data_date'].is_monotonic_increasing, "日期非单调递增！"
    df['data_date_str'] = df['data_date'].dt.strftime('%Y-%m-%d')

    # 2. 修复已知的 4 处微观人工录入笔误并记录审计（按精确统计日期定位，具备防位移稳健性）
    audit_log = []
    
    # 笔误 1: 2019-05-20 杭州出库 4040.0 -> 4.04
    mask1 = (df['data_date_str'] == '2019-05-20') & (df['杭州出库'].astype(str).str.strip().isin(['4040', '4040.0']))
    if mask1.any():
        df.loc[mask1, '杭州出库'] = 4.04
        audit_log.append("Date 2019-05-20: 杭州出库 4040.0 -> 4.04 万吨 (修复漏打小数点笔误)")

    # 笔误 2: 2022-03-22 杭州出库 '2..3' -> 2.3
    mask2 = (df['data_date_str'] == '2022-03-22') & (df['杭州出库'].astype(str).str.strip() == '2..3')
    if mask2.any():
        df.loc[mask2, '杭州出库'] = 2.3
        audit_log.append("Date 2022-03-22: 杭州出库 '2..3' -> 2.3 万吨 (修复双小数点笔误)")

    # 笔误 3: 2025-05-27 杭州出库 '4..7' -> 4.7
    mask3 = (df['data_date_str'] == '2025-05-27') & (df['杭州出库'].astype(str).str.strip() == '4..7')
    if mask3.any():
        df.loc[mask3, '杭州出库'] = 4.7
        audit_log.append("Date 2025-05-27: 杭州出库 '4..7' -> 4.7 万吨 (修复双小数点笔误)")

    # 笔误 4: 2021-11-15 杭州库存 '39。9' -> 39.9
    mask4 = (df['data_date_str'] == '2021-11-15') & (df['杭州库存'].astype(str).str.strip().isin(['39。9', '39.9']))
    if mask4.any():
        df.loc[mask4, '杭州库存'] = 39.9
        audit_log.append("Date 2021-11-15: 杭州库存 '39。9' -> 39.9 万吨 (修复中文句号笔误)")

    print("[2/5] 异常清洗审计日志:")
    for log in audit_log:
        print(f"  * {log}")

    # 3. 构建清洗后的宽表 (Wide DataFrame)，始终存放最新权威数值 (以最新修改价格为准)
    wide_df = pd.DataFrame()
    wide_df['date'] = df['data_date_str']

    clean_stats = {}
    for col_cn, spec in COLUMN_SPEC_MAP.items():
        if col_cn in df.columns:
            # 清洗并强转 float64
            cleaned_series = pd.to_numeric(df[col_cn].astype(str).str.replace('。', '.', regex=False), errors='coerce')
            wide_df[spec['col_en']] = cleaned_series
            valid_cnt = cleaned_series.notnull().sum()
            clean_stats[col_cn] = {
                'col_en': spec['col_en'],
                'valid_cnt': valid_cnt,
                'min': cleaned_series.min() if valid_cnt > 0 else np.nan,
                'max': cleaned_series.max() if valid_cnt > 0 else np.nan,
                'mean': cleaned_series.mean() if valid_cnt > 0 else np.nan
            }
        else:
            print(f"  ! 警告: 原表未找到列: {col_cn}")

    wide_df.to_csv(CLEAN_WIDE_CSV_PATH, index=False, encoding='utf-8')
    print(f"[3/5] 成功导出清洗规范宽表: {CLEAN_WIDE_CSV_PATH}")
    print(f"  - 宽表尺寸: {wide_df.shape[0]} 行 x {wide_df.shape[1]} 列 (已完全吸收最新修订值)")

    # 4. 构建标准点时长表 (PIT Long Table) 并进行历史修正检测
    # 核心业务准则: 用户表格中最近几天的价格可能会修改，系统以最新修改为准，并按 PIT 契约生成修订版本链 (supersedes 旧记录)
    print("[4/5] 正在构建标准点时 (PIT) 明细库并执行版本修订检测...")
    
    existing_pit_records = []
    existing_latest_map = {}
    if os.path.exists(PIT_LONG_CSV_PATH):
        try:
            old_pit_df = pd.read_csv(PIT_LONG_CSV_PATH, low_memory=False)
            existing_pit_records = old_pit_df.to_dict('records')
            for rec in existing_pit_records:
                key = (rec['variable_id'], str(rec['data_date']))
                existing_latest_map[key] = rec
        except Exception as e:
            print(f"  ! 读取已有 PIT 文件失败，将全量重新构建: {e}")
            existing_pit_records = []
            existing_latest_map = {}

    pit_records = list(existing_pit_records)
    recorded_at_now = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    revision_audit_log = []
    new_records_count = 0
    new_revisions_count = 0

    for idx, row in df.iterrows():
        d_str = row['data_date_str']
        for col_cn, spec in COLUMN_SPEC_MAP.items():
            if col_cn not in df.columns:
                continue
            
            val = wide_df.loc[idx, spec['col_en']]
            if pd.isna(val):
                continue
            
            val_float = float(val)
            var_id = spec['variable_id']
            freq = spec['freq']
            
            if freq == '周频':
                pub_time = f"{d_str}T17:00:00+08:00"
                avail_time = f"{d_str}T17:00:00+08:00"
            elif 'flow' in spec['col_en']:
                pub_time = f"{d_str}T17:30:00+08:00"
                avail_time = f"{d_str}T17:30:00+08:00"
            else:
                pub_time = f"{d_str}T16:30:00+08:00"
                avail_time = f"{d_str}T16:30:00+08:00"

            key = (var_id, d_str)
            if key in existing_latest_map:
                old_rec = existing_latest_map[key]
                old_val = float(old_rec['value'])
                # 数值未修改，保留原历史记录
                if np.isclose(old_val, val_float, rtol=1e-5, atol=1e-5):
                    continue
                else:
                    # 发现价格修正！按照 PIT 契约追加增量修订行
                    old_rev = str(old_rec.get('revision_id', 'REV_0'))
                    try:
                        rev_num = int(old_rev.replace('REV_', '')) + 1
                    except Exception:
                        rev_num = 1
                    
                    new_rev_id = f"REV_{rev_num}"
                    obs_id = f"OBS_PROPRIETARY_{var_id}_{d_str.replace('-', '')}_{new_rev_id}"
                    supersedes_id = old_rec['observation_id']
                    
                    rec = {
                        'observation_id': obs_id,
                        'variable_id': var_id,
                        'data_date': d_str,
                        'period_start': d_str,
                        'period_end': d_str,
                        'source_published_at': recorded_at_now,
                        'first_seen_at': recorded_at_now,
                        'available_date': recorded_at_now,
                        'recorded_at': recorded_at_now,
                        'availability_basis': 'OFFICIAL_DAILY_TRADING_LOG',
                        'information_set_mode': 'PROPRIETARY_SPOT_PIT',
                        'value': val_float,
                        'unit': spec['unit'],
                        'source': spec['source'],
                        'source_ref': f"每日现货.xlsx:{col_cn}",
                        'frequency': spec['freq'],
                        'scope': spec['scope'],
                        'contract': '',
                        'revision_id': new_rev_id,
                        'supersedes': supersedes_id,
                        'quality_flag': 'VALID',
                        'note': f"自有现货事后价格修正:{col_cn} (原值:{old_val:.2f} -> 最新值:{val_float:.2f})"
                    }
                    pit_records.append(rec)
                    existing_latest_map[key] = rec
                    new_revisions_count += 1
                    revision_audit_log.append(f"[{d_str}] {col_cn} ({var_id}): 原值 {old_val} -> 最新修订值 {val_float} ({new_rev_id})")
            else:
                # 全新观测记录
                obs_id = f"OBS_PROPRIETARY_{var_id}_{d_str.replace('-', '')}"
                rec = {
                    'observation_id': obs_id,
                    'variable_id': var_id,
                    'data_date': d_str,
                    'period_start': d_str,
                    'period_end': d_str,
                    'source_published_at': pub_time,
                    'first_seen_at': pub_time,
                    'available_date': avail_time,
                    'recorded_at': recorded_at_now,
                    'availability_basis': 'OFFICIAL_DAILY_TRADING_LOG',
                    'information_set_mode': 'PROPRIETARY_SPOT_PIT',
                    'value': val_float,
                    'unit': spec['unit'],
                    'source': spec['source'],
                    'source_ref': f"每日现货.xlsx:{col_cn}",
                    'frequency': spec['freq'],
                    'scope': spec['scope'],
                    'contract': '',
                    'revision_id': 'REV_0',
                    'supersedes': '',
                    'quality_flag': 'VALID',
                    'note': f"自有现货高频事实:{col_cn}"
                }
                pit_records.append(rec)
                existing_latest_map[key] = rec
                new_records_count += 1

    pit_df = pd.DataFrame(pit_records)
    pit_df.to_csv(PIT_LONG_CSV_PATH, index=False, encoding='utf-8')
    print(f"[5/5] 成功导出标准点时明细库: {PIT_LONG_CSV_PATH}")
    print(f"  - 点时明细库总记录数: {len(pit_df)} 条 (新增初始观测: {new_records_count} 条, 价格修正记录: {new_revisions_count} 条)")
    if revision_audit_log:
        print("  * 历史价格修订审计记录 (以最新修改为准):")
        for rev_log in revision_audit_log:
            print(f"    -> {rev_log}")

    # 输出清洗后部分核心字段总结
    print("\n=== 核心高频字段清洗入库验收统计 (最新值) ===")
    summary_cols = ['中天螺纹', '三类螺纹', '杭州出库', '杭州库存', '全国成交量', '华东长流程成本', '华东平电成本', '华东谷电成本', '华东铁水成本', '华东废钢≥6mm', '320样本钢厂废钢到货', '唐山方坯（含税）']
    for c in summary_cols:
        st = clean_stats.get(c, {})
        print(f"  * {c:20s} ({st.get('col_en', ''):25s}): 有效 {st.get('valid_cnt', 0):4d} 条 | 均值: {st.get('mean', np.nan):8.2f} | 范围: [{st.get('min', np.nan):.2f}, {st.get('max', np.nan):.2f}]")

    return new_records_count, new_revisions_count

def update_all():
    """一键执行清洗入库、微观特征衍生与期现基差套利联动计算全流程"""
    print("==================================================")
    print(">>> 启动现货数据全流程自动化更新与联动计算管道 <<<")
    print("==================================================")
    clean_and_ingest()
    
    print("\n>>> 正在联动刷新下游微观现货衍生指标库...")
    sys.path.insert(0, os.path.join(PROJECT_ROOT, "scripts"))
    from compute_hangzhou_spot_features import compute_features
    compute_features()

    print("\n>>> 正在联动刷新期现基差与持仓套利指标库...")
    from compute_futures_derived_features import compute_futures_features
    compute_futures_features()
    
    print("\n>>> 全流程更新与最新指标计算完成！<<<")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--all":
        update_all()
    else:
        clean_and_ingest()

