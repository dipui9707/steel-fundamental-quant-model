#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
生成《螺纹钢基本面与量化策略全景研报》专业 PDF 报告
"""
import os
import subprocess
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

html_content = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>螺纹钢基本面与量化策略全景研报 (2026-09-22)</title>
<style>
  @page {
    size: A4;
    margin: 14mm 14mm 14mm 14mm;
    @bottom-center {
      content: "第 " counter(page) " 页";
      font-size: 9pt;
      color: #718096;
    }
  }
  * {
    box-sizing: border-box;
  }
  body {
    font-family: "Noto Sans CJK SC", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
    color: #2d3748;
    background-color: #ffffff;
    font-size: 10pt;
    line-height: 1.55;
    margin: 0;
    padding: 0;
  }
  .header {
    border-bottom: 2.5px solid #1a365d;
    padding-bottom: 8px;
    margin-bottom: 14px;
  }
  .report-tag {
    display: inline-block;
    background: #ebf8ff;
    color: #2b6cb0;
    font-size: 8.5pt;
    font-weight: 700;
    padding: 2px 8px;
    border-radius: 3px;
    border: 1px solid #bee3f8;
    margin-bottom: 4px;
    text-transform: uppercase;
  }
  h1 {
    font-size: 18pt;
    font-weight: 800;
    color: #0f2942;
    margin: 4px 0 6px 0;
    letter-spacing: -0.2px;
  }
  .meta-grid {
    display: table;
    width: 100%;
    margin-top: 6px;
    font-size: 8.5pt;
    color: #4a5568;
    background: #f7fafc;
    border: 1px solid #edf2f7;
    border-radius: 4px;
    padding: 6px 10px;
  }
  .meta-row {
    display: table-row;
  }
  .meta-cell {
    display: table-cell;
    padding: 2px 8px;
  }
  .meta-label {
    font-weight: 700;
    color: #2d3748;
  }

  h2 {
    font-size: 12.5pt;
    font-weight: 700;
    color: #1a365d;
    border-bottom: 1.5px solid #2b6cb0;
    padding-bottom: 3px;
    margin-top: 14px;
    margin-bottom: 8px;
    page-break-after: avoid;
  }
  h3 {
    font-size: 10.5pt;
    font-weight: 700;
    color: #2c5282;
    margin-top: 10px;
    margin-bottom: 4px;
    page-break-after: avoid;
  }

  p {
    margin: 0 0 6px 0;
    text-align: justify;
  }

  /* Tables */
  table {
    width: 100%;
    border-collapse: collapse;
    margin: 8px 0 12px 0;
    font-size: 8.5pt;
    page-break-inside: avoid;
  }
  th {
    background-color: #2b6cb0;
    color: #ffffff;
    font-weight: 700;
    text-align: left;
    padding: 5px 7px;
    border: 1px solid #2b6cb0;
  }
  td {
    padding: 4px 7px;
    border: 1px solid #e2e8f0;
    vertical-align: middle;
  }
  tr:nth-child(even) td {
    background-color: #f8fafc;
  }

  /* Callout Boxes */
  .callout-box {
    background: #f0f4f8;
    border-left: 4px solid #2b6cb0;
    padding: 8px 12px;
    margin: 8px 0;
    border-radius: 0 4px 4px 0;
    page-break-inside: avoid;
  }
  .callout-alert {
    background: #fff5f5;
    border-left: 4px solid #e53e3e;
    padding: 8px 12px;
    margin: 8px 0;
    border-radius: 0 4px 4px 0;
    page-break-inside: avoid;
  }
  .callout-success {
    background: #f0fff4;
    border-left: 4px solid #38a169;
    padding: 8px 12px;
    margin: 8px 0;
    border-radius: 0 4px 4px 0;
    page-break-inside: avoid;
  }

  .badge {
    display: inline-block;
    padding: 1px 5px;
    border-radius: 3px;
    font-size: 8pt;
    font-weight: 600;
  }
  .badge-neutral { background: #edf2f7; color: #4a5568; }
  .badge-warn { background: #feebc8; color: #c05621; }
  .badge-danger { background: #fed7d7; color: #9b2c2c; }
  .badge-info { background: #e2e8f0; color: #2b6cb0; }
  .badge-success { background: #c6f6d5; color: #22543d; }

  .highlight {
    font-weight: 700;
    color: #1a365d;
  }

  .page-break {
    page-break-before: always;
  }

  ul, ol {
    margin: 3px 0 8px 0;
    padding-left: 18px;
  }
  li {
    margin-bottom: 3px;
  }
</style>
</head>
<body>

<div class="header">
  <div class="report-tag">钢材产业基本面量化系统 · 阶段 E 宏观与基本面研究报告</div>
  <h1>螺纹钢产业基本面、盘面结构与量化策略全景研报</h1>
  <div class="meta-grid">
    <div class="meta-row">
      <div class="meta-cell"><span class="meta-label">报告日期：</span>2026年9月22日</div>
      <div class="meta-cell"><span class="meta-label">研究对象：</span>上期所螺纹钢主力 (SHFE.rb2701)</div>
      <div class="meta-cell"><span class="meta-label">系统版本：</span>Stage-E-0.1-QuantCore</div>
    </div>
    <div class="meta-row">
      <div class="meta-cell"><span class="meta-label">基本面评级：</span>中性偏弱 (FBS: -7.29, Low)</div>
      <div class="meta-cell"><span class="meta-label">模型信任度：</span>中等 (48.0分, FULL_RESEARCH)</div>
      <div class="meta-cell"><span class="meta-label">策略执行建议：</span><span class="badge badge-warn" style="font-size:9pt;font-weight:bold;">观望空仓 (FLAT 0%)</span></div>
    </div>
  </div>
</div>

<div class="callout-box">
  <strong style="color:#1a365d;font-size:10pt;">【核心摘要与量化结论】</strong><br>
  截至 2026年9月22日，系统六大状态模块综合判定螺纹处于<strong>“宏观产业主导、基本面弱平衡中性、成本下轨硬底支撑、盘面波动极度压缩”</strong>的窄幅蓄势状态。长流程钢厂即期亏损达 -117元/吨，触发系统底层<strong>“成本下轨物理支撑一票否决做空”</strong>；同时，基本面评分 FBS=-7.29 未达右侧买入阈值，且上方紧贴 MA20(3126) 均线压制。<strong>阶段 E 策略给出 FLAT (空仓 0%) 决策，坚决不参与震荡假突破，耐心等待右侧突破信号。</strong>
</div>

<h2>一、 阶段 C 市场状态矩阵综合判决</h2>
<table>
  <thead>
    <tr>
      <th style="width:20%;">状态维度</th>
      <th style="width:28%;">系统判定状态</th>
      <th style="width:52%;">核心量化证据与关键阈值</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>1. 宏观环境 (Macro)</strong></td>
      <td><span class="badge badge-info">产业主导</span> (Neutral)</td>
      <td>外部覆盖强度 0.30，无黑天鹅突发脉冲，宏观侧无单边单向强推力</td>
    </tr>
    <tr>
      <td><strong>2. 产业基本面 (Fund)</strong></td>
      <td><span class="badge badge-neutral">中性偏弱</span> (FBS = -7.29)</td>
      <td>供需动量 FV=-1.19，处于成本下轨支撑与原料负反馈踩踏的对峙区</td>
    </tr>
    <tr>
      <td><strong>3. 现货状态 (Spot)</strong></td>
      <td><span class="badge badge-neutral">混合确认</span> (Mixed)</td>
      <td>杭州库存 85.5万吨常态健康去化，出库量 4.2万吨/日，无流动性挤压</td>
    </tr>
    <tr>
      <td><strong>4. 情绪与持仓 (Sent)</strong></td>
      <td><span class="badge badge-info">平稳分化</span> (Normal)</td>
      <td>品种分化博弈，中信席位锁死净多，空头主力高盛等低位大举止盈离场</td>
    </tr>
    <tr>
      <td><strong>5. 价格结构 (Struct)</strong></td>
      <td><span class="badge badge-warn">窄幅箱体</span> (Compressed)</td>
      <td>日内振幅仅 24点，价格收敛在 MA20(3126) 与 MA60(3075) 夹角末端</td>
    </tr>
    <tr>
      <td><strong>6. 模型信任 (Trust)</strong></td>
      <td><span class="badge badge-success">中等可信</span> (48.0分)</td>
      <td>数据完整度 100%，无背离 (0天)，处于行情生命周期“孕育期”</td>
    </tr>
  </tbody>
</table>

<h2>二、 宏观与外部驱动层 (Macro & External Drivers)</h2>
<p>
  <strong>1. 宏观政策与外部定调</strong>：当前宏观环境判定为“产业主导”，外部覆盖强度仅为 0.30。在缺乏单向强刺激政策窗口下，钢材价格中枢完全由黑色产业链内生实物供需与成本物理边界主导。
</p>
<p>
  <strong>2. 下游地产磨底与制造业韧性分化</strong>：
</p>
<ul>
  <li><strong>地产筑底失血</strong>：统计局 8 月累计数据显示，全国房地产开发投资累计同比 <strong>-19.9%</strong>，房屋新开工面积累计同比 <strong>-24.8%</strong>，施工面积累计同比 <strong>-12.8%</strong>。传统建筑用钢刚需处于长期代际收缩，向上弹性匮乏。</li>
  <li><strong>制造业与外需托底</strong>：8 月汽车产量 269.7 万辆，空调 1495.2 万台，冷柜 1006.7 万台；全国钢材单月出口依然高达 <strong>1015.0 万吨</strong>（超千万吨高位），中厚板京唐港 FOB 报 540 美元/吨，热卷 FOB 报 497 美元/吨。外需平抑了内需地产的部分减量，但对长材螺纹的边际拉动显著弱于板材。</li>
</ul>

<h2>三、 产业基本面全景与供需平衡 (Industrial Fundamentals)</h2>
<h3>1. 供应端：总资源池与产量刚性约束</h3>
<p>
  全国 247 家钢厂日均铁水产量为 <strong>237.69 万吨</strong>，高炉开工率与产能利用率低位维稳；短流程电炉开工率 68.75%，产能利用率 55.71%，受制于华东废钢（2204元/吨）紧俏，电炉谷电成本高达 3119 元/吨，平峰电全面亏损，短流程无高产抛压。主要钢厂螺纹周产量仅 <strong>174.02 万吨</strong>，处于近 5 年历史同期绝对低位（历史分位 &lt; 10%），供应端无过剩积压。
</p>

<h3>2. 品种分配：卷螺差与铁水流向替代</h3>
<p>
  2026-09-22 盘面卷螺差为 <strong>185.0 元/吨</strong>（历史全景分位 <strong>75.71%</strong>），现货上海卷螺差为 <strong>150 元/吨</strong>（热卷 3290 vs 螺纹 3140）。板材外需强于螺纹，驱动钢厂铁水分配持续优先向板卷倾斜，螺纹供给弹性被动锁死在极低水位，为螺纹提供坚实供给底座。
</p>

<h3>3. 需求韧性与微观流速</h3>
<p>
  旺季成色呈现“低基数弱平衡”：全国主流建材日成交量 9月21日为 <strong>11.14 万吨</strong>，9月22日为 <strong>9.32 万吨</strong>（近1年分位 53.97%）；杭州螺纹单日出库量维持在 <strong>4.0 ~ 4.2 万吨</strong> 正常水位（近1年分位 67.86%）。终端按需采购，无恐慌抛售亦无投机囤货。
</p>

<h3>4. 成本硬底与钢厂深度亏损（核心下轨防线）</h3>
<div class="callout-alert">
  <strong>【核心下轨支撑】：长流程亏损跌入极值区</strong><br>
  华东长流程螺纹完全成本为 <strong>3347.0 元/吨</strong>（铁水成本 2418.0 元/吨），中天现货 3160 元/吨，钢厂即期实物利润录得 <strong>-117.0 元/吨</strong>；盘面虚拟钢厂毛利 (VMM) 为 <strong>-210.8 元/吨</strong>。触发模型最高级<strong>“深度亏损下轨支撑”</strong>判定。历史 9 年实证表明，现金成本线下杀跌将遭遇钢厂自主减产控产与空头踩踏的强力阻击。
</div>

<h3>5. 原料负反馈压制（反弹天花板）</h3>
<p>
  全国 45 港铁矿石港口库存高达 <strong>16,350.5 万吨</strong>（超 1.63 亿吨高位），青岛港 PB 粉报 675 元/湿吨。系统判定为 <strong>“原料负反馈踩踏”</strong>。虽然成材跌不动，但原料高库存导致成本线自身在缓慢下移，压制了螺纹向上打开反弹估值的想象空间。
</p>

<h3>6. 动态库存与库销比</h3>
<p>
  华东蓄水池良性消化：杭州螺纹库存由 9 月中的 98.4 万吨降至 <strong>85.5 万吨</strong>，库销比处于 <strong>20.4 ~ 21.6 天</strong> 常态健康区间，未出现积压风险。
</p>

<div class="page-break"></div>

<h2>四、 现货确认与基差/期限结构 (Spot, Basis & Carry)</h2>
<table>
  <thead>
    <tr>
      <th>监测维度</th>
      <th>最新数值 (2026-09-22)</th>
      <th>历史/季节分位</th>
      <th>产业因果与状态解释</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td><strong>中天现货价格</strong></td>
      <td><strong>3160.0 元/吨</strong> (+10)</td>
      <td>代际低估值区</td>
      <td>华东主流优质品价格企稳，现货贸易商拒绝低价甩卖</td>
    </tr>
    <tr>
      <td><strong>三类 CTD 现货</strong></td>
      <td><strong>3110.0 元/吨</strong> (+10)</td>
      <td>最便宜交割品</td>
      <td>富鑫/西王等交割品贴水收敛，反映现货刚需承接平稳</td>
    </tr>
    <tr>
      <td><strong>流动性基差</strong></td>
      <td><strong>+46.0 元/吨</strong> (收盘差)</td>
      <td>近1年中枢</td>
      <td>现货温和升水盘面，无基差塌陷风险</td>
    </tr>
    <tr>
      <td><strong>CTD 交割基差</strong></td>
      <td><strong>-4.0 元/吨</strong> (收盘差)</td>
      <td>基本平水</td>
      <td>盘面与最便宜交割品几乎 1:1 平水，定价高度公允</td>
    </tr>
    <tr>
      <td><strong>期现套利净利</strong></td>
      <td><strong>-54.79 元/吨</strong></td>
      <td>无套利窗口</td>
      <td>期现正套资金无无风险入场套利空间，市场无抛压盘</td>
    </tr>
    <tr>
      <td><strong>Carry 展期收益</strong></td>
      <td><strong>0.6983 分位</strong></td>
      <td>中性平缓</td>
      <td>RB2701 对 RB2705 贴水 17元 (微幅 Contango)，结构中性</td>
    </tr>
  </tbody>
</table>

<h2>五、 盘面情况与技术/资金结构 (Market Disk & Positions)</h2>
<h3>1. 价格走势与均线收敛</h3>
<p>
  2026-09-22 螺纹主力收盘报 <strong>3114.0</strong>，结算价 <strong>3121.0</strong>，最高 3131.0，最低 3107.0。
  均线系统呈现高度收敛：<strong>MA5: 3115.0</strong>，<strong>MA20: 3126.25</strong>，<strong>MA60: 3075.82</strong>。盘面价格受压于 20 日生命线下方，受托于 60 日代际线上方，处于三角形整理极度狭窄末端。
</p>

<h3>2. 波动率异动比 (Volatility Shock Ratio)</h3>
<p>
  波动率异动比 <code>rb_vol_shock_ratio == 1.0415</code>，处于 <strong>“Compressed (极致压缩)”</strong> 状态。日线 ATR 处于近两个月低谷，统计规律显示单边洗盘震荡摩擦剧烈，但距离 5~10 交易日内的破局变盘窗口已极度临近。
</p>

<h3>3. 会员龙虎榜与席位资金偏度 ($B^{rank}_{20}$)</h3>
<table>
  <thead>
    <tr>
      <th>席位类型</th>
      <th>主力席位名称</th>
      <th>多单量 (手)</th>
      <th>空单量 (手)</th>
      <th>净持仓 (手)</th>
      <th>当日核心变动与意图</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="2"><strong>多头主力</strong></td>
      <td><strong>中信期货</strong></td>
      <td>217,242</td>
      <td>89,461</td>
      <td><strong>+127,781</strong></td>
      <td>绝对多头领头羊，手握重兵锁死底部底仓</td>
    </tr>
    <tr>
      <td><strong>银河期货</strong></td>
      <td>82,557</td>
      <td>36,290</td>
      <td><strong>+46,267</strong></td>
      <td>多头防线副攻席位，维持净多坚守</td>
    </tr>
    <tr>
      <td rowspan="3"><strong>空头主力</strong></td>
      <td><strong>高盛期货</strong></td>
      <td>29,500</td>
      <td>84,995</td>
      <td><strong>-55,495</strong></td>
      <td><strong>单日暴减空单 15,708 手</strong>，低位主动获利离场</td>
    </tr>
    <tr>
      <td><strong>国泰君安</strong></td>
      <td>150,324</td>
      <td>176,062</td>
      <td><strong>-25,738</strong></td>
      <td>减持空单 3,051 手，空头阵营出现防守减仓</td>
    </tr>
    <tr>
      <td><strong>永安期货</strong></td>
      <td>66,292</td>
      <td>87,701</td>
      <td><strong>-21,409</strong></td>
      <td>小幅增持空单 4,721 手，低位博弈对冲</td>
    </tr>
  </tbody>
</table>
<p style="font-size:8.5pt;color:#4a5568;">
  <strong>资金博弈特征总结</strong>：空头阵营在外资（高盛）与产业主力（国泰）主导下出现明显的<strong>低位减空止盈动作</strong>，主动杀跌动能枯竭；多头虽有中信重仓护盘，但未出现放量增仓进攻，市场呈现典型的多空存量僵局。
</p>

<h2>六、 客观交易建议与执行策略 (Trading Recommendations)</h2>
<div class="callout-success">
  <div style="font-size:11pt;font-weight:bold;color:#22543d;margin-bottom:4px;">
    【阶段 E 策略执行决议】：维持观望空仓 (FLAT)
  </div>
  <strong>仓位建议：0% (Lots = 0) | 账户现金比例：100% | 恪守 State != Position 铁律</strong>
</div>

<h3>1. 决策严谨因果（为什么两端均不可妄动？）</h3>
<ul>
  <li><strong>坚决一票否决追空</strong>：华东实物利润跌至 <strong>-117 元/吨</strong>，高炉现金成本物理硬底生效，触发系统最高级 <code>cost_floor_support</code> 否决做空；同时现价 3114 距离前期下轨 3080 仅 1.0% 空间，做空盈亏比不足 0.5，在此位置杀跌极易遭遇轧空反扑。</li>
  <li><strong>坚决一票否决追多</strong>：景气评分 $FBS = -7.29$ 为负值，未达多头启动线 (+15.0)；盘面被压在 MA20 (3126) 之下，上方有铁矿高库存负反馈拖累，左侧抢反弹胜率受损。</li>
</ul>

<h3>2. 后市右侧破局触发预案（何时进场？）</h3>
<ul>
  <li><strong>【情景 A：右侧转多信号 (突破买入)】</strong><br>
    若盘面<strong>放量有效收破 MA20（站稳 3135 ~ 3140 元/吨上方）</strong>，且杭州出库持续 &gt;4.5 万吨、全国日成交突破 12 万吨，伴随钢厂深度亏损引发实质性减产（日均铁水下破 235 万吨），系统将立即触发右侧做多开仓，第一目标位看至华东生产成本线 3280 ~ 3320。
  </li>
  <li><strong>【情景 B：右侧转空信号 (破位追空)】</strong><br>
    若原料端铁矿/双焦发生实质性塌陷（铁矿港口爆库下破 680），带动钢厂长流程成本下移至 3200 以下，且螺纹价格<strong>有效跌破前期代际铁底 3070 ~ 3080</strong>，成本支撑彻底失效，系统将顺势释放追空许可，目标位下看 2950 ~ 3000。
  </li>
</ul>

<div style="margin-top:20px;border-top:1px solid #e2e8f0;padding-top:6px;font-size:7.5pt;color:#a0aec0;text-align:center;">
  本报告由【钢材产业基本面量化系统 (Stage E)】自动生成 | 严格杜绝未来函数与过拟合 | 仅供产业研究与量化决策参考
</div>

</body>
</html>
"""

