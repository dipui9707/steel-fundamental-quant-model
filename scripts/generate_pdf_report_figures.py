#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: generate_pdf_report_figures.py
用途:
  为《热卷现货与卷螺差专题量化研究报告 (2024-2026)》生成专用的高分辨率嵌入图表。
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
FIG_DIR = os.path.join(PROJECT_ROOT, "研究/现货价差专题/pdf_figures")
os.makedirs(FIG_DIR, exist_ok=True)

plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'DejaVu Sans', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False

def load_data():
    excel_path = os.path.join(PROJECT_ROOT, "数据/原始/每日现货.xlsx")
    wind_path = os.path.join(PROJECT_ROOT, "数据/原始/wind_edb/wind_edb_all.parquet")

    df_excel = pd.read_excel(excel_path)
    df_excel['date'] = pd.to_datetime(df_excel['日期'])
    df_excel = df_excel.sort_values('date').set_index('date')

    df_wind = pd.read_parquet(wind_path)
    wind_hc = df_wind[df_wind['code'] == 'S0033272'].copy()
    wind_hc['date'] = pd.to_datetime(wind_hc['data_date'])
    wind_hc = wind_hc.sort_values('date').set_index('date')['value'].rename('hc_wind')

    wind_rb = df_wind[df_wind['code'] == 'S0033227'].copy()
    wind_rb['date'] = pd.to_datetime(wind_rb['data_date'])
    wind_rb = wind_rb.sort_values('date').set_index('date')['value'].rename('rb_wind')

    df = pd.DataFrame(index=df_excel.index.union(wind_hc.index)).sort_index()
    df['sh_hc'] = df_excel['上海热卷'].combine_first(wind_hc)
    df['sh_rb'] = df_excel['杭州螺纹'].combine_first(wind_rb) # 权威长材基准
    df['sh_rb_wind'] = wind_rb
    df['hc_wind'] = wind_hc
    
    # 区域热卷
    for col in ['乐从热卷', '天津热卷', '武汉热卷', '无锡热卷', '成都热卷']:
        if col in df_excel.columns:
            df[col] = df_excel[col]
            
    df['wh_hc'] = df_excel['热卷仓单(吨)']
    df['wh_rb'] = df_excel['螺纹仓单(吨)']
    df['profit_bf'] = df_excel['华东长流程利润']
    df['spread_local'] = df['hc_wind'] - df['sh_rb_wind']
    df['spread_cross'] = df['sh_hc'] - df_excel['杭州螺纹'].combine_first(df_excel['中天螺纹'])
    
    return df

def plot_fig1_regional_hrc(df):
    sub = df[df.index >= '2024-01-01'].copy()
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 6), sharex=True, gridspec_kw={'height_ratios': [2.2, 1.0]})
    fig.patch.set_facecolor('#FFFFFF')
    ax1.set_facecolor('#F8FAFC')
    ax2.set_facecolor('#F8FAFC')

    # 主流区域热卷价格
    ax1.plot(sub.index, sub['sh_hc'], color='#0284C7', linewidth=2.0, label='上海热卷 (华东基准)')
    ax1.plot(sub.index, sub['乐从热卷'], color='#F97316', linewidth=1.5, label='乐从热卷 (华南核心)')
    ax1.plot(sub.index, sub['天津热卷'], color='#10B981', linewidth=1.5, label='天津热卷 (北方集散)')
    ax1.plot(sub.index, sub['武汉热卷'], color='#8B5CF6', linewidth=1.2, linestyle='--', label='武汉热卷 (华中枢纽)')

    ax1.set_ylabel("现货价格 (元/吨)", fontsize=10, color='#334155')
    ax1.set_title("近3年 (2024-2026) 全国主流区域热卷现货价格走势对比", fontsize=12, fontweight='bold', color='#0F172A', pad=10)
    ax1.grid(True, color='#E2E8F0', linestyle='--', alpha=0.7)
    ax1.legend(loc='upper right', frameon=True, facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=8.5, ncol=2)

    # 南北区域价差 (乐从 - 天津, 上海 - 天津)
    spread_south_north = sub['乐从热卷'] - sub['天津热卷']
    spread_east_north = sub['sh_hc'] - sub['天津热卷']
    ax2.plot(sub.index, spread_south_north, color='#D97706', linewidth=1.3, label='南北价差: 乐从 - 天津')
    ax2.plot(sub.index, spread_east_north, color='#0284C7', linewidth=1.3, linestyle=':', label='区域价差: 上海 - 天津')
    ax2.axhline(0, color='#94A3B8', linestyle='-', linewidth=0.8)

    ax2.set_ylabel("区域价差 (元/吨)", fontsize=9, color='#334155')
    ax2.set_title("跨区套利价差监控 (运费窗口通常为 120-150 元/吨)", fontsize=10, color='#475569', pad=6)
    ax2.grid(True, color='#E2E8F0', linestyle='--', alpha=0.7)
    ax2.legend(loc='upper left', frameon=True, facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=8)

    ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=[1, 4, 7, 10]))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m'))
    
    plt.tight_layout()
    p = os.path.join(FIG_DIR, "fig1_3y_hc_spot_regional.png")
    plt.savefig(p, dpi=250, bbox_inches='tight')
    plt.close()
    print("Saved:", p)

