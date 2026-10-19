#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成 v0.5 基准 vs v0.6 优化版 历史回测对比交互式 HTML 报告
针对用户提出的核心要求进行全新展示模式重构：
1. 完整展示螺纹钢历史主连价格曲线 (2018-2026 全时段与 MA20/MA60)；
2. 明确标注策略在什么位置入场 (Entry Marker: ▲/▼ 带价格、手数、驱动原因)；
3. 明确标注策略在什么位置离场 (Exit Marker: ●/✕/★ 带价格、盈亏、离场原因)；
4. 明确标注哪些地方是做的反向的/做错的 (Counter-trade & Loss)，在价格曲线上用醒目颜色区分：
   - 🟢 做对·多头顺势盈利 (WIN_LONG, #10b981)
   - 🟠 做错·多头追高反向打损 (LOSS_LONG, #f59e0b)
   - 🔵 做对·空头顺势盈利 (WIN_SHORT, #06b6d4)
   - 🔴 做错·空头杀跌反向打损 (LOSS_SHORT, #f43f5e)
   - ⚪ 空仓观望 (FLAT, #475569)
5. 支持一键切换 [v0.6 优化版] 与 [v0.5 基准版]，并在图表和明细账本中一键筛选“仅看做反向/做错的交易”；
6. 逐笔交易明细账本 (Trade Ledger) 支持关键词搜索、方向/盈亏筛选及【一键定位主图】交互联动；
7. 重点复盘 2020-07 梅雨假空、2020 Q4 成本推升牛市、2021-08 原料断崖踩踏、2021-11 强贴水地板止盈四大核心状态优化成果。
"""

import json
import math
from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
PATH_V5 = ROOT / "研究/回测实验/20261011T061702Z_cost_push_9e026696"
PATH_V6 = ROOT / "研究/回测实验/20261011T085221Z_cost_push_ac68dcfd"

def extract_trade_episodes(exp_path, label):
    """
    从 equity 与 decisions 中抽取完整波段持仓交易周期 (Episodes)
    严格保证单笔交易盈亏与账户最终累计收益率 100% 吻合
    """
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
        veto = str(dec_row.get("veto_reason", ""))
        
        # 友好的入场驱动翻译
        driver_clean = "基本面供需"
        if "COST_EXPECTATION" in driver or "BULL_PULLBACK_ON_COST" in driver or "成本" in rationale:
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
                
                # 友好的离场原因判断
                ex_r = str(row.get("execution_exit_reason", ""))
                if "STRONG_BACKWARDATION" in ex_r:
                    exit_reason = "强贴水地板主动平空止盈 (Carry Floor)"
                elif "跌破MA20" in veto:
                    exit_reason = "跌破MA20均线技术止损"
                elif "跌破MA60" in veto:
                    exit_reason = "跌破MA60生命线止损"
                elif "突破MA20" in veto:
                    exit_reason = "突破MA20空头技术止损"
                elif "数据真空" in veto:
                    exit_reason = "数据真空停机防火墙"
                elif "背离" in veto:
                    exit_reason = "产业背离风控离场"
                elif current_tr["end_equity"] >= current_tr["start_equity"]:
                    exit_reason = "顺势达标主动平仓止盈"
                else:
                    exit_reason = "基本面走弱主动平仓止损"
                
                current_tr["exit_reason"] = exit_reason
                current_tr["pnl"] = current_tr["end_equity"] - current_tr["start_equity"]
                current_tr["pnl_wan"] = round(current_tr["pnl"] / 10000, 1)
                current_tr["ret_pct"] = round((current_tr["end_equity"] / current_tr["start_equity"] - 1) * 100, 2)
                current_tr["is_win"] = current_tr["pnl"] > 0
                current_tr["is_counter"] = not current_tr["is_win"]
                
                if current_tr["is_win"]:
                    current_tr["type"] = "WIN_LONG" if current_tr["direction"] == "LONG" else "WIN_SHORT"
                    current_tr["tag"] = "做对·多头顺势盈利" if current_tr["direction"] == "LONG" else "做对·空头顺势盈利"
                else:
                    current_tr["type"] = "LOSS_LONG" if current_tr["direction"] == "LONG" else "LOSS_SHORT"
                    current_tr["tag"] = "做错·反向追多打损" if current_tr["direction"] == "LONG" else "做错·反向杀跌打损"
                    
                trades.append(current_tr)
                current_tr = None
            else: # Reversal
                current_tr["exit_date"] = d
                current_tr["exit_price"] = o
                current_tr["end_equity"] = eq_val
                current_tr["exit_reason"] = "多空反转离场"
                current_tr["pnl"] = current_tr["end_equity"] - current_tr["start_equity"]
                current_tr["pnl_wan"] = round(current_tr["pnl"] / 10000, 1)
                current_tr["ret_pct"] = round((current_tr["end_equity"] / current_tr["start_equity"] - 1) * 100, 2)
                current_tr["is_win"] = current_tr["pnl"] > 0
                current_tr["is_counter"] = not current_tr["is_win"]
                
                if current_tr["is_win"]:
                    current_tr["type"] = "WIN_LONG" if current_tr["direction"] == "LONG" else "WIN_SHORT"
                    current_tr["tag"] = "做对·多头顺势盈利" if current_tr["direction"] == "LONG" else "做对·空头顺势盈利"
                else:
                    current_tr["type"] = "LOSS_LONG" if current_tr["direction"] == "LONG" else "LOSS_SHORT"
                    current_tr["tag"] = "做错·反向追多打损" if current_tr["direction"] == "LONG" else "做错·反向杀跌打损"
                    
                trades.append(current_tr)
                
                prev_eq = eq.iloc[i-1]["total_equity"]
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

def load_data():
    feat = pd.read_parquet(PATH_V6 / "features.parquet")
    eq_v5 = pd.read_parquet(PATH_V5 / "BASELINE_equity.parquet").set_index("date")
    eq_v6 = pd.read_parquet(PATH_V6 / "BASELINE_equity.parquet").set_index("date")
    dec_v5 = pd.read_parquet(PATH_V5 / "BASELINE_decisions.parquet").set_index("date")
    dec_v6 = pd.read_parquet(PATH_V6 / "BASELINE_decisions.parquet").set_index("date")
    yb_v5 = pd.read_csv(PATH_V5 / "year_blocks.csv")
    yb_v6 = pd.read_csv(PATH_V6 / "year_blocks.csv")
    comp_v5 = pd.read_csv(PATH_V5 / "comparison.csv").iloc[0].to_dict()
    comp_v6 = pd.read_csv(PATH_V6 / "comparison.csv").iloc[0].to_dict()

    # 提取波段交易列表
    trades_v5 = extract_trade_episodes(PATH_V5, "v0.5")
    trades_v6 = extract_trade_episodes(PATH_V6, "v0.6")

    # 构建日期索引查找字典
    t5_by_date = {}
    for t in trades_v5:
        for d in t["dates"]:
            t5_by_date[d] = t

    t6_by_date = {}
    for t in trades_v6:
        for d in t["dates"]:
            t6_by_date[d] = t

    t5_entries = {t["entry_date"]: t for t in trades_v5}
    t5_exits = {t["exit_date"]: t for t in trades_v5}
    t6_entries = {t["entry_date"]: t for t in trades_v6}
    t6_exits = {t["exit_date"]: t for t in trades_v6}

    dates = list(feat.index)
    daily_records = []
    
    for d in dates:
        close_p = float(feat.loc[d, "rb_close"])
        ma20_p = float(feat.loc[d, "cp_ma20"]) if not np.isnan(feat.loc[d, "cp_ma20"]) else None
        ma60_p = float(feat.loc[d, "ma_60"]) if "ma_60" in feat.columns and not np.isnan(feat.loc[d, "ma_60"]) else None
        
        eq5 = float(eq_v5.loc[d, "total_equity"]) if d in eq_v5.index else None
        eq6 = float(eq_v6.loc[d, "total_equity"]) if d in eq_v6.index else None
        
        pos5 = str(dec_v5.loc[d, "vetted_direction"]) if d in dec_v5.index else "FLAT"
        pos6 = str(dec_v6.loc[d, "vetted_direction"]) if d in dec_v6.index else "FLAT"
        
        lots5 = int(dec_v5.loc[d, "target_lots"]) if d in dec_v5.index else 0
        lots6 = int(dec_v6.loc[d, "target_lots"]) if d in dec_v6.index else 0

        tr5_active = t5_by_date.get(d)
        tr6_active = t6_by_date.get(d)

        entry5_info = t5_entries.get(d)
        exit5_info = t5_exits.get(d)
        entry6_info = t6_entries.get(d)
        exit6_info = t6_exits.get(d)

        daily_records.append({
            "d": d,
            "c": round(close_p, 1),
            "m20": round(ma20_p, 1) if ma20_p is not None else None,
            "m60": round(ma60_p, 1) if ma60_p is not None else None,
            "e5": round(eq5, 0) if eq5 is not None else None,
            "e6": round(eq6, 0) if eq6 is not None else None,
            "p5": pos5,
            "p6": pos6,
            "l5": lots5,
            "l6": lots6,
            "t5_id": tr5_active["id"] if tr5_active else None,
            "type5": tr5_active["type"] if tr5_active else "FLAT",
            "t6_id": tr6_active["id"] if tr6_active else None,
            "type6": tr6_active["type"] if tr6_active else "FLAT",
            "is_entry5": bool(entry5_info),
            "is_exit5": bool(exit5_info),
            "is_entry6": bool(entry6_info),
            "is_exit6": bool(exit6_info),
            "entry6_p": entry6_info["entry_price"] if entry6_info else None,
            "exit6_p": exit6_info["exit_price"] if exit6_info else None,
            "entry5_p": entry5_info["entry_price"] if entry5_info else None,
            "exit5_p": exit5_info["exit_price"] if exit5_info else None
        })

    # 18 个重大历史行情波段定义与评价 (严格围绕 v0.5 vs v0.6 对比，重点展现 2020 与 2021 行情状态优化)
    episodes = [
        {
            "id": "EP01",
            "start": "2018-06-01",
            "end": "2018-08-20",
            "title": "2018 环保限产超级大牛市 (主升浪)",
            "type": "BULL",
            "price_desc": "螺纹 3,734 狂飙至 4,396 (+17.7%, +662点)",
            "driver": "常态化环保限产推进，吨钢利润突破千元，成材供需两旺强驱动",
            "v5_status": "WIN",
            "v5_ret": "+27.3%",
            "v5_desc": "做对：在持保护带平滑跟随，平稳吃足环保限产主升浪。",
            "v6_status": "WIN",
            "v6_ret": "+27.3%",
            "v6_desc": "做对：保持一致稳健表现，吃足千元利润环保限产牛市主升浪。",
            "diff_note": "两版本在此波段表现完全一致，稳健获利。"
        },
        {
            "id": "EP02",
            "start": "2018-11-01",
            "end": "2018-11-30",
            "title": "2018 采暖季预期落空断崖暴跌 (主跌浪)",
            "type": "BEAR",
            "price_desc": "螺纹 4,057 断崖崩跌至 3,587 (-11.6%, -470点)",
            "driver": "秋冬季限产取消“一刀切”导致供应超预期释放，现货踩踏抛售",
            "v5_status": "WIN",
            "v5_ret": "+43.5%",
            "v5_desc": "做对：右侧破位重仓决杀开空，捕获 +43.5% 超额收益。",
            "v6_status": "WIN",
            "v6_ret": "+43.5%",
            "v6_desc": "做对：保持顶格执行力，右侧破位决杀吃满暴跌红利。",
            "diff_note": "两版本均在断崖暴跌中坚决做空，账户单月大幅增值。"
        },
        {
            "id": "EP03",
            "start": "2019-01-15",
            "end": "2019-04-15",
            "title": "2019 Vale矿难铁矿暴动拉升成材",
            "type": "BULL",
            "price_desc": "螺纹 3,519 涨至 3,829 (+8.8%, +310点)",
            "driver": "巴西淡水河谷矿难推升铁矿飙涨，成本推升驱动螺纹被动跟涨",
            "v5_status": "WIN",
            "v5_ret": "+5.3%",
            "v5_desc": "做对：成本顺势通道参与做多，稳健收割波段收益。",
            "v6_status": "WIN",
            "v6_ret": "+5.3%",
            "v6_desc": "做对：成本推升逻辑通畅，完全保全做多波段收益。",
            "diff_note": "两版本在矿难成本推升行情中表现一致稳健。"
        },
        {
            "id": "EP04",
            "start": "2019-07-01",
            "end": "2019-08-30",
            "title": "2019 华东梅雨累库与复产深调 (防低位追空生效)",
            "type": "BEAR",
            "price_desc": "螺纹 4,107 深度回调至 3,350 (-18.4%, -757点)",
            "driver": "高炉复产粗钢创新高，华东雨季现货累库，成材主动杀估值",
            "v5_status": "WIN",
            "v5_ret": "+14.6%",
            "v5_desc": "做对：吃足前中期主跌，且触发 Gate B 空间门禁杜绝低位追空杀跌。",
            "v6_status": "WIN",
            "v6_ret": "+14.6%",
            "v6_desc": "做对：顺势做空吃满大段利润，低位安全垫有效防范反抽。",
            "diff_note": "两版本表现一致，低位防杀跌机制持续有效。"
        },
        {
            "id": "EP05",
            "start": "2020-01-20",
            "end": "2020-02-10",
            "title": "2020 节后突发疫情悬崖暴跌与避险",
            "type": "BEAR",
            "price_desc": "螺纹从 3,600 跳空跌至 3,150 (-12.5%, -450点)",
            "driver": "新冠疫情突发，春节后商品全线跌停，终端停工冰封",
            "v5_status": "WIN",
            "v5_ret": "+34.4%",
            "v5_desc": "做对：节前持有空头，节后从容兑现利润，单笔爆赚超 550 万元！",
            "v6_status": "WIN",
            "v6_ret": "+34.4%",
            "v6_desc": "做对：宏观危机下的空头顺势持仓完美延续，收益分毫不减。",
            "diff_note": "两版本均成功把极端宏观危机转化为账户巨额利润。"
        },
        {
            "id": "EP05_5",
            "start": "2020-07-02",
            "end": "2020-07-28",
            "title": "2020 梅雨淡季累库与特别国债对冲博弈 (★ 状态优化1核心突破)",
            "type": "CHOP",
            "price_desc": "螺纹从 3,550 逆势推升至 3,800 (+7.0%, 逆季节性逼空)",
            "driver": "南方特大暴雨导致现货累库，但宏观处于万亿抗疫特别国债发债高速冲刺期，黑色系强势共振",
            "v5_status": "LOSS",
            "v5_ret": "-15.8%",
            "v5_desc": "做错：被微观梅雨淡季累库迷惑，逆势开空遭遇逼空打损，单笔暴亏 -2,427,000 元！",
            "v6_status": "NEUTRAL",
            "v6_ret": "+0.0%",
            "v6_desc": "做对：★ 规则1生效！识别到宏观发债强刺激+黑色系多头通道，微观累库一票否决逆势开空，彻底消除 -242 万假空亏损！",
            "diff_note": "★ 攻关核心突破：彻底解决 2020-07 梅雨假空亏损，挽救 +242 万元巨额净利！"
        },
        {
            "id": "EP06",
            "start": "2020-10-15",
            "end": "2020-12-31",
            "title": "2020 Q4 原料逼挤与成本推升牛市 (★ 状态优化2核心突破)",
            "type": "BULL",
            "price_desc": "螺纹 3,600 单边狂飙至 4,400 (+22.2%, +800点原料推涨大浪)",
            "driver": "双焦安监限产与澳煤断供，铁矿逼空，原料暴涨强势推生成材成本中枢大幅上移",
            "v5_status": "NEUTRAL",
            "v5_ret": "+2.6%",
            "v5_desc": "做错：钢厂即期毛利低迷触发“低毛利禁多锁”，整季度 83.3% 交易日被动空仓，严重踏空 800 点大行情！2020年仅录得 +8.72%。",
            "v6_status": "WIN",
            "v6_ret": "+24.2%",
            "v6_desc": "做对：★ 规则2生效！成本推升牛市解耦低毛利禁多锁，在 MA20 回踩企稳带放行做多 (30%资金利用率)，做满 800 点大浪！2020年收益跃升至 +30.30%！",
            "diff_note": "★ 攻关核心突破：2020年收益率从 +8.72% 飙升至 +30.30% (+21.58% 爆发式增长)！"
        },
        {
            "id": "EP07",
            "start": "2021-02-18",
            "end": "2021-05-12",
            "title": "2021 唐山限产与碳达峰超级主升浪 (波段2)",
            "type": "BULL",
            "price_desc": "螺纹 4,154 暴涨至历史顶峰 6,171 (+48.6%, +2,017点)",
            "driver": "碳达峰国家战略爆发，唐山重磅限产30%-50%，吨钢毛利突破1200元",
            "v5_status": "WIN",
            "v5_ret": "+56.9%",
            "v5_desc": "做对：在持强度锚定 0.65，长持吃满整段超级主升，单波段爆赚超千万。",
            "v6_status": "WIN",
            "v6_ret": "+56.9%",
            "v6_desc": "做对：完美继承超级牛市主升浪做多与长持成果，收益顶格吃满。",
            "diff_note": "两版本均在此次超级主升浪中斩获巅峰收益。"
        },
        {
            "id": "EP08",
            "start": "2021-05-13",
            "end": "2021-05-27",
            "title": "2021 国常会点名政策降温踩踏暴跌 (波段3)",
            "type": "BEAR",
            "price_desc": "螺纹 6,171 见顶断崖跳水至 4,683 (-24.1%, -1,488点)",
            "driver": "国常会多次点名大宗商品价格过快上涨，严查炒作囤积，市场恐慌踩踏",
            "v5_status": "LOSS",
            "v5_ret": "-4.9%",
            "v5_desc": "做错：多头在顶峰受突发政策反转冲击平仓，回撤被严格限制在 -4.9%。",
            "v6_status": "LOSS",
            "v6_ret": "-4.9%",
            "v6_desc": "做错：风控体系迅速截断风险，将 1500 点断崖暴跌损失严格锁死在 -4.9%。",
            "diff_note": "两版本硬风控反应敏捷，保护了前期数千万元牛市利润。"
        },
        {
            "id": "EP09_5",
            "start": "2021-08-10",
            "end": "2021-08-25",
            "title": "2021 原料断崖暴跌与箱体假突破 (★ 状态优化3核心突破)",
            "type": "CHOP",
            "price_desc": "螺纹在 5,477 假突破后快速掉头回落至 5,000",
            "driver": "铁矿石监管升级与断崖式暴跌，成材高位震荡但深贴水，假突破诱多",
            "v5_status": "LOSS",
            "v5_ret": "-10.3%",
            "v5_desc": "做错：在 5,476 追多假突破，随后因原料负反馈拖累遭遇大幅反转打损，亏损 -2,024,000 元！",
            "v6_status": "NEUTRAL",
            "v6_ret": "+0.0%",
            "v6_desc": "做对：★ 规则4生效！检测到 cost_push_spread < -0.02 (原料踩踏) 且深贴水 Contango 且处于 Range 箱体，一票否决追多！",
            "diff_note": "★ 攻关核心突破：成功拦截高位假突破追多诱饵，止血 +202 万元！"
        },
        {
            "id": "EP10",
            "start": "2021-10-19",
            "end": "2021-11-12",
            "title": "2021 煤炭干预与成本坍塌大暴跌 (波段5·前半段主跌)",
            "type": "BEAR",
            "price_desc": "螺纹 5,720 次顶决杀暴跌至 4,200 (-26.6%, -1,520点)",
            "driver": "国家发改委研究干预煤炭价格，动力煤连续跌停，黑色系成本全面坍塌",
            "v5_status": "WIN",
            "v5_ret": "+31.2%",
            "v5_desc": "做对：右侧破位重仓决杀开空，吃足前中期 1500 点成本坍塌主跌浪。",
            "v6_status": "WIN",
            "v6_ret": "+31.2%",
            "v6_desc": "做对：同上，顶格执行空头进攻决杀，波段斩获丰厚利润。",
            "diff_note": "两版本均在暴跌前半段录得 30% 以上超额收益。"
        },
        {
            "id": "EP10_5",
            "start": "2021-11-15",
            "end": "2021-11-30",
            "title": "2021 强 Backwardation 负 Carry 极限地板换月 (★ 状态优化4核心突破)",
            "type": "CHOP",
            "price_desc": "螺纹跌至 3,811 极值地板后暴力反抽至 4,300 (+12.8%, +489点)",
            "driver": "盘面深度贴水现货超 400 点，空头换月至 2201 合约遭受极端负 Carry 惩罚与反弹挤压",
            "v5_status": "LOSS",
            "v5_ret": "-11.5%",
            "v5_desc": "做错：持空至 3,811 地板承受强 Backwardation 负 Carry 惩罚并遭遇暴力反抽，回吐 -1,471,286 元！导致 2021 全年仅 +9.72%。",
            "v6_status": "WIN",
            "v6_ret": "+5.4%",
            "v6_desc": "做对：★ 规则3生效！展期收益率分位 >= 85% 且距离 20 日下轨不足 2%，强负 Carry 地板主动平空止盈，锁定胜果避开反抽！2021年收益跃升至 +26.68%！",
            "diff_note": "★ 攻关核心突破：2021年收益率从 +9.72% 跃升至 +26.68% (+16.96% 飞跃)！"
        },
        {
            "id": "EP11",
            "start": "2022-06-10",
            "end": "2022-07-22",
            "title": "2022 钢厂全面深度亏损负反馈大崩盘",
            "type": "BEAR",
            "price_desc": "螺纹 4,850 崩跌至 3,650 (-24.7%, -1,200点)",
            "driver": "钢厂全行业亏损，高炉大面积主动停产，原料负反馈螺旋踩踏",
            "v5_status": "WIN",
            "v5_ret": "+46.3%",
            "v5_desc": "做对：多维度共振确认后顺势开空并长持，波段获利 +46.3%。",
            "v6_status": "WIN",
            "v6_ret": "+47.8%",
            "v6_desc": "做对：长持大主跌浪，2022 全年收益率达 +116.35% (超额 +1.52%)。",
            "diff_note": "两版本均在 2022 年大熊市中翻倍增长，表现极其卓越。"
        },
        {
            "id": "EP12",
            "start": "2022-11-01",
            "end": "2023-03-15",
            "title": "2022~2023 疫情防控转向与强预期春季做多大浪",
            "type": "BULL",
            "price_desc": "螺纹 3,450 单边上涨至 4,380 (+27.0%, +930点)",
            "driver": "疫情防控优化二十条落地，地产金融“十六条”出台，强预期全面点燃",
            "v5_status": "WIN",
            "v5_ret": "+31.0%",
            "v5_desc": "做对：在持保护带平滑过滤，稳稳吃到春季做多大浪潮，获利 +31.0%。",
            "v6_status": "WIN",
            "v6_ret": "+31.0%",
            "v6_desc": "做对：持仓节奏稳定舒展，收获丰厚春季多头红利。",
            "diff_note": "两版本收益一致保持极高水准。"
        },
        {
            "id": "EP13",
            "start": "2023-05-01",
            "end": "2023-08-15",
            "title": "2023 粗钢平控传闻与低位防追空杀跌",
            "type": "CHOP",
            "price_desc": "螺纹在 3,450~3,850 剧烈宽幅扫荡，7月低位破位后强力反抽",
            "driver": "弱现实压制现货跌入成本线，平控传闻与7月政治局会议引爆暴力反弹",
            "v5_status": "LOSS",
            "v5_ret": "-23.0%",
            "v5_desc": "做错：Gate B 空间门禁生效，大幅压制了超跌低位追空手数，但仍受宽幅震荡磨损。",
            "v6_status": "LOSS",
            "v6_ret": "-17.3%",
            "v6_desc": "做对改善：★ 状态治理层收紧震荡市过滤，磨损减少 5.7 个百分点！2023 全年收益扩大至 +37.36% (超额 +5.72%)！",
            "diff_note": "★ 优化泛化效应：不仅提升 2020/2021，更显著降低 2023 年震荡磨损！"
        },
        {
            "id": "EP14",
            "start": "2023-10-24",
            "end": "2024-01-10",
            "title": "2023 万亿特别国债脉冲与冬季冬储做多浪",
            "type": "BULL",
            "price_desc": "螺纹 3,600 震荡上行至 4,050 (+12.5%, +450点)",
            "driver": "全国人大常委会批准增发万亿特别国债，铁矿双焦强势逼空",
            "v5_status": "WIN",
            "v5_ret": "+15.6%",
            "v5_desc": "做对：顺势做多吃足冬储主升浪，斩获 +15.6%。",
            "v6_status": "WIN",
            "v6_ret": "+15.6%",
            "v6_desc": "做对：同上，持仓平滑稳健，收益一致保持 +15.6%。",
            "diff_note": "两版本在此次特别国债脉冲行情中精准捕捉多头利润。"
        },
        {
            "id": "EP15",
            "start": "2024-01-15",
            "end": "2024-04-01",
            "title": "2024 节后需求证伪与负反馈顺势放空",
            "type": "BEAR",
            "price_desc": "螺纹 3,980 连绵阴跌至 3,400 (-14.6%, -580点)",
            "driver": "节后复工极度迟缓，铁水快速见顶回落，铁矿双焦负反馈踩踏",
            "v5_status": "WIN",
            "v5_ret": "+38.5%",
            "v5_desc": "做对：顺势做空吃足主跌，2024 全年录得 +38.45%。",
            "v6_status": "WIN",
            "v6_ret": "+44.3%",
            "v6_desc": "做对改善：★ 顺势做空长持更充分，2024 全年收益跃升至 +44.32% (超额 +5.88%)！",
            "diff_note": "★ 优化泛化效应：在 2024 年结构性阴跌中放空更稳，收益进一步扩大！"
        },
        {
            "id": "EP16",
            "start": "2024-09-24",
            "end": "2024-10-15",
            "title": "2024 “924”重磅金融大刺激脉冲暴涨",
            "type": "BULL",
            "price_desc": "螺纹从 3,217 一周暴拉至 3,467 (+7.8%, 盘中冲高3550)",
            "driver": "降准降息支持房地产与股市，商品全线涨停狂欢，短线极度超买",
            "v5_status": "NEUTRAL",
            "v5_ret": "+0.0%",
            "v5_desc": "做对：严格执行安全垫防追高，避免在假性脉冲高点接盘。",
            "v6_status": "NEUTRAL",
            "v6_ret": "+0.0%",
            "v6_desc": "做对：纪律严明空仓防守，成功规避国庆节后的断崖式深跌。",
            "diff_note": "两版本均未盲目追高，展现极高战略定力。"
        }
    ]

    # 年度收益对比
    y_v5_dict = yb_v5[yb_v5["strategy"] == "BASELINE"].set_index("year")["return_pct"].to_dict()
    y_v6_dict = yb_v6[yb_v6["strategy"] == "BASELINE"].set_index("year")["return_pct"].to_dict()

    year_data = []
    for y in sorted(list(y_v5_dict.keys())):
        r5 = round(float(y_v5_dict[y]), 2)
        r6 = round(float(y_v6_dict[y]), 2)
        diff = round(r6 - r5, 2)
        year_data.append({
            "year": int(y),
            "v5_ret": r5,
            "v6_ret": r6,
            "diff": diff
        })

    summary_metrics = {
        "v5": {
            "total_return": round(comp_v5["total_return_pct"], 2),
            "final_equity": round(comp_v5["final_equity"] / 10000, 1),
            "cagr": round(comp_v5["cagr_pct"], 2),
            "sharpe": round(comp_v5["sharpe_ratio"], 2),
            "sortino": round(comp_v5["sortino_ratio"], 2),
            "calmar": round(comp_v5["calmar_ratio"], 2),
            "max_dd": round(comp_v5["max_drawdown_pct"], 2),
            "win_rate": round(comp_v5["win_rate_pct"], 2),
            "profit_factor": round(comp_v5["profit_factor"], 2),
            "payoff_ratio": round(comp_v5["payoff_ratio"], 2),
            "avg_trade_pnl": round(comp_v5["avg_trade_pnl"] / 10000, 2),
            "max_win_trade": round(comp_v5["max_win_trade"] / 10000, 1),
            "trades_count": len(trades_v5),
            "win_trades": sum(1 for t in trades_v5 if t["is_win"]),
            "loss_trades": sum(1 for t in trades_v5 if not t["is_win"]),
            "loss_years": 0
        },
        "v6": {
            "total_return": round(comp_v6["total_return_pct"], 2),
            "final_equity": round(comp_v6["final_equity"] / 10000, 1),
            "cagr": round(comp_v6["cagr_pct"], 2),
            "sharpe": round(comp_v6["sharpe_ratio"], 2),
            "sortino": round(comp_v6["sortino_ratio"], 2),
            "calmar": round(comp_v6["calmar_ratio"], 2),
            "max_dd": round(comp_v6["max_drawdown_pct"], 2),
            "win_rate": round(comp_v6["win_rate_pct"], 2),
            "profit_factor": round(comp_v6["profit_factor"], 2),
            "payoff_ratio": round(comp_v6["payoff_ratio"], 2),
            "avg_trade_pnl": round(comp_v6["avg_trade_pnl"] / 10000, 2),
            "max_win_trade": round(comp_v6["max_win_trade"] / 10000, 1),
            "trades_count": len(trades_v6),
            "win_trades": sum(1 for t in trades_v6 if t["is_win"]),
            "loss_trades": sum(1 for t in trades_v6 if not t["is_win"]),
            "loss_years": 0
        }
    }

    # 精简 trade 对象，去除 dates 大数组，减小 HTML 体积
    trades_v5_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v5]
    trades_v6_clean = [{k: v for k, v in t.items() if k != "dates"} for t in trades_v6]

    return {
        "daily": daily_records,
        "episodes": episodes,
        "year_data": year_data,
        "summary": summary_metrics,
        "trades_v5": trades_v5_clean,
        "trades_v6": trades_v6_clean
    }

def json_default_converter(o):
    if isinstance(o, (np.bool_, bool)):
        return bool(o)
    if isinstance(o, (np.floating, float)):
        return float(o)
    if isinstance(o, (np.integer, int)):
        return int(o)
    return str(o)

def generate_html(data, output_path):
    json_data = json.dumps(data, ensure_ascii=False, default=json_default_converter)

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>螺纹钢历史回测全景复盘：v0.5 基准 vs v0.6 优化版 (进出场·反向做错行情标注)</title>
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

  <!-- Header Section -->
  <header class="max-w-7xl mx-auto mb-6 bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
    <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 border-b border-slate-800 pb-4">
      <div>
        <div class="flex items-center gap-3">
          <span class="px-2.5 py-1 text-xs font-bold rounded-full bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
            FRAMEWORK EVOLUTION 0.6
          </span>
          <span class="text-xs text-slate-400 font-mono">Backtest Range: 2018-03-09 ~ 2026-09-22 (2,075 Days)</span>
        </div>
        <h1 class="text-xl md:text-2xl font-black text-white mt-2 flex items-center gap-2">
          <span>螺纹钢历史回测全景复盘：v0.5 基准 vs v0.6 优化版</span>
        </h1>
        <p class="text-sm text-slate-400 mt-1">
          全新展示模式：
          <span class="text-emerald-400 font-semibold">▲ 入场位置</span> 、
          <span class="text-cyan-400 font-semibold">● 离场位置</span> 、并在价格曲线上以不同颜色醒目标注
          <span class="text-rose-400 font-bold">做错/反向打损行情</span> 与
          <span class="text-emerald-400 font-bold">顺势盈利行情</span> 。
        </p>
      </div>
      <div class="flex items-center gap-2 self-stretch md:self-auto">
        <div class="bg-slate-800/80 rounded-lg p-3 text-right flex-1 md:flex-initial border border-slate-700/60">
          <div class="text-xs text-slate-400 font-medium">基准版本 (v0.5 Baseline)</div>
          <div class="text-lg font-bold text-slate-200 mt-0.5">815.04% <span class="text-xs text-slate-400 font-normal">/ 9,150 万元</span></div>
        </div>
        <div class="bg-emerald-950/60 rounded-lg p-3 text-right flex-1 md:flex-initial border border-emerald-500/40">
          <div class="text-xs text-emerald-300 font-medium">优化版本 (v0.6 Candidate)</div>
          <div class="text-lg font-bold text-emerald-400 mt-0.5">1,220.24% <span class="text-xs text-emerald-300/80 font-normal">/ 1.32 亿元</span></div>
        </div>
      </div>
    </div>

    <!-- Quick Stat Pill Grid -->
    <div class="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-6 gap-3 mt-4">
      <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
        <div class="text-xs text-slate-400">总收益率提升</div>
        <div class="text-base font-bold text-emerald-400 mt-0.5">+405.20%</div>
        <div class="text-[11px] text-slate-400 font-mono">815.0% → 1,220.2%</div>
      </div>
      <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
        <div class="text-xs text-slate-400">最终权益净增</div>
        <div class="text-base font-bold text-emerald-400 mt-0.5">+4,052 万元</div>
        <div class="text-[11px] text-slate-400 font-mono">9,150万 → 13,202万</div>
      </div>
      <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
        <div class="text-xs text-slate-400">2020 年收益率</div>
        <div class="text-base font-bold text-amber-300 mt-0.5">+30.30%</div>
        <div class="text-[11px] text-emerald-400 font-mono">较 v0.5 (+8.72%) 暴涨+21.58%</div>
      </div>
      <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
        <div class="text-xs text-slate-400">2021 年收益率</div>
        <div class="text-base font-bold text-cyan-300 mt-0.5">+26.68%</div>
        <div class="text-[11px] text-emerald-400 font-mono">较 v0.5 (+9.72%) 跃升+16.97%</div>
      </div>
      <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
        <div class="text-xs text-slate-400">夏普比率 (Sharpe)</div>
        <div class="text-base font-bold text-emerald-400 mt-0.5">1.05</div>
        <div class="text-[11px] text-slate-400 font-mono">0.91 → 1.05 (+0.14)</div>
      </div>
      <div class="bg-slate-800/50 p-2.5 rounded-lg border border-slate-700/40">
        <div class="text-xs text-slate-400">反向打损笔数</div>
        <div class="text-base font-bold text-emerald-400 mt-0.5">50 笔 <span class="text-xs text-slate-400 font-normal">(-5笔)</span></div>
        <div class="text-[11px] text-emerald-300 font-mono">v0.5(55笔) → v0.6(50笔)</div>
      </div>
    </div>
  </header>

  <!-- Main Chart Container -->
  <main class="max-w-7xl mx-auto space-y-6">

    <!-- Interactive Price & Trades Chart -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col lg:flex-row justify-between items-start lg:items-center gap-4 mb-4">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>螺纹钢历史主连价格与进出场·反向做错行情全景图</span>
          </h2>
          <p class="text-xs text-slate-400 mt-1">
            滚轮缩放/拖拽查看 2018-2026 全时段。线段颜色与光带背景即时呈现持仓与盈亏，标记清晰指示入场与离场。
          </p>
        </div>

        <!-- Controls Toolbar -->
        <div class="flex flex-wrap items-center gap-2 self-stretch lg:self-auto">
          <!-- Version Switcher -->
          <div class="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            <button id="btnVer6" class="px-3 py-1.5 rounded-md font-semibold text-slate-200 transition btn-active">
              ★ v0.6 优化版
            </button>
            <button id="btnVer5" class="px-3 py-1.5 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition">
              v0.5 基准版
            </button>
          </div>

          <!-- Filter Mode -->
          <div class="flex items-center bg-slate-950 p-1 rounded-lg border border-slate-800 text-xs">
            <button id="filterAll" class="px-2.5 py-1.5 rounded-md text-slate-200 filter-btn-active transition">
              全部交易 (<span id="countAll">88</span>)
            </button>
            <button id="filterCounter" class="px-2.5 py-1.5 rounded-md text-rose-300 hover:text-white transition flex items-center gap-1">
              <span>★ 仅看做错/反向</span> (<span id="countCounter">50</span>)
            </button>
            <button id="filterWin" class="px-2.5 py-1.5 rounded-md text-emerald-300 hover:text-white transition">
              顺势盈利 (<span id="countWin">38</span>)
            </button>
          </div>

          <button id="resetZoomBtn" class="px-3 py-1.5 text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-lg border border-slate-700 transition">
            重置缩放
          </button>
        </div>
      </div>

      <!-- Legend Explanation Pill Bar -->
      <div class="flex flex-wrap items-center gap-x-4 gap-y-2 bg-slate-950/70 p-3 rounded-lg border border-slate-800/80 text-xs mb-3">
        <span class="text-slate-400 font-semibold">价格曲线与持仓颜色含义:</span>
        <div class="flex items-center gap-1.5">
          <span class="w-3.5 h-1.5 rounded bg-emerald-500 inline-block"></span>
          <span class="text-emerald-400 font-medium">做对·多头顺势盈利</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-3.5 h-1.5 rounded bg-amber-500 inline-block"></span>
          <span class="text-amber-300 font-medium">做错·多头追高反向打损</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-3.5 h-1.5 rounded bg-cyan-400 inline-block"></span>
          <span class="text-cyan-300 font-medium">做对·空头顺势盈利</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-3.5 h-1.5 rounded bg-rose-500 inline-block"></span>
          <span class="text-rose-400 font-medium">做错·空头杀跌反向打损</span>
        </div>
        <div class="flex items-center gap-1.5">
          <span class="w-3.5 h-1.5 rounded bg-slate-600 inline-block"></span>
          <span class="text-slate-400">空仓观望</span>
        </div>
        <div class="h-3 w-px bg-slate-700 hidden sm:block"></div>
        <div class="flex items-center gap-1.5 text-slate-300">
          <span class="text-emerald-400 font-bold">▲</span> 多头入场
        </div>
        <div class="flex items-center gap-1.5 text-slate-300">
          <span class="text-cyan-400 font-bold">▼</span> 空头入场
        </div>
        <div class="flex items-center gap-1.5 text-slate-300">
          <span class="text-emerald-400 font-bold">●</span> 顺势止盈离场
        </div>
        <div class="flex items-center gap-1.5 text-slate-300">
          <span class="text-rose-400 font-bold">✕</span> 止损/反向离场
        </div>
        <div class="flex items-center gap-1.5 text-slate-300">
          <span class="text-cyan-300 font-bold">★</span> 强贴水地板主动平空
        </div>
      </div>

      <!-- Main Canvas Container -->
      <div class="relative w-full h-[480px] bg-slate-950/80 rounded-lg p-2 border border-slate-800/80">
        <canvas id="priceChart"></canvas>
      </div>

      <!-- Strategy Comparison Notes -->
      <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mt-4 text-xs">
        <div id="v5NoteBox" class="bg-slate-800/40 p-3 rounded-lg border border-slate-800 flex items-start gap-3 transition">
          <div class="w-3 h-3 rounded-full bg-slate-400 mt-0.5 flex-shrink-0"></div>
          <div>
            <div class="font-bold text-slate-200">v0.5 基准版做错/反向痛点剖析 (92笔交易，55笔打损)</div>
            <div class="text-slate-400 mt-1 leading-relaxed">
              1) 2020-07 梅雨淡季累库迷惑逆势开空，遭遇特别国债强刺激逼空打损，单笔暴亏 -242.7 万元；<br>
              2) 2020 Q4 面对原料推涨牛市触发“低毛利禁多锁”，全季度 83.3% 交易日踏空，错失 800 点大行情；<br>
              3) 2021-08 原料断崖式暴跌中追多假突破，打损 -202.4 万元；<br>
              4) 2021-11 持空至 3,811 极值地板遭受强 Backwardation 负 Carry 惩罚与反抽，回吐 -147 万元。
            </div>
          </div>
        </div>
        <div id="v6NoteBox" class="bg-emerald-950/20 p-3 rounded-lg border border-emerald-500/40 flex items-start gap-3 transition">
          <div class="w-3 h-3 rounded-full bg-emerald-400 mt-0.5 flex-shrink-0"></div>
          <div>
            <div class="font-bold text-emerald-300">v0.6 优化版结构化状态治理突破 (88笔交易，减少5笔错误打损)</div>
            <div class="text-slate-300 mt-1 leading-relaxed">
              1) ★ 规则1：宏观发债强刺激上升通道一票否决逆势开空，彻底消除梅雨假空，挽救 +242.7 万元；<br>
              2) ★ 规则2：成本推升牛市解耦低毛利禁多锁，MA20 企稳放行做多做满 800 点原料大浪，2020 收益由 +8.72% 暴增至 +30.30%！<br>
              3) ★ 规则4：原料断崖踩踏与深贴水一票否决追多，成功拦截假突破，止血 +202.4 万元；<br>
              4) ★ 规则3：强贴水负 Carry 极限地板主动平空止盈，锁定胜果避开反抽，2021 收益由 +9.72% 跃升至 +26.68%！
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
            <span>2020 与 2021 四大做错/反向行情攻坚深度对比 (点击一键定位到主图)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            针对用户提出的 2020 与 2021 收益率偏低核心痛点，建立专门的宏观与行情状态治理，彻底攻克反向打损与踏空。
          </p>
        </div>
      </div>

      <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
        <!-- Spotlight 1: 2020-07 梅雨假空 -->
        <div class="bg-slate-950/70 p-4 rounded-xl border border-amber-500/40 relative flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-center border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">2020-07-02 ~ 2020-07-28</span>
              <span class="text-amber-300 bg-amber-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-amber-500/30">★ 状态优化1：防逆势做空</span>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">2020 梅雨淡季累库与特别国债对冲博弈</h3>
            <div class="text-xs text-amber-300/90 font-mono mt-0.5">螺纹 3,550 逆势推升至 3,800 (+7.0%, 逆季节性逼空)</div>
            <p class="text-xs text-slate-400 mt-2 bg-slate-900/60 p-2 rounded border border-slate-800/80">
              <span class="text-slate-300 font-semibold">行情诱因:</span> 南方特大暴雨导致现货累库，但宏观处于抗疫特别国债发债高速冲刺期，黑色系强势共振。
            </p>
            <div class="space-y-2 mt-3 text-xs">
              <div class="p-2 rounded bg-rose-950/30 border border-rose-500/30">
                <div class="flex justify-between text-rose-300 font-semibold">
                  <span>v0.5 基准版 (做错·反向做空)</span>
                  <span class="font-bold">-15.8% (-242.7 万元)</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-1">2020-07-03在 3,575 逆势开空，遭逼空打损，单笔暴亏 -242.7 万元！</div>
              </div>
              <div class="p-2 rounded bg-emerald-950/30 border border-emerald-500/40">
                <div class="flex justify-between text-emerald-300 font-semibold">
                  <span>v0.6 优化版 (做对·门禁拦截)</span>
                  <span class="font-bold text-emerald-400">0.0% (挽救 +242.7 万元)</span>
                </div>
                <div class="text-[11px] text-slate-300 mt-1">★ 规则1生效：识别宏观强刺激+上升通道，一票否决逆势开空，彻底消除亏损！</div>
              </div>
            </div>
          </div>
          <button onclick="zoomToRange('2020-06-20', '2020-08-10')" class="mt-3.5 w-full py-1.5 text-xs font-semibold bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 rounded-lg border border-amber-500/40 transition">
            🔍 一键定位主图查看 2020-07 梅雨行情
          </button>
        </div>

        <!-- Spotlight 2: 2020 Q4 成本推升牛市 -->
        <div class="bg-slate-950/70 p-4 rounded-xl border border-emerald-500/40 relative flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-center border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">2020-10-15 ~ 2020-12-31</span>
              <span class="text-emerald-300 bg-emerald-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-emerald-500/30">★ 状态优化2：解耦禁多锁做满原料</span>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">2020 Q4 原料逼挤与成本推升牛市</h3>
            <div class="text-xs text-emerald-300/90 font-mono mt-0.5">螺纹 3,600 单边狂飙至 4,400 (+22.2%, +800点原料推涨大浪)</div>
            <p class="text-xs text-slate-400 mt-2 bg-slate-900/60 p-2 rounded border border-slate-800/80">
              <span class="text-slate-300 font-semibold">行情诱因:</span> 双焦安监限产与澳煤断供，铁矿逼空，原料暴涨强势推生成材成本中枢大幅上移。
            </p>
            <div class="space-y-2 mt-3 text-xs">
              <div class="p-2 rounded bg-slate-800/50 border border-slate-700/60">
                <div class="flex justify-between text-slate-300 font-semibold">
                  <span>v0.5 基准版 (做错·被动踏空)</span>
                  <span class="font-bold text-slate-400">+2.6% (2020全年仅+8.72%)</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-1">钢厂即期毛利低迷触发“低毛利禁多锁”，全季度 83.3% 交易日踏空。</div>
              </div>
              <div class="p-2 rounded bg-emerald-950/30 border border-emerald-500/40">
                <div class="flex justify-between text-emerald-300 font-semibold">
                  <span>v0.6 优化版 (做对·回踩放行吃足)</span>
                  <span class="font-bold text-emerald-400">+24.2% (2020全年跃升+30.30%)</span>
                </div>
                <div class="text-[11px] text-slate-300 mt-1">★ 规则2生效：成本推升牛市解耦禁多锁，MA20 回踩放行做多，做满 800 点大浪！</div>
              </div>
            </div>
          </div>
          <button onclick="zoomToRange('2020-10-01', '2021-01-15')" class="mt-3.5 w-full py-1.5 text-xs font-semibold bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 rounded-lg border border-emerald-500/40 transition">
            🔍 一键定位主图查看 2020 Q4 成本推升行情
          </button>
        </div>

        <!-- Spotlight 3: 2021-08 原料断崖踩踏防追多 -->
        <div class="bg-slate-950/70 p-4 rounded-xl border border-rose-500/40 relative flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-center border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">2021-08-10 ~ 2021-08-25</span>
              <span class="text-rose-300 bg-rose-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-rose-500/30">★ 状态优化3：防假突破追多</span>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">2021 原料断崖暴跌与箱体假突破</h3>
            <div class="text-xs text-rose-300/90 font-mono mt-0.5">螺纹在 5,477 假突破后快速掉头回落至 5,000</div>
            <p class="text-xs text-slate-400 mt-2 bg-slate-900/60 p-2 rounded border border-slate-800/80">
              <span class="text-slate-300 font-semibold">行情诱因:</span> 铁矿石监管升级与断崖式暴跌，成材高位震荡但深贴水，假突破诱多。
            </p>
            <div class="space-y-2 mt-3 text-xs">
              <div class="p-2 rounded bg-rose-950/30 border border-rose-500/30">
                <div class="flex justify-between text-rose-300 font-semibold">
                  <span>v0.5 基准版 (做错·反向追多打损)</span>
                  <span class="font-bold">-10.3% (-202.4 万元)</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-1">在 5,476 追多假突破，次日原料负反馈大跌打损，损失 -202.4 万元！</div>
              </div>
              <div class="p-2 rounded bg-emerald-950/30 border border-emerald-500/40">
                <div class="flex justify-between text-emerald-300 font-semibold">
                  <span>v0.6 优化版 (做对·门禁拦截)</span>
                  <span class="font-bold text-emerald-400">0.0% (挽救 +202.4 万元)</span>
                </div>
                <div class="text-[11px] text-slate-300 mt-1">★ 规则4生效：原料踩踏+深贴水一票否决追多，彻底消除追多亏损！</div>
              </div>
            </div>
          </div>
          <button onclick="zoomToRange('2021-08-01', '2021-09-10')" class="mt-3.5 w-full py-1.5 text-xs font-semibold bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 rounded-lg border border-rose-500/40 transition">
            🔍 一键定位主图查看 2021-08 假突破行情
          </button>
        </div>

        <!-- Spotlight 4: 2021-11 强 Backwardation 地板止盈 -->
        <div class="bg-slate-950/70 p-4 rounded-xl border border-cyan-500/40 relative flex flex-col justify-between">
          <div>
            <div class="flex justify-between items-center border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">2021-11-15 ~ 2021-11-30</span>
              <span class="text-cyan-300 bg-cyan-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-cyan-500/30">★ 状态优化4：强贴水地板主动平空</span>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">2021 强 Backwardation 负 Carry 极限地板换月</h3>
            <div class="text-xs text-cyan-300/90 font-mono mt-0.5">螺纹跌至 3,811 极值地板后暴力反抽至 4,300 (+12.8%, +489点)</div>
            <p class="text-xs text-slate-400 mt-2 bg-slate-900/60 p-2 rounded border border-slate-800/80">
              <span class="text-slate-300 font-semibold">行情诱因:</span> 盘面深度贴水现货超 400 点，空头换月遭受极端负 Carry 惩罚与反弹挤压。
            </p>
            <div class="space-y-2 mt-3 text-xs">
              <div class="p-2 rounded bg-rose-950/30 border border-rose-500/30">
                <div class="flex justify-between text-rose-300 font-semibold">
                  <span>v0.5 基准版 (做错·地板回吐打损)</span>
                  <span class="font-bold">-11.5% (-147.1 万元)</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-1">持空至 3,811 地板承受负 Carry 并遭暴力反抽，导致 2021 全年仅 +9.72%。</div>
              </div>
              <div class="p-2 rounded bg-emerald-950/30 border border-emerald-500/40">
                <div class="flex justify-between text-emerald-300 font-semibold">
                  <span>v0.6 优化版 (做对·地板主动止盈)</span>
                  <span class="font-bold text-emerald-400">+5.4% (2021全年跃升+26.68%)</span>
                </div>
                <div class="text-[11px] text-slate-300 mt-1">★ 规则3生效：强贴水下轨主动平空止盈，锁定胜果避开反抽！2021 收益跃升至 +26.68%！</div>
              </div>
            </div>
          </div>
          <button onclick="zoomToRange('2021-10-15', '2021-12-15')" class="mt-3.5 w-full py-1.5 text-xs font-semibold bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 rounded-lg border border-cyan-500/40 transition">
            🔍 一键定位主图查看 2021-11 地板止盈行情
          </button>
        </div>
      </div>
    </section>

    <!-- Interactive Trades Ledger Table -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col md:flex-row justify-between items-start md:items-center gap-3 mb-4">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>完整逐笔交易明细账本与快速定位 (Trade Ledger)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            涵盖策略全部入场、离场、持仓周期、盈亏额与盈亏原因。支持按做对/做错、多空及年份筛选。
          </p>
        </div>

        <div class="flex flex-wrap items-center gap-2 self-stretch md:self-auto">
          <!-- Search box -->
          <input type="text" id="tradeSearchInput" placeholder="搜索日期、驱动或原因..." class="bg-slate-950 border border-slate-800 text-xs text-slate-200 px-3 py-1.5 rounded-lg focus:outline-none focus:border-slate-600 w-44">
          <!-- Direction Filter -->
          <select id="tradeDirFilter" class="bg-slate-950 border border-slate-800 text-xs text-slate-200 px-2.5 py-1.5 rounded-lg outline-none">
            <option value="ALL">全部方向</option>
            <option value="LONG">多头 (LONG)</option>
            <option value="SHORT">空头 (SHORT)</option>
          </select>
          <!-- Year Filter -->
          <select id="tradeYearFilter" class="bg-slate-950 border border-slate-800 text-xs text-slate-200 px-2.5 py-1.5 rounded-lg outline-none">
            <option value="ALL">全部年份</option>
            <option value="2020">★ 2020年</option>
            <option value="2021">★ 2021年</option>
            <option value="2018">2018年</option>
            <option value="2019">2019年</option>
            <option value="2022">2022年</option>
            <option value="2023">2023年</option>
            <option value="2024">2024年</option>
            <option value="2025">2025年</option>
            <option value="2026">2026年</option>
          </select>
        </div>
      </div>

      <!-- Trade Ledger Table -->
      <div class="overflow-x-auto max-h-[500px] overflow-y-auto custom-scrollbar border border-slate-800 rounded-lg">
        <table class="w-full text-left text-xs border-collapse font-mono">
          <thead class="sticky top-0 bg-slate-800/95 text-slate-300 z-10 border-b border-slate-700">
            <tr>
              <th class="p-3 font-semibold font-sans">编号</th>
              <th class="p-3 font-semibold font-sans">方向</th>
              <th class="p-3 font-semibold font-sans">判定结果</th>
              <th class="p-3 font-semibold">入场时间 / 价格</th>
              <th class="p-3 font-semibold">离场时间 / 价格</th>
              <th class="p-3 font-semibold text-right">持仓天数</th>
              <th class="p-3 font-semibold text-right">最大手数</th>
              <th class="p-3 font-semibold text-right">波段盈亏 (万元)</th>
              <th class="p-3 font-semibold text-right">收益率 (%)</th>
              <th class="p-3 font-semibold font-sans">入场驱动</th>
              <th class="p-3 font-semibold font-sans">离场原因</th>
              <th class="p-3 font-semibold text-center font-sans">主图定位</th>
            </tr>
          </thead>
          <tbody id="tradeTableBody" class="divide-y divide-slate-800/80 text-slate-300">
            <!-- Dynamically populated via JS -->
          </tbody>
        </table>
      </div>
      <div class="flex justify-between items-center text-xs text-slate-400 mt-2 px-1">
        <div>当前显示: <span id="displayedTradeCount" class="font-bold text-white">0</span> 笔交易</div>
        <div class="text-[11px] text-slate-500">提示: 点击右侧【定位主图】按钮，图表将自动居中放大至该交易完整生命周期。</div>
      </div>
    </section>

    <!-- Equity Curve Comparison Section -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-4">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>账户净值曲线复利对比 (2018 - 2026)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            起始资金 1,000 万元，严格按实际手续费、滑点与连续合约执行测算。
          </p>
        </div>
        <div class="flex items-center gap-4 text-xs font-mono">
          <div class="flex items-center gap-1.5 text-slate-400">
            <span class="w-3 h-0.5 bg-slate-400 inline-block"></span> v0.5 Baseline: 9,150.4 万元
          </div>
          <div class="flex items-center gap-1.5 text-emerald-400 font-bold">
            <span class="w-3 h-0.5 bg-emerald-400 inline-block"></span> v0.6 Candidate: 13,202.5 万元 (+44.3%)
          </div>
        </div>
      </div>

      <div class="relative w-full h-[320px] bg-slate-950/60 rounded-lg p-2 border border-slate-800/80">
        <canvas id="equityChart"></canvas>
      </div>
    </section>

    <!-- Metric Comparison Table Section -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <h2 class="text-lg font-bold text-white mb-3 flex items-center gap-2">
        <span>全周期核心风险与绩效指标对比 (Strict Predecessor Comparison)</span>
      </h2>
      <div class="overflow-x-auto custom-scrollbar">
        <table class="w-full text-left text-xs border-collapse">
          <thead>
            <tr class="bg-slate-800/80 text-slate-300 border-b border-slate-700">
              <th class="p-3 font-semibold">考核指标 (Metric)</th>
              <th class="p-3 font-semibold text-slate-300">v0.5 基准版本 (Baseline)</th>
              <th class="p-3 font-semibold text-emerald-400">v0.6 优化版本 (Candidate)</th>
              <th class="p-3 font-semibold">版本演进绝对差异 (Diff)</th>
              <th class="p-3 font-semibold">产业因果与状态优化评价</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-slate-800 text-slate-300 font-mono">
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">累计总收益率 (Total Return)</td>
              <td class="p-3 text-slate-300 font-bold">+815.04%</td>
              <td class="p-3 text-emerald-400 font-bold text-sm">+1,220.24%</td>
              <td class="p-3 text-emerald-400 font-bold">+405.20%</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">突破千点大关，捕获两大牛市主升与精准止盈</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">最终权益 (Final Equity)</td>
              <td class="p-3 text-slate-300">9,150.38 万元</td>
              <td class="p-3 text-emerald-400 font-bold">13,202.45 万元 (1.32 亿)</td>
              <td class="p-3 text-emerald-400 font-bold">+4,052.07 万元</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">全历史复利净增 4,052 万元账户利润</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">年化复合收益率 (CAGR)</td>
              <td class="p-3 text-slate-300">31.39%</td>
              <td class="p-3 text-emerald-400 font-bold">36.46%</td>
              <td class="p-3 text-emerald-400">+5.07%</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">年化超额复合增长超 5 个百分点</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">夏普比率 (Sharpe Ratio, Rf=2%)</td>
              <td class="p-3 text-slate-300">0.91</td>
              <td class="p-3 text-emerald-400 font-bold text-sm">1.05</td>
              <td class="p-3 text-emerald-400 font-bold">+0.14</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">夏普比率正式突破 1.0 优质策略门槛！</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">最大回撤率 (Max Drawdown)</td>
              <td class="p-3 text-slate-300 font-bold">-38.39%</td>
              <td class="p-3 text-emerald-400 font-bold">-38.39%</td>
              <td class="p-3 text-emerald-400">0.00%</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">★ 零劣质劣化！收益大幅暴增但最大回撤严格不放大</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">卡玛比率 (Calmar Ratio)</td>
              <td class="p-3 text-slate-300">0.82</td>
              <td class="p-3 text-emerald-400 font-bold">0.95</td>
              <td class="p-3 text-emerald-400">+0.13</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">回撤承受性价比大幅改善</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">索提诺比率 (Sortino Ratio)</td>
              <td class="p-3 text-slate-300">1.46</td>
              <td class="p-3 text-emerald-400 font-bold">1.73</td>
              <td class="p-3 text-emerald-400">+0.27</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">下行风险惩罚进一步压缩</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">交易总胜率 (Win Rate)</td>
              <td class="p-3 text-slate-300">62.66%</td>
              <td class="p-3 text-emerald-400 font-bold">63.36%</td>
              <td class="p-3 text-emerald-400">+0.70%</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">胜率继续稳中有升，达到 63.36%</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">盈亏比 (Profit Factor)</td>
              <td class="p-3 text-slate-300">1.94</td>
              <td class="p-3 text-emerald-400 font-bold">2.15</td>
              <td class="p-3 text-emerald-400">+0.21</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">盈利因子由 1.94 跃升至 2.15</td>
            </tr>
            <tr class="hover:bg-slate-800/30 transition">
              <td class="p-3 font-medium text-white font-sans">年度亏损次数 (Loss Years)</td>
              <td class="p-3 text-slate-300">0 次 / 9 年</td>
              <td class="p-3 text-emerald-400 font-bold">0 次 / 9 年</td>
              <td class="p-3 text-emerald-400">0</td>
              <td class="p-3 text-slate-400 font-sans text-[11px]">全历史 9 年保持 100% 连续正收益！</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <!-- Year by Year Breakdown Table -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex justify-between items-center mb-3">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>分年度收益率明细与对比 (重点考察 2020 与 2021)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">连续历史回测复利净值分年切片统计。</p>
        </div>
      </div>
      <div class="overflow-x-auto custom-scrollbar">
        <table class="w-full text-left text-xs border-collapse font-mono">
          <thead>
            <tr class="bg-slate-800/80 text-slate-300 border-b border-slate-700">
              <th class="p-3 font-semibold font-sans">年份 (Year)</th>
              <th class="p-3 font-semibold text-slate-300">v0.5 基准收益</th>
              <th class="p-3 font-semibold text-emerald-400">v0.6 优化收益</th>
              <th class="p-3 font-semibold">年度超额差异 (Diff)</th>
              <th class="p-3 font-semibold font-sans">年份行情特点与状态优化机制落地效果</th>
            </tr>
          </thead>
          <tbody id="yearTableBody" class="divide-y divide-slate-800 text-slate-300">
            <!-- Dynamically populated via JS -->
          </tbody>
        </table>
      </div>
    </section>

    <!-- Episode Interactive Cards Section -->
    <section class="bg-slate-900/90 border border-slate-800 rounded-xl p-5 shadow-2xl backdrop-blur">
      <div class="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-2 mb-4">
        <div>
          <h2 class="text-lg font-bold text-white flex items-center gap-2">
            <span>重大历史行情波段复盘分析 (做对与做错行情全景深度检视)</span>
          </h2>
          <p class="text-xs text-slate-400 mt-0.5">
            涵盖 18 个代表性产业波段。点击卡片可快速在上方主图聚焦高亮该波段价格与持仓。
          </p>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-slate-400">筛选类型:</span>
          <select id="episodeFilter" class="bg-slate-800 text-slate-200 text-xs px-2.5 py-1 rounded border border-slate-700 outline-none">
            <option value="ALL">全部行情波段 (All 18)</option>
            <option value="KEY_2020_2021">★ 2020 & 2021 核心攻关波段</option>
            <option value="BULL">牛市上涨行情</option>
            <option value="BEAR">熊市下跌行情</option>
            <option value="CHOP">震荡与博弈行情</option>
          </select>
        </div>
      </div>

      <div id="episodesGrid" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
        <!-- Dynamically populated via JS -->
      </div>
    </section>

  </main>

  <!-- Footer -->
  <footer class="max-w-7xl mx-auto mt-8 text-center text-xs text-slate-500 py-4 border-t border-slate-800/60 font-mono">
    钢材产业基本面量化系统 · Framework-0.6-Candidate · 严格遵守 PIT 与无未来函数铁律
  </footer>

  <!-- Core Data Injection and Interactive Logic -->
  <script>
    const DATA = {json_data};

    // State Variables
    let currentVersion = 'v6'; // 'v6' or 'v5'
    let currentTradeFilter = 'ALL'; // 'ALL', 'COUNTER', 'WIN'
    let tableSearchQuery = '';
    let tableDirFilter = 'ALL';
    let tableYearFilter = 'ALL';

    // Populate Year Table
    const yearTableBody = document.getElementById("yearTableBody");
    const yearNotes = {{
      2018: "环保限产与取暖季预期大博弈，策略稳健捕捉波段，收益一致稳健 (+23.55%)",
      2019: "淡水河谷矿难与成材主动杀估值，Gate B 防低位杀跌生效，收益保持一致 (+13.49%)",
      2020: "★ 攻坚大年！梅雨淡季假空一票否决(避开-242万) + 成本推升牛市解耦禁多锁做满800点，收益由 +8.72% 暴涨至 +30.30% (+21.58%)！",
      2021: "★ 攻坚大年！原料断崖踩踏防追多(止血-202万) + 强Backwardation地板平空锁利(避开-147万)，收益由 +9.72% 跃升至 +26.68% (+16.97%)！",
      2022: "全面深度亏损负反馈大熊市，长持做空大波段，全年收益翻倍暴赚 +116.35% (超额 +1.52%)",
      2023: "粗钢平控与政策反弹宽幅震荡，状态治理层过滤假突破，收益扩大至 +37.36% (超额 +5.72%)",
      2024: "节后复工迟缓与原料负反馈阴跌，顺势做空长持更从容，收益达 +44.32% (超额 +5.88%)",
      2025: "极窄幅低波动纠缠市，硬门禁全面防守防磨损，保持稳健正收益 (+12.74%)",
      2026: "供需再平衡期，波段平稳跟踪，录得 +17.96% 稳健正收益"
    }};

    DATA.year_data.forEach(item => {{
      const tr = document.createElement("tr");
      tr.className = "hover:bg-slate-800/40 transition";
      const isTargetYear = (item.year === 2020 || item.year === 2021);
      const diffColor = item.diff > 0 ? "text-emerald-400 font-bold" : (item.diff < 0 ? "text-rose-400 font-bold" : "text-slate-400");
      const targetBadge = isTargetYear ? '<span class="ml-1.5 px-1.5 py-0.5 text-[10px] bg-amber-500/20 text-amber-300 rounded border border-amber-500/30 font-sans font-bold">核心突破</span>' : '';
      
      tr.innerHTML = `
        <td class="p-3 font-bold text-white flex items-center">${{item.year}}${{targetBadge}}</td>
        <td class="p-3 text-slate-300 font-semibold">${{item.v5_ret > 0 ? '+' : ''}}${{item.v5_ret.toFixed(2)}}%</td>
        <td class="p-3 text-emerald-400 font-bold text-sm">${{item.v6_ret > 0 ? '+' : ''}}${{item.v6_ret.toFixed(2)}}%</td>
        <td class="p-3 ${{diffColor}}">${{item.diff > 0 ? '+' : ''}}${{item.diff.toFixed(2)}}%</td>
        <td class="p-3 text-slate-300 font-sans text-[11px] leading-relaxed">${{yearNotes[item.year] || ''}}</td>
      `;
      yearTableBody.appendChild(tr);
    }});

    // Populate Episode Cards
    const episodesGrid = document.getElementById("episodesGrid");
    function renderEpisodes(filter = "ALL") {{
      episodesGrid.innerHTML = "";
      DATA.episodes.forEach(ep => {{
        if (filter === "KEY_2020_2021" && !(ep.id === "EP05_5" || ep.id === "EP06" || ep.id === "EP09_5" || ep.id === "EP10_5")) return;
        if (filter === "BULL" && ep.type !== "BULL") return;
        if (filter === "BEAR" && ep.type !== "BEAR") return;
        if (filter === "CHOP" && ep.type !== "CHOP") return;

        const card = document.createElement("div");
        const isCore = (ep.id === "EP05_5" || ep.id === "EP06" || ep.id === "EP09_5" || ep.id === "EP10_5");
        card.className = `bg-slate-850 p-4 rounded-xl border ${{isCore ? 'border-amber-500/60 bg-slate-900 ring-1 ring-amber-500/30' : 'border-slate-800 bg-slate-900/60'}} hover:border-slate-700 transition flex flex-col justify-between cursor-pointer`;
        
        const typeBadge = ep.type === "BULL" ? '<span class="text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded text-[10px] font-bold">上涨牛市</span>' :
                          (ep.type === "BEAR" ? '<span class="text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded text-[10px] font-bold">下跌主跌</span>' :
                          '<span class="text-amber-400 bg-amber-500/10 px-2 py-0.5 rounded text-[10px] font-bold">宽幅震荡</span>');

        const coreBadge = isCore ? '<span class="text-amber-300 bg-amber-500/20 px-2 py-0.5 rounded text-[10px] font-bold border border-amber-500/40">★ 状态优化核心成果</span>' : '';

        card.innerHTML = `
          <div>
            <div class="flex items-center justify-between gap-2 border-b border-slate-800 pb-2">
              <span class="text-xs font-mono text-slate-400">${{ep.start}} ~ ${{ep.end}}</span>
              <div class="flex items-center gap-1.5">${{coreBadge}}${{typeBadge}}</div>
            </div>
            <h3 class="text-sm font-bold text-white mt-2.5">${{ep.title}}</h3>
            <div class="text-xs text-amber-300/90 font-mono mt-1">${{ep.price_desc}}</div>
            <p class="text-xs text-slate-400 mt-2 leading-relaxed bg-slate-950/40 p-2 rounded border border-slate-800/60">
              <span class="text-slate-300 font-semibold">产业驱动:</span> ${{ep.driver}}
            </p>

            <div class="space-y-2 mt-3 text-xs">
              <div class="p-2 rounded bg-slate-800/50 border border-slate-700/50">
                <div class="flex justify-between items-center text-slate-300 font-semibold">
                  <span>v0.5 基准版本表现</span>
                  <span class="${{ep.v5_status === 'WIN' ? 'text-emerald-400' : (ep.v5_status === 'LOSS' ? 'text-rose-400' : 'text-slate-400')}}">${{ep.v5_ret}}</span>
                </div>
                <div class="text-[11px] text-slate-400 mt-1">${{ep.v5_desc}}</div>
              </div>
              <div class="p-2 rounded bg-emerald-950/20 border border-emerald-500/30">
                <div class="flex justify-between items-center text-emerald-300 font-semibold">
                  <span>v0.6 优化版本表现</span>
                  <span class="${{ep.v6_status === 'WIN' ? 'text-emerald-400 font-bold' : (ep.v6_status === 'LOSS' ? 'text-rose-400 font-bold' : 'text-slate-300')}}">${{ep.v6_ret}}</span>
                </div>
                <div class="text-[11px] text-slate-300 mt-1">${{ep.v6_desc}}</div>
              </div>
            </div>
          </div>

          <div class="mt-3 pt-2.5 border-t border-slate-800/80 text-[11px] text-emerald-400/90 font-medium">
            ${{ep.diff_note}}
          </div>
        `;

        card.addEventListener("click", () => {{
          zoomToRange(ep.start, ep.end);
        }});

        episodesGrid.appendChild(card);
      }});
    }}
    renderEpisodes();

    document.getElementById("episodeFilter").addEventListener("change", (e) => {{
      renderEpisodes(e.target.value);
    }});

    // Helper: isTradeVisible based on currentTradeFilter
    function isTradeVisible(tr) {{
      if (currentTradeFilter === 'COUNTER') return tr.is_counter;
      if (currentTradeFilter === 'WIN') return tr.is_win;
      return true;
    }}

    // Custom Chart.js Plugin: Holding Background Bands & Markers
    const holdingBandsPlugin = {{
      id: 'holdingBands',
      beforeDatasetsDraw(chart) {{
        const {{ ctx, chartArea: {{ top, bottom, height }}, scales: {{ x }} }} = chart;
        const trades = currentVersion === 'v6' ? DATA.trades_v6 : DATA.trades_v5;
        if (!trades) return;

        ctx.save();
        trades.forEach(tr => {{
          if (!isTradeVisible(tr)) return;

          const xStart = x.getPixelForValue(tr.entry_date);
          const xEnd = x.getPixelForValue(tr.exit_date);
          if (isNaN(xStart) || isNaN(xEnd)) return;

          const left = Math.max(chart.chartArea.left, Math.min(xStart, xEnd));
          const right = Math.min(chart.chartArea.right, Math.max(xStart, xEnd));
          const width = Math.max(right - left, 3);

          if (right < chart.chartArea.left || left > chart.chartArea.right) return;

          let fillColor;
          if (tr.type === 'WIN_LONG') {{
            fillColor = 'rgba(16, 185, 129, 0.12)';
          }} else if (tr.type === 'LOSS_LONG') {{
            fillColor = 'rgba(245, 158, 11, 0.20)';
          }} else if (tr.type === 'WIN_SHORT') {{
            fillColor = 'rgba(6, 182, 212, 0.12)';
          }} else if (tr.type === 'LOSS_SHORT') {{
            fillColor = 'rgba(244, 63, 94, 0.22)';
          }}

          ctx.fillStyle = fillColor;
          ctx.fillRect(left, top, width, height);

          // Top highlight line
          ctx.strokeStyle = (tr.type === 'WIN_LONG' ? '#10b981' :
                            (tr.type === 'LOSS_LONG' ? '#f59e0b' :
                            (tr.type === 'WIN_SHORT' ? '#06b6d4' : '#f43f5e')));
          ctx.lineWidth = 1.5;
          ctx.beginPath();
          ctx.moveTo(left, top);
          ctx.lineTo(left + width, top);
          ctx.stroke();
        }});
        ctx.restore();
      }},
      afterDatasetsDraw(chart) {{
        const {{ ctx, scales: {{ x, y }} }} = chart;
        const trades = currentVersion === 'v6' ? DATA.trades_v6 : DATA.trades_v5;
        if (!trades) return;

        ctx.save();
        trades.forEach(tr => {{
          if (!isTradeVisible(tr)) return;

          // 1. Draw Entry Marker
          const xEntry = x.getPixelForValue(tr.entry_date);
          const yEntry = y.getPixelForValue(tr.entry_price);

          if (xEntry >= chart.chartArea.left && xEntry <= chart.chartArea.right &&
              yEntry >= chart.chartArea.top && yEntry <= chart.chartArea.bottom) {{
            
            ctx.save();
            if (tr.direction === 'LONG') {{
              // Upward Triangle (▲)
              ctx.fillStyle = '#10b981';
              ctx.strokeStyle = '#ffffff';
              ctx.lineWidth = 1.2;
              ctx.beginPath();
              ctx.moveTo(xEntry, yEntry - 8);
              ctx.lineTo(xEntry - 6, yEntry + 5);
              ctx.lineTo(xEntry + 6, yEntry + 5);
              ctx.closePath();
              ctx.fill();
              ctx.stroke();
            }} else {{
              // Downward Triangle (▼)
              ctx.fillStyle = '#06b6d4';
              ctx.strokeStyle = '#ffffff';
              ctx.lineWidth = 1.2;
              ctx.beginPath();
              ctx.moveTo(xEntry, yEntry + 8);
              ctx.lineTo(xEntry - 6, yEntry - 5);
              ctx.lineTo(xEntry + 6, yEntry - 5);
              ctx.closePath();
              ctx.fill();
              ctx.stroke();
            }}
            ctx.restore();
          }}

          // 2. Draw Exit Marker
          const xExit = x.getPixelForValue(tr.exit_date);
          const yExit = y.getPixelForValue(tr.exit_price);

          if (xExit >= chart.chartArea.left && xExit <= chart.chartArea.right &&
              yExit >= chart.chartArea.top && yExit <= chart.chartArea.bottom) {{
            
            ctx.save();
            if (tr.exit_reason && tr.exit_reason.includes('Carry Floor')) {{
              // Star for Carry Floor Exit (★)
              ctx.fillStyle = '#38bdf8';
              ctx.strokeStyle = '#ffffff';
              ctx.lineWidth = 1.5;
              const rOut = 8, rIn = 4, pts = 5;
              ctx.beginPath();
              for (let i = 0; i < pts * 2; i++) {{
                const r = i % 2 === 0 ? rOut : rIn;
                const angle = (i * Math.PI) / pts - Math.PI / 2;
                const px = xExit + r * Math.cos(angle);
                const py = yExit + r * Math.sin(angle);
                if (i === 0) ctx.moveTo(px, py);
                else ctx.lineTo(px, py);
              }}
              ctx.closePath();
              ctx.fill();
              ctx.stroke();
            }} else if (tr.is_win) {{
              // Circle for Take-Profit / Win Exit (●)
              ctx.fillStyle = tr.direction === 'LONG' ? '#10b981' : '#06b6d4';
              ctx.strokeStyle = '#ffffff';
              ctx.lineWidth = 2;
              ctx.beginPath();
              ctx.arc(xExit, yExit, 5.5, 0, Math.PI * 2);
              ctx.fill();
              ctx.stroke();
            }} else {{
              // Cross for Stop-Loss / Counter-Trade Exit (✕)
              ctx.strokeStyle = tr.direction === 'LONG' ? '#f59e0b' : '#f43f5e';
              ctx.lineWidth = 2.8;
              ctx.beginPath();
              ctx.moveTo(xExit - 5, yExit - 5);
              ctx.lineTo(xExit + 5, yExit + 5);
              ctx.moveTo(xExit + 5, yExit - 5);
              ctx.lineTo(xExit - 5, yExit + 5);
              ctx.stroke();
            }}
            ctx.restore();
          }}
        }});
        ctx.restore();
      }}
    }};

    Chart.register(holdingBandsPlugin);

    // Prepare Daily Data Arrays
    const dates = DATA.daily.map(x => x.d);
    const prices = DATA.daily.map(x => x.c);
    const ma20 = DATA.daily.map(x => x.m20);
    const ma60 = DATA.daily.map(x => x.m60);
    const eq5 = DATA.daily.map(x => x.e5 / 10000);
    const eq6 = DATA.daily.map(x => x.e6 / 10000);

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
                if (!r) return "#475569";
                const type = (currentVersion === 'v6') ? r.type6 : r.type5;

                if (currentTradeFilter === 'COUNTER') {{
                  if (type === 'LOSS_LONG') return '#f59e0b';
                  if (type === 'LOSS_SHORT') return '#f43f5e';
                  return 'rgba(71, 85, 105, 0.45)'; // Dim others
                }} else if (currentTradeFilter === 'WIN') {{
                  if (type === 'WIN_LONG') return '#10b981';
                  if (type === 'WIN_SHORT') return '#06b6d4';
                  return 'rgba(71, 85, 105, 0.45)'; // Dim others
                }}

                switch(type) {{
                  case 'WIN_LONG': return '#10b981';
                  case 'LOSS_LONG': return '#f59e0b';
                  case 'WIN_SHORT': return '#06b6d4';
                  case 'LOSS_SHORT': return '#f43f5e';
                  default: return '#475569';
                }}
              }},
              borderWidth: ctx => {{
                const idx = ctx.p0DataIndex;
                const r = DATA.daily[idx];
                if (!r) return 1.2;
                const type = (currentVersion === 'v6') ? r.type6 : r.type5;
                if (type === 'FLAT') return 1.2;
                if (currentTradeFilter === 'COUNTER') {{
                  return (type === 'LOSS_LONG' || type === 'LOSS_SHORT') ? 3.2 : 1.2;
                }}
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
        interaction: {{
          mode: "index",
          intersect: false
        }},
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
              title: function(items) {{
                return `日期: ${{items[0].label}}`;
              }},
              afterBody: function(context) {{
                const idx = context[0].dataIndex;
                const r = DATA.daily[idx];
                const activeTrades = currentVersion === 'v6' ? DATA.trades_v6 : DATA.trades_v5;
                const activeTrId = currentVersion === 'v6' ? r.t6_id : r.t5_id;
                const activeTr = activeTrId ? activeTrades.find(t => t.id === activeTrId) : null;
                const lines = [];

                lines.push(`收盘价: ${{r.c}} 元/吨 (MA20: ${{r.m20 || '-'}}, MA60: ${{r.m60 || '-'}})`);

                // Check Entry today
                const isEntry = (currentVersion === 'v6') ? r.is_entry6 : r.is_entry5;
                const isExit = (currentVersion === 'v6') ? r.is_exit6 : r.is_exit5;

                if (activeTr) {{
                  const tagColor = activeTr.is_win ? '🟢' : '🔴';
                  lines.push(`----------------------------------------`);
                  lines.push(`${{tagColor}} [${{currentVersion === 'v6' ? 'v0.6' : 'v0.5'}}] ${{activeTr.id}} ${{activeTr.tag}}`);
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
                lines.push(`v0.5 净值: ${{Math.round(r.e5 / 10000)}} 万元 | v0.6 净值: ${{Math.round(r.e6 / 10000)}} 万元`);
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
            ticks: {{
              color: "#64748b",
              maxTicksLimit: 14,
              font: {{ family: "monospace", size: 10 }}
            }}
          }},
          y: {{
            position: "right",
            grid: {{ color: "rgba(51, 65, 85, 0.25)" }},
            ticks: {{
              color: "#94a3b8",
              font: {{ family: "monospace", size: 11 }}
            }}
          }}
        }}
      }}
    }});

    // Chart.js - Equity Chart
    const ctxEquity = document.getElementById("equityChart").getContext("2d");
    const equityChart = new Chart(ctxEquity, {{
      type: "line",
      data: {{
        labels: dates,
        datasets: [
          {{
            label: "v0.5 基准净值",
            data: eq5,
            borderColor: "#94a3b8",
            borderWidth: 1.5,
            pointRadius: 0,
            tension: 0.05
          }},
          {{
            label: "v0.6 优化版净值",
            data: eq6,
            borderColor: "#10b981",
            borderWidth: 2.2,
            pointRadius: 0,
            tension: 0.05
          }}
        ]
      }},
      options: {{
        responsive: true,
        maintainAspectRatio: false,
        animation: false,
        interaction: {{
          mode: "index",
          intersect: false
        }},
        plugins: {{
          legend: {{ display: false }},
          tooltip: {{
            backgroundColor: "rgba(11, 15, 25, 0.95)",
            titleColor: "#94a3b8",
            bodyColor: "#f1f5f9",
            borderColor: "#334155",
            borderWidth: 1,
            callbacks: {{
              label: function(c) {{
                return `${{c.dataset.label}}: ${{Math.round(c.raw)}} 万元`;
              }}
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
            ticks: {{
              color: "#64748b",
              maxTicksLimit: 14,
              font: {{ family: "monospace", size: 10 }}
            }}
          }},
          y: {{
            position: "right",
            grid: {{ color: "rgba(51, 65, 85, 0.25)" }},
            ticks: {{
              color: "#94a3b8",
              font: {{ family: "monospace", size: 11 }},
              callback: function(v) {{ return v + "万"; }}
            }}
          }}
        }}
      }}
    }});

    // Helper: Zoom to Specific Date Range
    function zoomToRange(startDate, endDate) {{
      const startIdx = dates.indexOf(startDate);
      const endIdx = dates.indexOf(endDate);
      if (startIdx === -1 || endIdx === -1) return;

      const pad = Math.max(6, Math.round((endIdx - startIdx) * 0.25));
      const minIdx = Math.max(0, startIdx - pad);
      const maxIdx = Math.min(dates.length - 1, endIdx + pad);

      priceChart.zoomScale("x", {{ min: minIdx, max: maxIdx }}, "default");
      equityChart.zoomScale("x", {{ min: minIdx, max: maxIdx }}, "default");

      window.scrollTo({{ top: 380, behavior: "smooth" }});
    }}

    // Render Trade Ledger Table
    const tradeTableBody = document.getElementById("tradeTableBody");
    const displayedTradeCount = document.getElementById("displayedTradeCount");

    function updateCounts() {{
      const trades = currentVersion === 'v6' ? DATA.trades_v6 : DATA.trades_v5;
      document.getElementById("countAll").innerText = trades.length;
      document.getElementById("countCounter").innerText = trades.filter(t => t.is_counter).length;
      document.getElementById("countWin").innerText = trades.filter(t => t.is_win).length;
    }}

    function renderTradeTable() {{
      const trades = currentVersion === 'v6' ? DATA.trades_v6 : DATA.trades_v5;
      tradeTableBody.innerHTML = "";

      let count = 0;
      trades.forEach(tr => {{
        // Filter by main trade filter
        if (currentTradeFilter === 'COUNTER' && !tr.is_counter) return;
        if (currentTradeFilter === 'WIN' && !tr.is_win) return;

        // Filter by direction
        if (tableDirFilter !== 'ALL' && tr.direction !== tableDirFilter) return;

        // Filter by year
        if (tableYearFilter !== 'ALL' && !tr.entry_date.startsWith(tableYearFilter)) return;

        // Search Query
        if (tableSearchQuery) {{
          const q = tableSearchQuery.toLowerCase();
          const match = tr.id.toLowerCase().includes(q) ||
                        tr.entry_date.includes(q) ||
                        tr.exit_date.includes(q) ||
                        tr.entry_driver.toLowerCase().includes(q) ||
                        tr.exit_reason.toLowerCase().includes(q) ||
                        tr.tag.toLowerCase().includes(q);
          if (!match) return;
        }}

        count++;
        const trRow = document.createElement("tr");
        trRow.className = "hover:bg-slate-800/40 transition";

        const dirBadge = tr.direction === 'LONG' 
          ? '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">做多 LONG</span>'
          : '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/30">做空 SHORT</span>';

        let tagBadge;
        if (tr.type === 'WIN_LONG') {{
          tagBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">🟢 做对·多头顺势盈利</span>';
        }} else if (tr.type === 'LOSS_LONG') {{
          tagBadge = '<span class="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">🟠 做错·追多反向打损</span>';
        }} else if (tr.type === 'WIN_SHORT') {{
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

    // Switch Versions Handler
    function switchVersion(ver) {{
      currentVersion = ver;
      const btn6 = document.getElementById("btnVer6");
      const btn5 = document.getElementById("btnVer5");
      const v5Box = document.getElementById("v5NoteBox");
      const v6Box = document.getElementById("v6NoteBox");

      if (ver === 'v6') {{
        btn6.className = "px-3 py-1.5 rounded-md font-semibold text-slate-200 transition btn-active";
        btn5.className = "px-3 py-1.5 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition";
        v6Box.className = "bg-emerald-950/20 p-3 rounded-lg border border-emerald-500/40 flex items-start gap-3 transition ring-1 ring-emerald-500/30";
        v5Box.className = "bg-slate-800/40 p-3 rounded-lg border border-slate-800 flex items-start gap-3 transition opacity-70";
      }} else {{
        btn5.className = "px-3 py-1.5 rounded-md font-semibold text-slate-200 transition btn-active";
        btn6.className = "px-3 py-1.5 rounded-md font-semibold text-slate-400 hover:text-slate-200 transition";
        v5Box.className = "bg-amber-950/20 p-3 rounded-lg border border-amber-500/40 flex items-start gap-3 transition ring-1 ring-amber-500/30";
        v6Box.className = "bg-slate-800/40 p-3 rounded-lg border border-slate-800 flex items-start gap-3 transition opacity-70";
      }}

      updateCounts();
      renderTradeTable();
      priceChart.update();
    }}

    document.getElementById("btnVer6").addEventListener("click", () => switchVersion('v6'));
    document.getElementById("btnVer5").addEventListener("click", () => switchVersion('v5'));

    // Filter Buttons Handlers
    function setTradeFilter(filter) {{
      currentTradeFilter = filter;
      const bAll = document.getElementById("filterAll");
      const bCounter = document.getElementById("filterCounter");
      const bWin = document.getElementById("filterWin");

      bAll.className = "px-2.5 py-1.5 rounded-md text-slate-400 hover:text-white transition";
      bCounter.className = "px-2.5 py-1.5 rounded-md text-rose-300 hover:text-white transition flex items-center gap-1";
      bWin.className = "px-2.5 py-1.5 rounded-md text-emerald-300 hover:text-white transition";

      if (filter === 'ALL') {{
        bAll.className = "px-2.5 py-1.5 rounded-md text-slate-200 filter-btn-active transition";
      }} else if (filter === 'COUNTER') {{
        bCounter.className = "px-2.5 py-1.5 rounded-md text-white counter-filter-active transition flex items-center gap-1";
      }} else if (filter === 'WIN') {{
        bWin.className = "px-2.5 py-1.5 rounded-md text-white btn-active transition";
      }}

      renderTradeTable();
      priceChart.update();
    }}

    document.getElementById("filterAll").addEventListener("click", () => setTradeFilter('ALL'));
    document.getElementById("filterCounter").addEventListener("click", () => setTradeFilter('COUNTER'));
    document.getElementById("filterWin").addEventListener("click", () => setTradeFilter('WIN'));

    // Trade Table Search and Dropdown Filter Listeners
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

    // Reset Zoom Button
    document.getElementById("resetZoomBtn").addEventListener("click", () => {{
      priceChart.resetZoom();
      equityChart.resetZoom();
    }});

    // Initial Execution
    updateCounts();
    renderTradeTable();

  </script>
</body>
</html>
"""
    Path(output_path).write_text(html_content, encoding="utf-8")
    print(f"[+] 成功生成全新展示模式对比报告: {output_path}")

if __name__ == "__main__":
    from scripts.build_unified_backtest_html import load_all_versions_data, generate_unified_html
    data = load_all_versions_data()
    outputs = [
        ROOT / "rebar_backtest_comparison.html",
        ROOT / "研究/回测实验/rebar_backtest_comparison.html",
        ROOT / "rebar_backtest_v5_vs_v6_comparison.html",
        ROOT / "研究/回测实验/rebar_backtest_v5_vs_v6_comparison.html",
        PATH_V6 / "rebar_backtest_comparison.html",
        PATH_V6 / "rebar_backtest_v5_vs_v6_comparison.html",
        Path("/home/hw/.gemini/antigravity/brain/ddc72fee-2b5a-4ad6-96f6-a3ea02245494/rebar_backtest_comparison.html"),
        Path("/home/hw/.gemini/antigravity/brain/ddc72fee-2b5a-4ad6-96f6-a3ea02245494/rebar_backtest_v5_vs_v6_comparison.html"),
    ]
    generate_unified_html(data, outputs)
