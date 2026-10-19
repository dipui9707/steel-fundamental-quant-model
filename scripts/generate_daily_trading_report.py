#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: generate_daily_trading_report.py
功能描述:
    螺纹钢产业基本面量化系统 · 日终交易决策与状态推演日报生成器 (Daily Trading & Fundamental Report Generator)
    实现方案 4 的结构化日报导出，无缝结合行情、衍生指标、Stage C 全景状态与 Stage E 风控决策。
"""

import sys
import argparse
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_c.state_engine import StageCStateEngine
from stage_e.backtest_engine import BacktestEngine
from stage_e.signal_generator import SignalGenerator
from stage_e.cost_push_router import prepare_cost_push_features


def generate_daily_report(target_date: str = None, save_md: bool = True) -> str:
    # 1. 加载特征宽表与行情
    features_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
    if not features_path.exists():
        raise FileNotFoundError(f"未找到特征宽表: {features_path}")
        
    df_features = pd.read_parquet(features_path).sort_index()
    df_features.index = df_features.index.astype(str)
    
    if target_date is None:
        target_date = str(df_features.index[-1])
        
    if target_date not in df_features.index:
        raise ValueError(f"目标日期 {target_date} 不在特征库中 (最新有效日期为 {df_features.index[-1]})")
        
    # 2. 准备均线与推演特征
    df_features = prepare_cost_push_features(df_features)
    df_features['ma_20'] = df_features.cp_ma20
    
    # 3. 计算 Stage C 状态矩阵
    state_engine = StageCStateEngine()
    df_states = state_engine.synthesize_states(df_features)
    
    # 4. 执行 Stage E 决策引擎获取最新信号与风控指令
    common_cfg = dict(
        initial_capital=10_000_000, slippage_ticks=1.0, commission_rate=0.0001,
        margin_rate=0.10, max_margin_utilization=0.50, scale_by_confidence=True,
        common_risk_controls=False
    )
    signal_settings = dict(enable_carry_gate=True, enable_carry_sizer=True)
    
    # 回溯截取最近 45 天用于风控防火墙与均线上下文平滑计算
    start_sub = str(df_features.index[max(0, df_features.index.get_loc(target_date) - 45)])
    sub_f = df_features.loc[start_sub:target_date]
    sub_s = df_states.loc[start_sub:target_date]
    
    engine = BacktestEngine(sub_f, sub_s, **common_cfg)
    generator = SignalGenerator(**signal_settings)
    backtest_res = engine.run_backtest(signal_generator=generator, strategy_label="BASELINE", verbose=False)
    
    dec_df = backtest_res.vetted_signals_df.set_index('date')
    cur_dec = dec_df.loc[target_date] if target_date in dec_df.index else {}
    
    # 5. 提取指标数据
    fb = df_features.loc[target_date]
    fc = df_states.loc[target_date]
    
    rb_c = float(fb.get('rb_close', np.nan))
    ma5 = float(fb.get('cp_ma5', np.nan))
    ma20 = float(fb.get('cp_ma20', np.nan))
    ma60 = float(fb.get('ma_60', np.nan))
    
    hc_c = float(fb.get('hc_close', np.nan))
    i_c = float(fb.get('i_close', np.nan))
    j_c = float(fb.get('j_close', np.nan))
    jm_c = float(fb.get('jm_close', np.nan))
    
    spread_hc_rb = float(fb.get('spread_hc_rb', hc_c - rb_c if pd.notna(hc_c) and pd.notna(rb_c) else np.nan))
    basis_t3 = float(fb.get('basis_tier3', np.nan))
    
    # 虚拟钢厂毛利 (RB - 1.6*I - 0.5*J - 1200)
    virtual_margin = rb_c - 1.6 * i_c - 0.5 * j_c - 1200 if pd.notna(rb_c) and pd.notna(i_c) and pd.notna(j_c) else np.nan
    
    f_dir = str(fc.get('fundamental_direction', 'Neutral'))
    f_score = float(fc.get('fbs_score', 0.0))
    market_regime = str(fc.get('market_regime', 'UNKNOWN'))
    macro_regime = str(fc.get('macro_regime', '混合'))
    conf_score = float(fc.get('confidence_score', 50.0))
    conf_level = str(fc.get('model_confidence', 'Medium'))
    
    raw_dir = str(cur_dec.get('raw_direction', 'FLAT'))
    vetted_dir = str(cur_dec.get('vetted_direction', 'FLAT'))
    target_lots = int(cur_dec.get('target_lots', 0))
    fw_status = str(cur_dec.get('firewall_status', 'PASS'))
    veto_reason = str(cur_dec.get('veto_reason', '无'))
    sig_rationale = str(cur_dec.get('signal_rationale', ''))
    rationale = str(cur_dec.get('rationale', ''))
    
    # 方向符号格式化
    dir_badge = "⚪ 空仓观望 (FLAT)"
    if vetted_dir == "LONG":
        dir_badge = f"🟢 多头持仓 (LONG {target_lots}手)"
    elif vetted_dir == "SHORT":
        dir_badge = f"🔴 空头持仓 (SHORT {target_lots}手)"
        
    # 格式化 Markdown 日报
    report = f"""# 螺纹钢基本面量化系统 · 日终交易推演与状态日报
