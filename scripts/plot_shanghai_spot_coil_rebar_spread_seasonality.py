#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: plot_shanghai_spot_coil_rebar_spread_seasonality.py
用途:
  基于 Wind EDB 官方现货数据，制作纯正的“上海同城现货卷螺差”按年划分季节图（2018-2026年）。
  数据口径:
  - 上海热卷现货: Wind S0033272 (中国:上海:价格:热轧板卷(Q235B,4.75mm))
  - 上海螺纹现货: Wind S0033227 (中国:上海:价格:螺纹钢(HRB400E,20mm))
  - 现货卷螺差 = 上海热卷 - 上海螺纹 (元/吨)
"""

import os
import shutil
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
ARTIFACT_DIR = "/home/hw/.gemini/antigravity/brain/78cbb79d-10e8-49b1-a7f1-b02789ba9c27"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "研究/现货价差专题")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARTIFACT_DIR, exist_ok=True)

# 字体配置
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'DejaVu Sans', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

def load_shanghai_wind_spread():
    wind_path = os.path.join(PROJECT_ROOT, "数据/原始/wind_edb/wind_edb_all.parquet")
    df_wind = pd.read_parquet(wind_path)
    
    rb = df_wind[df_wind['code'] == 'S0033227'].set_index('data_date')['value'].rename('rb_sh')
    hc = df_wind[df_wind['code'] == 'S0033272'].set_index('data_date')['value'].rename('hc_sh')
    
    df = pd.concat([rb, hc], axis=1).dropna()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    
    # 上海同城卷螺差
    df['spread'] = df['hc_sh'] - df['rb_sh']
    return df

def generate_shanghai_spread_seasonality_chart(df):
    ref_dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    ref_mm_dd = ref_dates.strftime('%m-%d')
    pivot_df = pd.DataFrame(index=ref_mm_dd)
    
    years = list(range(2018, 2027))
    for y in years:
        start_d = f'{y}-01-01'
        end_d = f'{y}-12-31'
        cal_days = pd.date_range(start_d, end_d, freq='D')
        sub = df.loc[(df.index >= start_d) & (df.index <= end_d), 'spread']
        s_cal = sub.reindex(cal_days).ffill().bfill()
        s_cal.index = s_cal.index.strftime('%m-%d')
        
        if y == 2026:
            max_dt = df.loc[df['spread'].notna() & (df.index.year == 2026)].index.max()
            max_mm_dd = max_dt.strftime('%m-%d')
            s_cal = s_cal[s_cal.index <= max_mm_dd]
            
        pivot_df[str(y)] = s_cal

    # 统计指标 (5年基准: 2021-2025)
    hist_5y = ['2021', '2022', '2023', '2024', '2025']
    pivot_df['5Y_Avg'] = pivot_df[hist_5y].mean(axis=1)
    pivot_df['5Y_Min'] = pivot_df[hist_5y].min(axis=1)
    pivot_df['5Y_Max'] = pivot_df[hist_5y].max(axis=1)
    pivot_df['5Y_Q25'] = pivot_df[hist_5y].quantile(0.25, axis=1)
    pivot_df['5Y_Q75'] = pivot_df[hist_5y].quantile(0.75, axis=1)

    plot_df = pivot_df.copy()
    plot_df['plot_date'] = ref_dates
    plot_df = plot_df.set_index('plot_date')

    # ================= 绘图开始 =================
    fig = plt.figure(figsize=(16, 11), facecolor='#0F172A')
    gs = GridSpec(2, 2, height_ratios=[1.7, 1.0], width_ratios=[1.3, 1.0], figure=fig, hspace=0.28, wspace=0.22)

    color_palette = {
        '2018': '#64748B',  # 灰
        '2019': '#0284C7',  # 蓝 (长强板弱)
        '2020': '#38BDF8',  # 浅天蓝
        '2021': '#8B5CF6',  # 紫 (大宗牛市高点)
        '2022': '#0D9488',  # 青绿
        '2023': '#10B981',  # 绿
        '2024': '#F59E0B',  # 琥珀金
        '2025': '#F97316',  # 橙色
        '2026': '#EF4444',  # 鲜红 (最新)
    }

    # ------------------ 子图 1: 全历史上海现货卷螺差季节图 (2018-2026) ------------------
    ax1 = fig.add_subplot(gs[0, :], facecolor='#1E293B')
    
    # 5年历史极值与分位带
    ax1.fill_between(plot_df.index, plot_df['5Y_Min'], plot_df['5Y_Max'],
                     color='#334155', alpha=0.35, label='2021-2025 历史极值区间 (Min-Max)')
    ax1.fill_between(plot_df.index, plot_df['5Y_Q25'], plot_df['5Y_Q75'],
                     color='#38BDF8', alpha=0.15, label='2021-2025 核心四分位区间 (25%-75%)')
    
    # 5年同期均值线
    ax1.plot(plot_df.index, plot_df['5Y_Avg'], color='#CBD5E1', linestyle='--', linewidth=2.0,
             label='2021-2025 五年同期均值', zorder=6)
    
    # 历年曲线
    for y in [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
        col = str(y)
        ls = ':' if y in [2018, 2019] else '-'
        lw = 1.2 if y in [2018, 2019] else 1.7
        alpha = 0.55 if y in [2018, 2019] else 0.85
        ax1.plot(plot_df.index, plot_df[col], color=color_palette[col], linestyle=ls,
                 linewidth=lw, alpha=alpha, label=f'{y}年')

    # 2026年加粗高亮红线
    valid_2026 = plot_df['2026'].dropna()
    ax1.plot(valid_2026.index, valid_2026, color=color_palette['2026'], linestyle='-',
             linewidth=3.2, label='2026年 (当前最新)', zorder=10)
    
    # 最新点标记与气泡标注
    latest_pt_x = valid_2026.index[-1]
    latest_pt_y = valid_2026.iloc[-1]
    ax1.scatter([latest_pt_x], [latest_pt_y], color='#EF4444', s=90, edgecolors='#FFFFFF', linewidth=2, zorder=12)
    
    latest_date_str = df.loc[df.index.year == 2026].index.max().strftime('%Y-%m-%d')
    latest_hc_val = df.loc[df.index.max(), 'hc_sh']
    latest_rb_val = df.loc[df.index.max(), 'rb_sh']
    
    ax1.annotate(f"最新: {latest_date_str}\n上海卷螺差: {latest_pt_y:+.0f} 元/吨\n(热卷 {latest_hc_val:.0f} / 螺纹 {latest_rb_val:.0f})",
                 xy=(latest_pt_x, latest_pt_y),
                 xytext=(latest_pt_x - pd.Timedelta(days=50), latest_pt_y + 110),
                 color='#FFFFFF', fontsize=10.5, fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.5', facecolor='#EF4444', edgecolor='#FFFFFF', alpha=0.95),
                 arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=-0.2', color='#FFFFFF', lw=1.5),
                 zorder=15)

    # 零轴与强弱区域文本
    ax1.axhline(0, color='#64748B', linestyle='-', linewidth=1.2, alpha=0.9)
    ax1.text(plot_df.index[5], 25, "板材溢价区间 (上海热卷强于螺纹 / 卷强螺弱 ↑)", color='#38BDF8', fontsize=9.5, alpha=0.9)
    ax1.text(plot_df.index[5], -45, "长材溢价区间 (上海螺纹强于热卷 / 螺强卷弱 ↓)", color='#F472B6', fontsize=9.5, alpha=0.9)

    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    ax1.set_xlim(pd.to_datetime('2024-01-01'), pd.to_datetime('2024-12-31'))
    ax1.tick_params(colors='#CBD5E1', labelsize=10)
    ax1.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax1.set_title("上海现货卷螺差 (上海热卷 - 上海螺纹) 按年划分季节图 (Wind 2018-2026)", fontsize=16, fontweight='bold', color='#F8FAFC', pad=14)
    ax1.set_ylabel("现货卷螺差 (元/吨)", fontsize=12, color='#94A3B8')
    ax1.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9, ncol=4, framealpha=0.9)

    # ------------------ 子图 2: 近3年 (2024-2026) 上海卷螺差高精季节对比 ------------------
    ax2 = fig.add_subplot(gs[1, 0], facecolor='#1E293B')
    
    for y in [2024, 2025]:
        col = str(y)
        ax2.plot(plot_df.index, plot_df[col], color=color_palette[col], linewidth=2.0, alpha=0.9, label=f'{y}年')
        
    ax2.plot(valid_2026.index, valid_2026, color=color_palette['2026'], linewidth=3.0, label='2026年 (最新)')
    ax2.scatter([latest_pt_x], [latest_pt_y], color='#EF4444', s=60, edgecolors='#FFFFFF', linewidth=1.5, zorder=12)
    
    ax2.axhline(0, color='#64748B', linestyle='-', linewidth=0.8)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=range(1, 13, 2)))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    ax2.set_xlim(pd.to_datetime('2024-01-01'), pd.to_datetime('2024-12-31'))
    ax2.tick_params(colors='#CBD5E1', labelsize=9)
    ax2.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax2.set_title("近3年上海现货卷螺差季节对比 (2024-2026)", fontsize=12, fontweight='bold', color='#F8FAFC', pad=10)
    ax2.set_ylabel("卷螺差 (元/吨)", fontsize=10, color='#94A3B8')
    ax2.legend(loc='lower left', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9)

    # ------------------ 子图 3: 月度卷螺差历史分布箱线图 vs 2026年定位 ------------------
    ax3 = fig.add_subplot(gs[1, 1], facecolor='#1E293B')
    
    df_hist = df[(df.index >= '2018-01-01') & (df.index < '2026-01-01')].copy()
    df_hist['month'] = df_hist.index.month
    monthly_data = [df_hist[df_hist['month'] == m]['spread'].dropna().values for m in range(1, 13)]
    
    bp = ax3.boxplot(monthly_data, positions=range(1, 13), widths=0.55, patch_artist=True,
                     boxprops=dict(facecolor='#334155', color='#94A3B8'),
                     capprops=dict(color='#94A3B8'),
                     whiskerprops=dict(color='#94A3B8', linestyle='--'),
                     flierprops=dict(marker='o', markersize=3, markerfacecolor='#64748B', alpha=0.5),
                     medianprops=dict(color='#38BDF8', linewidth=1.8))
    
    df_2026 = df[df.index >= '2026-01-01'].copy()
    df_2026['month'] = df_2026.index.month
    m_2026_means = df_2026.groupby('month')['spread'].mean()
    m_2026_latest = df_2026.loc[df_2026.index.max(), 'spread']
    cur_month = df_2026.index.max().month
    
    ax3.plot(m_2026_means.index, m_2026_means.values, color='#EF4444', marker='s', markersize=6,
             linewidth=2.2, label='2026年月均卷螺差', zorder=10)
    ax3.scatter([cur_month], [m_2026_latest], color='#EF4444', s=90, edgecolors='#FFFFFF',
                linewidth=2, zorder=12, label=f'9月最新 ({m_2026_latest:+.0f})')
    
    ax3.axhline(0, color='#64748B', linestyle='-', linewidth=0.8)
    ax3.set_xticks(range(1, 13))
    ax3.set_xticklabels([f'{m}月' for m in range(1, 13)])
    ax3.tick_params(colors='#CBD5E1', labelsize=9)
    ax3.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax3.set_title("各月上海卷螺差历史分布箱线图 vs 2026年定位", fontsize=12, fontweight='bold', color='#F8FAFC', pad=10)
    ax3.set_ylabel("卷螺差 (元/吨)", fontsize=10, color='#94A3B8')
    ax3.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9)

    # 水印与注释
    fig.text(0.5, 0.015,
             "数据来源: Wind EDB (上海热轧板卷: S0033272, 上海螺纹钢: S0033227) | 计算公式: 上海热卷 - 上海螺纹 | 截至日期: 2026-09-22",
             ha='center', fontsize=9.5, color='#64748B')
    
    out_png = os.path.join(OUTPUT_DIR, "上海卷螺差现货_按年划分季节图.png")
    plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
    
    artifact_png = os.path.join(ARTIFACT_DIR, "shanghai_spot_coil_rebar_spread_seasonality.png")
    shutil.copyfile(out_png, artifact_png)
    
    print(f"[OK] 上海现货卷螺差季节图已生成:")
    print(f"  - 项目路径: {out_png}")
    print(f"  - 展示路径: {artifact_png}")
    
    return out_png, artifact_png, pivot_df

if __name__ == "__main__":
    df = load_shanghai_wind_spread()
    out_png, artifact_png, pivot_df = generate_shanghai_spread_seasonality_chart(df)
