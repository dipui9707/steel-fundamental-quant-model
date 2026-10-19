#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成针对近期热卷现货与卷螺差走弱专题报告的高清量化图表:
- 第3页四张图采用一个页面宽度放2张图的并排版式 (2x2 网格，每行放2张图)
- 尺寸比例优化，避免单图横向过宽拉伸，字体加大清晰
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

sys.path.append('scripts')
from smm_client import SmmMcpClient

plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'WenQuanYi Zen Hei', 'SimHei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

OUTPUT_DIR = "/home/hw/项目/钢材产业系统量化模型/研究/现货价差专题/pdf_figures"
os.makedirs(OUTPUT_DIR, exist_ok=True)

# 1. 权威现货数据
df_spot = pd.read_excel('数据/原始/每日现货.xlsx')
df_spot['日期'] = pd.to_datetime(df_spot['日期'])
df_spot = df_spot.sort_values('日期').reset_index(drop=True)
recent_spot = df_spot[(df_spot['日期'] >= '2026-06-01') & (df_spot['日期'] <= '2026-09-23')].copy()
recent_spot['hz_rb'] = recent_spot['杭州螺纹'].fillna(recent_spot['中天螺纹'])
recent_spot['spread_sh_hc_hz_rb'] = recent_spot['上海热卷'] - recent_spot['hz_rb']

# 2. Wind 现货趋势验证
df_wind = pd.read_parquet('数据/原始/wind_edb/observations_2026.parquet')
df_wind['data_date'] = pd.to_datetime(df_wind['data_date'])
hc_wind = df_wind[df_wind['code'] == 'S0033272'].sort_values('data_date')[['data_date', 'value']].rename(columns={'value': 'hc_wind'})
rb_wind = df_wind[df_wind['code'] == 'S0033227'].sort_values('data_date')[['data_date', 'value']].rename(columns={'value': 'rb_wind'})
wind_spot = pd.merge(hc_wind, rb_wind, on='data_date')
wind_spot['spread_wind'] = wind_spot['hc_wind'] - wind_spot['rb_wind']
recent_wind = wind_spot[wind_spot['data_date'] >= '2026-06-01'].copy()

# 3. 期货盘面全量日线
hc_f = pd.read_parquet('数据/原始/期货合约全量日线/standardized/hc_daily.parquet')
rb_f = pd.read_parquet('数据/原始/期货合约全量日线/standardized/rb_daily.parquet')
hc_main = hc_f[hc_f['contract_code'] == 'main'].copy()
rb_main = rb_f[rb_f['contract_code'] == 'main'].copy()
hc_main['date'] = pd.to_datetime(hc_main['date'])
rb_main['date'] = pd.to_datetime(rb_main['date'])

disk = pd.merge(hc_main[['date', 'close', 'open_interest', 'volume']],
                rb_main[['date', 'close', 'open_interest', 'volume']],
                on='date', suffixes=('_hc', '_rb'))
disk['disk_spread'] = disk['close_hc'] - disk['close_rb']
recent_disk = disk[(disk['date'] >= '2026-06-01') & (disk['date'] <= '2026-09-23')].sort_values('date').reset_index(drop=True)

# 4. SMM 数据底座
df_smm = pd.read_parquet('数据/原始/smm/smm_export_manufacturing.parquet')
df_smm['date'] = pd.to_datetime(df_smm['date'])

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

# ==============================================================================
# 图 1: 现货基准价格走势、跨区卷螺差与杭州库存去化 (大字清晰版)
# ==============================================================================
fig1, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(11.2, 8.5), sharex=True)
plt.subplots_adjust(top=0.94, bottom=0.06, left=0.05, right=0.95, hspace=0.28)

