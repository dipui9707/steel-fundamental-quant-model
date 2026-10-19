#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SMM 数据受控安全更新脚本 (带配额断路器保护)
----------------------------------------
规则与约束:
1. 每天 MCP 调用额度上限为 25 次；
2. 本脚本将 20 项核心指标严格分为 4 个批次（每批 5 个指标），单次运行恰好消耗 4 次配额；
3. 内置断路器: 若当天调用记录 >= 15 次，立即熔断中止，坚决保护剩余配额；
4. 增量拉取最近 45 天数据，与本地已落盘的 parquet 进行去重合并；
5. 同步维护原始回执 smm_raw_receipts.json 与调用审计日志 smm_call_audit.json。
"""

import os
import sys
import json
import time
import datetime
import pandas as pd

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from smm_client import SmmMcpClient

API_KEY = "sk-ebded532758f488e0a378a8a320213023408eca85617bc07c4a433152ad9579b"
DAILY_CALL_LIMIT = 15  # 保守安全阈值 (用户总额度25次)
SMM_DIR = os.path.join(PROJECT_ROOT, "数据/原始/smm")
AUDIT_LOG_FILE = os.path.join(SMM_DIR, "smm_call_audit.json")
RECEIPTS_FILE = os.path.join(SMM_DIR, "smm_raw_receipts.json")

# 20 项核心指标批次
BATCHES = [
    ["s22804474", "s22804484", "s22813839", "s22813854", "s22813804"],  # 批次1: 日度出口价格
    ["a10148222", "a10135358", "a10135357", "a10146512", "a10102482"],  # 批次2: 周度出港与月度排产
    ["a12885073", "a12885074", "a12885072", "a12885082", "a12885083"],  # 批次3: 制造业实际与预测
    ["a12885081", "a12796380", "a12750001", "a12817930", "a12885068"],  # 批次4: 表需/冷轧/间接出口
]


def check_and_record_quota(calls_to_make=4):
    """配额断路器：检查当天调用频次"""
    today_str = datetime.date.today().isoformat()
    audit_data = {}
    if os.path.exists(AUDIT_LOG_FILE):
        try:
            with open(AUDIT_LOG_FILE, "r", encoding="utf-8") as f:
                audit_data = json.load(f)
        except Exception:
            audit_data = {}

    today_calls = audit_data.get(today_str, 0)
    print(f"[Quota Breaker] Today ({today_str}) calls recorded: {today_calls}/{DAILY_CALL_LIMIT}")

    if today_calls + calls_to_make > DAILY_CALL_LIMIT:
        raise PermissionError(
            f"Quota Circuit Breaker Triggered! Today's calls ({today_calls}) + requested ({calls_to_make}) "
            f"exceeds safe threshold ({DAILY_CALL_LIMIT}). Abortion to protect daily quota!"
        )
    return audit_data, today_str, today_calls


def update_audit(audit_data, today_str, actual_calls):
    audit_data[today_str] = audit_data.get(today_str, 0) + actual_calls
    with open(AUDIT_LOG_FILE, "w", encoding="utf-8") as f:
        json.dump(audit_data, f, ensure_ascii=False, indent=2)
    print(f"[Quota Breaker] Updated call count for {today_str}: {audit_data[today_str]}")


def update_raw_receipts(new_receipts):
    """保存/增量更新原始回执"""
    os.makedirs(SMM_DIR, exist_ok=True)
    existing_receipts = []
    if os.path.exists(RECEIPTS_FILE):
        try:
            with open(RECEIPTS_FILE, "r", encoding="utf-8") as f:
                existing_receipts = json.load(f)
        except Exception:
            existing_receipts = []

    # 将新抓取回执追加/覆盖
    existing_receipts.extend(new_receipts)
    # 保留最近 20 次批次抓取回执，避免体积无限膨胀
    if len(existing_receipts) > 20:
        existing_receipts = existing_receipts[-20:]

    with open(RECEIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(existing_receipts, f, ensure_ascii=False, indent=2)
    print(f"[Audit] Updated raw receipts in: {RECEIPTS_FILE}")


def main():
    print("=" * 80)
    print("=== SMM SAFE DATA UPDATER (CIRCUIT BREAKER PROTECTED) ===")
    print("=" * 80)

    # 1. 检查断路器
    audit_data, today_str, _ = check_and_record_quota(calls_to_make=len(BATCHES))

    # 2. 读取元数据字典
    meta_file = os.path.join(SMM_DIR, "smm_indicators_metadata.json")
    with open(meta_file, "r", encoding="utf-8") as f:
        meta_dict = json.load(f)

    client = SmmMcpClient(API_KEY)
    init_info = client.initialize()
    if isinstance(init_info, dict) and "error" in init_info:
        raise RuntimeError(f"Failed to initialize SMM MCP client: {init_info['error']}")

    # 拉取区间设定为近 45 天 (增量回溯，覆盖周度和月度修订)
    start_date = (datetime.date.today() - datetime.timedelta(days=45)).isoformat()
    end_date = (datetime.date.today() + datetime.timedelta(days=15)).isoformat()
    print(f"Fetch Date Range: {start_date} ~ {end_date}")

    new_rows = []
    actual_calls = 0
    batch_receipts = []

    for idx, batch in enumerate(BATCHES, 1):
        print(f"Calling Batch {idx}/{len(BATCHES)} (IDs: {batch})...")
        actual_calls += 1
        res = client.call_tool("smm_indicator_data_query", {
            "indicator_ids": ",".join(batch),
            "start_date": start_date,
            "end_date": end_date
        })

        batch_receipts.append({
            "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "batch_index": idx,
            "requested_ids": batch,
            "response": res
        })

        if isinstance(res, dict) and res.get("data"):
            for d in res["data"]:
                iid = d.get("indicator_id")
                records = d.get("records", [])
                meta = meta_dict.get(iid, {})
                print(f"  -> Indicator [{iid}] ({meta.get('name', iid)[:25]}): {len(records)} records")
                for r in records:
                    new_rows.append({
                        "date": r.get("date"),
                        "indicator_id": iid,
                        "indicator_name": meta.get("name", iid),
                        "value": float(r.get("value")) if r.get("value") is not None and r.get("value") != "" else None,
                        "unit": r.get("unit") or meta.get("unit", ""),
                        "frequency": meta.get("frequency", ""),
                        "category": meta.get("type_all", meta.get("category", ""))
                    })
        time.sleep(0.5)

    # 3. 记录实际调用配额与回执
    update_audit(audit_data, today_str, actual_calls)
    update_raw_receipts(batch_receipts)

    # 4. 合并本地已有 parquet
    parquet_path = os.path.join(SMM_DIR, "smm_export_manufacturing.parquet")
    csv_path = os.path.join(SMM_DIR, "smm_export_manufacturing.csv")

    if os.path.exists(parquet_path):
        old_df = pd.read_parquet(parquet_path)
        print(f"Existing parquet loaded: {len(old_df)} rows")
    else:
        old_df = pd.DataFrame()

    new_df = pd.DataFrame(new_rows)
    new_df["date"] = pd.to_datetime(new_df["date"])

    combined = pd.concat([old_df, new_df], ignore_index=True)
    # 按 indicator_id 与 date 去重，保留最新更新的一条
    combined = combined.drop_duplicates(subset=["indicator_id", "date"], keep="last")
    combined = combined.sort_values(by=["indicator_id", "date"]).reset_index(drop=True)

    combined.to_parquet(parquet_path, index=False)
    combined.to_csv(csv_path, index=False, encoding="utf-8-sig")
    print(f"\n[✓] SMM Update Complete! Total rows now: {len(combined)} (Parsed from API: {len(new_df)})")

    # 打印最新截面日期
    print("\n--- SMM 最新数据日期透视 ---")
    latest_summary = combined.groupby(["indicator_id", "indicator_name", "frequency"]).agg(
        records_count=("value", "count"),
        max_date=("date", "max"),
        latest_value=("value", "last")
    ).reset_index()
    print(latest_summary.to_string(index=False))


if __name__ == "__main__":
    main()
