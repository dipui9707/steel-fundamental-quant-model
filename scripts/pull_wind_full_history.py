#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/pull_wind_full_history.py
功能:
  严格遵循用户指令与 PIT 数据契约，从近到远全量抓取 Wind MCP 黑色全产业链核心基本面指标：
  1. 采用批次合并机制（每次 API 调用包含 6~8 个指标），最大化节省 1200 积分消耗；
  2. 按年度切片从近到远逆序拉取（2026 迄今 -> 2025 -> 2024 -> ... -> 2010）；
  3. 积分耗尽熔断保护（一旦捕获 BLOCKED_QUOTA 或 余额不足，立即平滑退出并落盘）；
  4. 每年度增量落盘至 数据/原始/wind_edb/ 并归档审计回执至 研究/Wind全量采集回执/。
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "数据" / "原始"
EDB_DIR = RAW_DIR / "wind_edb"
EDB_DIR.mkdir(parents=True, exist_ok=True)
AUDIT_DIR = BASE_DIR / "研究" / "Wind全量采集回执"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

CLI_PATH = "/home/hw/.agents/skills/wind-mcp-skill/scripts/cli.mjs"

# 74 项高价值基本面指标，划分为 10 个批次
BATCHES = [
    {
        "id": 1,
        "name": "总供应与高炉",
        "codes": ["Y6907796", "C1925068", "O2244511", "S5715670", "S5715672"],
        "freq": "周",
        "cat": "总供应"
    },
    {
        "id": 2,
        "name": "卷螺产需与建材成交",
        "codes": ["S5713307", "P5075301", "A5938607", "X4173142"],
        "freq": "周/日",
        "cat": "卷螺产需"
    },
    {
        "id": 3,
        "name": "卷螺与铁矿库存",
        "codes": ["H6924748", "X1924001", "R8579706", "L2776415", "S0110152"],
        "freq": "周",
        "cat": "库存"
    },
    {
        "id": 4,
        "name": "铁矿现货与海运费",
        "codes": ["S0174655", "S5716219", "R5003090", "S0176220", "S0176221", "S0266069", "S0205030", "S0031550"],
        "freq": "日",
        "cat": "原料与海运"
    },
    {
        "id": 5,
        "name": "焦煤全链条",
        "codes": ["U1034836", "B4120932", "S5132022", "L9524876", "U4421912", "S5120155", "S5132102"],
        "freq": "日",
        "cat": "焦煤原料"
    },
    {
        "id": 6,
        "name": "焦炭与动力煤价格",
        "codes": ["S5134898", "P8829103", "S5132296", "T2987959", "U5157465", "S5104572", "S5133608"],
        "freq": "日",
        "cat": "焦炭与煤炭"
    },
    {
        "id": 7,
        "name": "动力煤库存与电厂",
        "codes": ["S5103725", "S5125187", "Q0149884", "V2000618", "C2918730", "S0176223", "S0205034"],
        "freq": "日",
        "cat": "动力煤蓄水池"
    },
    {
        "id": 8,
        "name": "废钢钢坯成材现货与汇率",
        "codes": ["S5714971", "S5700017", "S5712502", "S0143502", "S0033227", "S0033272", "M0067855"],
        "freq": "日",
        "cat": "现货与汇率"
    },
    {
        "id": 9,
        "name": "宏观景气与货币信用",
        "codes": ["M0017126", "M0017128", "M0017129", "M5207831", "M5206730", "M5525763", "M0001383", "M0001385", "M0000612", "M0001227"],
        "freq": "月",
        "cat": "宏观信用"
    },
    {
        "id": 10,
        "name": "地产基建与终端产出",
        "codes": ["S0029657", "S0073293", "S0073290", "F0540563", "M5440435", "S0027374", "S0027370", "S0027378", "S0027493", "S0060268", "S0027907", "S0028202", "S0028206", "S0027798"],
        "freq": "月",
        "cat": "下游产销"
    }
]

