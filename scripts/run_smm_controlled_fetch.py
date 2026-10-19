import json
import os
import sys
import time
import pandas as pd

sys.path.append("/home/hw/.gemini/antigravity/brain/1d6b414a-e618-4378-98ae-ea7d1e8d2e72/scratch")
from test_ranges import SmmMcpClient

API_KEY = "sk-ebded532758f488e0a378a8a320213023408eca85617bc07c4a433152ad9579b"

# 20项指标精确划分为 4 个批次，每批 5 个
BATCHES = [
    # 批次 1: 日度出口现货价格
    [
        "s22804474", # SMM: 热轧板卷: FOB 天津港, 中国: Q235B: 3.0*1250*C: 日度
        "s22804484", # SMM: 热轧板卷: FOB 京唐港, 中国: Q235B: 3.0*1250*C: 日度
        "s22813839", # SMM: 螺纹钢: FOB 天津港, 中国: Gr60: Φ16-20: 日度
        "s22813854", # SMM: 中厚板: FOB 京唐港, 中国: Q235B: 14-30mm: 日度
        "s22813804", # SMM: 方坯: FOB 天津港, 中国: 150*150: 3SP: 日度
    ],
    # 批次 2: 周度出港发运与排产
    [
        "a10148222", # 沸腾环贸: 钢材国内主要港口出港汇总: 32港: 周度
        "a10135358", # 沸腾环贸: 全球钢材分品种出港: 钢卷: 周度
        "a10135357", # 沸腾环贸: 全球钢材分品种出港: 钢棒: 周度
        "a10146512", # 沸腾环贸: 钢材内贸出港: 总量: 周度
        "a10102482", # SMM: 热卷本月计划出口量: 26家: 月度
    ],
    # 批次 3: 制造业实际耗钢量与前瞻预测
    [
        "a12885073", # SMM: 钢铁下游耗钢量: 汽车行业: 月度
        "a12885074", # SMM: 钢铁下游耗钢量: 家电行业: 月度
        "a12885072", # SMM: 钢铁下游耗钢量: 机械行业: 月度
        "a12885082", # SMM: 钢铁下游耗钢量: 汽车行业-预测: 月度
        "a12885083", # SMM: 钢铁下游耗钢量: 家电行业-预测: 月度
    ],
    # 批次 4: 深加工排产、表需与间接出口
    [
        "a12885081", # SMM: 钢铁下游耗钢量: 机械行业-预测: 月度
        "a12796380", # SMM: 冷轧本月计划产量: 31家: 月度
        "a12750001", # SMM: 热轧板卷表观需求: 大样本: 周度
        "a12817930", # 中国海关/SMM: 钢材间接出口总量: 月度
        "a12885068", # SMM: 钢铁下游耗钢量: 综合: 月度
    ]
]

