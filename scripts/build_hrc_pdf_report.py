#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成高质量出版级《热轧板卷市场全景深度分析报告（2026年10月中旬）》PDF
"""
from pathlib import Path
from weasyprint import HTML

BASE_DIR = Path(__file__).resolve().parent.parent

html_code = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>20261014 热卷市场情况分析</title>
<style>
  @page {
    size: A4 portrait;
    margin: 15mm 16mm 15mm 16mm;
    @top-left {
      content: "20261014 热卷市场情况分析";
      font-size: 8pt;
      font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
      color: #64748b;
      border-bottom: 0.5pt solid #cbd5e1;
      padding-bottom: 3px;
    }
    @top-right {
      content: "评估基准：2026-10-14 (日终结算)";
      font-size: 8pt;
      font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
      color: #64748b;
      border-bottom: 0.5pt solid #cbd5e1;
      padding-bottom: 3px;
    }
    @bottom-left {
      content: "本报告基于全链路客观产业数据编制 · 仅供量化投研参考 · 不构成投资买卖指令";
      font-size: 7.5pt;
      font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
      color: #94a3b8;
      border-top: 0.5pt solid #cbd5e1;
      padding-top: 3px;
    }
    @bottom-right {
      content: "第 " counter(page) " 页 / 共 " counter(pages) " 页";
      font-size: 8pt;
      font-family: "Noto Sans CJK SC", "Microsoft YaHei", sans-serif;
      color: #64748b;
      border-top: 0.5pt solid #cbd5e1;
      padding-top: 3px;
    }
  }

  * {
    box-sizing: border-box;
  }

  body {
    font-family: "Noto Sans CJK SC", "Source Han Sans CN", "Microsoft YaHei", sans-serif;
    color: #1e293b;
    line-height: 1.55;
    font-size: 9.5pt;
    background: #ffffff;
    margin: 0;
    padding: 0;
  }

  /* 标题与头部 */
  .header-box {
    border-bottom: 2pt solid #1e3a8a;
    padding-bottom: 8px;
    margin-bottom: 14px;
  }
  .report-tag {
    display: inline-block;
    background-color: #1e3a8a;
    color: #ffffff;
    font-size: 7.5pt;
    font-weight: bold;
    padding: 2px 7px;
    border-radius: 3px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 4px;
  }
  h1 {
    font-size: 17pt;
    color: #0f172a;
    margin: 4px 0 6px 0;
    font-weight: 800;
    letter-spacing: -0.3px;
  }
  .meta-bar {
    font-size: 8pt;
    color: #64748b;
    display: flex;
    justify-content: space-between;
    margin-top: 4px;
  }

  /* 核心摘要卡片 */
  .exec-summary {
    background-color: #f8fafc;
    border: 1pt solid #e2e8f0;
    border-left: 4pt solid #2563eb;
    border-radius: 4px;
    padding: 10px 12px;
    margin-bottom: 14px;
  }
  .exec-summary h3 {
    margin: 0 0 6px 0;
    font-size: 10.5pt;
    color: #1e3a8a;
    display: flex;
    align-items: center;
  }
  .exec-summary ul {
    margin: 0;
    padding-left: 16px;
  }
  .exec-summary li {
    margin-bottom: 4px;
    font-size: 9pt;
    color: #334155;
  }
  .exec-summary li:last-child {
    margin-bottom: 0;
  }

  /* 章节标题 */
  h2 {
    font-size: 11.5pt;
    color: #0f172a;
    border-bottom: 1pt solid #cbd5e1;
    padding-bottom: 4px;
    margin-top: 14px;
    margin-bottom: 8px;
    font-weight: 700;
    display: flex;
    align-items: center;
  }
  h2::before {
    content: "";
    display: inline-block;
    width: 3.5pt;
    height: 11.5pt;
    background-color: #2563eb;
    margin-right: 6px;
    border-radius: 1.5px;
  }

  h3 {
    font-size: 10pt;
    color: #1e3a8a;
    margin-top: 10px;
    margin-bottom: 5px;
    font-weight: 700;
  }

  p {
    margin: 0 0 7px 0;
    text-align: justify;
  }

  /* 流程框与网格 */
  .flow-grid {
    display: table;
    width: 100%;
    margin: 10px 0;
    border-collapse: separate;
    border-spacing: 6px 0;
  }
  .flow-col {
    display: table-cell;
    width: 33.33%;
    background: #f8fafc;
    border: 1pt solid #e2e8f0;
    border-radius: 4px;
    padding: 8px;
    vertical-align: top;
  }
  .flow-title {
    font-size: 8.5pt;
    font-weight: bold;
    color: #1e3a8a;
    border-bottom: 1pt solid #e2e8f0;
    padding-bottom: 4px;
    margin-bottom: 6px;
  }
  .flow-body {
    font-size: 8pt;
    color: #475569;
    line-height: 1.45;
  }

  /* 表格样式 */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 12px 0;
    font-size: 8pt;
  }
  th {
    background-color: #f1f5f9;
    color: #0f172a;
    font-weight: 700;
    text-align: center;
    padding: 5px 6px;
    border: 0.5pt solid #cbd5e1;
  }
  td {
    padding: 5px 6px;
    border: 0.5pt solid #e2e8f0;
    color: #334155;
    vertical-align: middle;
  }
  tr:nth-child(even) td {
    background-color: #f8fafc;
  }
  td.num {
    text-align: right;
    font-variant-numeric: tabular-nums;
  }
  td.center {
    text-align: center;
  }
  .tag-danger {
    color: #b91c1c;
    font-weight: bold;
  }
  .tag-success {
    color: #15803d;
    font-weight: bold;
  }
  .tag-neutral {
    color: #0369a1;
    font-weight: bold;
  }

  /* 哨兵警示卡片 */
  .sentinel-box {
    display: table;
    width: 100%;
    margin: 8px 0;
    border-collapse: separate;
    border-spacing: 8px 0;
  }
  .sentinel-card {
    display: table-cell;
    width: 50%;
    border-radius: 4px;
    padding: 8px 10px;
    vertical-align: top;
  }
  .sentinel-card.up {
    background-color: #f0fdf4;
    border: 1pt solid #bbf7d0;
  }
  .sentinel-card.down {
    background-color: #fef2f2;
    border: 1pt solid #fecaca;
  }
  .sentinel-title-up {
    font-size: 8.5pt;
    font-weight: bold;
    color: #166534;
    margin-bottom: 4px;
  }
  .sentinel-title-down {
    font-size: 8.5pt;
    font-weight: bold;
    color: #991b1b;
    margin-bottom: 4px;
  }
  .sentinel-list {
    margin: 0;
    padding-left: 14px;
    font-size: 8pt;
    color: #334155;
  }
  .sentinel-list li {
    margin-bottom: 3px;
  }

  .page-break {
    page-break-before: always;
  }
</style>
</head>
<body>

  <!-- 头部信息 -->
  <div class="header-box">
    <h1>20261014 热卷市场情况分析</h1>
    <div class="meta-bar">
      <span><strong>报告日期</strong>：2026年10月14日</span>
      <span><strong>数据基准</strong>：期货/出口至 10-14 盘后 | 现货至 10-13 | 产业周度至 10-09</span>
      <span><strong>核心标的</strong>：热轧板卷（主力合约/现货/钢厂产销/外贸）</span>
    </div>
  </div>

  <!-- 执行摘要 -->
  <div class="exec-summary">
    <h3>核心结论速览：供需高位对峙，库存与仓单承压，区间震荡等待去化拐点</h3>
    <ul>
      <li><strong>基本面矛盾</strong>：国庆节后全国热卷总库存单周跳增 <strong>31.99 万吨</strong>（达 456.34 万吨），期货注册仓单增至 <strong>22.85 万吨</strong> 历史阶段高位；同时钢厂即期保持微利，高炉铁水保持 <strong>233.9 万吨/日</strong>，热卷周产反弹至 <strong>292.19 万吨</strong>，供给端处于高位刚性状态，现货消化承压。</li>
      <li><strong>需求与外贸托底</strong>：汽车制造受益于“以旧换新”政策与四季度冲量，10月耗钢量预期回升至 <strong>520 万吨</strong>；天津港与京唐港 FOB 离岸价报 <strong>492~493 美元/吨</strong>，海关 9 月钢材出口再破千万吨（<strong>1049.2 万吨</strong>），强劲外贸依然是国内最关键的产能泄洪池。</li>
      <li><strong>盘面与后市定调</strong>：热卷期货主力 2701 合约收于 <strong>3242 元/吨</strong>，期现基差仅 <strong>28 元/吨（期现平水）</strong>，远月呈现微幅升水 Contango 结构，主力持仓剧增至 <strong>155.3 万手</strong>。市场短期陷入 <strong>3200 ~ 3320 元/吨</strong> 箱体博弈，向上受阻于高库存和高仓单，向下受成本中枢和出口托底，后市打破僵局的核心观察点在节后第二至第三周的社库去化速率。</li>
    </ul>
  </div>

  <!-- 产业因果流向逻辑 -->
  <div class="flow-grid">
    <div class="flow-col">
      <div class="flow-title">1. 供给与成本中枢</div>
      <div class="flow-body">
        • 高炉铁水 233.9 万吨/日稳定高位<br>
        • 热卷周产 292.19 万吨（是螺纹 1.72 倍）<br>
        • 铁水成本 2277 元/吨，毛利微幅盈利 50~90 元/吨<br>
        • 钢厂无大面积亏损，缺乏自发减产动力
      </div>
    </div>
    <div class="flow-col">
      <div class="flow-title">2. 库存与期现流通</div>
      <div class="flow-body">
        • 社会库存节后跳增 26 万吨至 380.66 万吨<br>
        • 合计总库存 456.34 万吨，创阶段偏高水平<br>
        • 上期所注册仓单大增至 22.85 万吨顶压近月<br>
        • 上海现货 3270 元，基差仅 28 元（基本平水）
      </div>
    </div>
    <div class="flow-col">
      <div class="flow-title">3. 终端与外贸出口</div>
      <div class="flow-body">
        • 汽车 10 月耗钢回升至 520 万吨，机械稳定<br>
        • 天津港 FOB 493 美元/吨，离岸窗口顺畅<br>
        • 9 月全国出口 1049 万吨，32 港出港维持高位<br>
        • 表需 286.77 万吨，供需处于阶段性窄幅过剩
      </div>
    </div>
  </div>

  <!-- 一、行情与结构 -->
  <h2>一、 价格走势与期现结构表现（截至 2026-10-14 盘后）</h2>
  <p>截至 2026 年 10 月 14 日收盘，热轧板卷的期货盘面、跨期月差、现货价格、基差及跨品种比价数据如下：</p>

  <table>
    <thead>
      <tr>
        <th style="width: 14%;">监测维度</th>
        <th style="width: 22%;">具体监测标的</th>
        <th style="width: 16%;">最新数据 (10-14)</th>
        <th style="width: 16%;">节前基准 (09-30)</th>
        <th style="width: 14%;">节后变动</th>
        <th style="width: 18%;">结构属性与含义</th>
      </tr>
    </thead>
    <tbody>
      <tr>
        <td><strong>期货主力收盘</strong></td>
        <td>热卷期货 2701 合约</td>
        <td class="num"><strong>3242 元/吨</strong></td>
        <td class="num">3274 元/吨</td>
        <td class="center tag-danger">-32 元/吨</td>
        <td>承压下行，区间下轨探底</td>
      </tr>
      <tr>
        <td><strong>期货主力结算</strong></td>
        <td>热卷期货 2701 合约</td>
        <td class="num"><strong>3242 元/吨</strong></td>
        <td class="num">3282 元/吨</td>
        <td class="center tag-danger">-40 元/吨</td>
        <td>价格中枢下移，日内最低 3237</td>
      </tr>
      <tr>
        <td><strong>主力合约持仓</strong></td>
        <td>热卷期货 2701 合约</td>
        <td class="num"><strong>155.27 万手</strong></td>
        <td class="num">136.60 万手</td>
        <td class="center tag-danger"><strong>+18.67 万手</strong></td>
        <td>显著增仓下行，资金分歧白热化</td>
      </tr>
      <tr>
        <td><strong>跨期月差结构</strong></td>
        <td>2701 主力 对 2703 次主力</td>
        <td class="num"><strong>-11.0 元/吨</strong></td>
        <td class="num">-11.0 元/吨</td>
        <td class="center">持平</td>
        <td>Contango结构，反映近端现货压力</td>
      </tr>
      <tr>
        <td><strong>远期期限结构</strong></td>
        <td>2701 主力 对 2705 远月</td>
        <td class="num"><strong>-17.0 元/吨</strong></td>
        <td class="center">-</td>
        <td class="center">-</td>
        <td>远月溢价，近月受即期库存压制</td>
      </tr>
      <tr>
        <td><strong>主流现货价格</strong></td>
        <td>上海 4.75mm 热轧板卷</td>
        <td class="num"><strong>3270 元/吨</strong></td>
        <td class="num">3300 元/吨</td>
        <td class="center tag-danger">-30 元/吨</td>
        <td>乐从 3250，天津 3240，区域价差扁平</td>
      </tr>
      <tr>
        <td><strong>即期期现基差</strong></td>
        <td>上海现货 - 2701 主力收盘</td>
        <td class="num"><strong>+28.0 元/吨</strong></td>
        <td class="num">+26.0 元/吨</td>
        <td class="center tag-neutral">低位震荡</td>
        <td>期现基本平水，缺乏基差驱动</td>
      </tr>
      <tr>
        <td><strong>交割注册仓单</strong></td>
        <td>上期所热卷注册仓单</td>
        <td class="num"><strong>22.85 万吨</strong></td>
        <td class="num">19.73 万吨</td>
        <td class="center tag-danger"><strong>+3.12 万吨</strong></td>
        <td>仓单激增创阶段新高，顶压近月</td>
      </tr>
      <tr>
        <td><strong>盘面卷螺差</strong></td>
        <td>热卷主力 - 螺纹主力</td>
        <td class="num"><strong>+164.0 元/吨</strong></td>
        <td class="num">+120.0 元/吨</td>
        <td class="center tag-success">+44 元/吨</td>
        <td>卷强螺弱扩大，长流程铁水偏向板材</td>
      </tr>
    </tbody>
  </table>

  <!-- 二、供给与库存 -->
  <h2>二、 钢厂供应与库存现状：节后集中累库包袱较重</h2>
  <p>根据 Wind EDB 与行业最新周度统计（数据截至 2026-10-09），热卷呈现典型的<strong>“高炉供给刚性 + 节后到货跳增 + 累库加速”</strong>特征：</p>
  
  <p><strong>1. 钢厂供给缺乏主动收缩动力</strong>：全国 247 家主要钢铁企业高炉日均铁水产量保持在 <strong>233.90 万吨/日</strong>（开工率 81.35%，炼铁产能利用率 87.82%），整体处于充裕区间。重点钢厂热卷周产量由节前的 285.63 万吨连续回升至 <strong>292.19 万吨/周</strong>（单周增长 +6.56 万吨/周）。对比之下，螺纹钢周产量仅为 <strong>170.22 万吨/周</strong>，热卷周产量是螺纹钢的 <strong>1.72 倍</strong>。由于盘面和现货卷螺差维持在 100~160 元/吨的高位，双栖钢企转炉优先拉浇板坯，铁水持续向热卷产线倾斜。</p>

  <p><strong>2. 国庆长假集中到货，社会库存激增</strong>：全国热卷流通环节社会库存跃升至 <strong>380.66 万吨</strong>，节后大幅跳增 <strong>26.05 万吨</strong>；重点钢厂厂内库存小幅增至 <strong>75.68 万吨</strong>；两者合计总库存达 <strong>456.34 万吨</strong>，假期前后净累积近 <strong>32 万吨</strong>。虽然长假累库符合季节性，但单周跳增幅度较大，市场流通环节资金占用和套现压力显现，表观消费（286.77 万吨/周）低于周产量，供需阶段性存在约 5.4 万吨的周度差额。</p>

  <div class="page-break"></div>

  <!-- 三、终端与外贸 -->
  <h2>三、 终端需求与外贸出口：内需韧性托底，外贸泄洪关键</h2>

  <p><strong>1. 制造业终端消耗保持平稳韧性</strong>：</p>
  <ul>
    <li><strong>汽车行业（四季度主要增量点）</strong>：8 月全国汽车产量为 269.7 万辆。受益于国家汽车以旧换新补贴细则全面落地与车企“金九银十”冲量排产，行业前瞻预测 10 月汽车行业耗钢量将回升至 <strong>520 万吨/月</strong>（显著高于 8 月实际的 450 万吨），冲压板材需求具备弹性。</li>
    <li><strong>通用机械装备</strong>：大型工程机械与装备制造业月度耗钢量稳定在 <strong>1470 ~ 1500 万吨</strong> 区间，重工开工保持正常节奏。</li>
    <li><strong>家用电器制造</strong>：空调生产进入传统秋冬淡季（月度产量由夏季峰值 2700 万台降至约 1500 万台），家电行业月度耗钢维持在 <strong>150 万吨</strong> 左右。</li>
  </ul>

  <p><strong>2. 外贸出口是化解国内板材过剩的最大支撑阀</strong>：</p>
  <ul>
    <li><strong>离岸出口报价（截至 2026-10-14）</strong>：SMM 天津港热卷 FOB 现货价报 <strong>493 美元/吨</strong>，京唐港报 <strong>492 美元/吨</strong>。折合人民币离岸价约在 <strong>3500 ~ 3550 元/吨</strong>，相对于国内 3240~3270 元现货仍有合理溢价空间，国内钢厂外贸接单意愿维持积极。</li>
    <li><strong>出口数据</strong>：海关最新数据显示 9 月份全国钢材出口达 <strong>1049.2 万吨</strong>，年内再度突破单月千万吨级；全国 32 个重点港口钢材周度出港量为 <strong>303.35 万吨/周</strong>（其中钢卷出港达 47.69 万吨/周），重点大厂计划出口量保持在 80 万吨以上高位。强劲外贸直接避免了板材资源在内贸市场的过度踩踏。</li>
  </ul>

  <!-- 四、成本与盈利 -->
  <h2>四、 成本中枢与钢厂盈利：微利运行下的刚性供给</h2>
  <p><strong>1. 成本支撑线震荡走平</strong>：节后原料端（焦煤、焦炭、铁矿石）跟随大盘回调，华东地区长流程高炉铁水现金成本由节前的 2396 元/吨逐步下移至 <strong>2277 元/吨</strong> 附近，成本底线下移但近期在 2250~2300 元区间趋稳。</p>
  <p><strong>2. 钢厂即期毛利小幅回正</strong>：华东高炉螺纹即期毛利约为 <strong>+35 元/吨</strong>，热卷即期毛利在 <strong>+50 至 +90 元/吨</strong>。全行业既无超额暴利，也未见全行业持续现金流深度亏损。在“微利维持生产”的格局下，全国主流热卷产线缺乏主动停炉减产的内在动力，短期供给刚性将持续存在。</p>

  <!-- 五、资金与席位持仓 -->
  <h2>五、 主力期货席位持仓博弈（前二十大主力机构）</h2>
  <p>根据 2026 年 10 月 13 日交易所持仓龙虎榜数据：</p>
  <ul>
    <li><strong>持仓总量与偏度</strong>：热卷主力 2701 合约前 20 名多头席位合计持仓 <strong>114.59 万手</strong>（日增 27,392 手），前 20 名空头席位合计持仓 <strong>104.52 万手</strong>（日增 27,885 手），前 20 名净多单 <strong>+10.07 万手</strong>，但多空增量势均力敌。</li>
    <li><strong>核心席位分布</strong>：<strong>国泰君安期货</strong> 呈现大单对锁格局（多单 21.39 万手，空单 24.16 万手，净偏空 2.77 万手）；<strong>中信期货</strong> 净偏多（多单 13.57 万手，空单 11.13 万手，净偏多 2.44 万手）；银河期货、东证期货、光大期货持仓规模均超过 7~10 万手。</li>
    <li><strong>资金盘面特征</strong>：价格走弱而主力持仓急剧膨胀至 155 万手，但日成交量缩至 29~35 万手，呈现典型的资金锁仓僵持与震荡洗盘特征。</li>
  </ul>

  <!-- 六、研判与哨兵 -->
  <h2>六、 后市研判与关键监测哨兵清单</h2>
  <p>目前热卷市场处于<strong>“上行有高库存和高仓单盖顶、下行有制造业韧性与成本托底”</strong>的区间震荡期，核心波动区间维持在 <strong>3200 ~ 3320 元/吨</strong>。</p>

  <div class="sentinel-box">
    <div class="sentinel-card up">
      <div class="sentinel-title-up">▲ 向上突破需满足的确认信号</div>
      <ul class="sentinel-list">
        <li><strong>社会库存连续 2 周顺畅去化</strong>：单周去库规模超过 10 万吨以上，证实节后终端真实采购加速启动；</li>
        <li><strong>上期所仓单集中注销离场</strong>：注册仓单由 22.8 万吨显著回落至 18 万吨以下，化解近月交割实物压力；</li>
        <li><strong>期现基差由平水扩大</strong>：上海现货涨幅领先期货，即期基差由 20~30 元扩大至 60~80 元以上。</li>
      </ul>
    </div>
    <div class="sentinel-card down">
      <div class="sentinel-title-down">▼ 向下破位需防范的风险警示</div>
      <ul class="sentinel-list">
        <li><strong>钢厂供给进一步逆势扩张</strong>：重点钢厂周产突破 295 万吨，而社会库存连续两周反常累积；</li>
        <li><strong>离岸出口价格出现滑落</strong>：天津/京唐港 FOB 跌破 480 美元/吨，海外订单走弱导致出口转内销；</li>
        <li><strong>原料端再度开启负反馈</strong>：煤焦与铁矿石加速破位，导致钢材成本支撑线进一步向下坍塌。</li>
      </ul>
    </div>
  </div>

  <p style="margin-top: 14px; font-size: 8pt; color: #64748b; border-top: 0.5pt solid #e2e8f0; padding-top: 6px;">
    <strong>监测建议</strong>：重点跟踪本周四/周五最新公布的全国主要钢厂热卷周度产量、社会库存变化及港口发运数据，以确认节后去库拐点是否确立。
  </p>

</body>
</html>
"""

def generate_pdf():
    output_dir = BASE_DIR / "研究"
    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_path_research = output_dir / "20261014_热卷市场情况分析.pdf"
    pdf_path_root = BASE_DIR / "20261014_热卷市场情况分析.pdf"
    
    print(f"正在使用 WeasyPrint 编译生成 PDF 报告...")
    HTML(string=html_code, base_url=str(BASE_DIR)).write_pdf(str(pdf_path_research))
    print(f"-> 研究目录 PDF 生成成功: {pdf_path_research}")
    
    # 根目录同步保存一份
    import shutil
    shutil.copy2(str(pdf_path_research), str(pdf_path_root))
    print(f"-> 根目录 PDF 同步成功: {pdf_path_root}")
    
    return pdf_path_root

if __name__ == "__main__":
    generate_pdf()
