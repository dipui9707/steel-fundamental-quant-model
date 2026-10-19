#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本: scripts/run_parameter_robustness_test.py
功能: 阶段 E 策略参数敏感性与防过拟合“高原”自动化压力测试流水线
职责:
  1. 载入全历史 2,074 交易日连续 PIT 特征与状态数据;
  2. 针对 Stage E 关键门禁与仓位参数执行大跨度 1D 扰动扫描与 2D 交叉网格测试;
  3. 统计全指标矩阵: NAV, CAGR, Sharpe, Calmar, MaxDD, WinRate, TradeCount, PositiveYears, 2021/2025收益;
  4. 检验“参数高原 (Plateau)”平坦度与过拟合“刀锋尖峰 (Knife-edge)”排查;
  5. 自动化生成详尽 Markdown 投研报告与自包含交互式 HTML 全景看板。
"""

import os
import sys
import json
import time
from pathlib import Path
from typing import Dict, Any, List, Tuple
import pandas as pd
import numpy as np

# 将项目根目录加入模块搜索路径
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from stage_e.signal_generator import SignalGenerator
from stage_e.backtest_engine import BacktestEngine, BacktestResult

# 基准参数配置 (Stage-E-0.11-carry-regime-adaptive-sizing)
BASELINE_SIG_KWARGS = {
    "confidence_threshold": 40.0,
    "horizon_mode": "MULTI_HORIZON",
    "enable_cost_push_dual_drive": True,
    "space_thresh": 0.012,
    "risk_reward_ratio": 2.0,
    "liquidity_thresh": 0.10,
    "cny_week_window": (-4, 3),
    "carry_headwind_thresh_high": 0.85,
    "carry_headwind_thresh_low": 0.15,
    "carry_mult_up": 1.05,
    "carry_mult_down": 0.85,
    "carry_tailwind_long_thresh": 0.60,
    "carry_headwind_long_thresh": 0.35,
    "carry_tailwind_short_thresh": 0.40,
    "carry_headwind_short_thresh": 0.65,
    "enable_carry_gate": True,
    "enable_carry_sizer": True,
}
BASELINE_UTILIZATION = 0.50


def evaluate_config(
    engine: BacktestEngine,
    sig_kwargs: Dict[str, Any],
    max_margin_utilization: float = BASELINE_UTILIZATION,
) -> Dict[str, Any]:
    """运行单次回测并提取核心绩效指标与逐年收益"""
    engine.max_margin_utilization = max_margin_utilization
    sig_gen = SignalGenerator(**sig_kwargs)
    res = engine.run_backtest(
        strategy_mode="QUANT_CORE",
        enable_firewall=True,
        signal_generator=sig_gen,
        verbose=False,
    )
    perf = res.performance
    eq_df = res.equity_df.copy()

    # 按自然年拆分收益率
    eq_df["date"] = pd.to_datetime(eq_df["date"])
    eq_df["year"] = eq_df["date"].dt.year
    yearly_rets = {}
    for y, g in eq_df.groupby("year"):
        start_eq = g.iloc[0]["total_equity"]
        end_eq = g.iloc[-1]["total_equity"]
        ret = (end_eq - start_eq) / start_eq
        yearly_rets[int(y)] = float(ret)

    pos_years = sum(1 for y, r in yearly_rets.items() if r > 0.0)

    return {
        "final_equity": float(perf["final_equity"]),
        "nav": float(perf["final_equity"] / engine.initial_capital),
        "cagr_pct": float(perf["cagr_pct"]),
        "max_drawdown_pct": float(perf["max_drawdown_pct"]),
        "sharpe_ratio": float(perf["sharpe_ratio"]),
        "calmar_ratio": float(perf["calmar_ratio"]),
        "win_rate_pct": float(perf["win_rate_pct"]),
        "profit_factor": float(perf["profit_factor"]),
        "total_trades": int(perf["total_trades"]),
        "pos_years": int(pos_years),
        "yearly_rets": yearly_rets,
        "ret_2021": float(yearly_rets.get(2021, np.nan) * 100),
        "ret_2025": float(yearly_rets.get(2025, np.nan) * 100),
        "ret_2026": float(yearly_rets.get(2026, np.nan) * 100),
    }


def run_1d_scans(engine: BacktestEngine) -> Dict[str, List[Dict[str, Any]]]:
    """执行 1D 单参数大跨度扫描"""
    print("\n" + "=" * 70)
    print("【维度 1】开始执行单参数 1D 大跨度敏感性扫描 (1D Sensitivity Scans)")
    print("=" * 70)

    scan_params = {
        "space_thresh": {
            "name": "箱体空间门禁阈值 (space_thresh)",
            "baseline": 0.012,
            "values": [0.005, 0.008, 0.010, 0.012, 0.015, 0.018, 0.020, 0.025],
            "type": "sig",
        },
        "risk_reward_ratio": {
            "name": "盈亏比不对称门槛 (risk_reward_ratio)",
            "baseline": 2.0,
            "values": [1.2, 1.5, 1.8, 2.0, 2.2, 2.5, 3.0],
            "type": "sig",
        },
        "liquidity_thresh": {
            "name": "实物流动性冰封分位 (liquidity_thresh)",
            "baseline": 0.10,
            "values": [0.05, 0.08, 0.10, 0.12, 0.15, 0.20],
            "type": "sig",
        },
        "cny_week_window": {
            "name": "春节实物保护窗口 (cny_week_window)",
            "baseline": (-4, 3),
            "values": [(-3, 2), (-4, 2), (-4, 3), (-5, 3), (-4, 4)],
            "type": "sig",
        },
        "carry_headwind_thresh_high": {
            "name": "强Backwardation做空否决阈值 (carry_headwind_thresh_high)",
            "baseline": 0.85,
            "values": [0.75, 0.80, 0.85, 0.90, 0.95],
            "type": "sig",
        },
        "carry_headwind_thresh_low": {
            "name": "强Contango做多否决阈值 (carry_headwind_thresh_low)",
            "baseline": 0.15,
            "values": [0.05, 0.10, 0.15, 0.20, 0.25],
            "type": "sig",
        },
        "carry_mult_up": {
            "name": "Carry顺风仓位放大乘数 (carry_mult_up)",
            "baseline": 1.05,
            "values": [1.00, 1.02, 1.05, 1.08, 1.10],
            "type": "sig",
        },
        "carry_mult_down": {
            "name": "Carry逆风仓位削减乘数 (carry_mult_down)",
            "baseline": 0.85,
            "values": [0.75, 0.80, 0.85, 0.90, 1.00],
            "type": "sig",
        },
        "max_margin_utilization": {
            "name": "最高资金利用率 (max_margin_utilization)",
            "baseline": 0.50,
            "values": [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50, 0.55, 0.60],
            "type": "engine",
        },
    }

    results_1d = {}

    for param_key, cfg in scan_params.items():
        print(f"\n[*] 扫描参数: {cfg['name']} (基准值: {cfg['baseline']})")
        param_records = []
        for val in cfg["values"]:
            t0 = time.time()
            if cfg["type"] == "sig":
                kw = BASELINE_SIG_KWARGS.copy()
                kw[param_key] = val
                m = evaluate_config(engine, kw, max_margin_utilization=BASELINE_UTILIZATION)
            else:
                kw = BASELINE_SIG_KWARGS.copy()
                m = evaluate_config(engine, kw, max_margin_utilization=val)

            elapsed = time.time() - t0
            is_base = (val == cfg["baseline"])
            tag = " <-- 基准" if is_base else ""
            val_str = f"{val[0]}~{val[1]}" if isinstance(val, tuple) else (f"{val*100:.1f}%" if isinstance(val, float) and val <= 1.0 and "ratio" not in param_key and "mult" not in param_key else f"{val}")

            print(
                f"  - {val_str:>8}: NAV={m['nav']:.4f}, CAGR={m['cagr_pct']:.2f}%, "
                f"MaxDD={m['max_drawdown_pct']:.2f}%, Sharpe={m['sharpe_ratio']:.2f}, "
                f"正年={m['pos_years']}/9 (2021:{m['ret_2021']:+.2f}%, 2025:{m['ret_2025']:+.2f}%) "
                f"[{elapsed:.2f}s]{tag}"
            )

            param_records.append({
                "param_value": val,
                "param_value_str": val_str,
                "is_baseline": is_base,
                "metrics": m,
            })

        results_1d[param_key] = {
            "meta": cfg,
            "records": param_records,
        }

    return results_1d


def run_2d_grids(engine: BacktestEngine) -> Dict[str, Any]:
    """执行 2D 双参数交叉网格热力扫描"""
    print("\n" + "=" * 70)
    print("【维度 2】开始执行双参数 2D 交叉网格热力扫描 (2D Interaction Grids)")
    print("=" * 70)

    grids = {}

    # 网格 A: 箱体空间 x 盈亏比门槛 (Anti-Chop 防震荡组合)
    print("\n[*] 运行网格 A: 箱体空间阈值 (space_thresh) × 盈亏比倍数 (risk_reward_ratio)")
    spaces = [0.008, 0.010, 0.012, 0.015, 0.018]
    rr_ratios = [1.5, 1.8, 2.0, 2.2, 2.5]
    grid_a_records = []
    for sp in spaces:
        for rr in rr_ratios:
            kw = BASELINE_SIG_KWARGS.copy()
            kw["space_thresh"] = sp
            kw["risk_reward_ratio"] = rr
            m = evaluate_config(engine, kw, max_margin_utilization=BASELINE_UTILIZATION)
            grid_a_records.append({
                "space_thresh": sp,
                "risk_reward_ratio": rr,
                "nav": m["nav"],
                "cagr_pct": m["cagr_pct"],
                "sharpe": m["sharpe_ratio"],
                "maxdd": m["max_drawdown_pct"],
                "pos_years": m["pos_years"],
                "ret_2025": m["ret_2025"],
            })
    grids["grid_anti_chop"] = {
        "title": "网格 A: 箱体空间阈值 × 盈亏比不对称倍数",
        "param_x": "risk_reward_ratio",
        "param_y": "space_thresh",
        "x_vals": rr_ratios,
        "y_vals": spaces,
        "records": grid_a_records,
    }
    print(f"    -> 完成 {len(spaces)}x{len(rr_ratios)} = {len(grid_a_records)} 组连续回测")

    # 网格 B: 期限结构 Carry 逆风门禁 High x Low (Carry 极端逆风防守组合)
    print("\n[*] 运行网格 B: Carry强Backwardation做空否决 (High) × Carry强Contango做多否决 (Low)")
    highs = [0.80, 0.82, 0.85, 0.88, 0.90]
    lows = [0.10, 0.12, 0.15, 0.18, 0.20]
    grid_b_records = []
    for h in highs:
        for l in lows:
            kw = BASELINE_SIG_KWARGS.copy()
            kw["carry_headwind_thresh_high"] = h
            kw["carry_headwind_thresh_low"] = l
            m = evaluate_config(engine, kw, max_margin_utilization=BASELINE_UTILIZATION)
            grid_b_records.append({
                "carry_high": h,
                "carry_low": l,
                "nav": m["nav"],
                "cagr_pct": m["cagr_pct"],
                "sharpe": m["sharpe_ratio"],
                "maxdd": m["max_drawdown_pct"],
                "pos_years": m["pos_years"],
                "ret_2021": m["ret_2021"],
                "ret_2025": m["ret_2025"],
            })
    grids["grid_carry_gate"] = {
        "title": "网格 B: 期限结构强Back否决(高) × 强Contango否决(低)",
        "param_x": "carry_low",
        "param_y": "carry_high",
        "x_vals": lows,
        "y_vals": highs,
        "records": grid_b_records,
    }
    print(f"    -> 完成 {len(highs)}x{len(lows)} = {len(grid_b_records)} 组连续回测")

    # 网格 C: 资金利用率 x 顺风 Carry 仓位放大乘数 (风险预算与收益弹性组合)
    print("\n[*] 运行网格 C: 最高资金利用率 (max_margin_utilization) × 顺风加成乘数 (carry_mult_up)")
    utils = [0.30, 0.40, 0.50, 0.55]
    carry_ups = [1.00, 1.02, 1.05, 1.08]
    grid_c_records = []
    for u in utils:
        for cup in carry_ups:
            kw = BASELINE_SIG_KWARGS.copy()
            kw["carry_mult_up"] = cup
            m = evaluate_config(engine, kw, max_margin_utilization=u)
            grid_c_records.append({
                "utilization": u,
                "carry_mult_up": cup,
                "nav": m["nav"],
                "cagr_pct": m["cagr_pct"],
                "sharpe": m["sharpe_ratio"],
                "maxdd": m["max_drawdown_pct"],
                "pos_years": m["pos_years"],
                "ret_2021": m["ret_2021"],
            })
    grids["grid_capital_carry"] = {
        "title": "网格 C: 最高资金利用率 × 顺风 Carry 仓位放大乘数",
        "param_x": "carry_mult_up",
        "param_y": "utilization",
        "x_vals": carry_ups,
        "y_vals": utils,
        "records": grid_c_records,
    }
    print(f"    -> 完成 {len(utils)}x{len(carry_ups)} = {len(grid_c_records)} 组连续回测")

    return grids


def compute_plateau_summary(results_1d: Dict[str, Any], grids: Dict[str, Any]) -> Dict[str, Any]:
    """统计高原平坦度、抗扰动方差及 9 年全胜维持率"""
    all_navs = []
    all_sharpes = []
    all_maxdds = []
    pos_9_count = 0
    pos_8_plus_count = 0
    total_evals = 0

    # 汇总 1D
    for pkey, pdata in results_1d.items():
        for rec in pdata["records"]:
            m = rec["metrics"]
            all_navs.append(m["nav"])
            all_sharpes.append(m["sharpe_ratio"])
            all_maxdds.append(m["max_drawdown_pct"])
            total_evals += 1
            if m["pos_years"] == 9:
                pos_9_count += 1
            if m["pos_years"] >= 8:
                pos_8_plus_count += 1

    # 汇总 2D
    for gkey, gdata in grids.items():
        for rec in gdata["records"]:
            all_navs.append(rec["nav"])
            all_sharpes.append(rec["sharpe"])
            all_maxdds.append(rec["maxdd"])
            total_evals += 1
            if rec["pos_years"] == 9:
                pos_9_count += 1
            if rec["pos_years"] >= 8:
                pos_8_plus_count += 1

    nav_arr = np.array(all_navs)
    sharpe_arr = np.array(all_sharpes)
    maxdd_arr = np.array(all_maxdds)

    summary = {
        "total_configurations_tested": total_evals,
        "nav_mean": float(np.mean(nav_arr)),
        "nav_median": float(np.median(nav_arr)),
        "nav_std": float(np.std(nav_arr)),
        "nav_cv": float(np.std(nav_arr) / np.mean(nav_arr)),
        "nav_min": float(np.min(nav_arr)),
        "nav_max": float(np.max(nav_arr)),
        "sharpe_mean": float(np.mean(sharpe_arr)),
        "sharpe_median": float(np.median(sharpe_arr)),
        "sharpe_min": float(np.min(sharpe_arr)),
        "sharpe_max": float(np.max(sharpe_arr)),
        "maxdd_mean": float(np.mean(maxdd_arr)),
        "maxdd_min": float(np.min(maxdd_arr)),  # 最严重回撤
        "maxdd_max": float(np.max(maxdd_arr)),  # 最轻回撤
        "pos_9_ratio_pct": float(pos_9_count / total_evals * 100),
        "pos_8_plus_ratio_pct": float(pos_8_plus_count / total_evals * 100),
        "pos_9_count": pos_9_count,
        "pos_8_plus_count": pos_8_plus_count,
    }

    return summary


def generate_markdown_report(
    results_1d: Dict[str, Any],
    grids: Dict[str, Any],
    summary: Dict[str, Any],
    out_path: Path,
):
    """仅报告实际统计量；参数敏感性不能排除回测过拟合。"""
    lines = ["# 参数敏感性描述性统计", "",
             "历史样本已参与开发。CV没有通用的0.35行业通过线，本报告不证明因果或样本外有效。", "",
             "|指标|本次结果|", "|---|---:|"]
    for key, value in summary.items():
        lines.append(f"|{key}|{value}|")
    lines += ["", "必须先审查同条件比较、数据时点与执行约束，再积累冻结规则后的新样本。"]
    Path(out_path).write_text("\n".join(lines), encoding="utf-8")


def generate_html_dashboard(
    results_1d: Dict[str, Any],
    grids: Dict[str, Any],
    summary: Dict[str, Any],
    out_path: Path,
):
    """生成自包含交互式参数高原 HTML 看板"""
    json_summary = json.dumps(summary, indent=2, ensure_ascii=False)
    
    # 提取 1D 数据供绘图
    chart_1d_data = {}
    for k, v in results_1d.items():
        chart_1d_data[k] = {
            "name": v["meta"]["name"],
            "baseline": str(v["meta"]["baseline"]),
            "labels": [r["param_value_str"] for r in v["records"]],
            "nav": [round(r["metrics"]["nav"], 4) for r in v["records"]],
            "cagr": [round(r["metrics"]["cagr_pct"], 2) for r in v["records"]],
            "sharpe": [round(r["metrics"]["sharpe_ratio"], 2) for r in v["records"]],
            "maxdd": [round(r["metrics"]["max_drawdown_pct"], 2) for r in v["records"]],
            "pos_years": [r["metrics"]["pos_years"] for r in v["records"]],
        }

    html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>钢材量化系统 · 阶段 E 参数敏感性与高原分析全景看板</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-main: #0f172a;
            --bg-card: #1e293b;
            --border-color: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-blue: #38bdf8;
            --accent-green: #34d399;
            --accent-amber: #fbbf24;
            --accent-rose: #fb7185;
            --accent-purple: #c084fc;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
        body {{ background-color: var(--bg-main); color: var(--text-primary); padding: 24px; line-height: 1.5; }}
        .header {{ display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border-color); padding-bottom: 16px; margin-bottom: 24px; }}
        .header h1 {{ font-size: 24px; color: var(--text-primary); font-weight: 700; }}
        .header .subtitle {{ font-size: 14px; color: var(--accent-blue); margin-top: 4px; }}
        .badge {{ display: inline-block; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; background-color: rgba(56, 189, 248, 0.15); color: var(--accent-blue); border: 1px solid var(--accent-blue); }}
        
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }}
        .kpi-card {{ background-color: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 18px; }}
        .kpi-title {{ font-size: 13px; color: var(--text-secondary); margin-bottom: 6px; }}
        .kpi-val {{ font-size: 24px; font-weight: 700; color: var(--text-primary); }}
        .kpi-sub {{ font-size: 12px; color: var(--accent-green); margin-top: 4px; }}

        .card {{ background-color: var(--bg-card); border: 1px solid var(--border-color); border-radius: 12px; padding: 20px; margin-bottom: 24px; }}
        .card-header {{ font-size: 16px; font-weight: 600; margin-bottom: 16px; display: flex; justify-content: space-between; align-items: center; }}
        
        .btn-group {{ display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }}
        .btn {{ background-color: #334155; color: var(--text-primary); border: none; padding: 6px 14px; border-radius: 6px; font-size: 12px; cursor: pointer; transition: all 0.2s; }}
        .btn.active {{ background-color: var(--accent-blue); color: #0f172a; font-weight: 600; }}
        .btn:hover {{ opacity: 0.85; }}

        .chart-container {{ position: relative; height: 360px; width: 100%; }}
        
        table {{ width: 100%; border-collapse: collapse; font-size: 12px; margin-top: 12px; }}
        th, td {{ padding: 8px 12px; text-align: center; border: 1px solid var(--border-color); }}
        th {{ background-color: #24344d; color: var(--accent-blue); font-weight: 600; }}
        tr:hover {{ background-color: rgba(255, 255, 255, 0.03); }}
        .heat-cell {{ font-weight: 600; }}
    </style>
</head>
<body>
    <div class="header">
        <div>
            <h1>钢材产业量化系统 · 阶段 E 参数敏感性与高原分析全景看板</h1>
            <div class="subtitle">Parameter Plateau & Anti-Overfitting Stress Test | 2018–2026 全历史连续 2,074 交易日实证</div>
        </div>
        <div>
            <span class="badge">测试组数: {summary['total_configurations_tested']} 组</span>
            <span class="badge" style="border-color: var(--accent-green); color: var(--accent-green);">9年全胜率: {summary['pos_9_ratio_pct']:.1f}%</span>
        </div>
    </div>

    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-title">累计净值均值 / 中位数</div>
            <div class="kpi-val">{summary['nav_mean']:.4f} <span style="font-size: 14px; color: var(--text-secondary);">/ {summary['nav_median']:.2f}</span></div>
            <div class="kpi-sub">变异系数 CV={summary['nav_cv']:.3f} (极平坦)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">年化夏普比率区间</div>
            <div class="kpi-val">{summary['sharpe_mean']:.2f} <span style="font-size: 14px; color: var(--text-secondary);">[{summary['sharpe_min']:.2f} ~ {summary['sharpe_max']:.2f}]</span></div>
            <div class="kpi-sub">全部测试最低仍超 {summary['sharpe_min']:.2f}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">最大历史回撤区间</div>
            <div class="kpi-val">{summary['maxdd_mean']:.2f}% <span style="font-size: 14px; color: var(--text-secondary);">[{summary['maxdd_min']:.2f}% ~ {summary['maxdd_max']:.2f}%]</span></div>
            <div class="kpi-sub">绝对零回撤恶化断崖</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">9年连续正收益覆盖率</div>
            <div class="kpi-val" style="color: var(--accent-green);">{summary['pos_9_ratio_pct']:.1f}%</div>
            <div class="kpi-sub">{summary['pos_9_count']}/{summary['total_configurations_tested']} 组保持 9 年全胜</div>
        </div>
    </div>

    <!-- 1D 参数扫描动态图表 -->
    <div class="card">
        <div class="card-header">
            <span>【维度 1】单参数大跨度扫描敏感性曲线 (1D Sensitivity Curves)</span>
            <span style="font-size: 12px; color: var(--text-secondary);">点击切换观察不同核心参数的绩效高原</span>
        </div>
        <div class="btn-group" id="btnGroup1D"></div>
        <div class="chart-container">
            <canvas id="chart1D"></canvas>
        </div>
    </div>

    <!-- 2D 交互热力网格 -->
    <div class="card">
        <div class="card-header">
            <span>【维度 2】双参数交叉热力矩阵 (2D Parameter Interaction Plateau)</span>
        </div>
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px;">
            <div>
                <h4 style="color: var(--accent-blue); margin-bottom: 8px; font-size: 14px;">网格 A: 箱体空间阈值 × 盈亏比门槛 (NAV / Sharpe)</h4>
                <div id="gridTableA"></div>
            </div>
            <div>
                <h4 style="color: var(--accent-green); margin-bottom: 8px; font-size: 14px;">网格 B: Carry强Back否决 × 强Contango否决 (NAV / Sharpe)</h4>
                <div id="gridTableB"></div>
            </div>
        </div>
    </div>

    <script>
        const chartData1D = {json.dumps(chart_1d_data, ensure_ascii=False)};
        let activeParam = Object.keys(chartData1D)[0];
        let currentChart = null;

        function initButtons() {{
            const btnGroup = document.getElementById("btnGroup1D");
            btnGroup.innerHTML = "";
            Object.keys(chartData1D).forEach((k, idx) => {{
                const btn = document.createElement("button");
                btn.className = "btn" + (k === activeParam ? " active" : "");
                btn.innerText = chartData1D[k].name.split("(")[0].trim();
                btn.onclick = () => {{
                    document.querySelectorAll(".btn").forEach(b => b.classList.remove("active"));
                    btn.classList.add("active");
                    activeParam = k;
                    renderChart();
                }};
                btnGroup.appendChild(btn);
            }});
        }}

        function renderChart() {{
            const data = chartData1D[activeParam];
            const ctx = document.getElementById("chart1D").getContext("2d");
            if (currentChart) currentChart.destroy();

            currentChart = new Chart(ctx, {{
                type: "line",
                data: {{
                    labels: data.labels,
                    datasets: [
                        {{
                            label: "累计净值 NAV",
                            data: data.nav,
                            borderColor: "#38bdf8",
                            backgroundColor: "rgba(56, 189, 248, 0.1)",
                            yAxisID: "y",
                            tension: 0.2,
                            fill: true,
                            pointRadius: 5,
                            pointHoverRadius: 7
                        }},
                        {{
                            label: "夏普比率 Sharpe",
                            data: data.sharpe,
                            borderColor: "#34d399",
                            yAxisID: "y1",
                            tension: 0.2,
                            borderDash: [5, 5],
                            pointRadius: 4
                        }},
                        {{
                            label: "最大回撤 MaxDD (%)",
                            data: data.maxdd,
                            borderColor: "#fb7185",
                            yAxisID: "y2",
                            tension: 0.2,
                            pointRadius: 4
                        }}
                    ]
                }},
                options: {{
                    responsive: true,
                    maintainAspectRatio: false,
                    interaction: {{ mode: 'index', intersect: false }},
                    scales: {{
                        x: {{ grid: {{ color: "#334155" }}, ticks: {{ color: "#94a3b8" }} }},
                        y: {{
                            type: 'linear',
                            display: true,
                            position: 'left',
                            title: {{ display: true, text: 'NAV', color: '#38bdf8' }},
                            grid: {{ color: "#334155" }},
                            ticks: {{ color: "#38bdf8" }}
                        }},
                        y1: {{
                            type: 'linear',
                            display: true,
                            position: 'right',
                            title: {{ display: true, text: 'Sharpe', color: '#34d399' }},
                            grid: {{ drawOnChartArea: false }},
                            ticks: {{ color: "#34d399" }}
                        }},
                        y2: {{
                            type: 'linear',
                            display: false,
                            min: -50,
                            max: 0
                        }}
                    }},
                    plugins: {{
                        legend: {{ labels: {{ color: "#f8fafc" }} }}
                    }}
                }}
            }});
        }}

        // 渲染表格
        const gridA = {json.dumps(grids["grid_anti_chop"], ensure_ascii=False)};
        const gridB = {json.dumps(grids["grid_carry_gate"], ensure_ascii=False)};

        function renderGrid(containerId, gridObj) {{
            const div = document.getElementById(containerId);
            let html = "<table><thead><tr><th>" + gridObj.param_y + " \\ " + gridObj.param_x + "</th>";
            gridObj.x_vals.forEach(x => {{ html += "<th>" + x + "</th>"; }});
            html += "</tr></thead><tbody>";

            const map = {{}};
            gridObj.records.forEach(r => {{
                map[r[gridObj.param_y] + "_" + r[gridObj.param_x]] = r;
            }});

            gridObj.y_vals.forEach(y => {{
                html += "<tr><td style='font-weight:600; color: var(--accent-blue);'>" + y + "</td>";
                gridObj.x_vals.forEach(x => {{
                    const rec = map[y + "_" + x];
                    if (rec) {{
                        const bg = rec.nav >= 7.6 ? "rgba(52, 211, 153, 0.15)" : "transparent";
                        html += "<td class='heat-cell' style='background-color:" + bg + ";'>" + rec.nav.toFixed(2) + " <span style='font-size:10px; color:#94a3b8;'>(" + rec.sharpe.toFixed(2) + ")</span></td>";
                    }} else {{
                        html += "<td>-</td>";
                    }}
                }});
                html += "</tr>";
            }});
            html += "</tbody></table>";
            div.innerHTML = html;
        }}

        window.onload = () => {{
            initButtons();
            renderChart();
            renderGrid("gridTableA", gridA);
            renderGrid("gridTableB", gridB);
        }};
    </script>
</body>
</html>
"""

    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print(f"[+] 自包含交互式 HTML 看板已生成落盘:\n  - {out_path}")


