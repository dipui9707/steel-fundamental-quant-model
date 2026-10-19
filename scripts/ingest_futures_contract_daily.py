#!/usr/bin/env python3
"""
黑色五品种全合约日线数据标准化清洗与入库管道
来源: futures_data_2026-09-20.zip (解压至 数据/原始/期货合约全量日线/data/)
品种: RB (上期所螺纹), HC (上期所热卷), I (大商所铁矿), J (大商所焦炭), JM (大商所焦煤)
"""

import os
import sys
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
INPUT_DIR = BASE_DIR / "数据" / "原始" / "期货合约全量日线" / "data"
OUTPUT_DIR = BASE_DIR / "数据" / "原始" / "期货合约全量日线" / "standardized"

SYMBOL_CONFIG = {
    "rb": {"exchange": "SHFE", "name": "螺纹钢", "multiplier": 10, "default_margin": 0.08},
    "hc": {"exchange": "SHFE", "name": "热轧卷板", "multiplier": 10, "default_margin": 0.08},
    "i": {"exchange": "DCE", "name": "铁矿石", "multiplier": 100, "default_margin": 0.12},
    "j": {"exchange": "DCE", "name": "焦炭", "multiplier": 100, "default_margin": 0.15},
    "jm": {"exchange": "DCE", "name": "焦煤", "multiplier": 60, "default_margin": 0.15},
}

COLUMN_MAPPING = {
    "date": "date",
    "开盘价": "open",
    "最高价": "high",
    "最低价": "low",
    "收盘价": "close",
    "成交量": "volume",
    "oi": "open_interest",
    "结算价": "settlement",
    "合约代码": "contract_code",
    "交割月份": "delivery_month",
}


