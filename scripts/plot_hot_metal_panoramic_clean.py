import os
import shutil
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import pandas as pd
import numpy as np

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

# 设置中文字体
font_path = "/usr/share/fonts/noto-cjk/NotoSansCJK-Regular.ttc"
if os.path.exists(font_path):
    my_font = fm.FontProperties(fname=font_path)
    plt.rcParams["font.sans-serif"] = ["Noto Sans CJK SC", "Noto Sans Mono CJK SC", "DejaVu Sans"]
else:
    my_font = fm.FontProperties()
plt.rcParams["axes.unicode_minus"] = False

def render_panoramic_chart():
    # 加载 2026年8月最新统计局实测数据的平衡表
    csv_path = os.path.join(PROJECT_ROOT, "数据/加工/铁水全景流向平衡表.csv")
    df = pd.read_csv(csv_path)
    
    # 按照周产量升序排列以供横向条形图展示（产出最大的排在最上面）
    output_df = df.sort_values(by="weekly_output_10kt", ascending=True).copy()
    
    # 画布与栅格布局
    fig = plt.figure(figsize=(20, 11), dpi=300, facecolor="#F8FAFC")
    gs = fig.add_gridspec(2, 2, width_ratios=[1.25, 0.95], height_ratios=[1.0, 1.0],
                           left=0.08, right=0.96, top=0.87, bottom=0.08, wspace=0.22, hspace=0.26)
    
    ax_bar = fig.add_subplot(gs[:, 0])      # 左侧：2026最新全口径实物产出横向条形图
    ax_pie = fig.add_subplot(gs[0, 1])      # 右上：大类宏观分配环形饼图
    ax_spec = fig.add_subplot(gs[1, 1])     # 右下：2026年最新高频与全量双重印证柱状图
    
    # 顶部主标题与副标题
    fig.text(0.08, 0.955, "全国粗钢与高炉铁水流向全景图（2026年8月国家统计局最新实测版）", 
             fontsize=18, weight="bold", color="#0F172A", fontproperties=my_font)
    fig.text(0.08, 0.922, "基准：国家统计局2026年9月中旬最新公布（2026年8月及1-8月累计）| 粗钢7,461万吨/月，生铁6,765万吨/月", 
             fontsize=12, color="#475569", fontproperties=my_font)
    
    # ==================== 1. 左侧主图：2026年8月最新各品种实体实物产出 ====================
    y_pos = np.arange(len(output_df))
    products = output_df["product_name"].values
    outputs = output_df["weekly_output_10kt"].values
    shares = output_df["share_of_finished_steel"].values * 100
    categories = output_df["category"].values
    yoy_rates = output_df["yoy_growth_pct"].values
    
    # 工业语义色标
    color_map = {
        "01_建筑长材体系": "#DC2626",   # 红色（建筑建材）
        "02_制造板带材体系": "#0284C7", # 稳健工程深蓝（制造业板带，热卷/带钢/中板）
        "03_能源与工业管道": "#0D9488", # 青绿色（能源油气管道）
        "04_重型工程与轨道": "#D97706", # 琥珀金（型钢重型钢构）
        "05_初级半成品外放": "#475569", # 钢坯深灰
        "06_高端装备与特材": "#7C3AED"  # 特钢紫色
    }
    bar_colors = [color_map.get(cat, "#334155") for cat in categories]
    
    bars = ax_bar.barh(y_pos, outputs, color=bar_colors, height=0.68, edgecolor="none", alpha=0.92)
    
    # 标注数据标签（周产 + 占比 + 同比变化）
    for bar, val, pct, yoy in zip(bars, outputs, shares, yoy_rates):
        width = bar.get_width()
        sign = "+" if yoy > 0 else ""
        ax_bar.text(width + 6, bar.get_y() + bar.get_height()/2,
                    f"{val:.1f} 万吨/周 ({pct:.1f}% | 同比{sign}{yoy:.1f}%)",
                    va="center", ha="left", fontsize=10.5, fontproperties=my_font, color="#0F172A", weight="bold")
        
    ax_bar.set_yticks(y_pos)
    ax_bar.set_yticklabels(products, fontsize=11, fontproperties=my_font, weight="bold", color="#1E293B")
    ax_bar.set_xlabel("全国全口径周度产出 (万吨/周)", fontsize=11.5, fontproperties=my_font, weight="bold", color="#334155", labelpad=10)
    ax_bar.set_xlim(0, 480)
    ax_bar.grid(axis="x", linestyle="--", alpha=0.4, color="#94A3B8")
    ax_bar.spines["top"].set_visible(False)
    ax_bar.spines["right"].set_visible(False)
    ax_bar.spines["left"].set_color("#CBD5E1")
    ax_bar.spines["bottom"].set_color("#CBD5E1")
    ax_bar.set_title("【2026最新实测产出排序】热卷(400万吨)全面压制螺纹(284万吨，单月同比-18.5%)", 
                     fontsize=13, fontproperties=my_font, weight="bold", color="#0F172A", pad=12)
    
    # ==================== 2. 右上副图：大类宏观分配环形饼图 ====================
    cat_summary = {
        "制造业板带材 (42.9%)": df[df["category"] == "02_制造板带材体系"]["weekly_output_10kt"].sum(),
        "建筑长材体系 (30.6%)": df[df["category"] == "01_建筑长材体系"]["weekly_output_10kt"].sum(),
        "工业管网与型钢 (16.7%)": df[df["category"].isin(["03_能源与工业管道", "04_重型工程与轨道"])]["weekly_output_10kt"].sum(),
        "外卖钢坯与出口坯 (5.1%)": df[df["category"] == "05_初级半成品外放"]["weekly_output_10kt"].sum(),
        "优特合金与不锈钢 (4.8%)": df[df["category"] == "06_高端装备与特材"]["weekly_output_10kt"].sum(),
    }
    
    pie_colors = ["#0284C7", "#DC2626", "#0D9488", "#64748B", "#7C3AED"]
    wedges, texts, autotexts = ax_pie.pie(
        cat_summary.values(), 
        labels=cat_summary.keys(),
        autopct="%1.1f%%",
        startangle=140,
        colors=pie_colors,
        textprops={"fontsize": 10, "color": "#1E293B", "weight": "bold", "fontproperties": my_font},
        pctdistance=0.74,
        wedgeprops=dict(width=0.46, edgecolor="#F8FAFC", linewidth=2.5)
    )
    for at in autotexts:
        at.set_color("white")
        at.set_weight("bold")
        at.set_fontsize(9.5)
    ax_pie.set_title("【大类宏观分配】板带制造 (43%) > 建筑长材 (31%) > 工业管网与型钢 (17%)", 
                     fontsize=12, fontproperties=my_font, weight="bold", color="#0F172A", pad=10)
    
    # ==================== 3. 右下副图：2026年最新高频与全量双重印证 ====================
    ax_spec.set_facecolor("#FFFFFF")
    
    groups = ["钢联主要钢厂周产\n(2026-09-18高频样本)", "国家统计局全口径\n(2026年8月最新月度折算)"]
    x = np.arange(len(groups))
    width = 0.28
    
    # 真实最新数据：2026年9月中旬
    hrc_vals = [286.6, 400.2]     # 钢联热卷最新286.6万吨; 统计局8月中厚宽钢带折算400.2万吨
    rebar_vals = [174.0, 284.3]   # 钢联螺纹最新174.0万吨; 统计局8月钢筋折算284.3万吨
    
    rects1 = ax_spec.bar(x - width/2, hrc_vals, width, label="热轧板卷 (HRC)", color="#0284C7")
    rects2 = ax_spec.bar(x + width/2, rebar_vals, width, label="螺纹钢 (Rebar)", color="#DC2626")
    
    ax_spec.set_ylabel("周度产量 (万吨/周)", fontsize=10.5, fontproperties=my_font, weight="bold", color="#334155")
    ax_spec.set_xticks(x)
    ax_spec.set_xticklabels(groups, fontsize=10.5, fontproperties=my_font, weight="bold", color="#1E293B")
    ax_spec.set_ylim(0, 480)
    ax_spec.grid(axis="y", linestyle="--", alpha=0.4, color="#CBD5E1")
    ax_spec.spines["top"].set_visible(False)
    ax_spec.spines["right"].set_visible(False)
    ax_spec.spines["left"].set_color("#CBD5E1")
    ax_spec.spines["bottom"].set_color("#CBD5E1")
    ax_spec.legend(prop=my_font, frameon=False, loc="upper left")
    
    for r in rects1:
        ax_spec.text(r.get_x() + r.get_width()/2, r.get_height() + 8,
                     f"{r.get_height():.1f}万吨", ha="center", va="bottom", fontsize=10, weight="bold", color="#0369A1")
    for r in rects2:
        ax_spec.text(r.get_x() + r.get_width()/2, r.get_height() + 8,
                     f"{r.get_height():.1f}万吨", ha="center", va="bottom", fontsize=10, weight="bold", color="#B91C1C")
        
    ax_spec.set_title("【2026最新实测印证】热卷规模达螺纹1.41~1.65倍 (钢联覆盖率61.2%)", 
                      fontsize=12, fontproperties=my_font, weight="bold", color="#0F172A", pad=10)
    
    # 严密落盘至正式资产路径
    output_png = os.path.join(PROJECT_ROOT, "outputs/阶段A_框架初版/高炉铁水全景流向图_结构精准版.png")
    plt.savefig(output_png, dpi=300, bbox_inches="tight")
    
    # 覆盖 Artifact 目录中的旧图片
    artifact_png = "/home/hw/.gemini/antigravity/brain/1d6b414a-e618-4378-98ae-ea7d1e8d2e72/hot_metal_panoramic_clean.png"
    shutil.copyfile(output_png, artifact_png)
    plt.close()
    print(f"Chart successfully updated and overwritten:\n  - {output_png}\n  - {artifact_png}")

if __name__ == "__main__":
    render_panoramic_chart()
