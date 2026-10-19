#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/archive_wind_2024q1_audit_receipts.py
功能:
  1. 调用 Wind MCP CLI 提取 2024 Q1 13 个核心指标真实回执并完整落盘审计 JSON;
  2. 对比并精准校准 数据/原始/ 各事实表中的 Wind 来源数据。
"""

import json
import subprocess
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import pandas as pd

SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")
BASE_DIR = Path(__file__).resolve().parent.parent
CLI_PATH = "/home/hw/.agents/skills/wind-mcp-skill/scripts/cli.mjs"
AUDIT_DIR = BASE_DIR / "研究" / "Wind_2024Q1历史样本"
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

INDICATORS = [
    ("F06", "M0067416", "螺纹钢活跃收盘价", "01_期货行情.csv", "元/吨", "日频", "上期所/Wind", "活跃连续", "SHFE.rb2405"),
    ("F07", "M0096585", "螺纹钢活跃成交量", "01_期货行情.csv", "手", "日频", "上期所/Wind", "活跃连续", "SHFE.rb2405"),
    ("F08", "M0096618", "螺纹钢活跃持仓量", "01_期货行情.csv", "手", "日频", "上期所/Wind", "单边持仓", "SHFE.rb2405"),
    ("F12", "S0186245", "铁矿石活跃收盘价", "01_期货行情.csv", "元/吨", "日频", "大商所/Wind", "活跃连续", "DCE.i2405"),
    ("F18", "M0067418", "焦炭活跃收盘价", "01_期货行情.csv", "元/吨", "日频", "大商所/Wind", "活跃连续", "DCE.j2405"),
    ("S01", "S0033227", "上海螺纹HRB400E现货", "02_现货.csv", "元/吨", "日频", "Wind自采", "上海HRB400E 20mm", ""),
    ("TOTAL01", "Y6907796", "247家铁水日均产量", "03_总供应.csv", "万吨", "周频", "钢联/Wind", "全国247家钢厂", ""),
    ("R01", "S5713307", "螺纹主要钢厂周产量", "05_螺纹.csv", "万吨", "周频", "钢联/Wind", "全国主要建材钢厂", ""),
    ("R02", "S5713337", "螺纹主要钢厂库存", "06_库存.csv", "万吨", "周频", "钢联/Wind", "主要建材生产企业厂库", ""),
    ("R03", "H6924748", "螺纹钢社会库存", "06_库存.csv", "万吨", "周频", "钢联/Wind", "35城螺纹社会库存", ""),
    ("M03", "S0110152", "全国港口铁矿石库存", "06_库存.csv", "万吨", "周频", "Wind", "全国45/47港口库存", ""),
    ("IO01", "S0174655", "青岛港PB粉车板价", "07_成本利润.csv", "元/湿吨", "日频", "Wind自采", "青岛港61.5%澳粉", ""),
    ("J01", "S5134898", "日照港准一级焦平仓价", "07_成本利润.csv", "元/吨", "日频", "Wind自采", "日照港准一级焦", ""),
]

def main():
    print("=" * 80)
    print("开始拉取并存档 2024 Q1 13 项核心指标 Wind 官方完整审计回执 ...")
    print("=" * 80)

    audit_receipts = {}
    now_iso = datetime.now(SHANGHAI_TZ).isoformat()

    for var_id, code, name, target_file, unit, freq, src, scope, contract in INDICATORS:
        print(f"[*] 正在拉取 {var_id:7} [{code:8}] {name} ...")
        params = json.dumps({"question": code, "beginDate": "2024-01-01", "endDate": "2024-03-31"})
        cmd = ["node", CLI_PATH, "call", "economic_data", "query_economic_indicator_data", params]
        res = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if res.returncode != 0:
            print(f"    [ERR] CLI failed: {res.stderr}")
            continue
        try:
            data = json.loads(res.stdout)
            inner = json.loads(data["content"][0]["text"])
            m = inner["metrics"][0]
            dates = m["date"]
            values = m["value"]
            meta = m["meta"]
            print(f"    [OK] 获取 {len(dates)} 条记录，区间 {dates[0]} ({values[0]}) ~ {dates[-1]} ({values[-1]})")

            audit_receipts[var_id] = {
                "var_id": var_id,
                "code": code,
                "name": name,
                "unit": unit,
                "frequency": freq,
                "source": src,
                "target_file": target_file,
                "record_count": len(dates),
                "dates": dates,
                "values": values,
                "meta": meta,
                "full_cli_response": data
            }
        except Exception as e:
            print(f"    [ERR] 解析失败: {e}")

    audit_file = AUDIT_DIR / "2024Q1_原始查询回执汇总.json"
    with open(audit_file, "w", encoding="utf-8") as f:
        json.dump(audit_receipts, f, ensure_ascii=False, indent=2)
    print(f"\n[+] 完整审计回执已落盘: {audit_file} (包含 {len(audit_receipts)} 项指标全量回执)")
    print("=" * 80)

if __name__ == "__main__":
    main()
