#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/tactical_exhaustion_engine.py
功能: 战术级动能衰竭与右侧微观拐点“全平全回补”量化执行引擎 (Tactical Exhaustion & Right-Side Pivot Engine)
定位:
  恪守用户决议: 不采用底仓加滚动仓拆分，维持最利落的 100% 全平与 100% 全额回补单轨执行架构。
四重升级机制:
  1. 【左侧异动预警 (Alert Only)】: 天量长影 Pinbar、持仓断崖减仓潮、VWAP 极端乖离仅作拉响警报，绝不提前跑路抢跑平仓;
  2. 【右侧微观拐点确认 (Right-Side Pivot Exit)】: 必须等 5 分钟图上跌破冲顶低点、跌破进攻均线 MA5 或顶底分型破位才果断全仓平仓锁利;
  3. 【价格保护防追单门禁 (Price Protection Gate)】: 回补价格必须优于或贴近平仓价，若因长假/隔夜大幅跳空劣于平仓价，一票否决回补，杜绝天价接盘;
  4. 【双重安全约束 (Safety Firewalls)】: 强制反抽波段最小空间与时间窗口，单日极窄止损上限 2 次自动熔断防磨损。
"""

from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class TacticalConfig:
    """战术执行引擎参数配置"""
    bias_threshold: float = 1.8         # VWAP 极端乖离率阈值 (%)
    vol_ratio_threshold: float = 2.2    # 异常放量倍数阈值 (相对20均量)
    shadow_threshold: float = 0.38      # 吸收滞涨/滞跌长影线比例
    oi_climax_threshold: float = -8000  # 3根Bar累计持仓断崖减仓手
    price_protection_tol: float = 10.0  # 价格保护容忍容限 (元/吨，超出严禁倒贴回补)
    min_pullback_space: float = 10.0    # 常规反抽/回调最小空间 (元/吨)
    min_gap_pullback_space: float = 20.0 # 跳空后允许重新回补所需的最小回调/反抽空间 (元/吨)
    enable_gap_pullback_reentry: bool = True # 是否开启跳空后价格充分回调继续执行回补
    enable_gap_exhaustion_exit: bool = True   # 是否开启跳空未延续即退出趋势模式 (用户核心逻辑)
    gap_confirm_bars: int = 4                 # 跳空确认观察窗口 (Bar数，如前4根5分钟Bar即20分钟)
    enable_choppy_exit: bool = True           # 是否开启震荡假突破快速退出与锁定 (震荡市及时识别)
    choppy_stagnant_bars: int = 8             # 假突破滞涨/滞跌最大容忍Bar数
    min_pullback_bars: int = 4          # 反抽/回调最小观察Bar数
    tight_stop_ticks: float = 2.0       # 极窄硬止损缓冲 (ticks)
    max_retries_per_day: int = 2        # 单日最大止损重试熔断次数
    commission_per_lot: float = 3.0     # 每手单边手续费 (元)
    slippage_ticks: float = 1.0         # 滑点每边 (ticks)
    
    # 15分钟全平门槛与趋势确立初期/中后期退出灵敏度 (用户进阶指导)
    trend_establishment_profit: float = 20.0 # 趋势确立所需的有利利润空间 (元/吨，超出转入中后期)
    early_stage_bars: int = 24               # 趋势确立初期蓄势窗口Bar数 (24根5m Bar = 2小时)
    enable_phase_sensitivity: bool = True     # 是否区分趋势确立初期与中后期退出灵敏度
    exit_timeframe: str = "15m"              # 全平判断时间级别: "15m" (推荐) 或 "5m"

    # 初始突破结构防守线 (解决初期恶性假突破识别与止损漏洞)
    enable_initial_structural_stop: bool = True  # 是否开启初始底仓突破结构防守线
    initial_stop_buffer_ticks: float = 15.0      # 初始突破结构极值缓冲 (ticks/点，螺纹热卷推荐15点容忍蓄势)
    max_initial_risk_points: float = 30.0        # 初始底仓最大允许试错空间 (元/吨)


@dataclass
class TacticalTrade:
    """战术交易流水记录"""
    trade_id: str
    trade_type: str        # "PIVOT_EXIT", "PIVOT_RE_ENTRY", "TIGHT_STOP_HIT", "INITIAL_BREAKOUT_FAILED", "GAP_EXHAUSTION_EXIT", "CHOPPY_REGIME_EXIT", "FINAL_CLOSE"
    time: str
    price: float
    direction: str         # "LONG", "SHORT", "FLAT"
    lots: int
    pnl: float = 0.0       # 平仓净盈亏 (已扣除手续费与滑点)
    fees: float = 0.0      # 本笔手续费
    reason: str = ""
    stop_loss_price: Optional[float] = None


class MicroFeatureEngineering:
    """分时 5分钟 微观结构与动力学特征工程"""

    @staticmethod
    def compute_features(df: pd.DataFrame) -> pd.DataFrame:
        data = df.copy()
        
        # 必须的基础列检查
        for col in ['open', 'high', 'low', 'close', 'volume', 'open_interest', 'trade_date']:
            if col not in data.columns:
                raise ValueError(f"缺少必要的基础字段: {col}")

        # 1. 日内分时成交均价 VWAP (每日按交易日重置累积)
        data['cum_vol'] = data.groupby('trade_date')['volume'].cumsum()
        data['turnover'] = data['close'] * data['volume']
        data['cum_turnover'] = data.groupby('trade_date')['turnover'].cumsum()
        data['intraday_vwap'] = np.where(data['cum_vol'] > 0, data['cum_turnover'] / data['cum_vol'], data['close'])

        # 2. VWAP 瞬时乖离率 (%)
        data['bias_vwap'] = (data['close'] - data['intraday_vwap']) / data['intraday_vwap'] * 100.0

        # 3. 成交量异动倍数 Vol_ratio (相对过去 20 根均量)
        data['vol_ma20'] = data['volume'].rolling(20, min_periods=5).mean()
        data['vol_ratio'] = np.where(data['vol_ma20'] > 0, data['volume'] / data['vol_ma20'], 1.0)

        # 4. 持仓量动力学变化
        data['delta_oi'] = data['open_interest'].diff().fillna(0)
        data['delta_oi_3bar'] = data['delta_oi'].rolling(3).sum()

        # 5. 微观 K 线形态与影线比例
        hl_range = data['high'] - data['low']
        data['shadow_lower'] = np.where(hl_range > 0, (np.minimum(data['open'], data['close']) - data['low']) / hl_range, 0.0)
        data['shadow_upper'] = np.where(hl_range > 0, (data['high'] - np.maximum(data['open'], data['close'])) / hl_range, 0.0)

        # 6. 短期与中期均线及布林通道 (严格时序向前计算)
        data['ma5'] = data['close'].rolling(5, min_periods=2).mean()
        data['ma20'] = data['close'].rolling(20, min_periods=5).mean()
        data['std20'] = data['close'].rolling(20, min_periods=5).std().fillna(0)
        data['boll_up'] = data['ma20'] + 2.0 * data['std20']
        data['boll_down'] = data['ma20'] - 2.0 * data['std20']
        data['rolling_high_20'] = data['high'].shift(1).rolling(20, min_periods=5).max()
        data['rolling_low_20'] = data['low'].shift(1).rolling(20, min_periods=5).min()

        # 7. 15分钟级别中周期指标 (由 5m Bar 向前滚动聚合: 15m = 3根5m Bar)
        # 15m MA5 = 15根5m Bar (75分钟均线)
        data['ma15_5'] = data['close'].rolling(15, min_periods=5).mean()
        # 15m MA20 = 60根5m Bar (300分钟均线)
        data['ma15_20'] = data['close'].rolling(60, min_periods=15).mean()
        # 15m 结构极值 (过去 3 根 5m Bar = 15分钟结构极值点)
        data['rolling_high_15m'] = data['high'].shift(1).rolling(3, min_periods=1).max()
        data['rolling_low_15m'] = data['low'].shift(1).rolling(3, min_periods=1).min()

        return data


class TacticalExhaustionEngine:
    """
    战术级动能衰竭与右侧微观拐点“全平全回补”执行引擎
    """

    def __init__(self, config: Optional[TacticalConfig] = None):
        self.config = config or TacticalConfig()

    def run_backtest(
        self,
        df_5m: pd.DataFrame,
        trend_direction: str,  # "LONG" 或 "SHORT"
        initial_capital: float = 1_000_000.0,
        lots: int = 50,
        contract_multiplier: int = 10,
        start_idx: int = 10,
    ) -> Dict[str, Any]:
        """
        执行单波段行情回测
        """
        # 特征工程加工
        df = MicroFeatureEngineering.compute_features(df_5m)
        cfg = self.config
        
        tick_size = 1.0 if contract_multiplier == 10 else 0.5
        slippage_val = cfg.slippage_ticks * tick_size
        tight_stop_val = cfg.tight_stop_ticks * tick_size
        gap_pullback_val = cfg.min_gap_pullback_space if contract_multiplier == 10 else cfg.min_gap_pullback_space * 0.15

        # 基准组价格与利润计算 (单边持有死抱)
        if trend_direction == "LONG":
            base_entry = df.iloc[start_idx]['close'] + slippage_val
            base_exit = df.iloc[-1]['close'] - slippage_val
            base_pnl = (base_exit - base_entry) * lots * contract_multiplier - 2 * cfg.commission_per_lot * lots
        else:
            base_entry = df.iloc[start_idx]['close'] - slippage_val
            base_exit = df.iloc[-1]['close'] + slippage_val
            base_pnl = (base_entry - base_exit) * lots * contract_multiplier - 2 * cfg.commission_per_lot * lots

        # 策略状态机实时维护变量
        state = "IN_TREND"  # "IN_TREND", "OBSERVING_PULLBACK"
        position = lots if trend_direction == "LONG" else -lots
        current_entry = base_entry
        last_exit_price = base_entry
        
        trades: List[TacticalTrade] = []
        realized_pnl = 0.0
        total_commissions = cfg.commission_per_lot * lots  # 开仓初始手续费
        
        alert = False
        alert_reason = ""
        extreme_high = 0.0
        extreme_low = float('inf')
        gap_peak = 0.0
        gap_trough = float('inf')
        pullback_alert = False
        stop_loss_price = 0.0
        retries_today = 0
        current_date = df.iloc[start_idx]['trade_date']
        equity_curve = []
        trade_counter = 0

        # 初始底仓突破结构防守线 (解决初期恶性假突破漏洞)
        is_initial_position = True
        if cfg.enable_initial_structural_stop:
            pre_start = max(0, start_idx - 2)
            if trend_direction == "LONG":
                structural_low = df.iloc[pre_start:start_idx + 1]['low'].min()
                calc_stop = structural_low - cfg.initial_stop_buffer_ticks * tick_size
                stop_loss_price = max(calc_stop, base_entry - cfg.max_initial_risk_points)
            else:
                structural_high = df.iloc[pre_start:start_idx + 1]['high'].max()
                calc_stop = structural_high + cfg.initial_stop_buffer_ticks * tick_size
                stop_loss_price = min(calc_stop, base_entry + cfg.max_initial_risk_points)

        # 趋势失效与震荡假突破追踪变量
        bars_in_position = 0
        entry_bar_low = df.iloc[start_idx]['low']
        entry_bar_high = df.iloc[start_idx]['high']
        max_fav_price = base_entry
        min_fav_price = base_entry
        is_gap_day = False
        day_open = df.iloc[start_idx]['open']
        gap_bars_count = 0
        gap_initial_high = 0.0
        gap_initial_low = float('inf')

        for i in range(start_idx + 1, len(df)):
            row = df.iloc[i]
            prev = df.iloc[i - 1]
            c_date = row['trade_date']

            # 跨日重置单日试错计数与跳空开盘检测
            if c_date != current_date:
                current_date = c_date
                retries_today = 0
                day_open = row['open']
                gap_bars_count = 0
                
                # 检测跨日跳空缺口
                if trend_direction == "LONG":
                    gap_size = row['open'] - prev['close']
                    is_gap_day = (gap_size >= cfg.price_protection_tol)
                    gap_initial_high = row['high']
                    gap_initial_low = row['low']
                else:
                    gap_size = prev['close'] - row['open']
                    is_gap_day = (gap_size >= cfg.price_protection_tol)
                    gap_initial_high = row['high']
                    gap_initial_low = row['low']

            # 若已退出趋势模式，保持空仓观望并统计权益
            if state == "TREND_TERMINATED":
                equity_curve.append({
                    "bar_idx": i,
                    "datetime": row['datetime_str'],
                    "close": row['close'],
                    "position": 0,
                    "equity": initial_capital + realized_pnl
                })
                continue

            # 计算有利空间与阶段划分 (趋势确立初期 vs 中后期)
            if trend_direction == "LONG":
                fav_profit = max_fav_price - current_entry
            else:
                fav_profit = current_entry - min_fav_price
                
            profit_target = max(current_entry * 0.006, 5.0)
            is_early_stage = (
                cfg.enable_phase_sensitivity
                and (bars_in_position < cfg.early_stage_bars)
                and (fav_profit < profit_target)
            )

            # 趋势确立脱离成本区后，解除初始底仓脆弱状态并抬升至保本防守线
            if is_initial_position and (fav_profit >= profit_target):
                is_initial_position = False
                if cfg.enable_initial_structural_stop and stop_loss_price > 0:
                    if trend_direction == "LONG":
                        stop_loss_price = max(stop_loss_price, current_entry)
                    else:
                        stop_loss_price = min(stop_loss_price, current_entry)

            # =========================================================================
            # 分支 1: 多头大趋势波段 (LONG MODE)
            # =========================================================================
            if trend_direction == "LONG":
                # 1.0 跨日跳空动能耗尽与未延续退出趋势模式检查 (用户核心逻辑)
                if cfg.enable_gap_exhaustion_exit and is_gap_day:
                    gap_bars_count += 1
                    gap_initial_high = max(gap_initial_high, row['high'])
                    
                    if gap_bars_count <= cfg.gap_confirm_bars:
                        # 检查跳空后是否未能沿跳空方向运行或未立即收复 (用户核心哲学):
                        # 1) 跌破开盘价，且跌幅吞没跳空缺口的20%以上 (冲高断头铡出货)
                        # 2) 跌破开盘价，且跌破MA20或跌破前低
                        # 3) 确认窗口结束(第4根Bar)仍无法收复开盘价
                        gap_failed = (
                            (row['close'] < day_open - 1.0)
                            and (
                                (gap_size >= 20.0 and row['close'] < day_open - 0.2 * gap_size)
                                or (row['close'] < row['ma20'])
                                or (row['close'] < prev['low'])
                                or (gap_bars_count >= cfg.gap_confirm_bars)
                            )
                        )
                        if gap_failed:
                            trade_counter += 1
                            if position > 0:
                                exit_p = row['close'] - slippage_val
                                pnl = (exit_p - current_entry) * lots * contract_multiplier - cfg.commission_per_lot * lots
                                realized_pnl += pnl
                                total_commissions += cfg.commission_per_lot * lots
                                position = 0
                                trades.append(TacticalTrade(
                                    trade_id=f"TRD_{trade_counter:03d}",
                                    trade_type="GAP_EXHAUSTION_EXIT",
                                    time=row['datetime_str'],
                                    price=exit_p,
                                    direction="FLAT",
                                    lots=lots,
                                    pnl=pnl,
                                    fees=cfg.commission_per_lot * lots,
                                    reason=f"跳空未延续·跌破开盘套牢线({round(day_open, 1)}) -> 趋势改变退出趋势模式"
                                ))
                            else:
                                trades.append(TacticalTrade(
                                    trade_id=f"TRD_{trade_counter:03d}",
                                    trade_type="GAP_EXHAUSTION_EXIT",
                                    time=row['datetime_str'],
                                    price=row['close'],
                                    direction="FLAT",
                                    lots=0,
                                    pnl=0.0,
                                    fees=0.0,
                                    reason=f"跳空未延续·跌破开盘套牢线({round(day_open, 1)}) -> 趋势改变退出趋势模式，终止回补锁定利润"
                                ))
                            state = "TREND_TERMINATED"
                            equity_curve.append({
                                "bar_idx": i,
                                "datetime": row['datetime_str'],
                                "close": row['close'],
                                "position": 0,
                                "equity": initial_capital + realized_pnl
                            })
                            continue

                # 震荡假突破与停滞敏捷退出检查 (震荡市保护)
                if cfg.enable_choppy_exit and state == "IN_TREND" and position > 0:
                    bars_in_position += 1
                    max_fav_price = max(max_fav_price, row['high'])
                    
                    # 规则 A: 单日遭遇连续止损熔断 -> 判定为无序震荡洗盘，退出趋势模式
                    if retries_today >= cfg.max_retries_per_day:
                        trade_counter += 1
                        exit_p = row['close'] - slippage_val
                        pnl = (exit_p - current_entry) * lots * contract_multiplier - cfg.commission_per_lot * lots
                        realized_pnl += pnl
                        total_commissions += cfg.commission_per_lot * lots
                        position = 0
                        state = "TREND_TERMINATED"
                        trades.append(TacticalTrade(
                            trade_id=f"TRD_{trade_counter:03d}",
                            trade_type="CHOPPY_REGIME_EXIT",
                            time=row['datetime_str'],
                            price=exit_p,
                            direction="FLAT",
                            lots=lots,
                            pnl=pnl,
                            fees=cfg.commission_per_lot * lots,
                            reason="触发单日熔断上限(2次) -> 识别为无序震荡洗盘，退出趋势模式"
                        ))
                        equity_curve.append({
                            "bar_idx": i,
                            "datetime": row['datetime_str'],
                            "close": row['close'],
                            "position": 0,
                            "equity": initial_capital + realized_pnl
                        })
                        continue
                        
                    # 规则 B: 假突破停滞破位检查 (仅在尚未脱离成本确立趋势时生效)
                    # 给予充分蓄势突破空间 (24 根 5m Bar = 2 小时)，避免将趋势孕育期误判为震荡
                    limit_bars = cfg.choppy_stagnant_bars if (cfg.choppy_stagnant_bars != 8 and cfg.early_stage_bars == 24) or not cfg.enable_phase_sensitivity else cfg.early_stage_bars
                    if fav_profit < profit_target and bars_in_position >= limit_bars:
                        stagnant = (max_fav_price - current_entry < 5.0)
                        ma20_cond = (row['close'] < row['ma20']) if not pd.isna(row['ma20']) else True
                        broke_support = (row['close'] < entry_bar_low) and ma20_cond
                        if stagnant and broke_support:
                            trade_counter += 1
                            exit_p = row['close'] - slippage_val
                            pnl = (exit_p - current_entry) * lots * contract_multiplier - cfg.commission_per_lot * lots
                            realized_pnl += pnl
                            total_commissions += cfg.commission_per_lot * lots
                            position = 0
                            state = "TREND_TERMINATED"
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="CHOPPY_REGIME_EXIT",
                                time=row['datetime_str'],
                                price=exit_p,
                                direction="FLAT",
                                lots=lots,
                                pnl=pnl,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"持仓{bars_in_position}根Bar未脱离成本且破位 -> 识别为震荡假突破，退出趋势模式"
                            ))
                            equity_curve.append({
                                "bar_idx": i,
                                "datetime": row['datetime_str'],
                                "close": row['close'],
                                "position": 0,
                                "equity": initial_capital + realized_pnl
                            })
                            continue

                # 1.1 持有多头中: 15分钟级别全平门槛判断 (仅在趋势确立中后期生效，避免初期被洗盘误杀)
                if state == "IN_TREND" and position > 0 and not is_early_stage:
                    cond_bias = (row['bias_vwap'] >= cfg.bias_threshold) and (row['close'] > row['boll_up'])
                    cond_absorb = (row['vol_ratio'] >= cfg.vol_ratio_threshold) and (row['shadow_upper'] >= cfg.shadow_threshold) and (row['close'] >= row['rolling_high_20'])
                    cond_oi = (row['delta_oi_3bar'] <= cfg.oi_climax_threshold) and (row['vol_ratio'] >= 1.8) and (row['close'] >= row['rolling_high_20'])

                    if cond_bias or cond_absorb or cond_oi:
                        if not alert:
                            alert = True
                            alert_reason = "VWAP极端乖离" if cond_bias else ("天量吸收长上影" if cond_absorb else "多头断崖平仓潮")
                            extreme_high = row['high']
                            extreme_low = row['low']

                    if alert:
                        extreme_high = max(extreme_high, row['high'])
                        if cfg.exit_timeframe == "15m":
                            # 15分钟级别右侧确认: 破位 15m 结构低点，或连续跌破 15m MA5
                            pivot_break = (row['close'] < row['rolling_low_15m']) and (row['close'] < row['open'])
                            ma15_break = (row['close'] < row['ma15_5']) and (prev['close'] <= row['ma15_5']) and (row['close'] < extreme_high - 10.0)
                            trigger_exit = pivot_break or ma15_break
                            reason_str = "破15m结构低点" if pivot_break else "跌破15mMA5均线"
                        else:
                            pivot_break = (row['close'] < extreme_low) and (row['close'] < row['open'])
                            ma5_break = (row['close'] < row['ma5']) and (prev['close'] < row['ma5'] or row['close'] < prev['low'])
                            bear_engulf = (row['close'] < prev['open']) and (row['open'] >= prev['close']) and (row['close'] < prev['low'])
                            trigger_exit = pivot_break or (ma5_break and row['close'] < extreme_high - 6.0) or bear_engulf
                            reason_str = "破冲顶低点" if pivot_break else ("跌破MA5" if ma5_break else "阴包阳顶分型")

                        if trigger_exit:
                            trade_counter += 1
                            exit_p = row['close'] - slippage_val
                            pnl = (exit_p - current_entry) * lots * contract_multiplier - cfg.commission_per_lot * lots
                            realized_pnl += pnl
                            total_commissions += cfg.commission_per_lot * lots
                            last_exit_price = exit_p
                            
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="PIVOT_EXIT",
                                time=row['datetime_str'],
                                price=exit_p,
                                direction="FLAT",
                                lots=lots,
                                pnl=pnl,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"[{alert_reason}] -> {cfg.exit_timeframe}右侧【{reason_str}】全平止盈"
                            ))
                            
                            position = 0
                            state = "OBSERVING_PULLBACK"
                            is_initial_position = False  # 已成功兑现一次波段全平，解除初始底仓状态
                            alert = False
                            extreme_low = row['low']
                            gap_peak = row['high']
                            gap_pullback_trough = row['low']
                            pullback_alert = False
                            stop_loss_price = 0.0
                            continue

                # 1.2 空仓观察回调中: 检测【支撑预警】+【安全门禁/跳空回调】+【右侧企稳全额回补】
                elif state == "OBSERVING_PULLBACK":
                    extreme_low = min(extreme_low, row['low'])
                    
                    # 动态追踪跳空最高峰与跳空后的回调低点
                    if row['high'] > gap_peak:
                        gap_peak = row['high']
                        gap_pullback_trough = row['low']
                    else:
                        gap_pullback_trough = min(gap_pullback_trough, row['low'])
                        
                    pullback_depth = gap_peak - gap_pullback_trough
                    
                    near_vwap = (row['low'] <= row['intraday_vwap'] * 1.003) and (row['close'] >= row['intraday_vwap'] * 0.998)
                    pinbar_sup = (row['shadow_lower'] >= 0.35) and (row['vol_ratio'] <= 1.5)
                    gap_pullback_alert = (
                        cfg.enable_gap_pullback_reentry
                        and (pullback_depth >= gap_pullback_val)
                    )

                    if near_vwap or pinbar_sup or gap_pullback_alert:
                        pullback_alert = True

                    if pullback_alert and retries_today < cfg.max_retries_per_day:
                        bull_rev = (row['close'] > prev['high']) and (row['close'] > row['open'])
                        ma5_regain = (row['close'] > row['ma5']) and (prev['close'] <= prev['ma5']) and (row['close'] > row['open'])

                        if bull_rev or ma5_regain:
                            reenter_p = row['close'] + slippage_val
                            
                            # 核心安全防火墙判断:
                            # 1. 常规平价保护 (贴近平仓价)
                            is_price_fair = (reenter_p <= last_exit_price + cfg.price_protection_tol)
                            # 2. 跳空后深幅回调企稳判断 (用户指定: 跳空后若价格回调充分，继续执行回补)
                            is_gap_pullback_ready = (
                                cfg.enable_gap_pullback_reentry
                                and (pullback_depth >= gap_pullback_val)
                            )
                            
                            if not (is_price_fair or is_gap_pullback_ready):
                                # 既不贴近平仓价，跳空后回调也不充分 (盲目追高)，触发一票否决!
                                pullback_alert = False
                                continue
                            
                            trade_counter += 1
                            position = lots
                            current_entry = reenter_p
                            total_commissions += cfg.commission_per_lot * lots
                            
                            # 若为跳空回调回补，止损设在跳空回调最低点下方 2 ticks，否则设在 extreme_low 下方 2 ticks
                            active_stop_base = gap_pullback_trough if (not is_price_fair and is_gap_pullback_ready) else extreme_low
                            stop_loss_price = active_stop_base - tight_stop_val
                            state = "IN_TREND"
                            is_initial_position = False  # 回补仓为波段接力仓，非初始脆弱期底仓
                            pullback_alert = False
                            bars_in_position = 0
                            entry_bar_low = row['low']
                            entry_bar_high = row['high']
                            max_fav_price = row['close']
                            min_fav_price = row['close']
                            
                            reentry_tag = f"跳空回调{round(pullback_depth, 1)}点企稳" if (not is_price_fair and is_gap_pullback_ready) else "右侧企稳"
                            reason_str = "底分型反转突破前高" if bull_rev else "实体大阳翻上MA5"
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="PIVOT_RE_ENTRY",
                                time=row['datetime_str'],
                                price=reenter_p,
                                direction="LONG",
                                lots=lots,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"回调企稳 -> 【{reentry_tag}·{reason_str}】安全回补",
                                stop_loss_price=stop_loss_price
                            ))
                            continue

                # 1.3 止损盯市: 初始底仓结构防守止损 vs 中途回补极窄止损
                if state == "IN_TREND" and position > 0 and stop_loss_price > 0:
                    if row['low'] <= stop_loss_price:
                        trade_counter += 1
                        stop_p = stop_loss_price - slippage_val
                        pnl = (stop_p - current_entry) * lots * contract_multiplier - cfg.commission_per_lot * lots
                        realized_pnl += pnl
                        total_commissions += cfg.commission_per_lot * lots
                        
                        if is_initial_position:
                            # 初始底仓在建仓初期直接被打穿结构防守线 -> 识别为恶性假突破，趋势破坏！
                            position = 0
                            state = "TREND_TERMINATED"  # 彻底退出趋势模式，空仓锁定，绝不盲目回补
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="INITIAL_BREAKOUT_FAILED",
                                time=row['datetime_str'],
                                price=stop_p,
                                direction="FLAT",
                                lots=lots,
                                pnl=pnl,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"跌破初始突破防守线({round(stop_loss_price, 1)}) -> 假突破趋势破坏，退出趋势模式",
                                stop_loss_price=stop_loss_price
                            ))
                            equity_curve.append({
                                "bar_idx": i,
                                "datetime": row['datetime_str'],
                                "close": row['close'],
                                "position": 0,
                                "equity": initial_capital + realized_pnl
                            })
                            continue
                        else:
                            # 中途回补仓位的极窄硬止损
                            retries_today += 1
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="TIGHT_STOP_HIT",
                                time=row['datetime_str'],
                                price=stop_p,
                                direction="FLAT",
                                lots=lots,
                                pnl=pnl,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"跌破拐点极窄硬止损 (微损仅 {round(current_entry - stop_p, 1)} 元/吨)",
                                stop_loss_price=stop_loss_price
                            ))
                            position = 0
                            state = "OBSERVING_PULLBACK"
                            stop_loss_price = 0.0
                            continue

            # =========================================================================
            # 分支 2: 空头大趋势波段 (SHORT MODE - 严格镜像对称)
            # =========================================================================
            else:
                # 2.0 跨日跳空动能耗尽与未延续退出趋势模式检查 (用户核心逻辑)
                if cfg.enable_gap_exhaustion_exit and is_gap_day:
                    gap_bars_count += 1
                    gap_initial_low = min(gap_initial_low, row['low'])
                    
                    if gap_bars_count <= cfg.gap_confirm_bars:
                        # 检查跳空低开后是否未能沿空头方向运行或未立即收复 (用户核心哲学):
                        # 1) 突破站上开盘价，且反弹吞没跳空缺口的20%以上
                        # 2) 突破站上开盘价，且突破MA20或突破前高
                        # 3) 确认窗口结束(第4根Bar)仍无法下破/收复开盘价
                        gap_failed = (
                            (row['close'] > day_open + 1.0)
                            and (
                                (gap_size >= 20.0 and row['close'] > day_open + 0.2 * gap_size)
                                or (row['close'] > row['ma20'])
                                or (row['close'] > prev['high'])
                                or (gap_bars_count >= cfg.gap_confirm_bars)
                            )
                        )
                        if gap_failed:
                            trade_counter += 1
                            if position < 0:
                                exit_p = row['close'] + slippage_val
                                pnl = (current_entry - exit_p) * lots * contract_multiplier - cfg.commission_per_lot * lots
                                realized_pnl += pnl
                                total_commissions += cfg.commission_per_lot * lots
                                position = 0
                                trades.append(TacticalTrade(
                                    trade_id=f"TRD_{trade_counter:03d}",
                                    trade_type="GAP_EXHAUSTION_EXIT",
                                    time=row['datetime_str'],
                                    price=exit_p,
                                    direction="FLAT",
                                    lots=lots,
                                    pnl=pnl,
                                    fees=cfg.commission_per_lot * lots,
                                    reason=f"跳空未延续·反弹站上开盘突破线({round(day_open, 1)}) -> 趋势改变退出趋势模式"
                                ))
                            else:
                                trades.append(TacticalTrade(
                                    trade_id=f"TRD_{trade_counter:03d}",
                                    trade_type="GAP_EXHAUSTION_EXIT",
                                    time=row['datetime_str'],
                                    price=row['close'],
                                    direction="FLAT",
                                    lots=0,
                                    pnl=0.0,
                                    fees=0.0,
                                    reason=f"跳空未延续·反弹站上开盘突破线({round(day_open, 1)}) -> 趋势改变退出趋势模式，终止回补锁定利润"
                                ))
                            state = "TREND_TERMINATED"
                            equity_curve.append({
                                "bar_idx": i,
                                "datetime": row['datetime_str'],
                                "close": row['close'],
                                "position": 0,
                                "equity": initial_capital + realized_pnl
                            })
                            continue

                # 震荡假突破与停滞敏捷退出检查 (震荡市保护)
                if cfg.enable_choppy_exit and state == "IN_TREND" and position < 0:
                    bars_in_position += 1
                    min_fav_price = min(min_fav_price, row['low'])
                    
                    # 规则 A: 单日遭遇连续止损熔断 -> 判定为无序震荡洗盘，退出趋势模式
                    if retries_today >= cfg.max_retries_per_day:
                        trade_counter += 1
                        exit_p = row['close'] + slippage_val
                        pnl = (current_entry - exit_p) * lots * contract_multiplier - cfg.commission_per_lot * lots
                        realized_pnl += pnl
                        total_commissions += cfg.commission_per_lot * lots
                        position = 0
                        state = "TREND_TERMINATED"
                        trades.append(TacticalTrade(
                            trade_id=f"TRD_{trade_counter:03d}",
                            trade_type="CHOPPY_REGIME_EXIT",
                            time=row['datetime_str'],
                            price=exit_p,
                            direction="FLAT",
                            lots=lots,
                            pnl=pnl,
                            fees=cfg.commission_per_lot * lots,
                            reason="触发单日熔断上限(2次) -> 识别为无序震荡洗盘，退出趋势模式"
                        ))
                        equity_curve.append({
                            "bar_idx": i,
                            "datetime": row['datetime_str'],
                            "close": row['close'],
                            "position": 0,
                            "equity": initial_capital + realized_pnl
                        })
                        continue
                        
                    # 规则 B: 假突破停滞破位检查 (仅在尚未脱离成本确立趋势时生效)
                    # 给予充分蓄势突破空间 (24 根 5m Bar = 2 小时)，避免将趋势孕育期误判为震荡
                    limit_bars = cfg.choppy_stagnant_bars if (cfg.choppy_stagnant_bars != 8 and cfg.early_stage_bars == 24) or not cfg.enable_phase_sensitivity else cfg.early_stage_bars
                    if fav_profit < profit_target and bars_in_position >= limit_bars:
                        stagnant = (current_entry - min_fav_price < 5.0)
                        ma20_cond = (row['close'] > row['ma20']) if not pd.isna(row['ma20']) else True
                        broke_resistance = (row['close'] > entry_bar_high) and ma20_cond
                        if stagnant and broke_resistance:
                            trade_counter += 1
                            exit_p = row['close'] + slippage_val
                            pnl = (current_entry - exit_p) * lots * contract_multiplier - cfg.commission_per_lot * lots
                            realized_pnl += pnl
                            total_commissions += cfg.commission_per_lot * lots
                            position = 0
                            state = "TREND_TERMINATED"
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="CHOPPY_REGIME_EXIT",
                                time=row['datetime_str'],
                                price=exit_p,
                                direction="FLAT",
                                lots=lots,
                                pnl=pnl,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"持仓{bars_in_position}根Bar未脱离成本且破位 -> 识别为震荡假突破，退出趋势模式"
                            ))
                            equity_curve.append({
                                "bar_idx": i,
                                "datetime": row['datetime_str'],
                                "close": row['close'],
                                "position": 0,
                                "equity": initial_capital + realized_pnl
                            })
                            continue

                # 2.1 持有空头中: 15分钟级别全平门槛判断 (仅在趋势确立中后期生效，避免初期被洗盘误杀)
                if state == "IN_TREND" and position < 0 and not is_early_stage:
                    cond_bias = (row['bias_vwap'] <= -cfg.bias_threshold) and (row['close'] < row['boll_down'])
                    cond_absorb = (row['vol_ratio'] >= cfg.vol_ratio_threshold) and (row['shadow_lower'] >= cfg.shadow_threshold) and (row['close'] <= row['rolling_low_20'])
                    cond_oi = (row['delta_oi_3bar'] <= cfg.oi_climax_threshold) and (row['vol_ratio'] >= 1.8) and (row['close'] <= row['rolling_low_20'])

                    if cond_bias or cond_absorb or cond_oi:
                        if not alert:
                            alert = True
                            alert_reason = "VWAP极端负乖离" if cond_bias else ("天量吸收长下影" if cond_absorb else "空头断崖平仓潮")
                            extreme_low = row['low']
                            extreme_high = row['high']

                    if alert:
                        extreme_low = min(extreme_low, row['low'])
                        if cfg.exit_timeframe == "15m":
                            # 15分钟级别右侧确认: 突破 15m 结构高点，或连续突破 15m MA5
                            pivot_break = (row['close'] > row['rolling_high_15m']) and (row['close'] > row['open'])
                            ma15_break = (row['close'] > row['ma15_5']) and (prev['close'] >= row['ma15_5']) and (row['close'] > extreme_low + 10.0)
                            trigger_exit = pivot_break or ma15_break
                            reason_str = "破15m结构高点" if pivot_break else "突破15mMA5均线"
                        else:
                            pivot_break = (row['close'] > extreme_high) and (row['close'] > row['open'])
                            ma5_break = (row['close'] > row['ma5']) and (prev['close'] > row['ma5'] or row['close'] > prev['high'])
                            bull_engulf = (row['close'] > prev['open']) and (row['open'] <= prev['close']) and (row['close'] > prev['high'])
                            trigger_exit = pivot_break or (ma5_break and row['close'] > extreme_low + 6.0) or bull_engulf
                            reason_str = "突破探底高点" if pivot_break else ("突破MA5" if ma5_break else "阳包阴底分型")

                        if trigger_exit:
                            trade_counter += 1
                            exit_p = row['close'] + slippage_val
                            pnl = (current_entry - exit_p) * lots * contract_multiplier - cfg.commission_per_lot * lots
                            realized_pnl += pnl
                            total_commissions += cfg.commission_per_lot * lots
                            last_exit_price = exit_p
                            
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="PIVOT_EXIT",
                                time=row['datetime_str'],
                                price=exit_p,
                                direction="FLAT",
                                lots=lots,
                                pnl=pnl,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"[{alert_reason}] -> {cfg.exit_timeframe}右侧【{reason_str}】全平止盈"
                            ))
                            
                            position = 0
                            state = "OBSERVING_PULLBACK"
                            is_initial_position = False  # 已成功兑现一次波段全平，解除初始底仓状态
                            alert = False
                            extreme_high = row['high']
                            gap_trough = row['low']
                            gap_pullback_crest = row['high']
                            pullback_alert = False
                            stop_loss_price = 0.0
                            continue

                # 2.2 空仓观察反抽中: 检测【阻力预警】+【安全门禁/跳空反抽】+【右侧遇阻全额回补】
                elif state == "OBSERVING_PULLBACK":
                    extreme_high = max(extreme_high, row['high'])
                    
                    # 动态追踪跳空最低谷与跳空后的反抽高点
                    if row['low'] < gap_trough:
                        gap_trough = row['low']
                        gap_pullback_crest = row['high']
                    else:
                        gap_pullback_crest = max(gap_pullback_crest, row['high'])
                        
                    pullback_height = gap_pullback_crest - gap_trough
                    
                    near_vwap = (row['high'] >= row['intraday_vwap'] * 0.997) and (row['close'] <= row['intraday_vwap'] * 1.002)
                    pinbar_res = (row['shadow_upper'] >= 0.35) and (row['vol_ratio'] <= 1.5)
                    gap_pullback_alert = (
                        cfg.enable_gap_pullback_reentry
                        and (pullback_height >= gap_pullback_val)
                    )

                    if near_vwap or pinbar_res or gap_pullback_alert:
                        pullback_alert = True

                    if pullback_alert and retries_today < cfg.max_retries_per_day:
                        bear_rev = (row['close'] < prev['low']) and (row['close'] < row['open'])
                        ma5_lose = (row['close'] < row['ma5']) and (prev['close'] >= prev['ma5']) and (row['close'] < row['open'])

                        if bear_rev or ma5_lose:
                            reenter_p = row['close'] - slippage_val
                            
                            # 核心安全防火墙判断:
                            # 1. 常规平价保护 (贴近平仓价)
                            is_price_fair = (reenter_p >= last_exit_price - cfg.price_protection_tol)
                            # 2. 跳空后深幅反抽遇阻判断 (用户指定: 跳空后若价格反抽充分，继续执行空头回补)
                            is_gap_pullback_ready = (
                                cfg.enable_gap_pullback_reentry
                                and (pullback_height >= gap_pullback_val)
                            )
                            
                            if not (is_price_fair or is_gap_pullback_ready):
                                # 既不贴近平仓价，跳空后反抽也不充分 (地板追空)，触发一票否决!
                                pullback_alert = False
                                continue
                            
                            trade_counter += 1
                            position = -lots
                            current_entry = reenter_p
                            total_commissions += cfg.commission_per_lot * lots
                            
                            # 若为跳空反抽回补，止损设在跳空反抽最高点上方 2 ticks，否则设在 extreme_high 上方 2 ticks
                            active_stop_base = gap_pullback_crest if (not is_price_fair and is_gap_pullback_ready) else extreme_high
                            stop_loss_price = active_stop_base + tight_stop_val
                            state = "IN_TREND"
                            is_initial_position = False  # 回补仓为波段接力仓，非初始脆弱期底仓
                            pullback_alert = False
                            bars_in_position = 0
                            entry_bar_low = row['low']
                            entry_bar_high = row['high']
                            max_fav_price = row['close']
                            min_fav_price = row['close']
                            
                            reentry_tag = f"跳空反抽{round(pullback_height, 1)}点遇阻" if (not is_price_fair and is_gap_pullback_ready) else "右侧遇阻"
                            reason_str = "顶分型反转跌破前低" if bear_rev else "实体大阴跌破MA5"
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="PIVOT_RE_ENTRY",
                                time=row['datetime_str'],
                                price=reenter_p,
                                direction="SHORT",
                                lots=lots,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"反抽遇阻 -> 【{reentry_tag}·{reason_str}】安全回补",
                                stop_loss_price=stop_loss_price
                            ))
                            continue

                # 2.3 止损盯市: 初始底仓结构防守止损 vs 中途回补极窄止损
                if state == "IN_TREND" and position < 0 and stop_loss_price > 0:
                    if row['high'] >= stop_loss_price:
                        trade_counter += 1
                        stop_p = stop_loss_price + slippage_val
                        pnl = (current_entry - stop_p) * lots * contract_multiplier - cfg.commission_per_lot * lots
                        realized_pnl += pnl
                        total_commissions += cfg.commission_per_lot * lots
                        
                        if is_initial_position:
                            # 初始底仓在建仓初期直接被突破结构高点 -> 识别为恶性假突破，趋势破坏！
                            position = 0
                            state = "TREND_TERMINATED"  # 彻底退出趋势模式，空仓锁定，绝不盲目回补
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="INITIAL_BREAKOUT_FAILED",
                                time=row['datetime_str'],
                                price=stop_p,
                                direction="FLAT",
                                lots=lots,
                                pnl=pnl,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"突破初始突破防守线({round(stop_loss_price, 1)}) -> 假突破趋势破坏，退出趋势模式",
                                stop_loss_price=stop_loss_price
                            ))
                            equity_curve.append({
                                "bar_idx": i,
                                "datetime": row['datetime_str'],
                                "close": row['close'],
                                "position": 0,
                                "equity": initial_capital + realized_pnl
                            })
                            continue
                        else:
                            # 中途回补仓位的极窄硬止损
                            retries_today += 1
                            trades.append(TacticalTrade(
                                trade_id=f"TRD_{trade_counter:03d}",
                                trade_type="TIGHT_STOP_HIT",
                                time=row['datetime_str'],
                                price=stop_p,
                                direction="FLAT",
                                lots=lots,
                                pnl=pnl,
                                fees=cfg.commission_per_lot * lots,
                                reason=f"突破拐点极窄硬止损 (微损仅 {round(stop_p - current_entry, 1)} 元/吨)",
                                stop_loss_price=stop_loss_price
                            ))
                            position = 0
                            state = "OBSERVING_PULLBACK"
                            stop_loss_price = 0.0
                            continue

            # 动态盯市浮动盈亏与净值记录
            if trend_direction == "LONG":
                unreal = (row['close'] - current_entry) * lots * contract_multiplier if position > 0 else 0.0
            else:
                unreal = (current_entry - row['close']) * lots * contract_multiplier if position < 0 else 0.0
            
            eq = initial_capital + realized_pnl + unreal - total_commissions
            equity_curve.append({
                "bar_idx": i,
                "datetime": row['datetime_str'],
                "close": row['close'],
                "position": position,
                "equity": eq
            })

        # 回测周期末强平清算
        if position != 0:
            trade_counter += 1
            final_exit = df.iloc[-1]['close'] - slippage_val if position > 0 else df.iloc[-1]['close'] + slippage_val
            pnl = (final_exit - current_entry) * lots * contract_multiplier - cfg.commission_per_lot * lots if position > 0 else (current_entry - final_exit) * lots * contract_multiplier - cfg.commission_per_lot * lots
            realized_pnl += pnl
            total_commissions += cfg.commission_per_lot * lots
            trades.append(TacticalTrade(
                trade_id=f"TRD_{trade_counter:03d}",
                trade_type="FINAL_CLOSE",
                time=df.iloc[-1]['datetime_str'],
                price=final_exit,
                direction="FLAT",
                lots=lots,
                pnl=pnl,
                fees=cfg.commission_per_lot * lots,
                reason="回测周期结束强制平仓清算"
            ))

        # 统计指标核算
        eq_df = pd.DataFrame(equity_curve)
        eq_df['drawdown'] = eq_df['equity'] - eq_df['equity'].cummax()
        eq_df['dd_pct'] = eq_df['drawdown'] / eq_df['equity'].cummax() * 100.0
        strat_mdd = abs(eq_df['dd_pct'].min())
        strat_pnl = realized_pnl - total_commissions

        # 基准组 MDD
        base_eq = []
        for i in range(start_idx, len(df)):
            c_p = df.iloc[i]['close']
            unreal = (c_p - base_entry) * lots * contract_multiplier if trend_direction == "LONG" else (base_entry - c_p) * lots * contract_multiplier
            base_eq.append(initial_capital + unreal)
        b_series = pd.Series(base_eq)
        b_dd = (b_series - b_series.cummax()) / b_series.cummax() * 100.0
        base_mdd = abs(b_dd.min())

        return {
            "strategy_pnl": strat_pnl,
            "strategy_mdd": strat_mdd,
            "base_pnl": base_pnl,
            "base_mdd": base_mdd,
            "trades": trades,
            "commissions": total_commissions,
            "equity_df": eq_df
        }
