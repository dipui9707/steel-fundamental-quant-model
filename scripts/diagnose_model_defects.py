#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/diagnose_model_defects.py
功能: 纯数据盲测下模型有效性与真实缺陷全景诊断
职责:
  1. 加载阶段 B 连续特征宽表、阶段 C 全景状态矩阵与阶段 D 实证标签 (2018-2026 全量 2,074 交易日)；
  2. 按照 7 大典型历史宏观/产业情景切片开展压力测试；
  3. 逐个切片剖析模型的真实优势区 (Sweet Spots) 与真实盲区/缺陷 (Blind Spots & Failure Modes)；
  4. 重点解剖 2024-0924 暴涨前夕纯数据模型的真实被动反应与亏损暴露；
  5. 输出学术级《模型真实缺陷与失效场景全景诊断报告.md》。
"""

import sys
from pathlib import Path
import pandas as pd
import numpy as np
import time

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))


def run_defect_diagnosis():
    print("=" * 80)
    print("🔬 启动【钢材产业基本面量化系统】纯数据盲测模型有效性与真实缺陷诊断...")
    print("=" * 80)

    # 1. 加载全量数据资产
    feat_p = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
    state_p = BASE_DIR / "数据" / "状态" / "阶段C_全景状态矩阵.parquet"
    ret_p = BASE_DIR / "数据" / "状态" / "阶段D_收益与交易研究特征矩阵.parquet"

    features_df = pd.read_parquet(feat_p)
    states_df = pd.read_parquet(state_p)
    research_df = pd.read_parquet(ret_p)

    report_lines = []
    report_lines.append("# 模型真实缺陷与失效场景全景诊断报告 (纯数据盲测版)\n")
    report_lines.append(f"**生成时间**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())} (Asia/Shanghai)  ")
    report_lines.append("**核心原则**: **坚决杜绝后视镜叙事与事后诸葛亮补丁，100% 呈现机器在面对未知世界时的真实反应**  ")
    report_lines.append("**评估样本**: 2018-03-09 至 2026-09-21（全历史 2,074 个交易日连续时序）\n")
    report_lines.append("---\n")

    # --------------------------------------------------------------------------
    # 2. 七大典型历史行情情景切片分析
    # --------------------------------------------------------------------------
    regimes = [
        {
            "id": "REGIME_01",
            "name": "2018 供给侧去产能高毛利与环保限产期",
            "start": "2018-03-09",
            "end": "2018-12-31",
            "desc": "地条钢出清后高炉高开工、长流程吨钢毛利破 1000 元，供需两旺",
        },
        {
            "id": "REGIME_02",
            "name": "2019 巴西淡水河谷矿难供给大冲击期",
            "start": "2019-01-25",
            "end": "2019-07-31",
            "desc": "外生矿难导致铁矿石暴涨一倍，成材被动跟涨，利润被严重吞噬",
        },
        {
            "id": "REGIME_03",
            "name": "2020 疫情黑天鹅断崖与疫后超级复苏期",
            "start": "2020-01-23",
            "end": "2020-12-31",
            "desc": "节后首周跌停开盘，随后全球流动性大放水驱动大宗超级牛市启动",
        },
        {
            "id": "REGIME_04",
            "name": "2021 能耗双控限产顶与动力煤调控踩踏期",
            "start": "2021-05-01",
            "end": "2021-11-30",
            "desc": "螺纹创 6,200 元历史极值后，发改委雷霆调控煤价，全产业链崩跌",
        },
        {
            "id": "REGIME_05",
            "name": "2022-2023 地产下行长周期与微利震荡期",
            "start": "2022-06-01",
            "end": "2023-12-31",
            "desc": "房地产新开工腰斩，钢厂陷入长期微利甚至亏损，低波震荡为主",
        },
        {
            "id": "REGIME_06",
            "name": "2024Q1 成材需求落空与原料负反馈踩踏期",
            "start": "2024-01-02",
            "end": "2024-04-15",
            "desc": "冬储预期证伪，周表需断崖，长流程毛利跌破-200元，负反馈主跌",
        },
        {
            "id": "REGIME_07",
            "name": "2024-0924 宏观一揽子增量政策超级大转向期",
            "start": "2024-09-20",
            "end": "2024-10-31",
            "desc": "基本面极弱背景下，央行/政治局突发重磅刺激，盘面短短一周暴涨600点",
        },
    ]

    report_lines.append("## 一、七大历史典型情景纯盲测综合体检表\n")
    report_lines.append("| 编号 | 历史情景区间 | 交易日 | 期间螺纹主力涨跌 | 期间状态分布特征 | 优势度 (甜区) | 脆弱度 (缺陷) | 机器真实评价 |")
    report_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    for r in regimes:
        sub_feat = features_df.loc[r["start"]:r["end"]]
        sub_state = states_df.loc[r["start"]:r["end"]]
        if sub_feat.empty:
            continue

        p_start = sub_feat["rb_close"].iloc[0]
        p_end = sub_feat["rb_close"].iloc[-1]
        p_ret = (p_end - p_start) / p_start * 100.0

        n_days = len(sub_feat)
        fund_dist = sub_state["fundamental_direction"].value_counts(normalize=True).to_dict()
        top_fund = sub_state["fundamental_direction"].mode().iloc[0]
        top_macro = sub_state["macro_regime"].mode().iloc[0]

        sweet = "未验证"
        blind = "待核对成交与预测快照"
        verdict = f"区间价格变化{p_ret:+.1f}%，主导状态{top_fund}；状态分布不能证明获利或避险"

        report_lines.append(
            f"| `{r['id']}` | {r['name']} | {n_days}d | {p_ret:+.1f}% | 供需多: {fund_dist.get('Bullish',0)*100:.0f}%, 空: {fund_dist.get('Bearish',0)*100:.0f}% | {sweet} | {blind} | {verdict} |"
        )

    # --------------------------------------------------------------------------
    # 3. 重点深度解剖：2024-0924 宏观大转向时纯数据模型的真实缺陷
    # --------------------------------------------------------------------------
    report_lines.append("\n---\n")
    report_lines.append("## 二、核心缺陷深度解剖：2024 年 924 暴涨前夕机器的真实被动表现\n")
    report_lines.append("为了彻底打消“后见之明”的疑虑，我们调出 **2024 年 9 月 20 日至 10 月 10 日** 纯数据驱动下的每日真实输出：\n")
    report_lines.append("| 交易日期 | 螺纹收盘价 | 真实单日涨跌 | 纯数据宏观状态 | 基本面方向 | 现货确认 | 置信度评级 | 机器真实判断与暴露的缺陷 |")
    report_lines.append("| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |")

    sample_924 = states_df.loc["2024-09-20":"2024-10-10"].copy()
    sample_feat = features_df.loc["2024-09-20":"2024-10-10"].copy()

    for dt, row in sample_924.iterrows():
        dt_str = str(dt)[:10]
        c_p = sample_feat.loc[dt, "rb_close"]
        r_1d = sample_feat.loc[dt, "rb_ret_1d"] * 100.0 if "rb_ret_1d" in sample_feat.columns else 0.0

        m_regime = row["macro_regime"]
        f_dir = row["fundamental_direction"]
        s_conf = row["spot_confirmation"]
        conf = row["model_confidence"]

        critique = f"当日输出：{f_dir}，现货{s_conf}，置信评级{conf}；成交与损失须查独立实验流水"

        report_lines.append(f"| `{dt_str}` | {c_p:.0f} 元 | {r_1d:+.2f}% | {m_regime} | {f_dir} | {s_conf} | {conf} | {critique} |")

    report_lines.append("\n### 924 真实缺陷总结：\n")
    report_lines.append("1. **滞后性不可避免**：在政策出台的第 1~2 天（9-24 与 9-25），持有反向头寸的策略可能亏损，具体损失取决于当时仓位与成交约束！因为实物供需（库存、表需）都是周度滞后指标，根本不可能跑赢突发政策；\n")
    report_lines.append("2. **合规应对之道不是事后改代码，而是依靠风控止损**：\n")
    report_lines.append("   - 价格突破均线通道上限时触发价格硬止损；\n")
    report_lines.append("   - 波动率骤增触发模型置信度降级（由 High 降为 Low），停止信号输出；\n")
    report_lines.append("   - **我们绝不能为了好看，在代码里写 `if date == '2024-09-24': 做多`！坦然承受这次滞后是量化研究诚实性的唯一底线。**\n")

    # --------------------------------------------------------------------------
    # 4. 模型的真实优势区与缺陷清单
    # --------------------------------------------------------------------------
    report_lines.append("\n---\n")
    report_lines.append("## 三、模型核心能力边界清单 (优势区 vs 盲区)\n")
    report_lines.append("本报告只提供状态与价格的观察记录。机制兑现、交易损益与执行风控需分别检验；不从情景名称推断胜率。\n")
    report_lines.append("数据发布时点、历史修订、突发事件、涨跌停与成交约束仍需核实；当前资料不足以宣称工业级或实盘准入。\n")

    report_path = BASE_DIR / "研究" / "测试报告" / "模型真实缺陷与失效场景全景诊断报告.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(report_lines) + "\n")

    print(f"\n[+] 诊断报告已生成: {report_path}")
    print("=" * 80)


if __name__ == "__main__":
    run_defect_diagnosis()
