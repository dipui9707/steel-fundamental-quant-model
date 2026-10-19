#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/populate_2025q3_status_judgments.py
功能:
  将 2025 Q3 两个关键转折节点 (2025-07-04, 2025-07-25) 的多维度市场状态判断追加至 数据/状态/状态判断.csv。
"""

import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATUS_FILE = BASE_DIR / "数据" / "状态" / "状态判断.csv"

def main():
    new_rows = [
        # ---------------------------------------------------------
        # 节点一: 2025-07-04 破三触底、极低库存与估值修复启动前夕
        # ---------------------------------------------------------
        {
            "snapshot_id": "SNAP_20250704",
            "as_of": "2025-07-04T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Macro_Regime",
            "state_name": "Macro_Regime",
            "state_value": "Neutral_Policy_Expectation",
            "evidence_ids": "OBS_WIND_F06_20250704",
            "assessment_method": "三季度宏观稳增长政策预期与重大改革窗口评估",
            "limitations": "政策落地节奏受财政发债节奏影响，短期以预期博弈为主"
        },
        {
            "snapshot_id": "SNAP_20250704",
            "as_of": "2025-07-04T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Fundamental",
            "state_name": "Fundamental_State",
            "state_value": "Bullish_Low_Inventory",
            "evidence_ids": "OBS_WIND_R01_20250704;OBS_WIND_R02_20250704;OBS_WIND_R03_20250704;FEAT_FBS_SCORE_20250704",
            "assessment_method": "历史极低库存水平检验与供需边际评估",
            "limitations": "虽处夏季高温淡季，但螺纹总库存仅545万吨创多年极低水平，去库至极限形成强支撑"
        },
        {
            "snapshot_id": "SNAP_20250704",
            "as_of": "2025-07-04T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Spot",
            "state_name": "Spot_State",
            "state_value": "Strong_Backwardation",
            "evidence_ids": "OBS_WIND_S01_20250704;FEAT_BASIS_RB_20250704",
            "assessment_method": "现货升水幅度与基差安全边际测算",
            "limitations": "现货报价坚挺在3170，期货贴水近100元/吨，现货端贸易商拒绝低价抛售"
        },
        {
            "snapshot_id": "SNAP_20250704",
            "as_of": "2025-07-04T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Sentiment",
            "state_name": "Sentiment_State",
            "state_value": "Short_Covering",
            "evidence_ids": "OBS_WIND_F07_20250704;OBS_WIND_F08_20250704",
            "assessment_method": "盘面持仓异动与资金回补动向",
            "limitations": "空头主力开始大规模获利止盈平仓，多头低位增仓推升量能"
        },
        {
            "snapshot_id": "SNAP_20250704",
            "as_of": "2025-07-04T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Divergence",
            "state_name": "Divergence_State",
            "state_value": "Bullish_Oversold_Divergence",
            "evidence_ids": "FEAT_FBS_SCORE_20250704;OBS_WIND_F06_20250704",
            "assessment_method": "价格过度破位下跌至3000整数关口与极低库存及高升水背离",
            "limitations": "超跌反弹驱动强劲，但需警惕高铁水压制下反弹高度受限"
        },
        {
            "snapshot_id": "SNAP_20250704",
            "as_of": "2025-07-04T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "System",
            "state_name": "Model_Confidence",
            "state_value": "High",
            "evidence_ids": "FEAT_FBS_W_20250704;FEAT_BASIS_RB_20250704",
            "assessment_method": "极低库存+现货高升水双重硬约束支撑模型高置信度",
            "limitations": "阶段性反弹目标关注 3300~3350 成本压力区间"
        },

        # ---------------------------------------------------------
        # 节点二: 2025-07-25 暴涨至 3356 见顶与预期透支顶背离
        # ---------------------------------------------------------
        {
            "snapshot_id": "SNAP_20250725",
            "as_of": "2025-07-25T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Macro_Regime",
            "state_name": "Macro_Regime",
            "state_value": "Neutral_Wait_and_See",
            "evidence_ids": "OBS_WIND_F06_20250725",
            "assessment_method": "政策利好充分定价后进入落地观察期",
            "limitations": "市场强预期被盘面在短期内完全提前计入，缺乏新政策催化剂"
        },
        {
            "snapshot_id": "SNAP_20250725",
            "as_of": "2025-07-25T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Fundamental",
            "state_name": "Fundamental_State",
            "state_value": "Bearish_Accumulation",
            "evidence_ids": "OBS_WIND_TOTAL01_20250725;OBS_WIND_R03_20250724;FEAT_FBS_SCORE_20250725",
            "assessment_method": "高炉铁水持续高位与淡季累库检验",
            "limitations": "247家铁水维持在240万吨以上，高温多雨阻碍施工，螺纹社库出现连续累库拐点"
        },
        {
            "snapshot_id": "SNAP_20250725",
            "as_of": "2025-07-25T18:00:00+08:00",
            "module": "Spot",
            "state_name": "Spot_State",
            "state_value": "Weakening_Contango",
            "evidence_ids": "OBS_WIND_S01_20250725;FEAT_BASIS_RB_20250725",
            "assessment_method": "现货跟涨乏力与盘面转为升水监控",
            "limitations": "现货报价3330无法承接高价，盘面3356反超现货转为升水，基差转负透支估值"
        },
        {
            "snapshot_id": "SNAP_20250725",
            "as_of": "2025-07-25T18:00:00+08:00",
            "module": "Sentiment",
            "state_name": "Sentiment_State",
            "state_value": "Bullish_Euphoria_Exhaustion",
            "evidence_ids": "OBS_WIND_F07_20250725;OBS_WIND_F08_20250725",
            "assessment_method": "投机多头情绪达极值与套保盘进场打压",
            "limitations": "连续冲高后多头成交天量放量滞涨，钢厂在盘面大幅挂单套保锁定利润"
        },
        {
            "snapshot_id": "SNAP_20250725",
            "as_of": "2025-07-25T18:00:00+08:00",
            "module": "Divergence",
            "state_name": "Divergence_State",
            "state_value": "Bearish_Overbought_Divergence",
            "evidence_ids": "FEAT_FBS_SCORE_20250725;OBS_WIND_F06_20250725",
            "assessment_method": "期货盘面大幅升水冲高与实物累库和淡季现实形成隐性顶背离",
            "limitations": "预期透支后反弹衰竭，面临向基本面均值回归的回调压力"
        },
        {
            "snapshot_id": "SNAP_20250725",
            "as_of": "2025-07-25T18:00:00+08:00",
            "module": "System",
            "state_name": "Model_Confidence",
            "state_value": "Medium_High",
            "evidence_ids": "FEAT_FBS_W_20250725;FEAT_BASIS_RATE_RB_20250725",
            "assessment_method": "基差转负与淡季高铁水累库双重顶背离预警",
            "limitations": "回调下探目标关注 3050~3100 元/吨区间"
        }
    ]

    cols = [
        "snapshot_id", "as_of", "model_version", "module", "state_name",
        "state_value", "evidence_ids", "assessment_method", "limitations"
    ]
    df_old = pd.read_csv(STATUS_FILE)
    df_combined = pd.concat([df_old, pd.DataFrame(new_rows)[cols]], ignore_index=True)
    df_combined = df_combined.drop_duplicates(subset=["snapshot_id", "module", "state_name"], keep="last")
    df_combined.to_csv(STATUS_FILE, index=False, encoding="utf-8-sig")
    print(f"[+] 数据/状态/状态判断.csv 追加成功: 现有总计 {len(df_combined)} 条 (本次新增 {len(new_rows)} 条)")

if __name__ == "__main__":
    main()
