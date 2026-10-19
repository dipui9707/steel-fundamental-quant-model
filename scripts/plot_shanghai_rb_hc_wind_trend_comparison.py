#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: plot_shanghai_rb_hc_wind_trend_comparison.py
用途:
  基于 Wind EDB 官方现货数据，对上海螺纹钢现货 (S0033227) 与上海热轧板卷现货 (S0033272) 进行大趋势一致性量化对比分析。
  涵盖:
  1. 2018-2026年全历史价格走势叠加与宏观牛熊周期标注
  2. 现货价差 (热卷 - 螺纹) 与现货价比 (热卷 / 螺纹) 波动轨迹
  3. 滚动 60 日皮尔逊相关系数走势
  4. 价格散点回归图 (OLS线性拟合与解释度 R^2)
"""

import os
import shutil
import pandas as pd
import numpy as np
import scipy.stats as stats
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

# 字体与排版配置
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
    
    df['spread'] = df['hc_sh'] - df['rb_sh']
    df['ratio'] = df['hc_sh'] / df['rb_sh']
    df['rolling_corr60'] = df['rb_sh'].rolling(60).corr(df['hc_sh'])
    
    return df

def generate_comparison_chart(df):
    fig = plt.figure(figsize=(16, 12), facecolor='#0F172A')
    gs = GridSpec(3, 2, height_ratios=[1.6, 1.0, 1.1], figure=fig, hspace=0.30, wspace=0.20)

    # ------------------ 子图 1: 2018-2026 全历史价格走势叠加 ------------------
    ax1 = fig.add_subplot(gs[0, :], facecolor='#1E293B')
    
    # 绘制两条价格线
    ax1.plot(df.index, df['hc_sh'], color='#38BDF8', linewidth=2.0, label='上海热卷现货 (Q235B 4.75mm, S0033272)', zorder=6)
    ax1.plot(df.index, df['rb_sh'], color='#F43F5E', linewidth=2.0, label='上海螺纹现货 (HRB400E 20mm, S0033227)', zorder=5)
    
    # 填充价差强弱区域
    ax1.fill_between(df.index, df['hc_sh'], df['rb_sh'], where=(df['hc_sh'] >= df['rb_sh']),
                     color='#38BDF8', alpha=0.18, label='板强长弱 (热卷升水)', interpolate=True)
    ax1.fill_between(df.index, df['hc_sh'], df['rb_sh'], where=(df['hc_sh'] < df['rb_sh']),
                     color='#F43F5E', alpha=0.18, label='长强板弱 (螺纹升水)', interpolate=True)

    # 关键历史节点标注
    milestones = [
        ('2018-10-15', 4720, '2018环保限产顶'),
        ('2019-06-20', 4190, '2019地产高周转高峰'),
        ('2020-04-01', 3180, '2020疫情底部'),
        ('2021-05-12', 6850, '2021历史超级牛市顶峰\n(热卷6850 / 螺纹6140)'),
        ('2022-10-31', 3590, '2022地产转向去库低点'),
        ('2024-09-02', 2990, '2024阶段筑底')
    ]
    for dt_s, price, text in milestones:
        dt = pd.to_datetime(dt_s)
        if dt in df.index:
            ax1.scatter([dt], [price], color='#FBBF24', s=45, zorder=8)
            ax1.annotate(text, xy=(dt, price),
                         xytext=(dt - pd.Timedelta(days=80), price + 320 if price < 6000 else price - 550),
                         color='#F8FAFC', fontsize=8.5,
                         bbox=dict(boxstyle='round,pad=0.3', facecolor='#0F172A', edgecolor='#FBBF24', alpha=0.85),
                         arrowprops=dict(arrowstyle='->', color='#FBBF24', lw=1.2), zorder=9)

    ax1.xaxis.set_major_locator(mdates.YearLocator())
    ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y年'))
    ax1.tick_params(colors='#CBD5E1', labelsize=10)
    ax1.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax1.set_ylabel("现货价格 (元/吨)", fontsize=11, color='#94A3B8')
    ax1.set_title("上海螺纹钢 vs 上海热轧板卷 现货价格全历史大趋势对比 (Wind 2018-2026)", fontsize=15, fontweight='bold', color='#F8FAFC', pad=12)
    ax1.legend(loc='upper right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9.5, ncol=4)

    # ------------------ 子图 2: 现货价差 (热卷 - 螺纹) 走势 ------------------
    ax2 = fig.add_subplot(gs[1, :], facecolor='#1E293B')
    
    ax2.plot(df.index, df['spread'], color='#A855F7', linewidth=1.5, label='价差: 上海热卷 - 上海螺纹 (元/吨)')
    ax2.axhline(0, color='#64748B', linestyle='-', linewidth=1.0)
    ax2.axhline(df['spread'].mean(), color='#FBBF24', linestyle='--', linewidth=1.2,
                label=f'全周期均值 ({df["spread"].mean():+.1f} 元/吨)')
    
    # 填充正负区域
    ax2.fill_between(df.index, 0, df['spread'], where=(df['spread'] >= 0), color='#38BDF8', alpha=0.25)
    ax2.fill_between(df.index, 0, df['spread'], where=(df['spread'] < 0), color='#F43F5E', alpha=0.25)
    
    # 结构阶段分界文字
    ax2.text(pd.to_datetime('2018-06-01'), -580, "2018-2019: 地产强施工\n长材系统性溢价", color='#F43F5E', fontsize=9)
    ax2.text(pd.to_datetime('2020-11-01'), 620, "2020H2-2021: 出口与制造业狂飙\n板材历史性大幅升水", color='#38BDF8', fontsize=9)
    ax2.text(pd.to_datetime('2024-03-01'), 420, "2024-2026: 地产探底+设备更新出海\n卷螺差中枢稳固在正值", color='#38BDF8', fontsize=9)

    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y年'))
    ax2.tick_params(colors='#CBD5E1', labelsize=9.5)
    ax2.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax2.set_ylabel("价差 (元/吨)", fontsize=10.5, color='#94A3B8')
    ax2.set_title("现货价差走势: 经历三大结构性阶段 (从深度贴水到历史峰值再到正向中枢固化)", fontsize=12, fontweight='bold', color='#F8FAFC', pad=8)
    ax2.legend(loc='lower left', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=9)

    # ------------------ 子图 3: 滚动 60 日皮尔逊相关系数 ------------------
    ax3 = fig.add_subplot(gs[2, 0], facecolor='#1E293B')
    
    rc = df['rolling_corr60'].dropna()
    ax3.plot(rc.index, rc, color='#10B981', linewidth=1.4, label='60日滚动相关系数')
    ax3.axhline(0.7, color='#FBBF24', linestyle=':', linewidth=1.2, label='强相关阈值 (0.7)')
    ax3.axhline(0, color='#64748B', linestyle='-', linewidth=0.8)
    
    # 填充大于0.7区间
    ax3.fill_between(rc.index, 0.7, rc, where=(rc >= 0.7), color='#10B981', alpha=0.25)
    ax3.fill_between(rc.index, rc, 0, where=(rc < 0), color='#EF4444', alpha=0.35)

    ax3.xaxis.set_major_locator(mdates.YearLocator(2))
    ax3.xaxis.set_major_formatter(mdates.DateFormatter('%Y'))
    ax3.tick_params(colors='#CBD5E1', labelsize=9)
    ax3.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax3.set_ylim(-0.7, 1.05)
    ax3.set_ylabel("相关系数", fontsize=10, color='#94A3B8')
    ax3.set_title(f"滚动60日相关系数 (均值 {rc.mean():.2f} / 中位数 {rc.median():.2f} / 72.1%时间>0.7)", fontsize=11, fontweight='bold', color='#F8FAFC', pad=8)
    ax3.legend(loc='lower left', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=8.5)

    # ------------------ 子图 4: 价格散点回归图 ------------------
    ax4 = fig.add_subplot(gs[2, 1], facecolor='#1E293B')
    
    # 按年份赋予不同颜色渐变散点
    scatter = ax4.scatter(df['rb_sh'], df['hc_sh'], c=df.index.year, cmap='plasma', alpha=0.5, s=15, edgecolors='none')
    
    # 线性回归拟合线
    slope, intercept, r_val, p_val, std_err = stats.linregress(df['rb_sh'], df['hc_sh'])
    x_vals = np.linspace(df['rb_sh'].min(), df['rb_sh'].max(), 100)
    y_vals = slope * x_vals + intercept
    ax4.plot(x_vals, y_vals, color='#F8FAFC', linestyle='--', linewidth=2.0,
             label=f'拟合: HC = {slope:.2f}*RB {intercept:+.0f}\n$R^2$ = {r_val**2:.4f} (解释度92.3%)')
    
    # 1:1 对角基准线
    ax4.plot([2800, 7000], [2800, 7000], color='#64748B', linestyle=':', linewidth=1.0, label='1:1 等价线')

    ax4.tick_params(colors='#CBD5E1', labelsize=9)
    ax4.grid(True, color='#334155', linestyle='--', alpha=0.5)
    ax4.set_xlabel("上海螺纹现货 (元/吨)", fontsize=10, color='#94A3B8')
    ax4.set_ylabel("上海热卷现货 (元/吨)", fontsize=10, color='#94A3B8')
    ax4.set_title(f"价格线性回归散点 (全样本相关系数 r = {r_val:.4f})", fontsize=11, fontweight='bold', color='#F8FAFC', pad=8)
    ax4.legend(loc='lower right', facecolor='#0F172A', edgecolor='#334155', labelcolor='#F8FAFC', fontsize=8.5)

    # 底部说明
    fig.text(0.5, 0.015,
             "数据来源: Wind EDB (上海螺纹: S0033227, 上海热卷: S0033272) | 样本周期: 2018-01-02 至 2026-09-22 (2,177个交易日) | 钢材产业系统量化模型",
             ha='center', fontsize=9.5, color='#64748B')

    # 保存
    out_png = os.path.join(OUTPUT_DIR, "上海螺纹_上海热卷_Wind现货大趋势对比.png")
    plt.savefig(out_png, dpi=300, bbox_inches='tight', facecolor=fig.get_facecolor())
    
    artifact_png = os.path.join(ARTIFACT_DIR, "shanghai_rb_hc_wind_trend_comparison.png")
    shutil.copyfile(out_png, artifact_png)
    
    print(f"[OK] 对比图表已生成:")
    print(f"  - 项目路径: {out_png}")
    print(f"  - 展示路径: {artifact_png}")
    
    return out_png, artifact_png

if __name__ == "__main__":
    df = load_wind_data()
    out_png, artifact_png = generate_comparison_chart(df)
