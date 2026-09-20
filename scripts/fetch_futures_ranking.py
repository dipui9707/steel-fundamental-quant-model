#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: fetch_futures_ranking.py
任务编号: T-LOCAL-001 (基于 02_席位与数据契约审定.md 严密重构)
功能描述: 
    基于天勤量化 (TqSdk) 接口获取黑色系五大核心品种（RB, HC, I, JM, J）每日交易所会员持仓龙虎榜数据。
    严格遵守点时数据契约 (Point-In-Time Contract) 与量化审定标准：
    1. 榜外席位严禁填零：单侧未入榜席位持仓/变动保留 NaN，不以零作假设；提供数学截断界限，仅在多空重合交集中计算对称精确净持仓；
    2. 真实时间戳与动态日期绑定：记录真实的带时区接收时刻 (Asia/Shanghai)，禁止硬编码 18:30；请求绑定 start_dt 并校验返回日期；
    3. Mock 与真实环境物理隔离：离线仿真数据独立落盘于 [研究/mock_data/] 且显式标注 SYNTHETIC/MOCK，严禁污染正式事实库；
    4. 合约解析防胡猜与指标精化：正确传递绝对超时戳，解析失败显式报错，严禁回退猜测 2501；统一 B_rank 集中度差额算法。
"""

import os
import sys
import json
import time
import math
import getpass
import argparse
import logging
from datetime import datetime, date
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

# 时区设定
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# 基础目录
BASE_DIR = Path(__file__).resolve().parent.parent

# 正式生产路径 (LIVE_RECORDED)
LIVE_RAW_DIR = BASE_DIR / "数据" / "原始" / "期货会员持仓"
LIVE_PROCESSED_FILE = BASE_DIR / "数据" / "加工" / "加工指标.csv"

# 隔离测试路径 (SYNTHETIC / MOCK)
MOCK_RAW_DIR = BASE_DIR / "研究" / "mock_data" / "期货会员持仓"
MOCK_PROCESSED_FILE = BASE_DIR / "研究" / "mock_data" / "加工指标_mock.csv"

# 配置与字典路径
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

def get_now_shanghai_iso():
    """获取带 Asia/Shanghai 时区的当前 ISO 8601 字符串"""
    return datetime.now(SHANGHAI_TZ).isoformat()

def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return logging.getLogger("FuturesRankingPipeline")

def load_credentials(cli_user=None):
    """安全加载天勤凭据：优先级 CLI User > 环境变量 > 配置文件 > 交互式隐藏输入"""
    env_user = os.environ.get("TQ_USER")
    env_pwd = os.environ.get("TQ_PASSWORD")
    
    user = cli_user or env_user
    pwd = env_pwd
    
    if (not user or not pwd) and CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                u = cfg.get("tq_user")
                p = cfg.get("tq_password")
                if u and p and u != "YOUR_SHINNYTECH_PHONE_OR_USERNAME":
                    user = user or u
                    pwd = pwd or p
        except Exception as e:
            logging.warning(f"读取凭据配置文件失败: {e}")
            
    return user, pwd

def load_broker_classification():
    """加载会员席位分群字典"""
    if BROKER_DICT_FILE.exists():
        try:
            with open(BROKER_DICT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logging.warning(f"读取席位分类字典失败: {e}")
    return {"categories": {}}

def resolve_underlying_symbols(api, target_commodities, explicit_contracts=None, timeout=15.0):
    """
    解析对应的主力实际合约代码。
    严禁任何硬编码猜测（如猜 2501）。若超时未就绪且未显式指定，抛出明确异常。
    """
    resolved = {}
    explicit_map = {}
    if explicit_contracts:
        for c in explicit_contracts:
            # 形如 SHFE.rb2501 或 rb2501
            parts = c.split(".")
            inst = parts[-1]
            for v in COMMODITY_MAP.keys():
                if inst.lower().startswith(v.lower()):
                    explicit_map[v] = c
                    break

    for code in target_commodities:
        meta = COMMODITY_MAP[code]
        if code in explicit_map:
            actual_contract = explicit_map[code]
            quote = api.get_quote(actual_contract)
            # 等待该合约行情就绪
            deadline = time.time() + timeout
            while time.time() < deadline:
                api.wait_update(deadline=deadline)
                if quote.datetime and quote.datetime != "":
                    break
            oi = quote.open_interest if (quote.open_interest and math.isfinite(quote.open_interest)) else np.nan
            sp = quote.settlement if (quote.settlement and math.isfinite(quote.settlement)) else (quote.last_price if (quote.last_price and math.isfinite(quote.last_price)) else np.nan)
            resolved[code] = {
                "variety": code,
                "name": meta["name"],
                "exchange": meta["exchange"],
                "contract": actual_contract,
                "multiplier": meta["multiplier"],
                "open_interest": oi,
                "settle_price": sp,
                "resolution_method": "EXPLICIT_SPECIFIED"
            }
        else:
            main_sym = meta["main_symbol"]
            quote = api.get_quote(main_sym)
            deadline = time.time() + timeout
            underlying = None
            while time.time() < deadline:
                api.wait_update(deadline=deadline)
                if quote.underlying_symbol and quote.underlying_symbol.strip() != "":
                    underlying = quote.underlying_symbol.strip()
                    break
            
            if not underlying:
                raise RuntimeError(
                    f"【拒绝猜测实约】在超时时间 {timeout}s 内无法解析主连 {main_sym} 的底层主力合约。"
                    f"严禁主观硬编码兜底猜测合约！请核查网络或使用 --contracts 显式传入目标合约。"
                )
            
            # 读取实际合约日终快照
            sub_quote = api.get_quote(underlying)
            deadline_sub = time.time() + timeout
            while time.time() < deadline_sub:
                api.wait_update(deadline=deadline_sub)
                if sub_quote.datetime and sub_quote.datetime != "":
                    break
                    
            oi = sub_quote.open_interest if (sub_quote.open_interest and math.isfinite(sub_quote.open_interest)) else (quote.open_interest if (quote.open_interest and math.isfinite(quote.open_interest)) else np.nan)
            sp = sub_quote.settlement if (sub_quote.settlement and math.isfinite(sub_quote.settlement)) else (quote.settlement if (quote.settlement and math.isfinite(quote.settlement)) else np.nan)

            resolved[code] = {
                "variety": code,
                "name": meta["name"],
                "exchange": meta["exchange"],
                "contract": underlying,
                "multiplier": meta["multiplier"],
                "open_interest": oi,
                "settle_price": sp,
                "resolution_method": "DYNAMIC_RESOLVED"
            }

    return resolved

def fetch_and_merge_rankings(api, contract, target_date=None, days=1):
    """
    拉取多头与空头排名并合并为统一明细表。
    严格执行点时数据契约：
    1. 榜外席位持仓保留 NaN，严禁 fillna(0)；
    2. 计算有界的数学截断界限 [net_lower, net_upper]；
    3. 仅在两侧皆在榜的对称交集计算精确净持仓；
    4. 严格校验返回数据的真实交易日，拒绝日期贴错标签。
    """
    start_dt = None
    if target_date:
        start_dt = datetime.strptime(target_date, "%Y-%m-%d").date()

    df_long = api.query_symbol_ranking(contract, ranking_type="LONG", days=days, start_dt=start_dt)
    df_short = api.query_symbol_ranking(contract, ranking_type="SHORT", days=days, start_dt=start_dt)

    if df_long is None or len(df_long) == 0 or df_short is None or len(df_short) == 0:
        raise RuntimeError(f"合约 {contract} 查询返回空排名数据，交易所尚未披露或该日非交易日。")

    # 提取多头数据并校验
    df_l = df_long[["datetime", "symbol", "exchange_id", "instrument_id", "broker", 
                    "long_oi", "long_change", "long_ranking"]].copy()
    # 提取空头数据并校验
    df_s = df_short[["datetime", "symbol", "exchange_id", "instrument_id", "broker", 
                     "short_oi", "short_change", "short_ranking"]].copy()

    # 日期核验
    returned_dates_l = df_l["datetime"].dropna().unique()
    returned_dates_s = df_s["datetime"].dropna().unique()
    if len(returned_dates_l) == 0 or len(returned_dates_s) == 0:
        raise RuntimeError(f"合约 {contract} 返回数据中缺少有效 datetime 字段。")
    
    actual_date_str = str(returned_dates_l[-1])
    if target_date and actual_date_str != target_date:
        raise RuntimeError(
            f"【日期错配拒绝】合约 {contract} 请求日期为 {target_date}，"
            f"但 TqSdk 实际返回日期为 {actual_date_str}。严禁以请求日硬重命名返回数据！"
        )

    # 过滤出当前目标交易日
    df_l = df_l[df_l["datetime"] == actual_date_str].copy()
    df_s = df_s[df_s["datetime"] == actual_date_str].copy()

    # 外连接合并席位
    df_merged = pd.merge(df_l, df_s, on=["datetime", "symbol", "broker"], how="outer", suffixes=("_l", "_s"))

    # 合并元数据列
    df_merged["exchange_id"] = df_merged["exchange_id_l"].combine_first(df_merged["exchange_id_s"])
    df_merged["instrument_id"] = df_merged["instrument_id_l"].combine_first(df_merged["instrument_id_s"])
    df_merged.drop(columns=["exchange_id_l", "exchange_id_s", "instrument_id_l", "instrument_id_s"], inplace=True)

    # 获取第 20 名门槛值（用于截断区间计算）
    # 若在榜数不足 20，取在榜末位作为截断门槛
    s_20_threshold = df_s["short_oi"].dropna().min() if len(df_s["short_oi"].dropna()) > 0 else 0
    l_20_threshold = df_l["long_oi"].dropna().min() if len(df_l["long_oi"].dropna()) > 0 else 0

    net_oi_list = []
    net_lower_list = []
    net_upper_list = []
    net_change_list = []
    is_exact_list = []

    for _, row in df_merged.iterrows():
        l_val = row["long_oi"]
        s_val = row["short_oi"]
        l_chg = row["long_change"]
        s_chg = row["short_change"]

        l_present = pd.notna(l_val)
        s_present = pd.notna(s_val)

        if l_present and s_present:
            # 多空双侧均入榜：确定的精确净持仓
            exact_net = l_val - s_val
            net_oi_list.append(exact_net)
            net_lower_list.append(exact_net)
            net_upper_list.append(exact_net)
            is_exact_list.append(True)
        elif l_present and not s_present:
            # 仅多头入榜，空头在榜外：空头范围为 [0, s_20_threshold]
            # 真实净持仓范围为 [l_val - s_20_threshold, l_val]
            net_oi_list.append(np.nan) # 绝不简单填 0
            net_lower_list.append(l_val - s_20_threshold)
            net_upper_list.append(l_val)
            is_exact_list.append(False)
        elif not l_present and s_present:
            # 仅空头入榜，多头在榜外：多头范围为 [0, l_20_threshold]
            # 真实净持仓范围为 [-s_val, l_20_threshold - s_val]
            net_oi_list.append(np.nan) # 绝不简单填 0
            net_lower_list.append(-s_val)
            net_upper_list.append(l_20_threshold - s_val)
            is_exact_list.append(False)
        else:
            net_oi_list.append(np.nan)
            net_lower_list.append(np.nan)
            net_upper_list.append(np.nan)
            is_exact_list.append(False)

        # 变动量计算：仅当多空变动量均有效时计算精确净变动
        if pd.notna(l_chg) and pd.notna(s_chg):
            net_change_list.append(l_chg - s_chg)
        else:
            net_change_list.append(np.nan)

    df_merged["net_oi"] = net_oi_list
    df_merged["net_oi_lower_bound"] = net_lower_list
    df_merged["net_oi_upper_bound"] = net_upper_list
    df_merged["net_change"] = net_change_list
    df_merged["is_exact_net"] = is_exact_list

    return df_merged, actual_date_str

def compute_metrics_for_contract(df_merged, contract_info, broker_classes, query_date):
    """
    依据 A05.2 审定规范计算合约的集中度差额与席位子样本流向指标。
    统一算法：
    1. B_rank = CR_Long_20 - CR_Short_20 = (LongSum20 - ShortSum20) / N_t
    2. 计算对称交集 (L ∩ S) 的共同净持仓与共同会员数；
    3. 席位画像分群仅对多空双侧均有有效变动值的样本计算，不把未知填零。
    """
    total_oi = contract_info.get("open_interest")
    long_sum_20 = df_merged["long_oi"].dropna().sum()
    short_sum_20 = df_merged["short_oi"].dropna().sum()

    has_valid_oi = (total_oi is not None) and math.isfinite(total_oi) and (total_oi > 0)
    
    cr_long_20 = (long_sum_20 / total_oi) if has_valid_oi else np.nan
    cr_short_20 = (short_sum_20 / total_oi) if has_valid_oi else np.nan
    
    # B_rank：两份截断榜单总额差占单边 OI 的比例
    b_rank = (cr_long_20 - cr_short_20) if (not np.isnan(cr_long_20) and not np.isnan(cr_short_20)) else np.nan

    # 对称重合交集 (Common Overlap Members)
    common_mask = df_merged["is_exact_net"] == True
    common_df = df_merged[common_mask]
    common_count = len(common_df)
    common_net_pos = common_df["net_oi"].sum() if common_count > 0 else 0
    common_net_change = common_df["net_change"].dropna().sum() if len(common_df["net_change"].dropna()) > 0 else 0

    # 席位分群：仅对具有确定净变动的会员统计
    ind_brokers = set(broker_classes.get("categories", {}).get("industrial", {}).get("brokers", []))
    spec_brokers = set(broker_classes.get("categories", {}).get("speculative", {}).get("brokers", []))

    ind_net_change = 0
    spec_net_change = 0
    ind_count = 0
    spec_count = 0

    for _, row in common_df.iterrows():
        b = str(row["broker"]).strip()
        chg = row["net_change"]
        if pd.notna(chg):
            if any(ib in b for ib in ind_brokers):
                ind_net_change += chg
                ind_count += 1
            elif any(sb in b for sb in spec_brokers):
                spec_net_change += chg
                spec_count += 1

    return {
        "query_date": query_date,
        "variety": contract_info["variety"],
        "contract": contract_info["contract"],
        "total_oi": total_oi if has_valid_oi else np.nan,
        "long_sum_20": long_sum_20,
        "short_sum_20": short_sum_20,
        "cr_long_20": round(cr_long_20 * 100, 4) if not np.isnan(cr_long_20) else np.nan,
        "cr_short_20": round(cr_short_20 * 100, 4) if not np.isnan(cr_short_20) else np.nan,
        "b_rank": round(b_rank * 100, 4) if not np.isnan(b_rank) else np.nan,
        "common_count": common_count,
        "common_net_pos": int(common_net_pos),
        "common_net_change": int(common_net_change),
        "ind_net_change": int(ind_net_change),
        "ind_covered_count": ind_count,
        "spec_net_change": int(spec_net_change),
        "spec_covered_count": spec_count
    }

def save_raw_table(df_all_ranks, data_date, is_mock=False):
    """
    保存原始席位龙虎榜记录。
    严格物理隔离与元数据隔离：
    - is_mock=True: 强制写入 研究/mock_data/期货会员持仓/，标记 SYNTHETIC/MOCK
    - is_mock=False: 写入 数据/原始/期货会员持仓/，标记 LIVE_RECORDED/VALID
    """
    target_dir = MOCK_RAW_DIR if is_mock else LIVE_RAW_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    
    prefix = "MOCK_" if is_mock else ""
    file_path = target_dir / f"{prefix}{data_date.replace('-', '')}_黑色五品种席位持仓原始明细.csv"

    df_out = df_all_ranks.copy()
    recorded_at = get_now_shanghai_iso()
    info_mode = "SYNTHETIC" if is_mock else "LIVE_RECORDED"
    quality_flag = "MOCK" if is_mock else "VALID"
    source = "SYNTHETIC_FIXTURE" if is_mock else "TqSdk / 交易所官方结算日度龙虎榜"
    avail_basis = "SYNTHETIC" if is_mock else "LIVE_RECEIPT"

    # 生成稳定 Observation ID
    obs_prefix = "OBS_MOCK" if is_mock else "OBS_RANK"
    df_out["observation_id"] = [f"{obs_prefix}_{data_date.replace('-', '')}_{i+1:05d}" for i in range(len(df_out))]
    df_out["data_date"] = data_date
    df_out["available_date"] = recorded_at
    df_out["recorded_at"] = recorded_at
    df_out["availability_basis"] = avail_basis
    df_out["information_set_mode"] = info_mode
    df_out["source"] = source
    df_out["quality_flag"] = quality_flag

    col_order = [
        "observation_id", "data_date", "available_date", "recorded_at",
        "availability_basis", "information_set_mode",
        "symbol", "exchange_id", "instrument_id", "broker", "is_exact_net",
        "long_ranking", "long_oi", "long_change",
        "short_ranking", "short_oi", "short_change",
        "net_oi", "net_oi_lower_bound", "net_oi_upper_bound", "net_change",
        "source", "quality_flag"
    ]
    existing_cols = [c for c in col_order if c in df_out.columns]
    df_out[existing_cols].to_csv(file_path, index=False, encoding="utf-8-sig")
    logging.info(f"[{info_mode}] 原始席位明细落盘: {file_path} (共 {len(df_out)} 条席位记录)")
    return file_path

def append_to_processed_metrics(metrics_list, data_date, is_mock=False):
    """
    保存或追加加工衍生指标。
    严格物理隔离：
    - is_mock=True: 写入 研究/mock_data/加工指标_mock.csv
    - is_mock=False: 写入 数据/加工/加工指标.csv
    """
    target_file = MOCK_PROCESSED_FILE if is_mock else LIVE_PROCESSED_FILE
    target_file.parent.mkdir(parents=True, exist_ok=True)

    now_ts = get_now_shanghai_iso()
    quality_flag = "MOCK" if is_mock else "VALID"
    rule_prefix = "RULE_MOCK" if is_mock else "RULE_A05.2"
    obs_prefix = "OBS_MOCK" if is_mock else "OBS_RANK"

    new_rows = []
    for m in metrics_list:
        v = m["variety"]
        # B_rank 指标 (F27 集中度差额)
        if not np.isnan(m["b_rank"]):
            new_rows.append({
                "feature_id": f"FEAT_BRANK_{v}_{data_date.replace('-', '')}",
                "variable_id": "F27",
                "as_of": now_ts,
                "data_date": data_date,
                "value": m["b_rank"],
                "unit": "%",
                "input_observation_ids": f"{obs_prefix}_{data_date.replace('-', '')}_{v}_MANIFEST",
                "rule_id": f"{rule_prefix}_B_RANK",
                "rule_version": "V1.1_审定版",
                "quality_flag": quality_flag,
                "note": f"{v}主力合约({m['contract']})前20榜单集中度差额率(B_rank=CR_L-CR_S)"
            })
        # 对称重合交集净持仓
        new_rows.append({
            "feature_id": f"FEAT_COMMON_NET_{v}_{data_date.replace('-', '')}",
            "variable_id": "F27_COMMON",
            "as_of": now_ts,
            "data_date": data_date,
            "value": m["common_net_pos"],
            "unit": "手",
            "input_observation_ids": f"{obs_prefix}_{data_date.replace('-', '')}_{v}_MANIFEST",
            "rule_id": f"{rule_prefix}_COMMON_NET",
            "rule_version": "V1.1_审定版",
            "quality_flag": quality_flag,
            "note": f"{v}多空双侧重合席位({m['common_count']}家)对称精确净持仓"
        })
        # 席位分群流向变动
        new_rows.append({
            "feature_id": f"FEAT_SEAT_FLOW_{v}_{data_date.replace('-', '')}",
            "variable_id": "F27_FLOW",
            "as_of": now_ts,
            "data_date": data_date,
            "value": f"Ind:{m['ind_net_change']}(n={m['ind_covered_count']});Spec:{m['spec_net_change']}(n={m['spec_covered_count']})",
            "unit": "手",
            "input_observation_ids": f"{obs_prefix}_{data_date.replace('-', '')}_{v}_MANIFEST",
            "rule_id": f"{rule_prefix}_SEAT_FLOW",
            "rule_version": "V1.1_审定版",
            "quality_flag": quality_flag,
            "note": f"{v}产业套保席位 vs 量化投机席位双侧有效净变动及样本覆盖数"
        })

    if not new_rows:
        return

    df_new = pd.DataFrame(new_rows)
    if target_file.exists() and target_file.stat().st_size > 0:
        try:
            df_old = pd.read_csv(target_file, encoding="utf-8")
            df_combined = pd.concat([df_old[~df_old["feature_id"].isin(df_new["feature_id"])], df_new], ignore_index=True)
            df_combined.to_csv(target_file, index=False, encoding="utf-8-sig")
        except Exception as e:
            logging.warning(f"更新加工指标旧文件出错，直接追加: {e}")
            df_new.to_csv(target_file, mode="a", header=False, index=False, encoding="utf-8-sig")
    else:
        df_new.to_csv(target_file, index=False, encoding="utf-8-sig")

    logging.info(f"加工特征已更新至: {target_file} (新增/更新 {len(new_rows)} 条指标)")

def generate_mock_data(query_date, commodities):
    """
    生成确定性高仿真离线测试样本 (R05, R16)。
    固定种子 seed=42，模拟真实的席位多空非完全重合特征（28家会员：12家重合，8家仅多头，8家仅空头）。
    数据完全物理隔离写入 [研究/mock_data/]。
    """
    logging.info("【离线仿真测试模式】采用确定性伪随机种子 (seed=42) 模拟真实非对称多空榜单...")
    np.random.seed(42)
    broker_classes = load_broker_classification()
    all_sample_rows = []
    sample_metrics = []

    # 构造 28 家典型会员池
    common_pool = ["永安期货", "中信期货", "国泰君安", "银河期货", "浙商期货", "华泰期货", 
                   "东证期货", "广发期货", "中粮期货", "南华期货", "申银万国", "一德期货"] # 12家重合
    long_only_pool = ["鲁证期货", "新湖期货", "光大期货", "方正中期", "招商期货", "国投安信", "金瑞期货", "宏源期货"] # 8家仅多头
    short_only_pool = ["海通期货", "建信期货", "创元期货", "兴证期货", "弘业期货", "长江期货", "东吴期货", "美尔雅"] # 8家仅空头

    for code in commodities:
        meta = COMMODITY_MAP[code]
        contract = f"{meta['exchange']}.{code.lower()}2501"
        base_oi = {"RB": 1850000, "HC": 1120000, "I": 820000, "JM": 210000, "J": 58000}[code]

        long_brokers = common_pool + long_only_pool # 20家
        short_brokers = common_pool + short_only_pool # 20家

        long_records = {}
        for rank, b in enumerate(long_brokers, start=1):
            l_oi = int(base_oi * 0.024 * (21 - rank) / 10 * (1 + np.random.uniform(-0.05, 0.05)))
            l_chg = int(np.random.normal(300, 800))
            long_records[b] = (l_oi, l_chg, rank)

        short_records = {}
        for rank, b in enumerate(short_brokers, start=1):
            s_oi = int(base_oi * 0.023 * (21 - rank) / 10 * (1 + np.random.uniform(-0.05, 0.05)))
            s_chg = int(np.random.normal(-150, 800))
            short_records[b] = (s_oi, s_chg, rank)

        all_brokers = list(dict.fromkeys(long_brokers + short_brokers)) # 28家

        s_20_val = short_records[short_brokers[-1]][0]
        l_20_val = long_records[long_brokers[-1]][0]

        for b in all_brokers:
            l_info = long_records.get(b)
            s_info = short_records.get(b)

            l_oi = l_info[0] if l_info else np.nan
            l_chg = l_info[1] if l_info else np.nan
            l_rk = l_info[2] if l_info else np.nan

            s_oi = s_info[0] if s_info else np.nan
            s_chg = s_info[1] if s_info else np.nan
            s_rk = s_info[2] if s_info else np.nan

            if pd.notna(l_oi) and pd.notna(s_oi):
                net = l_oi - s_oi
                net_l = net
                net_u = net
                net_c = l_chg - s_chg
                exact = True
            elif pd.notna(l_oi) and pd.isna(s_oi):
                net = np.nan
                net_l = l_oi - s_20_val
                net_u = l_oi
                net_c = np.nan
                exact = False
            elif pd.isna(l_oi) and pd.notna(s_oi):
                net = np.nan
                net_l = -s_oi
                net_u = l_20_val - s_oi
                net_c = np.nan
                exact = False
            else:
                net = np.nan
                net_l = np.nan
                net_u = np.nan
                net_c = np.nan
                exact = False

            all_sample_rows.append({
                "datetime": query_date,
                "symbol": contract,
                "exchange_id": meta["exchange"],
                "instrument_id": f"{code.lower()}2501",
                "broker": b,
                "is_exact_net": exact,
                "long_ranking": l_rk,
                "long_oi": l_oi,
                "long_change": l_chg,
                "short_ranking": s_rk,
                "short_oi": s_oi,
                "short_change": s_chg,
                "net_oi": net,
                "net_oi_lower_bound": net_l,
                "net_oi_upper_bound": net_u,
                "net_change": net_c
            })

        contract_info = {
            "variety": code,
            "contract": contract,
            "open_interest": base_oi
        }
        df_merged_contract = pd.DataFrame([r for r in all_sample_rows if r["symbol"] == contract])
        m = compute_metrics_for_contract(df_merged_contract, contract_info, broker_classes, query_date)
        sample_metrics.append(m)

    df_all = pd.DataFrame(all_sample_rows)
    raw_path = save_raw_table(df_all, query_date, is_mock=True)
    append_to_processed_metrics(sample_metrics, query_date, is_mock=True)

    print("\n" + "="*96)
    print(f"【离线仿真验收汇总表】 日期: {query_date} (已物理隔离至 研究/mock_data/)")
    print("="*96)
    df_summary = pd.DataFrame(sample_metrics)[["variety", "contract", "total_oi", "cr_long_20", "cr_short_20", "b_rank", "common_count", "common_net_pos", "ind_net_change", "spec_net_change"]]
    df_summary.columns = ["品种", "主力合约", "单边OI(手)", "多头Top20(%)", "空头Top20(%)", "集中度偏度(B_rank%)", "对称重合席位数", "重合净持仓(手)", "产业净变动", "投机净变动"]
    print(df_summary.to_string(index=False))
    print("="*96 + "\n")
    return raw_path, sample_metrics

def main():
    parser = argparse.ArgumentParser(description="TqSdk 黑色五品种交易所会员持仓龙虎榜采集与衍生量化计算工具 (T-LOCAL-001 审定版)")
    parser.add_argument("--commodities", nargs="+", default=["RB", "HC", "I", "JM", "J"], help="目标品种列表，默认五大品种")
    parser.add_argument("--contracts", nargs="+", default=None, help="显式指定目标合约列表（如 SHFE.rb2501 DCE.i2501），避免实时解析或用于历史回溯")
    parser.add_argument("--date", type=str, default=None, help="目标交易日 (YYYY-MM-DD)，默认为今日")
    parser.add_argument("--user", type=str, default=None, help="快期账号（仅支持用户名/手机号传参，严禁命令行传明文密码）")
    parser.add_argument("--mock", action="store_true", help="启用离线仿真模式（数据物理隔离至 研究/mock_data/）")
    parser.add_argument("--timeout", type=float, default=15.0, help="TqSdk 行情就绪与解析超时秒数")

    args = parser.parse_args()
    logger = setup_logger()

    query_date = args.date if args.date else datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d")

    # 1. 离线仿真模式
    if args.mock:
        generate_mock_data(query_date, args.commodities)
        return

    # 2. 真实生产环境模式
    user, password = load_credentials(args.user)
    if not user:
        logger.warning("未检测到有效快期账号。")
        logger.info("可通过以下安全方式提供：")
        logger.info("  1. 复制 config/tqsdk_config.example.json 为 config/tqsdk_config.json 并填入")
        logger.info("  2. 设置环境变量 TQ_USER 与 TQ_PASSWORD")
        logger.info("  3. 运行离线仿真验收测试: python scripts/fetch_futures_ranking.py --mock")
        return

    if not password:
        password = getpass.getpass("请输入快期密码（隐藏输入）: ")

    try:
        from tqsdk import TqApi, TqAuth
    except ImportError:
        logger.error("当前 Python 环境中未安装 tqsdk，请先安装: pip install tqsdk")
        sys.exit(1)

    logger.info("正在建立天勤量化安全连接...")
    broker_classes = load_broker_classification()
    manifest = {"query_date": query_date, "results": {}, "success_count": 0, "failed_count": 0}

    try:
        with TqApi(auth=TqAuth(user, password)) as api:
            logger.info("认证成功。开始安全解析目标合约与日终快照...")
            resolved_map = resolve_underlying_symbols(
                api, 
                args.commodities, 
                explicit_contracts=args.contracts, 
                timeout=args.timeout
            )

            all_dfs = []
            metrics_list = []

            for code, meta in resolved_map.items():
                contract = meta["contract"]
                logger.info(f"正在拉取 [{code}] 合约 {contract} (所属日期: {query_date})...")
                try:
                    df_contract, actual_date = fetch_and_merge_rankings(
                        api, contract, target_date=args.date, days=1
                    )
                    all_dfs.append(df_contract)

                    m = compute_metrics_for_contract(df_contract, meta, broker_classes, actual_date)
                    metrics_list.append(m)
                    manifest["results"][code] = {"status": "SUCCESS", "contract": contract, "actual_date": actual_date}
                    manifest["success_count"] += 1
                except Exception as ex:
                    logger.error(f"处理品种 [{code}] 合约 {contract} 失败: {ex}")
                    manifest["results"][code] = {"status": "FAILED", "contract": contract, "error": str(ex)}
                    manifest["failed_count"] += 1

            if all_dfs:
                df_all_ranks = pd.concat(all_dfs, ignore_index=True)
                # 正式实盘落盘（写入 数据/原始/ 和 数据/加工/）
                save_raw_table(df_all_ranks, query_date, is_mock=False)
                append_to_processed_metrics(metrics_list, query_date, is_mock=False)

                print("\n" + "="*96)
                print(f"【真实盘后席位持仓龙虎榜与集中度衍生指标汇总】 日期: {query_date}")
                print("="*96)
                df_summary = pd.DataFrame(metrics_list)[["variety", "contract", "total_oi", "cr_long_20", "cr_short_20", "b_rank", "common_count", "common_net_pos", "ind_net_change", "spec_net_change"]]
                df_summary.columns = ["品种", "主力合约", "单边OI(手)", "多头Top20(%)", "空头Top20(%)", "集中度偏度(B_rank%)", "对称重合席位数", "重合净持仓(手)", "产业净变动", "投机净变动"]
                print(df_summary.to_string(index=False))
                print("="*96 + "\n")

            if manifest["failed_count"] > 0:
                logger.warning(f"部分品种拉取失败 ({manifest['failed_count']} 个失败)，跳过全板块跨品种合成计算。")

    except Exception as exc:
        logger.error(f"TqSdk 执行过程异常终止: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    main()
