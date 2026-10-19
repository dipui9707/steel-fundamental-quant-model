#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: build_recent_spread_pdf_report.py
用途:
  生成《近期热卷现货与卷螺差走弱深度量化事实报告（2026年9月23日更新版）》PDF
  - 页面宽度放2张图 (第3页2x2布局，每行两张图，比例适中无过度拉伸)
  - 边距贴合 (margin: 6mm 8mm)，消除页面两侧不必要留白
  - 表格与文字尺寸保持清晰饱满 (正文9.8pt，表格8.5pt/8.0pt)
  - 严格 4 页 A4 独立排版，每页独立成章
"""

import os
import shutil
import weasyprint

PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
ARTIFACT_DIR = "/home/hw/.gemini/antigravity/brain/78cbb79d-10e8-49b1-a7f1-b02789ba9c27"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "研究/现货价差专题")
PDF_FIG_DIR = os.path.join(OUTPUT_DIR, "pdf_figures")

PDF_OUTPUT_PROJECT = os.path.join(OUTPUT_DIR, "近期热卷现货与卷螺差走弱深度量化分析报告_20260923.pdf")
PDF_OUTPUT_ARTIFACT = os.path.join(ARTIFACT_DIR, "近期热卷现货与卷螺差走弱深度量化分析报告_20260923.pdf")

fig1_path = os.path.join(PDF_FIG_DIR, "fig_recent_1_spot_hz_sh.png")
fig2_path = os.path.join(PDF_FIG_DIR, "fig_recent_2_disk_futures.png")
fig3_path = os.path.join(PDF_FIG_DIR, "fig_recent_3_demand_export.png")

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>近期热卷现货与卷螺差走弱深度量化事实报告 (2026年9月23日数据更新版)</title>
<style>
  @page {{
    size: A4 portrait;
    margin: 6mm 8mm 6mm 8mm;
    @top-left {{
      content: "钢材产业系统量化模型 · 客观数据事实专题";
      font-size: 8.0pt;
      font-family: 'Noto Sans CJK SC', sans-serif;
      color: #64748b;
      border-bottom: 0.5pt solid #cbd5e1;
      padding-bottom: 2px;
    }}
    @top-right {{
      content: "数据截止时点: 2026年9月23日收盘";
      font-size: 8.0pt;
      font-family: 'Noto Sans CJK SC', sans-serif;
      color: #64748b;
      border-bottom: 0.5pt solid #cbd5e1;
      padding-bottom: 2px;
    }}
    @bottom-center {{
      content: "第 " counter(page) " 页 / 共 " counter(pages) " 页";
      font-size: 8.0pt;
      font-family: 'Noto Sans CJK SC', sans-serif;
      color: #94a3b8;
    }}
  }}

  body {{
    font-family: 'Noto Serif CJK SC', 'Noto Sans CJK SC', 'Source Han Serif SC', serif;
    color: #0f172a;
    line-height: 1.45;
    font-size: 9.8pt;
    margin: 0;
    padding: 0;
  }}

  h1, h2, h3, h4, th, .sans {{
    font-family: 'Noto Sans CJK SC', 'Source Han Sans SC', sans-serif;
  }}

  .page-container {{
    page-break-after: always;
    height: 100%;
    box-sizing: border-box;
  }}

  .page-container:last-child {{
    page-break-after: avoid;
  }}

  .header-box {{
    border-bottom: 2.5pt solid #0284c7;
    padding-bottom: 3px;
    margin-bottom: 4px;
  }}

  .report-tag {{
    display: inline-block;
    background-color: #e0f2fe;
    color: #0369a1;
    font-size: 8.0pt;
    font-weight: bold;
    padding: 1.5px 7px;
    border-radius: 3px;
    margin-bottom: 2px;
  }}

  h1 {{
    font-size: 16.5pt;
    color: #0f172a;
    margin: 1px 0 2px 0;
    line-height: 1.25;
    font-weight: 800;
  }}

  .meta-bar {{
    font-size: 8.5pt;
    color: #475569;
    margin-bottom: 1px;
  }}

  h2 {{
    font-size: 11.8pt;
    color: #0369a1;
    border-left: 3.5pt solid #0284c7;
    padding-left: 6px;
    margin: 4px 0 4px 0;
    line-height: 1.25;
  }}

  .chart-box {{
    width: 100%;
    text-align: center;
    margin: 2px 0 4px 0;
    padding: 0;
  }}

  .chart-box img {{
    width: 100%;
    display: block;
    margin: 0 auto;
    border: none;
  }}

  .data-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 8.5pt;
    margin: 3px 0 5px 0;
  }}

  .data-table th {{
    background-color: #f1f5f9;
    color: #1e293b;
    font-weight: bold;
    padding: 3.5px 5px;
    border: 0.5pt solid #cbd5e1;
    text-align: center;
  }}

  .data-table td {{
    padding: 3px 5px;
    border: 0.5pt solid #e2e8f0;
    text-align: center;
  }}

  .data-table tr:nth-child(even) {{
    background-color: #f8fafc;
  }}

  .highlight-cell {{
    font-weight: bold;
    color: #b91c1c;
  }}

  .fact-list {{
    margin: 3px 0 0 0;
    padding-left: 14px;
    font-size: 9.3pt;
    line-height: 1.45;
  }}

  .fact-list li {{
    margin-bottom: 3.0px;
  }}

  .badge {{
    font-weight: bold;
    color: #0369a1;
  }}

  .num-bold {{
    font-family: 'Noto Sans CJK SC', sans-serif;
    font-weight: bold;
  }}
</style>
</head>
<body>

<!-- ==================== 第 1 页: 现货价格与跨区卷螺差事实 ==================== -->
<div class="page-container">
  <div class="header-box">
    <span class="report-tag">产业量化事实系列报告 · 权威现货更新版</span>
    <h1>近期热卷现货与卷螺差走弱深度量化事实报告</h1>
    <div class="meta-bar">
      <span><strong>最新数据时点:</strong> 2026年9月23日收盘</span> |
      <span><strong>现货权威基准:</strong> 《每日现货.xlsx》Authoritative Truth</span> |
      <span><strong>趋势验证:</strong> Wind 现货数据库</span>
    </div>
  </div>

  <h2>1. 现货基准走势与跨区卷螺差（上海热卷 vs 杭州螺纹）</h2>
  
  <div class="chart-box">
    <img src="file://{fig1_path}" style="max-height: 94mm;" alt="现货与跨区卷螺差走势图">
  </div>

  <table class="data-table">
    <thead>
      <tr>
        <th>统计基准日期</th>
        <th>上海热卷(实录)</th>
        <th>杭州螺纹(实录)</th>
        <th>跨区卷螺差(沪-杭)</th>
        <th>Wind本地卷螺差</th>
        <th>杭州螺纹库存</th>
        <th>杭州出库量</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>2026-08-17 (峰值)</strong></td>
        <td>3,290 元/吨</td>
        <td>3,010 元/吨</td>
        <td class="highlight-cell">+280 元/吨</td>
        <td>+170 元/吨</td>
        <td>113.8 万吨</td>
        <td>4.8 万吨/日</td>
      </tr>
      <tr>
        <td><strong>2026-08-31 (高点)</strong></td>
        <td>3,400 元/吨</td>
        <td>3,160 元/吨</td>
        <td>+240 元/吨</td>
        <td>+110 元/吨</td>
        <td>110.5 万吨</td>
        <td>5.2 万吨/日</td>
      </tr>
      <tr>
        <td><strong>2026-09-10</strong></td>
        <td>3,370 元/吨</td>
        <td>3,150 元/吨</td>
        <td>+220 元/吨</td>
        <td>+80 元/吨</td>
        <td>105.9 万吨</td>
        <td>3.6 万吨/日</td>
      </tr>
      <tr>
        <td><strong>2026-09-18</strong></td>
        <td>3,310 元/吨</td>
        <td>3,130 元/吨</td>
        <td>+180 元/吨</td>
        <td>+40 元/吨</td>
        <td>93.3 万吨</td>
        <td>3.5 万吨/日</td>
      </tr>
      <tr>
        <td><strong>2026-09-22</strong></td>
        <td>3,310 元/吨</td>
        <td>3,160 元/吨</td>
        <td>+150 元/吨</td>
        <td>+20 元/吨</td>
        <td>85.5 万吨</td>
        <td>4.4 万吨/日</td>
      </tr>
      <tr style="background-color: #fef2f2;">
        <td><strong>2026-09-23 (最新)</strong></td>
        <td><strong class="num-bold">3,310 元/吨</strong></td>
        <td><strong class="num-bold">3,160 元/吨</strong></td>
        <td><strong class="highlight-cell">+150 元/吨</strong></td>
        <td><strong>+20 元/吨</strong></td>
        <td><strong class="num-bold">82.8 万吨</strong></td>
        <td>4.4 万吨(22日)</td>
      </tr>
    </tbody>
  </table>

  <ul class="fact-list">
    <li><span class="badge">跨区卷螺差收窄事实:</span> 上海热卷与杭州螺纹跨区现货价差在 2026年8月17日 达到峰值 <span class="num-bold">+280 元/吨</span>，截至 9月23日 收窄至 <span class="num-bold">+150 元/吨</span>，区间收窄幅度达 <span class="highlight-cell">130 元/吨 (-46.4%)</span>。</li>
    <li><span class="badge">现货绝对价格变动:</span> 上海热卷现货价格在 8月31日 达到阶段高点 3,400 元/吨，随后回落至 3,310 元/吨，较8月末回落 <span class="num-bold">90 元/吨</span>；同期杭州螺纹现货由 8月17日的 3,010 元/吨上涨并维持在 3,160 元/吨，区间上涨 <span class="num-bold">150 元/吨</span>。</li>
    <li><span class="badge">Wind同城数据趋势验证:</span> Wind 数据库记录的上海热卷现货同期由 3,480 元/吨降至 3,330 元/吨，上海螺纹现货维持在 3,310 元/吨附近，同城卷螺差由 <span class="num-bold">+170 元/吨</span> 收敛至最新 <span class="num-bold">+20 元/吨</span>，与跨区价差走势同向印证。</li>
    <li><span class="badge">杭州螺纹库存去化事实:</span> 杭州螺纹现货库存从 8月17日的 <span class="num-bold">113.8 万吨</span> 持续降至 9月23日的 <span class="num-bold">82.8 万吨</span>，区间连续去化 <span class="num-bold">31.0 万吨 (降幅 -27.2%)</span>，单日出库量保持在 3.5~7.8 万吨区间。</li>
  </ul>
</div>

<!-- ==================== 第 2 页: 期货盘面走势与仓单客观数量变动事实 ==================== -->
<div class="page-container">
  <h2>2. 期货盘面走势与仓单客观数量变动事实</h2>
  
  <div class="chart-box">
    <img src="file://{fig2_path}" style="max-height: 94mm;" alt="期货走势与仓单客观变动图">
  </div>

  <table class="data-table">
    <thead>
      <tr>
        <th>统计基准日期</th>
        <th>热卷期货主力(HC)</th>
        <th>螺纹期货主力(RB)</th>
        <th>盘面主力卷螺差</th>
        <th>热卷期货仓单(万吨)</th>
        <th>螺纹期货仓单(万吨)</th>
        <th>SMM三城现货成交</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>2026-08-17 (价差高点)</strong></td>
        <td>3,478 元/吨</td>
        <td>3,209 元/吨</td>
        <td class="highlight-cell">+269 元/吨</td>
        <td>23.80 万吨</td>
        <td>6.85 万吨</td>
        <td>12,450 吨/日</td>
      </tr>
      <tr>
        <td><strong>2026-08-31 (成交高点)</strong></td>
        <td>3,450 元/吨</td>
        <td>3,215 元/吨</td>
        <td>+235 元/吨</td>
        <td>22.45 万吨</td>
        <td>7.12 万吨</td>
        <td>13,810 吨/日</td>
      </tr>
      <tr>
        <td><strong>2026-09-14 (成交低点)</strong></td>
        <td>3,325 元/吨</td>
        <td>3,120 元/吨</td>
        <td>+205 元/吨</td>
        <td>22.13 万吨</td>
        <td>8.67 万吨</td>
        <td>9,950 吨/日</td>
      </tr>
      <tr>
        <td><strong>2026-09-17</strong></td>
        <td>3,317 元/吨</td>
        <td>3,122 元/吨</td>
        <td>+195 元/吨</td>
        <td>22.01 万吨</td>
        <td>9.19 万吨</td>
        <td>10,880 吨/日</td>
      </tr>
      <tr>
        <td><strong>2026-09-18</strong></td>
        <td>3,290 元/吨</td>
        <td>3,095 元/吨</td>
        <td>+195 元/吨</td>
        <td>18.23 万吨</td>
        <td>7.43 万吨</td>
        <td>10,400 吨/日</td>
      </tr>
      <tr style="background-color: #fef2f2;">
        <td><strong>2026-09-23 (最新)</strong></td>
        <td><strong class="num-bold">3,301 元/吨</strong></td>
        <td><strong class="num-bold">3,113 元/吨</strong></td>
        <td><strong class="highlight-cell">+188 元/吨</strong></td>
        <td><strong class="num-bold">18.47 万吨</strong></td>
        <td><strong class="num-bold">7.34 万吨</strong></td>
        <td>11,400 吨(16日)</td>
      </tr>
    </tbody>
  </table>

  <ul class="fact-list">
    <li><span class="badge">期货盘面卷螺差变动:</span> 热卷主力合约(HC2701)与螺纹主力合约(RB2701)的收盘价差自 8月17日 的 <span class="num-bold">+269 元/吨</span> 回落至 9月23日 的 <span class="num-bold">+188 元/吨</span>，区间收窄 <span class="highlight-cell">81 元/吨 (-30.1%)</span>。</li>
    <li><span class="badge">热卷仓单客观数据变动:</span> 2026年4月27日 热卷期货注册仓单达到年度极值 <span class="num-bold">62.70 万吨</span>。8月初仓单位于 27.75 万吨，8月中旬为 23.80 万吨，9月17日为 22.01 万吨。9月18日仓单降至 18.23 万吨，9月23日最新为 <span class="num-bold">18.47 万吨</span>，较4月高点减少 <span class="num-bold">44.23 万吨</span>，较8月初减少 <span class="num-bold">9.28 万吨</span>。</li>
    <li><span class="badge">螺纹仓单客观数据变动:</span> 螺纹期货注册仓单在 9月17日 达到阶段高位 <span class="num-bold">9.19 万吨</span>，9月18日回落至 7.43 万吨，9月23日最新为 <span class="num-bold">7.34 万吨</span>。</li>
    <li><span class="badge">热卷仓单历史均值参考:</span> 热卷期货自身历史统计显示，2024年全年热卷注册仓单均值为 <span class="num-bold">29.1 万吨</span>，2025年同期均值为 <span class="num-bold">18.5 万吨</span>。</li>
    <li><span class="badge">SMM现货成交量变动:</span> SMM 每日三城（上海、乐从、天津）热卷现货成交总量在 8月31日 达到 <span class="num-bold">13,810 吨/日</span>，9月14日 跌破万吨至 <span class="num-bold">9,950 吨/日</span>，随后在 10,000~11,400 吨/日区间波动。</li>
  </ul>
</div>

<!-- ==================== 第 3 页: 需求端、钢厂排产接单与出口发运事实 (一个页面宽度放2张图) ==================== -->
<div class="page-container">
  <h2>3. 制造业耗钢、钢厂排产接单与出口外贸发运客观事实</h2>
  
  <div class="chart-box">
    <img src="file://{fig3_path}" style="max-height: 86mm;" alt="制造业需求与出口发运2x2展示">
  </div>

  <table class="data-table" style="font-size: 8.5pt;">
    <thead>
      <tr>
        <th>板块 / 统计口径</th>
        <th>6月度数据</th>
        <th>7月度数据</th>
        <th>8月实际/预测</th>
        <th>9月计划量</th>
        <th>客观变动情况</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>机械行业耗钢量</strong></td>
        <td>15.66 百万吨</td>
        <td>14.72 百万吨</td>
        <td>14.79 百万吨</td>
        <td>-</td>
        <td>7-8月月均稳定在 14.7~14.8 百万吨</td>
      </tr>
      <tr>
        <td><strong>汽车行业耗钢量</strong></td>
        <td>4.87 百万吨</td>
        <td>4.39 百万吨</td>
        <td>4.70 百万吨</td>
        <td>-</td>
        <td>8月较7月环比增加 0.31 百万吨</td>
      </tr>
      <tr>
        <td><strong>家电行业耗钢量</strong></td>
        <td>1.89 百万吨</td>
        <td>1.54 百万吨</td>
        <td>1.54 百万吨</td>
        <td>-</td>
        <td class="highlight-cell">较5-6月高点减少 0.38 百万吨/月</td>
      </tr>
      <tr>
        <td><strong>39家钢厂热卷总排产</strong></td>
        <td>1,326.8 万吨</td>
        <td>1,344.6 万吨</td>
        <td>1,344.6 万吨</td>
        <td>1,308.6 万吨</td>
        <td class="highlight-cell">9月计划排产环比减少 36.0 万吨 (-2.68%)</td>
      </tr>
      <tr>
        <td><strong>39家钢厂热卷出口计划</strong></td>
        <td>103.0 万吨</td>
        <td>105.9 万吨</td>
        <td>105.9 万吨</td>
        <td>102.3 万吨</td>
        <td>9月出口计划环比减少 3.6 万吨 (-3.40%)</td>
      </tr>
      <tr>
        <td><strong>26家重点钢厂商品卷排产</strong></td>
        <td>-</td>
        <td>925.0 万吨</td>
        <td>930.5 万吨</td>
        <td>905.7 万吨</td>
        <td>9月排产环比减少 24.8 万吨 (-2.67%)</td>
      </tr>
    </tbody>
  </table>

  <ul class="fact-list">
    <li><span class="badge">下游制造业耗钢分化事实:</span> SMM 行业耗钢监测显示，机械行业月耗钢 14.72~14.79 百万吨保持平稳；家电行业耗钢量由 5-6月的 1.92 百万吨降至 7-8月的 <span class="num-bold">1.54 百万吨</span>，月均减少 <span class="highlight-cell">38 万吨 (-19.8%)</span>。</li>
    <li><span class="badge">重点钢厂主动调减排产事实:</span> SMM 39家热卷样本钢厂 8月实际总排产为 1,344.60 万吨，9月计划排产为 <span class="num-bold">1,308.60 万吨</span>，环比减少 <span class="highlight-cell">36.00 万吨 (-2.68%)</span>；计划出口量由 105.90 万吨调减至 <span class="num-bold">102.30 万吨 (-3.40%)</span>。26家重点钢厂9月商品卷排产同样由 930.50 万吨下调至 <span class="num-bold">905.70 万吨 (-2.67%)</span>。</li>
    <li><span class="badge">天津港 FOB 理论价差测算事实:</span> 截至 9月23日，天津港热卷 FOB 报价为 <span class="num-bold">497.0 美元/吨</span>，按汇率 7.11 折算人民币含税价约为 <span class="num-bold">3,534 元/吨</span>。对比上海热卷现货 3,310 元/吨，理论内外直接价差为 <span class="num-bold">+224 元/吨</span>；扣除 80 元港杂运费后，理论出口利润为 <span class="num-bold">+144 元/吨</span>。</li>
    <li><span class="badge">32港钢卷出港周度发运腰斩事实:</span> 沸腾环贸 32 港统计显示，全国钢卷出港周度发运量在 9月4日当周 达到阶段高点 <span class="num-bold">45.72 万吨/周</span>，9月11日当周 降至 32.15 万吨/周，9月18日当周 降至 <span class="num-bold">24.83 万吨/周</span>，两周内变动 <span class="highlight-cell">-20.89 万吨/周 (降幅 -45.70%)</span>。</li>
  </ul>
</div>

<!-- ==================== 第 4 页: 全景数据事实总览表与客观事实摘要 ==================== -->
<div class="page-container">
  <h2>4. 全景数据事实对照总览表与客观事实摘要</h2>

  <table class="data-table" style="font-size: 8.0pt;">
    <thead>
      <tr style="background-color: #e2e8f0;">
        <th>统计监测维度</th>
        <th>8月17日(价差峰值)</th>
        <th>8月31日(价格峰值)</th>
        <th>9月10日</th>
        <th>9月18日</th>
        <th>9月22日</th>
        <th style="background-color: #fee2e2;">9月23日(最新值)</th>
        <th>区间变动量 / 趋势</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>上海热卷现货(实录)</strong></td>
        <td>3,290 元/吨</td>
        <td>3,400 元/吨</td>
        <td>3,370 元/吨</td>
        <td>3,310 元/吨</td>
        <td>3,310 元/吨</td>
        <td class="highlight-cell">3,310 元/吨</td>
        <td>较8月末高点 -90 元/吨</td>
      </tr>
      <tr>
        <td><strong>杭州螺纹现货(实录)</strong></td>
        <td>3,010 元/吨</td>
        <td>3,160 元/吨</td>
        <td>3,150 元/吨</td>
        <td>3,130 元/吨</td>
        <td>3,160 元/吨</td>
        <td class="highlight-cell">3,160 元/吨</td>
        <td>较8月17日 +150 元/吨</td>
      </tr>
      <tr style="background-color: #fef2f2;">
        <td><strong>跨区卷螺差 (沪卷 - 杭螺)</strong></td>
        <td><strong>+280 元/吨</strong></td>
        <td>+240 元/吨</td>
        <td>+220 元/吨</td>
        <td>+180 元/吨</td>
        <td>+150 元/吨</td>
        <td><strong class="highlight-cell">+150 元/吨</strong></td>
        <td><strong>大幅收窄 130 元/吨 (-46.4%)</strong></td>
      </tr>
      <tr>
        <td><strong>Wind上海卷螺差 (验证)</strong></td>
        <td>+170 元/吨</td>
        <td>+110 元/吨</td>
        <td>+80 元/吨</td>
        <td>+40 元/吨</td>
        <td>+20 元/吨</td>
        <td>+20 元/吨</td>
        <td>收敛 150 元/吨 (同向印证)</td>
      </tr>
      <tr>
        <td><strong>杭州螺纹库存</strong></td>
        <td>113.8 万吨</td>
        <td>110.5 万吨</td>
        <td>105.9 万吨</td>
        <td>93.3 万吨</td>
        <td>85.5 万吨</td>
        <td class="highlight-cell">82.8 万吨</td>
        <td>持续去化 31.0 万吨 (-27.2%)</td>
      </tr>
      <tr>
        <td><strong>热卷主力期货(HC)</strong></td>
        <td>3,478 元/吨</td>
        <td>3,450 元/吨</td>
        <td>3,380 元/吨</td>
        <td>3,290 元/吨</td>
        <td>3,299 元/吨</td>
        <td>3,301 元/吨</td>
        <td>较8月中旬 -177 元/吨</td>
      </tr>
      <tr>
        <td><strong>螺纹主力期货(RB)</strong></td>
        <td>3,209 元/吨</td>
        <td>3,215 元/吨</td>
        <td>3,160 元/吨</td>
        <td>3,095 元/吨</td>
        <td>3,114 元/吨</td>
        <td>3,113 元/吨</td>
        <td>较8月中旬 -96 元/吨</td>
      </tr>
      <tr style="background-color: #fef2f2;">
        <td><strong>盘面卷螺差 (HC - RB)</strong></td>
        <td><strong>+269 元/吨</strong></td>
        <td>+235 元/吨</td>
        <td>+220 元/吨</td>
        <td>+195 元/吨</td>
        <td>+185 元/吨</td>
        <td><strong class="highlight-cell">+188 元/吨</strong></td>
        <td><strong>收窄 81 元/吨 (-30.1%)</strong></td>
      </tr>
      <tr>
        <td><strong>热卷期货注册仓单</strong></td>
        <td>23.80 万吨</td>
        <td>22.45 万吨</td>
        <td>21.36 万吨</td>
        <td>18.23 万吨</td>
        <td>18.47 万吨</td>
        <td class="highlight-cell">18.47 万吨</td>
        <td>较4月极值 62.70万吨 -44.23万吨</td>
      </tr>
      <tr>
        <td><strong>螺纹期货注册仓单</strong></td>
        <td>6.85 万吨</td>
        <td>7.12 万吨</td>
        <td>7.81 万吨</td>
        <td>7.43 万吨</td>
        <td>7.34 万吨</td>
        <td>7.34 万吨</td>
        <td>9月中旬曾升至 9.19 万吨</td>
      </tr>
      <tr>
        <td><strong>SMM三城热卷成交量</strong></td>
        <td>12,450 吨/日</td>
        <td>13,810 吨/日</td>
        <td>11,650 吨/日</td>
        <td>10,400 吨/日</td>
        <td>10,200 吨/日</td>
        <td>11,400 吨(16日)</td>
        <td>9月中旬曾跌至 9,950 吨/日</td>
      </tr>
      <tr>
        <td><strong>39家钢厂月度热卷排产</strong></td>
        <td>1,344.6 万吨</td>
        <td>1,344.6 万吨</td>
        <td>1,308.6 万吨</td>
        <td>1,308.6 万吨</td>
        <td>1,308.6 万吨</td>
        <td>1,308.6 万吨</td>
        <td>9月计划减产 36.0 万吨</td>
      </tr>
      <tr>
        <td><strong>天津港FOB折算价差</strong></td>
        <td>+185 元/吨</td>
        <td>+125 元/吨</td>
        <td>+155 元/吨</td>
        <td>+215 元/吨</td>
        <td>+224 元/吨</td>
        <td>+224 元/吨</td>
        <td>理论出口利润维持在 +144 元/吨</td>
      </tr>
      <tr>
        <td><strong>32港钢卷出港周发运量</strong></td>
        <td>38.60 万吨</td>
        <td>41.20 万吨</td>
        <td>45.72 万吨(9/4)</td>
        <td>24.83 万吨(9/18)</td>
        <td>24.83 万吨</td>
        <td class="highlight-cell">24.83 万吨</td>
        <td>两周自 45.72万吨腰斩 -45.70%</td>
      </tr>
    </tbody>
  </table>

  <h2>5. 客观事实变动要点归纳</h2>
  <ul class="fact-list" style="font-size: 9.2pt;">
    <li><strong>现货价格与跨区价差:</strong> 上海热卷与杭州螺纹跨区价差由 8月17日 的 <span class="highlight-cell">+280 元/吨</span> 单边收窄至 9月23日 的 <span class="highlight-cell">+150 元/吨</span>，收窄幅度为 130 元/吨。杭州螺纹现货价格自 3,010 元/吨上涨至 3,160 元/吨，杭州螺纹库存自 113.8 万吨降至 82.8 万吨（减少 31.0 万吨，降幅 -27.2%）。</li>
    <li><strong>期货盘面与注册仓单:</strong> 盘面主力卷螺差自 8月17日 的 +269 元/吨收窄至 9月23日 的 +188 元/吨。热卷期货注册仓单在 2026年4月27日 达到 62.70 万吨年度高位，9月23日 降至 18.47 万吨（较高点减少 44.23 万吨，较8月初减少 9.28 万吨）；螺纹仓单最新为 7.34 万吨。</li>
    <li><strong>微观成交与钢厂排产:</strong> SMM 每日三城成交总量自 8月底的 13,810 吨/日滑落，9月中旬曾跌至 9,950 吨/日；SMM 39家热卷样本钢厂 9月计划总排产环比减少 36.00 万吨至 1,308.60 万吨，计划出口量调减 3.60 万吨至 102.30 万吨。</li>
    <li><strong>出口折算与外贸发运:</strong> 天津港 FOB 理论折算价为 3,534 元/吨，高于国内上海热卷现货 224 元/吨，理论出口利润测算为 +144 元/吨；但沸腾环贸 32 港统计显示，全国钢卷出港周度发运量自 9月4日当周 的 45.72 万吨/周降至 9月18日 的 24.83 万吨/周，两周降幅达 -45.70%。</li>
  </ul>
</div>

</body>
</html>
"""

print("[1/3] 正在生成 PDF 报告并验证格式与排版...")
html_obj = weasyprint.HTML(string=html_content)
html_obj.write_pdf(PDF_OUTPUT_PROJECT)
shutil.copyfile(PDF_OUTPUT_PROJECT, PDF_OUTPUT_ARTIFACT)
print(f"[2/3] PDF 生成成功: {PDF_OUTPUT_PROJECT}")
print(f"[3/3] 已同步复制到 Artifact 路径: {PDF_OUTPUT_ARTIFACT}")
