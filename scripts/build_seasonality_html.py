#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: build_seasonality_html.py
用途:
  读取 seasonal_data.json 并构建自包含交互式季节性看板 HTML。
"""

import json
import os

PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
JSON_PATH = os.path.join(PROJECT_ROOT, "研究/现货价差专题/seasonal_data.json")
ARTIFACT_DIR = "/home/hw/.gemini/antigravity/brain/78cbb79d-10e8-49b1-a7f1-b02789ba9c27"
HTML_OUTPUT_PROJECT = os.path.join(PROJECT_ROOT, "研究/现货价差专题/上海热卷_杭州螺纹_价差季节看板.html")
HTML_OUTPUT_ARTIFACT = os.path.join(ARTIFACT_DIR, "shanghai_hc_hangzhou_rb_seasonality.html")

with open(JSON_PATH, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

json_str = json.dumps(raw_data, ensure_ascii=False)

html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>华东卷螺现货价差季节性看板 (上海热卷 - 杭州螺纹)</title>
  <script src="https://www.gstatic.com/antigravity/web/dev/tailwindcss.min.js"></script>
  <style>
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Noto Sans CJK SC', sans-serif;
    }
    .badge {
      display: inline-flex;
      align-items: center;
      padding: 0.125rem 0.625rem;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 500;
    }
  </style>
</head>
<body class="bg-[var(--background,#0f172a)] text-[var(--foreground,#f8fafc)] antialiased p-4 md:p-6">
  <div class="max-w-7xl mx-auto space-y-6">
    
    <!-- 头部标题 -->
    <div class="flex flex-col md:flex-row md:items-center justify-between pb-4 border-b border-[var(--border,#334155)] gap-4">
      <div>
        <div class="flex items-center gap-3">
          <h1 class="text-2xl font-bold tracking-tight text-[var(--foreground,#f8fafc)]">上海热卷 - 杭州螺纹 现货价差季节图</h1>
          <span class="badge bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">实录现货 Authoritative</span>
        </div>
        <p class="text-sm text-[var(--muted-foreground,#94a3b8)] mt-1">
          口径: 上海热卷(Q235B 4.75mm) - 杭州螺纹(HRB400E 20mm/中天基准) | 数据范围: 2019 - 2026年 (截至 2026-09-22)
        </p>
      </div>
      <div class="text-right">
        <div class="text-xs text-[var(--muted-foreground,#94a3b8)]">最新数据时点</div>
        <div class="text-sm font-semibold text-[var(--accent,#38bdf8)]">2026-09-22 收盘现货</div>
      </div>
    </div>

    <!-- 关键指标卡片 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground,#94a3b8)]">最新现货价差 (2026-09-22)</div>
        <div class="text-2xl font-bold text-rose-500 mt-1 flex items-baseline gap-2">
          +150 <span class="text-xs font-normal text-[var(--muted-foreground,#94a3b8)]">元/吨</span>
        </div>
        <div class="text-xs text-rose-400/80 mt-1">热卷 3310 vs 螺纹 3160 (卷强螺弱)</div>
      </div>

      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground,#94a3b8)]">近5年同期均值 (09-22)</div>
        <div class="text-2xl font-bold text-[var(--foreground,#f8fafc)] mt-1 flex items-baseline gap-2">
          +34 <span class="text-xs font-normal text-[var(--muted-foreground,#94a3b8)]">元/吨</span>
        </div>
        <div class="text-xs text-emerald-400 mt-1">当前高于均值 +116 元/吨</div>
      </div>

      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground,#94a3b8)]">历年同期历史分位</div>
        <div class="text-2xl font-bold text-amber-400 mt-1 flex items-baseline gap-2">
          85.7% <span class="text-xs font-normal text-[var(--muted-foreground,#94a3b8)]">分位数</span>
        </div>
        <div class="text-xs text-amber-400/80 mt-1">处于历史同期偏高区间</div>
      </div>

      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground,#94a3b8)]">2026年波动区间</div>
        <div class="text-2xl font-bold text-sky-400 mt-1 flex items-baseline gap-2">
          50 ~ 280 <span class="text-xs font-normal text-[var(--muted-foreground,#94a3b8)]">元/吨</span>
        </div>
        <div class="text-xs text-sky-400/80 mt-1">年度均值 +177.6 元/吨</div>
      </div>
    </div>

    <!-- 图表容器 -->
    <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-5 shadow-sm space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <span class="text-sm font-semibold text-[var(--foreground,#f8fafc)]">年份筛选与对照:</span>
          <div id="yearToggles" class="flex flex-wrap gap-1.5"></div>
        </div>
        <div class="text-xs text-[var(--muted-foreground,#94a3b8)]">
          在图表上移动鼠标可查看对应公历日期的历年价差横向对比
        </div>
      </div>

      <!-- Canvas 图表区域 -->
      <div class="relative w-full h-[480px] bg-[#0f172a] rounded-lg border border-[var(--border,#334155)] overflow-hidden">
        <canvas id="seasonCanvas" class="w-full h-full cursor-crosshair"></canvas>
        <div id="tooltip" class="absolute hidden pointer-events-none bg-slate-900/95 border border-slate-700 text-xs rounded-lg p-3 shadow-xl backdrop-blur-sm z-20 min-w-[210px]"></div>
      </div>
    </div>

    <!-- 宏观与产业逻辑解读 -->
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-5 shadow-sm space-y-3">
        <h3 class="text-base font-semibold text-[var(--accent,#38bdf8)] flex items-center gap-2">
          <span>📊</span> 季节性特征与历史规律
        </h3>
        <ul class="text-sm text-[var(--muted-foreground,#94a3b8)] space-y-2 leading-relaxed">
          <li>• <strong class="text-slate-200">夏季走阔 (6-8月):</strong> 高温梅雨季节抑制建筑工地户外施工，螺纹表现为淡季累库与需求低谷；而制造业工厂受气候影响小且外需出口维持，卷螺差常显著走阔（2026年7-8月达 +240~+280 元/吨）。</li>
          <li>• <strong class="text-slate-200">秋季收敛 (9-11月):</strong> “金九银十”与北方停工前赶工催生螺纹短期表需脉冲，卷螺差常出现明显季节性压缩（如2024年秋季最低被压缩至 -140 元/吨）。</li>
          <li>• <strong class="text-slate-200">冬储与春节 (12-2月):</strong> 临近冬储博弈，现货回归钢厂成本锚，通常在 50~120 元/吨合理成本溢价区间运行。</li>
        </ul>
      </div>

      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-5 shadow-sm space-y-3">
        <h3 class="text-base font-semibold text-rose-400 flex items-center gap-2">
          <span>🔍</span> 2026年当前产业格局归因
        </h3>
        <ul class="text-sm text-[var(--muted-foreground,#94a3b8)] space-y-2 leading-relaxed">
          <li>• <strong class="text-slate-200">结构性分化延续:</strong> 地产新开工与施工面积持续承压，建材刚需中枢下移；造船、家电、汽车及机械制造用钢维持高景气，叠加直接与间接钢材出口放量，热卷基本面持续强于螺纹。</li>
          <li>• <strong class="text-slate-200">高位回落但韧性极强:</strong> 2026年9月价差由8月末的 +260 元/吨温和回落至 +150 元/吨，顺应金九开工季季节性收敛，但远高于2022(-50)与2024(-130)同期水平，表明板材对长材的绝对溢价基础坚实。</li>
          <li>• <strong class="text-slate-200">数据治理保障:</strong> 2024-2026年全量基于用户《每日现货.xlsx》Authoritative修正价重算，2019-2023年精准衔接 Wind EDB S0033272，实现无未来函数的长周期一致性。</li>
        </ul>
      </div>
    </div>

  </div>

  <script>
    const rawData = __DATA_PLACEHOLDER__;
    const years = ['2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026'];
    const colors = {
      '2019': '#64748b',
      '2020': '#0284c7',
      '2021': '#8b5cf6',
      '2022': '#0d9488',
      '2023': '#10b981',
      '2024': '#f59e0b',
      '2025': '#f97316',
      '2026': '#ef4444',
      '5Y_Avg': '#94a3b8'
    };

    const activeYears = {
      '2019': false,
      '2020': false,
      '2021': true,
      '2022': true,
      '2023': true,
      '2024': true,
      '2025': true,
      '2026': true,
      '5Y_Avg': true
    };

    // 生成公历 366 日期列表 (按闰年2024排列)
    const dateList = [];
    const daysInMonth = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    for (let m = 1; m <= 12; m++) {
      for (let d = 1; d <= daysInMonth[m - 1]; d++) {
        const mm = String(m).padStart(2, '0');
        const dd = String(d).padStart(2, '0');
        dateList.push(`${mm}-${dd}`);
      }
    }

    // 计算5年均值 (2021-2025)
    const avg5y = {};
    const hist5yYears = ['2021', '2022', '2023', '2024', '2025'];
    dateList.forEach(k => {
      let sum = 0, count = 0;
      hist5yYears.forEach(y => {
        if (rawData[y] && rawData[y][k] !== undefined) {
          sum += rawData[y][k];
          count++;
        }
      });
      if (count > 0) avg5y[k] = Math.round(sum / count);
    });
    rawData['5Y_Avg'] = avg5y;

    // 渲染筛选按钮
    const togglesContainer = document.getElementById('yearToggles');
    const allToggleKeys = [...years, '5Y_Avg'];
    allToggleKeys.forEach(k => {
      const btn = document.createElement('button');
      btn.className = `px-2.5 py-1 text-xs rounded-md font-medium transition border ${
        activeYears[k]
          ? 'border-transparent text-white'
          : 'bg-transparent text-slate-500 border-slate-700 hover:text-slate-300'
      }`;
      btn.style.backgroundColor = activeYears[k] ? colors[k] : 'transparent';
      btn.innerText = k === '5Y_Avg' ? '5年均值' : `${k}年`;
      btn.onclick = () => {
        activeYears[k] = !activeYears[k];
        btn.style.backgroundColor = activeYears[k] ? colors[k] : 'transparent';
        btn.className = `px-2.5 py-1 text-xs rounded-md font-medium transition border ${
          activeYears[k]
            ? 'border-transparent text-white'
            : 'bg-transparent text-slate-500 border-slate-700 hover:text-slate-300'
        }`;
        drawChart();
      };
      togglesContainer.appendChild(btn);
    });

    // Canvas 绘图
    const canvas = document.getElementById('seasonCanvas');
    const ctx = canvas.getContext('2d');
    const tooltip = document.getElementById('tooltip');

    let chartBounds = { left: 60, right: 20, top: 30, bottom: 40, width: 0, height: 0 };
    let currentHoverIndex = -1;

    function resizeCanvas() {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = rect.width * dpr;
      canvas.height = rect.height * dpr;
      ctx.scale(dpr, dpr);
      chartBounds.width = rect.width - chartBounds.left - chartBounds.right;
      chartBounds.height = rect.height - chartBounds.top - chartBounds.bottom;
      drawChart();
    }

    const yMin = -550;
    const yMax = 850;

    function getY(val) {
      return chartBounds.top + chartBounds.height - ((val - yMin) / (yMax - yMin)) * chartBounds.height;
    }

    function getX(index) {
      return chartBounds.left + (index / (dateList.length - 1)) * chartBounds.width;
    }

    function drawChart() {
      const rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);

      // 网格线与Y轴刻度
      ctx.lineWidth = 1;
      const yTicks = [-400, -200, 0, 200, 400, 600, 800];
      yTicks.forEach(tick => {
        const y = getY(tick);
        ctx.beginPath();
        if (tick === 0) {
          ctx.strokeStyle = '#64748b';
          ctx.lineWidth = 1.5;
        } else {
          ctx.strokeStyle = '#1e293b';
          ctx.lineWidth = 1;
        }
        ctx.moveTo(chartBounds.left, y);
        ctx.lineTo(chartBounds.left + chartBounds.width, y);
        ctx.stroke();

        ctx.fillStyle = tick === 0 ? '#94a3b8' : '#64748b';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'right';
        ctx.fillText(tick, chartBounds.left - 8, y + 4);
      });

      // X轴月份刻度
      const monthStartIndices = [0, 31, 60, 91, 121, 152, 182, 213, 244, 274, 305, 335];
      monthStartIndices.forEach((idx, m) => {
        const x = getX(idx);
        ctx.beginPath();
        ctx.strokeStyle = '#1e293b';
        ctx.moveTo(x, chartBounds.top);
        ctx.lineTo(x, chartBounds.top + chartBounds.height);
        ctx.stroke();

        ctx.fillStyle = '#94a3b8';
        ctx.font = '11px sans-serif';
        ctx.textAlign = 'center';
        ctx.fillText(`${m + 1}月`, x + 15, chartBounds.top + chartBounds.height + 22);
      });

      // 绘制各年份折线
      allToggleKeys.forEach(k => {
        if (!activeYears[k]) return;
        const s = rawData[k];
        if (!s) return;

        ctx.beginPath();
        ctx.strokeStyle = colors[k];
        if (k === '2026') {
          ctx.lineWidth = 3.2;
        } else if (k === '5Y_Avg') {
          ctx.lineWidth = 2.0;
          ctx.setLineDash([5, 4]);
        } else if (k === '2024' || k === '2025') {
          ctx.lineWidth = 2.0;
          ctx.setLineDash([]);
        } else {
          ctx.lineWidth = 1.4;
          ctx.setLineDash([]);
        }

        let started = false;
        dateList.forEach((dt, i) => {
          if (s[dt] !== undefined) {
            const x = getX(i);
            const y = getY(s[dt]);
            if (!started) {
              ctx.moveTo(x, y);
              started = true;
            } else {
              ctx.lineTo(x, y);
            }
          }
        });
        ctx.stroke();
        ctx.setLineDash([]);
      });

      // 悬停垂直十字线与数据点高亮
      if (currentHoverIndex >= 0 && currentHoverIndex < dateList.length) {
        const hoverX = getX(currentHoverIndex);
        ctx.beginPath();
        ctx.strokeStyle = '#38bdf8';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.moveTo(hoverX, chartBounds.top);
        ctx.lineTo(hoverX, chartBounds.top + chartBounds.height);
        ctx.stroke();
        ctx.setLineDash([]);

        const hoverDt = dateList[currentHoverIndex];
        allToggleKeys.forEach(k => {
          if (!activeYears[k]) return;
          const s = rawData[k];
          if (s && s[hoverDt] !== undefined) {
            const ptY = getY(s[hoverDt]);
            ctx.beginPath();
            ctx.fillStyle = colors[k];
            ctx.arc(hoverX, ptY, k === '2026' ? 5 : 3.5, 0, Math.PI * 2);
            ctx.fill();
            ctx.strokeStyle = '#ffffff';
            ctx.lineWidth = 1.5;
            ctx.stroke();
          }
        });
      }
    }

    // 交互悬停事件
    canvas.addEventListener('mousemove', e => {
      const rect = canvas.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      if (mouseX < chartBounds.left || mouseX > chartBounds.left + chartBounds.width) {
        tooltip.style.display = 'none';
        currentHoverIndex = -1;
        drawChart();
        return;
      }

      const ratio = (mouseX - chartBounds.left) / chartBounds.width;
      currentHoverIndex = Math.round(ratio * (dateList.length - 1));
      currentHoverIndex = Math.max(0, Math.min(dateList.length - 1, currentHoverIndex));
      const hoverDt = dateList[currentHoverIndex];

      let tipHtml = `<div class="font-bold text-slate-200 border-b border-slate-700 pb-1.5 mb-2">公历: ${hoverDt}</div>`;
      tipHtml += '<div class="space-y-1">';
      allToggleKeys.forEach(k => {
        if (!activeYears[k]) return;
        const s = rawData[k];
        if (s && s[hoverDt] !== undefined) {
          const val = s[hoverDt];
          const name = k === '5Y_Avg' ? '5年均值' : `${k}年`;
          const isCurrent = k === '2026';
          tipHtml += `<div class="flex justify-between items-center gap-4 ${isCurrent ? 'font-bold' : ''}">
            <span class="flex items-center gap-1.5">
              <span class="w-2.5 h-2.5 rounded-full inline-block" style="background-color:${colors[k]}"></span>
              <span style="color:${colors[k]}">${name}</span>
            </span>
            <span class="font-mono ${val >= 0 ? 'text-rose-400' : 'text-emerald-400'}">${val > 0 ? '+' : ''}${val} 元/吨</span>
          </div>`;
        }
      });
      tipHtml += '</div>';

      tooltip.innerHTML = tipHtml;
      tooltip.style.display = 'block';

      let leftPos = mouseX + 15;
      if (leftPos + 220 > rect.width) leftPos = mouseX - 235;
      tooltip.style.left = `${leftPos}px`;
      tooltip.style.top = '40px';

      drawChart();
    });

    canvas.addEventListener('mouseleave', () => {
      tooltip.style.display = 'none';
      currentHoverIndex = -1;
      drawChart();
    });

    window.addEventListener('resize', resizeCanvas);
    window.addEventListener('DOMContentLoaded', resizeCanvas);
  </script>
</body>
</html>
"""

full_html = html_template.replace("__DATA_PLACEHOLDER__", json_str)

for p in [HTML_OUTPUT_PROJECT, HTML_OUTPUT_ARTIFACT]:
    with open(p, "w", encoding="utf-8") as f:
        f.write(full_html)
    print(f"Generated HTML dashboard: {p}")