# Panel 1: 现货基准价格走势
ax1.plot(recent_spot['日期'], recent_spot['上海热卷'], label='上海热卷 (实录权威现货)', color='#0284c7', lw=2.8)
ax1.plot(recent_spot['日期'], recent_spot['hz_rb'], label='杭州螺纹 (实录权威现货)', color='#dc2626', lw=2.8)
ax1.plot(recent_wind['data_date'], recent_wind['hc_wind'], label='Wind上海热卷 (趋势验证)', color='#0284c7', lw=1.5, ls='--', alpha=0.75)
ax1.plot(recent_wind['data_date'], recent_wind['rb_wind'], label='Wind上海螺纹 (趋势验证)', color='#f97316', lw=1.5, ls='--', alpha=0.75)
ax1.set_title('图 1-A: 上海热卷与杭州螺纹实录现货价格走势 (含 Wind 趋势验证)', fontsize=12.0, fontweight='bold', pad=6)
ax1.set_ylabel('现货价格 (元/吨)', fontsize=10.5, fontweight='bold')
ax1.tick_params(labelsize=10.0)
ax1.grid(True, linestyle=':', alpha=0.6)
ax1.legend(loc='upper right', fontsize=9.5, framealpha=0.92, ncol=2)

# Panel 2: 卷螺差对比
ax2.plot(recent_spot['日期'], recent_spot['spread_sh_hc_hz_rb'], label='跨区卷螺差: 上海热卷 - 杭州螺纹 (实录)', color='#b91c1c', lw=3.0)
ax2.plot(recent_wind['data_date'], recent_wind['spread_wind'], label='Wind同城卷螺差: 上海热卷 - 上海螺纹 (验证)', color='#0284c7', lw=2.0, ls='--')
ax2.axhline(0, color='black', lw=1.0, ls='-')
ax2.axhline(150, color='#059669', lw=1.2, ls=':', label='工序成本参考线 (+150 元/吨)')
ax2.set_ylim(-40, 360)

ax2.annotate('8/17峰值: +280 元/吨', xy=(mdates.date2num(pd.to_datetime('2026-08-17')), 280),
             xytext=(mdates.date2num(pd.to_datetime('2026-08-17'))-18, 310),
             arrowprops=dict(facecolor='#b91c1c', shrink=0.08, width=1.8, headwidth=6),
             fontsize=9.5, fontweight='bold', color='#b91c1c')

ax2.annotate('9/23最新: +150 元/吨 (-130元)', xy=(mdates.date2num(pd.to_datetime('2026-09-23')), 150),
             xytext=(mdates.date2num(pd.to_datetime('2026-09-23'))-24, 75),
             arrowprops=dict(facecolor='#b91c1c', shrink=0.08, width=1.8, headwidth=6),
             fontsize=9.5, fontweight='bold', color='#b91c1c')

last_wind_val = recent_wind.iloc[-1]['spread_wind']
ax2.annotate(f'Wind最新: +{int(last_wind_val)} 元/吨', xy=(mdates.date2num(recent_wind.iloc[-1]['data_date']), last_wind_val),
             xytext=(mdates.date2num(recent_wind.iloc[-1]['data_date'])-24, last_wind_val+32),
             arrowprops=dict(facecolor='#0284c7', shrink=0.08, width=1.5, headwidth=5),
             fontsize=9.0, fontweight='bold', color='#0284c7')

ax2.set_title('图 1-B: 跨区卷螺差 (上海热卷 - 杭州螺纹) 与 Wind 卷螺差走势对比', fontsize=12.0, fontweight='bold', pad=6)
ax2.set_ylabel('卷螺差 (元/吨)', fontsize=10.5, fontweight='bold')
ax2.tick_params(labelsize=10.0)
ax2.grid(True, linestyle=':', alpha=0.6)
ax2.legend(loc='upper left', fontsize=9.5, framealpha=0.92)

# Panel 3: 杭州螺纹库存与出库量
ax3.bar(recent_spot['日期'], recent_spot['杭州出库'], label='杭州螺纹单日出库量 (万吨/日)', color='#38bdf8', width=0.8, alpha=0.85)
ax3_twin = ax3.twinx()
ax3_twin.plot(recent_spot['日期'], recent_spot['杭州库存'], label='杭州螺纹库存总量 (万吨)', color='#7c3aed', lw=2.8)
ax3_twin.set_ylim(60, 140)

ax3_twin.annotate('8/17库存: 113.8万吨', xy=(mdates.date2num(pd.to_datetime('2026-08-17')), 113.8),
                  xytext=(mdates.date2num(pd.to_datetime('2026-08-17'))-18, 126),
                  arrowprops=dict(facecolor='#7c3aed', shrink=0.08, width=1.6, headwidth=5),
                  fontsize=9.0, fontweight='bold', color='#7c3aed')

