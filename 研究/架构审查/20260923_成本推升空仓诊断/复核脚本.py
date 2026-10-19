import pandas as pd, numpy as np,json,hashlib
from pathlib import Path
root=Path(__file__).resolve().parents[3];exp=root/'研究/回测实验/20260923T031956Z_2bc43b82'
f=pd.read_parquet(root/'数据/加工/阶段B_特征宽表.parquet');f.index=f.index.astype(str)
s=pd.read_parquet(exp/'candidate_states.parquet');s.index=s.index.astype(str)
d=pd.read_parquet(exp/'util_50pct_FULL_WITH_DUPLICATE_PROXY_decisions.parquet').set_index('date')
e=pd.read_parquet(exp/'util_50pct_FULL_WITH_DUPLICATE_PROXY_equity.parquet').set_index('date')
f['ma20_audit']=f.rb_close.rolling(20).mean()
sq=f[[c for c in ['squeeze_index','i_squeeze_index','jm_squeeze_index','j_squeeze_index'] if c in f]].max(axis=1)
raw=(f.cost_push_spread_5d>.015)&((f.dominant_leader_type=='RAW_MATERIAL_SHOCK')|f.is_raw_material_squeeze|(sq>=2))
sust=raw&(f.pct_basis_tier3_1y>=.4)&(f.pct_flow_hz_outflow>=.3)&(f.rb_close>=f.cost_cash_floor)
low=(f.pct_virtual_mill_margin_1y<=.15)&(f.pct_virtual_mill_margin_hist<=.2)&(f.profit_bf.isna()|(f.profit_bf<=100))
lock=low&(f.rb_close>=f.ma20_audit*1.015)&raw
masks={'raw_push_proxy':raw,'raw_push_and_positive_rb_5d':raw&(f.rb_close.pct_change(5)>0),'sustained_push_proxy':sust,'sustained_and_low_margin_lock':sust&lock}
result={}
for label,mask in masks.items():
 x=d.reindex(f.index)[mask].dropna(subset=['raw_direction']);idx=x.index
 result[label]={'days':len(x),'raw_directions':x.raw_direction.value_counts().to_dict(),'vetted_directions':x.vetted_direction.value_counts().to_dict(),'actual_flat_days':int(e.reindex(idx).lots.eq(0).sum()),'flat_rationale':x[x.raw_direction=='FLAT'].signal_rationale.str.replace(r'\([^)]*\)','',regex=True).value_counts().head(10).to_dict(),'macro_override_days':int(s.reindex(idx).macro_regime.eq('宏观覆盖').sum()),'low_conf_lt40_days':int(s.reindex(idx).confidence_score.lt(40).sum()),'above_ma20_2p5_days':int((f.loc[idx].rb_close>f.loc[idx].ma20_audit*1.025).sum())}
print(json.dumps(result,ensure_ascii=False,indent=2))
idx=f.index[sust&lock];cols=['rb_close','ma20_audit','profit_bf','cost_push_spread_5d','pct_basis_tier3_1y','pct_flow_hz_outflow']
print('SUSTAINED BUT LOCKED EXAMPLES');print(f.loc[idx,cols].tail(8).join(d[['raw_direction','signal_rationale']]).to_string())
print('MACRO+POSITIVEPRICE EXAMPLES');idx=f.index[raw&(f.rb_close.pct_change(5)>0)&s.macro_regime.eq('宏观覆盖')];print(f.loc[idx,cols].tail(8).join(d[['raw_direction','signal_rationale']]).to_string())
manifest=json.loads((exp/'manifest.json').read_text());print('config',manifest['settings']);print('signal hash matches',hashlib.sha256((root/'stage_e/signal_generator.py').read_bytes()).hexdigest()==manifest['code_hashes']['stage_e/signal_generator.py'])
recent=d.loc[f.index[masks['raw_push_and_positive_rb_5d']&(f.index>='2021-01-01')]]
result['recent_2021_onward']={'days':len(recent),'raw_directions':recent.raw_direction.value_counts().to_dict(),'flat_rationale':recent[recent.raw_direction.eq('FLAT')].signal_rationale.str.replace(r'\([^)]*\)','',regex=True).value_counts().to_dict()}
result['metadata']={'checked_on':'2026-09-23','experiment':str(exp.relative_to(root)),'filter':'existing raw cost-push proxy AND past 5-trading-day RB return > 0; no forward-return filter','scope':'saved decision audit, not a new strategy backtest','settings':manifest['settings'],'sources':{}}
for path in [root/'数据/加工/阶段B_特征宽表.parquet', exp/'candidate_states.parquet',exp/'util_50pct_FULL_WITH_DUPLICATE_PROXY_decisions.parquet',exp/'util_50pct_FULL_WITH_DUPLICATE_PROXY_equity.parquet']:
 result['metadata']['sources'][str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
result['metadata']['feature_hash_matches_experiment']=result['metadata']['sources']['数据/加工/阶段B_特征宽表.parquet']==manifest['data_hashes']['数据/加工/阶段B_特征宽表.parquet']
Path(__file__).with_name('诊断统计.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
