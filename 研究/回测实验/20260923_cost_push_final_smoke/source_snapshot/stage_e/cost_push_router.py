"""成本传导候选路由。独立价格确认不代表需求/政策因果已证实。"""
from dataclasses import dataclass, replace
import json
import math
import pandas as pd
from framework_rules import MA_STOP_BUFFER
from stage_e.signal_generator import SignalGenerator

VERSION = 'cost-push-0.1-candidate'
DRIVER = 'COST_EXPECTATION'


@dataclass(frozen=True)
class CostPushConfig:
    # 冻结的研究设定，未按历史收益寻优。
    raw_spread_min: float = .015
    pilot_risk_fraction: float = .0025
    confirmed_risk_fraction: float = .005
    pilot_leverage_cap: float = .5
    confirmed_leverage_cap: float = 1.0
    max_entry_atr_distance: float = 3.0
    confirmation_bars: int = 5
    pullback_bars: int = 5
    cooldown_bars: int = 3
    max_spot_drop_5d: float = .01
    min_flow_ratio: float = .70
    low_profit_ceiling: float = 100.0


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
    f['cp_high20'] = high.shift(1).rolling(20).max()
    f['cp_prev_high20'] = f.cp_high20.shift(1)
    f['cp_prev_close'] = c.shift(1)
    f['cp_ret5'] = c.pct_change(5, fill_method=None)
    spot = f.get('spot_hz_zhongtian', pd.Series(float('nan'), index=f.index))
    flow = f.get('flow_hz_outflow', pd.Series(float('nan'), index=f.index))
    f['cp_spot'] = spot
    f['cp_spot_ret5'] = spot.pct_change(5, fill_method=None)
    f['cp_flow5'] = flow.rolling(5).mean()
    f['cp_flow_ratio'] = f.cp_flow5 / f.cp_flow5.shift(5).replace(0, float('nan'))
    f['cp_basis_delta5'] = (spot-c).diff(5)
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
        self.pending = None
        self.cooldown = 0
        self.bar = 0
        self.last_diagnostics = {}

    def on_execution(self, previous_lots, current_lots, executed_signal=None):
        if self.position is not None and current_lots <= 0:
            self.position = None
            self.setup = None
            self.cooldown = self.config.cooldown_bars
        if previous_lots <= 0 < current_lots and executed_signal is not None:
            if executed_signal.entry_driver == DRIVER and self.pending is not None:
                self.position = dict(self.pending, age=0, confirmed=False, exit_reason='')
                self.setup = None
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
        breakout = c > high and number(f,'cp_prev_close') <= number(f,'cp_prev_high20')
        if known and raw and breakout and self.position is None and not cooling:
            self.setup = dict(level=high, bar=self.bar, used=False)
        pullback = bool(self.setup and not self.setup['used'] and
                        0 < self.bar-self.setup['bar'] <= cfg.pullback_bars and
                        number(f,'rb_low') <= self.setup['level'] + .5*atr and
                        c >= self.setup['level'] and c > number(f,'cp_prev_close'))
        if self.setup and (self.bar-self.setup['bar'] > cfg.pullback_bars or c < self.setup['level']-atr):
            self.setup = None
            pullback = False
        distance = (c-ma)/atr if math.isfinite(atr) and atr>0 else float('nan')
        gates = dict(data_known=known, raw_push=bool(raw), price_rising=bool(ret>0 and c>ma),
                     spot_flow_not_deteriorating=bool(known and not deterioration),
                     fresh_breakout=bool(breakout), first_pullback=pullback,
                     distance_ok=bool(0 < distance <= cfg.max_entry_atr_distance),
                     cooldown=cooling, baseline_direction=base.direction,
                     baseline_reason=base.rationale, fundamental_confidence=float(base.confidence_score) if pd.notna(base.confidence_score) else None,
                     entry_ma_distance_pct=(c/ma-1) if ma>0 else None,
                     entry_atr_distance=distance if math.isfinite(distance) else None,
                     basis_delta5=number(f,'cp_basis_delta5') if math.isfinite(number(f,'cp_basis_delta5')) else None)
        self.last_diagnostics = gates
        diagnostic_json = json.dumps(gates, ensure_ascii=False, allow_nan=False)
        if self.position is not None and current_holding_direction == 'LONG':
            p = self.position
            p['age'] += 1
            # 止损用连续价格观察，不把换月价差直接当实约损失距离。
            stop = max(p['stop'], ma*(1-MA_STOP_BUFFER)) if math.isfinite(ma) else p['stop']
            p['stop'] = stop  # 保护边界仅上移，不能随均线下移放宽。
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
        if known and raw and ret>0 and c>ma and not deterioration and gates['distance_ok'] and not cooling and (breakout or pullback):
            trigger = 'BREAKOUT' if breakout else 'FIRST_PULLBACK'
            level = high if breakout else self.setup['level']
            stop = max(level-atr, ma*(1-MA_STOP_BUFFER))
            self.pending = dict(stop=stop,spot=spot,flow=flow,signal_close=c,trigger=trigger,signal_date=date_str)
            if pullback:
                self.setup['used'] = True
            return self._signal(base, f, 'PILOT', trigger, stop, diagnostic_json)
        return replace(base, participation_stage='OBSERVE' if raw else 'NONE', gate_diagnostics=diagnostic_json)

    def _signal(self, base, f, stage, trigger, stop, gates, reason='', allow_increase=True):
        cfg = self.config
        profit = number(f, 'profit_bf')
        # 利润未知不是低利润，但同样不足以批准较高风险预算。
        increase_budget = stage == 'TRANSMISSION_CONFIRMED' and math.isfinite(profit) and profit > cfg.low_profit_ceiling
        budget = cfg.confirmed_risk_fraction if increase_budget else cfg.pilot_risk_fraction
        cap = cfg.confirmed_leverage_cap if increase_budget else cfg.pilot_leverage_cap
        c, atr = number(f,'rb_close'), number(f,'cp_atr20')
        distance = max(2*atr, c-stop, c*.015)/c if c>0 and atr>0 else None
        return replace(base, direction='FLAT' if reason else 'LONG', strength=.5,
                       spot_confirmed=stage == 'TRANSMISSION_CONFIRMED', momentum_confirmed=not bool(reason),
                       strategy_name=VERSION, entry_driver=DRIVER, participation_stage=stage,
                       entry_trigger=trigger, invalidation_reason=reason,
                       risk_budget_fraction=budget, strategy_leverage_cap=cap, risk_distance_pct=distance,
                       allow_position_increase=allow_increase, entry_stop_level=stop,
                       entry_thesis='原料相对推涨后成材价格突破，等待现货上涨且出库不弱；不推断需求或政策因果',
                       last_new_evidence_date=(self.position or {}).get('last_evidence_date',''),
                       gate_diagnostics=gates, carry_multiplier=1.0, is_pilot_squeeze=False,
                       rationale=f'{VERSION}: {stage}; {trigger}; {reason or "原料推涨与价格确认；物理因果未证实"}')