ax3_twin.annotate('9/23最新: 82.8万吨 (-31.0万吨)', xy=(mdates.date2num(pd.to_datetime('2026-09-23')), 82.8),
                  xytext=(mdates.date2num(pd.to_datetime('2026-09-23'))-24, 68),
                  arrowprops=dict(facecolor='#7c3aed', shrink=0.08, width=1.6, headwidth=5),
                  fontsize=9.0, fontweight='bold', color='#7c3aed')

ax3.set_title('图 1-C: 杭州螺纹库存变动 (113.8万吨 -> 82.8万吨) 与日度出库量', fontsize=12.0, fontweight='bold', pad=6)
ax3.set_ylabel('出库量 (万吨)', fontsize=10.5, fontweight='bold', color='#0284c7')
ax3_twin.set_ylabel('库存量 (万吨)', fontsize=10.5, fontweight='bold', color='#7c3aed')
ax3.tick_params(labelsize=10.0)
ax3_twin.tick_params(labelsize=10.0)
ax3.grid(True, linestyle=':', alpha=0.6)

lines1, labels1 = ax3.get_legend_handles_labels()
lines2, labels2 = ax3_twin.get_legend_handles_labels()
ax3.legend(lines1 + lines2, labels1 + labels2, loc='upper right', fontsize=9.0, framealpha=0.92)

ax3.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
fig1_path = os.path.join(OUTPUT_DIR, "fig_recent_1_spot_hz_sh.png")
plt.savefig(fig1_path, dpi=250)
plt.close()
print("图 1 已更新:", fig1_path)

# ==============================================================================
# 图 2: 期货主力连续走势、热卷与螺纹仓单客观走势、SMM成交量 (大字清晰版)
# ==============================================================================
fig2, (bx1, bx2, bx3) = plt.subplots(3, 1, figsize=(11.2, 8.5), sharex=True)
plt.subplots_adjust(top=0.94, bottom=0.06, left=0.05, right=0.95, hspace=0.28)

# Panel 1: 期货主力连续走势与盘面卷螺差
bx1.plot(recent_disk['date'], recent_disk['close_hc'], label='热卷期货主力连续 (HC主力)', color='#0284c7', lw=2.4)
bx1.plot(recent_disk['date'], recent_disk['close_rb'], label='螺纹期货主力连续 (RB主力)', color='#dc2626', lw=2.4)
bx1_twin = bx1.twinx()
bx1_twin.plot(recent_disk['date'], recent_disk['disk_spread'], label='盘面主力卷螺差 (HC - RB)', color='#9333ea', lw=2.6)
bx1_twin.set_ylim(100, 340)

bx1_twin.annotate('8/17: +269 元', xy=(mdates.date2num(pd.to_datetime('2026-08-17')), 269),
                  xytext=(mdates.date2num(pd.to_datetime('2026-08-17'))-18, 280),
                  arrowprops=dict(facecolor='#9333ea', shrink=0.08, width=1.5, headwidth=5),
                  fontsize=9.0, fontweight='bold', color='#9333ea')
bx1_twin.annotate('9/23: +188 元', xy=(mdates.date2num(pd.to_datetime('2026-09-23')), 188),
                  xytext=(mdates.date2num(pd.to_datetime('2026-09-23'))-20, 135),
                  arrowprops=dict(facecolor='#9333ea', shrink=0.08, width=1.5, headwidth=5),
                  fontsize=9.0, fontweight='bold', color='#9333ea')

bx1.set_title('图 2-A: 期货主力连续收盘价走势与盘面主力卷螺差变动', fontsize=12.0, fontweight='bold', pad=6)
bx1.set_ylabel('期货收盘价 (元/吨)', fontsize=10.5, fontweight='bold')
bx1_twin.set_ylabel('盘面卷螺差 (元/吨)', fontsize=10.5, fontweight='bold', color='#9333ea')
bx1.tick_params(labelsize=10.0)
bx1_twin.tick_params(labelsize=10.0)
bx1.grid(True, linestyle=':', alpha=0.6)
lines1, labels1 = bx1.get_legend_handles_labels()
lines2, labels2 = bx1_twin.get_legend_handles_labels()
bx1.legend(lines1 + lines2, labels1 + labels2, loc='upper left', fontsize=9.0, framealpha=0.92, ncol=3)

