#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: build_coil_rebar_pdf_report.py
用途:
  基于项目实录权威数据与 Wind EDB 官方现货数据，生成专业级 PDF 专题研究报告:
  《热卷现货深度解析与卷螺差演化专题量化报告 (2024–2026)》
"""

import os
import shutil
import weasyprint

PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
ARTIFACT_DIR = "/home/hw/.gemini/antigravity/brain/78cbb79d-10e8-49b1-a7f1-b02789ba9c27"
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "研究/现货价差专题")
PDF_FIG_DIR = os.path.join(OUTPUT_DIR, "pdf_figures")

PDF_OUTPUT_PROJECT = os.path.join(OUTPUT_DIR, "热卷现货与卷螺差专题量化研究报告_2024-2026.pdf")
PDF_OUTPUT_ARTIFACT = os.path.join(ARTIFACT_DIR, "热卷现货与卷螺差专题量化研究报告_2024-2026.pdf")

fig1_path = os.path.join(PDF_FIG_DIR, "fig1_3y_hc_spot_regional.png")
fig2_path = os.path.join(PDF_FIG_DIR, "fig2_3y_coil_rebar_spread_seasonality.png")
fig3_path = os.path.join(PDF_FIG_DIR, "fig3_2026_recent_dynamics.png")

html_content = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>热卷现货深度解析与卷螺差演化专题量化报告 (2024-2026)</title>
<style>
  @page {{
    size: A4 portrait;
    margin: 14mm 15mm 14mm 15mm;
    @top-left {{
      content: "钢材产业系统量化模型 · 现货基本面专题";
      font-size: 8pt;
      font-family: 'Noto Sans CJK SC', sans-serif;
      color: #64748b;
      border-bottom: 0.5pt solid #cbd5e1;
      padding-bottom: 3px;
    }}
    @top-right {{
      content: "研判日期: 2026年9月23日";
      font-size: 8pt;
      font-family: 'Noto Sans CJK SC', sans-serif;
      color: #64748b;
      border-bottom: 0.5pt solid #cbd5e1;
      padding-bottom: 3px;
    }}
    @bottom-center {{
      content: "第 " counter(page) " 页 / 共 " counter(pages) " 页";
      font-size: 8pt;
      font-family: 'Noto Sans CJK SC', sans-serif;
      color: #94a3b8;
    }}
  }}

  body {{
    font-family: 'Noto Serif CJK SC', 'Noto Sans CJK SC', 'Source Han Serif SC', serif;
    color: #1e293b;
    line-height: 1.5;
    font-size: 9pt;
  }}

  h1, h2, h3, h4, th, .sans {{
    font-family: 'Noto Sans CJK SC', 'Source Han Sans SC', sans-serif;
  }}

  .header-box {{
    border-bottom: 2pt solid #0284c7;
    padding-bottom: 8px;
    margin-bottom: 12px;
  }}

  .report-tag {{
    display: inline-block;
    background-color: #e0f2fe;
    color: #0369a1;
    font-size: 7.5pt;
    font-weight: bold;
    padding: 2px 7px;
    border-radius: 4px;
    margin-bottom: 4px;
  }}

  h1 {{
    font-size: 17pt;
    color: #0f172a;
    margin: 2px 0 6px 0;
    line-height: 1.25;
  }}

  .subtitle {{
    font-size: 9.5pt;
    color: #475569;
    margin: 0;
  }}

  .meta-grid {{
    display: table;
    width: 100%;
    margin-top: 8px;
    font-size: 8pt;
    color: #64748b;
    background: #f8fafc;
    border: 0.5pt solid #e2e8f0;
    border-radius: 4px;
    padding: 5px 8px;
  }}
  .meta-cell {{
    display: table-cell;
    width: 25%;
  }}

  .alert-box {{
    background-color: #f0fdf4;
    border-left: 3pt solid #16a34a;
    padding: 7px 10px;
    margin: 10px 0;
    font-size: 8.5pt;
    border-radius: 0 4px 4px 0;
  }}
  .alert-title {{
    font-weight: bold;
    color: #15803d;
    margin-bottom: 3px;
  }}

  .alert-warning {{
    background-color: #fffbeb;
    border-left: 3pt solid #f59e0b;
  }}
  .alert-warning .alert-title {{
    color: #b45309;
  }}

  h2 {{
    font-size: 11pt;
    color: #0f172a;
    border-left: 3pt solid #0284c7;
    padding-left: 7px;
    margin: 12px 0 6px 0;
  }}

  h3 {{
    font-size: 9.5pt;
    color: #1e293b;
    margin: 8px 0 4px 0;
  }}

  p {{
    margin: 4px 0;
    text-align: justify;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0;
    font-size: 8pt;
    page-break-inside: avoid;
  }}

  th, td {{
    border: 0.5pt solid #cbd5e1;
    padding: 4px 6px;
    text-align: center;
  }}

  th {{
    background-color: #f1f5f9;
    color: #334155;
    font-weight: bold;
  }}

  tr:nth-child(even) td {{
    background-color: #f8fafc;
  }}

  .highlight-cell {{
    font-weight: bold;
    color: #dc2626;
  }}

  .figure-container {{
    text-align: center;
    margin: 8px 0 10px 0;
    page-break-inside: avoid;
  }}

  .figure-img {{
    width: 100%;
    border: 0.5pt solid #cbd5e1;
    border-radius: 4px;
  }}

  .figure-caption {{
    font-size: 7.5pt;
    color: #64748b;
    margin-top: 3px;
    font-style: italic;
  }}

  .page-break {{
    page-break-before: always;
  }}
</style>
</head>
<body>

  <!-- ==================== 第 1 页: 概览与近期核心特征 ==================== -->
  <div class="header-box">
    <div class="report-tag sans">钢材产业量化研究系列报告 · 现货基本面深度篇</div>
    <h1>热卷现货深度解析与卷螺差演化量化报告</h1>
    <div class="subtitle sans">基于华东与全国主流现货市场高频数据，聚焦2026年9月最新格局及近3年演变</div>
    <div class="meta-grid sans">
      <div class="meta-cell"><strong>研究对象:</strong> 热轧板卷现货 / 卷螺差</div>
      <div class="meta-cell"><strong>基准时点:</strong> 2026年9月22日收盘</div>
      <div class="meta-cell"><strong>数据体系:</strong> 实录现货 & Wind EDB</div>
      <div class="meta-cell"><strong>模型版本:</strong> framework-0.3-candidate</div>
    </div>
  </div>

  <div class="alert-box sans">
    <div class="alert-title">【执行摘要与核心研判】</div>
    <p>1. <strong>最新现货行情定性（2026-09-22）</strong>：热卷现货正由7–8月的<strong>“夏季超额溢价期”</strong>加速步入<strong>“金九顺季节性急剧收敛期”</strong>。上海热卷现货收于 <strong>3,310 元/吨</strong>（Wind本地报 3,290 元/吨），上海同城卷螺差已从8月下旬的 +200~+220 元/吨断崖式收窄至当前的 <strong>+20 元/吨</strong>（接近平水状态）；跨区卷螺差（上海热卷 - 杭州螺纹）亦从年内峰值 +280 元/吨回落至 <strong>+150 元/吨</strong>。</p>
    <p>2. <strong>热卷近期核心矛盾</strong>：<strong>高仓单压制 + 钢厂长流程深亏 + 建筑长材阶段性抢工</strong>。热卷期货仓单虽自8月历史极值（62.7万吨）有所回落，但目前仍高达 <strong>18.47 万吨</strong>（对比螺纹仅 7.34 万吨），高额仓单集中压制华东现货交割与去库节奏；华东长流程利润最新深幅亏损达 <strong>-117 元/吨</strong>，原料负反馈与成本塌陷风险压制钢厂生产积极性。</p>
    <p>3. <strong>近3年纵向对比（2024–2026）</strong>：热卷现货经历“2024宽幅深跌切换（4090→3000）→ 2025窄幅箱体沉淀（均价3332）→ 2026外需分化与供需博弈（当前3310）”。板材对长材的绝对溢价在中枢上保持韧性，但年内面临明显的季节性高低切换。</p>
  </div>

  <h2>一、 2026年近期（8–9月）热卷现货市场运行特征剖析</h2>
  <p>进入2026年三季度，热卷现货基本面呈现出极强的阶段性演化特征，先后经历了从外需支撑下的“淡季不淡”到金九开工期的“长强板弱”剧烈重塑：</p>

  <h3>1. 价格走势由升水高位向平水加速回落</h3>
  <p>在7月中旬至8月下旬，受海外板材接单旺盛（天津港FOB出口报价稳于490–497美元/吨）及国内设备更新政策预期催化，热卷现货表现出极强抗跌性，上海价格稳定在 3,380~3,450 元/吨，较螺纹钢持续维持 +200 元/吨以上的溢价。但进入9月上旬后，随着秋季施工黄金期启动，螺纹现货自 3,120 强力反弹至 3,160~3,270 元/吨，而热卷现货受累于内需增量有限及高库存抛压，价格自 3,380 震荡下挫至 3,310 元/吨，<strong>卷螺差在两周内被动收窄超 150 元/吨</strong>。</p>

  <h3>2. 巨量期货仓单与交割压力向现货库区倾泻</h3>
  <p>热卷近期最为显著的结构性矛盾在于交割仓单的畸高积累。2026年8月中旬热卷期货注册仓单曾一度冲破 <strong>62.7 万吨</strong>的历史极端天量。截至9月22日，热卷仓单仍滞留 <strong>18.47 万吨</strong>（9月16日曾反弹至 22.07 万吨），远超螺纹钢的 7.34 万吨。高额仓单表明现货贸易商与钢厂选择利用期货盘面锁定基差并大规模注册交割，加剧了华东主要交割仓库的货品积压与出库摩擦。</p>

  <h3>3. 钢厂长流程深幅亏损与铁水倒逼机制</h3>
  <p>根据《每日现货.xlsx》微观跟踪模型，当前华东铁水成本高达 2,650~2,700 元/吨，长流程螺卷综合生产成本在 3,420~3,450 元/吨附近，<strong>华东长流程钢厂每吨现货亏损扩大至 -117 元/吨</strong>（2025年同期为微利 +92 元/吨）。钢厂全面陷入亏损压制了铁水增产空间，热卷周产量自8月的 295 万吨回落至 286.59 万吨，但由于板材转产长材存在物理滞后，供给收缩尚未能扭转现货高库存格局。</p>

  <div class="page-break"></div>

  <!-- ==================== 第 2 页: 近期走势图表与全国区域现货联动 ==================== -->
  <div class="figure-container">
    <img src="{fig3_path}" class="figure-img" alt="2026年近期动态监控" />
    <div class="figure-caption">图 1: 2026年近期 (5月-9月) 上海热卷现货、期货交割仓单与华东长流程利润动态演化</div>
  </div>

  <h2>二、 全国主流区域热卷现货联动与跨区价差</h2>
  <p>热卷作为标准化大宗工业品，全国流通性极强。从上海、乐从（华南）、天津（北方）、武汉（华中）四大主流枢纽的现货联动来看，近期呈现出以下典型特征：</p>

  <table>
    <thead>
      <tr>
        <th>区域集散地</th>
        <th>主流基准规格</th>
        <th>2026-09-22 现货价</th>
        <th>近1个月变动</th>
        <th>相对上海价差</th>
        <th>区域流通与供需特征</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>上海 (华东)</strong></td>
        <td>Q235B 4.75mm</td>
        <td><strong>3,310 元/吨</strong></td>
        <td>-70 元/吨</td>
        <td>基准 (0)</td>
        <td>全国金融与现货交割枢纽，受交割仓单流动性冲击最直接</td>
      </tr>
      <tr>
        <td><strong>乐从 (华南)</strong></td>
        <td>Q235B 4.75mm</td>
        <td><strong>3,300 元/吨</strong></td>
        <td>-60 元/吨</td>
        <td>-10 元/吨</td>
        <td>华南家电、五金加工集聚区，内需平淡，对华东溢价窗口消失</td>
      </tr>
      <tr>
        <td><strong>天津 (北方)</strong></td>
        <td>Q235B 4.75mm</td>
        <td><strong>3,260 元/吨</strong></td>
        <td>-80 元/吨</td>
        <td>-50 元/吨</td>
        <td>华北主要集散地与出口离岸腹地，价格偏低，北材南下暂无利润</td>
      </tr>
      <tr>
        <td><strong>武汉 (华中)</strong></td>
        <td>Q235B 4.75mm</td>
        <td><strong>3,330 元/吨</strong></td>
        <td>-50 元/吨</td>
        <td>+20 元/吨</td>
        <td>九省通衢，武钢等本地直供占比高，汽车制造采购支撑价位</td>
      </tr>
      <tr>
        <td><strong>成都 (西南)</strong></td>
        <td>Q235B 4.75mm</td>
        <td><strong>3,410 元/吨</strong></td>
        <td>-40 元/吨</td>
        <td>+100 元/吨</td>
        <td>内陆封闭市场，包含运费溢价，受外省材调入成本强支撑</td>
      </tr>
    </tbody>
  </table>

  <p><strong>跨区套利窗口研判</strong>：通常天津至上海/乐从的汽运与水运运费在 <strong>120~150 元/吨</strong>。目前“上海 - 天津”价差仅为 <strong>50 元/吨</strong>，“乐从 - 天津”价差仅为 <strong>40 元/吨</strong>，南北价差严重收窄，<strong>北方热卷主动向华东、华南跨区发货的套利窗口完全关闭</strong>。这表明当前并非北材冲击，而是沿海主要集散地自身的高库存与下游消化缓慢所致。</p>

  <div class="page-break"></div>

  <!-- ==================== 第 3 页: 近三年现货运行与卷螺差演变对比 ==================== -->
  <div class="figure-container">
    <img src="{fig1_path}" class="figure-img" alt="全国主流区域热卷现货对比" />
    <div class="figure-caption">图 2: 近3年 (2024-2026) 全国主流区域热卷现货价格走势与跨区套利价差</div>
  </div>

  <h2>三、 近三年（2024–2026）热卷现货与卷螺差演变对比</h2>
  <p>纵观 2024、2025、2026 最近三年的现货运行，整个钢铁产业历经了自大牛市退潮后的产能出清与结构重塑：</p>

  <table>
    <thead>
      <tr>
        <th>年份</th>
        <th>上海热卷均价</th>
        <th>年内极端区间</th>
        <th>同城卷螺差均值</th>
        <th>卷螺差极端区间</th>
        <th>热卷仓单均值</th>
        <th>长流程利润均值</th>
        <th>阶段性宏观与产业主线</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>2024年</strong></td>
        <td>3,644.8 元/吨</td>
        <td>3000 ~ 4090</td>
        <td><strong>+99.2 元/吨</strong></td>
        <td>-200 ~ +340</td>
        <td>29.1 万吨</td>
        <td>-12.0 元/吨</td>
        <td>高波动宽幅出清；秋季新国标交替，长材赶工导致价差骤降至负值</td>
      </tr>
      <tr>
        <td><strong>2025年</strong></td>
        <td>3,332.5 元/吨</td>
        <td>3160 ~ 3500</td>
        <td><strong>+76.0 元/吨</strong></td>
        <td>-80 ~ +200</td>
        <td>18.5 万吨</td>
        <td>+92.4 元/吨</td>
        <td>极度收敛的低波动箱体；全行业供需暂平衡，热卷保持稳定溢价</td>
      </tr>
      <tr>
        <td><strong>2026年至今</strong></td>
        <td>3,327.7 元/吨</td>
        <td>3230 ~ 3520</td>
        <td><strong>+102.1 元/吨</strong></td>
        <td>-60 ~ +220</td>
        <td><strong>37.4 万吨</strong></td>
        <td>+20.0 元/吨</td>
        <td>外需超预期但高仓单压制；夏季热卷极强，9月金九强力顺势收敛</td>
      </tr>
    </tbody>
  </table>

  <p><strong>三年演化对比核心结论</strong>：
    <br>1. <strong>价格中枢持续下移但企稳于 3,300 元/吨关口</strong>：相较于 2024 年 3,645 元/吨的均价，2025–2026 年热卷价格中枢回落约 300 元/吨，并在 3,200~3,500 元/吨区间构筑了长周期的估值平台。
    <br>2. <strong>板材相对长材溢价长期存在但波动加剧</strong>：三年上海同城卷螺差年均值分别达到 +99.2、+76.0、+102.1 元/吨，板材凭借新能源汽车、白色家电和强劲出口需求持续享有物理工序溢价。然而在三季度向四季度转换期，极易受到螺纹秋季短暂供需错配的冲击而发生均值回归。
  </p>

  <div class="page-break"></div>

  <!-- ==================== 第 4 页: 季节性走势、机制映射与策略推演 ==================== -->
  <div class="figure-container">
    <img src="{fig2_path}" class="figure-img" alt="近3年现货卷螺差对比" />
    <div class="figure-caption">图 3: 近3年 (2024-2026) 上海同城现货卷螺差与华东跨区卷螺差季节走势对比</div>
  </div>

  <h2>四、 卷螺差机制映射与后市推演</h2>
  <div class="alert-box alert-warning sans">
    <div class="alert-title">【因果模型机制映射：A02.1 铁水配置与 A02.2 卷螺分配】</div>
    <p>• <strong>边际铁水流向天平</strong>：联合钢厂的板材轧制线相对长材通常具有 100~150 元/吨的物理工序超额成本。当卷螺差超过 <strong>+200 元/吨</strong> 时，钢厂边际铁水倾向于优先保证热卷，从而抑制长材供给，推升长材弹性；当卷螺差回落至 <strong>0 轴附近（如当前上海同城 +20 元/吨）</strong> 时，热卷的转产溢价优势丧失，钢厂进一步向热卷倾斜铁水的意愿基本冰冻。</p>
    <p>• <strong>“金九银十”向“年末备货”的阶段转换</strong>：从季节性统计来看，9月至10月是螺纹长材利用气候窗口集中赶工的传统发力期，卷螺差通常受压下探；但一旦进入 11月下旬及 12月，北方冰冻导致建筑全面停滞，而下游制造业进入年终冲刺与备货，<strong>卷螺差常在年末出现显著反弹回升</strong>（近8年12月热卷平均上涨 +3.55%，胜率达 75%）。</p>
  </div>

  <h2>五、 风险提示与后市策略建议</h2>
  <p>1. <strong>现货持货端风险防范</strong>：热卷贸易商应警惕当前华东仓单去化进度缓慢引发的基差走弱风险，尤其在上海热卷 3,310 元/吨一线，现货流动性变现压力较大，建议逢高加快周转、压降常备库存。</p>
  <p>2. <strong>跨品种套利窗口提示</strong>：
     <br>• <strong>短期（9月下旬至10月中旬）</strong>：若螺纹出库量与表需继续冲高，当前上海同城 +20 元/吨、跨区 +150 元/吨的价差可能顺势短暂下探至负值（如回落至 -30~-50 元/吨）；
     <br>• <strong>中期（11月以后）</strong>：在卷螺差完成金九银十的充分挤压、长材停工显现后，应着手布局<strong>“多热卷、空螺纹”</strong>的跨期套利机会，迎接年末制造业冲量与出口冬储行情。</p>

  <p style="font-size: 7.5pt; color: #94a3b8; margin-top: 15px; border-top: 0.5pt solid #cbd5e1; padding-top: 6px;">
    <strong>免责声明与数据溯源</strong>：本报告由钢材产业系统量化模型自动生成，原始数据源自 Wind 数据库及《每日现货.xlsx》Authoritative 修订明细，遵循阶段 A 框架演进与因果契约规范。报告仅供内部基本面量化研究交流，不构成实际交易的买卖指令建议。
  </p>

</body>
</html>
"""

def generate_pdf():
    print("[1/2] 正在利用 WeasyPrint 编译高品质 PDF 报告...")
    doc = weasyprint.HTML(string=html_content, base_url=PROJECT_ROOT)
    doc.write_pdf(PDF_OUTPUT_PROJECT)
    print(f"  - 项目工程路径: {PDF_OUTPUT_PROJECT}")
    
    shutil.copyfile(PDF_OUTPUT_PROJECT, PDF_OUTPUT_ARTIFACT)
    print(f"  - 交互展示路径: {PDF_OUTPUT_ARTIFACT}")
    
    file_size_kb = os.path.getsize(PDF_OUTPUT_PROJECT) / 1024
    print(f"[2/2] PDF 生成成功! 文件大小: {file_size_kb:.1f} KB")
    return PDF_OUTPUT_PROJECT, PDF_OUTPUT_ARTIFACT

if __name__ == "__main__":
    generate_pdf()
