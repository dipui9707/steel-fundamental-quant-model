#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: update_futures_via_tqsdk.py
功能描述:
    基于天勤量化 (TqSdk) 接口增量获取黑色系五大核心品种（RB, HC, I, JM, J）
    最新日线行情（包含连续主力 main、全市场指数 index 及存续各月份实约），
    标准化清洗后增量更新至本地 Parquet 数据仓库，并自动重新触发高频特征计算。

使用方式:
    1. 使用真实快期账号在线更新:
       python scripts/update_futures_via_tqsdk.py --tq-user <账号> --tq-password <密码>
       或者配置 config/tqsdk_config.json 后直接运行:
       python scripts/update_futures_via_tqsdk.py
    2. 离线仿真/管道测试模式 (--mock):
       python scripts/update_futures_via_tqsdk.py --mock
"""

import os
import sys
import json
import time
import math
import argparse
import logging
from datetime import datetime, date, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

# 时区设定
SHANGHAI_TZ = ZoneInfo("Asia/Shanghai")

# 基础目录
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "tqsdk_config.json"
PROD_STANDARDIZED_DIR = BASE_DIR / "数据" / "原始" / "期货合约全量日线" / "standardized"
MOCK_STANDARDIZED_DIR = BASE_DIR / "研究" / "mock_data" / "期货合约全量日线" / "standardized"
PROD_FUT_RAW_CSV = BASE_DIR / "数据" / "原始" / "01_期货行情.csv"

# 引入已有的数据加工管道
sys.path.insert(0, str(BASE_DIR))
from scripts.compute_futures_derived_features import compute_futures_features
from scripts.compute_hangzhou_spot_features import compute_features as compute_spot_features

# 品种配置映射
COMMODITY_CONFIG = {
    "rb": {"name": "螺纹钢", "exchange": "SHFE", "multiplier": 10, "default_margin": 0.08},
    "hc": {"name": "热轧卷板", "exchange": "SHFE", "multiplier": 10, "default_margin": 0.08},
    "i":  {"name": "铁矿石", "exchange": "DCE",  "multiplier": 100, "default_margin": 0.12},
    "j":  {"name": "焦炭",   "exchange": "DCE",  "multiplier": 100, "default_margin": 0.15},
    "jm": {"name": "焦煤",   "exchange": "DCE",  "multiplier": 60,  "default_margin": 0.15},
}

# 01_期货行情.csv 变量映射
FUT_VARIABLE_SPECS = {
    ("rb", "close"): ("F06", "元/吨", "RB主力合约收盘价", "活跃连续/主连"),
    ("rb", "volume"): ("F07", "手", "RB主力合约成交量", "活跃连续/主连"),
    ("rb", "open_interest"): ("F08", "手", "RB主力合约持仓量", "单边持仓"),
    ("hc", "close"): ("F09", "元/吨", "HC主力合约收盘价", "活跃连续/主连"),
    ("i", "close"): ("F12", "元/吨", "I主力合约收盘价", "活跃连续/主连"),
    ("j", "close"): ("F18", "元/吨", "J主力合约收盘价", "活跃连续/主连"),
    ("jm", "close"): ("F21", "元/吨", "JM主力合约收盘价", "活跃连续/主连"),
}


def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return logging.getLogger("TqFuturesUpdater")


def load_credentials(cli_user=None, cli_pwd=None):
    """加载天勤凭据: CLI 参数 > 环境变量 > 配置文件"""
    user = cli_user or os.environ.get("TQ_USER")
    pwd = cli_pwd or os.environ.get("TQ_PASSWORD")
    
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


def parse_trading_day(dt_nano: int) -> str:
    """根据纳秒时间戳精准换算其所属的中国期货交易所交易日 (YYYY-MM-DD)"""
    try:
        from tqsdk import datetime as td, tafunc
        t_day_nano = td._get_trading_day_from_timestamp(dt_nano)
        t_day_dt = tafunc.time_to_datetime(t_day_nano)
        return t_day_dt.strftime("%Y-%m-%d")
    except Exception:
        # 回退使用标准秒转换
        sec = dt_nano // 10**9
        dt = datetime.fromtimestamp(sec, tz=SHANGHAI_TZ)
        if dt.hour >= 18:
            dt += timedelta(days=1)
        while dt.weekday() >= 5:
            dt += timedelta(days=(7 - dt.weekday()))
        return dt.strftime("%Y-%m-%d")


def fetch_symbol_via_tqsdk(api, symbol: str, query_days: int = 15, max_date: str = None) -> pd.DataFrame:
    """
    从 TqSdk 实时拉取指定品种的连续主力、指数与有效实约日线数据
    """
    from tqsdk import tafunc
    cfg = COMMODITY_CONFIG[symbol]
    exch = cfg["exchange"]
    sym_upper = symbol.upper()
    sym_lower = symbol.lower()
    
    # 1. 获取该品种当前全部未到期的真实合约
    logging.info(f"[{sym_upper}] 正在查询活跃合约列表...")
    unexpired_contracts = api.query_quotes(ins_class="FUTURE", exchange_id=exch, product_id=sym_lower, expired=False)
    if not unexpired_contracts:
        # 兼容部分交易所大小写
        unexpired_contracts = api.query_quotes(ins_class="FUTURE", product_id=sym_lower, expired=False)
    logging.info(f"[{sym_upper}] 发现 {len(unexpired_contracts)} 个存续实约")

    # 目标更新代码列表: 主力连续 + 综合指数 + 存续实约
    target_tasks = [
        {"tq_code": f"KQ.m@{exch}.{sym_lower}", "code": "main", "type": "MAIN"},
        {"tq_code": f"KQ.i@{exch}.{sym_lower}", "code": "index", "type": "INDEX"},
    ]
    for c in unexpired_contracts:
        # 提取月份代码, 如 SHFE.rb2510 -> 2510
        code = c.split(".")[-1][len(sym_lower):]
        target_tasks.append({
            "tq_code": c,
            "code": code,
            "type": "SPECIFIC"
        })

    # 2. 批量并发订阅日线 (并发加载提升10倍拉取速度)
    task_kline_pairs = []
    for task in target_tasks:
        try:
            kl = api.get_kline_serial(task["tq_code"], duration_seconds=86400, data_length=query_days)
            task_kline_pairs.append((task, kl))
        except Exception as e:
            logging.warning(f"  - {task['tq_code']} 订阅K线异常: {e}")

    # 统一并发等待所有合约日线数据推送就绪
    deadline = time.time() + 15.0
    while time.time() < deadline:
        api.wait_update(deadline=deadline)
        if all(not kl.empty and not pd.isna(kl.iloc[-1]["close"]) for _, kl in task_kline_pairs):
            break

    rows = []
    for task, klines in task_kline_pairs:
        tq_code = task["tq_code"]
        code = task["code"]
        c_type = task["type"]
        
        try:
            if klines.empty or pd.isna(klines.iloc[-1]["close"]):
                logging.warning(f"  - {tq_code} 获取K线超时或空数据，跳过")
                continue

            # 查询结算价
            settle_map = {}
            try:
                settle_df = api.query_symbol_settlement(tq_code, days=query_days)
                if settle_df is not None and not settle_df.empty:
                    for _, s_row in settle_df.iterrows():
                        # YYYYMMDD -> YYYY-MM-DD
                        dt_str = str(s_row["datetime"])
                        if len(dt_str) == 8:
                            dt_fmt = f"{dt_str[:4]}-{dt_str[4:6]}-{dt_str[6:8]}"
                            settle_map[dt_fmt] = float(s_row["settlement"])
            except Exception as e:
                logging.debug(f"  - {tq_code} 查询历史结算价未就绪: {e}")

            # 解析K线每一行
            for _, k in klines.iterrows():
                if pd.isna(k["close"]):
                    continue
                dt_nano = int(k["datetime"])
                trade_date = parse_trading_day(dt_nano)
                
                # 过滤未完工的盘中交易日 (如当前正在进行的夜盘归属下一交易日)
                if max_date and trade_date > max_date:
                    continue
                
                open_p = float(k["open"])
                high_p = float(k["high"])
                low_p = float(k["low"])
                close_p = float(k["close"])
                vol = float(k["volume"])
                oi = float(k["close_oi"])
                
                # 结算价匹配，若无则使用收盘价兜底
                settle_p = settle_map.get(trade_date, close_p)
                
                delivery_month = code[-2:] if len(code) == 4 and code.isdigit() else ""
                full_sym = f"{exch}.{sym_lower}_{code}" if c_type in ("MAIN", "INDEX") else f"{exch}.{sym_lower}{code}"

                rows.append({
                    "date": trade_date,
                    "open": open_p,
                    "high": high_p,
                    "low": low_p,
                    "close": close_p,
                    "volume": vol,
                    "open_interest": oi,
                    "settlement": settle_p,
                    "contract_code": code,
                    "delivery_month": delivery_month,
                    "symbol": sym_lower,
                    "variety_name": cfg["name"],
                    "exchange": exch,
                    "multiplier": cfg["multiplier"],
                    "default_margin_rate": cfg["default_margin"],
                    "full_symbol": full_sym,
                    "contract_type": c_type,
                })
        except Exception as e:
            logging.warning(f"  - 拉取 {tq_code} 异常: {e}")

    df = pd.DataFrame(rows)

    # 自动校准 MAIN 主连合约官方结算价:
    # 提取当日匹配的主力具体实约的真实交易所官方结算价反填写入 MAIN
    if not df.empty and "MAIN" in df["contract_type"].values:
        specific_df = df[df["contract_type"] == "SPECIFIC"]
        main_mask = df["contract_type"] == "MAIN"
        active_by_date = {}
        for dt, group in specific_df.groupby("date"):
            active_by_date[dt] = group
            
        corrected_count = 0
        for idx in df[main_mask].index:
            dt = df.loc[idx, "date"]
            if dt in active_by_date:
                spec_dt = active_by_date[dt]
                m_close = df.loc[idx, "close"]
                m_oi = df.loc[idx, "open_interest"]
                cand = spec_dt[(spec_dt["close"] == m_close) & (spec_dt["open_interest"] == m_oi)]
                if cand.empty:
                    cand = spec_dt[spec_dt["close"] == m_close]
                if cand.empty:
                    cand = spec_dt.sort_values("open_interest", ascending=False)
                real_settle = float(cand.iloc[0]["settlement"])
                if df.loc[idx, "settlement"] != real_settle:
                    df.loc[idx, "settlement"] = real_settle
                    corrected_count += 1
        if corrected_count > 0:
            logging.info(f"[{sym_upper}] 成功根据对应实约校准主连 (MAIN) 官方结算价: {corrected_count} 个交易日")

    logging.info(f"[{sym_upper}] 本次从 TqSdk 提取 {len(df)} 条日线记录")
    return df


def generate_mock_incremental_bars(symbol: str) -> pd.DataFrame:
    """
    离线模拟生成增量最新交易日日线数据，用于测试管道合并与特征重算
    """
    file_path = PROD_STANDARDIZED_DIR / f"{symbol}_daily.parquet"
    existing = pd.read_parquet(file_path)
    latest_date = existing["date"].max()
    next_date = (datetime.fromisoformat(latest_date) + timedelta(days=1)).strftime("%Y-%m-%d")
    
    # 提取最近一天的所有合约作为模板
    sub = existing[existing["date"] == latest_date].copy()
    sub["date"] = next_date
    # 微调价格和成交量模拟微小变动
    np.random.seed(hash(symbol) % 10000)
    fluct = np.random.uniform(-0.01, 0.01, size=len(sub))
    sub["close"] = (sub["close"] * (1 + fluct)).round(1)
    sub["open"] = sub["close"]
    sub["high"] = (sub["close"] * 1.005).round(1)
    sub["low"] = (sub["close"] * 0.995).round(1)
    sub["settlement"] = sub["close"]
    sub["volume"] = (sub["volume"] * np.random.uniform(0.9, 1.1)).round(0)
    sub["open_interest"] = (sub["open_interest"] * np.random.uniform(0.95, 1.05)).round(0)
    
    return sub


def update_and_persist(new_data_dict: dict, target_dir: Path, is_mock: bool = False):
    """
    将获取的新日线数据与现有标准化 Parquet 仓库合并去重并落盘，并同步点时事实表
    """
    target_dir.mkdir(parents=True, exist_ok=True)
    all_symbols_dfs = []
    total_added_or_updated = 0

    for symbol, new_df in new_data_dict.items():
        file_path = target_dir / f"{symbol}_daily.parquet"
        if file_path.exists():
            old_df = pd.read_parquet(file_path)
        else:
            base_file = PROD_STANDARDIZED_DIR / f"{symbol}_daily.parquet"
            old_df = pd.read_parquet(base_file) if base_file.exists() else pd.DataFrame()

        if new_df is None or new_df.empty:
            logging.info(f"[{symbol.upper()}] 无新增数据，保留既有 {len(old_df)} 条记录")
            all_symbols_dfs.append(old_df)
            continue

        # 合并去重: 以 date + contract_code 为主键，保留最新
        combined = pd.concat([old_df, new_df], ignore_index=True)
        before_cnt = len(old_df)
        combined = combined.drop_duplicates(subset=["date", "contract_code"], keep="last")
        combined = combined.sort_values(by=["date", "contract_type", "contract_code"]).reset_index(drop=True)
        
        added_cnt = len(combined) - before_cnt
        total_added_or_updated += len(new_df)
        
        # 写回单品种 parquet
        combined.to_parquet(file_path, index=False, engine="pyarrow", compression="snappy")
        logging.info(f"[{symbol.upper()}] 成功落盘更新 {file_path.name}: 现有总行数 {len(combined)} (新增净增 {added_cnt} 行)")
        all_symbols_dfs.append(combined)

    # 重新合并全量 parquet
    if all_symbols_dfs:
        full_df = pd.concat(all_symbols_dfs, ignore_index=True)
        full_df = full_df.sort_values(by=["date", "symbol", "contract_type", "contract_code"]).reset_index(drop=True)
        combined_file = target_dir / "futures_all_daily.parquet"
        full_df.to_parquet(combined_file, index=False, engine="pyarrow", compression="snappy")
        logging.info(f"成功同步更新全量合并数据集: {combined_file.name} (总行数: {len(full_df)})")

    # 若为实盘生产更新，同步写入 数据/原始/01_期货行情.csv
    if not is_mock and PROD_FUT_RAW_CSV.exists():
        raw_df = pd.read_csv(PROD_FUT_RAW_CSV)
        now_ts = datetime.now(SHANGHAI_TZ).isoformat()
        new_raw_rows = []
        for sym, sym_df in new_data_dict.items():
            if sym_df is None or sym_df.empty:
                continue
            main_rows = sym_df[sym_df["contract_type"] == "MAIN"]
            spec_rows = sym_df[sym_df["contract_type"] == "SPECIFIC"]
            for _, m_row in main_rows.iterrows():
                m_dt = m_row["date"]
                spec_dt = spec_rows[spec_rows["date"] == m_dt]
                cand = spec_dt[(spec_dt["close"] == m_row["close"]) & (spec_dt["open_interest"] == m_row["open_interest"])]
                if cand.empty:
                    cand = spec_dt.sort_values("open_interest", ascending=False)
                actual_contract = cand.iloc[0]["full_symbol"] if not cand.empty else m_row["full_symbol"]
                
                cfg = COMMODITY_CONFIG[sym]
                exch = cfg["exchange"]
                src = f"{exch}/TqSdk"
                
                for field in ["close", "volume", "open_interest"]:
                    key = (sym, field)
                    if key in FUT_VARIABLE_SPECS:
                        var_id, unit, v_name, scope = FUT_VARIABLE_SPECS[key]
                        val = float(m_row[field])
                        obs_id = f"OBS_TQ_{var_id}_{m_dt.replace('-', '')}"
                        new_raw_rows.append({
                            "observation_id": obs_id,
                            "variable_id": var_id,
                            "data_date": m_dt,
                            "period_start": m_dt,
                            "period_end": m_dt,
                            "source_published_at": f"{m_dt}T17:00:00+08:00",
                            "first_seen_at": now_ts,
                            "available_date": f"{m_dt}T17:00:00+08:00",
                            "recorded_at": now_ts,
                            "availability_basis": "LIVE_RECEIPT",
                            "information_set_mode": "LIVE_RECORDED",
                            "value": val,
                            "unit": unit,
                            "source": src,
                            "source_ref": f"TQSDK_{actual_contract}_DAILY",
                            "frequency": "日频",
                            "scope": scope,
                            "contract": actual_contract,
                            "revision_id": "REV_0",
                            "supersedes": "",
                            "quality_flag": "VALID",
                            "note": f"{m_dt}真实行情:{cfg['name']}主力{field}"
                        })
        if new_raw_rows:
            new_raw_df = pd.DataFrame(new_raw_rows)
            combined_raw = pd.concat([raw_df, new_raw_df], ignore_index=True)
            combined_raw = combined_raw.drop_duplicates(subset=["variable_id", "data_date"], keep="last")
            combined_raw.to_csv(PROD_FUT_RAW_CSV, index=False, encoding="utf-8-sig")
            logging.info(f"成功同步更新点时事实表: {PROD_FUT_RAW_CSV.name} (写入 {len(new_raw_df)} 条记录，总行数: {len(combined_raw)})")


def main():
    parser = argparse.ArgumentParser(description="天勤量化 (TqSdk) 黑色五品种期货全合约日线更新落盘管道")
    parser.add_argument("--tq-user", type=str, default=None, help="天勤快期用户名/手机号")
    parser.add_argument("--tq-password", type=str, default=None, help="天勤快期密码")
    parser.add_argument("--symbols", type=str, default="rb,hc,i,j,jm", help="待更新的品种列表，英文逗号分隔")
    parser.add_argument("--days", type=int, default=15, help="请求的历史天数跨度，默认15天")
    parser.add_argument("--max-date", type=str, default=None, help="最大允许落盘交易日 (YYYY-MM-DD)，默认为今日(过滤夜盘未完工K线)")
    parser.add_argument("--mock", action="store_true", help="离线测试模式: 使用本地高仿真增量数据校验合并与落盘(输出至研究/mock_data/)")
    parser.add_argument("--skip-calc", action="store_true", help="跳过特征自动重算")
    args = parser.parse_args()

    logger = setup_logger()
    logger.info("=== 启动天勤量化 (TqSdk) 期货数据更新落盘任务 ===")

    symbols = [s.strip().lower() for s in args.symbols.split(",") if s.strip().lower() in COMMODITY_CONFIG]
    if not symbols:
        logger.error("未指定有效的黑色品种！支持: rb, hc, i, j, jm")
        sys.exit(1)

    max_date = args.max_date or datetime.now(SHANGHAI_TZ).strftime("%Y-%m-%d")
    new_data_dict = {}
    target_dir = MOCK_STANDARDIZED_DIR if args.mock else PROD_STANDARDIZED_DIR

    if args.mock:
        logger.info(f">>> 当前为 --mock 仿真测试模式，将模拟增量数据并隔离落盘至: {target_dir} <<<")
        for sym in symbols:
            mock_df = generate_mock_incremental_bars(sym)
            new_data_dict[sym] = mock_df
    else:
        user, pwd = load_credentials(args.tq_user, args.tq_password)
        if not user or not pwd:
            logger.error("未检测到有效的快期账号凭据！")
            print("\n" + "="*70)
            print("【配置指引】天勤量化 (TqSdk) 需要注册免费快期账户以连接交易所行情服务器：")
            print("1. 访问 https://account.shinnytech.com/ 免费注册一个快期账号")
            print("2. 在本地创建或编辑 config/tqsdk_config.json：")
            print('   {\n     "tq_user": "您的手机号或用户名",\n     "tq_password": "您的密码"\n   }')
            print("3. 或者在运行脚本时通过参数直接传入：")
            print("   python scripts/update_futures_via_tqsdk.py --tq-user <账号> --tq-password <密码>")
            print("4. 若仅需离线验证管道逻辑，可添加 --mock 参数：")
            print("   python scripts/update_futures_via_tqsdk.py --mock")
            print("="*70 + "\n")
            sys.exit(1)

        logger.info(f"正在连接天勤量化行情服务器 (User: {user[:3]}***)...")
        from tqsdk import TqApi, TqAuth
        api = TqApi(auth=TqAuth(user, pwd))
        try:
            for sym in symbols:
                df_sym = fetch_symbol_via_tqsdk(api, sym, query_days=args.days, max_date=max_date)
                new_data_dict[sym] = df_sym
        finally:
            api.close()
            logger.info("天勤量化连接已安全关闭。")

    # 执行更新落盘
    logger.info(f">>> 正在执行 Parquet 仓库增量合并落盘 (目标目录: {target_dir}) <<<")
    update_and_persist(new_data_dict, target_dir, is_mock=args.mock)

    # 重新触发高频衍生特征计算 (仅在生产模式下自动重算)
    if not args.mock and not args.skip_calc:
        logger.info(">>> 自动重新触发期货衍生指标与多维基差特征计算 <<<")
        compute_futures_features()
        logger.info(">>> 自动重新触发微观现货衍生指标与期现持有成本重算 <<<")
        compute_spot_features()

    logger.info("=== 天勤量化 (TqSdk) 期货数据更新落盘任务顺利完成 ===")


if __name__ == "__main__":
    main()