# Panel 2: 仓单客观数量变动情况 (严格客观陈述)
spot_wh = recent_spot.dropna(subset=['热卷仓单(吨)']).copy()
spot_wh['hc_wh_10k'] = spot_wh['热卷仓单(吨)'] / 10000.0
spot_wh['rb_wh_10k'] = spot_wh['螺纹仓单(吨)'] / 10000.0

bx2.plot(spot_wh['日期'], spot_wh['hc_wh_10k'], label='热卷期货注册仓单 (实录万吨)', color='#d97706', lw=3.0)
bx2.plot(spot_wh['日期'], spot_wh['rb_wh_10k'], label='螺纹期货注册仓单 (实录万吨)', color='#059669', lw=2.2, ls='--')
bx2.axhline(29.1, color='#64748b', lw=1.2, ls=':', label='热卷2024年均值参考 (29.1万吨)')
bx2.axhline(18.5, color='#10b981', lw=1.2, ls=':', label='热卷2025年均值参考 (18.5万吨)')
bx2.set_ylim(0, 56)

bx2.annotate('8月初: 27.75万吨', xy=(mdates.date2num(pd.to_datetime('2026-08-03')), 27.75),
             xytext=(mdates.date2num(pd.to_datetime('2026-08-03'))-18, 36),
             arrowprops=dict(facecolor='#d97706', shrink=0.08, width=1.5, headwidth=5),
             fontsize=9.0, fontweight='bold', color='#d97706')

bx2.annotate('9/17: 22.01万吨', xy=(mdates.date2num(pd.to_datetime('2026-09-17')), 22.01),
             xytext=(mdates.date2num(pd.to_datetime('2026-09-17'))-18, 28),
             arrowprops=dict(facecolor='#d97706', shrink=0.08, width=1.5, headwidth=5),
             fontsize=9.0, fontweight='bold', color='#d97706')

bx2.annotate('9/23最新: 18.47万吨\n(较4月高点-44.23万吨)', xy=(mdates.date2num(pd.to_datetime('2026-09-23')), 18.47),
             xytext=(mdates.date2num(pd.to_datetime('2026-09-23'))-28, 11),
             arrowprops=dict(facecolor='#d97706', shrink=0.08, width=1.5, headwidth=5),
             fontsize=9.0, fontweight='bold', color='#d97706')

bx2.set_title('图 2-B: 热卷与螺纹期货注册仓单客观走势 (含热卷历史均值参考)', fontsize=12.0, fontweight='bold', pad=6)
bx2.set_ylabel('注册仓单量 (万吨)', fontsize=10.5, fontweight='bold')
bx2.tick_params(labelsize=10.0)
bx2.grid(True, linestyle=':', alpha=0.6)
bx2.legend(loc='upper right', fontsize=8.8, framealpha=0.92, ncol=2)

# Panel 3: SMM 热卷三城日度成交量变动
if not df_smm_tx.empty:
    bx3.plot(df_smm_tx['date'], df_smm_tx['total_3c_tx'], label='SMM三城热卷成交量总计 (吨/日)', color='#0f766e', lw=2.6)
    bx3.plot(df_smm_tx['date'], df_smm_tx['lc_tx'], label='乐从日成交量 (吨/日)', color='#f59e0b', lw=1.5, ls='--')
    bx3.plot(df_smm_tx['date'], df_smm_tx['sh_tx'], label='上海日成交量 (吨/日)', color='#0284c7', lw=1.5, ls=':')
    bx3.plot(df_smm_tx['date'], df_smm_tx['tj_tx'], label='天津日成交量 (吨/日)', color='#64748b', lw=1.5, ls='-.')
    bx3.axhline(10000, color='red', lw=1.0, ls='--', alpha=0.7, label='10,000 吨参考线')
    bx3.set_ylim(0, 18500)

    bx3.annotate('8/31: 13,810 吨', xy=(mdates.date2num(pd.to_datetime('2026-08-31')), 13810),
                 xytext=(mdates.date2num(pd.to_datetime('2026-08-31'))-18, 14800),
                 arrowprops=dict(facecolor='#0f766e', shrink=0.08, width=1.5, headwidth=5),
                 fontsize=9.0, fontweight='bold', color='#0f766e')
    bx3.annotate('9/14: 9,950 吨', xy=(mdates.date2num(pd.to_datetime('2026-09-14')), 9950),
                 xytext=(mdates.date2num(pd.to_datetime('2026-09-14'))-18, 7500),
                 arrowprops=dict(facecolor='red', shrink=0.08, width=1.5, headwidth=5),
                 fontsize=9.0, fontweight='bold', color='red')

    bx3.set_title('图 2-C: SMM 热卷现货日度成交量走势 (三城总计及各分市场)', fontsize=12.0, fontweight='bold', pad=6)
    bx3.set_ylabel('成交量 (吨/日)', fontsize=10.5, fontweight='bold')
    bx3.tick_params(labelsize=10.0)
    bx3.grid(True, linestyle=':', alpha=0.6)
    bx3.legend(loc='upper right', fontsize=8.8, framealpha=0.92, ncol=3)

