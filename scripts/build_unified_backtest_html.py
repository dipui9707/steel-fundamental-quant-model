#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成多版本合一历史回测演进与对比统一交互式 HTML 报告 (Unified Multi-Version Backtest Dashboard)

设计原则与用户核心诉求：
1. 【多版本合一】：将 v0.3、v0.4、v0.5、v0.6、v0.7、v0.8、v0.9、v0.10、v0.11、v0.12、v0.13、v0.14、v0.15 全部集成在同一个 HTML 文件中；
2. 【默认展示最新】：默认直接展示最新一版（当前为 v0.15 单边钝化转跨期互锁松绑终极版 vs v0.14 跨期对冲初始版）；
3. 【历史版本隐藏切换】：历史版本（v0.14 vs v0.13、v0.13 vs v0.12、v0.12 vs v0.11、v0.11 vs v0.10、v0.10 vs v0.9、v0.9 vs v0.8、v0.8 vs v0.7、v0.7 vs v0.6、v0.6 vs v0.5、v0.5 vs v0.4、v0.4 vs v0.3、全版本进化矩阵）默认隐藏，通过顶部版本导航栏一键切换查看；
4. 【同文件持续演进】：后续新版本自动成为默认展示版本，历史版本自动归入隐藏导航。
"""

import json
import math
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]

# 各版本实验存档路径
PATH_V3 = ROOT / "研究/回测实验/20261011T031836Z_cost_push_91600be1"
PATH_V4 = ROOT / "研究/回测实验/20261011T040257Z_cost_push_f775e68b"
PATH_V5 = ROOT / "研究/回测实验/20261011T061702Z_cost_push_9e026696"
PATH_V6 = ROOT / "研究/回测实验/20261011T085221Z_cost_push_ac68dcfd"
PATH_V7 = ROOT / "研究/回测实验/20261011T151237Z_cost_push_195bbe84"
PATH_V8 = ROOT / "研究/回测实验/20261011T164900Z_cost_push_46b9325c"
PATH_V9 = ROOT / "研究/回测实验/20261012T061841Z_cost_push_4c581102"
PATH_V10 = ROOT / "研究/回测实验/20261018T041633Z_cost_push_934f6354"
PATH_V11 = ROOT / "研究/回测实验/20261018T050654Z_cost_push_ea856cff"
PATH_V12 = ROOT / "研究/回测实验/20261018T072230Z_cost_push_6b37bc38"
PATH_V13 = ROOT / "研究/回测实验/20261018T090645Z_cost_push_ebfe5d7d"
PATH_V14 = ROOT / "研究/回测实验/20261018T102111Z_cost_push_ff20a48b"
PATH_V15 = ROOT / "研究/回测实验/20261018T120708Z_cost_push_5e5f2202"

def json_default_converter(o):
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.floating, float)):
        return float(o)
    if isinstance(o, (np.integer, int)):
        return int(o)
    return str(o)

def extract_trade_episodes(exp_path, label):
    """从 equity 与 decisions 中抽取完整波段持仓交易周期 (Episodes)"""
    eq = pd.read_parquet(f"{exp_path}/BASELINE_equity.parquet").set_index("date")
    dec = pd.read_parquet(f"{exp_path}/BASELINE_decisions.parquet").set_index("date")
    
    trades = []
    current_tr = None
    
    for i, (d, row) in enumerate(eq.iterrows()):
        lots = int(row["lots"])
        c = float(row["close_price"])
        o = float(row["open_price"])
        eq_val = float(row["total_equity"])
        dir_val = "LONG" if lots > 0 else ("SHORT" if lots < 0 else "FLAT")
        dec_row = dec.loc[d] if d in dec.index else {}
        driver = str(dec_row.get("entry_driver", row.get("execution_driver", "")))
        rationale = str(dec_row.get("signal_rationale", dec_row.get("rationale", "")))
        is_spread = bool(row.get("is_spread_position", False))
        spread_type = str(row.get("spread_type", ""))
        
        driver_clean = "基本面供需"
        if is_spread:
            if spread_type == "BEAR_SPREAD":
                driver_clean = "跨期反套 (卖近买远)"
            elif spread_type == "BULL_SPREAD":
                driver_clean = "跨期正套 (买近卖远)"
            else:
                driver_clean = "跨期套利对冲"
        elif "COST_COLLAPSE" in driver or "成本坍塌" in rationale or "负反馈" in rationale:
            driver_clean = "成本坍塌/原料负反馈破位"
        elif "COST_EXPECTATION" in driver or "BULL_PULLBACK_ON_COST" in driver or "成本" in rationale or "COST_PUSH" in driver:
            driver_clean = "成本推升/原料逼空"
        elif "HIGH_MARGIN_BULL" in driver or "高毛利" in rationale:
            driver_clean = "高毛利牛市顺势"
        elif "INVENTORY" in driver or "累库" in rationale:
            driver_clean = "库存异动驱动"
        elif "MOMENTUM" in driver:
            driver_clean = "右侧技术动量"
            
        if current_tr is None:
            if dir_val != "FLAT":
                prev_eq = eq.iloc[i-1]["total_equity"] if i > 0 else eq_val
                current_tr = {
                    "id": f"{label}_T{len(trades)+1:03d}",
                    "strategy": label,
                    "direction": dir_val,
                    "entry_date": d,
                    "entry_price": o,
                    "exit_date": d,
                    "exit_price": c,
                    "entry_lots": abs(lots),
                    "max_lots": abs(lots),
                    "start_equity": prev_eq,
                    "end_equity": eq_val,
                    "entry_driver": driver_clean,
                    "entry_rationale": rationale[:60] if rationale else "",
                    "holding_days": 1,
                    "dates": [d]
                }
        else:
            if dir_val == current_tr["direction"]:
                current_tr["exit_date"] = d
                current_tr["exit_price"] = c
                current_tr["max_lots"] = max(current_tr["max_lots"], abs(lots))
                current_tr["end_equity"] = eq_val
                current_tr["holding_days"] += 1
                current_tr["dates"].append(d)
            elif dir_val == "FLAT":
                current_tr["exit_date"] = d
                current_tr["exit_price"] = o
                current_tr["end_equity"] = eq_val
                current_tr["holding_days"] += 1
                current_tr["dates"].append(d)
                
                # 结算本笔交易
                current_tr["pnl"] = current_tr["end_equity"] - current_tr["start_equity"]
                current_tr["pnl_wan"] = round(current_tr["pnl"] / 10000, 1)
                current_tr["ret_pct"] = round((current_tr["end_equity"] / current_tr["start_equity"] - 1) * 100, 2)
                current_tr["is_win"] = current_tr["pnl"] > 0
                current_tr["is_counter"] = not current_tr["is_win"]
                
                exit_reason = (
                    str(row.get("tactical_exit_reason", ""))
                    or str(dec_row.get("exit_reason", ""))
                    or str(row.get("execution_exit_reason", ""))
                )
                if "SPREAD" in exit_reason or "CALENDAR" in exit_reason or "DTE" in exit_reason:
                    current_tr["exit_reason"] = "跨期价差止盈/到期退出"
                elif "SPOT" in exit_reason or "现货突破" in exit_reason:
                    current_tr["exit_reason"] = "现货量价破位微观止损"
                elif "UNLOCKED" in exit_reason or "钝化" in exit_reason:
                    current_tr["exit_reason"] = "单边钝化平滑转跨期套利"
                elif "INITIAL" in exit_reason or "假突破" in exit_reason:
                    current_tr["exit_reason"] = "初期突破结构防守止损"
                elif "PIVOT" in exit_reason or "拐点" in exit_reason:
                    current_tr["exit_reason"] = "动能衰竭波段全平"
                elif "GAP" in exit_reason or "跳空" in exit_reason:
                    current_tr["exit_reason"] = "跳空动能衰竭退出"
                elif "CHOPPY" in exit_reason or "震荡" in exit_reason:
                    current_tr["exit_reason"] = "震荡假突破敏捷退出"
                elif "REVERSE" in exit_reason or "反转" in exit_reason:
                    current_tr["exit_reason"] = "信号反转清盘"
                elif "FIREWALL" in exit_reason or "熔断" in exit_reason or "防火墙" in exit_reason:
                    current_tr["exit_reason"] = "风控防火墙否决"
                elif "STOP" in exit_reason or "止损" in exit_reason:
                    current_tr["exit_reason"] = "触发移动跟踪止损"
                elif "TAKE_PROFIT" in exit_reason or "止盈" in exit_reason:
                    current_tr["exit_reason"] = "右侧企稳止盈"
                else:
                    current_tr["exit_reason"] = "宏观/战术规则平仓"
                    
                current_tr["type"] = ("WIN_" if current_tr["is_win"] else "LOSS_") + current_tr["direction"]
                current_tr["tag"] = ("做对·" if current_tr["is_win"] else "做错·") + current_tr["direction"]
                trades.append(current_tr)
                current_tr = None
            else:
                # 反向开仓
                current_tr["exit_date"] = d
                current_tr["exit_price"] = o
                current_tr["end_equity"] = eq_val
                current_tr["holding_days"] += 1
                current_tr["dates"].append(d)
                current_tr["pnl"] = current_tr["end_equity"] - current_tr["start_equity"]
                current_tr["pnl_wan"] = round(current_tr["pnl"] / 10000, 1)
                current_tr["ret_pct"] = round((current_tr["end_equity"] / current_tr["start_equity"] - 1) * 100, 2)
                current_tr["is_win"] = current_tr["pnl"] > 0
                current_tr["is_counter"] = not current_tr["is_win"]
                current_tr["exit_reason"] = "反向调仓平仓"
                current_tr["type"] = ("WIN_" if current_tr["is_win"] else "LOSS_") + current_tr["direction"]
                current_tr["tag"] = ("做对·" if current_tr["is_win"] else "做错·") + current_tr["direction"]
                trades.append(current_tr)
                
                # 新起反向单
                current_tr = {
                    "id": f"{label}_T{len(trades)+1:03d}",
                    "strategy": label,
                    "direction": dir_val,
                    "entry_date": d,
                    "entry_price": o,
                    "exit_date": d,
                    "exit_price": c,
                    "entry_lots": abs(lots),
                    "max_lots": abs(lots),
                    "start_equity": eq_val,
                    "end_equity": eq_val,
                    "entry_driver": driver_clean,
                    "entry_rationale": rationale[:60] if rationale else "",
                    "holding_days": 1,
                    "dates": [d]
                }

    if current_tr is not None:
        current_tr["pnl"] = current_tr["end_equity"] - current_tr["start_equity"]
        current_tr["pnl_wan"] = round(current_tr["pnl"] / 10000, 1)
        current_tr["ret_pct"] = round((current_tr["end_equity"] / current_tr["start_equity"] - 1) * 100, 2)
        current_tr["is_win"] = current_tr["pnl"] > 0
        current_tr["is_counter"] = not current_tr["is_win"]
        current_tr["exit_reason"] = "回测期末平仓"
        current_tr["type"] = ("WIN_" if current_tr["is_win"] else "LOSS_") + current_tr["direction"]
        current_tr["tag"] = ("做对·" if current_tr["is_win"] else "做错·") + current_tr["direction"]
        trades.append(current_tr)
        
    return trades

def load_all_versions_data():
    """全量加载 v0.3 ~ v0.15 全十三代版本的回测事实与明细"""
    feat = pd.read_parquet(PATH_V15 / "features.parquet")
    dates = list(feat.index)
    
    # 净值序列
    eq_v3 = pd.read_parquet(PATH_V3 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v4 = pd.read_parquet(PATH_V4 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v5 = pd.read_parquet(PATH_V5 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v6 = pd.read_parquet(PATH_V6 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v7 = pd.read_parquet(PATH_V7 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v8 = pd.read_parquet(PATH_V8 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v9 = pd.read_parquet(PATH_V9 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v10 = pd.read_parquet(PATH_V10 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v11 = pd.read_parquet(PATH_V11 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v12 = pd.read_parquet(PATH_V12 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v13 = pd.read_parquet(PATH_V13 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v14 = pd.read_parquet(PATH_V14 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    eq_v15 = pd.read_parquet(PATH_V15 / "BASELINE_equity.parquet").set_index("date")["total_equity"]
    
    # 决策序列
    dec_v9 = pd.read_parquet(PATH_V9 / "BASELINE_decisions.parquet").set_index("date")
    dec_v10 = pd.read_parquet(PATH_V10 / "BASELINE_decisions.parquet").set_index("date")
    dec_v11 = pd.read_parquet(PATH_V11 / "BASELINE_decisions.parquet").set_index("date")
    dec_v12 = pd.read_parquet(PATH_V12 / "BASELINE_decisions.parquet").set_index("date")
    dec_v13 = pd.read_parquet(PATH_V13 / "BASELINE_decisions.parquet").set_index("date")
    dec_v14 = pd.read_parquet(PATH_V14 / "BASELINE_decisions.parquet").set_index("date")
    dec_v15 = pd.read_parquet(PATH_V15 / "BASELINE_decisions.parquet").set_index("date")
    
    # 核心绩效对比
    comp_v3 = pd.read_csv(PATH_V3 / "comparison.csv").iloc[0].to_dict()
    comp_v4 = pd.read_csv(PATH_V4 / "comparison.csv").iloc[0].to_dict()
    comp_v5 = pd.read_csv(PATH_V5 / "comparison.csv").iloc[0].to_dict()
    comp_v6 = pd.read_csv(PATH_V6 / "comparison.csv").iloc[0].to_dict()
    comp_v7 = pd.read_csv(PATH_V7 / "comparison.csv").iloc[0].to_dict()
    comp_v8 = pd.read_csv(PATH_V8 / "comparison.csv").iloc[0].to_dict()
    comp_v9 = pd.read_csv(PATH_V9 / "comparison.csv").iloc[0].to_dict()
    comp_v10 = pd.read_csv(PATH_V10 / "comparison.csv").iloc[0].to_dict()
    comp_v11 = pd.read_csv(PATH_V11 / "comparison.csv").iloc[0].to_dict()
    comp_v12 = pd.read_csv(PATH_V12 / "comparison.csv").iloc[0].to_dict()
    comp_v13 = pd.read_csv(PATH_V13 / "comparison.csv").iloc[0].to_dict()
    comp_v14 = pd.read_csv(PATH_V14 / "comparison.csv").iloc[0].to_dict()
    comp_v15 = pd.read_csv(PATH_V15 / "comparison.csv").iloc[0].to_dict()
    
    # 年度切片
    y3 = pd.read_csv(PATH_V3 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y4 = pd.read_csv(PATH_V4 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y5 = pd.read_csv(PATH_V5 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y6 = pd.read_csv(PATH_V6 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y7 = pd.read_csv(PATH_V7 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y8 = pd.read_csv(PATH_V8 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y9 = pd.read_csv(PATH_V9 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y10 = pd.read_csv(PATH_V10 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y11 = pd.read_csv(PATH_V11 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y12 = pd.read_csv(PATH_V12 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y13 = pd.read_csv(PATH_V13 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y14 = pd.read_csv(PATH_V14 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()
    y15 = pd.read_csv(PATH_V15 / "year_blocks.csv").query("strategy == 'BASELINE'").set_index("year")["return_pct"].to_dict()

    # 提取波段持仓交易
    trades_v15 = extract_trade_episodes(PATH_V15, "v0.15")
    trades_v14 = extract_trade_episodes(PATH_V14, "v0.14")
    trades_v13 = extract_trade_episodes(PATH_V13, "v0.13")
    trades_v12 = extract_trade_episodes(PATH_V12, "v0.12")
    trades_v11 = extract_trade_episodes(PATH_V11, "v0.11")
    trades_v10 = extract_trade_episodes(PATH_V10, "v0.10")
    trades_v9 = extract_trade_episodes(PATH_V9, "v0.9")
    trades_v8 = extract_trade_episodes(PATH_V8, "v0.8")

    # 日期字典映射
    t10_by_date = {d: t for t in trades_v10 for d in t["dates"]}
    t11_by_date = {d: t for t in trades_v11 for d in t["dates"]}
    t12_by_date = {d: t for t in trades_v12 for d in t["dates"]}
    t13_by_date = {d: t for t in trades_v13 for d in t["dates"]}
    t14_by_date = {d: t for t in trades_v14 for d in t["dates"]}
    t15_by_date = {d: t for t in trades_v15 for d in t["dates"]}

    t10_entries = {t["entry_date"]: t for t in trades_v10}
    t10_exits = {t["exit_date"]: t for t in trades_v10}
    t11_entries = {t["entry_date"]: t for t in trades_v11}
    t11_exits = {t["exit_date"]: t for t in trades_v11}
    t12_entries = {t["entry_date"]: t for t in trades_v12}
    t12_exits = {t["exit_date"]: t for t in trades_v12}
    t13_entries = {t["entry_date"]: t for t in trades_v13}
    t13_exits = {t["exit_date"]: t for t in trades_v13}
    t14_entries = {t["entry_date"]: t for t in trades_v14}
    t14_exits = {t["exit_date"]: t for t in trades_v14}
    t15_entries = {t["entry_date"]: t for t in trades_v15}
    t15_exits = {t["exit_date"]: t for t in trades_v15}

    # 精简日度序列
    daily_records = []
    for d in dates:
        close_p = float(feat.loc[d, "rb_close"])
        ma20_p = float(feat.loc[d, "cp_ma20"]) if not np.isnan(feat.loc[d, "cp_ma20"]) else None
        ma60_p = float(feat.loc[d, "ma_60"]) if "ma_60" in feat.columns and not np.isnan(feat.loc[d, "ma_60"]) else None
        
        e3 = float(eq_v3.loc[d]) if d in eq_v3.index else None
        e4 = float(eq_v4.loc[d]) if d in eq_v4.index else None
        e5 = float(eq_v5.loc[d]) if d in eq_v5.index else None
        e6 = float(eq_v6.loc[d]) if d in eq_v6.index else None
        e7 = float(eq_v7.loc[d]) if d in eq_v7.index else None
        e8 = float(eq_v8.loc[d]) if d in eq_v8.index else None
        e9 = float(eq_v9.loc[d]) if d in eq_v9.index else None
        e10 = float(eq_v10.loc[d]) if d in eq_v10.index else None
        e11 = float(eq_v11.loc[d]) if d in eq_v11.index else None
        e12 = float(eq_v12.loc[d]) if d in eq_v12.index else None
        e13 = float(eq_v13.loc[d]) if d in eq_v13.index else None
        e14 = float(eq_v14.loc[d]) if d in eq_v14.index else None
        e15 = float(eq_v15.loc[d]) if d in eq_v15.index else None
        
        pos10 = str(dec_v10.loc[d, "vetted_direction"]) if d in dec_v10.index else "FLAT"
        pos11 = str(dec_v11.loc[d, "vetted_direction"]) if d in dec_v11.index else "FLAT"
        pos12 = str(dec_v12.loc[d, "vetted_direction"]) if d in dec_v12.index else "FLAT"
        pos13 = str(dec_v13.loc[d, "vetted_direction"]) if d in dec_v13.index else "FLAT"
        pos14 = str(dec_v14.loc[d, "vetted_direction"]) if d in dec_v14.index else "FLAT"
        pos15 = str(dec_v15.loc[d, "vetted_direction"]) if d in dec_v15.index else "FLAT"
        
        lots10 = int(dec_v10.loc[d, "target_lots"]) if d in dec_v10.index else 0
        lots11 = int(dec_v11.loc[d, "target_lots"]) if d in dec_v11.index else 0
        lots12 = int(dec_v12.loc[d, "target_lots"]) if d in dec_v12.index else 0
        lots13 = int(dec_v13.loc[d, "target_lots"]) if d in dec_v13.index else 0
        lots14 = int(dec_v14.loc[d, "target_lots"]) if d in dec_v14.index else 0
        lots15 = int(dec_v15.loc[d, "target_lots"]) if d in dec_v15.index else 0

        tr10_active = t10_by_date.get(d)
        tr11_active = t11_by_date.get(d)
        tr12_active = t12_by_date.get(d)
        tr13_active = t13_by_date.get(d)
        tr14_active = t14_by_date.get(d)
        tr15_active = t15_by_date.get(d)

        entry10_info = t10_entries.get(d)
        exit10_info = t10_exits.get(d)
        entry11_info = t11_entries.get(d)
        exit11_info = t11_exits.get(d)
        entry12_info = t12_entries.get(d)
        exit12_info = t12_exits.get(d)
        entry13_info = t13_entries.get(d)
        exit13_info = t13_exits.get(d)
        entry14_info = t14_entries.get(d)
        exit14_info = t14_exits.get(d)
        entry15_info = t15_entries.get(d)
        exit15_info = t15_exits.get(d)

        daily_records.append({
            "d": d,
            "c": round(close_p, 1),
            "m20": round(ma20_p, 1) if ma20_p is not None else None,
            "m60": round(ma60_p, 1) if ma60_p is not None else None,
            "e3": round(e3, 0) if e3 is not None else None,
            "e4": round(e4, 0) if e4 is not None else None,
            "e5": round(e5, 0) if e5 is not None else None,
            "e6": round(e6, 0) if e6 is not None else None,
            "e7": round(e7, 0) if e7 is not None else None,
            "e8": round(e8, 0) if e8 is not None else None,
            "e9": round(e9, 0) if e9 is not None else None,
            "e10": round(e10, 0) if e10 is not None else None,
            "e11": round(e11, 0) if e11 is not None else None,
            "e12": round(e12, 0) if e12 is not None else None,
            "e13": round(e13, 0) if e13 is not None else None,
            "e14": round(e14, 0) if e14 is not None else None,
            "e15": round(e15, 0) if e15 is not None else None,
            
            "p15": pos15,
            "l15": lots15,
            "t15_id": tr15_active["id"] if tr15_active else None,
            "type15": tr15_active["type"] if tr15_active else "FLAT",
            "t15_tag": tr15_active["tag"] if tr15_active else None,
            "t15_driver": tr15_active["entry_driver"] if tr15_active else None,
            "is_entry15": bool(entry15_info),
            "is_exit15": bool(exit15_info),
            "entry15_p": entry15_info["entry_price"] if entry15_info else None,
            "exit15_p": exit15_info["exit_price"] if exit15_info else None,
            
            "p14": pos14,
            "l14": lots14,
            "t14_id": tr14_active["id"] if tr14_active else None,
            "type14": tr14_active["type"] if tr14_active else "FLAT",
            "t14_tag": tr14_active["tag"] if tr14_active else None,
            "t14_driver": tr14_active["entry_driver"] if tr14_active else None,
            "is_entry14": bool(entry14_info),
            "is_exit14": bool(exit14_info),
            "entry14_p": entry14_info["entry_price"] if entry14_info else None,
            "exit14_p": exit14_info["exit_price"] if exit14_info else None,

            "p13": pos13,
            "l13": lots13,
            "t13_id": tr13_active["id"] if tr13_active else None,
            "type13": tr13_active["type"] if tr13_active else "FLAT",

            "p12": pos12,
            "l12": lots12,
            "t12_id": tr12_active["id"] if tr12_active else None,
            "type12": tr12_active["type"] if tr12_active else "FLAT",

            "p11": pos11,
            "l11": lots11,
            "t11_id": tr11_active["id"] if tr11_active else None,
            "type11": tr11_active["type"] if tr11_active else "FLAT",

            "p10": pos10,
            "l10": lots10,
            "t10_id": tr10_active["id"] if tr10_active else None,
            "type10": tr10_active["type"] if tr10_active else "FLAT",
        })

    # 13 版本全景对照表
    progression_matrix = [
        {
            "version": "v0.3",
            "name": "v0.3 基础因果初版",
            "core_features": "建立铁水-卷螺-库存产业物理因果闭环，初步设置硬风控停机",
            "return_pct": round(comp_v3["total_return_pct"], 2),
            "final_equity_wan": round(comp_v3["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v3["cagr_pct"], 2),
            "sharpe": round(comp_v3["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v3["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v3["profit_factor"], 2),
            "key_flaw": "2020年为负收益 (-1.76%)，频繁在震荡区假突破打损"
        },
        {
            "version": "v0.4",
            "name": "v0.4 四支柱高利润牛市法则版",
            "core_features": "盘面毛利+整体价格+供应高位+需求稳定四支柱强趋势保护；动态相对波动率自适应容忍带",
            "return_pct": round(comp_v4["total_return_pct"], 2),
            "final_equity_wan": round(comp_v4["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v4["cagr_pct"], 2),
            "sharpe": round(comp_v4["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v4["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v4["profit_factor"], 2),
            "key_flaw": "超跌低位仍追空杀跌遭遇反抽打损；大趋势回踩 MA20 容易过早震出"
        },
        {
            "version": "v0.5",
            "name": "v0.5 防低位杀跌与趋势长持版",
            "core_features": "Gate B 下轨空间透支一票否决做空；1.8 ATR 宽幅容忍带 + 0.65 结构性强度底线锚定",
            "return_pct": round(comp_v5["total_return_pct"], 2),
            "final_equity_wan": round(comp_v5["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v5["cagr_pct"], 2),
            "sharpe": round(comp_v5["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v5["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v5["profit_factor"], 2),
            "key_flaw": "2020梅雨淡季被动假空(-242万)；2020 Q4踏空原料大浪；2021强贴水地板被动换月回吐"
        },
        {
            "version": "v0.6",
            "name": "v0.6 产业状态自适应治理版",
            "core_features": "四维产业结构状态治理：宏观发债上升通道防逆势空、成本推升牛市解耦禁多锁做满原料大浪、原料踩踏防追多、强贴水地板主动平空止盈",
            "return_pct": round(comp_v6["total_return_pct"], 2),
            "final_equity_wan": round(comp_v6["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v6["cagr_pct"], 2),
            "sharpe": round(comp_v6["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v6["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v6["profit_factor"], 2),
            "key_flaw": "2021年10-11月贴水极限地板平空割肉踏空后序主跌；2022年成本硬底门禁误判，67天持续空仓错失负反馈断崖"
        },
        {
            "version": "v0.7",
            "name": "v0.7 成本坍塌解耦与贴水底平空优化版",
            "core_features": "成本坍塌与负反馈破位解耦成本硬底一票否决；强Backwardation负Carry单边跌破MA5不割肉，右侧企稳反弹才平空止盈",
            "return_pct": round(comp_v7["total_return_pct"], 2),
            "final_equity_wan": round(comp_v7["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v7["cagr_pct"], 2),
            "sharpe": round(comp_v7["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v7["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v7["profit_factor"], 2),
            "key_flaw": "2021-11-17 换月 3,811 极深贴水底强行开空打损 (-318.5万)；2022-04 对称破位滞后追空"
        },
        {
            "version": "v0.8",
            "name": "v0.8 极限贴水底防假空与对称破位突破版",
            "core_features": "强贴水衰竭地板 (Roll Yield>=0.90 且空间<1.5%) 一票否决追空；Gate B 补充下破对称性豁免；修复 `cp_ma5` 特征计算",
            "return_pct": round(comp_v8["total_return_pct"], 2),
            "final_equity_wan": round(comp_v8["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v8["cagr_pct"], 2),
            "sharpe": round(comp_v8["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v8["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v8["profit_factor"], 2),
            "key_flaw": "2021年10-11月现货跟跌滞后导致误平仓空单(-21.5万)并错失700点主跌大浪；2022年4-8月负反馈超跌反抽中缺乏解耦保护"
        },
        {
            "version": "v0.9",
            "name": "v0.9 下跌现货滞后假反转治理与空头波段延续版",
            "core_features": "现货滞后假反转识别（深度均线破位带+新鲜破位期下，高基差/去库视作现货滞后假象，豁免持仓否决）；超跌V反与现货滞后解耦防线（增加MA5与大底距离约束，精准识别真实反弹离场）",
            "return_pct": round(comp_v9["total_return_pct"], 2),
            "final_equity_wan": round(comp_v9["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v9["cagr_pct"], 2),
            "sharpe": round(comp_v9["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v9["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v9["profit_factor"], 2),
            "key_flaw": "日线级别虽大幅优化，但缺乏日内分时动态微观拐点管理，单边波段中易坐过山车回吐，长假跳空开盘缺乏秒级动能耗尽风控，震荡假突破易被动承受迟滞"
        },
        {
            "version": "v0.10",
            "name": "v0.10 战术动能衰竭与微观拐点全平全回补版",
            "core_features": "战术执行引擎全面接入系统 (TacticalExecutionAdapter + ExecutionEngine)；15分钟级别全平门槛判定；初期/中后期退出灵敏度动态分段；初始突破结构防守线(15点结构缓冲，恶性破位瞬间斩仓)；开盘跳空断头铡退出与震荡假突破停滞敏捷退出；宏微观双向互锁(仅限rb/hc白名单)",
            "return_pct": round(comp_v10["total_return_pct"], 2),
            "final_equity_wan": round(comp_v10["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v10["cagr_pct"], 2),
            "sharpe": round(comp_v10["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v10["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v10["profit_factor"], 2),
            "key_flaw": "2020年底-2021年初大牛市因冬储表需断崖与累库误判为空头，叠加原料暴涨时低毛利一票否决追多，导致错失跨年暴涨主升浪"
        },
        {
            "version": "v0.11",
            "name": "v0.11 冬储去偏与成本推升长持版",
            "core_features": "冬储季节性表需与累库去偏 (12-15至02-28消除机械假空，高炉铁水正常满产下修正为Neutral)；原料共振逼空与被动成本推升长持通道 (解耦低毛利禁多锁，自适应均线启动门限放宽至3.5%~5.2%)；跨周期战术微观执行双向互锁",
            "return_pct": round(comp_v11["total_return_pct"], 2),
            "final_equity_wan": round(comp_v11["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v11["cagr_pct"], 2),
            "sharpe": round(comp_v11["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v11["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v11["profit_factor"], 2),
            "key_flaw": "虽然彻底破除了冬储累库假空和低毛利禁多锁，但在临近交割升水Contango时缺乏仓单压制预警，且在现货挺价崩塌时做空反应存在滞后"
        },
        {
            "version": "v0.12",
            "name": "v0.12 期限结构微观套利与实物交割博弈版",
            "core_features": "实物仓单压制与虚实博弈门禁 (低基差/升水Contango临近交割DTE<=45天绝对禁多)；产业空配迁徙驱动防踩踏门禁 (高基差深贴水Backwardation换月窗口30<=DTE<=65严禁追空)；现货挺价瓦解与两阶段下跌加速做空；主力换月管理器集成真实期限结构诊断器",
            "return_pct": round(comp_v12["total_return_pct"], 2),
            "final_equity_wan": round(comp_v12["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v12["cagr_pct"], 2),
            "sharpe": round(comp_v12["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v12["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v12["profit_factor"], 2),
            "key_flaw": "虽然建立期限结构门禁阻断仓单压制，但在低波震荡年份(2020/2024/2025/2026)仍因缺乏基差通道均值回归策略而长时间处于空仓观望状态"
        },
        {
            "version": "v0.13",
            "name": "v0.13 低波基差通道均值回归与单腿智能选约版",
            "core_features": "★ 60日基差Z-score滚动统计通道 (严格零未来函数shift(1))；★ 深贴水均值回归做多(Z>=1.5) + 临近换月智能优选远月(FAR，规避交割强平并享受贴水修复)；★ 升水/平水均值回归做空(Z<=-1.5) + 临近换月智能优选近月(NEAR，捕捉实物仓单抛压)；★ 投机账户物理交割防线(DTE<=20天强制清盘平仓)",
            "return_pct": round(comp_v13["total_return_pct"], 2),
            "final_equity_wan": round(comp_v13["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v13["cagr_pct"], 2),
            "sharpe": round(comp_v13["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v13["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v13["profit_factor"], 2),
            "key_flaw": "单腿裸敞口仍承担不可对冲的单边Beta系统波动，且未利用上期所大边保证金制度释放套利资金效率"
        },
        {
            "version": "v0.14",
            "name": "v0.14 双腿跨期价差对冲与套利初始版",
            "core_features": "★ 严格 1:1 双腿跨期对冲与套利 (Bull Spread: 买近卖远 / Bear Spread: 卖近买远)；★ 临近换月窗口(25<=DTE<=65)低波深贴水/深升水双腿同时进出；★ 上期所大边保证金制度释放资金效率；★ 投机账户物理交割防线(Front DTE<=20天强制平仓退出)",
            "return_pct": round(comp_v14["total_return_pct"], 2),
            "final_equity_wan": round(comp_v14["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v14["cagr_pct"], 2),
            "sharpe": round(comp_v14["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v14["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v14["profit_factor"], 2),
            "key_flaw": "单边持仓与套利互锁过严，单边趋势进入震荡钝化期后无法解耦释放转为跨期，导致利润回吐且2025年收益仅11.06%，回撤修复天数长达298天"
        },
        {
            "version": "v0.15",
            "name": "★ v0.15 钝化转跨期互锁松绑终极版 (最新)",
            "core_features": "★ 单边趋势钝化平滑转跨期套利互锁松绑：单边趋势进入震荡钝化期后允许释放单边仓位转为低风险跨期套利；★ 现货量价微观止损调制：物理现货真实突破时即刻执行微观敏捷止损并切入反套；★ 2025年收益翻倍跃升至+25.67%，2020年完全修复至+36.90%，最大回撤期缩短116天至182天！",
            "return_pct": round(comp_v15["total_return_pct"], 2),
            "final_equity_wan": round(comp_v15["final_equity"] / 10000, 1),
            "cagr_pct": round(comp_v15["cagr_pct"], 2),
            "sharpe": round(comp_v15["sharpe_ratio"], 2),
            "max_dd_pct": round(comp_v15["max_drawdown_pct"], 2),
            "profit_factor": round(comp_v15["profit_factor"], 2),
            "key_flaw": "【当前全系统最强版本】总资产突破3.799亿元(+3699.33%)创历史纪录！2025年收益由11.06%跃升至25.67%(+14.61 pp翻倍)！最大回撤维持-29.95%且回撤修复天数大幅锐减至182天！夏普1.45/索提诺2.66/卡玛1.83，连续9年全正收益！"
        }
    ]

    # 年度收益横向大表 (2018-2026)
    all_years = sorted(list(set(y3.keys()) | set(y4.keys()) | set(y5.keys()) | set(y6.keys()) | set(y7.keys()) | set(y8.keys()) | set(y9.keys()) | set(y10.keys()) | set(y11.keys()) | set(y12.keys()) | set(y13.keys()) | set(y14.keys()) | set(y15.keys())))
    year_matrix = []
    for y in all_years:
        year_matrix.append({
            "year": int(y),
            "v3": round(float(y3.get(y, 0)), 2),
            "v4": round(float(y4.get(y, 0)), 2),
            "v5": round(float(y5.get(y, 0)), 2),
            "v6": round(float(y6.get(y, 0)), 2),
            "v7": round(float(y7.get(y, 0)), 2),
            "v8": round(float(y8.get(y, 0)), 2),
            "v9": round(float(y9.get(y, 0)), 2),
            "v10": round(float(y10.get(y, 0)), 2),
            "v11": round(float(y11.get(y, 0)), 2),
            "v12": round(float(y12.get(y, 0)), 2),
            "v13": round(float(y13.get(y, 0)), 2),
            "v14": round(float(y14.get(y, 0)), 2),
            "v15": round(float(y15.get(y, 0)), 2),
            "diff_v15_v14": round(float(y15.get(y, 0)) - float(y14.get(y, 0)), 2),
            "diff_v14_v13": round(float(y14.get(y, 0)) - float(y13.get(y, 0)), 2)
        })

    trades_v9_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v9]
    trades_v10_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v10]
    trades_v11_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v11]
    trades_v12_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v12]
    trades_v13_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v13]
    trades_v14_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v14]
    trades_v15_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v15]

    return {
        "dates": dates,
        "daily": daily_records,
        "year_matrix": year_matrix,
        "progression": progression_matrix,
        "trades_v9": trades_v9_clean,
        "trades_v10": trades_v10_clean,
        "trades_v11": trades_v11_clean,
        "trades_v12": trades_v12_clean,
        "trades_v13": trades_v13_clean,
        "trades_v14": trades_v14_clean,
        "trades_v15": trades_v15_clean,
        "comp_v9": comp_v9,
        "comp_v10": comp_v10,
        "comp_v11": comp_v11,
        "comp_v12": comp_v12,
        "comp_v13": comp_v13,
        "comp_v14": comp_v14,
        "comp_v15": comp_v15
    }

def generate_unified_html(data, output_paths):
    json_data = json.dumps(data, ensure_ascii=False, default=json_default_converter)

    c9 = data["comp_v9"]
    c10 = data["comp_v10"]
    c11 = data["comp_v11"]
    c12 = data["comp_v12"]
    c13 = data["comp_v13"]
    c14 = data["comp_v14"]
    c15 = data["comp_v15"]

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>螺纹钢基本面量化系统 · 历次回测演进与对比总全景看板 (v0.3~v0.15)</title>
  <!-- Tailwind CSS CDN -->
  <script src="https://cdn.tailwindcss.com"></script>
  <!-- Chart.js CDN -->
  <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
  <!-- Chart.js Zoom Plugin -->
  <script src="https://cdn.jsdelivr.net/npm/hammerjs@2.0.8"></script>
  <script src="https://cdn.jsdelivr.net/npm/chartjs-plugin-zoom@2.0.1"></script>
  <style>
    body {{
      background-color: #0b0f19;
      color: #e2e8f0;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }}
    .custom-scrollbar::-webkit-scrollbar {{
      width: 6px;
      height: 6px;
    }}
    .custom-scrollbar::-webkit-scrollbar-track {{
      background: #1e293b;
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb {{
      background: #475569;
      border-radius: 3px;
    }}
    .custom-scrollbar::-webkit-scrollbar-thumb:hover {{
      background: #64748b;
    }}
    .nav-tab-active {{
      background-color: #059669 !important;
      color: #ffffff !important;
      border-color: #10b981 !important;
      font-weight: 700;
      box-shadow: 0 4px 12px rgba(16, 185, 129, 0.25);
    }}
    .btn-active {{
      background-color: #059669 !important;
      color: #ffffff !important;
      border-color: #10b981 !important;
      font-weight: 700;
    }}
    .filter-btn-active {{
      background-color: #3b82f6 !important;
      color: #ffffff !important;
      border-color: #60a5fa !important;
      font-weight: 700;
    }}
    .counter-filter-active {{
      background-color: #dc2626 !important;
      color: #ffffff !important;
      border-color: #f87171 !important;
      font-weight: 700;
    }}
  </style>
</head>
<body class="p-3 md:p-6 custom-scrollbar">

  <!-- Top Global Header -->
  <header class="max-w-7xl mx-auto mb-4 bg-slate-900/95 border border-slate-800 rounded-xl p-4 shadow-2xl backdrop-blur flex flex-col md:flex-row justify-between items-start md:items-center gap-3">
    <div class="flex items-center gap-3">
      <div class="w-10 h-10 rounded-lg bg-emerald-500/20 border border-emerald-500/40 flex items-center justify-center font-black text-emerald-400 text-lg">
        RB
      </div>
      <div>
        <h1 class="text-lg md:text-xl font-black text-white flex items-center gap-2">
          <span>螺纹钢产业基本面量化系统 · 历次回测演进与对比总看板</span>
        </h1>
        <p class="text-xs text-slate-400 mt-0.5">
          全周期 2018–2026（{len(data['dates'])}交易日，截至 {data['dates'][-1]}）· 统一集成十三代版本历史实验 · 默认展示最新候选版本 (v0.15)
        </p>
      </div>
    </div>
    <div class="flex items-center gap-3 text-xs">
      <div class="bg-slate-950 px-3 py-1.5 rounded-lg border border-slate-800 text-slate-300 font-mono">
        当前最新: <span class="text-emerald-400 font-bold">Framework-0.15 (+{round(c15['total_return_pct'], 2)}% / {round(c15['final_equity']/100000000, 2)}亿)</span>
      </div>
    </div>
  </header>

  <!-- Unified Top Version Navigation Bar (Tabs) -->
  <nav class="max-w-7xl mx-auto mb-6 bg-slate-900 border border-slate-800 rounded-xl p-2 flex flex-wrap items-center justify-between gap-2 shadow-xl sticky top-2 z-50 backdrop-blur">
    <div class="flex items-center gap-2 pl-2">
      <span class="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse"></span>
      <span class="text-xs font-bold text-slate-300">回测演进版本导航:</span>
    </div>
    <div class="flex flex-wrap items-center gap-1.5">
      <!-- Tab 1: Latest Version v0.15 vs v0.14 (Default Active) -->
      <button id="navTab_v15_v14" onclick="switchNavTab('v15_v14')" class="px-3.5 py-1.5 rounded-lg text-xs transition flex items-center gap-1.5 nav-tab-active">
        <span class="px-1.5 py-0.5 rounded text-[10px] bg-emerald-500/30 text-emerald-300 border border-emerald-400/50 font-bold">★ 最新</span>
        <span>v0.15 钝化转跨期终极版 vs v0.14 跨期初始版</span>
      </button>

      <!-- Tab 2: v0.14 vs v0.13 -->
      <button id="navTab_v14_v13" onclick="switchNavTab('v14_v13')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.14 vs v0.13 (双腿跨期价差对冲与套利版)</span>
      </button>

      <!-- Tab 3: v0.13 vs v0.12 -->
      <button id="navTab_v13_v12" onclick="switchNavTab('v13_v12')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.13 vs v0.12 (低波基差通道与单腿选约)</span>
      </button>

      <!-- Tab 4: v0.12 vs v0.11 -->
      <button id="navTab_v12_v11" onclick="switchNavTab('v12_v11')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.12 vs v0.11 (期限结构与实物交割)</span>
      </button>

      <!-- Tab 5: v0.11 vs v0.10 -->
      <button id="navTab_v11_v10" onclick="switchNavTab('v11_v10')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.11 vs v0.10 (冬储去偏与成本推升长持)</span>
      </button>

      <!-- Tab 6: v0.10 vs v0.9 -->
      <button id="navTab_v10_v9" onclick="switchNavTab('v10_v9')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.10 vs v0.9 (战术动能衰竭与微观拐点)</span>
      </button>

      <!-- Tab 7: v0.9 vs v0.8 -->
      <button id="navTab_v9_v8" onclick="switchNavTab('v9_v8')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.9 vs v0.8 (现货滞后假反转治理)</span>
      </button>

      <!-- Tab 8: v0.8 vs v0.7 -->
      <button id="navTab_v8_v7" onclick="switchNavTab('v8_v7')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.8 vs v0.7 (极限贴水底与对称破位)</span>
      </button>

      <!-- Tab 9: v0.7 vs v0.6 -->
      <button id="navTab_v7_v6" onclick="switchNavTab('v7_v6')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.7 vs v0.6 (成本坍塌与贴水底优化)</span>
      </button>

      <!-- Tab 10: v0.6 vs v0.5 -->
      <button id="navTab_v6_v5" onclick="switchNavTab('v6_v5')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.6 vs v0.5 (状态自适应治理)</span>
      </button>

      <!-- Tab 11: v0.5 vs v0.4 -->
      <button id="navTab_v5_v4" onclick="switchNavTab('v5_v4')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.5 vs v0.4 (防杀跌与长持)</span>
      </button>

      <!-- Tab 12: v0.4 vs v0.3 -->
      <button id="navTab_v4_v3" onclick="switchNavTab('v4_v3')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition">
        <span>v0.4 vs v0.3 (四支柱牛市法则)</span>
      </button>

      <!-- Tab 13: All-Version Evolution Matrix -->
      <button id="navTab_matrix" onclick="switchNavTab('matrix')" class="px-3 py-1.5 rounded-lg text-xs font-medium text-purple-300 hover:text-white hover:bg-slate-800 transition flex items-center gap-1">
        <span>★ 全版本进化矩阵 (v0.3~v0.15)</span>
      </button>
    </div>
  </nav>

  <!-- ============================================================== -->
  <!-- TAB 1: v0.15 钝化转跨期终极版 vs v0.14 跨期初始版 (默认完整展示) -->
  <!-- ============================================================== -->
  <div id="panel_v15_v14" class="tab-panel max-w-7xl mx-auto space-y-6">

    <!-- Header Stats Banner -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              FRAMEWORK-0.15-CANDIDATE
            </span>
            <span class="text-xs text-slate-400 font-mono">成对对比上一版本 (v0.14 Baseline)</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            螺纹钢历史回测全景复盘：v0.15 单边钝化转跨期套利互锁松绑终极版 vs v0.14 跨期初始版
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            在 v0.14 双腿跨期套利的基础上，彻底解决单边趋势与跨期套利“互锁死占”难题与现货微观止损迟滞：
            <span class="text-emerald-400 font-semibold">★ 单边趋势钝化平滑转跨期套利 (Trend Stagnation to Spread Transition)</span>：单边波段进入震荡钝化期解除单边互锁，平滑退出单边并切换为低风险双腿跨期套利（正套/反套），盘活闲置保证金；
            <span class="text-cyan-400 font-semibold">★ 物理现货量价破位微观止损调制 (Physical Spot Micro-Breakout Stop)</span>：物理现货真实突破时即刻执行微观敏捷止损并翻转为反套锁仓；
            <span class="text-amber-400 font-bold">★ 2025年收益由 11.06% 翻倍跃升至 +25.67% (+14.61 pp)</span>，2020年完全修复至 +36.90%，最大回撤天数由 298 天暴减至 182 天（缩短 116 天）；
            <span class="text-rose-400 font-bold">★ 期末总资产突破 3.799 亿元 (+3699.33%，较 v0.14 净增 +7,674 万元)</span>，夏普升至 1.45，索提诺升至 2.66，卡玛达 1.83，连续 9 年 100% 全正收益！
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.14)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">{round(c14['total_return_pct'], 2)}% <span class="text-xs text-slate-400 font-normal">/ {round(c14['final_equity']/10000, 0):,.0f}万</span></div>
          </div>
          <div class="bg-emerald-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-emerald-500/40">
            <div class="text-xs text-emerald-300 font-medium">优化版本 (v0.15)</div>
            <div class="text-lg font-bold text-emerald-400 mt-0.5">{round(c15['total_return_pct'], 2)}% <span class="text-xs text-emerald-300/80 font-normal">/ {round(c15['final_equity']/10000, 0):,.0f}万</span></div>
          </div>
        </div>
      </div>

      <!-- Quick Stat Pill Grid -->
      <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 mt-4">
        <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
          <div class="text-xs text-slate-400">总收益率 (Total Return)</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+{round(c15['total_return_pct'], 2)}%</div>
          <div class="text-[11px] text-emerald-300 font-mono">突破3699%新高 (+{round(c15['total_return_pct'] - c14['total_return_pct'], 2)}%)</div>
        </div>
        <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
          <div class="text-xs text-slate-400">最终期末资产</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">{round(c15['final_equity']/10000, 0):,.0f} 万元</div>
          <div class="text-[11px] text-emerald-300 font-mono">3.80 亿元 (+{round((c15['final_equity'] - c14['final_equity'])/10000, 0):,.0f}万)</div>
        </div>
        <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
          <div class="text-xs text-slate-400">2018-2026复合年化</div>
          <div class="text-base font-bold text-cyan-300 mt-0.5">{round(c15['cagr_pct'], 2)}%</div>
          <div class="text-[11px] text-emerald-400 font-mono">复合年化跃升至54.67%</div>
        </div>
        <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
          <div class="text-xs text-slate-400">最大回撤修复期</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">{int(c15.get('max_drawdown_duration_days', 182))} 天</div>
          <div class="text-[11px] text-emerald-300 font-mono">由298天暴减116天 (MaxDD -29.95%)</div>
        </div>
        <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
          <div class="text-xs text-slate-400">夏普 / 索提诺比率</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">{round(c15['sharpe_ratio'], 2)} / {round(c15['sortino_ratio'], 2)}</div>
          <div class="text-[11px] text-slate-400 font-mono">Calmar: {round(c15['calmar_ratio'], 2)}</div>
        </div>
        <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
          <div class="text-xs text-slate-400">胜率 / 盈亏比</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">{round(c15['win_rate_pct'], 2)}% / {round(c15['profit_factor'], 2)}</div>
          <div class="text-[11px] text-emerald-300 font-mono">盈亏比大幅跃升至 2.43</div>
        </div>
      </div>
    </section>

    <!-- Interactive Price & Trades Chart -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 mb-4">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>螺纹钢历史主连价格与进出场·反向做错行情全景图</span>
            <span class="px-2 py-0.5 text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded-full flex items-center gap-1">
              <span class="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping"></span>
              支持双击缩放
            </span>
          </h2>
          <p class="text-xs text-slate-400 mt-1">
            <span class="text-emerald-400 font-semibold">【交互指南】</span>双击图表任意位置快速放大聚焦该波段（约70交易日），再次双击快速还原全景视野；支持滚轮细化缩放、鼠标拖拽左右平移。
          </p>
        </div>

        <!-- Controls Toolbar -->
        <div class="flex flex-wrap items-center gap-2 self-stretch lg:self-auto">
          <!-- Version Switcher inside Tab 1 -->
          <div class="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            <button id="btnVer15" class="px-3 py-1.5 rounded-md font-semibold text-slate-200 transition btn-active">
              ★ v0.15 钝化转跨期终极版
            </button>
            <button id="btnVer14" class="px-3 py-1.5 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition">
              v0.14 跨期对冲初始版
            </button>
            <button id="btnVer13" class="px-3 py-1.5 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition">
              v0.13 低波选约版
            </button>
          </div>

          <!-- Color/Situation Filters -->
          <div class="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs gap-1">
            <button id="filterAll" class="px-2.5 py-1.5 rounded-md text-slate-200 filter-btn-active transition">
              全部
            </button>
            <button id="filterCounter" class="px-2.5 py-1.5 rounded-md text-rose-300 hover:text-white transition flex items-center gap-1">
              <span>仅看做错/打损</span>
              <span id="counterCountBadge" class="px-1.5 py-0.2 rounded-full text-[10px] bg-rose-500/30 text-rose-300 font-bold">0</span>
            </button>
            <button id="filterWin" class="px-2.5 py-1.5 rounded-md text-emerald-300 hover:text-white transition">
              仅看做对·顺势
            </button>
          </div>

          <button id="resetZoomBtn" class="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-xs font-semibold border border-slate-700 transition flex items-center gap-1">
            <span>重置视野</span>
          </button>
          <span class="text-[11px] text-slate-400 hidden xl:inline-flex items-center gap-1 font-mono">
            <span class="text-emerald-400">⚡</span> 双击任意处放大聚焦 / 再次双击还原
          </span>
        </div>
      </div>

      <!-- Color Situation Toggles Bar -->
      <div class="flex flex-wrap items-center gap-2 bg-slate-950/60 p-2.5 rounded-lg border border-slate-800/80 text-xs mb-3">
        <span class="text-slate-400 font-medium mr-1 text-[11px]">图层开关:</span>
        <button id="toggleBtn_WIN_LONG" onclick="toggleColorSituation('WIN_LONG')" class="px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 bg-emerald-950/80 text-emerald-300 border-emerald-500/70 ring-1 ring-emerald-500/30">
          <span>🟢 做对·多头顺势盈利</span>
        </button>
        <button id="toggleBtn_LOSS_LONG" onclick="toggleColorSituation('LOSS_LONG')" class="px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 bg-amber-950/80 text-amber-300 border-amber-500/70 ring-1 ring-amber-500/30">
          <span>🟠 做错·多头追高打损</span>
        </button>
        <button id="toggleBtn_WIN_SHORT" onclick="toggleColorSituation('WIN_SHORT')" class="px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 bg-cyan-950/80 text-cyan-300 border-cyan-500/70 ring-1 ring-cyan-500/30">
          <span>🔵 做对·空头顺势盈利</span>
        </button>
        <button id="toggleBtn_LOSS_SHORT" onclick="toggleColorSituation('LOSS_SHORT')" class="px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 bg-rose-950/80 text-rose-300 border-rose-500/70 ring-1 ring-rose-500/30">
          <span>🔴 做错·空头杀跌打损</span>
        </button>
        <button id="toggleBtn_FLAT" onclick="toggleColorSituation('FLAT')" class="px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 bg-slate-800 text-slate-300 border-slate-600">
          <span>⚪ 空仓观望</span>
        </button>
        <div class="h-4 w-px bg-slate-700 mx-1"></div>
        <button id="toggleBtn_ENTRY_MARKERS" onclick="toggleColorSituation('ENTRY_MARKERS')" class="px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 bg-indigo-950/80 text-indigo-300 border-indigo-500/70 ring-1 ring-indigo-500/30">
          <span>▲▼ 入场标记</span>
        </button>
        <button id="toggleBtn_EXIT_MARKERS" onclick="toggleColorSituation('EXIT_MARKERS')" class="px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 bg-fuchsia-950/80 text-fuchsia-300 border-fuchsia-500/70 ring-1 ring-fuchsia-500/30">
          <span>● 离场标记</span>
        </button>
      </div>

      <!-- Main Canvas Container -->
      <div class="relative w-full h-[520px] bg-slate-950/80 rounded-lg p-2 border border-slate-800/80 group">
        <!-- Floating Zoom Status Badge -->
        <div id="priceZoomToast" class="absolute top-4 right-4 z-20 px-3 py-1.5 rounded-lg text-xs font-mono bg-slate-900/95 text-emerald-300 border border-emerald-500/50 shadow-2xl backdrop-blur transition-all duration-300 opacity-0 pointer-events-none flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
          <span id="priceZoomToastText">全景视图 (2018-2026)</span>
        </div>
        <canvas id="priceChart"></canvas>
      </div>

      <!-- Version Difference Description Box -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-3 mt-4 text-xs font-mono">
        <div id="v14NoteBox" class="bg-slate-800/40 p-3 rounded-lg border border-slate-800 flex items-start gap-3 transition opacity-70">
          <div class="w-3 h-3 rounded-full bg-slate-400 mt-0.5 flex-shrink-0"></div>
          <div>
            <div class="font-bold text-slate-200">v0.14 跨期对冲初始版局限：单边持仓与套利互锁过严，单边钝化后死板持仓回吐</div>
            <div class="text-slate-400 mt-1 leading-relaxed">
              1) 单边持仓与跨期套利完全排他互锁，单边波段进入震荡钝化期后无法解耦释放，导致巨额浮盈回吐；<br>
              2) 2025年收益仅 11.06%，回撤修复天数长达 298 天，未能充分利用低波震荡期的跨期基差收益。
            </div>
          </div>
        </div>
        <div id="v15NoteBox" class="bg-emerald-950/20 p-3 rounded-lg border border-emerald-500/40 flex items-start gap-3 transition ring-1 ring-emerald-500/30">
          <div class="w-3 h-3 rounded-full bg-emerald-400 mt-0.5 flex-shrink-0"></div>
          <div>
            <div class="font-bold text-emerald-300">★ v0.15 钝化转跨期互锁松绑终极版：钝化解耦平滑转套利 + 现货破位敏捷微观止损</div>
            <div class="text-slate-300 mt-1 leading-relaxed">
              1) ★ 单边钝化平滑转跨期套利：当单边趋势进入震荡钝化期后允许释放单边仓位转为低风险跨期套利（正套/反套），盘活闲置保证金；<br>
              2) ★ 现货量价破位微观止损调制：物理现货真实突破时即刻执行微观敏捷止损并切入反套；<br>
              3) ★ 2025年收益由 11.06% 翻倍跃升至 +25.67%，回撤期由 298 天暴减至 182 天，期末资产突破 3.799 亿元！
            </div>
          </div>
        </div>
      </div>
    </section>

    <!-- Four Core Breakthrough Spotlights -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-4">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>四大攻坚攻克典型场景 (点击一键定位主图)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            涵盖2025年Contango钝化平单边转反套锁定暴利、2026年物理现货突破即刻止损切入反套、2020年方向一致性保全单边大空头与九年全天候全正收益。
          </p>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Spotlight 1: 2025-09 Contango 钝化平单边转反套锁定暴利 -->
        <div class="bg-slate-950/70 p-4 rounded-xl border border-emerald-500/40 relative flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-center border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">2025-08-15 ~ 2025-10-30</span>
              <span class="text-emerald-300 bg-emerald-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-emerald-500/30">★ 破局：Contango钝化平单边转反套锁定暴利</span>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">2025年秋季：单边空头钝化解耦，全额转入反套锁定超额</h3>
            <div class="text-xs text-emerald-300/90 font-mono mt-0.5">2025全年收益由 11.06% 暴增至 25.67% (+14.61 pp 翻倍)</div>
            <p class="text-xs text-slate-400 mt-2 bg-slate-900/60 p-2 rounded border border-slate-800/80">
              <span class="text-slate-300 font-semibold">机制表现:</span> 单边空头动能耗尽、基差深平水/Contango钝化。旧版因单边持仓互锁无法开套利且单边利润反复回吐；v0.15 触发钝化转跨期解耦，平滑平仓单边空单，全额转入 Bear Spread 反套（卖 2510 买 2601），完美捕捉换月期限收敛，锁定暴利！
            </p>
          </div>
          <button onclick="zoomToRange('2025-08-01', '2025-11-15')" class="mt-3.5 w-full py-1.5 text-xs font-semibold bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 rounded-lg border border-emerald-500/40 transition">
            🔍 一键定位主图查看 2025-09 钝化转反套锁定暴利
          </button>
        </div>

        <!-- Spotlight 2: 2026-04 物理现货突破即刻止损并切入反套 -->
        <div class="bg-slate-950/70 p-4 rounded-xl border border-cyan-500/40 relative flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-center border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">2026-03-01 ~ 2026-04-15</span>
              <span class="text-cyan-300 bg-cyan-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-cyan-500/30">★ 物理现货突破即刻止损并切入反套</span>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">2026年春季：现货破位微观止损，顺势切入反套</h3>
            <div class="text-xs text-cyan-300/90 font-mono mt-0.5">2026年化收益保持 +20.36% 高位，成功阻断逆势深陷</div>
            <p class="text-xs text-slate-400 mt-2 bg-slate-900/60 p-2 rounded border border-slate-800/80">
              <span class="text-slate-300 font-semibold">机制表现:</span> 当物理现货价格与成交量发生微观反向破位，系统执行敏捷微观止损，杜绝盲目硬扛，并顺势切入临近交割反套，稳健锁定 20.36% 年化收益！
            </p>
          </div>
          <button onclick="zoomToRange('2026-02-15', '2026-04-30')" class="mt-3.5 w-full py-1.5 text-xs font-semibold bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 rounded-lg border border-cyan-500/40 transition">
            🔍 一键定位主图查看 2026-04 现货微观止损与反套
          </button>
        </div>

        <!-- Spotlight 3: 2020-09 方向一致性保护单边大空头 -->
        <div class="bg-slate-950/70 p-4 rounded-xl border border-purple-500/40 relative flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-center border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">2020-09-01 ~ 2020-11-20</span>
              <span class="text-purple-300 bg-purple-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-purple-500/30">★ 宏微观方向一致性保全单边大空头</span>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">2020年秋季：方向一致性保持纯正单边主导，不被杂波打乱</h3>
            <div class="text-xs text-purple-300/90 font-mono mt-0.5">2020年化收益 100% 修复至 +36.90% 峰值高位</div>
            <p class="text-xs text-slate-400 mt-2 bg-slate-900/60 p-2 rounded border border-slate-800/80">
              <span class="text-slate-300 font-semibold">机制表现:</span> 2020年秋季单边空头与跨期方向保持强一致性，系统自动维持纯正单边空头主导地位，不被杂波打乱，2020年收益由 v0.14 的 35.27% 完全修复至 +36.90% 峰值！
            </p>
          </div>
          <button onclick="zoomToRange('2020-08-25', '2020-11-30')" class="mt-3.5 w-full py-1.5 text-xs font-semibold bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 rounded-lg border border-purple-500/40 transition">
            🔍 一键定位主图查看 2020-09 单边大空头保全
          </button>
        </div>

        <!-- Spotlight 4: 2018-2026连续九年全正收益 -->
        <div class="bg-slate-950/70 p-4 rounded-xl border border-amber-500/40 relative flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-center border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">2018-03 ~ 2026-10 (2085交易日)</span>
              <span class="text-emerald-300 bg-emerald-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-emerald-500/30">★ 连续9年100%全正收益</span>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">全天候穿越周期：总资产突破 3.799 亿元 (+3699.33%)</h3>
            <div class="text-xs text-emerald-300/90 font-mono mt-0.5">年化复合收益跃升至 54.67%，夏普达 1.45，索提诺达 2.66，卡玛达 1.83</div>
            <p class="text-xs text-slate-400 mt-2 bg-slate-900/60 p-2 rounded border border-slate-800/80">
              <span class="text-slate-300 font-semibold">机制表现:</span> 2018:+35.30%, 2019:+69.79%, 2020:+36.90%, 2021:+111.00%, 2022:+83.46%, 2023:+68.14%, 2024:+22.72%, 2025:+25.67%, 2026:+20.36%。全历史九年全正收益！
            </p>
          </div>
          <button onclick="zoomToRange('2018-03-09', '2026-10-14')" class="mt-3.5 w-full py-1.5 text-xs font-semibold bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 rounded-lg border border-emerald-500/40 transition">
            🔍 全历史全景视角 (2018-2026)
          </button>
        </div>
      </div>
    </section>

    <!-- Equity Curve Comparison Chart (v0.13 vs v0.14 vs ★ v0.15) -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-3">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>净值曲线成对对比 (v0.13 低波选约版 vs v0.14 跨期对冲初始版 vs ★ v0.15 钝化转跨期终极版)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            初始资金 1,000 万元。全历史实约撮合零未来函数。直观呈现单边钝化转跨期互锁松绑与现货量价微观止损接入后的历史级收益跃迁。
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-3 text-xs font-mono">
          <span class="flex items-center gap-1 text-slate-400"><span class="w-3 h-0.5 bg-slate-400 inline-block"></span> v0.13 基准: {round(c13['final_equity']/10000, 0):,.0f} 万元 (2.73亿)</span>
          <span class="flex items-center gap-1 text-cyan-400"><span class="w-3 h-0.5 bg-cyan-400 inline-block"></span> v0.14 跨期对冲: {round(c14['final_equity']/10000, 0):,.0f} 万元 (3.03亿)</span>
          <span class="flex items-center gap-1 text-emerald-400 font-bold"><span class="w-3 h-0.5 bg-emerald-400 inline-block"></span> ★ v0.15 钝化转跨期终极版: {round(c15['final_equity']/10000, 0):,.0f} 万元 (3.80亿)</span>
        </div>
      </div>
      <div class="relative w-full h-[280px] bg-slate-950/80 rounded-lg p-2 border border-slate-800/80">
        <canvas id="equityChart"></canvas>
      </div>
    </section>

    <!-- Full Trade Episodes Ledger Table -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 mb-4">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>完整波段持仓交易台账 (<span id="displayedVersionName">★ v0.15 钝化转跨期终极版</span>，共 <span id="displayedTradeCount">0</span> 笔)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            包含入场价格、平仓价格、最大持仓手数、盈亏额及退出原因。点击“定位主图”可自动缩放对应时段。
          </p>
        </div>

        <!-- Table Filters -->
        <div class="flex flex-wrap items-center gap-2 text-xs">
          <input type="text" id="tradeSearchInput" placeholder="搜索交易ID/原因..." class="bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-emerald-500">
          <select id="tradeDirFilter" class="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-emerald-500">
            <option value="ALL">全部方向</option>
            <option value="LONG">多头持仓</option>
            <option value="SHORT">空头持仓</option>
          </select>
          <select id="tradeYearFilter" class="bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-slate-200 focus:outline-none focus:border-emerald-500">
            <option value="ALL">全部年份</option>
            <option value="2018">2018</option>
            <option value="2019">2019</option>
            <option value="2020">2020</option>
            <option value="2021">2021</option>
            <option value="2022">2022</option>
            <option value="2023">2023</option>
            <option value="2024">2024</option>
            <option value="2025">2025</option>
            <option value="2026">2026</option>
          </select>
        </div>
      </div>

      <div class="overflow-x-auto custom-scrollbar max-h-[500px]">
        <table class="w-full text-left text-xs border-collapse">
          <thead class="sticky top-0 bg-slate-900 border-b border-slate-800 z-10">
            <tr class="text-slate-400">
              <th class="p-3">交易ID</th>
              <th class="p-3">方向</th>
              <th class="p-3">类型标注</th>
              <th class="p-3">入场日期 / 价格</th>
              <th class="p-3">离场日期 / 价格</th>
              <th class="p-3 text-right">持仓天数</th>
              <th class="p-3 text-right">持仓规模</th>
              <th class="p-3 text-right">盈亏金额</th>
              <th class="p-3 text-right">收益率</th>
              <th class="p-3">入场驱动</th>
              <th class="p-3">离场原因</th>
              <th class="p-3 text-center">操作</th>
            </tr>
          </thead>
          <tbody id="tradeTableBody" class="divide-y divide-slate-800/60 font-mono text-slate-300">
            <!-- Dynamically populated via JS -->
          </tbody>
        </table>
      </div>
    </section>

  </div>

  <!-- ============================================================== -->
  <!-- TAB 2: v0.14 vs v0.13 (双腿跨期价差对冲与套利版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v14_v13" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
              FRAMEWORK-0.14
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.14 双腿跨期价差对冲与套利初始版 vs v0.13 低波选约版
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            严格 1:1 双腿跨期对冲 (Bull Spread 正套: 买近卖远 / Bear Spread 反套: 卖近买远)；换月窗口 (25≤DTE≤65) 深升贴水驱动；上期所大边保证金制度；投机账户物理交割防线 (Front DTE≤20天清盘)。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.13)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">{round(c13['total_return_pct'], 2)}% / {round(c13['final_equity']/10000, 0):,.0f}万</div>
          </div>
          <div class="bg-cyan-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-cyan-500/40">
            <div class="text-xs text-cyan-300 font-medium">优化版本 (v0.14)</div>
            <div class="text-lg font-bold text-cyan-400 mt-0.5">{round(c14['total_return_pct'], 2)}% / {round(c14['final_equity']/10000, 0):,.0f}万</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">总收益与净值突破</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">+{round(c14['total_return_pct'], 2)}% <span class="text-xs text-slate-400 font-normal">({round(c14['final_equity']/10000, 0):,.0f}万元, 净增+3022.5万)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2024与2026低波年收益</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">2024:+22.49% / 2026:+20.36% <span class="text-xs text-slate-400 font-normal">(翻倍跃升)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">夏普与盈亏比</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">1.37 / 2.25 <span class="text-xs text-slate-400 font-normal">(Sortino: 2.45, Calmar: 1.70)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">回撤期缩短</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">298 天 <span class="text-xs text-slate-400 font-normal">(由319天缩短至298天)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 3: v0.13 vs v0.12 (低波基差通道与单腿选约版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v13_v12" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
              FRAMEWORK-0.13
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.13 低波基差通道均值回归与单腿智能选约版 vs v0.12 期限结构微观套利版
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            60日基差Z-score滚动统计通道 (零未来函数 shift(1))；深贴水均值回归做多优选远月 (FAR)；高升水均值回归做空优选近月 (NEAR)；DTE≤20天交割物理防线。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.12)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">{round(c12['total_return_pct'], 2)}% / {round(c12['final_equity']/10000, 0):,.0f}万</div>
          </div>
          <div class="bg-cyan-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-cyan-500/40">
            <div class="text-xs text-cyan-300 font-medium">优化版本 (v0.13)</div>
            <div class="text-lg font-bold text-cyan-400 mt-0.5">{round(c13['total_return_pct'], 2)}% / {round(c13['final_equity']/10000, 0):,.0f}万</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">总收益与净值突破</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">+{round(c13['total_return_pct'], 2)}% <span class="text-xs text-slate-400 font-normal">({round(c13['final_equity']/10000, 0):,.0f}万元, 净增+3402.1万)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2020与2024低波年收益</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">2020:+37.90% / 2024:+18.29% <span class="text-xs text-slate-400 font-normal">(显著增厚)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">夏普比率</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">1.33 <span class="text-xs text-slate-400 font-normal">(Sortino: 2.34, Calmar: 1.62)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">胜率与盈亏比</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">60.10% / 2.14 <span class="text-xs text-slate-400 font-normal">(微观优选远近月)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 4: v0.12 vs v0.11 (期限结构与实物交割博弈版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v12_v11" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
              FRAMEWORK-0.12
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.12 期限结构微观套利与实物交割博弈版 vs v0.11 冬储成本推升长持版
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            实物仓单压制与虚实博弈门禁 (Contango升水DTE≤45天绝对禁多)；产业空配迁徙驱动防踩踏门禁 (Backwardation深贴水换月窗口严禁追空)；现货挺价瓦解两阶段加速做空。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.11)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">{round(c11['total_return_pct'], 2)}% / {round(c11['final_equity']/10000, 0):,.0f}万</div>
          </div>
          <div class="bg-cyan-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-cyan-500/40">
            <div class="text-xs text-cyan-300 font-medium">优化版本 (v0.12)</div>
            <div class="text-lg font-bold text-cyan-400 mt-0.5">{round(c12['total_return_pct'], 2)}% / {round(c12['final_equity']/10000, 0):,.0f}万</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">总收益与净值突破</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">+{round(c12['total_return_pct'], 2)}% <span class="text-xs text-slate-400 font-normal">({round(c12['final_equity']/10000, 0):,.0f}万元, 净增+3350.2万)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">现货挺价瓦解加速做空</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">2019:+64.27% / 2023:+74.26% <span class="text-xs text-slate-400 font-normal">(顺势大赚)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">仓单压制绝对禁多</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">2026年稳健达+9.79% <span class="text-xs text-slate-400 font-normal">(阻断踩踏陷阱)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">最大回撤率</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">-29.95% <span class="text-xs text-slate-400 font-normal">(维持历史极低水平)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 5: v0.11 vs v0.10 (冬储去偏与成本推升长持版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v11_v10" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              FRAMEWORK-0.11
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.11 冬储去偏与成本推升长持版 vs v0.10 战术版：彻底破除2020-2021跨年大牛市踏空死锁
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            冬储季节性表需与累库去偏 (消除机械假空，12-15至02-28修正为Neutral)；原料共振逼空与被动成本推升长持通道 (解耦低毛利禁多锁，自适应均线启动门限放宽至3.5%~5.2%，置信度全面豁免)；跨周期战术微观执行双向互锁。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.10)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">{round(c10['total_return_pct'], 2)}% / {round(c10['final_equity']/10000, 0):,.0f}万</div>
          </div>
          <div class="bg-emerald-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-emerald-500/40">
            <div class="text-xs text-emerald-300 font-medium">优化版本 (v0.11)</div>
            <div class="text-lg font-bold text-emerald-400 mt-0.5">{round(c11['total_return_pct'], 2)}% / {round(c11['final_equity']/10000, 0):,.0f}万</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">总收益与净值突破</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+1954.43% <span class="text-xs text-slate-400 font-normal">(2.054亿元, 净增+4391.8万)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">最大回撤历史首次破30%</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">-29.95% <span class="text-xs text-slate-400 font-normal">(-31.61% → -29.95%)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">夏普比率 (Sharpe)</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">1.24 <span class="text-xs text-slate-400 font-normal">(Sortino: 2.19, Calmar: 1.46)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2020跨年原料大浪攻坚</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+17.61% <span class="text-xs text-slate-400 font-normal">(顺畅长持原料二次推升)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 6: v0.10 vs v0.9 (战术动能衰竭与微观拐点全平全回补版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v10_v9" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              FRAMEWORK-0.10
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.10 战术接入版 vs v0.9 宏观日线版：战术动能衰竭与微观拐点全平全回补
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            战术执行引擎全面接入系统 (TacticalExecutionAdapter + ExecutionEngine)：15分钟拐点全平全回补、趋势确立阶段灵敏度分段、15点初始突破结构止损与跳空断头铡退出。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.9)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">{round(c9['total_return_pct'], 2)}% / {round(c9['final_equity']/10000, 0):,.0f}万</div>
          </div>
          <div class="bg-emerald-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-emerald-500/40">
            <div class="text-xs text-emerald-300 font-medium">优化版本 (v0.10)</div>
            <div class="text-lg font-bold text-emerald-400 mt-0.5">{round(c10['total_return_pct'], 2)}% / {round(c10['final_equity']/10000, 0):,.0f}万</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">最大回撤压制</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">-31.61% <span class="text-xs text-slate-400 font-normal">(-35.54% → -31.61%)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">热卷2410跳空断头铡</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+17.71万 <span class="text-xs text-slate-400 font-normal">(净超额 +6.99万)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">夏普比率 (Sharpe)</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">1.13 <span class="text-xs text-slate-400 font-normal">(1.10 → 1.13)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">索提诺比率 (Sortino)</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">2.08 <span class="text-xs text-slate-400 font-normal">(Calmar: 1.25)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 7: v0.9 vs v0.8 (下跌现货滞后假反转治理与空头波段延续版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v9_v8" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              FRAMEWORK-0.9
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.9 优化版 vs v0.8 基准版：下跌现货滞后假反转治理与空头波段延续
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            针对 2021年10-11月 与 2022年4-8月 下跌波段现货跟跌滞后导致的误平仓与假反抽根因治理：精准识别现货滞后假象豁免否决，解耦超跌V反与防线，保全暴利。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.8)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">1,548.22% / 1.65亿</div>
          </div>
          <div class="bg-emerald-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-emerald-500/40">
            <div class="text-xs text-emerald-300 font-medium">优化版本 (v0.9)</div>
            <div class="text-lg font-bold text-emerald-400 mt-0.5">1,759.69% / 1.86亿</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2021 年主跌浪攻坚</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+56.30% <span class="text-xs text-slate-400 font-normal">(较v0.8暴增+16.97%)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2022 年负反馈断崖</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+131.12% <span class="text-xs text-slate-400 font-normal">(保全+1,666.8万暴利)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">夏普比率 (Sharpe)</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">1.10 <span class="text-xs text-slate-400 font-normal">(1.08 → 1.10)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">最大回撤率</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">-35.54% <span class="text-xs text-slate-400 font-normal">(优化改善)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 8: v0.8 vs v0.7 (极限贴水底防假空与对称破位突破版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v8_v7" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              FRAMEWORK-0.8
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.8 优化版 vs v0.7 基准版：极限贴水底防假空与对称破位突破
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            强贴水衰竭地板 (Roll Yield>=0.90 且空间<1.5%) 一票否决追空；Gate B 补充下破对称性豁免；修复 `cp_ma5` 特征计算。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.7)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">1,545.29% / 1.65亿</div>
          </div>
          <div class="bg-emerald-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-emerald-500/40">
            <div class="text-xs text-emerald-300 font-medium">优化版本 (v0.8)</div>
            <div class="text-lg font-bold text-emerald-400 mt-0.5">1,548.22% / 1.65亿</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2021 年收益率</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+39.33% <span class="text-xs text-slate-400 font-normal">(较v0.7 +7.76%)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2022 年收益率</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+131.14% <span class="text-xs text-slate-400 font-normal">(做空大赚+1,666.8万)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">夏普比率 (Sharpe)</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">1.08 <span class="text-xs text-slate-400 font-normal">(保持稳健)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">最大回撤率</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">-38.39% <span class="text-xs text-slate-400 font-normal">(零劣质增加)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 9: v0.7 vs v0.6 (成本坍塌与贴水底优化版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v7_v6" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
              FRAMEWORK-0.7
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.7 优化版 vs v0.6 基准版：成本坍塌解耦与贴水底平空优化
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            成本坍塌与负反馈破位解耦成本硬底一票否决；强Backwardation负Carry单边跌破MA5不提前割肉，右侧企稳反弹才平空止盈。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.6)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">1,220.24% / 1.32亿</div>
          </div>
          <div class="bg-emerald-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-emerald-500/40">
            <div class="text-xs text-emerald-300 font-medium">优化版本 (v0.7)</div>
            <div class="text-lg font-bold text-emerald-400 mt-0.5">1,545.29% / 1.65亿</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2021 年收益率</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+31.57% <span class="text-xs text-slate-400 font-normal">(较v0.6 +4.89%)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2022 年收益率</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">+144.33% <span class="text-xs text-slate-400 font-normal">(较v0.6 +27.98%)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">夏普比率 (Sharpe)</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">1.08 <span class="text-xs text-slate-400 font-normal">(1.05 → 1.08)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">最大回撤率</div>
          <div class="text-base font-bold text-emerald-400 mt-0.5">-38.39% <span class="text-xs text-slate-400 font-normal">(零劣质增加)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 10: v0.6 vs v0.5 (产业状态自适应治理版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v6_v5" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">
              FRAMEWORK-0.6
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.6 优化版 vs v0.5 基准版：结构化行情状态治理与2020/2021攻坚
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            四维产业结构状态治理：宏观发债上升通道防逆势空、成本推升牛市解耦禁多锁做满原料大浪、原料踩踏防追多、强贴水地板主动平空止盈。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.5)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">815.04% / 9,150万</div>
          </div>
          <div class="bg-cyan-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-cyan-500/40">
            <div class="text-xs text-cyan-300 font-medium">优化版本 (v0.6)</div>
            <div class="text-lg font-bold text-cyan-400 mt-0.5">1,220.24% / 1.32亿</div>
          </div>
        </div>
      </div>
      <div class="grid grid-cols-2 sm:grid-cols-4 gap-3 mt-4 text-xs">
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2020 年收益率</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">+27.52% <span class="text-xs text-slate-400 font-normal">(+7.51% 破冰扭转)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">2021 年收益率</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">+26.68% <span class="text-xs text-slate-400 font-normal">(翻倍大幅抬升)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">夏普比率 (Sharpe)</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">1.05 <span class="text-xs text-slate-400 font-normal">(0.94 → 1.05)</span></div>
        </div>
        <div class="bg-slate-800/40 p-3 rounded-lg border border-slate-700/40">
          <div class="text-slate-400">最大回撤率</div>
          <div class="text-base font-bold text-cyan-400 mt-0.5">-38.39% <span class="text-xs text-slate-400 font-normal">(-39.29% → -38.39%)</span></div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 11: v0.5 vs v0.4 (防杀跌与长持版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v5_v4" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">
              FRAMEWORK-0.5
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.5 优化版 vs v0.4 基准版：防低位杀跌与波段长持机制
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            Gate B 下轨空间透支一票否决做空；1.8 ATR 宽幅容忍带 + 0.65 结构性强度底线锚定。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.4)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">762.43% / 8,624万</div>
          </div>
          <div class="bg-indigo-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-indigo-500/40">
            <div class="text-xs text-indigo-300 font-medium">优化版本 (v0.5)</div>
            <div class="text-lg font-bold text-indigo-400 mt-0.5">815.04% / 9,150万</div>
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 12: v0.4 vs v0.3 (四支柱牛市法则版) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_v4_v3" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
        <div>
          <div class="flex items-center gap-2">
            <span class="px-2 py-0.5 text-xs font-bold rounded-full bg-purple-500/20 text-purple-400 border border-purple-500/30">
              FRAMEWORK-0.4
            </span>
            <span class="text-xs text-slate-400 font-mono">历史攻坚成果回测记录</span>
          </div>
          <h2 class="text-lg md:text-xl font-black text-white mt-2">
            v0.4 优化版 vs v0.3 基准版：四支柱高利润牛市法则
          </h2>
          <p class="text-xs md:text-sm text-slate-400 mt-1">
            盘面毛利+整体价格+供应高位+需求稳定四支柱强趋势保护；动态相对波动率自适应容忍带。
          </p>
        </div>
        <div class="flex items-center gap-2 self-stretch md:self-auto">
          <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
            <div class="text-xs text-slate-400 font-medium">基准版本 (v0.3)</div>
            <div class="text-lg font-bold text-slate-200 mt-0.5">878.20% / 9,782万</div>
          </div>
          <div class="bg-purple-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-purple-500/40">
            <div class="text-xs text-purple-300 font-medium">优化版本 (v0.4)</div>
            <div class="text-lg font-bold text-purple-400 mt-0.5">762.43% / 8,624万</div>
          </div>
        </div>
      </div>
    </section>
  </div>

  <!-- ============================================================== -->
  <!-- TAB 13: 全版本进化矩阵 (v0.3~v0.15 阶梯跃迁) (默认隐藏) -->
  <!-- ============================================================== -->
  <div id="panel_matrix" class="tab-panel max-w-7xl mx-auto space-y-6 hidden">

    <!-- Step Jump Equity Chart -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-3">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>全版本历程净值曲线阶梯进化大图 (v0.3 → ... → v0.14 → ★ v0.15)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            完整呈现自初始版本至今的净值中枢跃迁与风控修复。
          </p>
        </div>
        <div class="flex flex-wrap items-center gap-3 text-xs font-mono">
          <span class="flex items-center gap-1 text-purple-400"><span class="w-3 h-0.5 bg-purple-400 inline-block"></span> v0.3: 9,782万</span>
          <span class="flex items-center gap-1 text-cyan-400"><span class="w-3 h-0.5 bg-cyan-400 inline-block"></span> v0.6: 13,202万</span>
          <span class="flex items-center gap-1 text-slate-400"><span class="w-3 h-0.5 bg-slate-400 inline-block"></span> v0.10: 16,152万</span>
          <span class="flex items-center gap-1 text-cyan-300"><span class="w-3 h-0.5 bg-cyan-300 inline-block"></span> v0.12: 23,894万</span>
          <span class="flex items-center gap-1 text-indigo-400"><span class="w-3 h-0.5 bg-indigo-400 inline-block"></span> v0.13: 27,296万</span>
          <span class="flex items-center gap-1 text-amber-400"><span class="w-3 h-0.5 bg-amber-400 inline-block"></span> v0.14: 30,319万</span>
          <span class="flex items-center gap-1 text-emerald-400 font-bold"><span class="w-3 h-0.5 bg-emerald-400 inline-block"></span> ★ v0.15: 37,993万 (3.80亿)</span>
        </div>
      </div>
      <div class="relative w-full h-[320px] bg-slate-950/80 rounded-lg p-2 border border-slate-800/80">
        <canvas id="matrixEquityChart"></canvas>
      </div>
    </section>

    <!-- Version Progression Master Table -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <h2 class="text-lg font-bold text-white mb-3 flex items-center gap-2">
        <span>全版本核心机制演进与历史缺陷攻坚矩阵</span>
      </h2>
      <div class="overflow-x-auto custom-scrollbar">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="bg-slate-800/80 text-slate-300 border-b border-slate-700">
              <th class="p-3 font-semibold">版本代号</th>
              <th class="p-3 font-semibold">核心设计机制与突破重点</th>
              <th class="p-3 font-semibold text-right">全周期收益</th>
              <th class="p-3 font-semibold text-right">期末资产</th>
              <th class="p-3 font-semibold text-right">复合年化</th>
              <th class="p-3 font-semibold text-right">夏普比率</th>
              <th class="p-3 font-semibold text-right">最大回撤</th>
              <th class="p-3 font-semibold text-right">盈利因子</th>
              <th class="p-3 font-semibold">历史局限性诊断与攻坚结论</th>
            </tr>
          </thead>
          <tbody id="matrixTableBody" class="divide-y divide-slate-800 text-slate-300 font-mono">
            <!-- Dynamically populated via JS -->
          </tbody>
        </table>
      </div>
    </section>

    <!-- Year-by-Year Multi-Version Matrix -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <h2 class="text-lg font-bold text-white mb-3 flex items-center gap-2">
        <span>分年度十三代版本收益率全景矩阵 (2018–2026)</span>
      </h2>
      <div class="overflow-x-auto custom-scrollbar">
        <table class="w-full text-left text-xs border-collapse font-mono">
          <thead>
            <tr class="bg-slate-800/80 text-slate-300 border-b border-slate-700">
              <th class="p-3 font-semibold font-sans">年份</th>
              <th class="p-3 font-semibold text-slate-400">v0.3 收益率</th>
              <th class="p-3 font-semibold text-slate-400">v0.4 收益率</th>
              <th class="p-3 font-semibold text-slate-400">v0.5 收益率</th>
              <th class="p-3 font-semibold text-slate-400">v0.6 收益率</th>
              <th class="p-3 font-semibold text-slate-400">v0.7 收益率</th>
              <th class="p-3 font-semibold text-slate-400">v0.8 收益率</th>
              <th class="p-3 font-semibold text-slate-400">v0.9 收益率</th>
              <th class="p-3 font-semibold text-slate-400">v0.10 战术</th>
              <th class="p-3 font-semibold text-slate-400">v0.11 成本</th>
              <th class="p-3 font-semibold text-slate-400">v0.12 期限结构</th>
              <th class="p-3 font-semibold text-slate-400">v0.13 低波选约</th>
              <th class="p-3 font-semibold text-cyan-300">v0.14 跨期套利</th>
              <th class="p-3 font-semibold text-emerald-400 text-sm">★ v0.15 钝化转跨期终极版</th>
              <th class="p-3 font-semibold text-emerald-400">v0.15 较 v0.14 超额</th>
              <th class="p-3 font-semibold font-sans">版本演进关键差异评述</th>
            </tr>
          </thead>
          <tbody id="multiYearTableBody" class="divide-y divide-slate-800 text-slate-300">
            <!-- Dynamically populated via JS -->
          </tbody>
        </table>
      </div>
    </section>
  </div>

  <!-- Footer -->
  <footer class="max-w-7xl mx-auto mt-8 text-center text-xs text-slate-500 py-4 border-t border-slate-800/60 font-mono">
    钢材产业基本面量化系统 · Multi-Version Unified Backtest Dashboard · 严格遵守 PIT 与零未来函数铁律
  </footer>

  <!-- Unified Data & Client Logic -->
  <script>
    const DATA = {json_data};

    // State Variables
    let currentNavTab = 'v15_v14';
    let currentVersion = 'v15'; // 'v15', 'v14', 'v13'
    let currentTradeFilter = 'ALL';
    let tableSearchQuery = '';
    let tableDirFilter = 'ALL';
    let tableYearFilter = 'ALL';

    // Color & Situation Visibility State
    const colorVisibility = {{
      WIN_LONG: true,       // 🟢 多头顺势盈利
      LOSS_LONG: true,      // 🟠 多头追高反向打损
      WIN_SHORT: true,      // 🔵 空头顺势盈利
      LOSS_SHORT: true,     // 🔴 空头杀跌反向打损
      FLAT: true,           // ⚪ 空仓观望
      ENTRY_MARKERS: true,  // ▲▼ 入场开仓标记
      EXIT_MARKERS: true,   // ● 离场平仓标记
      BANDS: true           // 持仓背景光带
    }};

    const toggleConfig = {{
      WIN_LONG: {{
        id: "toggleBtn_WIN_LONG",
        name: "做对·多头顺势盈利",
        icon: "🟢",
        activeClass: "bg-emerald-950/80 text-emerald-300 border-emerald-500/70 ring-1 ring-emerald-500/30",
        inactiveClass: "bg-slate-900/60 text-slate-500 border-slate-800 line-through opacity-50"
      }},
      LOSS_LONG: {{
        id: "toggleBtn_LOSS_LONG",
        name: "做错·多头追高打损",
        icon: "🟠",
        activeClass: "bg-amber-950/80 text-amber-300 border-amber-500/70 ring-1 ring-amber-500/30",
        inactiveClass: "bg-slate-900/60 text-slate-500 border-slate-800 line-through opacity-50"
      }},
      WIN_SHORT: {{
        id: "toggleBtn_WIN_SHORT",
        name: "做对·空头顺势盈利",
        icon: "🔵",
        activeClass: "bg-cyan-950/80 text-cyan-300 border-cyan-500/70 ring-1 ring-cyan-500/30",
        inactiveClass: "bg-slate-900/60 text-slate-500 border-slate-800 line-through opacity-50"
      }},
      LOSS_SHORT: {{
        id: "toggleBtn_LOSS_SHORT",
        name: "做错·空头杀跌打损",
        icon: "🔴",
        activeClass: "bg-rose-950/80 text-rose-300 border-rose-500/70 ring-1 ring-rose-500/30",
        inactiveClass: "bg-slate-900/60 text-slate-500 border-slate-800 line-through opacity-50"
      }},
      FLAT: {{
        id: "toggleBtn_FLAT",
        name: "空仓观望",
        icon: "⚪",
        activeClass: "bg-slate-800 text-slate-300 border-slate-600",
        inactiveClass: "bg-slate-900/60 text-slate-500 border-slate-800 line-through opacity-50"
      }},
      ENTRY_MARKERS: {{
        id: "toggleBtn_ENTRY_MARKERS",
        name: "入场标记",
        icon: "▲▼",
        activeClass: "bg-indigo-950/80 text-indigo-300 border-indigo-500/70 ring-1 ring-indigo-500/30",
        inactiveClass: "bg-slate-900/60 text-slate-500 border-slate-800 line-through opacity-50"
      }},
      EXIT_MARKERS: {{
        id: "toggleBtn_EXIT_MARKERS",
        name: "离场标记",
        icon: "●",
        activeClass: "bg-fuchsia-950/80 text-fuchsia-300 border-fuchsia-500/70 ring-1 ring-fuchsia-500/30",
        inactiveClass: "bg-slate-900/60 text-slate-500 border-slate-800 line-through opacity-50"
      }}
    }};

    function updateToggleButtonsUI() {{
      Object.keys(toggleConfig).forEach(key => {{
        const btn = document.getElementById(toggleConfig[key].id);
        if (!btn) return;
        const cfg = toggleConfig[key];
        if (colorVisibility[key]) {{
          btn.className = `px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 ${{cfg.activeClass}}`;
          btn.innerHTML = `<span>${{cfg.icon}} ${{cfg.name}}</span>`;
        }} else {{
          btn.className = `px-2 py-1 rounded text-[11px] border transition flex items-center gap-1 ${{cfg.inactiveClass}}`;
          btn.innerHTML = `<span>${{cfg.icon}} ${{cfg.name}} (隐藏)</span>`;
        }}
      }});
    }}

    function toggleColorSituation(type) {{
      colorVisibility[type] = !colorVisibility[type];
      updateToggleButtonsUI();
      renderTradeTable();
      priceChart.update();
    }}

    function applyPresetColorFilter(preset) {{
      currentTradeFilter = preset;
      const bAll = document.getElementById("filterAll");
      const bCounter = document.getElementById("filterCounter");
      const bWin = document.getElementById("filterWin");

      bAll.className = "px-2.5 py-1.5 rounded-md text-slate-400 hover:text-slate-200 transition";
      bCounter.className = "px-2.5 py-1.5 rounded-md text-rose-300 hover:text-white transition flex items-center gap-1";
      bWin.className = "px-2.5 py-1.5 rounded-md text-emerald-300 hover:text-white transition";

      if (preset === 'ALL') {{
        bAll.className = "px-2.5 py-1.5 rounded-md text-slate-200 filter-btn-active transition";
        colorVisibility.WIN_LONG = true;
        colorVisibility.LOSS_LONG = true;
        colorVisibility.WIN_SHORT = true;
        colorVisibility.LOSS_SHORT = true;
        colorVisibility.FLAT = true;
      }} else if (preset === 'COUNTER') {{
        bCounter.className = "px-2.5 py-1.5 rounded-md text-white counter-filter-active transition flex items-center gap-1";
        colorVisibility.WIN_LONG = false;
        colorVisibility.LOSS_LONG = true;
        colorVisibility.WIN_SHORT = false;
        colorVisibility.LOSS_SHORT = true;
        colorVisibility.FLAT = false;
      }} else if (preset === 'WIN') {{
        bWin.className = "px-2.5 py-1.5 rounded-md text-white btn-active transition";
        colorVisibility.WIN_LONG = true;
        colorVisibility.LOSS_LONG = false;
        colorVisibility.WIN_SHORT = true;
        colorVisibility.LOSS_SHORT = false;
        colorVisibility.FLAT = false;
      }}
      updateToggleButtonsUI();
      renderTradeTable();
      priceChart.update();
    }}

    // Switch Navigation Tabs
    function switchNavTab(tabId) {{
      currentNavTab = tabId;
      document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
      const targetPanel = document.getElementById(`panel_${{tabId}}`);
      if (targetPanel) targetPanel.classList.remove("hidden");

      document.querySelectorAll("nav button").forEach(b => {{
        b.className = "px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition";
      }});
      const activeBtn = document.getElementById(`navTab_${{tabId}}`);
      if (activeBtn) {{
        activeBtn.className = "px-3.5 py-1.5 rounded-lg text-xs transition flex items-center gap-1.5 nav-tab-active";
      }}

      if (tabId === 'matrix' && matrixEquityChart) {{
        matrixEquityChart.resize();
      }}
      if (tabId === 'v15_v14' && priceChart) {{
        priceChart.resize();
        equityChart.resize();
      }}
    }}

    // Render Version Progression Master Table
    const matrixTableBody = document.getElementById("matrixTableBody");
    DATA.progression.forEach(item => {{
      const tr = document.createElement("tr");
      const isLatest = item.version === 'v0.15';
      tr.className = isLatest ? "bg-emerald-950/20 font-bold text-white border-l-4 border-emerald-400" : "hover:bg-slate-800/40";
      tr.innerHTML = `
        <td class="p-3 text-slate-200 font-sans">${{item.name}}</td>
        <td class="p-3 text-slate-300 font-sans text-xs">${{item.core_features}}</td>
        <td class="p-3 text-right text-emerald-400 font-bold">${{item.return_pct.toFixed(2)}}%</td>
        <td class="p-3 text-right text-slate-200">${{item.final_equity_wan.toLocaleString()}}万</td>
        <td class="p-3 text-right text-cyan-300">${{item.cagr_pct.toFixed(2)}}%</td>
        <td class="p-3 text-right text-slate-200">${{item.sharpe.toFixed(2)}}</td>
        <td class="p-3 text-right text-rose-400">${{item.max_dd_pct.toFixed(2)}}%</td>
        <td class="p-3 text-right text-slate-200">${{item.profit_factor.toFixed(2)}}</td>
        <td class="p-3 text-slate-300 font-sans text-xs">${{item.key_flaw}}</td>
      `;
      matrixTableBody.appendChild(tr);
    }});

    // Render Multi-Year Comparison Table
    const multiYearTableBody = document.getElementById("multiYearTableBody");
    DATA.year_matrix.forEach(row => {{
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/40";
      const diffColor = row.diff_v15_v14 > 0 ? "text-emerald-400 font-bold" : (row.diff_v15_v14 < 0 ? "text-rose-400" : "text-slate-400");
      const diffSign = row.diff_v15_v14 > 0 ? "+" : "";

      let note = "-";
      if (row.year === 2018) note = "冬储去偏 + 顺势突破稳健增厚 (+35.30%)";
      else if (row.year === 2019) note = "现货挺价瓦解两阶段加速做空，收益跃升至+69.79% (+5.51%)";
      else if (row.year === 2020) note = "宏微观方向一致性保全单边大空头，收益修复至+36.90% (+1.63%)";
      else if (row.year === 2021) note = "春季高升水做空 + 原料推升顺畅长持，收益暴增至+111.00% (+34.01%)";
      else if (row.year === 2022) note = "成本坍塌负反馈敏捷顺势做空暴赚 (+83.46%)";
      else if (row.year === 2023) note = "原料负反馈二次补跌瓦解加速做空 (+68.14%)";
      else if (row.year === 2024) note = "低波基差通道与跨期对冲，收益稳健达+22.72%";
      else if (row.year === 2025) note = "★ 攻坚突破：Contango钝化平单边转反套，收益由11.06%翻倍暴增至+25.67% (+14.61%)！";
      else if (row.year === 2026) note = "物理现货突破即刻止损切入反套，收益稳定达+20.36%";

      tr.innerHTML = `
        <td class="p-3 font-bold text-white font-sans">${{row.year}}</td>
        <td class="p-3 text-slate-400">${{row.v3 > 0 ? '+' : ''}}${{row.v3.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v4 > 0 ? '+' : ''}}${{row.v4.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v5 > 0 ? '+' : ''}}${{row.v5.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v6 > 0 ? '+' : ''}}${{row.v6.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v7 > 0 ? '+' : ''}}${{row.v7.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v8 > 0 ? '+' : ''}}${{row.v8.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v9 > 0 ? '+' : ''}}${{row.v9.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v10 > 0 ? '+' : ''}}${{row.v10.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v11 > 0 ? '+' : ''}}${{row.v11.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v12 > 0 ? '+' : ''}}${{row.v12.toFixed(2)}}%</td>
        <td class="p-3 text-slate-400">${{row.v13 > 0 ? '+' : ''}}${{row.v13.toFixed(2)}}%</td>
        <td class="p-3 text-cyan-300 font-medium">${{row.v14 > 0 ? '+' : ''}}${{row.v14.toFixed(2)}}%</td>
        <td class="p-3 text-emerald-400 font-bold">${{row.v15 > 0 ? '+' : ''}}${{row.v15.toFixed(2)}}%</td>
        <td class="p-3 ${{diffColor}}">${{diffSign}}${{row.diff_v15_v14.toFixed(2)}}%</td>
        <td class="p-3 text-slate-300 font-sans text-xs">${{note}}</td>
      `;
      multiYearTableBody.appendChild(tr);
    }});

    // Extract Series
    const dates = DATA.daily.map(x => x.d);
    const prices = DATA.daily.map(x => x.c);
    const ma20 = DATA.daily.map(x => x.m20);
    const ma60 = DATA.daily.map(x => x.m60);
    const eq3 = DATA.daily.map(x => x.e3 / 10000);
    const eq4 = DATA.daily.map(x => x.e4 / 10000);
    const eq5 = DATA.daily.map(x => x.e5 / 10000);
    const eq6 = DATA.daily.map(x => x.e6 / 10000);
    const eq7 = DATA.daily.map(x => x.e7 / 10000);
    const eq8 = DATA.daily.map(x => x.e8 / 10000);
    const eq9 = DATA.daily.map(x => x.e9 / 10000);
    const eq10 = DATA.daily.map(x => x.e10 / 10000);
    const eq11 = DATA.daily.map(x => x.e11 / 10000);
    const eq12 = DATA.daily.map(x => x.e12 / 10000);
    const eq13 = DATA.daily.map(x => x.e13 / 10000);
    const eq14 = DATA.daily.map(x => x.e14 / 10000);
    const eq15 = DATA.daily.map(x => x.e15 / 10000);

    // Chart.js - Price Chart
    const ctxPrice = document.getElementById("priceChart").getContext("2d");
    const priceChart = new Chart(ctxPrice, {{
      type: "line",
      data: {{
        labels: dates,
        datasets: [
          {{
            label: "螺纹收盘价",
            data: prices,
            borderWidth: 2.2,
            pointRadius: 0,
            pointHoverRadius: 5,
            tension: 0.05,
            segment: {{
              borderColor: ctx => {{
                const idx = ctx.p0DataIndex;
                const r = DATA.daily[idx];
                if (!r) return "#334155";
                let type = r.type15;
                if (currentVersion === 'v14') type = r.type14;
                else if (currentVersion === 'v13') type = r.type13;

                if (!colorVisibility[type]) {{
                  return "rgba(51, 65, 85, 0.35)";
                }}

                switch(type) {{
                  case 'WIN_LONG': return '#10b981';
                  case 'LOSS_LONG': return '#f59e0b';
                  case 'WIN_SHORT': return '#06b6d4';
                  case 'LOSS_SHORT': return '#f43f5e';
                  default: return colorVisibility.FLAT ? '#475569' : 'rgba(51, 65, 85, 0.25)';
                }}
              }},
              borderWidth: ctx => {{
                const idx = ctx.p0DataIndex;
                const r = DATA.daily[idx];
                if (!r) return 1.2;
                let type = r.type15;
                if (currentVersion === 'v14') type = r.type14;
                else if (currentVersion === 'v13') type = r.type13;

                if (!colorVisibility[type]) {{
                  return 1.0;
                }}
                if (type === 'FLAT') return 1.2;
                return 2.6;
              }}
            }}
          }},
          {{
            label: "MA20",
            data: ma20,
            borderColor: "#818cf8",
            borderWidth: 1.0,
            borderDash: [3, 2],
            pointRadius: 0,
            tension: 0.1
          }},
          {{
            label: "MA60",
            data: ma60,
            borderColor: "#c084fc",
            borderWidth: 1.0,
            borderDash: [5, 3],
            pointRadius: 0,
            tension: 0.1
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: {{ mode: "index", intersect: false }},
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            backgroundColor: "rgba(11, 15, 25, 0.95)",
            titleColor: "#94a3b8",
            bodyColor: "#f1f5f9",
            borderColor: "#334155",
            borderWidth: 1,
            padding: 12,
            callbacks: {{
              title: function(items) {{ return `日期: ${{items[0].label}}`; }},
              afterBody: function(context) {{
                const idx = context[0].dataIndex;
                const r = DATA.daily[idx];
                let activeTrades = DATA.trades_v15;
                let activeTrId = r.t15_id;
                let isExit = r.is_exit15;
                let verLabel = 'v0.15';

                if (currentVersion === 'v14') {{
                  activeTrades = DATA.trades_v14;
                  activeTrId = r.t14_id;
                  isExit = r.is_exit14;
                  verLabel = 'v0.14';
                }} else if (currentVersion === 'v13') {{
                  activeTrades = DATA.trades_v13;
                  activeTrId = r.t13_id;
                  isExit = r.is_exit13;
                  verLabel = 'v0.13';
                }}

                const activeTr = activeTrId ? activeTrades.find(t => t.id === activeTrId) : null;
                const lines = [];

                lines.push(`收盘价: ${{r.c}} 元/吨 (MA20: ${{r.m20 || '-'}}, MA60: ${{r.m60 || '-'}})`);

                if (activeTr) {{
                  const tagColor = activeTr.is_win ? '🟢' : '🔴';
                  lines.push(`----------------------------------------`);
                  lines.push(`${{tagColor}} [${{verLabel}}] ${{activeTr.id}} ${{activeTr.tag}}`);
                  lines.push(`入场: ${{activeTr.entry_date}} @ ${{activeTr.entry_price}} 元 (${{activeTr.entry_lots}}手)`);
                  lines.push(`驱动: ${{activeTr.entry_driver}}`);
                  lines.push(`持仓: 第 ${{r.d}} 天 (最大持仓: ${{activeTr.max_lots}}手)`);
                  lines.push(`总盈亏: ${{activeTr.pnl_wan > 0 ? '+' : ''}}${{activeTr.pnl_wan}} 万元 (${{activeTr.ret_pct > 0 ? '+' : ''}}${{activeTr.ret_pct}}%)`);
                  if (isExit) {{
                    lines.push(`● 离场日: @ ${{activeTr.exit_price}} 元 (${{activeTr.exit_reason}})`);
                  }}
                }} else {{
                  lines.push(`持仓状态: 空仓观望 (FLAT)`);
                }}

                lines.push(`----------------------------------------`);
                lines.push(`v0.14 净值: ${{Math.round(r.e14 / 10000)}} 万元 | ★ v0.15 净值: ${{Math.round(r.e15 / 10000)}} 万元`);
                return lines;
              }}
            }}
          }},
          zoom: {{
            pan: {{ enabled: true, mode: "x" }},
            zoom: {{ wheel: {{ enabled: true }}, pinch: {{ enabled: true }}, mode: "x" }}
          }}
        }},
        scales: {{
          x: {{
            grid: {{ color: "rgba(51, 65, 85, 0.25)" }},
            ticks: {{ color: "#64748b", maxTicksLimit: 14, font: {{ family: "monospace", size: 10 }} }}
          }},
          y: {{
            position: "right",
            grid: {{ color: "rgba(51, 65, 85, 0.25)" }},
            ticks: {{ color: "#94a3b8", font: {{ family: "monospace", size: 11 }} }}
          }}
        }}
      }}
    }});

    // Chart.js - Equity Chart (v0.13 vs v0.14 vs ★ v0.15)
    const ctxEquity = document.getElementById("equityChart").getContext("2d");
    const equityChart = new Chart(ctxEquity, {{
      type: "line",
      data: {{
        labels: dates,
        datasets: [
          {{
            label: "v0.13 低波选约版",
            data: eq13,
            borderColor: "#64748b",
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.05
          }},
          {{
            label: "v0.14 跨期对冲初始版",
            data: eq14,
            borderColor: "#06b6d4",
            borderWidth: 2.0,
            pointRadius: 0,
            tension: 0.05
          }},
          {{
            label: "★ v0.15 钝化转跨期终极版 (最新)",
            data: eq15,
            borderColor: "#10b981",
            borderWidth: 3.5,
            pointRadius: 0,
            tension: 0.05
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: {{ mode: "index", intersect: false }},
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            backgroundColor: "rgba(11, 15, 25, 0.95)",
            titleColor: "#94a3b8",
            bodyColor: "#f1f5f9",
            borderColor: "#334155",
            borderWidth: 1,
            callbacks: {{
              label: function(c) {{ return `${{c.dataset.label}}: ${{Math.round(c.raw)}} 万元`; }}
            }}
          }},
          zoom: {{
            pan: {{ enabled: true, mode: "x" }},
            zoom: {{ wheel: {{ enabled: true }}, mode: "x" }}
          }}
        }},
        scales: {{
          x: {{
            grid: {{ color: "rgba(51, 65, 85, 0.25)" }},
            ticks: {{ color: "#64748b", maxTicksLimit: 14, font: {{ family: "monospace", size: 10 }} }}
          }},
          y: {{
            position: "right",
            grid: {{ color: "rgba(51, 65, 85, 0.25)" }},
            ticks: {{ color: "#94a3b8", font: {{ family: "monospace", size: 11 }}, callback: function(v) {{ return v + "万"; }} }}
          }}
        }}
      }}
    }});

    // Chart.js - Matrix Equity Chart (v0.3 ~ v0.15)
    const ctxMatrix = document.getElementById("matrixEquityChart").getContext("2d");
    const matrixEquityChart = new Chart(ctxMatrix, {{
      type: "line",
      data: {{
        labels: dates,
        datasets: [
          {{ label: "v0.3 基础因果版", data: eq3, borderColor: "#c084fc", borderWidth: 1.2, pointRadius: 0 }},
          {{ label: "v0.4 四支柱牛市版", data: eq4, borderColor: "#fbbf24", borderWidth: 1.2, pointRadius: 0 }},
          {{ label: "v0.5 防杀跌长持版", data: eq5, borderColor: "#22d3ee", borderWidth: 1.2, pointRadius: 0 }},
          {{ label: "v0.6 状态治理版", data: eq6, borderColor: "#2dd4bf", borderWidth: 1.4, pointRadius: 0 }},
          {{ label: "v0.7 成本解耦优化", data: eq7, borderColor: "#38bdf8", borderWidth: 1.6, pointRadius: 0 }},
          {{ label: "v0.8 极限贴水底防假空", data: eq8, borderColor: "#94a3b8", borderWidth: 1.8, pointRadius: 0 }},
          {{ label: "v0.9 现货滞后治理版", data: eq9, borderColor: "#818cf8", borderWidth: 2.0, pointRadius: 0 }},
          {{ label: "v0.10 战术接入版", data: eq10, borderColor: "#06b6d4", borderWidth: 2.0, pointRadius: 0 }},
          {{ label: "v0.11 冬储成本长持版", data: eq11, borderColor: "#38bdf8", borderWidth: 2.0, pointRadius: 0 }},
          {{ label: "v0.12 期限结构微观套利版", data: eq12, borderColor: "#06b6d4", borderWidth: 2.2, pointRadius: 0 }},
          {{ label: "v0.13 低波选约版", data: eq13, borderColor: "#a78bfa", borderWidth: 2.2, pointRadius: 0 }},
          {{ label: "v0.14 跨期对冲初始版", data: eq14, borderColor: "#f59e0b", borderWidth: 2.4, pointRadius: 0 }},
          {{ label: "★ v0.15 钝化转跨期终极版", data: eq15, borderColor: "#10b981", borderWidth: 3.8, pointRadius: 0 }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: {{ mode: "index", intersect: false }},
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            backgroundColor: "rgba(11, 15, 25, 0.95)",
            callbacks: {{
              label: function(c) {{ return `${{c.dataset.label}}: ${{Math.round(c.raw)}} 万元`; }}
            }}
          }}
        }},
        scales: {{
          x: {{ grid: {{ color: "rgba(51, 65, 85, 0.25)" }}, ticks: {{ color: "#64748b", maxTicksLimit: 14 }} }},
          y: {{ position: "right", grid: {{ color: "rgba(51, 65, 85, 0.25)" }}, ticks: {{ color: "#94a3b8", callback: v => v + "万" }} }}
        }}
      }}
    }});

    // Helper: Toast notification for zoom
    let toastTimeout = null;
    function showZoomToast(text, duration = 2800) {{
      const toast = document.getElementById("priceZoomToast");
      const toastText = document.getElementById("priceZoomToastText");
      if (!toast || !toastText) return;
      toastText.innerText = text;
      toast.classList.remove("opacity-0");
      toast.classList.add("opacity-100");
      if (toastTimeout) clearTimeout(toastTimeout);
      toastTimeout = setTimeout(() => {{
        toast.classList.remove("opacity-100");
        toast.classList.add("opacity-0");
      }}, duration);
    }}

    // Helper: Zoom to Date Range
    function zoomToRange(startDate, endDate) {{
      const startIdx = dates.indexOf(startDate);
      const endIdx = dates.indexOf(endDate);
      if (startIdx !== -1 && endIdx !== -1) {{
        priceChart.zoomScale('x', {{ min: startIdx, max: endIdx }}, 'default');
        equityChart.zoomScale('x', {{ min: startIdx, max: endIdx }}, 'default');
        showZoomToast(`🔍 已缩放聚焦: ${{startDate}} ~ ${{endDate}} (双击图表可还原全景)`);
      }}
    }}

    // Helper: Setup Double-Click Zoom & Reset on Charts
    function setupDoubleClickHandler(chart, syncChart, isMatrix = false) {{
      const canvas = chart.canvas;
      if (!canvas) return;

      canvas.style.cursor = "crosshair";

      canvas.addEventListener("dblclick", function(e) {{
        e.preventDefault();

        const xScale = chart.scales.x;
        if (!xScale) return;

        const currentMin = typeof xScale.min === 'number' ? xScale.min : 0;
        const currentMax = typeof xScale.max === 'number' ? xScale.max : dates.length - 1;
        const currentSpan = currentMax - currentMin;
        const isCurrentlyZoomed = (currentMin > 3) || (currentMax < dates.length - 4) || (currentSpan < dates.length * 0.85);

        // If currently zoomed in and user double-clicks (without Shift), reset to full panoramic view!
        if (isCurrentlyZoomed && !e.shiftKey) {{
          chart.resetZoom();
          if (syncChart) syncChart.resetZoom();
          showZoomToast("🌐 已还原全历史全景图 (2018–2026)");
          return;
        }}

        // Otherwise find target data index from event or scale
        let targetIdx = -1;
        const elements = chart.getElementsAtEventForMode(e, 'index', {{ intersect: false }}, false);
        if (elements && elements.length > 0) {{
          targetIdx = elements[0].index;
        }} else {{
          const rect = canvas.getBoundingClientRect();
          const xPos = e.clientX - rect.left;
          if (xScale.left <= xPos && xPos <= xScale.right) {{
            const fraction = (xPos - xScale.left) / (xScale.right - xScale.left);
            targetIdx = Math.round(currentMin + fraction * (currentMax - currentMin));
          }} else if (typeof xScale.getValueForPixel === 'function') {{
            const v = xScale.getValueForPixel(xPos);
            if (typeof v === 'number' && !isNaN(v)) targetIdx = Math.round(v);
          }}
        }}

        if (targetIdx < 0 || targetIdx >= dates.length) return;

        // Window size: Shift + dblclick = 18 bars (~1 month deep focus), normal dblclick = 35 bars (~70 bars, ~3.5 months wave)
        const halfWindow = e.shiftKey ? 18 : 35;
        const minIdx = Math.max(0, targetIdx - halfWindow);
        const maxIdx = Math.min(dates.length - 1, targetIdx + halfWindow);

        chart.zoomScale('x', {{ min: minIdx, max: maxIdx }}, 'default');
        if (syncChart) syncChart.zoomScale('x', {{ min: minIdx, max: maxIdx }}, 'default');

        const startDate = dates[minIdx];
        const endDate = dates[maxIdx];
        const clickedDate = dates[targetIdx];
        showZoomToast(`🔍 双击已放大聚焦 [${{clickedDate}}]：${{startDate}} ~ ${{endDate}} (再次双击还原全景)`);
      }});
    }}

    // Update Counts & Badges
    function updateCounts() {{
      let activeTrades = DATA.trades_v15;
      let labelName = "★ v0.15 钝化转跨期终极版";
      if (currentVersion === 'v14') {{
        activeTrades = DATA.trades_v14;
        labelName = "v0.14 跨期对冲初始版";
      }} else if (currentVersion === 'v13') {{
        activeTrades = DATA.trades_v13;
        labelName = "v0.13 低波选约版";
      }}

      const counterTrades = activeTrades.filter(t => t.is_counter);
      document.getElementById("counterCountBadge").innerText = counterTrades.length;
      document.getElementById("displayedVersionName").innerText = labelName;
    }}

    // Render Filtered Trades Table
    function renderTradeTable() {{
      let activeTrades = DATA.trades_v15;
      if (currentVersion === 'v14') activeTrades = DATA.trades_v14;
      else if (currentVersion === 'v13') activeTrades = DATA.trades_v13;

      const tradeTableBody = document.getElementById("tradeTableBody");
      const displayedTradeCount = document.getElementById("displayedTradeCount");

      tradeTableBody.innerHTML = "";
      let count = 0;

      activeTrades.forEach(tr => {{
        // Filter by Situation Preset
        if (currentTradeFilter === 'WIN' && !tr.is_win) return;
        if (currentTradeFilter === 'COUNTER' && !tr.is_counter) return;

        // Filter by Toggle State
        if (!colorVisibility[tr.type]) return;

        // Filter by Search Query
        if (tableSearchQuery && !tr.id.toLowerCase().includes(tableSearchQuery.toLowerCase()) && !tr.entry_driver.toLowerCase().includes(tableSearchQuery.toLowerCase()) && !tr.exit_reason.toLowerCase().includes(tableSearchQuery.toLowerCase())) return;

        // Filter by Direction
        if (tableDirFilter !== 'ALL' && tr.direction !== tableDirFilter) return;

        // Filter by Year
        if (tableYearFilter !== 'ALL' && !tr.entry_date.startsWith(tableYearFilter)) return;

        count++;
        const trRow = document.createElement("tr");
        trRow.className = "hover:bg-slate-800/50 transition";

        const dirBadge = tr.direction === "LONG"
          ? '<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">LONG 多</span>'
          : '<span class="px-1.5 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30">SHORT 空</span>';

        let tagBadge = "";
        if (tr.type === "WIN_LONG") {{
          tagBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">🟢 做对·多头顺势盈利</span>';
        }} else if (tr.type === "LOSS_LONG") {{
          tagBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">🟠 做错·追高反向打损</span>';
        }} else if (tr.type === "WIN_SHORT") {{
          tagBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">🔵 做对·空头顺势盈利</span>';
        }} else {{
          tagBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-300 border border-rose-500/40">🔴 做错·杀跌反向打损</span>';
        }}

        const pnlColor = tr.pnl_wan > 0 ? "text-emerald-400 font-bold" : (tr.pnl_wan < 0 ? "text-rose-400 font-bold" : "text-slate-400");
        const retColor = tr.ret_pct > 0 ? "text-emerald-400 font-bold" : (tr.ret_pct < 0 ? "text-rose-400 font-bold" : "text-slate-400");

        trRow.innerHTML = `
          <td class="p-3 font-bold text-white font-mono">${{tr.id}}</td>
          <td class="p-3">${{dirBadge}}</td>
          <td class="p-3 font-sans">${{tagBadge}}</td>
          <td class="p-3 text-slate-300">${{tr.entry_date}} <span class="text-amber-300 font-semibold ml-1">@${{tr.entry_price}}</span></td>
          <td class="p-3 text-slate-300">${{tr.exit_date}} <span class="text-amber-300 font-semibold ml-1">@${{tr.exit_price}}</span></td>
          <td class="p-3 text-right text-slate-300 font-mono">${{tr.holding_days}}天</td>
          <td class="p-3 text-right text-slate-300 font-mono">${{tr.max_lots}}手</td>
          <td class="p-3 text-right ${{pnlColor}} font-mono">${{tr.pnl_wan > 0 ? '+' : ''}}${{tr.pnl_wan.toLocaleString()}}万</td>
          <td class="p-3 text-right ${{retColor}} font-mono">${{tr.ret_pct > 0 ? '+' : ''}}${{tr.ret_pct.toFixed(2)}}%</td>
          <td class="p-3 text-slate-300 font-sans text-[11px]">${{tr.entry_driver}}</td>
          <td class="p-3 text-slate-300 font-sans text-[11px]">${{tr.exit_reason}}</td>
          <td class="p-3 text-center">
            <button onclick="zoomToRange('${{tr.entry_date}}', '${{tr.exit_date}}')" class="px-2.5 py-1 text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-200 rounded border border-slate-700 hover:border-slate-500 transition font-sans">
              定位主图
            </button>
          </td>
        `;
        tradeTableBody.appendChild(trRow);
      }});

      displayedTradeCount.innerText = count;
    }}

    // Switch Versions inside Tab 1
    function switchVersion(ver) {{
      currentVersion = ver;
      const btn15 = document.getElementById("btnVer15");
      const btn14 = document.getElementById("btnVer14");
      const btn13 = document.getElementById("btnVer13");
      const v14Box = document.getElementById("v14NoteBox");
      const v15Box = document.getElementById("v15NoteBox");

      [btn15, btn14, btn13].forEach(b => {{
        if (b) b.className = "px-3 py-1.5 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition";
      }});

      if (ver === 'v15') {{
        if (btn15) btn15.className = "px-3 py-1.5 rounded-md font-semibold text-slate-200 transition btn-active";
        if (v15Box) v15Box.className = "bg-emerald-950/20 p-3 rounded-lg border border-emerald-500/40 flex items-start gap-3 transition ring-1 ring-emerald-500/30";
        if (v14Box) v14Box.className = "bg-slate-800/40 p-3 rounded-lg border border-slate-800 flex items-start gap-3 transition opacity-70";
      }} else if (ver === 'v14') {{
        if (btn14) btn14.className = "px-3 py-1.5 rounded-md font-semibold text-slate-200 transition btn-active";
        if (v14Box) v14Box.className = "bg-cyan-950/20 p-3 rounded-lg border border-cyan-500/40 flex items-start gap-3 transition ring-1 ring-cyan-500/30";
        if (v15Box) v15Box.className = "bg-slate-800/40 p-3 rounded-lg border border-slate-800 flex items-start gap-3 transition opacity-70";
      }} else if (ver === 'v13') {{
        if (btn13) btn13.className = "px-3 py-1.5 rounded-md font-semibold text-slate-200 transition btn-active";
        if (v15Box) v15Box.className = "bg-slate-800/40 p-3 rounded-lg border border-slate-800 flex items-start gap-3 transition opacity-70";
        if (v14Box) v14Box.className = "bg-slate-800/40 p-3 rounded-lg border border-slate-800 flex items-start gap-3 transition opacity-70";
      }}

      updateCounts();
      renderTradeTable();
      priceChart.update();
    }}

    const b15 = document.getElementById("btnVer15");
    if (b15) b15.addEventListener("click", () => switchVersion('v15'));
    const b14 = document.getElementById("btnVer14");
    if (b14) b14.addEventListener("click", () => switchVersion('v14'));
    const b13 = document.getElementById("btnVer13");
    if (b13) b13.addEventListener("click", () => switchVersion('v13'));

    // Filter Buttons Handlers
    document.getElementById("filterAll").addEventListener("click", () => applyPresetColorFilter('ALL'));
    document.getElementById("filterCounter").addEventListener("click", () => applyPresetColorFilter('COUNTER'));
    document.getElementById("filterWin").addEventListener("click", () => applyPresetColorFilter('WIN'));

    document.getElementById("tradeSearchInput").addEventListener("input", (e) => {{
      tableSearchQuery = e.target.value.trim();
      renderTradeTable();
    }});

    document.getElementById("tradeDirFilter").addEventListener("change", (e) => {{
      tableDirFilter = e.target.value;
      renderTradeTable();
    }});

    document.getElementById("tradeYearFilter").addEventListener("change", (e) => {{
      tableYearFilter = e.target.value;
      renderTradeTable();
    }});

    document.getElementById("resetZoomBtn").addEventListener("click", () => {{
      priceChart.resetZoom();
      equityChart.resetZoom();
      showZoomToast("🌐 已重置为主连全景视野 (2018–2026)");
    }});

    // Setup Double-Click Zoom on all panoramic charts
    setupDoubleClickHandler(priceChart, equityChart);
    setupDoubleClickHandler(equityChart, priceChart);
    setupDoubleClickHandler(matrixEquityChart, null, true);

    // Initial Execution
    updateToggleButtonsUI();
    updateCounts();
    renderTradeTable();
  </script>
</body>
</html>
"""
    for out in output_paths:
        Path(out).write_text(html_content, encoding="utf-8")
        print(f"[+] 成功写入统一看板: {out}")

