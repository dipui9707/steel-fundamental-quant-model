#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_d/entry_exit_research.py
功能: 阶段 D 入场与退出机制量化研究引擎 (Entry & Exit Analytics Engine)
职责:
  严格遵循《实施手册》第 19 节与 A05/A05.3 规范:
  1. 恪守 State != Position 铁律，研究从“状态识别”到“信号触发与平仓规则”的动力学转换;
  2. 入场确认机制实证对比:
     - 立即入场 (Immediate Entry);
     - 现货微观确认入场 (Spot Confirmed Entry);
     - 价格均线突破顺势入场 (Momentum / MA Breakout Entry);
     - 回踩均线支撑逢低入场 (Pullback Entry);
  3. 退出规则实证对比:
     - 固定期限退出 (Fixed Horizon: 5, 10, 20d);
     - 状态恶化/降级断路退出 (State Deterioration Exit);
     - 跟踪移动止损退出 (Trailing Stop: 2.5% 动态回撤保护);
     - 目标分位止盈退出 (MFE Target Saturation: 达到 4% 阶梯获利结平);
     - 背离消解与均值回归退出 (Divergence Resolution Exit);
  4. 摩擦成本敏感性: 测算手续费与滑点下的净胜率与盈亏平衡点。
"""

from typing import Dict, Any, List, Optional, Tuple
import pandas as pd
import numpy as np


class EntryExitResearchEngine:
    """
    入场与退出机制量化研究引擎
    """

    def __init__(
        self,
        features_df: pd.DataFrame,
        state_matrix: pd.DataFrame,
    ):
        self.features_df = features_df.copy()
        self.state_matrix = state_matrix.copy()

        assert (self.features_df.index == self.state_matrix.index).all(), "特征宽表与状态矩阵必须严格对齐"

        # 准备价格与均线序列
        self._prepare_price_technicals()

    def _prepare_price_technicals(self):
        """计算基础技术均线与真实波幅 (ATR) 供入场/退出比对使用"""
        close = self.features_df["rb_close"]
        high = self.features_df["rb_high"]
        low = self.features_df["rb_low"]

        self.features_df["ma5"] = close.rolling(5).mean()
        self.features_df["ma20"] = close.rolling(20).mean()
        self.features_df["ma60"] = close.rolling(60).mean()

        tr1 = high - low
        tr2 = (high - close.shift(1)).abs()
        tr3 = (low - close.shift(1)).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        self.features_df["atr14"] = tr.rolling(14).mean()

    def evaluate_entry_timing_comparison(
        self,
        base_state_filter: pd.Series,
        direction: str = "long",
        horizon: int = 20,
    ) -> pd.DataFrame:
        """
        对比不同入场时机与确认机制的绩效分布:
        1. Immediate: 满足 base_state_filter 的第一天收盘入场
        2. Spot Confirmed: 满足 base_state 且 spot_confirmation == 'Confirmed'
        3. Momentum Breakout: 满足 base_state 且 close > ma20 且 ma5 > ma20
        4. Pullback / Dip: 满足 base_state 且 (low <= ma5) 且 (close >= ma5) (回踩企稳)
        """
        close = self.features_df["rb_close"]
        high = self.features_df["rb_high"]
        low = self.features_df["rb_low"]
        ma5 = self.features_df["ma5"]
        ma20 = self.features_df["ma20"]
        spot_conf = self.state_matrix["spot_confirmation"]

        # 仅取状态初次成立的触发点 (从 False 变为 True) 或持续状态首日
        is_active = base_state_filter.fillna(False)
        entry_trigger = is_active & (is_active.shift(1).fillna(False) == False)

        entry_modes = {
            "1. 触发即入 (Immediate Entry)": entry_trigger,
            "2. 现货微观确认 (Spot Confirmed)": is_active & (spot_conf == "Confirmed"),
            "3. 动量均线突破 (Momentum Breakout)": is_active & (close > ma20) & (ma5 > ma20),
            "4. 回踩均线企稳 (Pullback to MA5)": is_active & (low <= ma5 * 1.005) & (close >= ma5 * 0.995),
        }

        records = []
        for mode_name, mask in entry_modes.items():
            valid_idx = self.features_df.index[mask]
            # 过滤掉末尾无法观察完整 horizon 的样本
            valid_idx = [t for t in valid_idx if self.features_df.index.get_loc(t) + horizon < len(self.features_df)]
            n = len(valid_idx)
            if n < 5:
                continue

            rets = []
            mfes = []
            maes = []

            for dt in valid_idx:
                loc = self.features_df.index.get_loc(dt)
                c0 = close.iloc[loc]
                c_exit = close.iloc[loc + horizon]
                h_max = high.iloc[loc + 1: loc + horizon + 1].max()
                l_min = low.iloc[loc + 1: loc + horizon + 1].min()

                if direction == "long":
                    r = (c_exit - c0) / c0
                    mfe = (h_max - c0) / c0
                    mae = (l_min - c0) / c0
                else:
                    r = (c0 - c_exit) / c0
                    mfe = (c0 - l_min) / c0
                    mae = (c0 - h_max) / c0

                rets.append(r)
                mfes.append(max(0.0, mfe))
                maes.append(min(0.0, mae))

            rets_arr = np.array(rets)
            mfes_arr = np.array(mfes)
            maes_arr = np.array(maes)

            mean_r = float(rets_arr.mean()) * 100.0
            std_r = float(rets_arr.std(ddof=1)) * 100.0 if n > 1 else 1.0
            win_rate = float(np.mean(rets_arr > 0)) * 100.0
            mean_mfe = float(mfes_arr.mean()) * 100.0
            mean_mae = float(maes_arr.mean()) * 100.0
            abs_mae = abs(mean_mae) if abs(mean_mae) > 1e-4 else 1e-4
            elasticity = mean_mfe / abs_mae
            ann_factor = 250.0 / horizon
            sharpe = (mean_r / std_r) * np.sqrt(ann_factor) if std_r > 0 else 0.0

            records.append({
                "entry_mode": mode_name,
                "direction": direction.upper(),
                "horizon_days": horizon,
                "sample_count": n,
                "win_rate_pct": round(win_rate, 2),
                "mean_return_pct": round(mean_r, 2),
                "mean_mfe_pct": round(mean_mfe, 2),
                "mean_mae_pct": round(mean_mae, 2),
                "elasticity_ratio": round(elasticity, 2),
                "sharpe_ratio": round(sharpe, 2),
            })

        return pd.DataFrame(records)

    def evaluate_exit_mechanisms_comparison(
        self,
        base_state_filter: pd.Series,
        direction: str = "long",
        max_holding_days: int = 30,
        trailing_stop_pct: float = 0.025,
        target_profit_pct: float = 0.040,
    ) -> pd.DataFrame:
        """
        对比不同平仓退出逻辑的损益与持仓周期特征:
        1. Fixed Horizon (固定 10d 平仓)
        2. Fixed Horizon (固定 20d 平仓)
        3. State Deterioration (状态变质/不再满足 base_state_filter 即平仓)
        4. Trailing Stop (价格自入场后最高点回撤 >= 2.5% 平仓)
        5. Target Saturation (收益率达到 4.0% 止盈平仓)
        6. Combined Rule (Trailing Stop 止损 + Target 止盈 + 状态变质三重门)
        """
        close = self.features_df["rb_close"]
        high = self.features_df["rb_high"]
        low = self.features_df["rb_low"]

        is_active = base_state_filter.fillna(False)
        entry_triggers = is_active & (is_active.shift(1).fillna(False) == False)
        valid_indices = self.features_df.index[entry_triggers]

        # 过滤过近无法回溯的样本
        valid_indices = [t for t in valid_indices if self.features_df.index.get_loc(t) + max_holding_days < len(self.features_df)]
        if len(valid_indices) < 5:
            return pd.DataFrame()

        def simulate_rule(rule_name: str) -> Dict[str, Any]:
            trade_rets = []
            trade_durs = []
            max_drawdowns = []

            for dt in valid_indices:
                loc = self.features_df.index.get_loc(dt)
                p_entry = close.iloc[loc]

                peak_favorable = 0.0
                exit_price = p_entry
                exit_step = max_holding_days

                for tau in range(1, max_holding_days + 1):
                    cur_c = close.iloc[loc + tau]
                    cur_h = high.iloc[loc + tau]
                    cur_l = low.iloc[loc + tau]
                    cur_active = is_active.iloc[loc + tau]

                    if direction == "long":
                        cur_gain = (cur_h - p_entry) / p_entry
                        cur_dd = (cur_l - p_entry) / p_entry
                        cur_close_gain = (cur_c - p_entry) / p_entry
                        peak_favorable = max(peak_favorable, cur_gain)
                        pullback_from_peak = (cur_h - cur_l) / cur_h if cur_h > 0 else 0.0
                    else:
                        cur_gain = (p_entry - cur_l) / p_entry
                        cur_dd = (p_entry - cur_h) / p_entry
                        cur_close_gain = (p_entry - cur_c) / p_entry
                        peak_favorable = max(peak_favorable, cur_gain)

                    # 规则判断
                    should_exit = False
                    if rule_name == "Fixed 10d" and tau == 10:
                        should_exit = True
                    elif rule_name == "Fixed 20d" and tau == 20:
                        should_exit = True
                    elif rule_name == "State Deterioration" and not cur_active:
                        should_exit = True
                    elif rule_name == "Trailing Stop (2.5%)":
                        # 回撤达到 2.5%
                        if direction == "long" and (p_entry * (1.0 + peak_favorable) - cur_l) / p_entry >= trailing_stop_pct:
                            should_exit = True
                        elif direction == "short" and (cur_h - p_entry * (1.0 - peak_favorable)) / p_entry >= trailing_stop_pct:
                            should_exit = True
                    elif rule_name == "Target Saturation (4.0%)" and cur_gain >= target_profit_pct:
                        should_exit = True
                    elif rule_name == "Triple Guard (状态+移动止损+止盈)":
                        if not cur_active:
                            should_exit = True
                        elif cur_gain >= target_profit_pct:
                            should_exit = True
                        elif direction == "long" and (p_entry * (1.0 + peak_favorable) - cur_l) / p_entry >= trailing_stop_pct:
                            should_exit = True
                    elif tau == max_holding_days:
                        should_exit = True

                    if should_exit:
                        exit_price = cur_c
                        exit_step = tau
                        break

                pnl = (exit_price - p_entry) / p_entry if direction == "long" else (p_entry - exit_price) / p_entry
                trade_rets.append(pnl)
                trade_durs.append(exit_step)

            rets_arr = np.array(trade_rets)
            durs_arr = np.array(trade_durs)
            n_trades = len(rets_arr)

            mean_pnl = float(rets_arr.mean()) * 100.0
            win_rate = float(np.mean(rets_arr > 0)) * 100.0
            mean_dur = float(durs_arr.mean())
            wins = rets_arr[rets_arr > 0]
            losses = rets_arr[rets_arr < 0]
            avg_w = float(wins.mean()) if len(wins) > 0 else 0.0
            avg_l = abs(float(losses.mean())) if len(losses) > 0 else 1e-6
            pl_ratio = avg_w / avg_l if avg_l > 0 else 0.0

            ann_ret = (mean_pnl / mean_dur) * 250.0 if mean_dur > 0 else 0.0

            return {
                "exit_rule": rule_name,
                "direction": direction.upper(),
                "trades_count": n_trades,
                "mean_holding_days": round(mean_dur, 1),
                "win_rate_pct": round(win_rate, 2),
                "mean_pnl_pct": round(mean_pnl, 2),
                "profit_loss_ratio": round(pl_ratio, 2),
                "annualized_pnl_pct": round(ann_ret, 2),
            }

        rules = [
            "Fixed 10d",
            "Fixed 20d",
            "State Deterioration",
            "Trailing Stop (2.5%)",
            "Target Saturation (4.0%)",
            "Triple Guard (状态+移动止损+止盈)",
        ]

        records = [simulate_rule(r) for r in rules]
        return pd.DataFrame(records)

    def evaluate_friction_sensitivity(
        self,
        base_returns: pd.Series,
        slippage_ticks_list: Optional[List[int]] = None,
        fee_rate_bps: float = 1.0,  # 万分之一
    ) -> pd.DataFrame:
        """
        摩擦成本敏感性分析:
        评估手续费 (单边 fee_rate_bps) 与滑点 (1~3 ticks, 螺纹 1 tick = 1元) 对净收益率的衰减影响
        """
        ticks = slippage_ticks_list or [0, 1, 2, 3]
        avg_price = float(self.features_df["rb_close"].mean())
        clean_ret = base_returns.dropna().values
        n = len(clean_ret)

        records = []
        for t in ticks:
            # 往返滑点比例: (t * 2 ticks / avg_price)
            slip_pct = (t * 2.0 / avg_price)
            # 往返手续费: 2 * fee_rate_bps / 10000
            fee_pct = (2.0 * fee_rate_bps / 10000.0)
            total_cost = slip_pct + fee_pct

            net_rets = clean_ret - total_cost
            mean_net = float(net_rets.mean()) * 100.0
            win_net = float(np.mean(net_rets > 0)) * 100.0

            records.append({
                "slippage_ticks": t,
                "round_trip_cost_bps": round(total_cost * 10000.0, 1),
                "round_trip_cost_pct": round(total_cost * 100.0, 3),
                "gross_mean_return_pct": round(float(clean_ret.mean()) * 100.0, 2),
                "net_mean_return_pct": round(mean_net, 2),
                "net_win_rate_pct": round(win_net, 2),
            })

        return pd.DataFrame(records)