bx3.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
fig2_path = os.path.join(OUTPUT_DIR, "fig_recent_2_disk_futures.png")
plt.savefig(fig2_path, dpi=250)
plt.close()
print("图 2 已更新:", fig2_path)

# ==============================================================================
# 图 3: 制造业需求、钢厂排产计划、出口内外价差与32港发运 (一个页面宽度放2张图，2x2网格)
# ==============================================================================
fig3, ((cx1, cx2), (cx3, cx4)) = plt.subplots(2, 2, figsize=(11.2, 7.6))
plt.subplots_adjust(top=0.94, bottom=0.08, left=0.055, right=0.955, hspace=0.30, wspace=0.18)

# Subplot 1: 制造业下游行业月度耗钢量 (百万吨)
m_dates = ['5月', '6月', '7月', '8月(预)']
m_mech = [15.20, 15.66, 14.72, 14.79]
m_auto = [4.65, 4.87, 4.39, 4.70]
m_appl = [1.92, 1.89, 1.54, 1.54]

x_pos = np.arange(len(m_dates))
width = 0.26
cx1.bar(x_pos - width, m_mech, width, label='机械耗钢(百万吨)', color='#0284c7')
cx1.bar(x_pos, m_auto, width, label='汽车耗钢(百万吨)', color='#10b981')
cx1.bar(x_pos + width, m_appl, width, label='家电耗钢(百万吨)', color='#f59e0b')
cx1.set_xticks(x_pos)
cx1.set_xticklabels(m_dates, fontsize=9.5, fontweight='bold')
cx1.set_title('图 3-A: 下游制造业主要板块月度耗钢量 (百万吨)', fontsize=11.0, fontweight='bold', pad=5)
cx1.set_ylabel('月度耗钢量 (百万吨)', fontsize=9.5, fontweight='bold')
cx1.set_ylim(0, 18.5)
cx1.tick_params(labelsize=9.0)
cx1.grid(True, linestyle=':', alpha=0.6)
cx1.legend(loc='upper right', fontsize=8.5)

# Subplot 2: 钢厂月度排产与出口接单计划 (万吨)
p_dates = ['6月', '7月', '8月', '9月']
p_prod39 = [1326.8, 1344.6, 1308.6, 1315.0]
p_exp39 = [103.0, 105.9, 102.3, 104.5]
p_exp26 = [79.6, 81.2, 77.8, 81.7]

x2_pos = np.arange(len(p_dates))
cx2.plot(x2_pos, p_prod39, marker='s', markersize=6, color='#0284c7', lw=2.2, label='39家总排产 (左轴)')
cx2_twin = cx2.twinx()
cx2_twin.plot(x2_pos, p_exp39, marker='o', markersize=6, color='#f97316', lw=2.2, label='39家计划出口 (右轴)')
cx2_twin.plot(x2_pos, p_exp26, marker='^', markersize=6, color='#dc2626', lw=1.8, ls='--', label='26家计划出口 (右轴)')
cx2.set_ylim(1280, 1365)
cx2_twin.set_ylim(70, 115)

cx2.set_xticks(x2_pos)
cx2.set_xticklabels(p_dates, fontsize=9.5, fontweight='bold')
cx2.set_title('图 3-B: 重点钢厂热卷月度排产与出口计划 (万吨)', fontsize=11.0, fontweight='bold', pad=5)
cx2.set_ylabel('计划总排产 (万吨)', fontsize=9.5, fontweight='bold', color='#0284c7')
cx2_twin.set_ylabel('计划出口量 (万吨)', fontsize=9.5, fontweight='bold', color='#f97316')
cx2.tick_params(labelsize=9.0)
cx2_twin.tick_params(labelsize=9.0)
cx2.grid(True, linestyle=':', alpha=0.6)
lines1, labels1 = cx2.get_legend_handles_labels()
lines2, labels2 = cx2_twin.get_legend_handles_labels()
cx2.legend(lines1 + lines2, labels1 + labels2, loc='lower left', fontsize=8.2)

