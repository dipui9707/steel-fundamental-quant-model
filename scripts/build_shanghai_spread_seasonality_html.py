#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: build_shanghai_spread_seasonality_html.py
用途:
  构建纯正上海同城现货卷螺差 (上海热卷 - 上海螺纹) 的交互式季节性看板 HTML。
"""

import json
import os

PROJECT_ROOT = "/home/hw/项目/钢材产业系统量化模型"
JSON_PATH = os.path.join(PROJECT_ROOT, "研究/现货价差专题/shanghai_spread_seasonal_data.json")
ARTIFACT_DIR = "/home/hw/.gemini/antigravity/brain/78cbb79d-10e8-49b1-a7f1-b02789ba9c27"
HTML_OUTPUT_PROJECT = os.path.join(PROJECT_ROOT, "研究/现货价差专题/上海卷螺差现货_季节看板.html")
HTML_OUTPUT_ARTIFACT = os.path.join(ARTIFACT_DIR, "shanghai_spot_coil_rebar_spread_seasonality.html")

with open(JSON_PATH, "r", encoding="utf-8") as f:
    raw_data = json.load(f)

json_str = json.dumps(raw_data, ensure_ascii=False)

html_template = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>上海现货卷螺差季节看板 (上海热卷 - 上海螺纹)</title>
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
          <h1 class="text-2xl font-bold tracking-tight text-[var(--foreground,#f8fafc)]">上海现货卷螺差 按年划分季节图</h1>
          <span class="badge bg-sky-500/20 text-sky-400 border border-sky-500/30">Wind 官方同城现货</span>
        </div>
        <p class="text-sm text-[var(--muted-foreground,#94a3b8)] mt-1">
          口径: 上海热轧板卷(Q235B 4.75mm, S0033272) - 上海螺纹钢(HRB400E 20mm, S0033227) | 数据周期: 2018 - 2026年 (截至 2026-09-22)
        </p>
      </div>
      <div class="text-right">
        <div class="text-xs text-[var(--muted-foreground,#94a3b8)]">最新数据时点</div>
        <div class="text-sm font-semibold text-[var(--accent,#38bdf8)]">2026-09-22 现货收盘</div>
      </div>
    </div>

    <!-- 关键指标卡片 -->
    <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground,#94a3b8)]">最新上海卷螺差 (2026-09-22)</div>
        <div class="text-2xl font-bold text-rose-500 mt-1 flex items-baseline gap-2">
          +20 <span class="text-xs font-normal text-[var(--muted-foreground,#94a3b8)]">元/吨</span>
        </div>
        <div class="text-xs text-rose-400/80 mt-1">热卷 3290 vs 螺纹 3270 (微幅升水)</div>
      </div>

      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground,#94a3b8)]">近5年同期均值 (09-22)</div>
        <div class="text-2xl font-bold text-[var(--foreground,#f8fafc)] mt-1 flex items-baseline gap-2">
          -6 <span class="text-xs font-normal text-[var(--muted-foreground,#94a3b8)]">元/吨</span>
        </div>
        <div class="text-xs text-emerald-400 mt-1">历史同期长材略占优，当前强于均值</div>
      </div>

      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground,#94a3b8)]">2026年波动区间</div>
        <div class="text-2xl font-bold text-sky-400 mt-1 flex items-baseline gap-2">
          -60 ~ +220 <span class="text-xs font-normal text-[var(--muted-foreground,#94a3b8)]">元/吨</span>
        </div>
        <div class="text-xs text-sky-400/80 mt-1">年度均值 +102.1 元/吨</div>
      </div>

      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-4 shadow-sm">
        <div class="text-xs font-medium text-[var(--muted-foreground,#94a3b8)]">当前所处阶段</div>
        <div class="text-2xl font-bold text-amber-400 mt-1 flex items-baseline gap-2">
          金九收敛期
        </div>
        <div class="text-xs text-amber-400/80 mt-1">从8月峰值 +200 回落至平水附近</div>
      </div>
    </div>

    <!-- 图表容器 -->
    <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-5 shadow-sm space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex items-center gap-2">
          <span class="text-sm font-semibold text-[var(--foreground,#f8fafc)]">年份筛选:</span>
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
          <span>📊</span> 上海同城卷螺差核心季节规律
        </h3>
        <ul class="text-sm text-[var(--muted-foreground,#94a3b8)] space-y-2 leading-relaxed">
          <li>• <strong class="text-slate-200">夏季走阔 (6-8月):</strong> 高温暴雨致户外建筑施工停工，螺纹现货淡季累库走弱；而热卷受制造业平稳排产与外需出口托底，上海卷螺差常年走阔（2026年夏季峰值达 +220 元/吨）。</li>
          <li>• <strong class="text-slate-200">金九收敛 (9-10月):</strong> 随着秋季施工黄金期到来，建筑钢材表需脉冲式回升，螺纹现货大幅走强，卷螺差步入快速收窄阶段，历史同期甚至频繁击穿零轴转为深度贴水（如2018年-340、2024年-160）。</li>
          <li>• <strong class="text-slate-200">当前2026节律:</strong> 2026年9月上海卷螺差从8月高位 +200 元/吨快速回落至最新的 +20 元/吨，完全契合“金九”季节性收敛规律。</li>
        </ul>
      </div>

      <div class="bg-[var(--card,#1e293b)] border border-[var(--border,#334155)] rounded-xl p-5 shadow-sm space-y-3">
        <h3 class="text-base font-semibold text-rose-400 flex items-center gap-2">
          <span>🔍</span> 上海同城口径 vs 跨区域跨品种口径区别
        </h3>
        <ul class="text-sm text-[var(--muted-foreground,#94a3b8)] space-y-2 leading-relaxed">
          <li>• <strong class="text-slate-200">上海同城现货卷螺差:</strong> 上海热卷与上海螺纹均为上海本地库提现货，剔除了跨省运费和区域供需错配，最纯粹地反映板材与长材在华东中心市场的供需剪刀差。</li>
          <li>• <strong class="text-slate-200">杭州中天 vs 上海本地:</strong> 杭州通常为华东建筑钢材的定价高地（中天螺纹常比上海螺纹高出 50~100 元/吨，但近期杭州螺纹偏弱至 3160 元/吨，而上海螺纹为 3270 元/吨），因此上海同城卷螺差 (+20) 会比上海-杭州跨区卷螺差 (+150) 更贴近上海本地市场的实际供求格局。</li>
        </ul>
      </div>
    </div>

  </div>

  <script>
    const rawData = __DATA_PLACEHOLDER__;
    const years = ['2018', '2019', '2020', '2021', '2022', '2023', '2024', '2025', '2026'];
    const colors = {
      '2018': '#64748b',
      '2019': '#0284c7',
      '2020': '#38bdf8',
      '2021': '#8b5cf6',
      '2022': '#0d9488',
      '2023': '#10b981',
      '2024': '#f59e0b',
      '2025': '#f97316',
      '2026': '#ef4444',
      '5Y_Avg': '#cbd5e1'
    };

    const activeYears = {
      '2018': false,
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

    const dateList = [];
    const daysInMonth = [31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    for (let m = 1; m <= 12; m++) {
      for (let d = 1; d <= daysInMonth[m - 1]; d++) {
        const mm = String(m).padStart(2, '0');
        const dd = String(d).padStart(2, '0');
        dateList.push(`${mm}-${dd}`);
      }
    }

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

    const yMin = -750;
    const yMax = 800;

    function getY(val) {
      return chartBounds.top + chartBounds.height - ((val - yMin) / (yMax - yMin)) * chartBounds.height;
    }

    function getX(index) {
      return chartBounds.left + (index / (dateList.length - 1)) * chartBounds.width;
    }

    function drawChart() {
      const rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);

      ctx.lineWidth = 1;
      const yTicks = [-600, -400, -200, 0, 200, 400, 600];
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
    print(f"Generated Shanghai spread HTML dashboard: {p}")
