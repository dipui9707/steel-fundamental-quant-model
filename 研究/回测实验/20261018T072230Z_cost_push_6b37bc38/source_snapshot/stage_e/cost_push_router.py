"""成本传导候选路由 (cost-push-0.3-candidate)。
双轨入场（启动期突破轻仓底仓 + MA20回踩企稳主攻仓）、趋势生命线止损与主升浪二次追击状态机。
独立价格确认不代表需求/政策因果已证实。
"""
from dataclasses import dataclass, replace
import json
import math
import pandas as pd
from framework_rules import MA_STOP_BUFFER
from stage_e.signal_generator import SignalGenerator

VERSION = 'framework-0.12-candidate'
DRIVER = 'COST_EXPECTATION'


@dataclass(frozen=True)
class CostPushConfig:
    # 冻结的研究设定，未按历史收益寻优。
    raw_spread_min: float = .015
    full_margin_utilization: float = .50
    pilot_fraction_of_full: float = .20       # 10% 保证金资金使用率 (启动期试探底仓)
    pullback_fraction_of_full: float = .40    # 20% 保证金资金使用率 (回踩企稳/二次追击主攻仓)
    confirmed_fraction_of_full: float = .50   # 25% 保证金资金使用率 (传导全面确认仓)
    max_breakout_pct_distance: float = 0.035  # 突破距MA20超过3.5%判定为高位透支禁追，等待回踩
    max_breakout_atr_distance: float = 2.2    # 突破距MA20超过2.2 ATR判定为高位透支禁追
    max_entry_atr_distance: float = 3.0       # 绝对入场距离上限
    confirmation_bars: int = 5
    pullback_bars: int = 10                   # 允许最多10根日线寻找MA20回踩买点
    reentry_window_bars: int = 15             # 平仓后允许15根日线观察二次起爆追击
    cooldown_bars: int = 3                    # 平仓后冷却
    max_spot_drop_5d: float = .01
    min_flow_ratio: float = .70
    low_profit_ceiling: float = 100.0

    def __post_init__(self):
        if not 0 < self.full_margin_utilization <= .50:
            raise ValueError('满仓资金使用率须在(0, 50%]以内')
        if not 0 < self.pilot_fraction_of_full <= self.confirmed_fraction_of_full <= 1:
            raise ValueError('仓位比例须满足 0 < 试单 <= 确认 <= 满仓')


def number(row, key):
    try:
        value = float(row.get(key, float('nan')))
        return value if math.isfinite(value) else float('nan')
    except (TypeError, ValueError):
        return float('nan')


