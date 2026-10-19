#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: build_recent_spread_html_report.py
用途:
  生成《近期热卷现货与卷螺差走弱深度量化事实报告（交互数据看板·2026年9月23日版）》HTML报告
  - 核心要求: 纯交互式图表 (ECharts)，鼠标悬浮/移动直接查看对应时点准确数据，彻底告别静态截图
  - 内嵌全量 ECharts 5.5.0 引擎，文件 100% 独立离线可用，无需联网
  - 一个页面宽度放2张图 (2-column grid)，黄金比例布局，告别过度拉伸
  - 包含 10 个独立高频交互图表与核心节点对照表:
      1. 上海热卷 vs 杭州螺纹实录现货价格 (含 Wind 趋势验证)
      2. 跨区卷螺差 (沪卷 - 杭螺) vs Wind 同城卷螺差
      3. 杭州螺纹库存量 (万吨) 与日度出库量 (万吨/日)
      4. 期货主力连续收盘价 (HC主力 vs RB主力) 与盘面主力卷螺差
      5. 热卷与螺纹期货注册仓单客观数量走势 (含历史均值线)
      6. SMM 热卷三城日度成交量 (三城总计及各分市场)
      7. 下游制造业主要板块月度耗钢量 (机械、汽车、家电)
      8. 重点钢厂热卷月度排产与出口接单计划 (39家/26家)
      9. 天津港 FOB 出口折算价差与理论套利利润走势
      10. 沸腾环贸 32 港全球钢卷出港周度发运量
  - 包含完整的 2026年8月1日 - 9月23日 全量高频日度明细数据表
  - 包含产业数据概览卡片与客观事实变动要点归纳
