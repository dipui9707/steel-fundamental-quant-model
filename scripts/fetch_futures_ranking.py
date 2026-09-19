#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: fetch_futures_ranking.py
功能描述: 基于天勤量化 (TqSdk) 接口获取黑色系五大核心品种（RB, HC, I, JM, J）每日交易所会员持仓龙虎榜数据，
         规范化写入 [数据/原始/期货会员持仓/]，并本地离线计算多空集中度偏度 (CS)、主力净头寸偏度 (TNB)、
         以及产业席位与投机席位分群动向剪刀差，同步落盘至 [数据/加工/加工指标.csv]。
"""

import os
import sys
import json
import argparse
import logging
from datetime import datetime, date
from pathlib import Path
import pandas as pd
import numpy as np

# 设置基础目录
BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "数据" / "原始" / "期货会员持仓"
PROCESSED_FILE = BASE_DIR / "数据" / "加工" / "加工指标.csv"
CONFIG_FILE = BASE_DIR / "config" / "tqsdk_config.json"
BROKER_DICT_FILE = BASE_DIR / "config" / "broker_classification.json"

# 黑色五大品种主连映射
COMMODITY_MAP = {
    "RB": {"name": "螺纹钢", "exchange": "SHFE", "main_symbol": "KQ.m@SHFE.rb", "multiplier": 10},
    "HC": {"name": "热轧卷板", "exchange": "SHFE", "main_symbol": "KQ.m@SHFE.hc", "multiplier": 10},
    "I":  {"name": "铁矿石", "exchange": "DCE",  "main_symbol": "KQ.m@DCE.i",   "multiplier": 100},
    "JM": {"name": "焦煤",   "exchange": "DCE",  "main_symbol": "KQ.m@DCE.jm",  "multiplier": 60},
    "J":  {"name": "焦炭",   "exchange": "DCE",  "main_symbol": "KQ.m@DCE.j",   "multiplier": 100},
}

def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return logging.getLogger("FuturesRanking")

def load_credentials(cli_user=None, cli_password=None):
    """加载天勤认证凭据：优先级 CLI > 环境变量 > 配置文件"""
    if cli_user and cli_password:
        return cli_user, cli_password
    
    env_user = os.environ.get("TQ_USER")
    env_pwd = os.environ.get("TQ_PASSWORD")
    if env_user and env_pwd:
        return env_user, env_pwd
    
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                u = cfg.get("tq_user")
                p = cfg.get("tq_password")
                if u and p and u != "YOUR_SHINNYTECH_PHONE_OR_USERNAME":
                    return u, p
        except Exception as e:
            logging.warning(f"读取配置文件 {CONFIG_FILE} 失败: {e}")
            
    return None, None

def load_broker_classification():
    """加载席位分群字典"""
    if BROKER_DICT_FILE.exists():
        with open(BROKER_DICT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"categories": {}}

def resolve_underlying_symbols(api, target_commodities):
    """通过主连解析今日对应的主力实际合约代码"""
    resolved = {}
    for code in target_commodities:
        meta = COMMODITY_MAP[code]
        main_sym = meta["main_symbol"]
        quote = api.get_quote(main_sym)
        api.wait_update(deadline=10)
        underlying = quote.underlying_symbol
        if not underlying:
            # 若主连暂未推导，回退到常见月份合约或直接读取 quote
            underlying = f"{meta['exchange']}.{code.lower()}2501" # 兜底推测
        resolved[code] = {
            "variety": code,
            "name": meta["name"],
            "exchange": meta["exchange"],
            "main_symbol": main_sym,
            "contract": underlying,
            "multiplier": meta["multiplier"],
            "open_interest": quote.open_interest if quote.open_interest else np.nan,
            "settle_price": quote.settlement if quote.settlement else quote.last_price
        }
    return resolved

def fetch_and_merge_rankings(api, contract, days=1, start_dt=None):
    """拉取多头与空头排名并合并为统一明细表"""
    logging.info(f"正在拉取 {contract} 多头前20席位...")
    df_long = api.query_symbol_ranking(contract, ranking_type="LONG", days=days, start_dt=start_dt)
    
    logging.info(f"正在拉取 {contract} 空头前20席位...")
    df_short = api.query_symbol_ranking(contract, ranking_type="SHORT", days=days, start_dt=start_dt)
    
    # 提取多头数据
    df_l = df_long[["datetime", "symbol", "exchange_id", "instrument_id", "broker", 
                    "long_oi", "long_change", "long_ranking"]].copy()
    
    # 提取空头数据
    df_s = df_short[["datetime", "symbol", "broker", 
                     "short_oi", "short_change", "short_ranking"]].copy()
    
    # 外连接合并席位
    df_merged = pd.merge(df_l, df_s, on=["datetime", "symbol", "broker"], how="outer")
    
    # 填充非前20但可能存在的维度
    df_merged["long_oi_filled"] = df_merged["long_oi"].fillna(0)
    df_merged["short_oi_filled"] = df_merged["short_oi"].fillna(0)
    df_merged["net_oi"] = df_merged["long_oi_filled"] - df_merged["short_oi_filled"]
    df_merged["long_change"] = df_merged["long_change"].fillna(0)
    df_merged["short_change"] = df_merged["short_change"].fillna(0)
    df_merged["net_change"] = df_merged["long_change"] - df_merged["short_change"]
    
    return df_merged

def compute_metrics_for_contract(df_merged, contract_info, broker_classes, query_date):
    """计算单个合约的衍生集中度与席位流向指标"""
    total_oi = contract_info.get("open_interest")
    long_sum_20 = df_merged["long_oi"].dropna().sum()
    short_sum_20 = df_merged["short_oi"].dropna().sum()
    net_pos_20 = long_sum_20 - short_sum_20
    
    cr_long_20 = (long_sum_20 / total_oi) if (total_oi and not np.isnan(total_oi) and total_oi > 0) else np.nan
    cr_short_20 = (short_sum_20 / total_oi) if (total_oi and not np.isnan(total_oi) and total_oi > 0) else np.nan
    cs_20 = (cr_long_20 - cr_short_20) if (not np.isnan(cr_long_20) and not np.isnan(cr_short_20)) else np.nan
    tnb = (net_pos_20 / total_oi) if (total_oi and not np.isnan(total_oi) and total_oi > 0) else np.nan
    
    # 分群席位变动
    ind_brokers = set(broker_classes.get("categories", {}).get("industrial", {}).get("brokers", []))
    spec_brokers = set(broker_classes.get("categories", {}).get("speculative", {}).get("brokers", []))
    
    ind_net_change = 0
    spec_net_change = 0
    for _, row in df_merged.iterrows():
        b = str(row["broker"]).strip()
        # 席位简称匹配
        if any(ib in b for ib in ind_brokers):
            ind_net_change += row["net_change"]
        elif any(sb in b for sb in spec_brokers):
            spec_net_change += row["net_change"]
            
    return {
        "query_date": query_date,
        "variety": contract_info["variety"],
        "contract": contract_info["contract"],
        "total_oi": total_oi,
        "long_sum_20": long_sum_20,
        "short_sum_20": short_sum_20,
        "net_pos_20": net_pos_20,
        "cr_long_20": round(cr_long_20 * 100, 2) if not np.isnan(cr_long_20) else np.nan,
        "cr_short_20": round(cr_short_20 * 100, 2) if not np.isnan(cr_short_20) else np.nan,
        "cs_20": round(cs_20 * 100, 2) if not np.isnan(cs_20) else np.nan,
        "tnb": round(tnb * 100, 2) if not np.isnan(tnb) else np.nan,
        "ind_net_change": int(ind_net_change),
        "spec_net_change": int(spec_net_change)
    }

def save_raw_table(df_all_ranks, data_date):
    """将原始席位记录保存到 [数据/原始/期货会员持仓/]"""
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    file_path = RAW_DIR / f"{data_date.replace('-', '')}_黑色五品种席位持仓原始明细.csv"
    
    # 格式规范化
    df_out = df_all_ranks.copy()
    recorded_at = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    available_date = f"{data_date}T18:30:00+08:00"
    
    df_out["observation_id"] = [f"OBS_RANK_{data_date.replace('-', '')}_{i+1:05d}" for i in range(len(df_out))]
    df_out["data_date"] = data_date
    df_out["available_date"] = available_date
    df_out["recorded_at"] = recorded_at
    df_out["source"] = "TqSdk / 交易所官方结算日度龙虎榜"
    df_out["quality_flag"] = "VALID"
    
    col_order = [
        "observation_id", "data_date", "available_date", "recorded_at",
        "symbol", "exchange_id", "instrument_id", "broker",
        "long_oi", "long_change", "long_ranking",
        "short_oi", "short_change", "short_ranking",
        "net_oi", "net_change", "source", "quality_flag"
    ]
    existing_cols = [c for c in col_order if c in df_out.columns]
    df_out[existing_cols].to_csv(file_path, index=False, encoding="utf-8-sig")
    logging.info(f"原始席位明细已落盘: {file_path} (共 {len(df_out)} 条席位记录)")
    return file_path

def append_to_processed_metrics(metrics_list, data_date):
    """将加工指标保存或追加到 [数据/加工/加工指标.csv]"""
    now_ts = datetime.now().strftime("%Y-%m-%dT%H:%M:%S+08:00")
    new_rows = []
    
    for m in metrics_list:
        v = m["variety"]
        # TNB 指标 (F27)
        if not np.isnan(m["tnb"]):
            new_rows.append({
                "feature_id": f"FEAT_TNB_{v}_{data_date.replace('-', '')}",
                "variable_id": "F27",
                "as_of": now_ts,
                "data_date": data_date,
                "value": m["tnb"],
                "unit": "%",
                "input_observation_ids": f"OBS_RANK_{data_date.replace('-', '')}_TOP20_{v}",
                "rule_id": "RULE_A05.2_TNB",
                "rule_version": "V1.0",
                "quality_flag": "VALID",
                "note": f"{v}主力合约({m['contract']})前20席位多空净头寸偏度"
            })
        # CS 集中度偏度
        if not np.isnan(m["cs_20"]):
            new_rows.append({
                "feature_id": f"FEAT_CS_{v}_{data_date.replace('-', '')}",
                "variable_id": "F27_CS",
                "as_of": now_ts,
                "data_date": data_date,
                "value": m["cs_20"],
                "unit": "%",
                "input_observation_ids": f"OBS_RANK_{data_date.replace('-', '')}_CS_{v}",
                "rule_id": "RULE_A05.2_CS",
                "rule_version": "V1.0",
                "quality_flag": "VALID",
                "note": f"{v}主力合约({m['contract']})多空前20集中度偏度(CR_Long-CR_Short)"
            })
        # 产业 vs 投机席位变动
        new_rows.append({
            "feature_id": f"FEAT_IND_SPEC_{v}_{data_date.replace('-', '')}",
            "variable_id": "F27_FLOW",
            "as_of": now_ts,
            "data_date": data_date,
            "value": f"Ind:{m['ind_net_change']};Spec:{m['spec_net_change']}",
            "unit": "手",
            "input_observation_ids": f"OBS_RANK_{data_date.replace('-', '')}_FLOW_{v}",
            "rule_id": "RULE_A05.2_SEAT_CLUSTER",
            "rule_version": "V1.0",
            "quality_flag": "VALID",
            "note": f"{v}产业席位净变动 vs 投机量化席位净变动"
        })
        
    if not new_rows:
        return
        
    df_new = pd.DataFrame(new_rows)
    if PROCESSED_FILE.exists() and PROCESSED_FILE.stat().st_size > 0:
        try:
            df_old = pd.read_csv(PROCESSED_FILE, encoding="utf-8")
            # 去重：若当天该特征已存在则更新
            df_combined = pd.concat([df_old[~df_old["feature_id"].isin(df_new["feature_id"])], df_new], ignore_index=True)
            df_combined.to_csv(PROCESSED_FILE, index=False, encoding="utf-8-sig")
        except Exception as e:
            logging.warning(f"读取加工指标旧文件出错，直接追加: {e}")
            df_new.to_csv(PROCESSED_FILE, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        df_new.to_csv(PROCESSED_FILE, index=False, encoding="utf-8-sig")
        
    logging.info(f"加工指标已更新至: {PROCESSED_FILE} (新增/更新 {len(new_rows)} 条指标)")

def generate_mock_data(query_date, commodities):
    """为无账号测试/离线演示生成高仿真样本数据"""
    logging.info("【离线仿真测试模式】正在生成黑色五品种仿真席位持仓数据...")
    broker_classes = load_broker_classification()
    all_sample_rows = []
    sample_metrics = []
    
    ind_brokers = broker_classes.get("categories", {}).get("industrial", {}).get("brokers", ["永安期货", "浙商期货", "银河期货", "中粮期货"])
    spec_brokers = broker_classes.get("categories", {}).get("speculative", {}).get("brokers", ["东证期货", "华泰期货", "国泰君安", "广发期货"])
    other_brokers = ["中信期货", "鲁证期货", "海通期货", "南华期货", "申银万国", "一德期货", "新湖期货", "光大期货", "方正中期", "招商期货", "国投安信", "建信期货"]
    pool = list(dict.fromkeys(ind_brokers[:6] + spec_brokers[:6] + other_brokers[:8]))[:20]
    
    for code in commodities:
        meta = COMMODITY_MAP[code]
        contract = f"{meta['exchange']}.{code.lower()}2501"
        base_oi = {"RB": 1850000, "HC": 1120000, "I": 820000, "JM": 210000, "J": 58000}[code]
        
        long_ranks = []
        short_ranks = []
        for rank, b in enumerate(pool, start=1):
            l_oi = int(base_oi * 0.025 * (21 - rank) / 10 * (1 + np.random.uniform(-0.1, 0.1)))
            s_oi = int(base_oi * 0.024 * (21 - rank) / 10 * (1 + np.random.uniform(-0.1, 0.1)))
            l_chg = int(np.random.normal(200, 1500))
            s_chg = int(np.random.normal(-100, 1500))
            
            all_sample_rows.append({
                "datetime": query_date,
                "symbol": contract,
                "exchange_id": meta["exchange"],
                "instrument_id": f"{code.lower()}2501",
                "broker": b,
                "long_oi": l_oi,
                "long_change": l_chg,
                "long_ranking": rank,
                "short_oi": s_oi,
                "short_change": s_chg,
                "short_ranking": rank,
                "net_oi": l_oi - s_oi,
                "net_change": l_chg - s_chg
            })
            
        contract_info = {
            "variety": code,
            "contract": contract,
            "open_interest": base_oi
        }
        df_merged = pd.DataFrame([r for r in all_sample_rows if r["symbol"] == contract])
        m = compute_metrics_for_contract(df_merged, contract_info, broker_classes, query_date)
        sample_metrics.append(m)
        
    df_all = pd.DataFrame(all_sample_rows)
    raw_path = save_raw_table(df_all, query_date)
    append_to_processed_metrics(sample_metrics, query_date)
    
    print("\n" + "="*80)
    print(f"【黑色五品种持仓集中度与席位多空衍生指标汇总】 日期: {query_date}")
    print("="*80)
    df_summary = pd.DataFrame(sample_metrics)[["variety", "contract", "total_oi", "cr_long_20", "cr_short_20", "cs_20", "tnb", "ind_net_change", "spec_net_change"]]
    df_summary.columns = ["品种", "主力合约", "总持仓(手)", "多头前20占比(%)", "空头前20占比(%)", "集中度偏度(CS%)", "净偏度(TNB%)", "产业席位净变动", "投机席位净变动"]
    print(df_summary.to_string(index=False))
    print("="*80 + "\n")

def main():
    parser = argparse.ArgumentParser(description="TqSdk 黑色五品种交易所会员持仓龙虎榜采集与衍生量化计算工具")
    parser.add_argument("--commodities", nargs="+", default=["RB", "HC", "I", "JM", "J"], help="目标品种列表，默认五大品种")
    parser.add_argument("--date", type=str, default=None, help="查询日期 (YYYY-MM-DD)，默认为今日或最近交易日")
    parser.add_argument("--user", type=str, default=None, help="快期账号（优先于配置文件）")
    parser.add_argument("--password", type=str, default=None, help="快期密码（优先于配置文件）")
    parser.add_argument("--mock", action="store_true", help="启用离线仿真模式（无需账号直接测试全流程）")
    
    args = parser.parse_args()
    logger = setup_logger()
    
    query_date = args.date if args.date else datetime.now().strftime("%Y-%m-%d")
    
    # 离线模式
    if args.mock:
        generate_mock_data(query_date, args.commodities)
        return
        
    user, password = load_credentials(args.user, args.password)
    if not user or not password:
        logger.warning("未检测到有效快期账号与密码。")
        logger.info("可通过以下任意一种方式提供：")
        logger.info("  1. 复制 config/tqsdk_config.example.json 为 config/tqsdk_config.json 并填入")
        logger.info("  2. 设置环境变量 TQ_USER 与 TQ_PASSWORD")
        logger.info("  3. 运行时指定参数: python fetch_futures_ranking.py --user <账号> --password <密码>")
        logger.info("  4. 离线测试请输入参数: --mock")
        print("\n提示: 当前暂无快期凭据，是否以 --mock 模式运行全流程校验？")
        return

    # 正式通过 TqSdk 拉取
    try:
        from tqsdk import TqApi, TqAuth
    except ImportError:
        logger.error("当前环境中未安装 tqsdk，请先运行 pip install tqsdk")
        sys.exit(1)
        
    logger.info(f"正在连接天勤量化服务 (账号: {user[:3]}****)...")
    broker_classes = load_broker_classification()
    
    try:
        with TqApi(auth=TqAuth(user, password)) as api:
            logger.info("认证成功！正在解析五大品种今日主力合约...")
            resolved_map = resolve_underlying_symbols(api, args.commodities)
            
            all_dfs = []
            metrics_list = []
            
            for code, meta in resolved_map.items():
                contract = meta["contract"]
                logger.info(f"开始处理 [{code}] 主力合约: {contract}...")
                try:
                    df_contract = fetch_and_merge_rankings(api, contract, days=1)
                    all_dfs.append(df_contract)
                    
                    m = compute_metrics_for_contract(df_contract, meta, broker_classes, query_date)
                    metrics_list.append(m)
                except Exception as ex:
                    logger.error(f"获取 {contract} 排名数据失败: {ex}")
                    
            if all_dfs:
                df_all_ranks = pd.concat(all_dfs, ignore_index=True)
                save_raw_table(df_all_ranks, query_date)
                append_to_processed_metrics(metrics_list, query_date)
                
                print("\n" + "="*80)
                print(f"【黑色五品种持仓集中度与席位多空衍生指标汇总】 日期: {query_date}")
                print("="*80)
                df_summary = pd.DataFrame(metrics_list)[["variety", "contract", "total_oi", "cr_long_20", "cr_short_20", "cs_20", "tnb", "ind_net_change", "spec_net_change"]]
                df_summary.columns = ["品种", "主力合约", "总持仓(手)", "多头前20占比(%)", "空头前20占比(%)", "集中度偏度(CS%)", "净偏度(TNB%)", "产业席位净变动", "投机席位净变动"]
                print(df_summary.to_string(index=False))
                print("="*80 + "\n")
                
    except Exception as exc:
        logger.error(f"TqSdk 执行过程异常: {exc}")

if __name__ == "__main__":
    main()
