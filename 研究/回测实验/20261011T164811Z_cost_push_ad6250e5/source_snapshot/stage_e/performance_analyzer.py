#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/performance_analyzer.py
功能: 阶段 E 策略回测绩效评估与统计归因分析引擎 (Performance Analyzer)
职责:
  1. 计算国际标准量化基金绩效指标:
     - 累计收益率 (Total Return)、年化复合增长率 (CAGR);
     - 年化波动率 (Volatility)、夏普比率 (Sharpe Ratio, Rf=2%);
     - 索提诺比率 (Sortino Ratio)、卡玛比率 (Calmar Ratio);
     - 最大回撤 (Max Drawdown)、最长回撤持续天数 (MDD Duration);
  2. 统计逐笔交易微观指标:
     - 总交易笔数、多空分布、胜率 (Win Rate);
     - 盈亏比 (Profit Factor)、平均单笔盈亏、盈亏赔率比 (Payoff Ratio);
     - 最大连续盈利/亏损笔数;
  3. 生成月度收益矩阵与年度绩效汇总表;
  4. 支持策略 vs 对照组 vs 基准多维度横向比对。
"""

from typing import Dict, Any, Optional, List, Tuple
import pandas as pd
import numpy as np


class PerformanceAnalyzer:
    """
    量化绩效与归因评估器
    """

    def __init__(self, risk_free_rate: float = 0.02, trading_days_per_year: int = 250):
        self.rf = risk_free_rate
        self.annual_days = trading_days_per_year

    def analyze_equity_and_trades(
        self,
        equity_df: pd.DataFrame,
        trades_df: pd.DataFrame,
        strategy_name: str = "Stage_E_Strategy",
    ) -> Dict[str, Any]:
        """
        全面计算回测账户净值曲线与交易流水的综合绩效
        """
        if equity_df.empty:
            return {"strategy_name": strategy_name, "error": "Empty equity series"}

        eq = equity_df["total_equity"].astype(float)
        ret = equity_df["daily_return"].astype(float)
        n_days = len(eq)

        initial_capital = float(eq.iloc[0])
        final_equity = float(eq.iloc[-1])
        total_return = (final_equity / initial_capital) - 1.0

        years = max(0.1, n_days / self.annual_days)
        cagr = (final_equity / initial_capital) ** (1.0 / years) - 1.0 if final_equity > 0 else -1.0

        daily_std = ret.std()
        ann_vol = daily_std * np.sqrt(self.annual_days) if daily_std > 0 else 0.0

        # 夏普比率 (扣除无风险利率 2%)
        excess_ret = float(ret.mean()) * self.annual_days - self.rf
        sharpe = excess_ret / ann_vol if ann_vol > 0 else 0.0

        # 下行波动率与索提诺比率
        downside_ret = ret[ret < 0]
        downside_std = np.sqrt(np.mean(np.minimum(ret - self.rf / self.annual_days, 0.0) ** 2) * self.annual_days)
        sortino = excess_ret / downside_std if downside_std > 0 else 0.0

        # 最大回撤与持续期
        peak = eq.cummax()
        dd_series = (eq - peak) / peak
        max_dd = float(dd_series.min())

        # 计算最长回撤持续期 (Drawdown Duration)
        is_dd = dd_series < 0
        dd_groups = (~is_dd).cumsum()[is_dd]
        mdd_duration = int(dd_groups.value_counts().max()) if not dd_groups.empty else 0

        # 卡玛比率 (CAGR / |MaxDD|)
        calmar = cagr / abs(max_dd) if max_dd < 0 else 0.0

        # 交易微观统计
        trade_stats = self._analyze_trades(trades_df)

        # 换手率与摩擦统计
        tot_fees = float(equity_df["cumulative_fees"].iloc[-1]) if "cumulative_fees" in equity_df else 0.0
        tot_slip = float(equity_df["cumulative_slippage"].iloc[-1]) if "cumulative_slippage" in equity_df else 0.0
        avg_leverage = float(equity_df["effective_leverage"].mean()) if "effective_leverage" in equity_df else 0.0

        # 月度收益矩阵
        monthly_table = self._build_monthly_table(equity_df)

        return {
            "strategy_name": strategy_name,
            "start_date": str(equity_df["date"].iloc[0]),
            "end_date": str(equity_df["date"].iloc[-1]),
            "total_trading_days": n_days,
            "initial_capital": initial_capital,
            "final_equity": final_equity,
            "total_return_pct": round(total_return * 100, 2),
            "cagr_pct": round(cagr * 100, 2),
            "annualized_volatility_pct": round(ann_vol * 100, 2),
            "sharpe_ratio": round(sharpe, 2),
            "sortino_ratio": round(sortino, 2),
            "calmar_ratio": round(calmar, 2),
            "max_drawdown_pct": round(max_dd * 100, 2),
            "max_drawdown_duration_days": mdd_duration,
            "average_leverage": round(avg_leverage, 4),
            "total_fees_cny": round(tot_fees, 2),
            "total_slippage_cny": round(tot_slip, 2),
            **trade_stats,
            "monthly_returns_table": monthly_table,
        }

    def _analyze_trades(self, trades_df: pd.DataFrame) -> Dict[str, Any]:
        """统计逐笔交易明细指标"""
        if trades_df.empty:
            return {
                "total_trades": 0,
                "win_trades": 0,
                "loss_trades": 0,
                "win_rate_pct": 0.0,
                "profit_factor": 0.0,
                "payoff_ratio": 0.0,
                "avg_trade_pnl": 0.0,
                "max_win_trade": 0.0,
                "max_loss_trade": 0.0,
                "max_consecutive_wins": 0,
                "max_consecutive_losses": 0,
            }

        pnl = trades_df["pnl"].astype(float)
        total_trades = len(pnl)
        win_mask = pnl > 0
        loss_mask = pnl < 0

        win_trades = int(win_mask.sum())
        loss_trades = int(loss_mask.sum())
        win_rate = (win_trades / total_trades) * 100 if total_trades > 0 else 0.0

        gross_profit = float(pnl[win_mask].sum()) if win_trades > 0 else 0.0
        gross_loss = abs(float(pnl[loss_mask].sum())) if loss_trades > 0 else 0.0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else (99.0 if gross_profit > 0 else 0.0)

        avg_win = gross_profit / win_trades if win_trades > 0 else 0.0
        avg_loss = gross_loss / loss_trades if loss_trades > 0 else 0.0
        payoff_ratio = avg_win / avg_loss if avg_loss > 0 else 0.0

        # 最大连续胜负
        consecutive_wins = 0
        consecutive_losses = 0
        cur_w = 0
        cur_l = 0
        for val in pnl:
            if val > 0:
                cur_w += 1
                cur_l = 0
                consecutive_wins = max(consecutive_wins, cur_w)
            elif val < 0:
                cur_l += 1
                cur_w = 0
                consecutive_losses = max(consecutive_losses, cur_l)
            else:
                cur_w = 0
                cur_l = 0

        return {
            "total_trades": total_trades,
            "win_trades": win_trades,
            "loss_trades": loss_trades,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": round(profit_factor, 2),
            "payoff_ratio": round(payoff_ratio, 2),
            "avg_trade_pnl": round(float(pnl.mean()), 2),
            "max_win_trade": round(float(pnl.max()), 2),
            "max_loss_trade": round(float(pnl.min()), 2),
            "max_consecutive_wins": consecutive_wins,
            "max_consecutive_losses": consecutive_losses,
        }

    def _build_monthly_table(self, equity_df: pd.DataFrame) -> pd.DataFrame:
        """构建 年份 × 月份 收益率矩阵 (百分比)"""
        df = equity_df.copy()
        df["dt"] = pd.to_datetime(df["date"])
        df["year"] = df["dt"].dt.year
        df["month"] = df["dt"].dt.month

        # 取每个月末最后一天的净值
        monthly_last = df.groupby(["year", "month"])["net_asset_value"].last().reset_index()
        monthly_last["monthly_return"] = monthly_last["net_asset_value"].pct_change().fillna(
            monthly_last["net_asset_value"] - 1.0
        )

        pivot = monthly_last.pivot(index="year", columns="month", values="monthly_return")
        pivot = (pivot * 100).round(2)
        # 添加年度全收益
        yearly_last = df.groupby("year")["net_asset_value"].last()
        yearly_first = yearly_last.shift(1).fillna(1.0)
        pivot["YTD"] = ((yearly_last / yearly_first - 1.0) * 100).round(2)
        return pivot