def plot_fig2_spread_3y_seasonality(df):
    # 近3年季节性对比 (2024, 2025, 2026)
    ref_dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    ref_mm_dd = ref_dates.strftime('%m-%d')
    piv_local = pd.DataFrame(index=ref_mm_dd)
    piv_cross = pd.DataFrame(index=ref_mm_dd)

    for y in [2024, 2025, 2026]:
        start_d = f'{y}-01-01'
        end_d = f'{y}-12-31'
        cal_days = pd.date_range(start_d, end_d, freq='D')
        sub = df.loc[(df.index >= start_d) & (df.index <= end_d)]
        
        s_loc = sub['spread_local'].reindex(cal_days).ffill().bfill()
        s_loc.index = s_loc.index.strftime('%m-%d')
        
        s_cro = sub['spread_cross'].reindex(cal_days).ffill().bfill()
        s_cro.index = s_cro.index.strftime('%m-%d')
        
        if y == 2026:
            max_dt = df.loc[df.index.year == 2026].index.max().strftime('%m-%d')
            s_loc = s_loc[s_loc.index <= max_dt]
            s_cro = s_cro[s_cro.index <= max_dt]
            
        piv_local[str(y)] = s_loc
        piv_cross[str(y)] = s_cro

    plot_df = piv_local.copy()
    plot_df['plot_date'] = ref_dates
    plot_df = plot_df.set_index('plot_date')

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.6))
    fig.patch.set_facecolor('#FFFFFF')
    ax1.set_facecolor('#F8FAFC')
    ax2.set_facecolor('#F8FAFC')

    colors = {'2024': '#F59E0B', '2025': '#F97316', '2026': '#DC2626'}

    # 左图: 上海同城卷螺差
    for y in ['2024', '2025']:
        ax1.plot(plot_df.index, plot_df[y], color=colors[y], linewidth=1.8, label=f'{y}年')
    valid_26 = plot_df['2026'].dropna()
    ax1.plot(valid_26.index, valid_26, color=colors['2026'], linewidth=2.8, label='2026年 (最新)')
    ax1.scatter([valid_26.index[-1]], [valid_26.iloc[-1]], color='#DC2626', s=60, edgecolors='#FFFFFF', linewidth=1.5, zorder=8)
    ax1.annotate(f"最新: {valid_26.iloc[-1]:+.0f} 元/吨", xy=(valid_26.index[-1], valid_26.iloc[-1]),
                 xytext=(valid_26.index[-1] - pd.Timedelta(days=50), valid_26.iloc[-1] + 55),
                 color='#FFFFFF', fontsize=9, fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='#DC2626', edgecolor='none'),
                 arrowprops=dict(arrowstyle='->', color='#DC2626', lw=1.2))

    ax1.axhline(0, color='#64748B', linestyle='-', linewidth=0.8)
    ax1.xaxis.set_major_locator(mdates.MonthLocator(bymonth=range(1, 13, 2)))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    ax1.set_xlim(pd.to_datetime('2024-01-01'), pd.to_datetime('2024-12-31'))
    ax1.set_ylabel("现货卷螺差 (元/吨)", fontsize=10, color='#334155')
    ax1.set_title("上海同城卷螺差 (上海热卷 - 上海螺纹)", fontsize=11, fontweight='bold', color='#0F172A')
    ax1.grid(True, color='#E2E8F0', linestyle='--', alpha=0.7)
    ax1.legend(loc='lower left', frameon=True, facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=8.5)

    # 右图: 跨区域卷螺差 (上海热卷 - 杭州螺纹)
    plot_cro = piv_cross.copy()
    plot_cro['plot_date'] = ref_dates
    plot_cro = plot_cro.set_index('plot_date')

    for y in ['2024', '2025']:
        ax2.plot(plot_cro.index, plot_cro[y], color=colors[y], linewidth=1.8, label=f'{y}年')
    valid_cro_26 = plot_cro['2026'].dropna()
    ax2.plot(valid_cro_26.index, valid_cro_26, color=colors['2026'], linewidth=2.8, label='2026年 (最新)')
    ax2.scatter([valid_cro_26.index[-1]], [valid_cro_26.iloc[-1]], color='#DC2626', s=60, edgecolors='#FFFFFF', linewidth=1.5, zorder=8)
    ax2.annotate(f"最新: {valid_cro_26.iloc[-1]:+.0f} 元/吨", xy=(valid_cro_26.index[-1], valid_cro_26.iloc[-1]),
                 xytext=(valid_cro_26.index[-1] - pd.Timedelta(days=50), valid_cro_26.iloc[-1] + 55),
                 color='#FFFFFF', fontsize=9, fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='#DC2626', edgecolor='none'),
                 arrowprops=dict(arrowstyle='->', color='#DC2626', lw=1.2))

    ax2.axhline(0, color='#64748B', linestyle='-', linewidth=0.8)
    ax2.xaxis.set_major_locator(mdates.MonthLocator(bymonth=range(1, 13, 2)))
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    ax2.set_xlim(pd.to_datetime('2024-01-01'), pd.to_datetime('2024-12-31'))
    ax2.set_ylabel("跨区卷螺差 (元/吨)", fontsize=10, color='#334155')
    ax2.set_title("华东跨区卷螺差 (上海热卷 - 杭州螺纹)", fontsize=11, fontweight='bold', color='#0F172A')
    ax2.grid(True, color='#E2E8F0', linestyle='--', alpha=0.7)
    ax2.legend(loc='lower left', frameon=True, facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=8.5)

    plt.tight_layout()
    p = os.path.join(FIG_DIR, "fig2_3y_coil_rebar_spread_seasonality.png")
    plt.savefig(p, dpi=250, bbox_inches='tight')
    plt.close()
    print("Saved:", p)