def prepare_cost_push_features(frame):
    """只读取本日及过去数据；必须在截取实验日期前计算预热。不填补缺数。"""
    f = frame.copy()
    c = f.rb_close
    high, low = f.get('rb_high', c), f.get('rb_low', c)
    tr = pd.concat([high-low, (high-c.shift()).abs(), (low-c.shift()).abs()], axis=1).max(axis=1)
    f['cp_atr20'] = tr.rolling(20, min_periods=20).mean()
    f['cp_ma20'] = c.rolling(20).mean()
    f['cp_ma5'] = c.rolling(5, min_periods=2).mean()
    f['ma_5'] = f['cp_ma5']
    f['cp_high20'] = high.shift(1).rolling(20).max()
    f['cp_prev_high20'] = f.cp_high20.shift(1)
    f['cp_high5'] = high.shift(1).rolling(5).max()
    f['cp_prev_close'] = c.shift(1)
    f['cp_ret5'] = c.pct_change(5, fill_method=None)
    f['rolling_low_20'] = low.shift(1).rolling(20, min_periods=10).min()
    f['rolling_high_20'] = high.shift(1).rolling(20, min_periods=10).max()
    f['rolling_low_60'] = low.shift(1).rolling(60, min_periods=20).min()
    f['rolling_high_60'] = high.shift(1).rolling(60, min_periods=20).max()
    spot = f.get('spot_hz_zhongtian', f.get('spot_hz_tier3', pd.Series(float('nan'), index=f.index)))
    basis = spot - c
    flow = f.get('flow_hz_outflow', pd.Series(float('nan'), index=f.index))
    f['cp_spot'] = spot
    f['cp_spot_ret5'] = spot.pct_change(5, fill_method=None)
    f['cp_spot_delta3'] = spot.diff(3)
    f['cp_flow5'] = flow.rolling(5).mean()
    f['cp_flow_ratio'] = f.cp_flow5 / f.cp_flow5.shift(5).replace(0, float('nan'))
    f['cp_basis_delta5'] = basis.diff(5)
    f['cp_basis_delta3'] = basis.diff(3)
    f['cp_basis_max5'] = basis.shift(1).rolling(5, min_periods=2).max()
    f['rolling_high_120'] = high.shift(1).rolling(120, min_periods=20).max()
    spread = f.get('cost_push_spread_5d', pd.Series(0.0, index=f.index))
    f['rolling_max_spread_30'] = spread.shift(1).rolling(30, min_periods=5).max()

    # 4大支柱高利润牛市前置特征
    commodities = ["rb", "hc", "i", "j", "jm"]
    rising_count = pd.Series(0, index=f.index)
    rising_dict = {}
    for com in commodities:
        col_close = f"{com}_close" if f"{com}_close" in f.columns else None
        if col_close:
            cc = f[col_close]
            ma20_c = cc.rolling(20, min_periods=5).mean()
            ma5_c = cc.rolling(5, min_periods=2).mean()
            c_rising = (cc >= ma20_c * 0.99) | (ma5_c >= ma20_c) | (cc > cc.shift(5))
            rising_count += c_rising.astype(int)
            rising_dict[com] = c_rising
        else:
            rising_dict[com] = pd.Series(False, index=f.index)
    rising_rb = rising_dict.get("rb", pd.Series(False, index=f.index))
    rising_hc = rising_dict.get("hc", pd.Series(False, index=f.index))
    f["is_ferrous_complex_uptrend"] = (rising_count >= 3) | (rising_rb & rising_hc)

    if "hot_metal_247" in f.columns:
        hm = f["hot_metal_247"]
        hm_rising = (hm >= hm.shift(10) * 0.99) | (hm >= hm.shift(5))
        hm_stable_high = (hm >= 220.0) & (hm >= hm.shift(20) * 0.92)
        hm_ok = hm_rising | hm_stable_high
    else:
        hm_ok = pd.Series(True, index=f.index)

    if "rebar_weekly_prod" in f.columns:
        sp = f["rebar_weekly_prod"]
        sp_rising = (sp >= sp.shift(10) * 0.99) | (sp >= sp.shift(5))
        sp_stable_high = (sp >= 240.0) & (sp >= sp.shift(20) * 0.90)
        sp_ok = sp_rising | sp_stable_high
    else:
        sp_ok = pd.Series(True, index=f.index)

    f["is_supply_high_or_rising"] = hm_ok & sp_ok

    if "rebar_apparent_demand" in f.columns:
        dem = f["rebar_apparent_demand"]
        dem_max_20 = dem.shift(1).rolling(20, min_periods=5).max()
        outflow_pct = f.get("pct_flow_hz_outflow", pd.Series(0.5, index=f.index))
        dem_healthy_level = (dem >= 230.0) | (outflow_pct >= 0.30)
        dem_not_collapsing = (dem >= dem_max_20 * 0.78) | (dem >= 270.0)
        f["is_demand_high_or_stable"] = dem_healthy_level & dem_not_collapsing
    else:
        f["is_demand_high_or_stable"] = pd.Series(True, index=f.index)

    if "contract_dte" not in f.columns and "dte" not in f.columns:
        from stage_e.contract_rollover import ContractRolloverManager
        mgr = ContractRolloverManager(symbol="rb")
        full_map = mgr.get_full_map()
        dtes = {}
        for d, c in zip(full_map.index, full_map["contract_code_short"]):
            try:
                yr = 2000 + int(str(c)[:2])
                mo = int(str(c)[2:])
                exp_dt = pd.Timestamp(year=yr, month=mo, day=15)
                cur_dt = pd.Timestamp(d)
                dtes[d] = (exp_dt - cur_dt).days
            except Exception:
                dtes[d] = 999
        f["contract_dte"] = pd.Series(dtes).reindex(f.index).fillna(999)

    return f