# Subplot 3: 出口内外直接价差与理论套利利润 (元/吨)
fob_hc = df_smm[df_smm['indicator_id'] == 's22804474'].sort_values('date')[['date', 'value']].rename(columns={'value': 'fob_usd'})
m_exp = pd.merge(recent_spot[['日期', '上海热卷']], fob_hc, left_on='日期', right_on='date')
m_exp['fob_cny'] = m_exp['fob_usd'] * 7.11
m_exp['export_spread'] = m_exp['fob_cny'] - m_exp['上海热卷']
m_exp['export_profit'] = m_exp['export_spread'] - 80.0

cx3.plot(m_exp['日期'], m_exp['export_spread'], label='出口内外直接价差 (FOB折算 - 沪卷现货)', color='#0284c7', lw=2.4)
cx3.plot(m_exp['日期'], m_exp['export_profit'], label='理论出口利润 (扣除80元杂费)', color='#10b981', lw=2.0)
cx3.axhline(50, color='#059669', lw=1.0, ls=':', label='利润基准线 (+50元)')
cx3.set_ylim(-30, 260)
cx3.set_title('图 3-C: 天津港 FOB 出口折算价差与理论利润 (元/吨)', fontsize=11.0, fontweight='bold', pad=5)
cx3.set_ylabel('价差 / 利润 (元/吨)', fontsize=9.5, fontweight='bold')
cx3.tick_params(labelsize=9.0)
cx3.grid(True, linestyle=':', alpha=0.6)
cx3.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
cx3.legend(loc='upper left', fontsize=8.2)

latest_pt = m_exp.iloc[-1]
cx3.annotate(f"9/23最新: 利润+{int(latest_pt['export_profit'])}元", (mdates.date2num(latest_pt['日期']), latest_pt['export_profit']),
             textcoords="offset points", xytext=(-20, 8), ha='center', fontsize=8.8, fontweight='bold', color='#047857')

# Subplot 4: 沸腾环贸 32 港全球钢卷出港周度发运量 (万吨/周)
shp_coil = df_smm[df_smm['indicator_id'] == 'a10135358'].sort_values('date')
shp_recent = shp_coil[shp_coil['date'] >= '2026-06-01']
cx4.bar(shp_recent['date'], shp_recent['value'], width=4.5, color='#f97316', alpha=0.88, label='全球钢卷出港总量 (万吨/周)')
cx4.set_ylim(0, 56)
cx4.set_title('图 3-D: 沸腾环贸 32 港全球钢卷出港周度发运量 (万吨/周)', fontsize=11.0, fontweight='bold', pad=5)
cx4.set_ylabel('发运量 (万吨/周)', fontsize=9.5, fontweight='bold')
cx4.tick_params(labelsize=9.0)
cx4.grid(True, linestyle=':', alpha=0.6)
cx4.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

last_shp = shp_recent.iloc[-1]
prev_peak = shp_recent[shp_recent['date'] == '2026-09-04'].iloc[0]
cx4.annotate(f"9/4高点: {prev_peak['value']:.1f}万吨", (mdates.date2num(prev_peak['date']), prev_peak['value']),
             textcoords="offset points", xytext=(-15, 6), ha='center', fontsize=8.8, fontweight='bold', color='#c2410c')
cx4.annotate(f"9/18: {last_shp['value']:.1f}万吨 (-45.7%)", (mdates.date2num(last_shp['date']), last_shp['value']),
             textcoords="offset points", xytext=(0, 6), ha='center', fontsize=8.8, fontweight='bold', color='#dc2626')
cx4.legend(loc='upper left', fontsize=8.2)

fig3_path = os.path.join(OUTPUT_DIR, "fig_recent_3_demand_export.png")
plt.savefig(fig3_path, dpi=250)
plt.close()
print("图 3 已更新 (一个页面宽度放2张图，2x2网格):", fig3_path)