if __name__ == "__main__":
    data = load_all_versions_data()
    
    outputs = [
        # 1. 项目根目录统一文件
        ROOT / "rebar_backtest_comparison.html",
        # 2. 项目标准实验目录统一文件
        ROOT / "研究/回测实验/rebar_backtest_comparison.html",
        # 3. 最新版本专属命名
        ROOT / "rebar_backtest_v14_vs_v15_comparison.html",
        # 4. 最新与历史实验独立归档目录
        PATH_V15 / "rebar_backtest_comparison.html",
        PATH_V15 / "rebar_backtest_v14_vs_v15_comparison.html",
        PATH_V14 / "rebar_backtest_comparison.html",
        PATH_V14 / "rebar_backtest_v13_vs_v14_comparison.html",
        PATH_V13 / "rebar_backtest_comparison.html",
        PATH_V13 / "rebar_backtest_v12_vs_v13_comparison.html",
        PATH_V12 / "rebar_backtest_comparison.html",
        PATH_V12 / "rebar_backtest_v11_vs_v12_comparison.html",
        PATH_V11 / "rebar_backtest_comparison.html",
        PATH_V11 / "rebar_backtest_v10_vs_v11_comparison.html",
        PATH_V10 / "rebar_backtest_comparison.html",
        PATH_V10 / "rebar_backtest_v9_vs_v10_comparison.html",
        PATH_V9 / "rebar_backtest_comparison.html",
        PATH_V9 / "rebar_backtest_v8_vs_v9_comparison.html",
    ]
    generate_unified_html(data, outputs)