def process_symbol(symbol: str) -> pd.DataFrame:
    raw_file = INPUT_DIR / f"{symbol}_data.parquet"
    if not raw_file.exists():
        raise FileNotFoundError(f"Missing input parquet: {raw_file}")
    
    print(f"Reading {raw_file.name}...")
    df = pd.read_parquet(raw_file)
    cfg = SYMBOL_CONFIG[symbol]
    
    # 1. 重命名列
    df = df.rename(columns=COLUMN_MAPPING)
    
    # 2. 规范数据类型
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    for col in ["open", "high", "low", "close", "settlement"]:
        df[col] = df[col].astype(float)
    df["volume"] = df["volume"].astype(float)
    df["open_interest"] = df["open_interest"].astype(float)
    df["contract_code"] = df["contract_code"].astype(str)
    df["delivery_month"] = df["delivery_month"].astype(str)
    
    # 3. 增加品种和交易所标识
    df["symbol"] = symbol
    df["variety_name"] = cfg["name"]
    df["exchange"] = cfg["exchange"]
    df["multiplier"] = cfg["multiplier"]
    df["default_margin_rate"] = cfg["default_margin"]
    
    # 4. 规范全局统一合约全称 full_symbol
    def make_full_symbol(row):
        code = row["contract_code"]
        exch = row["exchange"]
        sym = row["symbol"]
        if code in ("main", "index"):
            return f"{exch}.{sym}_{code}"
        else:
            return f"{exch}.{sym}{code}"
            
    df["full_symbol"] = df.apply(make_full_symbol, axis=1)
    
    # 5. 合约类型标识: MAIN / INDEX / SPECIFIC
    def classify_contract(code):
        if code == "main":
            return "MAIN"
        elif code == "index":
            return "INDEX"
        else:
            return "SPECIFIC"
            
    df["contract_type"] = df["contract_code"].apply(classify_contract)
    
    # 5.1 自动校准 MAIN 连续主力合约在历史区间被收盘价代替的假结算价
    # 利用 2019-2026 年已有的真实具体月份实约官方结算价进行反向映射精准对齐
    specific_df = df[df["contract_type"] == "SPECIFIC"]
    main_mask = df["contract_type"] == "MAIN"
    
    active_by_date = {}
    for dt, group in specific_df.groupby("date"):
        active_by_date[dt] = group
        
    corrected_count = 0
    for idx in df[main_mask].index:
        dt = df.loc[idx, "date"]
        if dt in active_by_date:
            spec_dt = active_by_date[dt]
            m_close = df.loc[idx, "close"]
            m_oi = df.loc[idx, "open_interest"]
            m_low = df.loc[idx, "low"]
            m_high = df.loc[idx, "high"]
            # 只有当具体实约的 close 严格一致且其结算价位于 [low, high] 时才进行校准
            cand = spec_dt[(spec_dt["close"] == m_close) & (spec_dt["open_interest"] == m_oi)]
            if cand.empty:
                cand = spec_dt[spec_dt["close"] == m_close]
            if not cand.empty:
                real_settle = float(cand.iloc[0]["settlement"])
                if m_low <= real_settle <= m_high:
                    if df.loc[idx, "settlement"] != real_settle:
                        df.loc[idx, "settlement"] = real_settle
                        corrected_count += 1
                
    print(f"[{symbol.upper()}] 成功校准主连 (MAIN) 历史真实结算价: {corrected_count} 个交易日")

    # 5.2 兜底校验：任何合约若出现 settlement < low 或 settlement > high 的异常脏数据，安全对齐至 close
    bad_settle_mask = (df["settlement"] < df["low"]) | (df["settlement"] > df["high"])
    bad_count = int(bad_settle_mask.sum())
    if bad_count > 0:
        print(f"[{symbol.upper()}] 修正了 {bad_count} 条结算价超出 [low, high] 范围的脏数据，已安全对齐至 close")
        df.loc[bad_settle_mask, "settlement"] = df.loc[bad_settle_mask, "close"]

    
    # 6. 排序
    df = df.sort_values(by=["date", "contract_type", "contract_code"]).reset_index(drop=True)
    
    # 7. 质量审计校验
    assert not df.isnull().any().any(), f"Found nulls in {symbol} cleaned data!"
    assert (df["volume"] >= 0).all(), f"Negative volume found in {symbol}!"
    assert (df["open_interest"] >= 0).all(), f"Negative open interest found in {symbol}!"
    assert (df["close"] > 0).all(), f"Non-positive close found in {symbol}!"
    assert (df["settlement"] > 0).all(), f"Non-positive settlement found in {symbol}!"
    
    print(f"Processed {symbol}: {len(df)} rows, dates {df['date'].min()} to {df['date'].max()}, {df['contract_code'].nunique()} unique codes.")
    return df


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    all_dfs = []
    for symbol in ["rb", "hc", "i", "j", "jm"]:
        df_sym = process_symbol(symbol)
        out_sym_path = OUTPUT_DIR / f"{symbol}_daily.parquet"
        df_sym.to_parquet(out_sym_path, index=False, engine="pyarrow", compression="snappy")
        print(f"Saved standardized symbol file: {out_sym_path}")
        all_dfs.append(df_sym)
        
    combined_df = pd.concat(all_dfs, ignore_index=True)
    combined_df = combined_df.sort_values(by=["date", "symbol", "contract_type", "contract_code"]).reset_index(drop=True)
    out_all_path = OUTPUT_DIR / "futures_all_daily.parquet"
    combined_df.to_parquet(out_all_path, index=False, engine="pyarrow", compression="snappy")
    print(f"\nSaved combined futures dataset: {out_all_path} with {len(combined_df)} rows.")
    
    # 打印概况
    summary = combined_df.groupby("symbol").agg(
        total_rows=("date", "count"),
        min_date=("date", "min"),
        max_date=("date", "max"),
        contract_count=("contract_code", "nunique"),
    )
    print("\n=== Ingestion Summary ===")
    print(summary)


if __name__ == "__main__":
    main()