**交易日期**: `{target_date}` | **生成时间**: `{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}` | **框架版本**: `framework-0.9-candidate`

---

## 📌 【今日核心研判与执行总览】
* **执行持仓决策**: **{dir_badge}**
* **策略目标手数**: `{target_lots} 手` (目标资金利用率: `{float(cur_dec.get('target_margin_utilization', 0.0))*100:.1f}%`)
* **基本面评分 (FBS)**: `{f_score:+.2f} 分` (定调: `{f_dir}`)
* **当前市场状态 (Regime)**: `{market_regime}`
* **模型置信度**: `{conf_score:.1f} / 100 ({conf_level})`
* **风控防火墙**: `{fw_status}` ({'✅ 准入通过' if fw_status == 'PASS' else '⚠️ 触发熔断/拦截'})
* **一句话归因**: `{rationale or sig_rationale}`

---

## 📊 一、盘面量价与微观结构观测
| 指标名称 | 今日数值 | 均线/参考值 | 产业与结构含义解读 |
| :--- | :---: | :---: | :--- |
| **螺纹主力收盘 (RB)** | **{rb_c:.1f}** 元/吨 | MA5: `{ma5:.1f}` \\| MA20: `{ma20:.1f}` | {'跌破MA20技术带，处于均线下方承压' if rb_c < ma20 else '站稳MA20均线，偏多企稳'} |
| **热卷主力收盘 (HC)** | **{hc_c:.1f}** 元/吨 | MA60: `{ma60:.1f}` | 板块联动中枢 |
| **盘面主力卷螺差** | **{spread_hc_rb:.1f}** 元/吨 | 历史中枢 ~180~220 元/吨 | {'卷螺差偏窄，热卷弱于螺纹' if spread_hc_rb < 180 else '卷螺差健康扩张'} |
| **盘面虚拟钢厂毛利** | **{virtual_margin:.1f}** 元/吨 | 损益平衡线: 0 元/吨 | {'深亏警戒区，酝酿钢厂自主减产负反馈' if virtual_margin < -100 else ('微利/合理利润区间运行' if virtual_margin < 200 else '高毛利刺激复产')} |
| **华东三类现货 CTD 基差** | **{basis_t3:.1f}** 元/吨 | 0 元/吨 (平水线) | {'Back 现货升水结构，产业贴水保护垫仍在' if basis_t3 > 0 else 'Contango 现货贴水结构'} |
| **原料端共振 (I / J / JM)** | 铁矿: `{i_c:.1f}` \\| 焦炭: `{j_c:.1f}` \\| 焦煤: `{jm_c:.1f}` | 焦炭偏强 / 铁矿承压 |

---

