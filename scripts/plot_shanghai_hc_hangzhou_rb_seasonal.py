#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: plot_shanghai_hc_hangzhou_rb_seasonal.py
用途:
  绘制上海热卷与杭州螺纹钢现货价差的按年划分季节图（2019-2026年）。
  数据口径:
  - 杭州螺纹: 《每日现货.xlsx》杭州螺纹 (优先) 与中天螺纹 (2019-2026连续基准，中天为杭州现货交割与定价核心品牌)。
  - 上海热卷: 《每日现货.xlsx》上海热卷 (2024-2026 Authoritative Truth 最新修正版) + Wind EDB S0033272 (2018-2023 历史延续)。
  - 价差定义: 上海热卷 - 杭州螺纹 (元/吨，卷螺差)。
"""

import os
import shutil
import datetime
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.gridspec import GridSpec

# 1. 基础配置与中文字体
PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
ARTIFACT_DIR = "/home/hw/.gemini/antigravity/brain/78cbb79d-10e8-49b1-a7f1-b02789ba9c27"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "研究/现货价差专题")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(ARTIFACT_DIR, exist_ok=True)

# 设置字体
plt.rcParams['font.sans-serif'] = ['Noto Sans CJK SC', 'Noto Sans CJK JP', 'DejaVu Sans', 'sans-serif']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['figure.autolayout'] = False

def load_data():
    excel_path = os.path.join(PROJECT_ROOT, "数据/原始/每日现货.xlsx")
    wind_path = os.path.join(PROJECT_ROOT, "数据/原始/wind_edb/wind_edb_all.parquet")

    # 读取每日现货
    df_excel = pd.read_excel(excel_path)
    df_excel['date'] = pd.to_datetime(df_excel['日期'])
    df_excel = df_excel.sort_values('date').set_index('date')

    # 读取 Wind S0033272 (上海热卷)
    df_wind = pd.read_parquet(wind_path)
    wind_hc = df_wind[df_wind['code'] == 'S0033272'].copy()
    wind_hc['date'] = pd.to_datetime(wind_hc['data_date'])
    wind_hc = wind_hc.sort_values('date').set_index('date')['value']

    # 合并基准序列
    all_dates = df_excel.index.union(wind_hc.index).sort_values()
    df = pd.DataFrame(index=all_dates)
    
    # 杭州螺纹基准 (优先用户杭州螺纹列，缺测期取中天螺纹)
    df['hz_rb'] = df_excel['杭州螺纹'].combine_first(df_excel['中天螺纹'])
    # 上海热卷基准 (2024年起权威Excel为主，前期以Wind为主)
    df['sh_hc'] = df_excel['上海热卷'].combine_first(wind_hc)
    
    # 价差 (上海热卷 - 杭州螺纹)
    df['spread'] = df['sh_hc'] - df['hz_rb']
    
    # 仅保留纯 Excel 数据的价差供局部对比
    df['spread_excel_pure'] = df_excel['上海热卷'] - df['hz_rb']
    
    return df

def generate_seasonality_chart(df):
    # 构造以参考闰年(2024)为基准的366日历坐标
    ref_dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    ref_mm_dd = ref_dates.strftime('%m-%d')
    pivot_df = pd.DataFrame(index=ref_mm_dd)
    
    years = list(range(2019, 2027))
    for y in years:
        start_d = f'{y}-01-01'
        end_d = f'{y}-12-31'
        cal_days = pd.date_range(start_d, end_d, freq='D')
        s_y = df.loc[(df.index >= start_d) & (df.index <= end_d), 'spread']
        s_cal = s_y.reindex(cal_days).ffill().bfill()
        s_cal.index = s_cal.index.strftime('%m-%d')
        
        # 当前年份(2026)仅截断到实际有观测的最新一天
        if y == 2026:
            max_dt = df.loc[df['spread'].notna() & (df.index.year == 2026)].index.max()
            max_mm_dd = max_dt.strftime('%m-%d')
            s_cal = s_cal[s_cal.index <= max_mm_dd]
            
        pivot_df[str(y)] = s_cal

    # 统计指标 (5年基准: 2021-2025)
    hist_5y_cols = ['2021', '2022', '2023', '2024', '2025']
    pivot_df['5Y_Avg'] = pivot_df[hist_5y_cols].mean(axis=1)
    pivot_df['5Y_Q25'] = pivot_df[hist_5y_cols].quantile(0.25, axis=1)
    pivot_df['5Y_Q75'] = pivot_df[hist_5y_cols].quantile(0.75, axis=1)
    pivot_df['5Y_Min'] = pivot_df[hist_5y_cols].min(axis=1)
    pivot_df['5Y_Max'] = pivot_df[hist_5y_cols].max(axis=1)
    
    # 绑定回 2024 时间对象便于绘图
    plot_df = pivot_df.copy()
    plot_df['plot_date'] = ref_dates
    plot_df = plot_df.set_index('plot_date')

    # ================= 开始绘图 =================
    fig = plt.figure(figsize=(16, 11), facecolor='#0F172A')
    gs = GridSpec(2, 2, height_ratios=[1.7, 1.0], width_ratios=[1.3, 1.0], figure=fig, hspace=0.28, wspace=0.22)
    
    # 颜色配置 (高质感量化暗色主题)
    color_palette = {
        '2019': '#64748B',  # 灰蓝
        '2020': '#0284C7',  # 蓝
        '2021': '#8B5CF6',  # 紫 (大宗牛市峰值)
        '2022': '#0D9488',  # 青绿
        '2023': '#10B981',  # 绿
        '2024': '#F59E0B',  # 琥珀金
        '2025': '#F97316',  # 橙色
        '2026': '#EF4444',  # 鲜红 (当前最新年份)
    }

    # ------------------ 子图 1: 全历史季节图 (2019-2026) ------------------
    ax1 = fig.add_subplot(gs[0, :], facecolor='#1E293B')
    
    # 5年历史分位带
    ax1.fill_between(plot_df.index, plot_df['5Y_Min'], plot_df['5Y_Max'],
                     color='#334155', alpha=0.35, label='2021-2025 历史极值区间 (Min-Max)')
    ax1.fill_between(plot_df.index, plot_df['5Y_Q25'], plot_df['5Y_Q75'],
                     color='#38BDF8', alpha=0.15, label='2021-2025 核心四分位区间 (25%-75%)')
    
    # 5年均值线
    ax1.plot(plot_df.index, plot_df['5Y_Avg'], color='#94A3B8', linestyle='--', linewidth=2.0,
             label='2021-2025 五年同期均值')
    
    # 绘制历年曲线
    for y in [2019, 2020, 2021, 2022, 2023, 2024, 2025]:
        col = str(y)
        ls = ':' if y in [2019, 2020] else '-'
        lw = 1.3 if y in [2019, 2020] else 1.8
        alpha = 0.6 if y in [2019, 2020] else 0.85
        ax1.plot(plot_df.index, plot_df[col], color=color_palette[col], linestyle=ls,
                 linewidth=lw, alpha=alpha, label=f'{y}年')
        
    # 绘制 2026 鲜亮突出曲线
    valid_2026 = plot_df['2026'].dropna()
    ax1.plot(valid_2026.index, valid_2026, color=color_palette['2026'], linestyle='-',
             linewidth=3.2, label='2026年 (当前最新)', zorder=10)
    
    # 标记 2026 最新点
    latest_pt_x = valid_2026.index[-1]
    latest_pt_y = valid_2026.iloc[-1]
    ax1.scatter([latest_pt_x], [latest_pt_y], color='#EF4444', s=90, edgecolors='#FFFFFF', linewidth=2, zorder=12)
    
    # 最新点标注框
    latest_date_str = df.loc[df['spread'].notna() & (df.index.year == 2026)].index.max().strftime('%Y-%m-%d')
    ax1.annotate(f"最新: {latest_date_str}\n价差: {latest_pt_y:+.0f} 元/吨",
                 xy=(latest_pt_x, latest_pt_y),
                 xytext=(latest_pt_x - pd.Timedelta(days=45), latest_pt_y + 90),
                 color='#FFFFFF', fontsize=11, fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.5', facecolor='#EF4444', edgecolor='#FFFFFF', alpha=0.95),
                 arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=-0.2', color='#FFFFFF', lw=1.5),
                 zorder=15)

    # 零轴
    ax1.axhline(0, color='#64748B', linestyle='-', linewidth=1.0, alpha=0.8)
    ax1.text(plot_df.index[5], 15, "板材溢价 (热卷强于螺纹 / 卷强螺弱 ↑)", color='#38BDF8', fontsize=10, alpha=0.85)
    ax1.text(plot_df.index[5], -40, "长材溢价 (螺纹强于热卷 / 螺强卷弱 ↓)", color='#F472B6', fontsize=10, alpha=0.85)

    # X轴与格式
    ax1.xaxis.set_major_locator(mdates.MonthLocator(bymonth=range(1, 13)))
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    ax1.set_xlim(pd.to_datetime('2024-01-01'), pd.to_datetime('2024-12-31'))
    ax1.tick_params(colors='#CBD5E1', labelsize=10)
    ax1.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax1.set_title("上海热卷 - 杭州螺纹 现货价差按年划分季节图 (2019-2026 全历史视角)", fontsize=16, fontweight='bold', color='#F8FAFC', pad=14)
    ax1.set_ylabel("现货价差 (元/吨)", fontsize=12, color='#94A3B8')
    
    # 图例
    ax1.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC',
               fontsize=9, ncol=4, framealpha=0.9)

    # ------------------ 子图 2: 近3年纯《每日现货.xlsx》高精季节对比 ------------------
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
    ax2.set_title("近3年高精原生现货价差季节对比 (2024-2026)", fontsize=12, fontweight='bold', color='#F8FAFC', pad=10)
    ax2.set_ylabel("价差 (元/吨)", fontsize=10, color='#94A3B8')
    ax2.legend(loc='lower left', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9)

    # ------------------ 子图 3: 月度价差分布与2026当前定位 ------------------
    ax3 = fig.add_subplot(gs[1, 1], facecolor='#1E293B')
    
    # 提取历史 2019-2025 的月度分布
    df_hist = df[(df.index >= '2019-01-01') & (df.index < '2026-01-01')].copy()
    df_hist['month'] = df_hist.index.month
    monthly_data = [df_hist[df_hist['month'] == m]['spread'].dropna().values for m in range(1, 13)]
    
    # 箱线图
    bp = ax3.boxplot(monthly_data, positions=range(1, 13), widths=0.55, patch_artist=True,
                     boxprops=dict(facecolor='#334155', color='#94A3B8'),
                     capprops=dict(color='#94A3B8'),
                     whiskerprops=dict(color='#94A3B8', linestyle='--'),
                     flierprops=dict(marker='o', markersize=3, markerfacecolor='#64748B', alpha=0.5),
                     medianprops=dict(color='#38BDF8', linewidth=1.8))
    
    # 叠加 2026 年各月实际均值/最新值
    df_2026 = df[df.index >= '2026-01-01'].copy()
    df_2026['month'] = df_2026.index.month
    m_2026_means = df_2026.groupby('month')['spread'].mean()
    m_2026_latest = df_2026.loc[df_2026.index.max(), 'spread']
    cur_month = df_2026.index.max().month
    
    ax3.plot(m_2026_means.index, m_2026_means.values, color='#EF4444', marker='s', markersize=6,
             linewidth=2.2, label='2026年月度均值', zorder=10)
    ax3.scatter([cur_month], [m_2026_latest], color='#EF4444', s=90, edgecolors='#FFFFFF',
                linewidth=2, zorder=12, label=f'9月最新 ({m_2026_latest:+.0f})')
    
    ax3.axhline(0, color='#64748B', linestyle='-', linewidth=0.8)
    ax3.set_xticks(range(1, 13))
    ax3.set_xticklabels([f'{m}月' for m in range(1, 13)])
    ax3.tick_params(colors='#CBD5E1', labelsize=9)
    ax3.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax3.set_title("各月价差历史分布箱线图 vs 2026年定位", fontsize=12, fontweight='bold', color='#F8FAFC', pad=10)
    ax3.set_ylabel("价差 (元/吨)", fontsize=10, color='#94A3B8')
    ax3.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9)

    # 底部数据说明水印
    fig.text(0.5, 0.015,
             "数据来源: 《每日现货.xlsx》(上海热卷、杭州螺纹、中天螺纹) & Wind EDB (S0033272) | 计算公式: 上海热卷(Q235B) - 杭州螺纹(HRB400E) | 截至日期: 2026-09-22",
             ha='center', fontsize=10, color='#64748B')
    
    # 保存输出
    out_png = os.path.join(OUTPUT_DIR, "上海热卷_杭州螺纹_价差季节图.png")
    plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
    
    # 拷贝到 artifact 目录
    artifact_png = os.path.join(ARTIFACT_DIR, "shanghai_hc_hangzhou_rb_seasonal.png")
    shutil.copyfile(out_png, artifact_png)
    
    print(f"[OK] 图表已生成:")
    print(f"  - 项目路径: {out_png}")
    print(f"  - 交互/展示路径: {artifact_png}")
    
    return out_png, artifact_png, pivot_df

if __name__ == "__main__":
    df = load_data()
    out_png, artifact_png, pivot_df = generate_seasonality_chart(df)
