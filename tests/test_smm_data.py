import os
import json
import unittest
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SMM_DIR = os.path.join(PROJECT_ROOT, "数据/原始/smm")

class TestSMMData(unittest.TestCase):
    def test_smm_files_exist(self):
        self.assertTrue(os.path.exists(os.path.join(SMM_DIR, "smm_export_manufacturing.parquet")), "Parquet file missing!")
        self.assertTrue(os.path.exists(os.path.join(SMM_DIR, "smm_export_manufacturing.csv")), "CSV file missing!")
        self.assertTrue(os.path.exists(os.path.join(SMM_DIR, "smm_raw_receipts.json")), "Raw receipts missing!")
        self.assertTrue(os.path.exists(os.path.join(SMM_DIR, "smm_indicators_metadata.json")), "Metadata missing!")
        self.assertTrue(os.path.exists(os.path.join(SMM_DIR, "smm_call_audit.json")), "Audit log missing!")

    def test_smm_data_integrity(self):
        parquet_path = os.path.join(SMM_DIR, "smm_export_manufacturing.parquet")
        df = pd.read_parquet(parquet_path)
        
        # 1. 行数断言 (预期 1600+ 行)
        self.assertGreaterEqual(len(df), 1600, f"Expected >= 1600 rows, got {len(df)}")
        
        # 2. 20 项指标全部存在
        unique_ids = set(df["indicator_id"].unique())
        self.assertEqual(len(unique_ids), 20, f"Expected 20 unique indicators, got {len(unique_ids)}")
        
        # 3. 关键指标最新值校验
        fob_tj = df[df["indicator_id"] == "s22804474"].sort_values("date").iloc[-1]
        self.assertGreater(fob_tj["value"], 400, "FOB Tianjin should be realistic USD/tonne")
        
        shipment_32 = df[df["indicator_id"] == "a10148222"].sort_values("date").iloc[-1]
        self.assertGreater(shipment_32["value"], 200, "32 ports weekly shipment should be realistic")
        
        auto_demand = df[df["indicator_id"] == "a12885073"].sort_values("date").iloc[-1]
        self.assertTrue(2.0 <= auto_demand["value"] <= 10.0, "Auto monthly steel demand should be in range 2-10 million mt")

    def test_smm_quota_audit(self):
        audit_path = os.path.join(SMM_DIR, "smm_call_audit.json")
        with open(audit_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertIsInstance(data, dict)
        self.assertTrue(all(v <= 25 for v in data.values()), "Daily calls must never exceed 25")

if __name__ == "__main__":
    unittest.main()