def main():
    print("=== SMM CONTROLLED BATCH FETCHER ===")
    print(f"Total batches planned: {len(BATCHES)} (Exactly {len(BATCHES)} MCP calls)")
    
    # 复用之前已获取的元数据字典
    catalog_path = "/home/hw/.gemini/antigravity/brain/1d6b414a-e618-4378-98ae-ea7d1e8d2e72/scratch/smm_catalog_report.json"
    meta_dict = {}
    if os.path.exists(catalog_path):
        with open(catalog_path, "r", encoding="utf-8") as f:
            cat_data = json.load(f)
        for grp, items in cat_data.items():
            for it in items:
                meta_dict[it["indicator_id"]] = it
    
    # 补充日度价格的元数据（如果不在 catalog_path 中）
    extra_meta = {
        "s22804474": {"indicator_id": "s22804474", "name": "SMM: 热轧板卷: FOB 天津港, 中国: Q235B: 3.0*1250*C: 现货价格: 日度", "frequency": "日", "unit": "USD/tonne", "category": "出口价格/热卷FOB"},
        "s22804484": {"indicator_id": "s22804484", "name": "SMM: 热轧板卷: FOB 京唐港, 中国: Q235B: 3.0*1250*C: 现货价格: 日度", "frequency": "日", "unit": "USD/tonne", "category": "出口价格/热卷FOB"},
        "s22813839": {"indicator_id": "s22813839", "name": "SMM: 螺纹钢: FOB 天津港, 中国: Gr60: Φ16-20: 现货价格: 日度", "frequency": "日", "unit": "USD/tonne", "category": "出口价格/螺纹FOB"},
        "s22813854": {"indicator_id": "s22813854", "name": "SMM: 中厚板: FOB 京唐港, 中国: Q235B: 14-30mm: 现货价格: 日度", "frequency": "日", "unit": "USD/tonne", "category": "出口价格/中厚板FOB"},
        "s22813804": {"indicator_id": "s22813804", "name": "SMM: 方坯: FOB 天津港, 中国: 150*150: 3SP: 平均价: 日度", "frequency": "日", "unit": "USD/tonne", "category": "出口价格/方坯FOB"},
        "a10148222": {"indicator_id": "a10148222", "name": "沸腾环贸: 钢材出港: 钢材国内主要港口出港汇总: 32港: 周度", "frequency": "周", "unit": "万吨", "category": "港口发运/32港出港汇总"},
        "a10135358": {"indicator_id": "a10135358", "name": "沸腾环贸: 全球钢材分品种出港: 钢卷: 周度", "frequency": "周", "unit": "万吨", "category": "港口发运/钢卷出港"},
        "a10135357": {"indicator_id": "a10135357", "name": "沸腾环贸: 全球钢材分品种出港: 钢棒: 周度", "frequency": "周", "unit": "万吨", "category": "港口发运/钢棒出港"},
        "a10146512": {"indicator_id": "a10146512", "name": "沸腾环贸: 钢材内贸出港: 总量: 周度", "frequency": "周", "unit": "万吨", "category": "港口发运/内贸出港汇总"},
    }
    for k, v in extra_meta.items():
        if k not in meta_dict:
            meta_dict[k] = v

    client = SmmMcpClient(API_KEY)
    client.initialize()

    all_raw_receipts = []
    all_rows = []
    call_count = 0

    for idx, batch in enumerate(BATCHES, 1):
        print(f"\nExecuting Batch {idx}/{len(BATCHES)}: {batch}...")
        call_count += 1
        res = client.call_tool("smm_indicator_data_query", {
            "indicator_ids": ",".join(batch),
            "start_date": "2025-09-01",
            "end_date": "2026-09-30"
        })
        all_raw_receipts.append({
            "batch_index": idx,
            "requested_ids": batch,
            "response": res
        })
        
        if isinstance(res, dict) and res.get("data"):
            for ind_item in res["data"]:
                iid = ind_item.get("indicator_id")
                records = ind_item.get("records", [])
                meta = meta_dict.get(iid, {})
                ind_name = meta.get("name", iid)
                freq = meta.get("frequency", "")
                cat = meta.get("type_all", meta.get("category", ""))
                
                print(f" -> Indicator [{iid}] ({ind_name[:25]}...): {len(records)} records fetched")
                for r in records:
                    all_rows.append({
                        "date": r.get("date"),
                        "indicator_id": iid,
                        "indicator_name": ind_name,
                        "value": float(r.get("value")) if r.get("value") is not None and r.get("value") != "" else None,
                        "unit": r.get("unit") or meta.get("unit", ""),
                        "frequency": freq,
                        "category": cat
                    })
        else:
            print(f"Warning: Batch {idx} response unexpected: {res}")
        time.sleep(0.5)

    print(f"\n--- Fetch Complete! Total API calls made: {call_count} ---")
    assert call_count == 4, f"Expected exactly 4 calls, got {call_count}"

    # 1. 保存原始回执 JSON
    out_dir = "/home/hw/项目/钢材产业系统量化模型/数据/原始/smm"
    os.makedirs(out_dir, exist_ok=True)
    
    receipt_file = os.path.join(out_dir, "smm_raw_receipts.json")
    with open(receipt_file, "w", encoding="utf-8") as f:
        json.dump(all_raw_receipts, f, ensure_ascii=False, indent=2)
    print(f"1. Saved raw receipts to: {receipt_file}")

    # 2. 保存元数据字典 JSON
    meta_file = os.path.join(out_dir, "smm_indicators_metadata.json")
    # 过滤出这 20 项指标的完整元数据
    used_meta = {k: meta_dict.get(k, {}) for b in BATCHES for k in b}
    with open(meta_file, "w", encoding="utf-8") as f:
        json.dump(used_meta, f, ensure_ascii=False, indent=2)
    print(f"2. Saved metadata to: {meta_file}")

    # 3. 结构化 DataFrame 落盘
    df = pd.DataFrame(all_rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(by=["indicator_id", "date"]).reset_index(drop=True)

    parquet_file = os.path.join(out_dir, "smm_export_manufacturing.parquet")
    csv_file = os.path.join(out_dir, "smm_export_manufacturing.csv")
    
    df.to_parquet(parquet_file, index=False)
    df.to_csv(csv_file, index=False, encoding="utf-8-sig")
    print(f"3. Saved structured data to: {parquet_file} ({len(df)} rows)")
    print(f"   and {csv_file}")

    # 打印简要数据透视
    print("\nSummary by Indicator:")
    summary = df.groupby(["indicator_id", "frequency", "unit"]).agg(
        records_count=("value", "count"),
        start_date=("date", "min"),
        end_date=("date", "max"),
        latest_value=("value", "last")
    ).reset_index()
    print(summary.to_string(index=False))

if __name__ == "__main__":
    main()
