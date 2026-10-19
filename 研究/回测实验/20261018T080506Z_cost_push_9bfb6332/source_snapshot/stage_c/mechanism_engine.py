"""轻量候选机制账本：周度观察、冻结预测、独立后验评价；不把价格领先称为原因。

宽表缺少逐条发布版本，周窗口只是观察节奏，不能充当 available_date。
CONFIRMED 表示预设物理结果兑现，不表示因果识别成功或预测价格必涨。
"""
import hashlib
import json
import numpy as np
import pandas as pd
from framework_rules import FRAMEWORK_VERSION, MECHANISM_MAX_WINDOWS


class MechanismEngine:
    families = {
        'DEMAND': ('building_deal_volume', 'rebar_total_inv', -1, '成交改善后库存下降'),
        'SUPPLY': ('rebar_weekly_prod', 'rebar_total_inv', -1, '减产后库存下降'),
        'COST': ('profit_bf', 'hot_metal_247', -1, '亏损后铁水下降'),
    }

    def evaluate(self, features):
        """返回每日状态与追加式事件日志；逐日计算只访问当前及以前行。"""
        df = features.sort_index().copy()
        if 'rebar_total_inv' not in df and {'rebar_soc_inv','rebar_mill_inv'} <= set(df):
            df['rebar_total_inv'] = df.rebar_soc_inv + df.rebar_mill_inv
        last_week, prior_observation, last_row = None, None, None
        pending, statuses, events, rows = {}, {}, [], []
        active_ids = {}
        inventory_change = inventory_acceleration = np.nan
        inventory_trajectory = "Unknown"
        for dt, row in df.iterrows():
            week = str(pd.Timestamp(dt).to_period('W-FRI'))
            # 新周开始，上一完整观察周的事实才进入验证；不利用本周后续数据。
            if last_week is not None and week != last_week:
                obs = last_row
                old_inv = prior_observation.get('rebar_total_inv', np.nan) if prior_observation is not None else np.nan
                inv = obs.get('rebar_total_inv', np.nan)
                delta = inv - old_inv
                inventory_acceleration = delta - inventory_change
                inventory_change = delta
                inventory_trajectory = ('Unknown' if pd.isna(delta) else
                    'Accelerating Destock' if delta < 0 and inventory_acceleration < 0 else
                    'Normal Destock' if delta < 0 else
                    'Accelerating Accumulate' if delta > 0 and inventory_acceleration > 0 else
                    'Accumulating' if delta > 0 else 'Unchanged Observation')
                for family, (trigger_col, outcome_col, sign, prediction) in self.families.items():
                    ticket = pending.get(family)
                    outcome = obs.get(outcome_col, np.nan)
                    if ticket:
                        ticket['windows'] += 1
                        status = 'PENDING'
                        if pd.notna(outcome) and outcome != ticket['baseline']:
                            status = 'CONFIRMED' if sign * (outcome-ticket['baseline']) > 0 else 'FAILED'
                        elif ticket['windows'] >= MECHANISM_MAX_WINDOWS:
                            status = 'EXPIRED'
                        if status != 'PENDING':
                            events.append(dict(event_type='REVIEW', hypothesis_id=ticket['id'],
                                observed_at=str(dt), family=family, status=status,
                                outcome_value=float(outcome) if pd.notna(outcome) else None,
                                baseline=ticket['baseline'], windows=ticket['windows'],
                                error_attribution='OUTCOME_MISMATCH_CAUSE_UNRESOLVED' if status=='FAILED' else 'INSUFFICIENT_NEW_EVIDENCE' if status=='EXPIRED' else 'EXPECTED_FACT_OBSERVED',
                                next_action='复核需求/供给变化与口径，禁止据单例调参' if status=='FAILED' else '保留记录，等待独立新观察'))
                            statuses[family] = status
                            del pending[family]
                        continue  # 同一窗口不重开刚结束的假设
                    value = obs.get(trigger_col, np.nan)
                    previous = prior_observation.get(trigger_col, np.nan) if prior_observation is not None else np.nan
                    active_ids[family] = ''
                    statuses[family] = 'UNKNOWN' if pd.isna(value) or pd.isna(outcome) or pd.isna(previous) else 'INACTIVE'
                    if statuses[family] == 'UNKNOWN':
                        continue
                    triggered = (value > previous if family == 'DEMAND' else
                                 value < previous if family == 'SUPPLY' else value < 0)
                    if triggered:
                        payload = dict(rule_version=FRAMEWORK_VERSION, family=family,
                            issued_at=str(dt), trigger_column=trigger_col, trigger_value=float(value),
                            previous_value=float(previous), outcome_column=outcome_col,
                            expected_change='DECREASE', baseline=float(outcome),
                            max_observation_windows=MECHANISM_MAX_WINDOWS,
                            invalidation='下一观察窗口结果反向即失效；无变化最多等待两窗口',
                            prediction=prediction, evidence_group='PHYSICAL_BALANCE' if family=='SUPPLY' else family,
                            availability_status='UNVERIFIED_CURRENT_VINTAGE',
                            price_direction='UNSPECIFIED')
                        hid = hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()[:20]
                        events.append(dict(event_type='PREDICTION', hypothesis_id=hid, **payload))
                        active_ids[family] = hid
                        pending[family] = dict(id=hid, baseline=float(outcome), windows=0)
                        statuses[family] = 'PENDING'
                prior_observation = obs.copy()
            rec = {}
            for family in self.families:
                rec[f'mechanism_{family.lower()}'] = statuses.get(family, 'UNKNOWN')
                rec[f'hypothesis_{family.lower()}_id'] = active_ids.get(family, '')
            rec['physical_inventory_trajectory'] = inventory_trajectory
            rec['observed_week_inventory_change'] = inventory_change
            rec['observed_week_inventory_acceleration'] = inventory_acceleration
            rec['mechanism_external'] = 'UNKNOWN'  # 无外部事件证据不能用价格涨跌代替。
            required = ['rebar_weekly_prod','rebar_total_inv','building_deal_volume','profit_bf','hot_metal_247']
            rec['evidence_coverage'] = sum(pd.notna(row.get(c, np.nan)) for c in required)/len(required)
            rec['data_quality_status'] = 'UNVERIFIED_PIT'
            rec['mechanism_confirmation'] = 'CONFIRMED' if 'CONFIRMED' in statuses.values() else ('PENDING' if pending else 'UNKNOWN')
            price, ma = row.get('rb_close', np.nan), row.get('ma_20', np.nan)
            rec['trade_confirmation'] = 'UNKNOWN' if pd.isna(price) or pd.isna(ma) else ('UPTREND' if price > ma else 'DOWNTREND' if price < ma else 'NEUTRAL')
            rec['expected_holding_period_validated'] = 'UNKNOWN'
            rec['causal_identification_status'] = 'UNCONFIRMED'
            rows.append(rec)
            last_row, last_week = row, week
        return pd.DataFrame(rows, index=df.index), pd.DataFrame(events)