class CostPushRouter:
    """单一 RB 头寸。必须收到实际成交回报后才建立成本仓上下文。"""
    def __init__(self, core=None, config=None):
        self.core = core or SignalGenerator()
        self.config = config or CostPushConfig()
        self.reset()

    def reset(self):
        self.position = None
        self.setup = None
        self.reentry_watch = None
        self.pending = None
        self.cooldown = 0
        self.bar = 0
        self.last_diagnostics = {}

    def on_execution(self, previous_lots, current_lots, executed_signal=None):
        if self.position is not None and current_lots <= 0:
            # 平仓后保留观察上下文，等待主升浪二次追击机会
            self.reentry_watch = dict(bar=self.bar, exit_bar=self.bar)
            self.position = None
            self.setup = None
            self.cooldown = self.config.cooldown_bars
        if previous_lots <= 0 < current_lots and executed_signal is not None:
            if executed_signal.entry_driver == DRIVER and self.pending is not None:
                self.position = dict(self.pending, age=0, confirmed=False, exit_reason='')
                self.setup = None
                self.reentry_watch = None
        # 被风控否决/手数归零的信号不能创建幽灵持仓。
        self.pending = None

    def generate_signal(self, date_str, state_row, feature_row, strategy_mode='QUANT_CORE', current_holding_direction='FLAT'):
        base = self.core.generate_signal(date_str, state_row, feature_row, strategy_mode,
                                         current_holding_direction=current_holding_direction)
        f, s, cfg = feature_row, state_row, self.config
        self.bar += 1
        cooling = self.cooldown > 0
        self.cooldown = max(0, self.cooldown-1)
        c, ma, atr, high = [number(f, k) for k in ('rb_close','cp_ma20','cp_atr20','cp_high20')]
        spot, flow = number(f, 'cp_spot'), number(f, 'cp_flow5')
        spread, ret = number(f, 'cost_push_spread_5d'), number(f, 'cp_ret5')
        required = [c, ma, atr, high, spot, flow, spread, ret,
                    number(f,'cp_spot_ret5'),number(f,'cp_flow_ratio'),
                    number(f,'cp_prev_close'), number(f,'cp_prev_high20')]
        known = all(math.isfinite(v) for v in required) and min(c,ma,atr,high,spot)>0 and flow>=0
        squeeze = max([0.] + [v for k in ('squeeze_index','i_squeeze_index','j_squeeze_index','jm_squeeze_index')
                             if math.isfinite(v := number(f,k))])
        raw_flag = f.get('is_raw_material_squeeze', False)
        raw_flag = False if pd.isna(raw_flag) else bool(raw_flag)
        raw = spread > cfg.raw_spread_min and (s.get('dominant_leader_type', f.get('dominant_leader_type')) == 'RAW_MATERIAL_SHOCK' or raw_flag or squeeze >= 2)
        deterioration = (number(f,'cp_spot_ret5') < -cfg.max_spot_drop_5d or
                         number(f,'cp_flow_ratio') < cfg.min_flow_ratio)
        pct_b_1y = number(f, 'pct_basis_tier3_1y')
        if not math.isfinite(pct_b_1y):
            pct_b_1y = number(f, 'pct_basis_tier3')
        spot_basis_accepted = (not math.isfinite(pct_b_1y)) or (pct_b_1y >= 0.25)

        distance_atr = (c - ma) / atr if math.isfinite(atr) and atr > 0 else float('nan')
        distance_pct = (c / ma - 1.0) if ma > 0 else float('nan')

        # 1. 突破判定与 Setup 建立
        breakout = c > high and number(f, 'cp_prev_close') <= number(f, 'cp_prev_high20')
        if known and raw and breakout and self.position is None and not cooling:
            self.setup = dict(level=high, bar=self.bar, used=False)

        # 启动期突破 vs 高位透支拦截
        is_overbought = (distance_pct > cfg.max_breakout_pct_distance) or (distance_atr > cfg.max_breakout_atr_distance)
        can_early_breakout = breakout and (not is_overbought) and (0 < distance_atr <= cfg.max_entry_atr_distance)

        # 2. 回踩 MA20 均线支撑带企稳买点 (Pullback to MA20 Confirmation)
        # 允许回落触及突破位上方0.5ATR或触及MA20均线带，且守住MA20趋势生命线，今日收阳企稳
        pullback = bool(self.setup and not self.setup['used'] and
                        0 < self.bar - self.setup['bar'] <= cfg.pullback_bars and
                        number(f, 'rb_low') <= max(self.setup['level'] + .5 * atr, ma + 1.2 * atr) and
                        c >= min(self.setup['level'], ma * (1 - MA_STOP_BUFFER)) and
                        c > number(f, 'cp_prev_close'))

        if self.setup and (self.bar - self.setup['bar'] > cfg.pullback_bars or c < ma * (1 - 2 * MA_STOP_BUFFER)):
            self.setup = None
            pullback = False

        # 3. 主升浪二次追击状态机 (Second-Leg Re-Entry)
        high5 = number(f, 'cp_high5')
        reentry = bool(self.reentry_watch and
                       0 < self.bar - self.reentry_watch['bar'] <= cfg.reentry_window_bars and
                       raw and spread > 0.005 and
                       c >= ma and c > number(f, 'cp_prev_close') and
                       math.isfinite(high5) and c > high5)

        if self.reentry_watch and (self.bar - self.reentry_watch['bar'] > cfg.reentry_window_bars or c < ma * (1 - 2 * MA_STOP_BUFFER)):
            self.reentry_watch = None
            reentry = False

        gates = dict(data_known=known, raw_push=bool(raw), price_rising=bool(ret>0 and c>ma),
                     spot_flow_not_deteriorating=bool(known and not deterioration),
                     spot_basis_accepted=bool(spot_basis_accepted),
                     fresh_breakout=bool(breakout), first_pullback=pullback,
                     can_early_breakout=bool(can_early_breakout), is_overbought=bool(is_overbought),
                     second_leg_reentry=bool(reentry),
                     distance_ok=bool(0 < distance_atr <= cfg.max_entry_atr_distance),
                     cooldown=cooling, baseline_direction=base.direction,
                     baseline_reason=base.rationale, fundamental_confidence=float(base.confidence_score) if pd.notna(base.confidence_score) else None,
                     entry_ma_distance_pct=distance_pct if math.isfinite(distance_pct) else None,
                     entry_atr_distance=distance_atr if math.isfinite(distance_atr) else None,
                     basis_delta5=number(f,'cp_basis_delta5') if math.isfinite(number(f,'cp_basis_delta5')) else None)
        self.last_diagnostics = gates
        diagnostic_json = json.dumps(gates, ensure_ascii=False, allow_nan=False)

        # 在持头寸管理
        if self.position is not None and current_holding_direction == 'LONG':
            p = self.position
            p['age'] += 1
            stop = max(p['stop'], ma*(1-MA_STOP_BUFFER)) if math.isfinite(ma) else p['stop']
            p['stop'] = stop
            reason = p['exit_reason']
            if not known:
                reason = reason or 'REQUIRED_DATA_UNKNOWN'
            elif c < stop:
                reason = reason or 'BREAKOUT_OR_MA_FAILURE'
            elif deterioration:
                reason = reason or 'SPOT_FLOW_DETERIORATION'
            elif spread <= 0 and ret <= 0:
                reason = reason or 'RAW_PUSH_AND_PRICE_FAILED'
            confirmed_now = (known and not reason and spot > p['spot'] and flow >= p['flow'] and c >= p['signal_close'])
            was_confirmed = p['confirmed']
            if confirmed_now:
                p['confirmed'] = True
                if spot > p.get('max_confirmed_spot', p['spot']):
                    p['last_evidence_date'] = date_str
                    p['max_confirmed_spot'] = spot
            if not p['confirmed'] and p['age'] >= cfg.confirmation_bars:
                reason = reason or 'CONFIRMATION_TIMEOUT'
            p['exit_reason'] = reason
            stage = 'EXIT' if reason else ('TRANSMISSION_CONFIRMED' if p['confirmed'] else 'PILOT')
            return self._signal(base, f, stage, p['trigger'], stop, diagnostic_json, reason,
                                allow_increase=p['confirmed'] and not was_confirmed)

        # 原有仓位始终由原策略管理；新通道只填补原策略空仓。
        if current_holding_direction != 'FLAT' or base.direction != 'FLAT':
            return replace(base, gate_diagnostics=diagnostic_json)

        # 入场许可判定
        entry_allowed = known and raw and ret > 0 and c > ma and not deterioration and spot_basis_accepted and gates['distance_ok'] and not cooling

        if entry_allowed and (can_early_breakout or pullback or reentry):
            if can_early_breakout:
                trigger = 'BREAKOUT'
                level = high
                fraction = cfg.pilot_fraction_of_full
            elif pullback:
                trigger = 'FIRST_PULLBACK'
                level = self.setup['level']
                fraction = cfg.pullback_fraction_of_full
                self.setup['used'] = True
            elif reentry:
                trigger = 'SECOND_LEG_RE_ENTRY'
                level = high5
                fraction = cfg.pullback_fraction_of_full
                self.reentry_watch = None
            else:
                trigger = 'PILOT'
                level = high
                fraction = cfg.pilot_fraction_of_full

            stop = max(level - atr, ma * (1 - MA_STOP_BUFFER))
            self.pending = dict(stop=stop, spot=spot, flow=flow, signal_close=c, trigger=trigger, signal_date=date_str, fraction=fraction)
            return self._signal(base, f, 'PILOT', trigger, stop, diagnostic_json, target_fraction=fraction)

        return replace(base, participation_stage='OBSERVE' if raw else 'NONE', gate_diagnostics=diagnostic_json)

    def _signal(self, base, f, stage, trigger, stop, gates, reason='', allow_increase=True, target_fraction=None):
        cfg = self.config
        profit = number(f, 'profit_bf')
        increase_budget = stage == 'TRANSMISSION_CONFIRMED' and math.isfinite(profit) and profit > cfg.low_profit_ceiling
        if increase_budget:
            fraction = cfg.confirmed_fraction_of_full
        elif target_fraction is not None:
            fraction = target_fraction
        elif self.position is not None and 'fraction' in self.position:
            fraction = self.position['fraction']
        else:
            fraction = cfg.pilot_fraction_of_full

        margin_target = cfg.full_margin_utilization * fraction
        c, atr = number(f,'rb_close'), number(f,'cp_atr20')
        distance = max(2*atr, c-stop, c*.015)/c if c>0 and atr>0 else None
        return replace(base, direction='FLAT' if reason else 'LONG', strength=.5,
                       spot_confirmed=stage == 'TRANSMISSION_CONFIRMED', momentum_confirmed=not bool(reason),
                       strategy_name=VERSION, entry_driver=DRIVER, participation_stage=stage,
                       entry_trigger=trigger, invalidation_reason=reason,
                       risk_budget_fraction=None, strategy_leverage_cap=None, risk_distance_pct=distance,
                       strategy_margin_utilization=margin_target,
                       allow_position_increase=allow_increase, entry_stop_level=stop,
                       entry_thesis='原料相对推涨后成材突破/回踩企稳，等待现货上涨且出库不弱；不推断需求或政策因果',
                       last_new_evidence_date=(self.position or {}).get('last_evidence_date',''),
                       gate_diagnostics=gates, carry_multiplier=1.0, is_pilot_squeeze=False,
                       rationale=f'{VERSION}: {stage}; {trigger}; {reason or "原料推涨与价格确认；物理因果未证实"}')
