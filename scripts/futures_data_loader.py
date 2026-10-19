#!/usr/bin/env python3
"""
黑色五品种期货全合约数据访问适配器 (Futures DataLoader API)
统一提供：
1. 连续主力合约序列 (Continuous Main Contract)
2. 全市场综合指数序列与沉淀资金 (Market Aggregate & Sedimentation Capital)
3. 期限结构曲线切片 (Term Structure Forward Curve)
4. 跨期月间价差 (Calendar Spreads: 01-05, 05-10, 10-01 等)
5. 展期收益率与升贴水斜率 (Roll Yield & Contango/Backwardation Slope)
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
STANDARDIZED_DIR = BASE_DIR / "数据" / "原始" / "期货合约全量日线" / "standardized"

SYMBOL_SPECS = {
    "rb": {"exchange": "SHFE", "name": "螺纹钢", "multiplier": 10, "default_margin": 0.08, "main_months": ["01", "05", "10"]},
    "hc": {"exchange": "SHFE", "name": "热轧卷板", "multiplier": 10, "default_margin": 0.08, "main_months": ["01", "05", "10"]},
    "i": {"exchange": "DCE", "name": "铁矿石", "multiplier": 100, "default_margin": 0.12, "main_months": ["01", "05", "09"]},
    "j": {"exchange": "DCE", "name": "焦炭", "multiplier": 100, "default_margin": 0.15, "main_months": ["01", "05", "09"]},
    "jm": {"exchange": "DCE", "name": "焦煤", "multiplier": 60, "default_margin": 0.15, "main_months": ["01", "05", "09"]},
}

_CACHE: Dict[str, pd.DataFrame] = {}


def load_symbol_data(symbol: str) -> pd.DataFrame:
    """按品种加载标准化全合约日线数据"""
    symbol = symbol.lower()
    if symbol not in SYMBOL_SPECS:
        raise ValueError(f"Unknown symbol: {symbol}. Available: {list(SYMBOL_SPECS.keys())}")
    
    if symbol not in _CACHE:
        file_path = STANDARDIZED_DIR / f"{symbol}_daily.parquet"
        if not file_path.exists():
            raise FileNotFoundError(f"Standardized parquet not found: {file_path}")
        _CACHE[symbol] = pd.read_parquet(file_path)
    return _CACHE[symbol]


def get_continuous_main(symbol: str) -> pd.DataFrame:
    """获取指定品种连续主力日线序列 (2016-2026)"""
    df = load_symbol_data(symbol)
    sub = df[df["contract_type"] == "MAIN"].copy()
    return sub.sort_values("date").reset_index(drop=True)


def get_market_aggregate(symbol: str) -> pd.DataFrame:
    """获取指定品种全市场加权综合指数与总量序列 (2016-2026)"""
    df = load_symbol_data(symbol)
    sub = df[df["contract_type"] == "INDEX"].copy()
    spec = SYMBOL_SPECS[symbol.lower()]
    # 计算估算沉淀资金 (亿元) = OI * 结算价 * 合约乘数 * 保证金率 / 1e8
    sub["sedimentation_capital_cny_yi"] = (
        sub["open_interest"] * sub["settlement"] * spec["multiplier"] * spec["default_margin"] / 1e8
    ).round(4)
    return sub.sort_values("date").reset_index(drop=True)


def get_forward_curve(symbol: str, trade_date: str) -> pd.DataFrame:
    """
    获取指定交易日该品种的所有存续具体交割月份合约曲线 (Forward Curve)
    按交割月份/合约代码升序排列
    """
    df = load_symbol_data(symbol)
    sub = df[(df["date"] == trade_date) & (df["contract_type"] == "SPECIFIC")].copy()
    return sub.sort_values("contract_code").reset_index(drop=True)


def get_contract_daily(symbol: str, contract_code: str) -> pd.DataFrame:
    """获取单个指定合约的日线时序 (如 rb2405)"""
    df = load_symbol_data(symbol)
    sub = df[df["contract_code"] == str(contract_code)].copy()
    return sub.sort_values("date").reset_index(drop=True)


def get_specific_calendar_spread(
    symbol: str,
    near_contract: str,
    far_contract: str,
    price_col: str = "close"
) -> pd.DataFrame:
    """
    计算两个具体合约之间的价差时序: near_contract - far_contract
    正值: 近月升水 (Backwardation)
    负值: 近月贴水 (Contango)
    """
    df = load_symbol_data(symbol)
    near_df = df[df["contract_code"] == str(near_contract)][["date", price_col, "open_interest"]].rename(
        columns={price_col: f"price_near", "open_interest": "oi_near"}
    )
    far_df = df[df["contract_code"] == str(far_contract)][["date", price_col, "open_interest"]].rename(
        columns={price_col: f"price_far", "open_interest": "oi_far"}
    )
    merged = pd.merge(near_df, far_df, on="date", how="inner")
    merged["spread"] = merged["price_near"] - merged["price_far"]
    merged["symbol"] = symbol
    merged["near_contract"] = near_contract
    merged["far_contract"] = far_contract
    return merged.sort_values("date").reset_index(drop=True)


def get_active_calendar_spread(
    symbol: str,
    price_col: str = "close"
) -> pd.DataFrame:
    """
    计算主力合约与次主力合约之间的动态价差及年化展期收益率
    按每个交易日持仓量（OI）第一大（主力）与第二大（次主力）匹配
    """
    df = load_symbol_data(symbol)
    specific_df = df[df["contract_type"] == "SPECIFIC"].copy()
    
    results = []
    for dt, group in specific_df.groupby("date"):
        top2 = group.sort_values("open_interest", ascending=False).head(2)
        if len(top2) < 2:
            continue
        c1, c2 = top2.iloc[0], top2.iloc[1]
        # 判断谁是近月，谁是远月
        if str(c1["contract_code"]) < str(c2["contract_code"]):
            near, far = c1, c2
        else:
            near, far = c2, c1
            
        p_near = near[price_col]
        p_far = far[price_col]
        spread = p_near - p_far
        
        # 计算两个合约到期相隔月数
        y1, m1 = int("20" + str(near["contract_code"])[:2]), int(str(near["contract_code"])[2:])
        y2, m2 = int("20" + str(far["contract_code"])[:2]), int(str(far["contract_code"])[2:])
        months_diff = max(1, (y2 - y1) * 12 + (m2 - m1))
        
        # 年化展期收益率: ((p_near - p_far) / p_far) * (12 / months_diff)
        roll_yield = ((p_near - p_far) / p_far) * (12.0 / months_diff)
        
        results.append({
            "date": dt,
            "symbol": symbol,
            "near_code": near["contract_code"],
            "far_code": far["contract_code"],
            "price_near": p_near,
            "price_far": p_far,
            "spread": spread,
            "months_diff": months_diff,
            "roll_yield_annual": round(roll_yield, 6),
            "oi_near": near["open_interest"],
            "oi_far": far["open_interest"],
        })
        
    return pd.DataFrame(results).sort_values("date").reset_index(drop=True)


if __name__ == "__main__":
    # 快速自检演示
    print("=== Testing Futures DataLoader API ===")
    rb_main = get_continuous_main("rb")
    print(f"RB Main: {len(rb_main)} rows, latest: {rb_main.iloc[-1]['date']} close={rb_main.iloc[-1]['close']}")
    
    rb_agg = get_market_aggregate("rb")
    print(f"RB Agg: latest sedimentation capital: {rb_agg.iloc[-1]['sedimentation_capital_cny_yi']} 亿元")
    
    curve = get_forward_curve("rb", "2024-03-15")
    print(f"RB Forward Curve on 2024-03-15 ({len(curve)} contracts):")
    for _, row in curve.iterrows():
        print(f"  {row['contract_code']}: close={row['close']}, settlement={row['settlement']}, oi={int(row['open_interest'])}")
        
    spread_top2 = get_active_calendar_spread("rb")
    print(f"\nRB Active Calendar Spread ({len(spread_top2)} trading days):")
    print(spread_top2.tail(5)[["date", "near_code", "far_code", "spread", "roll_yield_annual"]])
