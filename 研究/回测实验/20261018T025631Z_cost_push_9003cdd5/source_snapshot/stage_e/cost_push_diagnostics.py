"""按实际持仓段归因；换月/减仓流水不重复计作追高交易。"""
import json
import pandas as pd

COLUMNS = ['signal_date','entry_date','end_date','closed','trigger','entry_ma_distance_pct',
           'entry_atr_distance','above_old_2_5pct_gate','initial_risk_fraction','planned_margin_utilization',
           'entry_actual_margin_utilization','estimated_distance_loss_fraction','entry_lots',
           'holding_bars','net_account_pnl','account_return_pct','worst_marked_return_pct',
           'best_marked_return_pct','baseline_same_period_return_pct','exit_reason']


def cost_position_episodes(result, baseline, initial_capital):
    eq = result.equity_df.reset_index(drop=True)
    control = baseline.equity_df.set_index('date').total_equity
    decisions = result.vetted_signals_df.set_index('date')
    rows, start = [], None
    for i in range(len(eq)+1):
        active = i < len(eq) and bool(eq.iloc[i].cost_position_active)
        if active and start is None:
            start = i
        if start is None or (active and i<len(eq)):
            continue
        closed = i < len(eq)
        end = i if closed else len(eq)-1
        first, last = eq.iloc[start], eq.iloc[end]
        signal = decisions.loc[first.execution_signal_date]
        gates = json.loads(signal.gate_diagnostics)
        before = float(eq.iloc[start-1].total_equity) if start else initial_capital
        control_before = float(control.loc[eq.iloc[start-1].date]) if start else initial_capital
        marks = eq.iloc[start:end+1].total_equity
        # 包含入场/减仓/换月/退出费用及结算浮动；不是盘中价格 MAE。
        end_signal = decisions.loc[last.execution_signal_date] if closed else None
        reason = (str(end_signal.invalidation_reason or end_signal.veto_reason) if closed else 'OPEN_AT_END')
        rows.append(dict(signal_date=first.execution_signal_date,entry_date=first.date,end_date=last.date,
            closed=closed,trigger=signal.entry_trigger,entry_ma_distance_pct=gates['entry_ma_distance_pct'],
            entry_atr_distance=gates['entry_atr_distance'],above_old_2_5pct_gate=gates['entry_ma_distance_pct']>.025,
            initial_risk_fraction=signal.route_risk_budget_fraction,
            planned_margin_utilization=signal.get('route_margin_utilization'),
            entry_actual_margin_utilization=float(first.margin_occupied)/float(first.total_equity),
            estimated_distance_loss_fraction=signal.get('estimated_distance_loss_fraction'),
            entry_lots=int(first.lots),
            holding_bars=end-start if closed else end-start+1,net_account_pnl=float(last.total_equity)-before,
            account_return_pct=(float(last.total_equity)/before-1)*100,
            worst_marked_return_pct=min(0.,(float(marks.min())/before-1)*100),
            best_marked_return_pct=max(0.,(float(marks.max())/before-1)*100),
            baseline_same_period_return_pct=(float(control.loc[last.date])/control_before-1)*100,
            exit_reason=reason))
        start=None
    return pd.DataFrame(rows,columns=COLUMNS)
