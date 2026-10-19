#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/record_2025q3_simulation_workbook.py
功能:
  1. 向 outputs/阶段A_框架初版/A07_预测日志.xlsx 追加 2025-07-04 与 2025-07-25 预测快照 (Row 8, Row 9)
  2. 向 outputs/阶段A_框架初版/A08_错误归因.xlsx 追加对应的行情兑现复盘与归因 (Row 8, Row 9)
  3. 向 outputs/阶段A_框架初版/A09_研究假设库.xlsx 更新 ARCH-H-010, ARCH-H-003, ARCH-H-001, H-001 的验证记录
"""

import openpyxl
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
A07_PATH = BASE_DIR / "outputs" / "阶段A_框架初版" / "A07_预测日志.xlsx"
A08_PATH = BASE_DIR / "outputs" / "阶段A_框架初版" / "A08_错误归因.xlsx"
A09_PATH = BASE_DIR / "outputs" / "阶段A_框架初版" / "A09_研究假设库.xlsx"

def update_a07():
    print("[+] 更新 A07_预测日志.xlsx (写入 Row 8, Row 9) ...")
    wb = openpyxl.load_workbook(A07_PATH)
    ws = wb['预测日志']

    # 预测快照 3: 2025-07-04
    pred_3 = [
        "PRED_20250704_01",
        datetime(2025, 7, 4, 18, 0, 0),
        "V0.2",
        "研究/案例/2025Q3_低估值强反弹与旺季预期博弈推演报告.md",
        "Neutral_Policy_Expectation",
        "Bullish_Low_Inventory",
        0.25,
        "Strong_Backwardation",
        "Short_Covering",
        "Super_Backwardation",
        "Bullish_Oversold_Divergence",
        "High",
        "Medium",
        "Active",
        "螺纹破三后极度超跌，全国总库存仅545万吨创多年历史极低，现货深升水近100元/吨构成强安全边际；空头集中平仓与三季度宏观稳增长政策预期共振，驱动强劲估值修复反弹",
        "极端低库存硬支撑与超跌贴水修复",
        "强劲估值修复反弹",
        10,
        25,
        "高温暴雨导致现货需求严重冰封；钢厂无节制复产导致库存拐点提前暴力累积",
        "螺纹主力合约跌破2950元/吨或社库单周爆发式累库超30万吨",
        "OBS_WIND_R02_20250704;OBS_WIND_R03_20250704;FEAT_BASIS_RB_20250704;FEAT_FBS_SCORE_20250704",
        "螺纹突破3300或盘面转为升水",
        None
    ]

    # 预测快照 4: 2025-07-25
    pred_4 = [
        "PRED_20250725_01",
        datetime(2025, 7, 25, 18, 0, 0),
        "V0.2",
        "研究/案例/2025Q3_低估值强反弹与旺季预期博弈推演报告.md",
        "Neutral_Wait_and_See",
        "Bearish_Accumulation",
        -0.28,
        "Weakening_Contango",
        "Bullish_Euphoria_Exhaustion",
        "Contango_Top",
        "Bearish_Overbought_Divergence",
        "Medium_High",
        "High",
        "Active",
        "螺纹自3003狂飙至3356(+11.8%)，铁矿飙至823(+16.2%)，短期预期完全透支；但247家铁水维持在240万吨以上高位，淡季高温施工受阻，现货跟涨乏力转为贴水，社库出现被动累积，反弹动能衰竭，面临见顶回落",
        "强预期透支与淡季高铁水累库顶背离",
        "震荡见顶回落",
        15,
        35,
        "出台超预期全国性粗钢行政平控压减限产政策；秋季旺季需求爆发式提前释放",
        "螺纹主力有效站稳3420元/吨上方且铁水单周大幅减产超8万吨",
        "OBS_WIND_TOTAL01_20250725;OBS_WIND_R03_20250724;FEAT_BASIS_RB_20250725;FEAT_FBS_SCORE_20250725",
        "螺纹回落考验3100或钢厂主动大幅减产",
        None
    ]

    for col_idx, val in enumerate(pred_3, start=1):
        ws.cell(row=8, column=col_idx, value=val)
    for col_idx, val in enumerate(pred_4, start=1):
        ws.cell(row=9, column=col_idx, value=val)

    wb.save(A07_PATH)
    print("    -> A07 成功写入 2025 Q3 预测快照 (Row 8, Row 9)")

def update_a08():
    print("[+] 更新 A08_错误归因.xlsx (写入 Row 8, Row 9) ...")
    wb = openpyxl.load_workbook(A08_PATH)
    ws = wb['复盘记录']

    # 复盘 3 (针对 PRED_20250704_01)
    rev_3 = [
        "REV_20250725_01",
        "PRED_20250704_01",
        datetime(2025, 7, 25, 18, 0, 0),
        datetime(2025, 7, 4, 0, 0, 0),
        datetime(2025, 7, 25, 0, 0, 0),
        "数据/原始/01_期货行情.csv;数据/原始/06_库存.csv;数据/加工/加工指标.csv",
        "螺纹活跃合约自3079大涨至3356(+9.0%)，铁矿自734飙升至823(+12.1%)，现货跟进至3330，反弹目标完全兑现",
        "完全正确",
        "未交易(模拟多头估值修复大丰收)",
        "无逻辑错误",
        "无",
        "价格跌破3000触发行业极端亏损停炉硬约束，叠加多年历史最低库存（545万吨）与近100元现货升水，空头平仓踩踏与政策预期共振驱动修复",
        "无",
        "将历史极低库存分位数与现货深度升水纳入底部正反馈反弹触发条件",
        "ARCH-H-010;ARCH-H-003",
        None,
        "V0.2",
        "已结项"
    ]

    # 复盘 4 (针对 PRED_20250725_01)
    rev_4 = [
        "REV_20250930_01",
        "PRED_20250725_01",
        datetime(2025, 9, 30, 18, 0, 0),
        datetime(2025, 7, 25, 0, 0, 0),
        datetime(2025, 9, 30, 0, 0, 0),
        "数据/原始/01_期货行情.csv;数据/原始/03_总供应.csv;数据/原始/06_库存.csv",
        "螺纹在3356见顶，随后在8-9月淡季向旺季转换不及预期中震荡回落至3072(-8.5%)，铁矿从823回落至780，社库累积至443万吨，逻辑完全兑现",
        "完全正确",
        "未交易(模拟高位减多翻空回落兑现盈利)",
        "无逻辑错误",
        "无",
        "高铁水(242万吨)支撑供应扩张，而夏季酷暑淡季需求承接乏力导致社库连续累库，盘面转为升水后引发套保抛压，预期落空后价格向实物均值回归",
        "无",
        "将基差由正转负与高铁水被动累库作为反弹衰竭见顶的核心卖点哨兵",
        "ARCH-H-001;H-001",
        None,
        "V0.2",
        "已结项"
    ]

    for col_idx, val in enumerate(rev_3, start=1):
        ws.cell(row=8, column=col_idx, value=val)
    for col_idx, val in enumerate(rev_4, start=1):
        ws.cell(row=9, column=col_idx, value=val)

    wb.save(A08_PATH)
    print("    -> A08 成功写入 2025 Q3 复盘记录 (Row 8, Row 9)")

def update_a09():
    print("[+] 更新 A09_研究假设库.xlsx ...")
    wb = openpyxl.load_workbook(A09_PATH)
    ws = wb['假设登记']

    # 查找并更新
    # Row 6: H-001
    # Row 11: ARCH-H-003
    # Row 9: ARCH-H-001
    # Row 18: ARCH-H-010
    updates = {
        "H-001": {
            "col_h": "2025Q3 (2025-07-01 至 2025-09-30)",
            "col_i": "部分验证通过",
            "col_q": "2025Q3热卷对螺纹现货溢价维持在120~180元/吨，具备切换能力的综合钢厂在7-8月微调铁水向热卷倾斜，螺纹周产自221降至206万吨，反映了相对利润对排产的温和引导。"
        },
        "ARCH-H-001": {
            "col_h": "2024Q1 与 2025Q3",
            "col_i": "历史验证通过",
            "col_q": "2025年7月下旬盘面因投机博弈狂飙至3356，但独立物理FBS因淡季表需走弱与高铁水累库早于价格翻负（-0.28），成功预警了超买顶背离，避免追高风险。"
        },
        "ARCH-H-003": {
            "col_h": "2024Q1 与 2025Q3",
            "col_i": "历史验证通过",
            "col_q": "2024Q1验证深度亏损下的负反馈向下踩踏；2025Q3验证了价格破3000跌破现金成本线后的行业自发挺价抵抗与极低库存强支撑，双向成本反馈区间成立。"
        },
        "ARCH-H-010": {
            "col_h": "2025Q3 (2025-07-01 至 2025-09-30)",
            "col_i": "历史验证通过",
            "col_q": "2025年7月初螺纹跌破3000、现货大幅升水100元/吨的极端低估瞬时偏离，在3周内以首达概率迅速向成本与现货均值收敛修复，验证了首达收敛分布特性。"
        }
    }

    for r in range(6, 25):
        h_id = ws.cell(row=r, column=1).value
        if h_id in updates:
            u = updates[h_id]
            ws.cell(row=r, column=8, value=u["col_h"])
            ws.cell(row=r, column=9, value=u["col_i"])
            ws.cell(row=r, column=17, value=u["col_q"])
            print(f"    -> 更新假设 {h_id}: {u['col_i']}")

    wb.save(A09_PATH)
    print("    -> A09 假设库验证状态更新成功！")

def main():
    update_a07()
    update_a08()
    update_a09()
    print("=" * 80)
    print("三大正式量化账本 (A07, A08, A09) 2025 Q3 记录更新落盘成功！")
    print("=" * 80)

if __name__ == "__main__":
    main()
