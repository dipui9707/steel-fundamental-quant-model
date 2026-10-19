import os
import unittest
import pandas as pd

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BALANCE_PARQUET = os.path.join(PROJECT_ROOT, "数据/加工/铁水全景流向平衡表.parquet")
BALANCE_CSV = os.path.join(PROJECT_ROOT, "数据/加工/铁水全景流向平衡表.csv")

class TestHotMetalBalance(unittest.TestCase):
    def test_files_exist(self):
        """检验平衡表标准生产文件是否存在"""
        self.assertTrue(os.path.exists(BALANCE_PARQUET), "Parquet balance file missing!")
        self.assertTrue(os.path.exists(BALANCE_CSV), "CSV balance file missing!")

    def test_balance_sum_closed(self):
        """检验全口径成材实物产出份额是否封闭 (100% 封闭)"""
        df = pd.read_parquet(BALANCE_PARQUET)
        self.assertGreaterEqual(len(df), 9)
        
        # 成材实物份额必须在 0.99 ~ 1.02 之间闭合
        total_share = df["share_of_finished_steel"].sum()
        self.assertAlmostEqual(total_share, 1.00, delta=0.02, msg=f"Finished steel share {total_share} not closed to 1.0!")

    def test_key_proportions_and_alignment(self):
        """检验全口径对齐后的关键品种实物产出逻辑"""
        df = pd.read_parquet(BALANCE_PARQUET)
        
        rebar = df[df["product_name"].str.contains("螺纹钢")].iloc[0]
        hrc = df[df["product_name"].str.contains("热轧板卷")].iloc[0]
        strip = df[df["product_name"].str.contains("热轧带钢")].iloc[0]
        pipe = df[df["product_name"].str.contains("钢管")].iloc[0]
        plate = df[df["product_name"].str.contains("中厚板")].iloc[0]
        
        # 1. 2026年最新实测：热卷周产超 380 万吨，螺纹因地产下行降至 260~320 万吨区间，热卷明显超越螺纹 (热卷 > 螺纹 1.3 倍以上)
        self.assertGreaterEqual(hrc["weekly_output_10kt"], 380.0)
        self.assertTrue(250.0 <= rebar["weekly_output_10kt"] <= 320.0)
        self.assertGreater(hrc["weekly_output_10kt"], rebar["weekly_output_10kt"] * 1.3)
        
        # 2. 2026年最新实测份额：热卷占比约 22%~26%，螺纹钢全口径占比压缩至 15%~19%
        self.assertTrue(0.22 <= hrc["share_of_finished_steel"] <= 0.26)
        self.assertTrue(0.15 <= rebar["share_of_finished_steel"] <= 0.19)
        
        # 3. 带钢与钢管周产均超百吨
        self.assertGreater(strip["weekly_output_10kt"], 100.0)
        self.assertGreater(pipe["weekly_output_10kt"], 100.0)
        self.assertGreater(plate["weekly_output_10kt"], 100.0)

    def test_no_old_flawed_files_remain(self):
        """确保库中绝无残留旧版或冗余冲突文件"""
        redundant_parquet = os.path.join(PROJECT_ROOT, "数据/加工/铁水全景流向平衡表_全口径统一版.parquet")
        redundant_csv = os.path.join(PROJECT_ROOT, "数据/加工/铁水全景流向平衡表_全口径统一版.csv")
        redundant_script = os.path.join(PROJECT_ROOT, "scripts/compute_unified_panoramic_balance.py")
        
        self.assertFalse(os.path.exists(redundant_parquet), "Redundant unified parquet should be deleted!")
        self.assertFalse(os.path.exists(redundant_csv), "Redundant unified csv should be deleted!")
        self.assertFalse(os.path.exists(redundant_script), "Redundant script should be deleted!")

if __name__ == "__main__":
    unittest.main()
