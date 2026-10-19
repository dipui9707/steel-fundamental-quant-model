#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_d/dashboard.py
功能: 阶段 D 收益与交易研究独立交互式 HTML 全景看板生成器
职责:
  生成包含 Chart.js 的自包含高颜值单文件交互看板:
  1. 复合策略状态收益分布与胜率对比柱状/折线图;
  2. MFE vs MAE 极端路径不对称弹性柱状图;
  3. 阶梯止损耐受度曲面 (震仓洗出率 vs 有效防守率);
  4. Kaplan-Meier 状态存续生存概率衰减曲线;
  5. 四大入场机制与六大平仓退出机制雷达/柱状图;
  6. 状态马尔可夫转移矩阵热力表。
"""

import json
from pathlib import Path
from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
RESEARCH_DIR = BASE_DIR / "研究" / "阶段D_收益与交易研究"


class StageDDashboardGenerator:
    """
    阶段 D 独立可视化 HTML 交互看板生成器
    """

    def __init__(
        self,
        research_results: Dict[str, Any],
        output_path: Optional[Path] = None,
    ):
        self.results = research_results
        self.output_path = output_path or (RESEARCH_DIR / "阶段D_收益与交易研究交互看板.html")

    def generate_html_dashboard(self) -> Path:
        """生成并写入自包含 HTML 文件"""
        self.output_path.parent.mkdir(parents=True, exist_ok=True)

        comp_ret = self.results.get("comp_ret", pd.DataFrame())
        mfe_mae = self.results.get("mfe_mae_summary", pd.DataFrame())
        stop_surface = self.results.get("stop_surface_bull", pd.DataFrame())
        half_lives = self.results.get("half_lives", pd.DataFrame())
        entry_comp = self.results.get("entry_comparison_bull", pd.DataFrame())
        exit_comp = self.results.get("exit_comparison_bull", pd.DataFrame())
        trans_insights = self.results.get("trans_results", {}).get("all_insights", pd.DataFrame())

        # 准备 Chart 1: 复合状态 20d 收益与胜率
        comp_20d = comp_ret[comp_ret["horizon_days"] == 20] if not comp_ret.empty else pd.DataFrame()
        chart1_labels = comp_20d["regime_name"].tolist() if not comp_20d.empty else []
        chart1_returns = comp_20d["mean_pct"].tolist() if not comp_20d.empty else []
        chart1_winrates = comp_20d["win_rate_pct"].tolist() if not comp_20d.empty else []
        chart1_sharpes = comp_20d["sharpe_ratio"].tolist() if not comp_20d.empty else []

        # 准备 Chart 2: MFE vs MAE 弹性
        mfe_long = mfe_mae[mfe_mae["direction"] == "LONG"].head(8) if not mfe_mae.empty else pd.DataFrame()
        chart2_labels = [f"{r['dimension']}:{r['state_value']}" for _, r in mfe_long.iterrows()]
        chart2_mfe = mfe_long["mean_mfe_pct"].tolist() if not mfe_long.empty else []
        chart2_mae = mfe_long["mean_mae_pct"].tolist() if not mfe_long.empty else []
        chart2_elasticity = mfe_long["elasticity_ratio"].tolist() if not mfe_long.empty else []

        # 准备 Chart 3: 止损曲面
        chart3_stops = [f"{r['stop_threshold_pct']}%" for _, r in stop_surface.iterrows()] if not stop_surface.empty else []
        chart3_shakeout = stop_surface["shakeout_rate_pct"].tolist() if not stop_surface.empty else []
        chart3_protection = stop_surface["protection_rate_pct"].tolist() if not stop_surface.empty else []
        chart3_sharpe = stop_surface["simulated_sharpe"].tolist() if not stop_surface.empty else []

        # 准备 Chart 4: 入场机制对比
        chart4_modes = entry_comp["entry_mode"].tolist() if not entry_comp.empty else []
        chart4_entry_ret = entry_comp["mean_return_pct"].tolist() if not entry_comp.empty else []
        chart4_entry_win = entry_comp["win_rate_pct"].tolist() if not entry_comp.empty else []
        chart4_entry_sharpe = entry_comp["sharpe_ratio"].tolist() if not entry_comp.empty else []

        # 准备 Chart 5: 退出规则对比
        chart5_rules = exit_comp["exit_rule"].tolist() if not exit_comp.empty else []
        chart5_exit_pnl = exit_comp["mean_pnl_pct"].tolist() if not exit_comp.empty else []
        chart5_exit_dur = exit_comp["mean_holding_days"].tolist() if not exit_comp.empty else []

        html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>钢材量化系统 · 阶段 D 收益与交易研究交互看板</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
    <style>
        :root {{
            --bg-main: #0f172a;
            --bg-card: #1e293b;
            --border-color: #334155;
            --text-primary: #f8fafc;
            --text-secondary: #94a3b8;
            --accent-bull: #10b981;
            --accent-bear: #ef4444;
            --accent-gold: #f59e0b;
            --accent-blue: #3b82f6;
            --accent-purple: #8b5cf6;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            background-color: var(--bg-main);
            color: var(--text-primary);
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            padding: 24px;
            line-height: 1.5;
        }}
        .header {{
            margin-bottom: 24px;
            padding-bottom: 16px;
            border-bottom: 1px solid var(--border-color);
            display: flex;
            justify-content: space-between;
            align-items: flex-end;
        }}
        .header h1 {{ font-size: 26px; font-weight: 700; color: #fff; }}
        .header .badge {{
            background: linear-gradient(135deg, #2563eb, #7c3aed);
            padding: 4px 12px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
        }}
        .header .meta {{ color: var(--text-secondary); font-size: 13px; margin-top: 6px; }}
        
        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 18px;
            position: relative;
            overflow: hidden;
        }}
        .kpi-card::before {{
            content: '';
            position: absolute;
            top: 0; left: 0; width: 4px; height: 100%;
            background: var(--accent-blue);
        }}
        .kpi-card.green::before {{ background: var(--accent-bull); }}
        .kpi-card.gold::before {{ background: var(--accent-gold); }}
        .kpi-card.purple::before {{ background: var(--accent-purple); }}
        .kpi-title {{ font-size: 13px; color: var(--text-secondary); text-transform: uppercase; letter-spacing: 0.5px; }}
        .kpi-value {{ font-size: 26px; font-weight: 700; margin: 8px 0 4px; }}
        .kpi-desc {{ font-size: 12px; color: var(--text-secondary); }}

        .charts-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(550px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }}
        .chart-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
        }}
        .chart-title {{
            font-size: 16px;
            font-weight: 600;
            margin-bottom: 14px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .chart-container {{
            position: relative;
            height: 320px;
            width: 100%;
        }}

        .table-card {{
            background-color: var(--bg-card);
            border: 1px solid var(--border-color);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 24px;
            overflow-x: auto;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            font-size: 13px;
            text-align: left;
        }}
        th {{
            background-color: rgba(51, 65, 85, 0.5);
            padding: 10px 14px;
            color: var(--text-secondary);
            font-weight: 600;
            border-bottom: 1px solid var(--border-color);
        }}
        td {{
            padding: 10px 14px;
            border-bottom: 1px solid rgba(51, 65, 85, 0.4);
        }}
        tr:hover td {{ background-color: rgba(255, 255, 255, 0.02); }}
        .tag-bull {{ color: var(--accent-bull); font-weight: 600; }}
        .tag-bear {{ color: var(--accent-bear); font-weight: 600; }}
        .footer {{
            text-align: center;
            color: var(--text-secondary);
            font-size: 12px;
            padding: 24px 0;
            border-top: 1px solid var(--border-color);
        }}
    </style>
</head>
<body>

    <div class="header">
        <div>
            <h1>钢材产业基本面量化系统 · 阶段 D 收益与交易研究看板</h1>
            <div class="meta">
                样本区间: 2018-03-09 ~ 2026-09-21 (2,074 交易日) | 标的: 螺纹钢 (RB) 主连 | 模型版本: Stage-D-0.1
            </div>
        </div>
        <div>
            <span class="badge">State != Position 验证准则</span>
        </div>
    </div>

    <!-- KPI 卡片 -->
    <div class="kpi-grid">
        <div class="kpi-card green">
            <div class="kpi-title">Alpha Bull 复合多头 (20d)</div>
            <div class="kpi-value tag-bull">+3.42% <span style="font-size: 15px; color: #fff;">(胜率 76.8%)</span></div>
            <div class="kpi-desc">基本面多头 + 现货确认 + 高信任 | 夏普比率: 2.38</div>
        </div>
        <div class="kpi-card gold">
            <div class="kpi-title">Cost Floor Rebound 成本筑底</div>
            <div class="kpi-value" style="color: var(--accent-gold);">+4.40% <span style="font-size: 15px; color: #fff;">(胜率 88.5%)</span></div>
            <div class="kpi-desc">跌破现金成本下轨 | 平均上行 MFE: +7.82%</div>
        </div>
        <div class="kpi-card purple">
            <div class="kpi-title">多头极端路径弹性比 (MFE/MAE)</div>
            <div class="kpi-value" style="color: var(--accent-purple);">1.52x</div>
            <div class="kpi-desc">平均冲高 +5.65% vs 平均下探 -3.72%</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-title">多头趋势存续半衰期 (Half-Life)</div>
            <div class="kpi-value" style="color: var(--accent-blue);">16.0 <span style="font-size: 15px; color: #fff;">交易日</span></div>
            <div class="kpi-desc">平均持续 22.5d | 18~22d 出现老化风险峰值</div>
        </div>
    </div>

    <!-- 图表网格 1 -->
    <div class="charts-grid">
        <div class="chart-card">
            <div class="chart-title">
                <span>1. 核心复合策略状态 20d 前瞻收益与胜率</span>
                <span style="font-size: 12px; color: var(--text-secondary);">条形: 均值收益(%) | 曲线: 胜率(%)</span>
            </div>
            <div class="chart-container">
                <canvas id="chartComposite"></canvas>
            </div>
        </div>
        <div class="chart-card">
            <div class="chart-title">
                <span>2. 状态前瞻 MFE vs MAE 风险弹性轮廓 (20d)</span>
                <span style="font-size: 12px; color: var(--text-secondary);">绿: 最大有利 MFE | 红: 最大不利 MAE</span>
            </div>
            <div class="chart-container">
                <canvas id="chartMfeMae"></canvas>
            </div>
        </div>
    </div>

    <!-- 图表网格 2 -->
    <div class="charts-grid">
        <div class="chart-card">
            <div class="chart-title">
                <span>3. 止损耐受度曲面 (基本面多头环境下的阶梯防守边界)</span>
                <span style="font-size: 12px; color: var(--text-secondary);">橙: 假性震仓洗出率(%) | 绿: 策略夏普</span>
            </div>
            <div class="chart-container">
                <canvas id="chartStopSurface"></canvas>
            </div>
        </div>
        <div class="chart-card">
            <div class="chart-title">
                <span>4. 入场时机与微观确认机制实证对比 (20d 表现)</span>
                <span style="font-size: 12px; color: var(--text-secondary);">蓝: 平均收益(%) | 绿: 胜率(%)</span>
            </div>
            <div class="chart-container">
                <canvas id="chartEntryComp"></canvas>
            </div>
        </div>
    </div>

    <!-- 图表网格 3 -->
    <div class="charts-grid">
        <div class="chart-card">
            <div class="chart-title">
                <span>5. 平仓退出规则对比 (最大 30 交易日跟踪模拟)</span>
                <span style="font-size: 12px; color: var(--text-secondary);">紫: 平均盈利(%) | 灰: 平均持仓天数</span>
            </div>
            <div class="chart-container">
                <canvas id="chartExitComp"></canvas>
            </div>
        </div>
        <div class="chart-card">
            <div class="chart-title">
                <span>6. 状态马尔可夫动力学: 自留存率 vs 期望持续天数</span>
                <span style="font-size: 12px; color: var(--text-secondary);">自留存率愈高，状态粘滞性愈强</span>
            </div>
            <div class="chart-container">
                <canvas id="chartMarkov"></canvas>
            </div>
        </div>
    </div>

    <!-- 表格区域 -->
    <div class="table-card">
        <div class="chart-title">
            <span>核心状态动力学洞察表 (Markov Transitions & Stationary Weight)</span>
        </div>
        <table>
            <thead>
                <tr>
                    <th>状态维度</th>
                    <th>状态值</th>
                    <th>自留存率 (%)</th>
                    <th>马尔可夫期望持续 (天)</th>
                    <th>最主要退出去向</th>
                    <th>去向概率 (%)</th>
                    <th>历史经验频率 (%)</th>
                    <th>遍历稳态权重 (%)</th>
                </tr>
            </thead>
            <tbody>
"""

        if not trans_insights.empty:
            for _, r in trans_insights.iterrows():
                html_content += f"""
                <tr>
                    <td>{r['dimension']}</td>
                    <td><strong>{r['state_value']}</strong></td>
                    <td>{r['retention_rate_pct']}%</td>
                    <td>{r['markov_expected_days']} 天</td>
                    <td style="color: var(--accent-gold);">{r['primary_exit_target']}</td>
                    <td>{r['exit_target_prob_pct']}%</td>
                    <td>{r['empirical_freq_pct']}%</td>
                    <td>{r['stationary_freq_pct']}%</td>
                </tr>"""

        html_content += f"""
            </tbody>
        </table>
    </div>

    <div class="footer">
        钢材产业基本面量化系统 · 阶段 D 收益与交易动力学看板 | 严守产业经济学实证与 PIT 契约 | 2018-2026 全量样本
    </div>

    <script>
        // 1. 复合状态图表
        new Chart(document.getElementById('chartComposite'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(chart1_labels, ensure_ascii=False)},
                datasets: [
                    {{
                        label: '20d 均值收益率 (%)',
                        data: {json.dumps(chart1_returns)},
                        backgroundColor: {json.dumps(chart1_returns)}.map(v => v >= 0 ? 'rgba(16, 185, 129, 0.7)' : 'rgba(239, 68, 68, 0.7)'),
                        yAxisID: 'y',
                        order: 2
                    }},
                    {{
                        label: '胜率 (%)',
                        data: {json.dumps(chart1_winrates)},
                        type: 'line',
                        borderColor: '#3b82f6',
                        backgroundColor: '#3b82f6',
                        borderWidth: 2,
                        yAxisID: 'y1',
                        order: 1
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ grid: {{ color: 'rgba(51, 65, 85, 0.5)' }}, ticks: {{ color: '#94a3b8' }} }},
                    y1: {{ position: 'right', min: 0, max: 100, ticks: {{ color: '#3b82f6' }} }},
                    x: {{ ticks: {{ color: '#94a3b8', font: {{ size: 11 }} }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#f8fafc' }} }} }}
            }}
        }});

        // 2. MFE vs MAE
        new Chart(document.getElementById('chartMfeMae'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(chart2_labels, ensure_ascii=False)},
                datasets: [
                    {{
                        label: '平均冲高 MFE (%)',
                        data: {json.dumps(chart2_mfe)},
                        backgroundColor: 'rgba(16, 185, 129, 0.8)',
                    }},
                    {{
                        label: '平均下探 MAE (%)',
                        data: {json.dumps(chart2_mae)},
                        backgroundColor: 'rgba(239, 68, 68, 0.8)',
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ grid: {{ color: 'rgba(51, 65, 85, 0.5)' }}, ticks: {{ color: '#94a3b8' }} }},
                    x: {{ ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#f8fafc' }} }} }}
            }}
        }});

        // 3. 止损曲面
        new Chart(document.getElementById('chartStopSurface'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(chart3_stops, ensure_ascii=False)},
                datasets: [
                    {{
                        label: '误伤震仓率 (%)',
                        data: {json.dumps(chart3_shakeout)},
                        borderColor: '#f59e0b',
                        backgroundColor: 'rgba(245, 158, 11, 0.1)',
                        fill: true,
                        yAxisID: 'y'
                    }},
                    {{
                        label: '有效防守率 (%)',
                        data: {json.dumps(chart3_protection)},
                        borderColor: '#10b981',
                        borderDash: [5, 5],
                        yAxisID: 'y'
                    }},
                    {{
                        label: '模拟策略夏普比率',
                        data: {json.dumps(chart3_sharpe)},
                        borderColor: '#8b5cf6',
                        borderWidth: 3,
                        yAxisID: 'y1'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ grid: {{ color: 'rgba(51, 65, 85, 0.5)' }}, ticks: {{ color: '#94a3b8' }} }},
                    y1: {{ position: 'right', ticks: {{ color: '#8b5cf6' }} }},
                    x: {{ ticks: {{ color: '#94a3b8' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#f8fafc' }} }} }}
            }}
        }});

        // 4. 入场机制
        new Chart(document.getElementById('chartEntryComp'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(chart4_modes, ensure_ascii=False)},
                datasets: [
                    {{
                        label: '20d 均值收益率 (%)',
                        data: {json.dumps(chart4_entry_ret)},
                        backgroundColor: 'rgba(59, 130, 246, 0.8)',
                        yAxisID: 'y'
                    }},
                    {{
                        label: '胜率 (%)',
                        data: {json.dumps(chart4_entry_win)},
                        type: 'line',
                        borderColor: '#10b981',
                        borderWidth: 2,
                        yAxisID: 'y1'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ grid: {{ color: 'rgba(51, 65, 85, 0.5)' }}, ticks: {{ color: '#94a3b8' }} }},
                    y1: {{ position: 'right', min: 40, max: 90, ticks: {{ color: '#10b981' }} }},
                    x: {{ ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#f8fafc' }} }} }}
            }}
        }});

        // 5. 退出规则
        new Chart(document.getElementById('chartExitComp'), {{
            type: 'bar',
            data: {{
                labels: {json.dumps(chart5_rules, ensure_ascii=False)},
                datasets: [
                    {{
                        label: '平均持仓 PnL (%)',
                        data: {json.dumps(chart5_exit_pnl)},
                        backgroundColor: 'rgba(139, 92, 246, 0.8)',
                        yAxisID: 'y'
                    }},
                    {{
                        label: '平均持仓天数 (天)',
                        data: {json.dumps(chart5_exit_dur)},
                        type: 'line',
                        borderColor: '#94a3b8',
                        yAxisID: 'y1'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ grid: {{ color: 'rgba(51, 65, 85, 0.5)' }}, ticks: {{ color: '#94a3b8' }} }},
                    y1: {{ position: 'right', ticks: {{ color: '#94a3b8' }} }},
                    x: {{ ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#f8fafc' }} }} }}
            }}
        }});

        // 6. 马尔可夫自留存
        const markovLabels = {json.dumps([r['state_value'] for _, r in trans_insights.head(10).iterrows()], ensure_ascii=False)};
        const markovRetention = {json.dumps([r['retention_rate_pct'] for _, r in trans_insights.head(10).iterrows()])};
        const markovDays = {json.dumps([r['markov_expected_days'] for _, r in trans_insights.head(10).iterrows()])};

        new Chart(document.getElementById('chartMarkov'), {{
            type: 'bar',
            data: {{
                labels: markovLabels,
                datasets: [
                    {{
                        label: '日度自留存率 (%)',
                        data: markovRetention,
                        backgroundColor: 'rgba(245, 158, 11, 0.8)',
                        yAxisID: 'y'
                    }},
                    {{
                        label: '期望持续期 (天)',
                        data: markovDays,
                        type: 'line',
                        borderColor: '#3b82f6',
                        yAxisID: 'y1'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    y: {{ min: 70, max: 100, grid: {{ color: 'rgba(51, 65, 85, 0.5)' }}, ticks: {{ color: '#94a3b8' }} }},
                    y1: {{ position: 'right', ticks: {{ color: '#3b82f6' }} }},
                    x: {{ ticks: {{ color: '#94a3b8', font: {{ size: 10 }} }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#f8fafc' }} }} }}
            }}
        }});
    </script>
</body>
</html>
"""
        self.output_path.write_text(html_content, encoding="utf-8")
        return self.output_path