def plot_fig3_2026_recent_hrc(df):
    sub = df[df.index >= '2026-05-01'].copy()
    
    fig, (ax1, ax2, ax3) = plt.subplots(3, 1, figsize=(10, 7.5), sharex=True, gridspec_kw={'height_ratios': [1.8, 1.2, 1.2]})
    fig.patch.set_facecolor('#FFFFFF')
    ax1.set_facecolor('#F8FAFC')
    ax2.set_facecolor('#F8FAFC')
    ax3.set_facecolor('#F8FAFC')

    # 价格与卷螺差
    ax1.plot(sub.index, sub['sh_hc'], color='#0284C7', linewidth=2.2, label='上海热卷现货')
    ax1.plot(sub.index, sub['sh_rb'], color='#F43F5E', linewidth=2.0, label='杭州螺纹现货')
    ax1.set_ylabel("现货价格 (元/吨)", fontsize=10, color='#334155')
    ax1.set_title("2026年近期 (5月-9月) 热卷现货、交割仓单与长流程利润高频动态监控", fontsize=12, fontweight='bold', color='#0F172A')
    ax1.grid(True, color='#E2E8F0', linestyle='--', alpha=0.7)
    ax1.legend(loc='upper right', frameon=True, facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=8.5)

    # 热卷仓单
    ax2.bar(sub.index, sub['wh_hc'] / 10000, color='#D97706', alpha=0.75, width=1.0, label='热卷期货仓单 (万吨)')
    ax2.set_ylabel("仓单数量 (万吨)", fontsize=9.5, color='#334155')
    ax2.grid(True, color='#E2E8F0', linestyle='--', alpha=0.7)
    ax2.legend(loc='upper right', frameon=True, facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=8.5)
    ax2.set_title("热卷仓单高位压制 (8月曾破40万吨，当前依然维持在18万吨高位)", fontsize=10, color='#475569')

    # 华东长流程利润
    sub['profit_bf_clean'] = sub['profit_bf'].ffill().bfill()
    ax3.plot(sub.index, sub['profit_bf_clean'], color='#7C3AED', linewidth=1.8, label='华东高炉长流程利润 (元/吨)')
    ax3.axhline(0, color='#DC2626', linestyle='--', linewidth=0.8)
    ax3.fill_between(sub.index, 0, sub['profit_bf_clean'], where=(sub['profit_bf_clean'] < 0), color='#EF4444', alpha=0.2, label='亏损区间')
    ax3.fill_between(sub.index, 0, sub['profit_bf_clean'], where=(sub['profit_bf_clean'] >= 0), color='#10B981', alpha=0.2, label='盈利区间')
    ax3.set_ylabel("长流程利润 (元/吨)", fontsize=9.5, color='#334155')
    ax3.set_title("钢厂长流程利润深幅亏损 (最新亏损 -117 元/吨，原料负反馈压制)", fontsize=10, color='#475569')
    ax3.grid(True, color='#E2E8F0', linestyle='--', alpha=0.7)
    ax3.legend(loc='lower left', frameon=True, facecolor='#FFFFFF', edgecolor='#CBD5E1', fontsize=8.5)

    ax3.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))

    plt.tight_layout()
    p = os.path.join(FIG_DIR, "fig3_2026_recent_dynamics.png")
    plt.savefig(p, dpi=250, bbox_inches='tight')
    plt.close()
    print("Saved:", p)

if __name__ == "__main__":
    df = load_data()
    plot_fig1_regional_hrc(df)
    plot_fig2_spread_3y_seasonality(df)
    plot_fig3_2026_recent_hrc(df)
