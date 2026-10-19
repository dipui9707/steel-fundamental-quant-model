#!/usr/bin/env python3
"""
单元测试: 期货全合约标准化数据与 Futures DataLoader API 检验
"""

import unittest
from pathlib import Path
import pandas as pd
import numpy as np

import sys
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from scripts.futures_data_loader import (
    load_symbol_data,
    get_continuous_main,
    get_market_aggregate,
    get_forward_curve,
    get_specific_calendar_spread,
    get_active_calendar_spread,
    SYMBOL_SPECS
)


class TestFuturesDataLoader(unittest.TestCase):

    def test_load_all_symbols(self):
        """测试五大黑色品种标准化数据能否正常加载且结构完备"""
        for sym in ["rb", "hc", "i", "j", "jm"]:
            df = load_symbol_data(sym)
            self.assertFalse(df.empty, f"{sym} should not be empty")
            self.assertEqual(df["date"].min(), "2016-01-05")
            self.assertGreaterEqual(df["date"].max(), "2026-09-21")
            self.assertFalse(df.isnull().any().any(), f"{sym} should have 0 nulls")
            
            # 必须包含规范字段
            expected_cols = [
                "date", "open", "high", "low", "close", "volume",
                "open_interest", "settlement", "contract_code", "delivery_month",
                "symbol", "variety_name", "exchange", "multiplier",
                "default_margin_rate", "full_symbol", "contract_type"
            ]
            for col in expected_cols:
                self.assertIn(col, df.columns, f"{col} missing in {sym}")

    def test_continuous_main(self):
        """测试连续主力合约序列 (>=2,604 交易日无断点)"""
        for sym in ["rb", "hc", "i", "j", "jm"]:
            main_df = get_continuous_main(sym)
            self.assertGreaterEqual(len(main_df), 2604, f"{sym} main contract count mismatch")
            self.assertTrue((main_df["close"] > 0).all())
            self.assertTrue((main_df["open_interest"] > 0).all())
            self.assertTrue((main_df["volume"] > 0).all())

    def test_market_aggregate_and_sedimentation_capital(self):
        """测试综合指数与全市场沉淀资金计算"""
        for sym in ["rb", "hc", "i", "j", "jm"]:
            main_df = get_continuous_main(sym)
            agg_df = get_market_aggregate(sym)
            self.assertEqual(len(agg_df), len(main_df))
            self.assertIn("sedimentation_capital_cny_yi", agg_df.columns)
            # 沉淀资金必须为正且在合理产业量级 (10亿 ~ 200亿元)
            latest_cap = agg_df.iloc[-1]["sedimentation_capital_cny_yi"]
            self.assertGreater(latest_cap, 5.0, f"{sym} sedimentation capital too small")
            self.assertLess(latest_cap, 500.0, f"{sym} sedimentation capital too large")

    def test_forward_curve_slice(self):
        """测试远期期限结构曲线截面提取"""
        trade_date = "2024-03-15"
        curve = get_forward_curve("rb", trade_date)
        self.assertGreater(len(curve), 5, "Curve should have multiple contracts")
        self.assertEqual(curve["date"].iloc[0], trade_date)
        # 确认按合约代码升序排序
        codes = curve["contract_code"].tolist()
        self.assertEqual(codes, sorted(codes))
        # 2405 应为当日主力合约
        row_2405 = curve[curve["contract_code"] == "2405"]
        self.assertFalse(row_2405.empty)
        self.assertGreater(row_2405.iloc[0]["open_interest"], 1_000_000)

    def test_calendar_spreads(self):
        """测试跨期价差与年化展期收益率"""
        spread_df = get_active_calendar_spread("rb")
        self.assertFalse(spread_df.empty)
        self.assertIn("spread", spread_df.columns)
        self.assertIn("roll_yield_annual", spread_df.columns)
        
        # 抽样检验某一交易日价差等于近月收盘减远月收盘
        sample = spread_df.iloc[-1]
        expected_spread = sample["price_near"] - sample["price_far"]
        self.assertAlmostEqual(sample["spread"], expected_spread, places=2)


if __name__ == "__main__":
    unittest.main()