html_path = BASE_DIR / "研究" / "研报PDF" / "螺纹钢基本面与量化策略全景研报_20260922.html"
pdf_target = BASE_DIR / "螺纹钢基本面与量化策略全景研报_20260922.pdf"
pdf_archive = BASE_DIR / "研究" / "研报PDF" / "螺纹钢基本面与量化策略全景研报_20260922.pdf"

with open(html_path, "w", encoding="utf-8") as f:
    f.write(html_content)
print(f"[+] HTML 已写入: {html_path}")

# 调用 libreoffice 导出 PDF
out_dir = BASE_DIR / "研究" / "研报PDF"
cmd = [
    "libreoffice",
    "--headless",
    "--convert-to", "pdf",
    "--outdir", str(out_dir),
    str(html_path)
]
print(f"[*] 执行命令: {' '.join(cmd)}")
res = subprocess.run(cmd, capture_output=True, text=True)
print("Stdout:", res.stdout)
print("Stderr:", res.stderr)

if pdf_archive.exists():
    import shutil
    shutil.copy(pdf_archive, pdf_target)
    print(f"✅ PDF 成功生成并复制到根目录: {pdf_target} ({pdf_target.stat().st_size / 1024:.1f} KB)")
else:
    print("❌ PDF 未成功生成！")