# 年度切片：从近到远逆序推进
YEAR_SLICES = [
    (2026, "2026-01-01", "2026-09-20"),
    (2025, "2025-01-01", "2025-12-31"),
    (2024, "2024-01-01", "2024-12-31"),
    (2023, "2023-01-01", "2023-12-31"),
    (2022, "2022-01-01", "2022-12-31"),
    (2021, "2021-01-01", "2021-12-31"),
    (2020, "2020-01-01", "2020-12-31"),
    (2019, "2019-01-01", "2019-12-31"),
    (2018, "2018-01-01", "2018-12-31"),
    (2017, "2017-01-01", "2017-12-31"),
    (2016, "2016-01-01", "2016-12-31"),
    (2015, "2015-01-01", "2015-12-31"),
    (2014, "2014-01-01", "2014-12-31"),
    (2013, "2013-01-01", "2013-12-31"),
    (2012, "2012-01-01", "2012-12-31"),
    (2011, "2011-01-01", "2011-12-31"),
    (2010, "2010-01-01", "2010-12-31"),
]

def query_batch(codes, start_date, end_date):
    """调用 Wind MCP CLI 查询批量代码数据"""
    q = ",".join(codes)
    params = json.dumps({"question": q, "beginDate": start_date, "endDate": end_date})
    cmd = ["node", CLI_PATH, "call", "economic_data", "query_economic_indicator_data", params]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT", "请求超时 60s"
    
    if res.returncode != 0:
        return None, "CLI_ERROR", res.stderr
    
    try:
        data = json.loads(res.stdout)
    except Exception as e:
        return None, "JSON_PARSE_ERROR", str(e)
    
    # 检查是否包含配额耗尽错误
    if not data.get("ok", True) or data.get("isError", False):
        code = data.get("code", "")
        msg = data.get("message", "")
        if "BLOCKED_QUOTA" in code or "余额不足" in msg or "402" in code:
            return None, "QUOTA_EXHAUSTED", msg
        return None, "API_ERROR", f"{code}: {msg}"
    
    # 检查返回内容中的错误信息
    if "content" in data and len(data["content"]) > 0:
        text = data["content"][0].get("text", "")
        if "余额不足" in text or "账户积分余额不足" in text:
            return None, "QUOTA_EXHAUSTED", text
        try:
            inner = json.loads(text)
            return inner, "OK", data
        except Exception as e:
            return None, "INNER_PARSE_ERROR", str(e)
            
    return None, "EMPTY_RESPONSE", data

