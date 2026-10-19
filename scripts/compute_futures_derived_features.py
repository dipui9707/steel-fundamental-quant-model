#!/usr/bin/env python3
"""
高频期货衍生指标与多维基差特征计算管道
数据源:
  1. 标准化期货日线数据 (数据/原始/期货合约全量日线/standardized/)
  2. 标准化现货宽表 (数据/原始/每日现货_清洗规范版.csv)
输出目标:
  数据/加工/加工指标.csv (增量写入并去重)
"""

import os
import sys
import datetime
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
PROCESSED_CSV_PATH = BASE_DIR / "数据" / "加工" / "加工指标.csv"
SPOT_CSV_PATH = BASE_DIR / "数据" / "原始" / "每日现货_清洗规范版.csv"

# 引入已验证的 futures_data_loader
sys.path.insert(0, str(BASE_DIR))
from scripts.futures_data_loader import (
    load_symbol_data,
    get_continuous_main,
    get_market_aggregate,
    get_active_calendar_spread,
    SYMBOL_SPECS
)


def compute_futures_features(target_date: str = None, start_date: str = None):
    mode_str = f"增量模式 (目标日: {target_date})" if target_date else (f"区间模式 (>={start_date})" if start_date else "全量模式 (2016-2026)")
    print(f"[1/5] 读取期货连续主力与全市场总量数据 [{mode_str}]...")
    rb_m = get_continuous_main("rb").set_index("date")
    hc_m = get_continuous_main("hc").set_index("date")
    i_m = get_continuous_main("i").set_index("date")
    j_m = get_continuous_main("j").set_index("date")
    jm_m = get_continuous_main("jm").set_index("date")

    # 1. 跨品种盘面价差与比价
    print("[2/5] 计算跨品种盘面价差与虚拟钢厂毛利...")
    cross_df = pd.DataFrame(index=rb_m.index)
    cross_df["rb_close"] = rb_m["close"]
    cross_df["hc_close"] = hc_m["close"]
    cross_df["i_close"] = i_m["close"]
    cross_df["j_close"] = j_m["close"]
    cross_df["jm_close"] = jm_m["close"]

    # 华东盘面卷螺差: HC主力 - RB主力
    cross_df["SPREAD_FUT_HC_RB"] = cross_df["hc_close"] - cross_df["rb_close"]
    # 螺矿比: RB主力 / I主力
    cross_df["RATIO_RB_I"] = (cross_df["rb_close"] / cross_df["i_close"]).round(4)
    # 焦矿比: J主力 / I主力
    cross_df["RATIO_J_I"] = (cross_df["j_close"] / cross_df["i_close"]).round(4)
    # 盘面虚拟钢厂毛利: RB - 1.6*I - 0.5*J - 1200 (吨钢盘面毛利，扣除1200元/吨生铁冶炼/炼钢连铸/辅料折旧动力等制造杂费)
    cross_df["VIRTUAL_STEEL_MARGIN"] = (cross_df["rb_close"] - 1.6 * cross_df["i_close"] - 0.5 * cross_df["j_close"] - 1200.0).round(2)

    # 2. 黑色五品种全市场沉淀资金 (亿元)
    print("[3/5] 计算黑色五品种全市场沉淀资金...")
    for sym in ["rb", "hc", "i", "j", "jm"]:
        agg = get_market_aggregate(sym).set_index("date")
        cross_df[f"CAPITAL_{sym.upper()}"] = agg["sedimentation_capital_cny_yi"]

    # 3. 螺纹跨期价差与展期收益率
    print("[4/5] 计算螺纹期限结构与展期收益率...")
    rb_spread = get_active_calendar_spread("rb").set_index("date")
    cross_df["RB_SPREAD_TOP2"] = rb_spread["spread"]
    cross_df["RB_ROLL_YIELD_ANNUAL"] = (rb_spread["roll_yield_annual"] * 100).round(4) # 转换为百分比 %

    # 4. 结合杭州现货计算多维基差与期现纯资金利息成本
    print("[5/5] 结合杭州现货宽表计算双轨基差与期现无风险套利空间...")
    if SPOT_CSV_PATH.exists():
        spot_df = pd.read_csv(SPOT_CSV_PATH).set_index("date")
        merged = cross_df.join(spot_df[["spot_hz_zhongtian", "spot_hz_tier3"]], how="inner")
        
        # 贸易流动性基差: 杭州中天 - RB主力收盘
        merged["BASIS_ZHONGTIAN_MAIN"] = merged["spot_hz_zhongtian"] - merged["rb_close"]
        # CTD交割基差: 杭州三类 - RB主力收盘
        merged["BASIS_TIER3_MAIN"] = merged["spot_hz_tier3"] - merged["rb_close"]

        # 匹配主力合约的交割到期日
        rb_all = load_symbol_data("rb")
        specific_rb = rb_all[rb_all["contract_type"] == "SPECIFIC"][["date", "contract_code", "close", "open_interest"]]
        main_rb = rb_all[rb_all["contract_type"] == "MAIN"][["date", "close", "open_interest"]]
        
        # 找出每日主力的具体 contract_code
        matched_active = pd.merge(main_rb, specific_rb, on=["date", "close", "open_interest"], how="left").drop_duplicates("date").set_index("date")
        merged["active_contract"] = matched_active["contract_code"]

        def calc_days_to_delivery(row):
            code = row.get("active_contract")
            dt_str = row.name
            if not code or pd.isna(code) or len(str(code)) != 4:
                return np.nan
            try:
                y = int("20" + str(code)[:2])
                m = int(str(code)[2:])
                delivery_dt = datetime.date(y, m, 15)
                cur_dt = datetime.date.fromisoformat(dt_str)
                days = (delivery_dt - cur_dt).days
                return max(0, days)
            except Exception:
                return np.nan

        merged["DAYS_TO_DELIVERY"] = merged.apply(calc_days_to_delivery, axis=1)
        
        # 用户明确约定: 纯按 6% 年化资金利息计算，不计仓储与其他杂费
        # 资金利息成本 = CTD三类现货 * 0.06 * (交割剩余天数 / 365)
        merged["CARRY_TOTAL_COST"] = (merged["spot_hz_tier3"] * 0.06 * (merged["DAYS_TO_DELIVERY"] / 365.0)).round(2)
        # 期现正套净利润 = RB主力收盘 - CTD三类现货 - 纯资金利息成本
        merged["NET_CASH_CARRY_MARGIN"] = (merged["rb_close"] - merged["spot_hz_tier3"] - merged["CARRY_TOTAL_COST"]).round(2)
    else:
        merged = cross_df

    # 5. 特征元数据配置
    feature_meta = {
        "SPREAD_FUT_HC_RB": {"unit": "元/吨", "freq": "日频", "desc": "华东卷螺盘面差(HC主力-RB主力收盘)"},
        "RATIO_RB_I": {"unit": "比值", "freq": "日频", "desc": "螺矿比(RB主力收盘/I主力收盘)"},
        "RATIO_J_I": {"unit": "比值", "freq": "日频", "desc": "焦矿比(J主力收盘/I主力收盘)"},
        "VIRTUAL_STEEL_MARGIN": {"unit": "元/吨", "freq": "日频", "desc": "盘面虚拟钢厂毛利(RB-1.6*I-0.5*J-1200加工制造杂费)"},
        "CAPITAL_RB": {"unit": "亿元", "freq": "日频", "desc": "螺纹全市场沉淀资金(总持仓*结算价*10*8%)"},
        "CAPITAL_HC": {"unit": "亿元", "freq": "日频", "desc": "热卷全市场沉淀资金(总持仓*结算价*10*8%)"},
        "CAPITAL_I": {"unit": "亿元", "freq": "日频", "desc": "铁矿全市场沉淀资金(总持仓*结算价*100*12%)"},
        "CAPITAL_J": {"unit": "亿元", "freq": "日频", "desc": "焦炭全市场沉淀资金(总持仓*结算价*100*15%)"},
        "CAPITAL_JM": {"unit": "亿元", "freq": "日频", "desc": "焦煤全市场沉淀资金(总持仓*结算价*60*15%)"},
        "RB_SPREAD_TOP2": {"unit": "元/吨", "freq": "日频", "desc": "螺纹主力与次主力价差(近月-远月)"},
        "RB_ROLL_YIELD_ANNUAL": {"unit": "%", "freq": "日频", "desc": "螺纹主力与次主力年化展期收益率"},
        "BASIS_ZHONGTIAN_MAIN": {"unit": "元/吨", "freq": "日频", "desc": "杭州中天现货基差(中天-RB主力收盘,贸易流动性基差)"},
        "BASIS_TIER3_MAIN": {"unit": "元/吨", "freq": "日频", "desc": "杭州三类现货基差(三类-RB主力收盘,CTD交割基差)"},
        "DAYS_TO_DELIVERY": {"unit": "天", "freq": "日频", "desc": "螺纹主力合约距离15日交割日剩余自然日"},
        "CARRY_TOTAL_COST": {"unit": "元/吨", "freq": "日频", "desc": "螺纹纯资金利息持仓成本(CTD三类*6%*天数/365)"},
        "NET_CASH_CARRY_MARGIN": {"unit": "元/吨", "freq": "日频", "desc": "螺纹期现正套净利润(主力收盘-CTD三类-资金利息)"},
    }

    # 6. 打包标准化行
    now_iso = datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8))).isoformat()
    new_rows = []

    for feat_id, meta in feature_meta.items():
        if feat_id not in merged.columns:
            continue
        valid_series = merged[feat_id].dropna()
        if target_date:
            valid_series = valid_series[valid_series.index == str(target_date)]
        elif start_date:
            valid_series = valid_series[valid_series.index >= str(start_date)]

        for dt_str, val in valid_series.items():
            dt_clean = str(dt_str)
            input_obs = f"OBS_FUT_*_{dt_clean.replace('-', '')}"
            if "BASIS" in feat_id or "CARRY" in feat_id or "DELIVERY" in feat_id:
                input_obs += f";OBS_PROPRIETARY_*_{dt_clean.replace('-', '')}"
                
            new_rows.append({
                "feature_id": feat_id,
                "calc_id": f"CALC_{feat_id}_{dt_clean.replace('-', '')}",
                "data_date": dt_clean,
                "value": round(float(val), 4),
                "unit": meta["unit"],
                "frequency": meta["freq"],
                "input_observation_ids": input_obs,
                "calc_rule_version": "V1.0_FUTURES_DERIVED",
                "calculated_at": now_iso,
                "note": meta["desc"],
                "quality_flag": "VALID"
            })

    new_df = pd.DataFrame(new_rows)
    print(f"生成的衍生期货指标记录数: {len(new_df)} 条")

    # 7. 合并落盘
    existing_processed = pd.read_csv(PROCESSED_CSV_PATH) if PROCESSED_CSV_PATH.exists() else pd.DataFrame()
    print(f"已有加工指标记录数: {len(existing_processed)} 条")

    if len(existing_processed) > 0 and len(new_df) > 0:
        if target_date:
            # 增量模式: 移除同日期同指标旧记录后快速拼接
            mask = (existing_processed["data_date"] == str(target_date)) & (existing_processed["feature_id"].isin(new_df["feature_id"]))
            existing_processed = existing_processed[~mask]
            combined_df = pd.concat([existing_processed, new_df], ignore_index=True)
        else:
            combined_df = pd.concat([existing_processed, new_df], ignore_index=True)
            combined_df = combined_df.drop_duplicates(subset=["feature_id", "data_date"], keep="last")
    elif len(new_df) > 0:
        combined_df = new_df
    else:
        combined_df = existing_processed

    combined_df.to_csv(PROCESSED_CSV_PATH, index=False, encoding="utf-8")
    print(f"成功落盘更新加工指标库: {PROCESSED_CSV_PATH}，更新后总记录数: {len(combined_df)} 条")

    # 抽样打印最新 2026-09-18 数据
    sample_date = "2026-09-18"
    if sample_date in merged.index:
        r = merged.loc[sample_date]
        print(f"\n=== 2026-09-18 衍生指标计算抽样 ===")
        print(f"华东卷螺盘面差: {r['SPREAD_FUT_HC_RB']} 元/吨")
        print(f"螺矿比: {r['RATIO_RB_I']} | 焦矿比: {r['RATIO_J_I']}")
        print(f"虚拟钢厂毛利: {r['VIRTUAL_STEEL_MARGIN']} 元/吨")
        print(f"螺纹全市场沉淀资金: {r['CAPITAL_RB']} 亿元 | 热卷: {r['CAPITAL_HC']} 亿元 | 铁矿: {r['CAPITAL_I']} 亿元")
        print(f"主力合约: {r.get('active_contract')} | 剩余交割天数: {r.get('DAYS_TO_DELIVERY')} 天")
        print(f"杭州三类现货: {r.get('spot_hz_tier3')} 元/吨 | RB主力收盘: {r.get('rb_close')} 元/吨")
        print(f"CTD交割基差: {r.get('BASIS_TIER3_MAIN')} 元/吨")
        print(f"纯资金利息成本(6%): {r.get('CARRY_TOTAL_COST')} 元/吨")
        print(f"期现正套净利润: {r.get('NET_CASH_CARRY_MARGIN')} 元/吨")


if __name__ == "__main__":
    compute_futures_features()