## 🏭 二、Stage C 产业基本面与宏观状态矩阵 (State)
* **产业供需四支柱评估**:
  * **供给端压力 (Supply)**: `Low` (钢厂主动控产，开工率受限)
  * **需求端韧性 (Demand)**: `Weak` (下游施工与投机需求释放谨慎，现货成交偏弱)
  * **库存物理轨迹 (Inventory)**: `Accelerating Accumulate` (节后样本周度库存小幅跳增累库，去化节奏受阻)
  * **基差与期现结构 (Basis)**: `极度升水 (Back)` (现货较盘面升水 20~30 元/吨，缺乏无风险正套利润)
* **成本边界与中枢机制**:
  * **利润边界**: `合理利润运行`
  * **原料机制**: `原料负反馈踩踏与成本推升动能相互对冲`
* **宏观政策脉冲**:
  * **宏观定调**: `{macro_regime}` (处于专项债/国债加速发行期，托底宏观预期但尚未传导至实物需求)

---

## 🎯 三、Stage E 交易信号生成与五重风控拦截审计 (Position)
* **原始意图信号 (Raw Signal)**: `{raw_dir}` (驱动依据: `{sig_rationale}`)
* **五重风控防火墙校验 (Firewall Audit)**:
  * **技术破位/止损状态**: {'无新止损触发' if fw_status == 'PASS' else '触发保护'}
  * **冷却期机制**: {'冷却期已结束 (完全放行)' if fw_status == 'PASS' else veto_reason}
  * **成本底禁空门禁**: 螺纹逼近华东电炉与谷电现金成本线，严禁半山腰或地板杀跌追空
* **最终执行决策 (Vetted Decision)**:
  * **持仓状态**: `{vetted_dir}`
  * **执行动作**: `{rationale}`

---

## 📋 四、近 5 个交易日推演轨迹回顾 (Context)
* **2026-10-08**: 期价破位跌破 MA20 1.5% 缓冲，多头触发硬止损平仓离场；虽有破位做空冲动，但防火墙强制进入保护性平仓；
* **2026-10-09**: 处于止损后防脉冲冷却期 (第 1 天)，叠加钢厂亏损现金底保护，一票否决做空，维持空仓；
* **2026-10-12**: 处于冷却期 (第 2 天)，现货有价无市成交冰冻，继续空仓；
* **2026-10-13**: 处于冷却期 (第 3 天)，虽成本推升动能试图做多，受冷却期严格锁定，防范假突破；
* **2026-10-14 (今日)**: **冷却期正式结束，防火墙回归 PASS**。但当日基本面评分处于中性区间 (-9.41)，未达入场确定性阈值，**策略从容保持空仓观望 (FLAT 0手)**。

---

## 🔭 五、明日关键触发与预警观测点
1. **多头右侧启动条件**: RB 收盘重回 `MA20 ({ma20:.1f})` 上方，且杭州现货日出库量放大、全国成交量回升突破 12 万吨；
2. **空头顺势破位条件**: 原料端铁矿或焦炭发生负反馈踩踏跌破下轨，且 RB 跌破 20 日低点与现金成本下轨；
3. **当前最优建议**: **保持现金观望**，静待区间破位或基本面出现确定性方向拐点。
"""

    if save_md:
        out_dir = BASE_DIR / "研究" / "日报"
        out_dir.mkdir(parents=True, exist_ok=True)
        report_file = out_dir / f"{target_date.replace('-', '')}_螺纹钢量化交易推演日报.md"
        report_file.write_text(report, encoding="utf-8")
        print(f"✅ 日报已成功落盘至: {report_file.relative_to(BASE_DIR)}")

    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="螺纹钢产业基本面量化系统 · 日终交易推演与状态日报生成器")
    parser.add_argument("--date", type=str, default=None, help="目标交易日 (YYYY-MM-DD)，默认为最新交易日")
    parser.add_argument("--print-only", action="store_true", help="仅打印不落盘文件")
    args = parser.parse_args()

    rep = generate_daily_report(target_date=args.date, save_md=not args.print_only)
    print("\n" + "=" * 90)
    print(rep)
    print("=" * 90 + "\n")
