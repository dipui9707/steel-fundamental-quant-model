#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
单元测试套件: tests/test_futures_ranking.py
任务编号: T-LOCAL-001 验收测试
测试范围:
1. 榜外席位保留 NaN，截断区间计算与对称交集准确性;
2. 真实动态时间戳与交易日强校验;
3. 离线仿真 (Mock) 物理隔离性测试;
4. 合约解析超时拒绝盲猜 2501.
"""

import os
import sys
import unittest
import numpy as np
import pandas as pd
from pathlib import Path
from unittest.mock import MagicMock
from zoneinfo import ZoneInfo

# 添加项目根目录至 sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import scripts.fetch_futures_ranking as ffr

class TestFuturesRankingPipeline(unittest.TestCase):

    def setUp(self):
        self.target_date = "2026-09-18"
        self.shanghai_tz = ZoneInfo("Asia/Shanghai")

    def test_01_nan_preservation_and_bounds_calculation(self):
        """
        测试点 1：榜外席位严禁填零，保留 NaN，并精确计算有界数学截断区间
        """
        # 模拟包含 5 家会员的非对称榜单
        # Broker A: 双向在榜 (Long=5000, Short=3000) -> Exact Net = 2000
        # Broker B: 仅多头在榜 (Long=4000, Short榜外) -> Net = NaN, Range = [4000 - S_20, 4000]
        # Broker C: 仅空头在榜 (Long榜外, Short=3500) -> Net = NaN, Range = [-3500, L_20 - 3500]
        # 设 S_20 = 1000, L_20 = 1500
        mock_df_long = pd.DataFrame([
            {"datetime": self.target_date, "symbol": "SHFE.rb2501", "exchange_id": "SHFE", "instrument_id": "rb2501",
             "broker": "BrokerA", "long_oi": 5000, "long_change": 100, "long_ranking": 1},
            {"datetime": self.target_date, "symbol": "SHFE.rb2501", "exchange_id": "SHFE", "instrument_id": "rb2501",
             "broker": "BrokerB", "long_oi": 4000, "long_change": 200, "long_ranking": 2},
            {"datetime": self.target_date, "symbol": "SHFE.rb2501", "exchange_id": "SHFE", "instrument_id": "rb2501",
             "broker": "BrokerD", "long_oi": 1500, "long_change": 10, "long_ranking": 20}, # L_20门槛
        ])
        mock_df_short = pd.DataFrame([
            {"datetime": self.target_date, "symbol": "SHFE.rb2501", "exchange_id": "SHFE", "instrument_id": "rb2501",
             "broker": "BrokerA", "short_oi": 3000, "short_change": -50, "short_ranking": 1},
            {"datetime": self.target_date, "symbol": "SHFE.rb2501", "exchange_id": "SHFE", "instrument_id": "rb2501",
             "broker": "BrokerC", "short_oi": 3500, "short_change": 30, "short_ranking": 2},
            {"datetime": self.target_date, "symbol": "SHFE.rb2501", "exchange_id": "SHFE", "instrument_id": "rb2501",
             "broker": "BrokerE", "short_oi": 1000, "short_change": 5, "short_ranking": 20}, # S_20门槛
        ])

        mock_api = MagicMock()
        def mock_query(contract, ranking_type, days=1, start_dt=None):
            if ranking_type == "LONG":
                return mock_df_long
            else:
                return mock_df_short
        mock_api.query_symbol_ranking.side_effect = mock_query

        df_merged, actual_date = ffr.fetch_and_merge_rankings(mock_api, "SHFE.rb2501", target_date=self.target_date)

        self.assertEqual(actual_date, self.target_date)
        
        # 检验 Broker A (双侧在榜)
        row_a = df_merged[df_merged["broker"] == "BrokerA"].iloc[0]
        self.assertTrue(row_a["is_exact_net"])
        self.assertEqual(row_a["net_oi"], 2000)
        self.assertEqual(row_a["net_oi_lower_bound"], 2000)
        self.assertEqual(row_a["net_oi_upper_bound"], 2000)
        self.assertEqual(row_a["net_change"], 150) # 100 - (-50)

        # 检验 Broker B (仅多头在榜，空头榜外)
        row_b = df_merged[df_merged["broker"] == "BrokerB"].iloc[0]
        self.assertFalse(row_b["is_exact_net"])
        self.assertTrue(np.isnan(row_b["net_oi"]), "单侧在榜 net_oi 必须为 NaN，严禁填零")
        self.assertTrue(np.isnan(row_b["net_change"]), "单侧在榜 net_change 必须为 NaN")
        # 空头门槛 S_20 为 1000，故净持仓下界为 4000 - 1000 = 3000，上界为 4000
        self.assertEqual(row_b["net_oi_lower_bound"], 3000)
        self.assertEqual(row_b["net_oi_upper_bound"], 4000)

        # 检验 Broker C (仅空头在榜，多头榜外)
        row_c = df_merged[df_merged["broker"] == "BrokerC"].iloc[0]
        self.assertFalse(row_c["is_exact_net"])
        self.assertTrue(np.isnan(row_c["net_oi"]), "单侧在榜 net_oi 必须为 NaN，严禁填零")
        # 多头门槛 L_20 为 1500，故净持仓下界为 -3500，上界为 1500 - 3500 = -2000
        self.assertEqual(row_c["net_oi_lower_bound"], -3500)
        self.assertEqual(row_c["net_oi_upper_bound"], -2000)

    def test_02_b_rank_and_common_intersection_aggregation(self):
        """
        测试点 2：集中度差额 B_rank 与对称交集 (Common Overlap) 聚合计算
        """
        df_merged = pd.DataFrame([
            {"broker": "A", "long_oi": 10000, "short_oi": 8000, "net_oi": 2000, "net_change": 200, "is_exact_net": True},
            {"broker": "B", "long_oi": 12000, "short_oi": np.nan, "net_oi": np.nan, "net_change": np.nan, "is_exact_net": False},
            {"broker": "C", "long_oi": np.nan, "short_oi": 7000, "net_oi": np.nan, "net_change": np.nan, "is_exact_net": False},
            {"broker": "D", "long_oi": 6000, "short_oi": 5000, "net_oi": 1000, "net_change": -100, "is_exact_net": True},
        ])
        contract_info = {
            "variety": "RB",
            "contract": "SHFE.rb2501",
            "open_interest": 100000.0 # 单边总持仓
        }
        broker_classes = {
            "categories": {
                "industrial": {"brokers": ["A"]},
                "speculative": {"brokers": ["D"]}
            }
        }

        m = ffr.compute_metrics_for_contract(df_merged, contract_info, broker_classes, self.target_date)

        # 验证总持仓合计
        # Long Sum 20 = 10000 + 12000 + 6000 = 28000 (CR_Long = 28%)
        # Short Sum 20 = 8000 + 7000 + 5000 = 20000 (CR_Short = 20%)
        # B_rank = 28% - 20% = +8.0%
        self.assertAlmostEqual(m["cr_long_20"], 28.0)
        self.assertAlmostEqual(m["cr_short_20"], 20.0)
        self.assertAlmostEqual(m["b_rank"], 8.0)

        # 验证对称交集：仅 A 和 D (2 家)
        self.assertEqual(m["common_count"], 2)
        # common_net_pos = 2000 (A) + 1000 (D) = 3000
        self.assertEqual(m["common_net_pos"], 3000)
        # common_net_change = 200 + (-100) = 100
        self.assertEqual(m["common_net_change"], 100)

        # 席位分群：A (产业套保) 净变动 200; D (量化投机) 净变动 -100
        self.assertEqual(m["ind_net_change"], 200)
        self.assertEqual(m["ind_covered_count"], 1)
        self.assertEqual(m["spec_net_change"], -100)
        self.assertEqual(m["spec_covered_count"], 1)

    def test_03_timestamp_and_date_validation(self):
        """
        测试点 3：动态时间戳非 18:30 硬编码，且拒绝交易日错配数据
        """
        # 验证当前时间戳生成器
        iso_str = ffr.get_now_shanghai_iso()
        self.assertIn("+08:00", iso_str, "必须包含上海时区偏移量 +08:00")
        self.assertNotIn("18:30:00", iso_str.split("T")[1][:8], "时间戳不得硬编码 18:30:00")

        # 模拟返回日期不匹配的异常情况 (返回 2026-09-17，但请求 2026-09-18)
        mock_df_l = pd.DataFrame([
            {"datetime": "2026-09-17", "symbol": "SHFE.rb2501", "exchange_id": "SHFE", "instrument_id": "rb2501",
             "broker": "A", "long_oi": 100, "long_change": 0, "long_ranking": 1}
        ])
        mock_df_s = pd.DataFrame([
            {"datetime": "2026-09-17", "symbol": "SHFE.rb2501", "exchange_id": "SHFE", "instrument_id": "rb2501",
             "broker": "A", "short_oi": 100, "short_change": 0, "short_ranking": 1}
        ])

        mock_api = MagicMock()
        def mock_query(contract, ranking_type, days=1, start_dt=None):
            return mock_df_l if ranking_type == "LONG" else mock_df_s
        mock_api.query_symbol_ranking.side_effect = mock_query

        with self.assertRaises(RuntimeError) as ctx:
            ffr.fetch_and_merge_rankings(mock_api, "SHFE.rb2501", target_date="2026-09-18")
        self.assertIn("日期错配拒绝", str(ctx.exception))

    def test_04_mock_data_physical_isolation(self):
        """
        测试点 4：离线仿真数据 (Mock) 严格物理隔离，绝不污染正式事实库
        """
        raw_path, metrics = ffr.generate_mock_data("2026-09-18", ["RB"])
        
        # 1. 验证落盘路径在 研究/mock_data/ 下
        self.assertTrue(str(raw_path).startswith(str(ffr.MOCK_RAW_DIR)), f"路径应在 {ffr.MOCK_RAW_DIR} 下，实际为: {raw_path}")
        self.assertTrue(ffr.MOCK_PROCESSED_FILE.exists(), "加工特征 mock 文件必须存在")

        # 2. 验证正式生产目录绝对未被污染
        live_raw_files = list(ffr.LIVE_RAW_DIR.glob("*20260918*")) if ffr.LIVE_RAW_DIR.exists() else []
        self.assertEqual(len(live_raw_files), 0, "正式生产目录 [数据/原始/] 严禁写入 mock 数据！")

        # 3. 验证元数据标识为 SYNTHETIC 与 MOCK
        df_raw = pd.read_csv(raw_path)
        self.assertTrue((df_raw["information_set_mode"] == "SYNTHETIC").all())
        self.assertTrue((df_raw["quality_flag"] == "MOCK").all())
        self.assertTrue((df_raw["source"] == "SYNTHETIC_FIXTURE").all())

        # 4. 验证指标文件内容
        df_proc = pd.read_csv(ffr.MOCK_PROCESSED_FILE)
        self.assertTrue((df_proc["quality_flag"] == "MOCK").all())

    def test_05_resolve_underlying_timeout_no_guessing(self):
        """
        测试点 5：合约解析超时时明确报错，严禁猜测回退 2501
        """
        mock_api = MagicMock()
        mock_quote = MagicMock()
        mock_quote.underlying_symbol = "" # 始终无法解析
        mock_api.get_quote.return_value = mock_quote

        # 传入极短超时 0.05 秒
        with self.assertRaises(RuntimeError) as ctx:
            ffr.resolve_underlying_symbols(mock_api, ["RB"], explicit_contracts=None, timeout=0.05)
        
        err_msg = str(ctx.exception)
        self.assertIn("拒绝猜测实约", err_msg)
        self.assertIn("严禁主观硬编码兜底猜测合约", err_msg)

        # 显式指定合约时，应成功绕过解析
        mock_quote.datetime = "2026-09-18 15:00:00.000"
        mock_quote.open_interest = 1500000
        mock_quote.settlement = 3400.0
        resolved = ffr.resolve_underlying_symbols(mock_api, ["RB"], explicit_contracts=["SHFE.rb2501"], timeout=0.05)
        self.assertEqual(resolved["RB"]["contract"], "SHFE.rb2501")
        self.assertEqual(resolved["RB"]["resolution_method"], "EXPLICIT_SPECIFIED")

if __name__ == "__main__":
    unittest.main(verbosity=2)