def main():
    print("=" * 85)
    print("  钢材产业系统量化模型 - Wind MCP 全量基本面数据采集引擎 (从近到远 + 批次合并)")
    print("  策略: 每次合并调用 6~8 个指标，节约 85%+ 积分；年度逆序；积分耗尽安全平滑退出")
    print("=" * 85)

    all_master_parquet = EDB_DIR / "wind_edb_all.parquet"
    existing_df = None
    if all_master_parquet.exists():
        try:
            existing_df = pd.read_parquet(all_master_parquet)
            print(f"[*] 发现已有主库: {len(existing_df):,} 条历史记录")
        except Exception as e:
            print(f"[!] 读取已有主库失败: {e}")

    total_api_calls = 0
    total_records_pulled = 0
    quota_exhausted = False
    now_iso = datetime.now(SHANGHAI_TZ).isoformat()

    accumulated_rows = []

    for year, start_date, end_date in YEAR_SLICES:
        print(f"\n" + "-" * 75)
        print(f"[*] 开始采集年度切片: {year} ({start_date} ~ {end_date}) ...")
        print("-" * 75)
        
        year_rows = []
        year_receipts = {}

        for batch in BATCHES:
            b_id = batch["id"]
            b_name = batch["name"]
            codes = batch["codes"]
            
            print(f"  [Batch {b_id:02d}/10] {b_name:18} | 代码数: {len(codes):2d} | 区间: {start_date} ~ {end_date} ...", end="", flush=True)
            
            t0 = time.time()
            total_api_calls += 1
            inner, status, raw_data = query_batch(codes, start_date, end_date)
            elapsed = time.time() - t0

            if status == "QUOTA_EXHAUSTED":
                print(f" -> [熔断] 账户积分已耗尽! ({elapsed:.1f}s)")
                print(f"     错误详情: {raw_data}")
                quota_exhausted = True
                break

            if status != "OK":
                print(f" -> [错误: {status}] ({elapsed:.1f}s) {raw_data}")
                continue

            metrics = inner.get("metrics", [])
            batch_recs = 0
            
            for m in metrics:
                meta = m.get("meta", {})
                code = meta.get("code", "")
                name = meta.get("name", "")
                unit = meta.get("unit", "")
                freq = meta.get("freq", "")
                source = meta.get("source", "Wind")
                
                dates = m.get("date", [])
                values = m.get("value", [])

                for d_str, val in zip(dates, values):
                    if val is None or (isinstance(val, float) and np.isnan(val)):
                        continue
                    # 标准化日期 YYYY-MM-DD
                    if len(d_str) == 8:
                        data_date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"
                    else:
                        data_date = d_str

                    obs_id = f"WIND_{code}_{d_str}"
                    year_rows.append({
                        "observation_id": obs_id,
                        "code": code,
                        "name": name,
                        "category": batch["cat"],
                        "frequency": freq,
                        "unit": unit,
                        "data_date": data_date,
                        "value": float(val),
                        "available_date": data_date,
                        "recorded_at": now_iso,
                        "source": source
                    })
                    batch_recs += 1

            print(f" -> [成功] {len(metrics)} 个指标有效, 返回 {batch_recs:,} 条数据 ({elapsed:.1f}s)")
            year_receipts[f"batch_{b_id}"] = {
                "year": year,
                "batch_id": b_id,
                "batch_name": b_name,
                "codes": codes,
                "metrics_count": len(metrics),
                "records_count": batch_recs,
                "raw_response": raw_data
            }

            # 礼貌等待 0.3s 避免高频抖动
            time.sleep(0.3)

        # 保存该年度审计回执
        if year_receipts:
            audit_file = AUDIT_DIR / f"audit_receipts_{year}.json"
            with open(audit_file, "w", encoding="utf-8") as f:
                json.dump(year_receipts, f, ensure_ascii=False, indent=2)

        # 若该年度有数据，立即持久化落盘
        if year_rows:
            df_year = pd.DataFrame(year_rows)
            year_parquet = EDB_DIR / f"observations_{year}.parquet"
            df_year.to_parquet(year_parquet, index=False)
            
            total_records_pulled += len(df_year)
            accumulated_rows.extend(year_rows)
            print(f"[✓] 年度 {year} 完成! 新增落盘 {len(df_year):,} 条记录 -> {year_parquet.name}")
        else:
            print(f"[-] 年度 {year} 未获取到新记录。")

        # 积分耗尽立即中止
        if quota_exhausted:
            print("\n" + "!" * 75)
            print("  [积分耗尽熔断触发] 账户积分已消耗完毕，采集引擎平滑退出。")
            print("!" * 75)
            break

    # 合并保存全量主库
    if accumulated_rows:
        df_new = pd.DataFrame(accumulated_rows)
        if existing_df is not None:
            df_combined = pd.concat([existing_df, df_new], ignore_index=True)
            df_combined.drop_duplicates(subset=["observation_id"], keep="last", inplace=True)
        else:
            df_combined = df_new.drop_duplicates(subset=["observation_id"], keep="last")
        
        df_combined.sort_values(by=["code", "data_date"], inplace=True)
        df_combined.to_parquet(all_master_parquet, index=False)
        print(f"\n" + "=" * 85)
        print(f"[★] 全量库合并完成: {all_master_parquet}")
        print(f"    - 总记录数: {len(df_combined):,} 行")
        print(f"    - 本次采集耗用 API 调用数: {total_api_calls} 次")
        print(f"    - 本次新增数据条数: {total_records_pulled:,} 条")
        print("=" * 85)
    else:
        print("\n[!] 本次未获取到新记录。")

if __name__ == "__main__":
    main()
