#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/populate_status_judgments.py
功能:
  将 2024 Q1 两个关键节点 (2024-01-19, 2024-03-08) 的多维度市场状态判断落盘至 数据/状态/状态判断.csv。
"""

import pandas as pd
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATUS_FILE = BASE_DIR / "数据" / "状态" / "状态判断.csv"

def main():
    rows = [
        # ---------------------------------------------------------
        # 节点一: 2024-01-19 节前高估值弱现实隐性背离
        # ---------------------------------------------------------
        {
            "snapshot_id": "SNAP_20240119",
            "as_of": "2024-01-19T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Macro_Regime",
            "state_name": "Macro_Regime",
            "state_value": "Neutral_Weak",
            "evidence_ids": "OBS_FUT_RB_20240119_CLOSE",
            "assessment_method": "宏观信用与节前政策窗口评估",
            "limitations": "岁末年初宏观处于信贷投放早春期，实物工作量尚未接受开工检验"
        },
        {
            "snapshot_id": "SNAP_20240119",
            "as_of": "2024-01-19T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Fundamental",
            "state_name": "Fundamental_State",
            "state_value": "Bearish",
            "evidence_ids": "OBS_PROD_R01_20240119;OBS_INV_R02_20240119;OBS_INV_R03_20240119;FEAT_FBS_SCORE_20240119",
            "assessment_method": "周度表需测算与冬储累库斜率检验",
            "limitations": "冬季季节性停工导致表需失真，冬储真实意愿需通过贸易商拿货节奏侧面佐证"
        },
        {
            "snapshot_id": "SNAP_20240119",
            "as_of": "2024-01-19T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Spot",
            "state_name": "Spot_State",
            "state_value": "Weak",
            "evidence_ids": "OBS_SPOT_RB_20240119;FEAT_BASIS_RB_20240119",
            "assessment_method": "现货冬储挂牌价与成交量跟踪",
            "limitations": "华东华北现货冬储出货缓慢，贸易商被动拿货为主"
        },
        {
            "snapshot_id": "SNAP_20240119",
            "as_of": "2024-01-19T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Sentiment",
            "state_name": "Sentiment_State",
            "state_value": "Bullish_Speculation",
            "evidence_ids": "OBS_FUT_RB_20240119_CLOSE;OBS_FUT_RB_20240119_OI",
            "assessment_method": "期货盘面估值溢价与主力资金持仓博弈",
            "limitations": "多头资金利用春季开工预期维持盘面高估值"
        },
        {
            "snapshot_id": "SNAP_20240119",
            "as_of": "2024-01-19T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Divergence",
            "state_name": "Divergence_State",
            "state_value": "Bearish_Hidden_Divergence",
            "evidence_ids": "FEAT_FBS_SCORE_20240119;OBS_FUT_RB_20240119_CLOSE",
            "assessment_method": "FBS得分持续负向走低与期货维持3900+高位背离",
            "limitations": "隐性背离在淡季预期主导阶段可能持续数周，需等待节后实物开工证伪"
        },
        {
            "snapshot_id": "SNAP_20240119",
            "as_of": "2024-01-19T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "System",
            "state_name": "Model_Confidence",
            "state_value": "Medium",
            "evidence_ids": "FEAT_FBS_W_20240119",
            "assessment_method": "淡季权重系数 W=0.6 调节置信度",
            "limitations": "冬储淡季信噪比一般，严禁左侧激进逆势摸顶加仓"
        },

        # ---------------------------------------------------------
        # 节点二: 2024-03-08 节后旺季不旺负反馈加速前夕
        # ---------------------------------------------------------
        {
            "snapshot_id": "SNAP_20240308",
            "as_of": "2024-03-08T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Macro_Regime",
            "state_name": "Macro_Regime",
            "state_value": "Bearish",
            "evidence_ids": "OBS_FUT_RB_20240308_CLOSE",
            "assessment_method": "两会定调与财政化债落地执行评估",
            "limitations": "化债约束下地方基建停缓建项目增多，地产销售持续探底"
        },
        {
            "snapshot_id": "SNAP_20240308",
            "as_of": "2024-03-08T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Fundamental",
            "state_name": "Fundamental_State",
            "state_value": "Extreme_Bearish",
            "evidence_ids": "OBS_PROD_R01_20240308;OBS_INV_R02_20240308;OBS_INV_R03_20240308;FEAT_DAPP_RB_20240308;FEAT_FBS_SCORE_20240308",
            "assessment_method": "旺季开工表需检验与库存拐点判定",
            "limitations": "表需仅200万吨断崖式低于往年同期，厂库社库双爆仓，库存去化完全受阻"
        },
        {
            "snapshot_id": "SNAP_20240308",
            "as_of": "2024-03-08T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Spot",
            "state_name": "Spot_State",
            "state_value": "Severe_Distress",
            "evidence_ids": "OBS_SPOT_RB_20240308;FEAT_BASIS_RB_20240308;OBS_PROFIT_C03_20240308",
            "assessment_method": "现货流动性枯竭与踩踏甩货监控",
            "limitations": "华东现货日均成交不足13万吨，现货贴水加剧，钢厂亏损突破200元/吨"
        },
        {
            "snapshot_id": "SNAP_20240308",
            "as_of": "2024-03-08T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Sentiment",
            "state_name": "Sentiment_State",
            "state_value": "Short_Panic",
            "evidence_ids": "OBS_FUT_RB_20240308_OI;OBS_FUT_I_20240308_CLOSE",
            "assessment_method": "主力资金净空单扩张与多头踩踏斩仓",
            "limitations": "市场强预期彻底粉碎，资金由成材向铁矿双焦发动全产业链负反馈做空"
        },
        {
            "snapshot_id": "SNAP_20240308",
            "as_of": "2024-03-08T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "Divergence",
            "state_name": "Divergence_State",
            "state_value": "Bearish_Convergence",
            "evidence_ids": "FEAT_FBS_SCORE_20240308;OBS_FUT_RB_20240308_CLOSE;OBS_FUT_I_20240308_CLOSE",
            "assessment_method": "基本面极度恶化与盘面向下破位由背离走向全面共振杀跌",
            "limitations": "共振下跌速度极快，负反馈主跌浪具有踩踏与流动性冲击特征"
        },
        {
            "snapshot_id": "SNAP_20240308",
            "as_of": "2024-03-08T18:00:00+08:00",
            "model_version": "V0.2",
            "module": "System",
            "state_name": "Model_Confidence",
            "state_value": "High",
            "evidence_ids": "FEAT_FBS_W_20240308",
            "assessment_method": "旺季验证期权重拉升至 W=0.9~1.0，证据链完全闭环",
            "limitations": "注意极端超跌后的钢厂联合减产自律与政策干预风险"
        }
    ]

    cols = [
        "snapshot_id", "as_of", "model_version", "module", "state_name",
        "state_value", "evidence_ids", "assessment_method", "limitations"
    ]
    df_status = pd.DataFrame(rows)[cols]
    df_status.to_csv(STATUS_FILE, index=False, encoding="utf-8-sig")
    print(f"[+] 数据/状态/状态判断.csv 落盘成功: {len(df_status)} 条状态记录")

if __name__ == "__main__":
    main()