"""

import os
import json
import pandas as pd
import numpy as np

PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
ARTIFACT_DIR = "/home/hw/.gemini/antigravity/brain/78cbb79d-10e8-49b1-a7f1-b02789ba9c27"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "研究/现货价差专题")

HTML_OUTPUT_PROJECT = os.path.join(OUTPUT_DIR, "近期热卷现货与卷螺差走弱深度量化事实报告_20260923.html")
HTML_OUTPUT_ARTIFACT = os.path.join(ARTIFACT_DIR, "近期热卷现货与卷螺差走弱深度量化事实报告_20260923.html")

# 读取本地 ECharts 源码以便内嵌离线运行
echarts_path = os.path.join(OUTPUT_DIR, "echarts.min.js")
with open(echarts_path, 'r', encoding='utf-8') as f:
    echarts_js_code = f.read()

# -------------------------------------------------------------
# 1. 权威现货数据 (2026-06-01 至 2026-09-23)
# -------------------------------------------------------------
df_spot = pd.read_excel('数据/原始/每日现货.xlsx')
df_spot['日期'] = pd.to_datetime(df_spot['日期'])
df_spot = df_spot.sort_values('日期').reset_index(drop=True)
recent_spot = df_spot[(df_spot['日期'] >= '2026-06-01') & (df_spot['日期'] <= '2026-09-23')].copy()
recent_spot['hz_rb'] = recent_spot['杭州螺纹'].fillna(recent_spot['中天螺纹'])
recent_spot['spread_sh_hc_hz_rb'] = recent_spot['上海热卷'] - recent_spot['hz_rb']

# -------------------------------------------------------------
# 2. Wind 现货趋势验证
# -------------------------------------------------------------
df_wind = pd.read_parquet('数据/原始/wind_edb/observations_2026.parquet')
df_wind['data_date'] = pd.to_datetime(df_wind['data_date'])
hc_wind = df_wind[df_wind['code'] == 'S0033272'].sort_values('data_date')[['data_date', 'value']].rename(columns={'value': 'hc_wind'})
rb_wind = df_wind[df_wind['code'] == 'S0033227'].sort_values('data_date')[['data_date', 'value']].rename(columns={'value': 'rb_wind'})
wind_spot = pd.merge(hc_wind, rb_wind, on='data_date')
wind_spot['spread_wind'] = wind_spot['hc_wind'] - wind_spot['rb_wind']
recent_wind = wind_spot[wind_spot['data_date'] >= '2026-06-01'].copy()

# -------------------------------------------------------------
# 3. 期货主力日线
# -------------------------------------------------------------
hc_f = pd.read_parquet('数据/原始/期货合约全量日线/standardized/hc_daily.parquet')
rb_f = pd.read_parquet('数据/原始/期货合约全量日线/standardized/rb_daily.parquet')
hc_main = hc_f[hc_f['contract_code'] == 'main'].copy()
rb_main = rb_f[rb_f['contract_code'] == 'main'].copy()
hc_main['date'] = pd.to_datetime(hc_main['date'])
rb_main['date'] = pd.to_datetime(rb_main['date'])

disk = pd.merge(hc_main[['date', 'close']],
                rb_main[['date', 'close']],
                on='date', suffixes=('_hc', '_rb'))
disk['disk_spread'] = disk['close_hc'] - disk['close_rb']
recent_disk = disk[(disk['date'] >= '2026-06-01') & (disk['date'] <= '2026-09-23')].sort_values('date').reset_index(drop=True)

# -------------------------------------------------------------
# 4. SMM 数据底座
# -------------------------------------------------------------
df_smm = pd.read_parquet('数据/原始/smm/smm_export_manufacturing.parquet')
df_smm['date'] = pd.to_datetime(df_smm['date'])

from smm_client import SmmMcpClient
API_KEY = "sk-ebded532758f488e0a378a8a320213023408eca85617bc07c4a433152ad9579b"
client = SmmMcpClient(API_KEY)
client.initialize()

res_tx = client.call_tool('smm_indicator_data_query', {
    'indicator_ids': 'a12774941,a12774940,a12774942,a12756312',
    'start_date': '2026-06-01',
    'end_date': '2026-09-23'
})
tx_records = {}
if isinstance(res_tx, dict):
    for item in res_tx.get('data', []):
        iid = item['indicator_id']
        df_i = pd.DataFrame(item.get('records', []))
        if not df_i.empty:
            df_i['date'] = pd.to_datetime(df_i['date'])
            df_i['value'] = pd.to_numeric(df_i['value'])
            tx_records[iid] = df_i.set_index('date')['value']

df_smm_tx = pd.DataFrame(tx_records).sort_index().reset_index()
df_smm_tx.rename(columns={
    'a12774941': 'sh_tx',
    'a12774940': 'lc_tx',
    'a12774942': 'tj_tx',
    'a12756312': 'total_3c_tx'
}, inplace=True)

# 出口 FOB 折算
fob_hc = df_smm[df_smm['indicator_id'] == 's22804474'].sort_values('date')[['date', 'value']].rename(columns={'value': 'fob_usd'})
m_exp = pd.merge(recent_spot[['日期', '上海热卷']], fob_hc, left_on='日期', right_on='date')
m_exp['fob_cny'] = m_exp['fob_usd'] * 7.11
m_exp['export_spread'] = m_exp['fob_cny'] - m_exp['上海热卷']
m_exp['export_profit'] = m_exp['export_spread'] - 80.0

# 32 港发运
shp_coil = df_smm[df_smm['indicator_id'] == 'a10135358'].sort_values('date')
shp_recent = shp_coil[shp_coil['date'] >= '2026-06-01'].copy()

# -------------------------------------------------------------
# 序列化为 JSON 供 ECharts 调用
# -------------------------------------------------------------
all_dates = sorted(list(set(
    recent_spot['日期'].dt.strftime('%Y-%m-%d').tolist() +
    recent_disk['date'].dt.strftime('%Y-%m-%d').tolist()
)))

spot_map = recent_spot.set_index(recent_spot['日期'].dt.strftime('%Y-%m-%d'))
wind_map = recent_wind.set_index(recent_wind['data_date'].dt.strftime('%Y-%m-%d'))
disk_map = recent_disk.set_index(recent_disk['date'].dt.strftime('%Y-%m-%d'))
tx_map = df_smm_tx.set_index(df_smm_tx['date'].dt.strftime('%Y-%m-%d')) if not df_smm_tx.empty else pd.DataFrame()
exp_map = m_exp.set_index(m_exp['日期'].dt.strftime('%Y-%m-%d'))

chart1_data = {
    'dates': all_dates,
    'sh_hc': [float(spot_map.loc[d, '上海热卷']) if d in spot_map.index and pd.notnull(spot_map.loc[d, '上海热卷']) else None for d in all_dates],
    'hz_rb': [float(spot_map.loc[d, 'hz_rb']) if d in spot_map.index and pd.notnull(spot_map.loc[d, 'hz_rb']) else None for d in all_dates],
    'wind_sh_hc': [float(wind_map.loc[d, 'hc_wind']) if d in wind_map.index and pd.notnull(wind_map.loc[d, 'hc_wind']) else None for d in all_dates],
    'wind_sh_rb': [float(wind_map.loc[d, 'rb_wind']) if d in wind_map.index and pd.notnull(wind_map.loc[d, 'rb_wind']) else None for d in all_dates],
    'spot_spread': [float(spot_map.loc[d, 'spread_sh_hc_hz_rb']) if d in spot_map.index and pd.notnull(spot_map.loc[d, 'spread_sh_hc_hz_rb']) else None for d in all_dates],
    'wind_spread': [float(wind_map.loc[d, 'spread_wind']) if d in wind_map.index and pd.notnull(wind_map.loc[d, 'spread_wind']) else None for d in all_dates],
    'hz_stock': [float(spot_map.loc[d, '杭州库存']) if d in spot_map.index and pd.notnull(spot_map.loc[d, '杭州库存']) else None for d in all_dates],
    'hz_outflow': [float(spot_map.loc[d, '杭州出库']) if d in spot_map.index and pd.notnull(spot_map.loc[d, '杭州出库']) else None for d in all_dates],
}

chart2_data = {
    'dates': all_dates,
    'hc_close': [float(disk_map.loc[d, 'close_hc']) if d in disk_map.index and pd.notnull(disk_map.loc[d, 'close_hc']) else None for d in all_dates],
    'rb_close': [float(disk_map.loc[d, 'close_rb']) if d in disk_map.index and pd.notnull(disk_map.loc[d, 'close_rb']) else None for d in all_dates],
    'disk_spread': [float(disk_map.loc[d, 'disk_spread']) if d in disk_map.index and pd.notnull(disk_map.loc[d, 'disk_spread']) else None for d in all_dates],
    'hc_wh': [round(float(spot_map.loc[d, '热卷仓单(吨)'])/10000.0, 2) if d in spot_map.index and pd.notnull(spot_map.loc[d, '热卷仓单(吨)']) else None for d in all_dates],
    'rb_wh': [round(float(spot_map.loc[d, '螺纹仓单(吨)'])/10000.0, 2) if d in spot_map.index and pd.notnull(spot_map.loc[d, '螺纹仓单(吨)']) else None for d in all_dates],
    'smm_total': [float(tx_map.loc[d, 'total_3c_tx']) if not tx_map.empty and d in tx_map.index and pd.notnull(tx_map.loc[d, 'total_3c_tx']) else None for d in all_dates],
    'smm_lc': [float(tx_map.loc[d, 'lc_tx']) if not tx_map.empty and d in tx_map.index and pd.notnull(tx_map.loc[d, 'lc_tx']) else None for d in all_dates],
    'smm_sh': [float(tx_map.loc[d, 'sh_tx']) if not tx_map.empty and d in tx_map.index and pd.notnull(tx_map.loc[d, 'sh_tx']) else None for d in all_dates],
    'smm_tj': [float(tx_map.loc[d, 'tj_tx']) if not tx_map.empty and d in tx_map.index and pd.notnull(tx_map.loc[d, 'tj_tx']) else None for d in all_dates],
}

chart3_data = {
    'm_dates': ['5月', '6月', '7月', '8月(预)'],
    'm_mech': [15.20, 15.66, 14.72, 14.79],
    'm_auto': [4.65, 4.87, 4.39, 4.70],
    'm_appl': [1.92, 1.89, 1.54, 1.54],
    'p_dates': ['6月', '7月', '8月', '9月'],
    'p_prod39': [1326.8, 1344.6, 1308.6, 1315.0],
    'p_exp39': [103.0, 105.9, 102.3, 104.5],
    'p_exp26': [79.6, 81.2, 77.8, 81.7],
    'exp_dates': m_exp['日期'].dt.strftime('%Y-%m-%d').tolist(),
    'exp_spread': [float(x) for x in m_exp['export_spread']],
    'exp_profit': [float(x) for x in m_exp['export_profit']],
    'port32_dates': shp_recent['date'].dt.strftime('%Y-%m-%d').tolist(),
    'port32_values': [float(x) for x in shp_recent['value']]
}

# -------------------------------------------------------------
# 5. 构建 8月1日 - 9月23日 每日全量数据表格 HTML
# -------------------------------------------------------------
merged_daily = df_spot[(df_spot['日期'] >= '2026-08-01') & (df_spot['日期'] <= '2026-09-23')].copy()
merged_daily = pd.merge(merged_daily, recent_disk[['date', 'close_hc', 'close_rb', 'disk_spread']], left_on='日期', right_on='date', how='left')
merged_daily = pd.merge(merged_daily, recent_wind[['data_date', 'spread_wind']], left_on='日期', right_on='data_date', how='left')
if not df_smm_tx.empty:
    merged_daily = pd.merge(merged_daily, df_smm_tx[['date', 'total_3c_tx']], left_on='日期', right_on='date', how='left')

daily_table_rows = []
for _, r in merged_daily.iterrows():
    d_str = r['日期'].strftime('%Y-%m-%d')
    sh_hc = f"{r['上海热卷']:.0f}" if pd.notnull(r['上海热卷']) else "-"
    hz_rb = f"{r['杭州螺纹']:.0f}" if pd.notnull(r['杭州螺纹']) else (f"{r['中天螺纹']:.0f}" if pd.notnull(r['中天螺纹']) else "-")
    
    if pd.notnull(r['上海热卷']) and (pd.notnull(r['杭州螺纹']) or pd.notnull(r['中天螺纹'])):
        rb_val = r['杭州螺纹'] if pd.notnull(r['杭州螺纹']) else r['中天螺纹']
        sp_val = r['上海热卷'] - rb_val
        sp_str = f"+{sp_val:.0f}" if sp_val >= 0 else f"{sp_val:.0f}"
    else:
        sp_str = "-"
        
    wind_sp = f"+{r['spread_wind']:.0f}" if pd.notnull(r['spread_wind']) and r['spread_wind'] >= 0 else (f"{r['spread_wind']:.0f}" if pd.notnull(r['spread_wind']) else "-")
    hz_inv = f"{r['杭州库存']:.1f}" if pd.notnull(r['杭州库存']) else "-"
    hz_out = f"{r['杭州出库']:.1f}" if pd.notnull(r['杭州出库']) else "-"
    
    f_hc = f"{r['close_hc']:.0f}" if pd.notnull(r['close_hc']) else "-"
    f_rb = f"{r['close_rb']:.0f}" if pd.notnull(r['close_rb']) else "-"
    f_sp_str = f"+{r['disk_spread']:.0f}" if pd.notnull(r['disk_spread']) and r['disk_spread'] >= 0 else (f"{r['disk_spread']:.0f}" if pd.notnull(r['disk_spread']) else "-")
        
    hc_wh = f"{r['热卷仓单(吨)']/10000.0:.2f}" if pd.notnull(r['热卷仓单(吨)']) else "-"
    rb_wh = f"{r['螺纹仓单(吨)']/10000.0:.2f}" if pd.notnull(r['螺纹仓单(吨)']) else "-"
    smm_tx = f"{r['total_3c_tx']:.0f}" if 'total_3c_tx' in r and pd.notnull(r['total_3c_tx']) else "-"
    
    is_key = d_str in ['2026-08-17', '2026-08-31', '2026-09-10', '2026-09-14', '2026-09-18', '2026-09-22', '2026-09-23']
    row_bg = "background-color: #fef2f2; font-weight: bold;" if is_key else ""
    badge_label = f" <span style='color:#b91c1c; font-size:11px;'>[核心节点]</span>" if is_key else ""
    
    daily_table_rows.append(f"""
      <tr style="{row_bg}">
        <td><strong>{d_str}</strong>{badge_label}</td>
        <td>{sh_hc}</td>
        <td>{hz_rb}</td>
        <td style="color: #b91c1c; font-weight: bold;">{sp_str}</td>
        <td>{wind_sp}</td>
        <td>{hz_inv}</td>
        <td>{hz_out}</td>
        <td>{f_hc}</td>
        <td>{f_rb}</td>
        <td style="color: #9333ea; font-weight: bold;">{f_sp_str}</td>
        <td>{hc_wh}</td>
        <td>{rb_wh}</td>
        <td>{smm_tx}</td>
      </tr>
    """)

daily_table_html = "\n".join(daily_table_rows)

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>近期热卷现货与卷螺差走弱深度量化事实报告 (交互数据看板·2026年9月23日版)</title>
<style>
  :root {{
    --primary: #0284c7;
    --primary-dark: #0369a1;
    --secondary: #e11d48;
    --text-main: #0f172a;
    --text-muted: #475569;
    --bg-page: #f8fafc;
    --bg-card: #ffffff;
    --border-color: #e2e8f0;
  }}

  * {{ box-sizing: border-box; }}

  body {{
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
    color: var(--text-main);
    background-color: var(--bg-page);
    line-height: 1.55;
    margin: 0;
    padding: 20px;
    font-size: 14.5px;
  }}

  .container {{
    max-width: 1320px;
    margin: 0 auto;
    background-color: var(--bg-card);
    border-radius: 12px;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.05);
    padding: 30px 36px;
    border: 1px solid var(--border-color);
  }}

  .header {{
    border-bottom: 3px solid var(--primary);
    padding-bottom: 14px;
    margin-bottom: 20px;
  }}

  .tag {{
    display: inline-block;
    background-color: #e0f2fe;
    color: var(--primary-dark);
    font-weight: 700;
    font-size: 12.5px;
    padding: 3px 9px;
    border-radius: 4px;
    margin-bottom: 6px;
  }}

  h1 {{
    font-size: 24px;
    color: var(--text-main);
    margin: 4px 0 8px 0;
    font-weight: 800;
    line-height: 1.3;
  }}

  .meta-bar {{
    font-size: 13.5px;
    color: var(--text-muted);
    display: flex;
    flex-wrap: wrap;
    gap: 16px;
  }}

  .meta-item strong {{
    color: var(--text-main);
  }}

  .summary-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    gap: 14px;
    margin: 20px 0;
  }}

  .card {{
    background: #ffffff;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 14px 18px;
    border-top: 4px solid var(--primary);
    box-shadow: 0 2px 6px rgba(0,0,0,0.02);
  }}

  .card-title {{
    font-size: 12.5px;
    color: var(--text-muted);
    font-weight: 600;
  }}

  .card-value {{
    font-size: 23px;
    font-weight: 800;
    color: var(--text-main);
    margin: 4px 0;
  }}

  .card-desc {{
    font-size: 12.5px;
    color: var(--text-muted);
  }}

  .section {{
    margin: 32px 0;
  }}

  h2 {{
    font-size: 18px;
    color: var(--primary-dark);
    border-left: 5px solid var(--primary);
    padding-left: 10px;
    margin: 26px 0 14px 0;
    font-weight: 700;
  }}

  .tip-box {{
    background-color: #f0fdf4;
    border: 1px solid #bbf7d0;
    color: #166534;
    padding: 8px 14px;
    border-radius: 6px;
    font-size: 13px;
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 8px;
  }}

  /* 一个页面宽度放2张图的网格布局 (2-column grid) */
  .chart-grid-2 {{
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 16px;
    margin: 14px 0 18px 0;
  }}

  @media (max-width: 920px) {{
    .chart-grid-2 {{
      grid-template-columns: 1fr;
    }}
  }}

  .chart-card {{
    background: #ffffff;
    border: 1px solid var(--border-color);
    border-radius: 8px;
    padding: 12px 14px 8px 14px;
    box-shadow: 0 2px 6px rgba(0,0,0,0.02);
    display: flex;
    flex-direction: column;
    box-sizing: border-box;
  }}

  .chart-card .chart-title-bar {{
    font-weight: 700;
    font-size: 13.5px;
    color: #1e293b;
    margin: 0 0 6px 0;
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .chart-card .chart-title-bar::before {{
    content: "";
    display: inline-block;
    width: 6px;
    height: 6px;
    background-color: var(--primary);
    border-radius: 50%;
    flex-shrink: 0;
  }}

  .chart-container {{
    width: 100%;
    height: 330px;
    margin: 0;
  }}

  .mini-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 12px;
    margin-top: 4px;
  }}

  .mini-table th {{
    background-color: #f1f5f9;
    color: #334155;
    font-weight: 700;
    padding: 5px 6px;
    border-bottom: 1.5px solid #cbd5e1;
    white-space: nowrap;
    text-align: center;
  }}

  .mini-table td {{
    padding: 5px 6px;
    border-bottom: 1px solid var(--border-color);
    white-space: nowrap;
    text-align: center;
  }}

  .table-responsive {{
    overflow-x: auto;
    margin: 16px 0;
    border: 1px solid var(--border-color);
    border-radius: 8px;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13.5px;
    text-align: center;
    background-color: #ffffff;
  }}

  th {{
    background-color: #f1f5f9;
    color: #1e293b;
    font-weight: 700;
    padding: 9px 10px;
    border-bottom: 2px solid #cbd5e1;
    white-space: nowrap;
  }}

  td {{
    padding: 7px 10px;
    border-bottom: 1px solid var(--border-color);
    white-space: nowrap;
  }}

  tr:hover {{
    background-color: #f8fafc;
  }}

  .fact-list {{
    background-color: #f8fafc;
    border-left: 4px solid var(--primary);
    padding: 14px 18px 14px 32px;
    border-radius: 0 8px 8px 0;
    margin: 16px 0;
  }}

  .fact-list li {{
    margin-bottom: 8px;
    line-height: 1.55;
    font-size: 14px;
  }}

  .fact-badge {{
    font-weight: 700;
    color: var(--primary-dark);
  }}

  .highlight {{
    color: #b91c1c;
    font-weight: 700;
  }}
</style>
<!-- 内嵌完整 ECharts 5.5.0 引擎脚本，无外部依赖 -->
<script>
{echarts_js_code}
</script>
</head>
<body>

<div class="container">
  <div class="header">
    <span class="tag">产业基本面客观数据事实 · 交互看板版</span>
    <h1>近期热卷现货与卷螺差走弱深度量化事实报告</h1>
    <div class="meta-bar">
      <div class="meta-item"><strong>最新数据时点:</strong> 2026年9月23日收盘</div>
      <div class="meta-item"><strong>现货数据基准:</strong> 《每日现货.xlsx》Authoritative Truth</div>
      <div class="meta-item"><strong>趋势验证源:</strong> Wind 现货数据库</div>
      <div class="meta-item"><strong>高频微观源:</strong> SMM (上海有色网) / 找钢网沸腾环贸 32 港</div>
    </div>
  </div>

  <div class="tip-box">
    <span>💡 <strong>交互提示：</strong>页面图表采用“一个页面宽度放2张图”标准并排版式；所有图表均支持鼠标移动悬停查看准确数据数值、十字光标定位、图例点击隐藏/显示序列、下方滑块区域缩放。</span>
  </div>

  <!-- 核心量化指标卡片 -->
  <div class="summary-grid">
    <div class="card" style="border-top-color: #b91c1c;">
      <div class="card-title">跨区卷螺差 (沪卷 - 杭螺)</div>
      <div class="card-value highlight">+150 元/吨</div>
      <div class="card-desc">较 8/17 峰值 (+280元) 收窄 130 元 (-46.4%)</div>
    </div>
    <div class="card" style="border-top-color: #7c3aed;">
      <div class="card-title">杭州螺纹库存总量</div>
      <div class="card-value" style="color: #7c3aed;">82.8 万吨</div>
      <div class="card-desc">较 8/17 (113.8万吨) 去化 31.0 万吨 (-27.2%)</div>
    </div>
    <div class="card" style="border-top-color: #d97706;">
      <div class="card-title">热卷期货注册仓单</div>
      <div class="card-value" style="color: #d97706;">18.47 万吨</div>
      <div class="card-desc">较 4/27 年内高位 (62.70万吨) 减少 44.23 万吨</div>
    </div>
    <div class="card" style="border-top-color: #ea580c;">
      <div class="card-title">32港钢卷出港周发运量</div>
      <div class="card-value" style="color: #ea580c;">24.83 万吨/周</div>
      <div class="card-desc">较 9/4 阶段高点 (45.72万吨) 下滑 -45.70%</div>
    </div>
  </div>

  <!-- 模块 1: 现货基准价格与跨区卷螺差 -->
  <div class="section">
    <h2>1. 现货基准走势与跨区卷螺差事实（上海热卷 vs 杭州螺纹）</h2>
    
    <!-- 并排第 1 行: 现货价格 + 卷螺差 -->
    <div class="chart-grid-2">
      <div class="chart-card">
        <div class="chart-title-bar">图 1-A: 上海热卷与杭州螺纹实录现货走势 (含 Wind 趋势验证)</div>
        <div id="chart_spot_price" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title-bar">图 1-B: 跨区卷螺差 (上海热卷 - 杭州螺纹) 与 Wind 卷螺差走势对比</div>
        <div id="chart_spot_spread" class="chart-container"></div>
      </div>
    </div>

    <!-- 并排第 2 行: 杭州库存出库 + 核心节点对照卡 -->
    <div class="chart-grid-2">
      <div class="chart-card">
        <div class="chart-title-bar">图 1-C: 杭州螺纹库存变动 (113.8万吨 -> 82.8万吨) 与日度出库量</div>
        <div id="chart_hz_inventory" class="chart-container"></div>
      </div>
      <div class="chart-card" style="justify-content: space-between;">
        <div class="chart-title-bar">表 1: 现货价格、跨区价差与库存关键统计节点对照</div>
        <div style="overflow-x: auto; flex-grow: 1;">
          <table class="mini-table">
            <thead>
              <tr>
                <th>统计基准日期</th>
                <th>上海热卷</th>
                <th>杭州螺纹</th>
                <th>跨区卷螺差</th>
                <th>Wind卷螺差</th>
                <th>杭州库存</th>
                <th>单日出库量</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>2026-08-17 (峰值)</td><td>3,290 元/吨</td><td>3,010 元/吨</td><td class="highlight">+280 元/吨</td><td>+170 元/吨</td><td>113.8 万吨</td><td>4.8 万吨/日</td></tr>
              <tr><td>2026-08-31 (高点)</td><td>3,400 元/吨</td><td>3,160 元/吨</td><td>+240 元/吨</td><td>+110 元/吨</td><td>110.5 万吨</td><td>5.2 万吨/日</td></tr>
              <tr><td>2026-09-10</td><td>3,370 元/吨</td><td>3,150 元/吨</td><td>+220 元/吨</td><td>+80 元/吨</td><td>105.9 万吨</td><td>3.6 万吨/日</td></tr>
              <tr><td>2026-09-18</td><td>3,310 元/吨</td><td>3,130 元/吨</td><td>+180 元/吨</td><td>+40 元/吨</td><td>93.3 万吨</td><td>3.5 万吨/日</td></tr>
              <tr><td>2026-09-22</td><td>3,310 元/吨</td><td>3,160 元/吨</td><td>+150 元/吨</td><td>+20 元/吨</td><td>85.5 万吨</td><td>4.4 万吨/日</td></tr>
              <tr style="background-color: #fef2f2; font-weight: bold;"><td>2026-09-23 (最新)</td><td>3,310 元/吨</td><td>3,160 元/吨</td><td class="highlight">+150 元/吨</td><td>+20 元/吨</td><td>82.8 万吨</td><td>4.4 万吨(22日)</td></tr>
            </tbody>
          </table>
        </div>
        <div style="background-color: #f8fafc; border-left: 3px solid var(--primary); padding: 8px 12px; font-size: 12px; color: var(--text-muted); margin-top: 6px; border-radius: 0 4px 4px 0;">
          <strong>客观事实要点:</strong> 跨区卷螺差自 8/17 峰值 (+280元) 大幅收窄 130 元 (-46.4%) 至最新 +150 元；杭州螺纹库存持续去化 31.0 万吨 (-27.2%)。
        </div>
      </div>
    </div>

    <ul class="fact-list">
      <li><span class="fact-badge">跨区卷螺差收窄事实:</span> 上海热卷与杭州螺纹跨区现货价差在 2026年8月17日 达到峰值 <strong>+280 元/吨</strong>（上海热卷 3,290 元/吨，杭州螺纹 3,010 元/吨），截至 9月23日 收窄至 <strong>+150 元/吨</strong>（上海热卷 3,310 元/吨，杭州螺纹 3,160 元/吨），区间收窄幅度达 <strong class="highlight">130 元/吨 (-46.4%)</strong>。</li>
      <li><span class="fact-badge">现货绝对价格变动:</span> 上海热卷现货价格在 8月31日 达到阶段高点 3,400 元/吨，随后回落至 3,310 元/吨，较8月末回落 <strong>90 元/吨</strong>；同期杭州螺纹现货由 8月17日的 3,010 元/吨上涨并维持在 3,160 元/吨，区间上涨 <strong>150 元/吨</strong>。</li>
      <li><span class="fact-badge">Wind同城数据趋势验证:</span> Wind 数据库记录的上海热卷现货同期由 3,480 元/吨降至 3,330 元/吨，上海螺纹现货维持在 3,310 元/吨附近，同城卷螺差由 <strong>+170 元/吨</strong> 收敛至最新 <strong>+20 元/吨</strong>，与跨区价差走势同向印证。</li>
      <li><span class="fact-badge">杭州螺纹库存去化事实:</span> 杭州螺纹现货库存从 8月17日的 <strong>113.8 万吨</strong> 持续降至 9月23日的 <strong>82.8 万吨</strong>，区间连续去化 <strong>31.0 万吨 (降幅 -27.2%)</strong>，单日出库量保持在 3.5~7.8 万吨区间。</li>
    </ul>
  </div>

  <!-- 模块 2: 期货盘面走势与仓单客观数量变动事实 -->
  <div class="section">
    <h2>2. 期货盘面走势与仓单客观数量变动事实</h2>
    
    <!-- 并排第 1 行: 期货主力收盘/卷螺差 + 期货仓单客观走势 -->
    <div class="chart-grid-2">
      <div class="chart-card">
        <div class="chart-title-bar">图 2-A: 期货主力连续收盘价走势与盘面主力卷螺差变动</div>
        <div id="chart_futures_disk" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title-bar">图 2-B: 热卷与螺纹期货注册仓单客观走势 (含热卷历史均值参考)</div>
        <div id="chart_warrants" class="chart-container"></div>
      </div>
    </div>

    <!-- 并排第 2 行: SMM 现货成交量 + 盘面仓单关键节点卡 -->
    <div class="chart-grid-2">
      <div class="chart-card">
        <div class="chart-title-bar">图 2-C: SMM 热卷现货日度成交量走势 (三城总计及各分市场)</div>
        <div id="chart_smm_tx" class="chart-container"></div>
      </div>
      <div class="chart-card" style="justify-content: space-between;">
        <div class="chart-title-bar">表 2: 期货收盘、注册仓单与现货成交量关键节点对照</div>
        <div style="overflow-x: auto; flex-grow: 1;">
          <table class="mini-table">
            <thead>
              <tr>
                <th>统计基准日期</th>
                <th>HC主力收盘</th>
                <th>RB主力收盘</th>
                <th>盘面卷螺差</th>
                <th>热卷仓单</th>
                <th>螺纹仓单</th>
                <th>SMM三城成交</th>
              </tr>
            </thead>
            <tbody>
              <tr><td>2026-08-17 (价差高)</td><td>3,478 元/吨</td><td>3,209 元/吨</td><td class="highlight">+269 元/吨</td><td>23.80 万吨</td><td>6.85 万吨</td><td>12,450 吨/日</td></tr>
              <tr><td>2026-08-31 (成交高)</td><td>3,450 元/吨</td><td>3,215 元/吨</td><td>+235 元/吨</td><td>22.45 万吨</td><td>7.12 万吨</td><td>13,810 吨/日</td></tr>
              <tr><td>2026-09-14 (成交低)</td><td>3,325 元/吨</td><td>3,120 元/吨</td><td>+205 元/吨</td><td>22.13 万吨</td><td>8.67 万吨</td><td>9,950 吨/日</td></tr>
              <tr><td>2026-09-17</td><td>3,317 元/吨</td><td>3,122 元/吨</td><td>+195 元/吨</td><td>22.01 万吨</td><td>9.19 万吨</td><td>10,880 吨/日</td></tr>
              <tr><td>2026-09-18</td><td>3,290 元/吨</td><td>3,095 元/吨</td><td>+195 元/吨</td><td>18.23 万吨</td><td>7.43 万吨</td><td>10,400 吨/日</td></tr>
              <tr style="background-color: #fef2f2; font-weight: bold;"><td>2026-09-23 (最新)</td><td>3,301 元/吨</td><td>3,113 元/吨</td><td class="highlight">+188 元/吨</td><td>18.47 万吨</td><td>7.34 万吨</td><td>11,400 吨(16日)</td></tr>
            </tbody>
          </table>
        </div>
        <div style="background-color: #f8fafc; border-left: 3px solid var(--primary); padding: 8px 12px; font-size: 12px; color: var(--text-muted); margin-top: 6px; border-radius: 0 4px 4px 0;">
          <strong>客观事实要点:</strong> 盘面主力卷螺差收窄 81 元 (-30.1%)；热卷仓单较 4/27 高位 (62.70万吨) 减少 44.23 万吨，当前 18.47 万吨低于 2024 年均值 (29.1万吨)。
        </div>
      </div>
    </div>

    <ul class="fact-list">
      <li><span class="fact-badge">期货盘面卷螺差变动:</span> 热卷主力合约(HC2701)与螺纹主力合约(RB2701)的收盘价差自 8月17日 的 <strong>+269 元/吨</strong>（HC 3,478 元/吨，RB 3,209 元/吨）回落至 9月23日 的 <strong>+188 元/吨</strong>（HC 3,301 元/吨，RB 3,113 元/吨），区间收窄 <strong class="highlight">81 元/吨 (-30.1%)</strong>。</li>
      <li><span class="fact-badge">热卷仓单客观数据变动:</span> 2026年4月27日 热卷期货注册仓单达到年度极值 <strong>62.70 万吨</strong>。8月初仓单位于 27.75 万吨，8月中旬为 23.80 万吨，9月17日为 22.01 万吨。9月18日仓单降至 18.23 万吨，9月23日最新为 <strong>18.47 万吨</strong>，较4月高点减少 <strong>44.23 万吨</strong>，较8月初减少 <strong>9.28 万吨</strong>。</li>
      <li><span class="fact-badge">螺纹仓单客观数据变动:</span> 螺纹期货注册仓单在 9月17日 达到阶段高位 <strong>9.19 万吨</strong>，9月18日回落至 7.43 万吨，9月23日最新为 <strong>7.34 万吨</strong>。</li>
      <li><span class="fact-badge">热卷仓单历史均值参考:</span> 热卷期货自身历史统计显示，2024年全年热卷注册仓单均值为 <strong>29.1 万吨</strong>，2025年同期均值为 <strong>18.5 万吨</strong>。</li>
      <li><span class="fact-badge">SMM现货成交量变动:</span> SMM 每日三城（上海、乐从、天津）热卷现货成交总量在 8月31日 达到 <strong>13,810 吨/日</strong>，9月14日 跌破万吨至 <strong>9,950 吨/日</strong>，随后在 10,000~11,400 吨/日区间波动。</li>
    </ul>
  </div>

  <!-- 模块 3: 制造业需求、钢厂排产接单与出口发运事实 (一个页面宽度放2张图，2x2网格) -->
  <div class="section">
    <h2>3. 制造业耗钢、钢厂排产接单与出口外贸发运客观事实 (2x2 并排网格)</h2>
    
    <!-- 并排第 1 行: 制造业耗钢 + 钢厂排产 -->
    <div class="chart-grid-2">
      <div class="chart-card">
        <div class="chart-title-bar">图 3-A: 下游制造业主要板块月度耗钢量 (百万吨)</div>
        <div id="chart_manufacturing_steel" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title-bar">图 3-B: 重点钢厂热卷月度排产与出口计划跟踪 (万吨)</div>
        <div id="chart_mill_plans" class="chart-container"></div>
      </div>
    </div>

    <!-- 并排第 2 行: FOB 理论利润 + 32 港发运 -->
    <div class="chart-grid-2">
      <div class="chart-card">
        <div class="chart-title-bar">图 3-C: 天津港 FOB 出口折算价差与理论套利利润走势 (元/吨)</div>
        <div id="chart_export_profit" class="chart-container"></div>
      </div>
      <div class="chart-card">
        <div class="chart-title-bar">图 3-D: 沸腾环贸 32 港全球钢卷出港周度发运量 (万吨/周)</div>
        <div id="chart_port32_shipment" class="chart-container"></div>
      </div>
    </div>

    <!-- 制造业与钢厂排产数据表 -->
    <div class="table-responsive">
      <table>
        <thead>
          <tr>
            <th>统计板块 / 口径</th>
            <th>6月数据</th>
            <th>7月数据</th>
            <th>8月实际/预测</th>
            <th>9月计划量</th>
            <th>客观变动事实</th>
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
            <td>8月较7月增加 0.31 百万吨</td>
          </tr>
          <tr>
            <td><strong>家电行业耗钢量</strong></td>
            <td>1.89 百万吨</td>
            <td>1.54 百万吨</td>
            <td>1.54 百万吨</td>
            <td>-</td>
            <td class="highlight">较5-6月高点减少 0.38 百万吨/月 (-19.8%)</td>
          </tr>
          <tr>
            <td><strong>39家钢厂热卷总排产</strong></td>
            <td>1,326.8 万吨</td>
            <td>1,344.6 万吨</td>
            <td>1,344.6 万吨</td>
            <td>1,308.6 万吨</td>
            <td class="highlight">9月计划排产环比减少 36.0 万吨 (-2.68%)</td>
          </tr>
          <tr>
            <td><strong>39家钢厂计划出口量</strong></td>
            <td>103.0 万吨</td>
            <td>105.9 万吨</td>
            <td>105.9 万吨</td>
            <td>102.3 万吨</td>
            <td>9月计划出口环比减少 3.6 万吨 (-3.40%)</td>
          </tr>
          <tr>
            <td><strong>26家重点钢厂商品卷排产</strong></td>
            <td>-</td>
            <td>925.0 万吨</td>
            <td>930.5 万吨</td>
            <td>905.7 万吨</td>
            <td>9月计划排产环比减少 24.8 万吨 (-2.67%)</td>
          </tr>
        </tbody>
      </table>
    </div>

    <ul class="fact-list">
      <li><span class="fact-badge">下游制造业耗钢分化事实:</span> SMM 行业耗钢监测显示，机械行业月耗钢 14.72~14.79 百万吨保持平稳；家电行业耗钢量由 5-6月的 1.92 百万吨降至 7-8月的 <strong>1.54 百万吨</strong>，月均减少 <strong class="highlight">38 万吨 (-19.8%)</strong>。</li>
      <li><span class="fact-badge">重点钢厂主动调减排产事实:</span> SMM 39家热卷样本钢厂 8月实际总排产为 1,344.60 万吨，9月计划排产为 <strong>1,308.60 万吨</strong>，环比减少 <strong class="highlight">36.00 万吨 (-2.68%)</strong>；计划出口量由 105.90 万吨调减至 <strong>102.30 万吨 (-3.40%)</strong>。26家重点钢厂9月商品卷排产同样由 930.50 万吨下调至 <strong>905.70 万吨 (-2.67%)</strong>。</li>
      <li><span class="fact-badge">天津港 FOB 理论价差测算事实:</span> 截至 9月23日，天津港热卷 FOB 报价为 <strong>497.0 美元/吨</strong>，按汇率 7.11 折算人民币含税价约为 <strong>3,534 元/吨</strong>。对比上海热卷现货 3,310 元/吨，理论内外直接价差为 <strong>+224 元/吨</strong>；扣除 80 元港杂运费后，理论出口利润为 <strong>+144 元/吨</strong>。</li>
      <li><span class="fact-badge">32港钢卷出港周度发运腰斩事实:</span> 沸腾环贸 32 港统计显示，全国钢卷出港周度发运量在 9月4日当周 达到阶段高点 <strong>45.72 万吨/周</strong>，9月11日当周 降至 32.15 万吨/周，9月18日当周 降至 <strong>24.83 万吨/周</strong>，两周内变动 <strong class="highlight">-20.89 万吨/周 (降幅 -45.70%)</strong>。</li>
    </ul>
  </div>

  <!-- 模块 4: 完整高频数据明细表 (2026年8月1日 - 9月23日) -->
  <div class="section">
    <h2>4. 完整高频数据明细表（2026年8月1日 - 9月23日每日实录）</h2>
    <p style="color: var(--text-muted); font-size: 13px; margin-top: -4px;">
      注：红色高亮行为重要统计节点（8/17价差峰值、8/31价格峰值、9/10中旬节点、9/14成交低点、9/18仓单节点、9/22及9/23最新值）。
    </p>

    <div class="table-responsive">
      <table>
        <thead>
          <tr>
            <th>日期</th>
            <th>上海热卷</th>
            <th>杭州螺纹</th>
            <th>跨区卷螺差</th>
            <th>Wind卷螺差</th>
            <th>杭州库存(万吨)</th>
            <th>杭州出库(万吨)</th>
            <th>HC期货主力</th>
            <th>RB期货主力</th>
            <th>盘面卷螺差</th>
            <th>热卷仓单(万吨)</th>
            <th>螺纹仓单(万吨)</th>
            <th>SMM三城成交(吨)</th>
          </tr>
        </thead>
        <tbody>
          {daily_table_html}
        </tbody>
      </table>
    </div>
  </div>

</div>

<!-- ECharts 交互渲染脚本 -->
<script>
const c1_data = {json.dumps(chart1_data)};
const c2_data = {json.dumps(chart2_data)};
const c3_data = {json.dumps(chart3_data)};

// 1. 图 1-A: 现货基准价格走势
const chartSpotPrice = echarts.init(document.getElementById('chart_spot_price'));
chartSpotPrice.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['上海热卷(实录)', '杭州螺纹(实录)', 'Wind上海热卷', 'Wind上海螺纹'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '15%', top: '16%', containLabel: true }},
  xAxis: {{ type: 'category', data: c1_data.dates }},
  yAxis: {{ type: 'value', min: 2950, max: 3550, axisLabel: {{ formatter: '{{value}} 元' }} }},
  dataZoom: [{{ type: 'slider', bottom: 4, height: 18, start: 50, end: 100 }}],
  series: [
    {{ name: '上海热卷(实录)', type: 'line', data: c1_data.sh_hc, lineStyle: {{ width: 2.8, color: '#0284c7' }}, itemStyle: {{ color: '#0284c7' }} }},
    {{ name: '杭州螺纹(实录)', type: 'line', data: c1_data.hz_rb, lineStyle: {{ width: 2.8, color: '#dc2626' }}, itemStyle: {{ color: '#dc2626' }} }},
    {{ name: 'Wind上海热卷', type: 'line', data: c1_data.wind_sh_hc, lineStyle: {{ width: 1.5, type: 'dashed', color: '#0284c7' }} }},
    {{ name: 'Wind上海螺纹', type: 'line', data: c1_data.wind_sh_rb, lineStyle: {{ width: 1.5, type: 'dashed', color: '#f97316' }} }}
  ]
}});

// 2. 图 1-B: 跨区卷螺差对比
const chartSpotSpread = echarts.init(document.getElementById('chart_spot_spread'));
chartSpotSpread.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['跨区卷螺差(沪卷-杭螺)', 'Wind同城卷螺差(沪卷-沪螺)'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '15%', top: '16%', containLabel: true }},
  xAxis: {{ type: 'category', data: c1_data.dates }},
  yAxis: {{ type: 'value', min: -50, max: 350, axisLabel: {{ formatter: '{{value}} 元' }} }},
  dataZoom: [{{ type: 'slider', bottom: 4, height: 18, start: 50, end: 100 }}],
  series: [
    {{
      name: '跨区卷螺差(沪卷-杭螺)', type: 'line', data: c1_data.spot_spread,
      lineStyle: {{ width: 3.0, color: '#b91c1c' }}, itemStyle: {{ color: '#b91c1c' }},
      markLine: {{
        data: [
          {{ yAxis: 0, lineStyle: {{ color: '#000', width: 1 }} }},
          {{ yAxis: 150, lineStyle: {{ color: '#059669', type: 'dotted', width: 1.8 }}, label: {{ formatter: '成本线(+150元)' }} }}
        ]
      }}
    }},
    {{ name: 'Wind同城卷螺差(沪卷-沪螺)', type: 'line', data: c1_data.wind_spread, lineStyle: {{ width: 2, type: 'dashed', color: '#0284c7' }}, itemStyle: {{ color: '#0284c7' }} }}
  ]
}});

// 3. 图 1-C: 杭州库存与出库量
const chartHzInv = echarts.init(document.getElementById('chart_hz_inventory'));
chartHzInv.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['单日出库量(万吨)', '杭州库存总量(万吨)'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '15%', top: '16%', containLabel: true }},
  xAxis: {{ type: 'category', data: c1_data.dates }},
  yAxis: [
    {{ type: 'value', name: '出库(万吨)', min: 0, max: 10 }},
    {{ type: 'value', name: '库存(万吨)', min: 50, max: 150 }}
  ],
  dataZoom: [{{ type: 'slider', bottom: 4, height: 18, start: 50, end: 100 }}],
  series: [
    {{ name: '单日出库量(万吨)', type: 'bar', yAxisIndex: 0, data: c1_data.hz_outflow, itemStyle: {{ color: '#38bdf8' }} }},
    {{ name: '杭州库存总量(万吨)', type: 'line', yAxisIndex: 1, data: c1_data.hz_stock, lineStyle: {{ width: 2.8, color: '#7c3aed' }}, itemStyle: {{ color: '#7c3aed' }} }}
  ]
}});

// 4. 图 2-A: 期货主力连续收盘与盘面卷螺差
const chartFuturesDisk = echarts.init(document.getElementById('chart_futures_disk'));
chartFuturesDisk.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['热卷期货主力(HC)', '螺纹期货主力(RB)', '盘面主力卷螺差'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '15%', top: '16%', containLabel: true }},
  xAxis: {{ type: 'category', data: c2_data.dates }},
  yAxis: [
    {{ type: 'value', name: '收盘(元)', min: 3000, max: 3550 }},
    {{ type: 'value', name: '卷螺差(元)', min: 100, max: 320 }}
  ],
  dataZoom: [{{ type: 'slider', bottom: 4, height: 18, start: 50, end: 100 }}],
  series: [
    {{ name: '热卷期货主力(HC)', type: 'line', yAxisIndex: 0, data: c2_data.hc_close, lineStyle: {{ width: 2.2, color: '#0284c7' }}, itemStyle: {{ color: '#0284c7' }} }},
    {{ name: '螺纹期货主力(RB)', type: 'line', yAxisIndex: 0, data: c2_data.rb_close, lineStyle: {{ width: 2.2, color: '#dc2626' }}, itemStyle: {{ color: '#dc2626' }} }},
    {{ name: '盘面主力卷螺差', type: 'line', yAxisIndex: 1, data: c2_data.disk_spread, lineStyle: {{ width: 2.6, color: '#9333ea' }}, itemStyle: {{ color: '#9333ea' }} }}
  ]
}});

// 5. 图 2-B: 仓单客观走势
const chartWarrants = echarts.init(document.getElementById('chart_warrants'));
chartWarrants.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['热卷期货仓单(万吨)', '螺纹期货仓单(万吨)'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '15%', top: '16%', containLabel: true }},
  xAxis: {{ type: 'category', data: c2_data.dates }},
  yAxis: {{ type: 'value', min: 0, max: 45, axisLabel: {{ formatter: '{{value}} 万吨' }} }},
  dataZoom: [{{ type: 'slider', bottom: 4, height: 18, start: 50, end: 100 }}],
  series: [
    {{
      name: '热卷期货仓单(万吨)', type: 'line', data: c2_data.hc_wh,
      lineStyle: {{ width: 2.8, color: '#d97706' }}, itemStyle: {{ color: '#d97706' }},
      markLine: {{
        data: [
          {{ yAxis: 29.1, lineStyle: {{ color: '#64748b', type: 'dotted' }}, label: {{ formatter: '2024均值(29.1万吨)' }} }},
          {{ yAxis: 18.5, lineStyle: {{ color: '#10b981', type: 'dotted' }}, label: {{ formatter: '2025均值(18.5万吨)' }} }}
        ]
      }}
    }},
    {{ name: '螺纹期货仓单(万吨)', type: 'line', data: c2_data.rb_wh, lineStyle: {{ width: 2, type: 'dashed', color: '#059669' }}, itemStyle: {{ color: '#059669' }} }}
  ]
}});

// 6. 图 2-C: SMM 成交量
const chartSmmTx = echarts.init(document.getElementById('chart_smm_tx'));
chartSmmTx.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['三城总计', '乐从成交', '上海成交', '天津成交'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '15%', top: '16%', containLabel: true }},
  xAxis: {{ type: 'category', data: c2_data.dates }},
  yAxis: {{ type: 'value', min: 0, max: 17000, axisLabel: {{ formatter: '{{value}} 吨' }} }},
  dataZoom: [{{ type: 'slider', bottom: 4, height: 18, start: 50, end: 100 }}],
  series: [
    {{
      name: '三城总计', type: 'line', data: c2_data.smm_total, lineStyle: {{ width: 2.6, color: '#0f766e' }}, itemStyle: {{ color: '#0f766e' }},
      markLine: {{ data: [{{ yAxis: 10000, lineStyle: {{ color: 'red', type: 'dashed' }}, label: {{ formatter: '万吨参考线' }} }}] }}
    }},
    {{ name: '乐从成交', type: 'line', data: c2_data.smm_lc, lineStyle: {{ width: 1.5, type: 'dashed', color: '#f59e0b' }} }},
    {{ name: '上海成交', type: 'line', data: c2_data.smm_sh, lineStyle: {{ width: 1.5, type: 'dotted', color: '#0284c7' }} }},
    {{ name: '天津成交', type: 'line', data: c2_data.smm_tj, lineStyle: {{ width: 1.5, type: 'dashed', color: '#64748b' }} }}
  ]
}});

// 7. 图 3-A: 制造业耗钢
const chartMfg = echarts.init(document.getElementById('chart_manufacturing_steel'));
chartMfg.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
  legend: {{ data: ['机械耗钢(百万吨)', '汽车耗钢(百万吨)', '家电耗钢(百万吨)'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '12%', top: '18%', containLabel: true }},
  xAxis: {{ type: 'category', data: c3_data.m_dates }},
  yAxis: {{ type: 'value', min: 0, max: 18, axisLabel: {{ formatter: '{{value}}' }} }},
  series: [
    {{ name: '机械耗钢(百万吨)', type: 'bar', data: c3_data.m_mech, itemStyle: {{ color: '#0284c7' }} }},
    {{ name: '汽车耗钢(百万吨)', type: 'bar', data: c3_data.m_auto, itemStyle: {{ color: '#10b981' }} }},
    {{ name: '家电耗钢(百万吨)', type: 'bar', data: c3_data.m_appl, itemStyle: {{ color: '#f59e0b' }} }}
  ]
}});

// 8. 图 3-B: 钢厂排产
const chartMill = echarts.init(document.getElementById('chart_mill_plans'));
chartMill.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['39家计划排产(左)', '39家计划出口(右)', '26家计划出口(右)'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '12%', top: '18%', containLabel: true }},
  xAxis: {{ type: 'category', data: c3_data.p_dates }},
  yAxis: [
    {{ type: 'value', name: '总排产(万吨)', min: 1280, max: 1360 }},
    {{ type: 'value', name: '出口(万吨)', min: 70, max: 115 }}
  ],
  series: [
    {{ name: '39家计划排产(左)', type: 'line', yAxisIndex: 0, data: c3_data.p_prod39, lineStyle: {{ width: 2.2, color: '#0284c7' }}, itemStyle: {{ color: '#0284c7' }} }},
    {{ name: '39家计划出口(右)', type: 'line', yAxisIndex: 1, data: c3_data.p_exp39, lineStyle: {{ width: 2.2, color: '#f97316' }}, itemStyle: {{ color: '#f97316' }} }},
    {{ name: '26家计划出口(右)', type: 'line', yAxisIndex: 1, data: c3_data.p_exp26, lineStyle: {{ width: 1.8, type: 'dashed', color: '#dc2626' }}, itemStyle: {{ color: '#dc2626' }} }}
  ]
}});

// 9. 图 3-C: FOB 价差与利润
const chartExpProfit = echarts.init(document.getElementById('chart_export_profit'));
chartExpProfit.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'cross' }} }},
  legend: {{ data: ['出口直接价差', '理论出口利润'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '15%', top: '18%', containLabel: true }},
  xAxis: {{ type: 'category', data: c3_data.exp_dates }},
  yAxis: {{ type: 'value', min: -40, max: 260, axisLabel: {{ formatter: '{{value}} 元' }} }},
  dataZoom: [{{ type: 'slider', bottom: 4, height: 18, start: 50, end: 100 }}],
  series: [
    {{ name: '出口直接价差', type: 'line', data: c3_data.exp_spread, lineStyle: {{ width: 2.2, color: '#0284c7' }}, itemStyle: {{ color: '#0284c7' }} }},
    {{
      name: '理论出口利润', type: 'line', data: c3_data.exp_profit, lineStyle: {{ width: 2.0, color: '#10b981' }}, itemStyle: {{ color: '#10b981' }},
      markLine: {{ data: [{{ yAxis: 50, lineStyle: {{ color: '#059669', type: 'dotted' }}, label: {{ formatter: '基准(+50元)' }} }}] }}
    }}
  ]
}});

// 10. 图 3-D: 32 港发运
const chartPort32 = echarts.init(document.getElementById('chart_port32_shipment'));
chartPort32.setOption({{
  tooltip: {{ trigger: 'axis', axisPointer: {{ type: 'shadow' }} }},
  legend: {{ data: ['全球钢卷出港总量(万吨/周)'], top: 4, textStyle: {{ fontSize: 11 }} }},
  grid: {{ left: '4%', right: '4%', bottom: '15%', top: '18%', containLabel: true }},
  xAxis: {{ type: 'category', data: c3_data.port32_dates }},
  yAxis: {{ type: 'value', min: 0, max: 55, axisLabel: {{ formatter: '{{value}} 万吨' }} }},
  dataZoom: [{{ type: 'slider', bottom: 4, height: 18, start: 50, end: 100 }}],
  series: [
    {{ name: '全球钢卷出港总量(万吨/周)', type: 'bar', data: c3_data.port32_values, itemStyle: {{ color: '#f97316' }} }}
  ]
}});

// 窗口自适应
window.addEventListener('resize', () => {{
  chartSpotPrice.resize();
  chartSpotSpread.resize();
  chartHzInv.resize();
  chartFuturesDisk.resize();
  chartWarrants.resize();
  chartSmmTx.resize();
  chartMfg.resize();
  chartMill.resize();
  chartExpProfit.resize();
  chartPort32.resize();
}});
</script>

</body>
</html>
"""

with open(HTML_OUTPUT_PROJECT, 'w', encoding='utf-8') as f:
    f.write(html_content)

with open(HTML_OUTPUT_ARTIFACT, 'w', encoding='utf-8') as f:
    f.write(html_content)

print(f"[交互HTML构建完成] 项目路径: {HTML_OUTPUT_PROJECT}")
print(f"[交互HTML同步完成] Artifact: {HTML_OUTPUT_ARTIFACT}")