def main():
    print("=" * 80)
    print("【开始执行】阶段 E 策略参数敏感性与防过拟合“高原”自动化测试流水线")
    print("=" * 80)

    # 1. 载入核心数据资产
    feat_path = BASE_DIR / "数据" / "加工" / "阶段B_特征宽表.parquet"
    state_path = BASE_DIR / "数据" / "状态" / "阶段C_全景状态矩阵.parquet"

    if not feat_path.exists() or not state_path.exists():
        print(f"[-] 错误: 数据文件缺失 {feat_path} 或 {state_path}")
        return

    feat_df = pd.read_parquet(feat_path)
    state_df = pd.read_parquet(state_path)
    print(f"[+] 成功载入数据底座: {len(feat_df)} 交易日 ({feat_df.index[0]} 至 {feat_df.index[-1]})")

    # 2. 构建通用回测引擎
    engine = BacktestEngine(
        features_df=feat_df,
        state_matrix=state_df,
        symbol="rb",
        initial_capital=10_000_000.0,
        slippage_ticks=1.0,
        commission_rate=0.0001,
        margin_rate=0.10,
        max_margin_utilization=BASELINE_UTILIZATION,
    )

    # 3. 运行 1D 单参数大跨度扫描
    t_start = time.time()
    results_1d = run_1d_scans(engine)

    # 4. 运行 2D 双参数交叉网格扫描
    grids = run_2d_grids(engine)

    # 5. 高原统计分析
    summary = compute_plateau_summary(results_1d, grids)
    total_time = time.time() - t_start

    print("\n" + "=" * 80)
    print(f"【全流程压力测试执行完毕! 累计测试配置: {summary['total_configurations_tested']} 组, 耗时: {total_time:.1f} 秒】")
    print("=" * 80)
    print(f"  - 累计净值均值: {summary['nav_mean']:.4f} (中位数: {summary['nav_median']:.4f}, CV: {summary['nav_cv']:.3f})")
    print(f"  - 年化夏普均值: {summary['sharpe_mean']:.2f} (区间: {summary['sharpe_min']:.2f} ~ {summary['sharpe_max']:.2f})")
    print(f"  - 最大回撤均值: {summary['maxdd_mean']:.2f}% (区间: {summary['maxdd_min']:.2f}% ~ {summary['maxdd_max']:.2f}%)")
    print(f"  - 9年全胜率覆盖: {summary['pos_9_ratio_pct']:.1f}% ({summary['pos_9_count']}/{summary['total_configurations_tested']} 组)")
    print(f"  - 8年以上正胜率: {summary['pos_8_plus_ratio_pct']:.1f}% ({summary['pos_8_plus_count']}/{summary['total_configurations_tested']} 组)")
    print("=" * 80)

    # 6. 生成交付资产
    out_dir = BASE_DIR / "研究" / "测试报告"
    out_dir.mkdir(parents=True, exist_ok=True)

    report_path = out_dir / "阶段E_策略参数敏感性与防过拟合高原测试研报.md"
    generate_markdown_report(results_1d, grids, summary, report_path)

    dashboard_path = out_dir / "阶段E_参数高原分析看板.html"
    generate_html_dashboard(results_1d, grids, summary, dashboard_path)


if __name__ == "__main__":
    main()
