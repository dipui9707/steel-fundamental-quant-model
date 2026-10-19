#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/update_wind_data.py
功能:
  Wind EDB 黑色全产业链核心基本面指标受控增量更新脚本
  1. 采用批次合并机制 (10 个批次覆盖 74 项核心指标)，每次 API 调用包含 4~14 个指标；
  2. 增量拉取最近 30 天数据 (2026-08-20 ~ 当前日期)，覆盖周度/月度最新修正与日度更新；
  3. 与本地已落盘的 wind_edb_all.parquet 与 observations_2026.parquet 进行去重合并；
  4. 归档本次增量采集审计回执至 研究/Wind全量采集回执/audit_receipts_update_<YYYYMMDD>.json。
"""

import os
import sys
import json
import time
import subprocess
from datetime import datetime, date, timedelta
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

# 74 项核心基本面指标划分的 10 个标准批次
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


def query_batch(codes, start_date, end_date):
    """调用 Wind MCP CLI 查询批量代码数据"""
    q = ",".join(codes)
    params = json.dumps({"question": q, "beginDate": start_date, "endDate": end_date})
    cmd = ["node", CLI_PATH, "call", "economic_data", "query_economic_indicator_data", params]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except subprocess.TimeoutExpired:
        return None, "TIMEOUT", "请求超时 60s"

    data = None
    if res.stdout:
        try:
            data = json.loads(res.stdout)
        except Exception:
            pass

    if data is not None:
        if not data.get("ok", True) or data.get("isError", False):
            code = str(data.get("code", ""))
            msg = str(data.get("message", ""))
            if "BLOCKED_QUOTA" in code or "余额不足" in msg or "402" in code:
                return None, "QUOTA_EXHAUSTED", msg
            return None, "API_ERROR", f"{code}: {msg}"
    elif res.returncode != 0:
        return None, "CLI_ERROR", res.stderr or res.stdout

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
    print("  钢材产业系统量化模型 - Wind EDB 核心指标受控增量更新引擎")
    print("  策略: 10个批次合并拉取，单次调用覆盖 74 项核心指标；增量回溯 30 天")
    print("=" * 85)

    today = date.today()
    today_str = today.isoformat()
    # 回溯 30 天，覆盖周度和月度最新修订
    start_date = (today - timedelta(days=30)).isoformat()
    end_date = today_str

    print(f"[*] 增量拉取区间: {start_date} ~ {end_date}")

    all_master_parquet = EDB_DIR / "wind_edb_all.parquet"
    existing_df = None
    if all_master_parquet.exists():
        try:
            existing_df = pd.read_parquet(all_master_parquet)
            print(f"[*] 已加载现有主库: {len(existing_df):,} 条历史记录 (最新日期: {existing_df['data_date'].max()})")
        except Exception as e:
            print(f"[!] 读取已有主库失败: {e}")

    total_api_calls = 0
    now_iso = datetime.now(SHANGHAI_TZ).isoformat()
    new_rows = []
    update_receipts = {}
    quota_exhausted = False

    for batch in BATCHES:
        b_id = batch["id"]
        b_name = batch["name"]
        codes = batch["codes"]

        print(f"  [Batch {b_id:02d}/10] {b_name:18} | 代码数: {len(codes):2d} ...", end="", flush=True)

        # 针对 >5 个指标的批次按 5 个一组分块，避免 Wind 后端超时
        CHUNK_SIZE = 5
        code_chunks = [codes[i:i + CHUNK_SIZE] for i in range(0, len(codes), CHUNK_SIZE)]

        all_batch_metrics = []
        batch_raw_responses = []
        batch_elapsed = 0.0

        for chunk_idx, chunk_codes in enumerate(code_chunks, 1):
            t0 = time.time()
            total_api_calls += 1
            inner, status, raw_data = query_batch(chunk_codes, start_date, end_date)
            elapsed = time.time() - t0
            batch_elapsed += elapsed

            if status == "QUOTA_EXHAUSTED":
                print(f" -> [熔断] 账户积分已耗尽! ({batch_elapsed:.1f}s)")
                print(f"     错误详情: {raw_data}")
                quota_exhausted = True
                break

            if status != "OK":
                print(f" [Chunk {chunk_idx}: 错误 {status} ({elapsed:.1f}s)]", end="", flush=True)
                continue

            metrics = inner.get("metrics", [])
            all_batch_metrics.extend(metrics)
            batch_raw_responses.append(raw_data)
            time.sleep(0.3)

        if quota_exhausted:
            break

        batch_recs = 0
        for m in all_batch_metrics:
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
                new_rows.append({
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

        print(f" -> [成功] {len(all_batch_metrics)} 个指标有效, 返回 {batch_recs} 条数据 ({batch_elapsed:.1f}s)")
        update_receipts[f"batch_{b_id}"] = {
            "batch_id": b_id,
            "batch_name": b_name,
            "codes": codes,
            "metrics_count": len(all_batch_metrics),
            "records_count": batch_recs,
            "raw_response": batch_raw_responses
        }
        time.sleep(0.3)

    # 1. 保存审计回执
    today_tag = today_str.replace("-", "")
    audit_file = AUDIT_DIR / f"audit_receipts_update_{today_tag}.json"
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(update_receipts, f, ensure_ascii=False, indent=2)
    print(f"\n[Audit] 增量审计回执已保存: {audit_file.name}")

    # 2. 合并主库
    if new_rows:
        df_new = pd.DataFrame(new_rows)
        print(f"[*] 解析到 API 新数据记录: {len(df_new):,} 条")

        if existing_df is not None:
            df_combined = pd.concat([existing_df, df_new], ignore_index=True)
            df_combined.drop_duplicates(subset=["observation_id"], keep="last", inplace=True)
        else:
            df_combined = df_new.drop_duplicates(subset=["observation_id"], keep="last")

        df_combined.sort_values(by=["code", "data_date"], inplace=True)
        df_combined.to_parquet(all_master_parquet, index=False)
        print(f"[✓] 主库更新完成: {all_master_parquet.name} -> 总计 {len(df_combined):,} 行")

        # 3. 同步更新 2026 年度切片
        obs_2026_file = EDB_DIR / "observations_2026.parquet"
        df_2026 = df_combined[df_combined["data_date"] >= "2026-01-01"]
        df_2026.to_parquet(obs_2026_file, index=False)
        print(f"[✓] 2026年度切片已同步: {obs_2026_file.name} -> 总计 {len(df_2026):,} 行")

        # 4. 打印最新日期透视
        print("\n--- Wind 最新数据日期透视 ---")
        summary = df_combined.groupby(["category", "frequency"]).agg(
            latest_date=("data_date", "max"),
            code_count=("code", "nunique"),
            total_records=("value", "count")
        ).reset_index()
        print(summary.to_string(index=False))
    else:
        print("\n[!] 本次未获取到新记录。")

    print(f"\nAPI 调用统计: 共发起 {total_api_calls} 次调用, 成功消耗完成。")


if __name__ == "__main__":
    main()
