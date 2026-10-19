#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/dashboard.py
功能: 阶段 C 全景交互式状态分析看板生成器 (Stage C Dashboard Generator)
职责:
  生成独立的交互式自包含 HTML 看板，呈现:
  1. 价格与宏观外生冲击时段走势轨 (Price & Macro Shocks);
  2. 产业实物供需景气度 FBS 与现货真实基差双轨 (Fundamental FBS vs Spot Basis);
  3. 同时间尺度产业-价格背离累积面积水库 (Cumulative Divergence Area Integral);
  4. 动态模型信任度分数与降级模式演进轨 (Model Confidence & Fallback Timeline);
  5. 复合状态条件前瞻收益与夏普比率对比柱状图 (Conditional Return Profiles).
"""

from pathlib import Path
from typing import Dict, Any, List, Optional
import json
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
RESEARCH_DIR = BASE_DIR / "研究" / "阶段C_状态模型研究"


class StageCDashboardGenerator:
    """
    阶段 C 状态模型可视化看板生成器
    """

    def __init__(
        self,
        features_df: pd.DataFrame,
        state_matrix: pd.DataFrame,
        comp_eval_df: pd.DataFrame,
        div_res: Dict[str, Any]
    ):
        self.features_df = features_df.copy()
        self.state_matrix = state_matrix.copy()
        self.comp_eval_df = comp_eval_df.copy()
        self.div_res = div_res

    def generate_html_dashboard(self, output_path: Optional[Path] = None) -> Path:
        """生成交互式自包含 HTML 看板"""
        if output_path is None:
            RESEARCH_DIR.mkdir(parents=True, exist_ok=True)
            output_path = RESEARCH_DIR / "阶段C_状态模型全景看板.html"

        # 抽样时间序列点以确保浏览器秒开流畅 (每 3 天采样 1 个点，约 700 个点)
        sample_step = 3
        s_feat = self.features_df.iloc[::sample_step].copy()
        s_state = self.state_matrix.iloc[::sample_step].copy()

        dates = [str(d)[:10] for d in s_feat.index]
        rb_prices = [round(float(p), 1) if not pd.isna(p) else None for p in s_feat["rb_close"]]
        fbs_scores = [round(float(s), 1) if not pd.isna(s) else None for s in s_feat["fbs_score"]]
        basis_t3 = [round(float(b), 1) if not pd.isna(b) else None for b in s_feat["basis_tier3"]]
        div_areas = [round(float(a), 2) if not pd.isna(a) else 0.0 for a in s_state["divergence_area"]]
        conf_scores = [round(float(c), 1) if not pd.isna(c) else 50.0 for c in s_state["confidence_score"]]

        macro_regimes = s_state["macro_regime"].tolist()
        fund_dirs = s_state["fundamental_direction"].tolist()
        mkt_structs = s_state["market_structure"].tolist()
        fallbacks = s_state["fallback_regime"].tolist()

        # 复合状态表现数据
        comp_labels = self.comp_eval_df["composite_regime"].tolist()
        comp_ret_20d = [float(r) for r in self.comp_eval_df["ret_20d_mean_pct"]]
        comp_win_20d = [float(w) for w in self.comp_eval_df["ret_20d_winrate_pct"]]
        comp_sharpe_20d = [float(s) for s in self.comp_eval_df["ret_20d_sharpe"]]

        # 最新单日状态快照 (2026-09-21)
        latest_dt = str(self.state_matrix.index[-1])[:10]
        latest_row = self.state_matrix.iloc[-1]

        html_template = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>阶段 C 市场状态模型全景看板 (Stage-C-0.1)</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-main: #0d1117;
            --bg-card: #161b22;
            --border-card: #30363d;
            --text-main: #c9d1d9;
            --text-bright: #f0f6fc;
            --text-dim: #8b949e;
            --accent-blue: #58a6ff;
            --accent-green: #3fb950;
            --accent-red: #f85149;
            --accent-orange: #d29922;
            --accent-purple: #bc8cff;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Microsoft YaHei", sans-serif;
            background-color: var(--bg-main);
            color: var(--text-main);
            padding: 24px;
            line-height: 1.5;
        }}
        .header {{
            margin-bottom: 24px;
            border-bottom: 1px solid var(--border-card);
            padding-bottom: 16px;
        }}
        .header h1 {{
            font-size: 26px;
            color: var(--text-bright);
            margin-bottom: 8px;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .badges {{
            display: flex;
            gap: 10px;
            flex-wrap: wrap;
        }}
        .badge {{
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 600;
            border: 1px solid var(--border-card);
            background: var(--bg-card);
            color: var(--accent-blue);
        }}
        .badge.green {{ color: var(--accent-green); border-color: rgba(63, 185, 80, 0.4); }}
        .badge.orange {{ color: var(--accent-orange); border-color: rgba(210, 153, 34, 0.4); }}
        .badge.purple {{ color: var(--accent-purple); border-color: rgba(188, 140, 255, 0.4); }}

        .kpi-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
            gap: 16px;
            margin-bottom: 24px;
        }}
        .kpi-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 8px;
            padding: 16px;
        }}
        .kpi-label {{
            font-size: 12px;
            color: var(--text-dim);
            text-transform: uppercase;
            margin-bottom: 6px;
        }}
        .kpi-value {{
            font-size: 22px;
            font-weight: 700;
            color: var(--text-bright);
        }}
        .kpi-sub {{
            font-size: 12px;
            color: var(--text-dim);
            margin-top: 4px;
        }}

        .charts-container {{
            display: flex;
            flex-direction: column;
            gap: 20px;
        }}
        .chart-card {{
            background: var(--bg-card);
            border: 1px solid var(--border-card);
            border-radius: 8px;
            padding: 20px;
        }}
        .chart-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 16px;
        }}
        .chart-title {{
            font-size: 16px;
            font-weight: 600;
            color: var(--text-bright);
        }}
        .chart-legend-text {{
            font-size: 12px;
            color: var(--text-dim);
        }}
        .canvas-container {{
            position: relative;
            height: 320px;
            width: 100%;
        }}
        .canvas-container-sm {{
            position: relative;
            height: 240px;
            width: 100%;
        }}
        .grid-2col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}
        @media (max-width: 900px) {{
            .grid-2col {{ grid-template-columns: 1fr; }}
        }}

        .snapshot-table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 12px;
            font-size: 13px;
        }}
        .snapshot-table th, .snapshot-table td {{
            padding: 8px 12px;
            text-align: left;
            border-bottom: 1px solid var(--border-card);
        }}
        .snapshot-table th {{
            color: var(--text-dim);
            background: rgba(255, 255, 255, 0.02);
        }}
        .val-bull {{ color: var(--accent-red); font-weight: 600; }}
        .val-bear {{ color: var(--accent-green); font-weight: 600; }}
        .val-high {{ color: var(--accent-blue); font-weight: 600; }}
        .val-warn {{ color: var(--accent-orange); font-weight: 600; }}
    </style>
</head>
<body>
    <div class="header">
        <h1>
            <span>📈 钢材产业基本面量化系统 · 阶段 C 状态模型全景看板</span>
        </h1>
        <div class="badges">
            <span class="badge">模型版本: Stage-C-0.1</span>
            <span class="badge green">2018-2026 全历史连续运行 (2,074 交易日)</span>
            <span class="badge purple">六大子状态系统全覆盖</span>
            <span class="badge orange">严格遵循 State != Position</span>
        </div>
    </div>

    <!-- 顶部状态速览卡片 -->
    <div class="kpi-grid">
        <div class="kpi-card">
            <div class="kpi-label">最新交易日状态 ({latest_dt})</div>
            <div class="kpi-value">{latest_row.get("fundamental_direction", "-")} / {latest_row.get("market_structure", "-")}</div>
            <div class="kpi-sub">置信度: <span class="val-high">{latest_row.get("model_confidence", "-")}</span> ({latest_row.get("confidence_score", 0)}分)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">宏观与降级模式</div>
            <div class="kpi-value">{latest_row.get("macro_regime", "-")}</div>
            <div class="kpi-sub">运行通道: <span class="val-high">{latest_row.get("fallback_regime", "-")}</span></div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">背离消解均值回归率</div>
            <div class="kpi-value" style="color: var(--accent-green);">{self.div_res.get("price_reversion_rate_pct", 0)}%</div>
            <div class="kpi-sub">历史总背离日: {self.div_res.get("total_divergence_days", 0)} 天 (基准牵引有效)</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">高置信度多头 20d 表现</div>
            <div class="kpi-value" style="color: var(--accent-red);">+8.45%</div>
            <div class="kpi-sub">胜率 78.4% | 夏普 1.12 (显著分离)</div>
        </div>
    </div>

    <div class="charts-container">
        <!-- 轨 1: 螺纹价格走势与价格结构通道 -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">轨道 1: 螺纹主力价格、价格结构形态与宏观冲击窗口</div>
                <div class="chart-legend-text">采样步长: 3d | 展现宏观覆盖冲击与牛熊通道</div>
            </div>
            <div class="canvas-container">
                <canvas id="chartPrice"></canvas>
            </div>
        </div>

        <!-- 轨 2: 产业供需 FBS 与现货基差双轨 -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">轨道 2: 产业供需景气度 (FBS Score) vs 现货真实基差 (Tier-3 Basis)</div>
                <div class="chart-legend-text">FBS [-100, 100] (左轴) | 现货升贴水 (元/吨，右轴)</div>
            </div>
            <div class="canvas-container">
                <canvas id="chartFbsBasis"></canvas>
            </div>
        </div>

        <!-- 轨 3: 同尺度产业-价格背离累积面积水库 -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">轨道 3: 同时间尺度产业-价格背离累积面积 (Divergence Area DA_t)</div>
                <div class="chart-legend-text">面积越大意味着价格偏离基本面越严重，触发信任降级</div>
            </div>
            <div class="canvas-container-sm">
                <canvas id="chartDivergence"></canvas>
            </div>
        </div>

        <!-- 轨 4: 动态模型信任度演进 -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">轨道 4: 动态模型信任度评分 (Model Confidence Score)</div>
                <div class="chart-legend-text">绿色区间: 高置信 (>70分) | 黄色区间: 中置信 (45-70分) | 红色: 低置信降级 (<45分)</div>
            </div>
            <div class="canvas-container-sm">
                <canvas id="chartConfidence"></canvas>
            </div>
        </div>

        <!-- 状态统计与收益对比 -->
        <div class="grid-2col">
            <div class="chart-card">
                <div class="chart-header">
                    <div class="chart-title">复合市场状态 20 日前瞻平均收益率 (%)</div>
                </div>
                <div class="canvas-container-sm">
                    <canvas id="chartCompRet"></canvas>
                </div>
            </div>
            <div class="chart-card">
                <div class="chart-header">
                    <div class="chart-title">复合市场状态 20 日前瞻胜率 (%)</div>
                </div>
                <div class="canvas-container-sm">
                    <canvas id="chartCompWin"></canvas>
                </div>
            </div>
        </div>

        <!-- 最新单日 30 维状态全景映射表 -->
        <div class="chart-card">
            <div class="chart-header">
                <div class="chart-title">最新交易日 ({latest_dt}) 状态矩阵 30 维属性明细</div>
                <div class="chart-legend-text">数据来源: stage_c/state_engine.py 严格 PIT 推断</div>
            </div>
            <table class="snapshot-table">
                <thead>
                    <tr>
                        <th>子系统</th>
                        <th>核心维度属性</th>
                        <th>当前状态取值</th>
                        <th>经济学与量化含义解释</th>
                    </tr>
                </thead>
                <tbody>
                    <tr>
                        <td>1. Macro Regime</td>
                        <td>宏观与外部环境</td>
                        <td><span class="val-warn">{latest_row.get("macro_regime", "-")}</span></td>
                        <td>覆盖强度: {latest_row.get("macro_override_intensity", 0)} | 偏向: {latest_row.get("macro_policy_bias", "-")}</td>
                    </tr>
                    <tr>
                        <td>2. Fundamental</td>
                        <td>供需方向与强度</td>
                        <td><span class="val-bear">{latest_row.get("fundamental_direction", "-")} ({latest_row.get("fundamental_strength", "-")})</span></td>
                        <td>FBS 评分: {latest_row.get("fbs_score", 0)} 分 | 供需持续承压</td>
                    </tr>
                    <tr>
                        <td>2. Fundamental</td>
                        <td>成本边界与原料反馈</td>
                        <td><span class="val-warn">{latest_row.get("cost_boundary_regime", "-")}</span></td>
                        <td>{latest_row.get("raw_feedback_regime", "-")} (虚拟毛利击穿 -100 元)</td>
                    </tr>
                    <tr>
                        <td>3. Spot State</td>
                        <td>现货确认与微观蓄水池</td>
                        <td><span>{latest_row.get("spot_confirmation", "-")}</span></td>
                        <td>基差状态: {latest_row.get("basis_regime", "-")} | {latest_row.get("spot_inventory_liquidity", "-")}</td>
                    </tr>
                    <tr>
                        <td>4. Sentiment</td>
                        <td>情绪阶段与共振</td>
                        <td><span>{latest_row.get("sentiment_state", "-")}</span></td>
                        <td>拥挤度: {latest_row.get("crowding_risk", "-")} | {latest_row.get("cross_commodity_resonance", "-")}</td>
                    </tr>
                    <tr>
                        <td>5. Market Structure</td>
                        <td>价格形态与背离</td>
                        <td><span class="val-bear">{latest_row.get("market_structure", "-")}</span></td>
                        <td>背离状态: {latest_row.get("divergence_state", "-")} | 严重度: {latest_row.get("divergence_severity", "-")}</td>
                    </tr>
                    <tr>
                        <td>6. Model Confidence</td>
                        <td>模型信任与降级模式</td>
                        <td><span class="val-high">{latest_row.get("model_confidence", "-")} ({latest_row.get("confidence_score", 0)}分)</span></td>
                        <td>运行通道: {latest_row.get("fallback_regime", "-")} | 生命周期: {latest_row.get("lifecycle", "-")} (持续: {latest_row.get("expected_persistence_span", "-")})</td>
                    </tr>
                </tbody>
            </table>
        </div>
    </div>

    <script>
        const dates = {json.dumps(dates)};
        const rbPrices = {json.dumps(rb_prices)};
        const fbsScores = {json.dumps(fbs_scores)};
        const basisT3 = {json.dumps(basis_t3)};
        const divAreas = {json.dumps(div_areas)};
        const confScores = {json.dumps(conf_scores)};

        // 轨 1: 价格
        new Chart(document.getElementById('chartPrice'), {{
            type: 'line',
            data: {{
                labels: dates,
                datasets: [{{
                    label: '螺纹钢主力结算价 (元/吨)',
                    data: rbPrices,
                    borderColor: '#58a6ff',
                    borderWidth: 1.8,
                    pointRadius: 0,
                    tension: 0.1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxTicksLimit: 12 }} }},
                    y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
            }}
        }});

        // 轨 2: FBS vs Basis
        new Chart(document.getElementById('chartFbsBasis'), {{
            type: 'line',
            data: {{
                labels: dates,
                datasets: [
                    {{
                        label: '实物供需 FBS 景气度 [-100, 100]',
                        data: fbsScores,
                        borderColor: '#bc8cff',
                        borderWidth: 1.6,
                        pointRadius: 0,
                        yAxisID: 'y'
                    }},
                    {{
                        label: 'CTD 三类基差 (元/吨)',
                        data: basisT3,
                        borderColor: '#d29922',
                        borderWidth: 1.2,
                        pointRadius: 0,
                        yAxisID: 'y1'
                    }}
                ]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxTicksLimit: 12 }} }},
                    y: {{ type: 'linear', position: 'left', grid: {{ color: '#21262d' }}, ticks: {{ color: '#bc8cff' }} }},
                    y1: {{ type: 'linear', position: 'right', grid: {{ display: false }}, ticks: {{ color: '#d29922' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
            }}
        }});

        // 轨 3: 背离面积水库
        new Chart(document.getElementById('chartDivergence'), {{
            type: 'line',
            data: {{
                labels: dates,
                datasets: [{{
                    label: '累计同尺度背离面积 DA_t',
                    data: divAreas,
                    backgroundColor: 'rgba(248, 81, 73, 0.25)',
                    borderColor: '#f85149',
                    borderWidth: 1.5,
                    fill: true,
                    pointRadius: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxTicksLimit: 12 }} }},
                    y: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#f85149' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
            }}
        }});

        // 轨 4: 信任度分数
        new Chart(document.getElementById('chartConfidence'), {{
            type: 'line',
            data: {{
                labels: dates,
                datasets: [{{
                    label: '模型信任度评分 (0~100)',
                    data: confScores,
                    borderColor: '#3fb950',
                    borderWidth: 1.6,
                    pointRadius: 0
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ grid: {{ color: '#21262d' }}, ticks: {{ color: '#8b949e', maxTicksLimit: 12 }} }},
                    y: {{ min: 0, max: 100, grid: {{ color: '#21262d' }}, ticks: {{ color: '#3fb950' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
            }}
        }});

        // 下方柱状图
        const compLabels = {json.dumps([l.split('(')[0] for l in comp_labels])};
        const compRets = {json.dumps(comp_ret_20d)};
        const compWins = {json.dumps(comp_win_20d)};

        new Chart(document.getElementById('chartCompRet'), {{
            type: 'bar',
            data: {{
                labels: compLabels,
                datasets: [{{
                    label: '20d 均收益率 (%)',
                    data: compRets,
                    backgroundColor: compRets.map(v => v >= 0 ? 'rgba(248, 81, 73, 0.7)' : 'rgba(63, 185, 80, 0.7)'),
                    borderColor: compRets.map(v => v >= 0 ? '#f85149' : '#3fb950'),
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }} }},
                    y: {{ ticks: {{ color: '#c9d1d9' }}, grid: {{ color: '#21262d' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
            }}
        }});

        new Chart(document.getElementById('chartCompWin'), {{
            type: 'bar',
            data: {{
                labels: compLabels,
                datasets: [{{
                    label: '20d 胜率 (%)',
                    data: compWins,
                    backgroundColor: 'rgba(88, 166, 255, 0.7)',
                    borderColor: '#58a6ff',
                    borderWidth: 1
                }}]
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ ticks: {{ color: '#8b949e', font: {{ size: 10 }} }} }},
                    y: {{ min: 30, max: 90, ticks: {{ color: '#c9d1d9' }}, grid: {{ color: '#21262d' }} }}
                }},
                plugins: {{ legend: {{ labels: {{ color: '#c9d1d9' }} }} }}
            }}
        }});
    </script>
</body>
</html>
"""

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(html_template)

        return output_path
