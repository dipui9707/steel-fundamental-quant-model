"""冻结的简单对照与机制候选；均用相同账户、成交、风控和仓位条件比较。"""
import pandas as pd
from stage_e.signal_generator import TradingSignal, SignalGenerator


class ComparisonSignals:
    def __init__(self, mode):
        self.mode = mode
        self.core = SignalGenerator()

    def generate_signal(self, date_str, state_row, feature_row, strategy_mode='QUANT_CORE', current_holding_direction='FLAT'):
        if self.mode in ('FULL', 'FULL_WITH_DUPLICATE_PROXY'):
            gen = self.core if self.mode == 'FULL' else SignalGenerator(enable_carry_gate=True, enable_carry_sizer=True)
            return gen.generate_signal(date_str, state_row, feature_row, current_holding_direction=current_holding_direction)
        close, ma = feature_row.get('rb_close'), feature_row.get('ma_20')
        trend = 'FLAT' if pd.isna(close) or pd.isna(ma) or close == ma else ('LONG' if close > ma else 'SHORT')
        supply = feature_row.get('score_supply', float('nan'))
        supply_dir = 'FLAT' if pd.isna(supply) or supply == 0 else ('LONG' if supply > 0 else 'SHORT')
        fund = {'Bullish':'LONG', 'Bearish':'SHORT'}.get(state_row.get('fundamental_direction'), 'FLAT')
        if self.mode == 'PRICE':
            direction = trend
        elif self.mode == 'SUPPLY':
            direction = supply_dir
        elif self.mode == 'PRICE_FUNDAMENTAL':
            direction = trend if trend == fund else 'FLAT'
        elif self.mode == 'MECHANISM_CANDIDATE':
            # 只研究两条利多资源平衡链；成本减产不直接指定钢价方向。
            confirmed = any(state_row.get(f'mechanism_{f}') == 'CONFIRMED' for f in ('demand','supply'))
            direction = 'LONG' if confirmed and trend == 'LONG' else 'FLAT'
        else:
            raise ValueError(self.mode)
        return TradingSignal(date_str, 'RB', direction, 1.0, 100.0, False,
                             trend != 'FLAT', self.mode, '冻结对照规则；100是固定仓位占位值，不是概率')
