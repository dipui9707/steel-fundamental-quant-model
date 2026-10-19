#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: plot_shanghai_rb_hc_seasonality.py
用途:
  基于 Wind EDB 官方现货数据，制作上海螺纹钢现货与上海热轧板卷现货的按年划分季节图（2018-2026），
  并深入量化对比两者的年内季节性规律、胜率分布与趋势一致性。
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

def load_wind_data():
    wind_path = os.path.join(PROJECT_ROOT, "数据/原始/wind_edb/wind_edb_all.parquet")
    df_wind = pd.read_parquet(wind_path)
    
    rb = df_wind[df_wind['code'] == 'S0033227'].set_index('data_date')['value'].rename('rb_sh')
    hc = df_wind[df_wind['code'] == 'S0033272'].set_index('data_date')['value'].rename('hc_sh')
    
    df = pd.concat([rb, hc], axis=1).dropna()
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df

def generate_seasonality_comparison(df):
    ref_dates = pd.date_range('2024-01-01', '2024-12-31', freq='D')
    ref_mm_dd = ref_dates.strftime('%m-%d')
    
    piv_rb = pd.DataFrame(index=ref_mm_dd)
    piv_hc = pd.DataFrame(index=ref_mm_dd)
    
    years = list(range(2018, 2027))
    for y in years:
        start_d = f'{y}-01-01'
        end_d = f'{y}-12-31'
        cal_days = pd.date_range(start_d, end_d, freq='D')
        sub = df.loc[(df.index >= start_d) & (df.index <= end_d)]
        
        s_rb = sub['rb_sh'].reindex(cal_days).ffill().bfill()
        s_hc = sub['hc_sh'].reindex(cal_days).ffill().bfill()
        s_rb.index = s_rb.index.strftime('%m-%d')
        s_hc.index = s_hc.index.strftime('%m-%d')
        
        if y == 2026:
            max_dt = df.loc[df.index.year == 2026].index.max().strftime('%m-%d')
            s_rb = s_rb[s_rb.index <= max_dt]
            s_hc = s_hc[s_hc.index <= max_dt]
            
        piv_rb[str(y)] = s_rb
        piv_hc[str(y)] = s_hc

    # 计算 2021-2025 5年均值
    hist_5y = ['2021', '2022', '2023', '2024', '2025']
    piv_rb['5Y_Avg'] = piv_rb[hist_5y].mean(axis=1)
    piv_hc['5Y_Avg'] = piv_hc[hist_5y].mean(axis=1)

    # 绑定绘图日期
    plot_rb = piv_rb.copy()
    plot_rb['plot_date'] = ref_dates
    plot_rb = plot_rb.set_index('plot_date')

    plot_hc = piv_hc.copy()
    plot_hc['plot_date'] = ref_dates
    plot_hc = plot_hc.set_index('plot_date')

    # 计算月度涨跌幅统计
    m_df = df.resample('ME').last()
    m_ret = m_df.pct_change() * 100
    m_ret['month'] = m_ret.index.month
    m_mean = m_ret.groupby('month')[['rb_sh', 'hc_sh']].mean()
    m_win = m_ret.groupby('month')[['rb_sh', 'hc_sh']].apply(lambda g: (g > 0).mean() * 100)

    # ================= 绘图开始 =================
    fig = plt.figure(figsize=(18, 12), facecolor='#0F172A')
    gs = GridSpec(2, 2, height_ratios=[1.2, 1.0], width_ratios=[1.0, 1.0], figure=fig, hspace=0.28, wspace=0.18)

    color_palette = {
        '2018': '#64748B',  # 灰
        '2019': '#94A3B8',  # 灰蓝
        '2020': '#0284C7',  # 蓝
        '2021': '#8B5CF6',  # 紫 (超级牛市峰顶)
        '2022': '#0D9488',  # 青绿
        '2023': '#10B981',  # 绿
        '2024': '#F59E0B',  # 琥珀金
        '2025': '#F97316',  # 橙
        '2026': '#EF4444',  # 鲜红 (2026最新)
    }

    # ------------------ 图 1: 上海螺纹现货按年季节图 ------------------
    ax1 = fig.add_subplot(gs[0, 0], facecolor='#1E293B')
    
    # 5年均值
    ax1.plot(plot_rb.index, plot_rb['5Y_Avg'], color='#CBD5E1', linestyle='--', linewidth=2.0,
             label='2021-2025 五年均值', zorder=7)
    
    for y in [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
        col = str(y)
        ls = ':' if y in [2018, 2019] else '-'
        lw = 1.2 if y in [2018, 2019] else 1.6
        alpha = 0.55 if y in [2018, 2019] else 0.8
        ax1.plot(plot_rb.index, plot_rb[col], color=color_palette[col], linestyle=ls,
                 linewidth=lw, alpha=alpha, label=f'{y}年')
        
    valid_rb_2026 = plot_rb['2026'].dropna()
    ax1.plot(valid_rb_2026.index, valid_rb_2026, color=color_palette['2026'], linewidth=3.2,
             label='2026年 (最新)', zorder=10)
    
    # 最新点标注
    latest_x = valid_rb_2026.index[-1]
    latest_rb_y = valid_rb_2026.iloc[-1]
    ax1.scatter([latest_x], [latest_rb_y], color='#EF4444', s=70, edgecolors='#FFFFFF', linewidth=1.5, zorder=12)
    ax1.annotate(f"2026最新: {latest_rb_y:.0f} 元/吨",
                 xy=(latest_x, latest_rb_y),
                 xytext=(latest_x - pd.Timedelta(days=55), latest_rb_y + 450),
                 color='#FFFFFF', fontsize=9.5, fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='#EF4444', edgecolor='#FFFFFF', alpha=0.9),
                 arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=-0.15', color='#FFFFFF', lw=1.2),
                 zorder=15)

    ax1.xaxis.set_major_locator(mdates.MonthLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    ax1.set_xlim(pd.to_datetime('2024-01-01'), pd.to_datetime('2024-12-31'))
    ax1.set_ylim(2800, 6500)
    ax1.tick_params(colors='#CBD5E1', labelsize=9.5)
    ax1.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax1.set_ylabel("现货价格 (元/吨)", fontsize=11, color='#94A3B8')
    ax1.set_title("上海螺纹钢现货 按年划分季节图 (2018-2026)", fontsize=13, fontweight='bold', color='#F8FAFC', pad=10)
    ax1.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=8, ncol=3)

    # ------------------ 图 2: 上海热卷现货按年季节图 ------------------
    ax2 = fig.add_subplot(gs[0, 1], facecolor='#1E293B')
    
    ax2.plot(plot_hc.index, plot_hc['5Y_Avg'], color='#CBD5E1', linestyle='--', linewidth=2.0,
             label='2021-2025 五年均值', zorder=7)
    
    for y in [2018, 2019, 2020, 2021, 2022, 2023, 2024, 2025]:
        col = str(y)
        ls = ':' if y in [2018, 2019] else '-'
        lw = 1.2 if y in [2018, 2019] else 1.6
        alpha = 0.55 if y in [2018, 2019] else 0.8
        ax2.plot(plot_hc.index, plot_hc[col], color=color_palette[col], linestyle=ls,
                 linewidth=lw, alpha=alpha, label=f'{y}年')
        
    valid_hc_2026 = plot_hc['2026'].dropna()
    ax2.plot(valid_hc_2026.index, valid_hc_2026, color=color_palette['2026'], linewidth=3.2,
             label='2026年 (最新)', zorder=10)
    
    latest_hc_y = valid_hc_2026.iloc[-1]
    ax2.scatter([latest_x], [latest_hc_y], color='#EF4444', s=70, edgecolors='#FFFFFF', linewidth=1.5, zorder=12)
    ax2.annotate(f"2026最新: {latest_hc_y:.0f} 元/吨",
                 xy=(latest_x, latest_hc_y),
                 xytext=(latest_x - pd.Timedelta(days=55), latest_hc_y + 450),
                 color='#FFFFFF', fontsize=9.5, fontweight='bold',
                 bbox=dict(boxstyle='round,pad=0.3', facecolor='#EF4444', edgecolor='#FFFFFF', alpha=0.9),
                 arrowprops=dict(arrowstyle='->', connectionstyle='arc3,rad=-0.15', color='#FFFFFF', lw=1.2),
                 zorder=15)

    ax2.xaxis.set_major_locator(mdates.MonthLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    ax2.set_xlim(pd.to_datetime('2024-01-01'), pd.to_datetime('2024-12-31'))
    ax2.set_ylim(2800, 7100)
    ax2.tick_params(colors='#CBD5E1', labelsize=9.5)
    ax2.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax2.set_ylabel("现货价格 (元/吨)", fontsize=11, color='#94A3B8')
    ax2.set_title("上海热轧板卷现货 按年划分季节图 (2018-2026)", fontsize=13, fontweight='bold', color='#F8FAFC', pad=10)
    ax2.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=8, ncol=3)

    # ------------------ 图 3: 螺纹 vs 热卷 季节性均值与2026年走势直接同框对比 ------------------
    ax3 = fig.add_subplot(gs[1, 0], facecolor='#1E293B')
    
    # 绘制5年均值对比
    ax3.plot(plot_rb.index, plot_rb['5Y_Avg'], color='#F43F5E', linestyle='--', linewidth=2.2,
             label='螺纹: 2021-2025 五年均值')
    ax3.plot(plot_hc.index, plot_hc['5Y_Avg'], color='#38BDF8', linestyle='--', linewidth=2.2,
             label='热卷: 2021-2025 五年均值')
    
    # 绘制2026年实际对比
    ax3.plot(valid_rb_2026.index, valid_rb_2026, color='#F43F5E', linestyle='-', linewidth=3.0,
             label='螺纹: 2026年实际走势')
    ax3.plot(valid_hc_2026.index, valid_hc_2026, color='#38BDF8', linestyle='-', linewidth=3.0,
             label='热卷: 2026年实际走势')

    # 关键季节性窗口高亮区
    ax3.axvspan(pd.to_datetime('2024-03-15'), pd.to_datetime('2024-04-30'),
                color='#10B981', alpha=0.12, label='春季旺季开工期 (两者同向上涨)')
    ax3.axvspan(pd.to_datetime('2024-06-01'), pd.to_datetime('2024-08-31'),
                color='#F59E0B', alpha=0.10, label='夏季淡季 (螺纹停工走弱, 热卷抗跌)')

    ax3.xaxis.set_major_locator(mdates.MonthLocator(bymonth=range(1, 13, 2)))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%m月'))
    ax3.set_xlim(pd.to_datetime('2024-01-01'), pd.to_datetime('2024-12-31'))
    ax3.set_ylim(2900, 5200)
    ax3.tick_params(colors='#CBD5E1', labelsize=9.5)
    ax3.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax3.set_ylabel("现货价格 (元/吨)", fontsize=11, color='#94A3B8')
    ax3.set_title("螺纹 vs 热卷 季节性节律同框对比 (五年均值 & 2026最新)", fontsize=12, fontweight='bold', color='#F8FAFC', pad=10)
    ax3.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=8.5)

    # ------------------ 图 4: 1-12月月均涨跌幅与季节规律对比柱状图 ------------------
    ax4 = fig.add_subplot(gs[1, 1], facecolor='#1E293B')
    
    x_months = np.arange(1, 13)
    width = 0.38
    
    # 柱状图
    rects1 = ax4.bar(x_months - width/2, m_mean['rb_sh'], width, color='#F43F5E', alpha=0.85, label='螺纹 月均涨跌幅(%)')
    rects2 = ax4.bar(x_months + width/2, m_mean['hc_sh'], width, color='#38BDF8', alpha=0.85, label='热卷 月均涨跌幅(%)')
    
    # 在柱上方/下方标注数值
    for rect in rects1:
        h = rect.get_height()
        va = 'bottom' if h >= 0 else 'top'
        ax4.text(rect.get_x() + rect.get_width()/2., h + (0.15 if h>=0 else -0.3),
                 f"{h:+.1f}%", ha='center', va=va, fontsize=7.5, color='#CBD5E1')
        
    for rect in rects2:
        h = rect.get_height()
        va = 'bottom' if h >= 0 else 'top'
        ax4.text(rect.get_x() + rect.get_width()/2., h + (0.15 if h>=0 else -0.3),
                 f"{h:+.1f}%", ha='center', va=va, fontsize=7.5, color='#CBD5E1')

    ax4.axhline(0, color='#64748B', linestyle='-', linewidth=0.8)
    ax4.set_xticks(x_months)
    ax4.set_xticklabels([f'{m}月' for m in range(1, 13)])
    ax4.tick_params(colors='#CBD5E1', labelsize=9.5)
    ax4.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax4.set_ylim(-3.8, 4.8)
    ax4.set_ylabel("月均涨跌幅 (%)", fontsize=11, color='#94A3B8')
    ax4.set_title("1-12月 季节性月均涨跌幅对比 (4月同涨 / 5-6月与10月同跌 / 9月与12月背离)", fontsize=12, fontweight='bold', color='#F8FAFC', pad=10)
    ax4.legend(loc='lower left', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9)

    # 底部说明
    fig.text(0.5, 0.015,
             "数据来源: Wind EDB (上海螺纹现货: S0033227, 上海热卷现货: S0033272) | 统计区间: 2018-01-02 至 2026-09-22 | 钢材产业系统量化模型",
             ha='center', fontsize=9.5, color='#64748B')

    # 输出保存
    out_png = os.path.join(OUTPUT_DIR, "上海螺纹_上海热卷_Wind现货季节性对比.png")
    plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
    
    artifact_png = os.path.join(ARTIFACT_DIR, "shanghai_rb_hc_wind_seasonality_comparison.png")
    shutil.copyfile(out_png, artifact_png)
    
    print(f"[OK] 季节性对比图已生成:")
    print(f"  - 项目路径: {out_png}")
    print(f"  - 展示路径: {artifact_png}")
    
    return out_png, artifact_png

if __name__ == "__main__":
    df = load_wind_data()
    out_png, artifact_png = generate_seasonality_comparison(df)
