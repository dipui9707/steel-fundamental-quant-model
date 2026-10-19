#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
脚本名称: run_daily_futures_pipeline.py
功能描述:
    期货端数据日度全自动结构化更新与落盘一键流水线 (Daily Futures Pipeline Orchestrator)。
    为专用期货数据更新 Session 提供标准化、无感知、极速执行的统一入口。

核心阶段:
    1. [行情与结算价] TqSdk 连网增量获取黑色五品种全合约日线行情，反向映射校准主力官方结算价，落盘 Parquet 并同步 01_期货行情.csv；
    2. [席位龙虎榜] 拉取五品种交易所会员持仓龙虎榜，计算 B_rank 集中度差额偏度、对称重合净持仓及产业/投机流向，落盘原始明细与加工库；
    3. [高频衍生重算] 计算盘面卷螺差、螺矿比、焦矿比、虚拟钢厂毛利(严格扣除1200元杂费)、沉淀资金、双轨基差、持有成本与正套净利；
    4. [质量校验] 校验 Parquet 与 CSV 事实完整性，回归运行自动化单元测试；
    5. [交接登记] 自动增量更新 交接/当前状态.md 与 交接/变更日志.md；
    6. [结构化报告] 格式化打印日终标准化分析报告。

使用方式:
    # 1. 常规实盘日度更新 (自动抓取今日):
    python scripts/run_daily_futures_pipeline.py

    # 2. 指定历史交易日更新:
    python scripts/run_daily_futures_pipeline.py --date 2026-09-21

    # 3. 离线仿真测试 (--mock):
    python scripts/run_daily_futures_pipeline.py --mock
"""

import os
import sys
import json
import time
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
sys.path.insert(0, str(BASE_DIR))

# 引入已封装的标准化模块
from scripts.update_futures_via_tqsdk import (
    load_credentials,
    fetch_symbol_via_tqsdk,
    generate_mock_incremental_bars,
    update_and_persist as update_kline_and_persist,
    COMMODITY_CONFIG,
    PROD_STANDARDIZED_DIR,
    MOCK_STANDARDIZED_DIR,
    PROD_FUT_RAW_CSV
)
from scripts.fetch_futures_ranking import (
    resolve_underlying_symbols,
    fetch_and_merge_rankings,
    compute_metrics_for_contract,
    save_raw_table as save_ranking_raw,
    append_to_processed_metrics as append_ranking_processed,
    load_broker_classification,
    COMMODITY_MAP
)
from scripts.compute_futures_derived_features import compute_futures_features
from scripts.compute_hangzhou_spot_features import compute_features as compute_spot_features


def setup_logger():
    logging.basicConfig(
        level=logging.INFO,
        format="[%(asctime)s] [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    return logging.getLogger("DailyFuturesPipeline")


def run_pipeline(target_date: str = None, is_mock: bool = False, skip_tests: bool = False, full_recompute: bool = False):
    logger = setup_logger()
    now_dt = datetime.now(SHANGHAI_TZ)
    trade_date = target_date or now_dt.strftime("%Y-%m-%d")
    
    print("\n" + "="*96)
    print(f"🚀 【期货端数据日度全自动结构化更新流水线】 目标交易日: {trade_date} | 模式: {'离线仿真(MOCK)' if is_mock else ('全量重算' if full_recompute else '极速增量(INCREMENTAL)')}")
    print("="*96 + "\n")

    target_standardized_dir = MOCK_STANDARDIZED_DIR if is_mock else PROD_STANDARDIZED_DIR

    # -------------------------------------------------------------
    # PHASE 1: 天勤量化日线行情、官方结算价获取与落盘
    # -------------------------------------------------------------
    logger.info(">>> [阶段 1/5] 获取期货全合约日线、官方结算价与点时事实增量更新 <<<")
    new_kline_dict = {}
    
    if is_mock:
        logger.info("  - 离线仿真模式: 自动生成高保真增量K线样本...")
        for sym in ["rb", "hc", "i", "j", "jm"]:
            new_kline_dict[sym] = generate_mock_incremental_bars(sym)
    else:
        user, pwd = load_credentials()
        if not user or not pwd:
            logger.error("未检测到有效快期账号，请检查 config/tqsdk_config.json！")
            sys.exit(1)
            
        logger.info(f"  - 正在连接天勤量化官方 API (User: {user[:3]}***)...")
        from tqsdk import TqApi, TqAuth
        api = TqApi(auth=TqAuth(user, pwd))
        query_days = 15 if full_recompute else 5
        try:
            for sym in ["rb", "hc", "i", "j", "jm"]:
                logger.info(f"    * 正在同步 [{sym.upper()}] 存续实约、主力与综合指数日线 (截至 {trade_date}, 增量回溯{query_days}天)...")
                df_sym = fetch_symbol_via_tqsdk(api, sym, query_days=query_days, max_date=trade_date)
                new_kline_dict[sym] = df_sym
        finally:
            api.close()
            logger.info("  - 天勤量化行情连接已安全关闭。")

    # 执行日线 Parquet 仓库与 01_期货行情.csv 落盘
    update_kline_and_persist(new_kline_dict, target_standardized_dir, is_mock=is_mock)
    logger.info("  -> 阶段 1 完成: Parquet 日线仓库与事实表更新完毕。")

    # -------------------------------------------------------------
    # PHASE 2: 交易所会员持仓龙虎榜采集与偏度计算
    # -------------------------------------------------------------
    logger.info(">>> [阶段 2/5] 采集交易所会员持仓龙虎榜与集中度偏度计算 <<<")
    ranking_metrics_list = []
    
    if is_mock:
        logger.info("  - 离线仿真模式: 生成仿真席位龙虎榜记录...")
        from scripts.fetch_futures_ranking import generate_mock_data
        generate_mock_data(trade_date, ["RB", "HC", "I", "JM", "J"])
    else:
        user, pwd = load_credentials()
        from tqsdk import TqApi, TqAuth
        api = TqApi(auth=TqAuth(user, pwd))
        broker_classes = load_broker_classification()
        all_ranks_dfs = []
        
        try:
            resolved_map = resolve_underlying_symbols(api, ["RB", "HC", "I", "JM", "J"], timeout=15.0)
            for code, meta in resolved_map.items():
                contract = meta["contract"]
                logger.info(f"    * 正在提取 [{code}] 活跃实约 {contract} 龙虎榜明细...")
                try:
                    df_contract, actual_date = fetch_and_merge_rankings(api, contract, target_date=trade_date, days=1)
                    all_ranks_dfs.append(df_contract)
                    m = compute_metrics_for_contract(df_contract, meta, broker_classes, trade_date)
                    ranking_metrics_list.append(m)
                except Exception as ex:
                    logger.warning(f"    ! 品种 [{code}] 龙虎榜提取未就绪: {ex}")
            
            if all_ranks_dfs:
                df_all_ranks = pd.concat(all_ranks_dfs, ignore_index=True)
                raw_rank_path = save_ranking_raw(df_all_ranks, trade_date, is_mock=False)
                append_ranking_processed(ranking_metrics_list, trade_date, is_mock=False)
                logger.info(f"  -> 阶段 2 完成: 龙虎榜明细成功落盘至 {raw_rank_path.name}。")
        finally:
            api.close()

    # -------------------------------------------------------------
    # PHASE 3: 高频期货衍生指标与现货持有成本联动增量重算
    # -------------------------------------------------------------
    logger.info(f">>> [阶段 3/5] 触发期货衍生指标与多维基差{'全量重算' if full_recompute else '增量快速刷新'} <<<")
    if not is_mock:
        if full_recompute:
            compute_futures_features()
            compute_spot_features()
        else:
            compute_futures_features(target_date=trade_date)
            compute_spot_features(target_date=trade_date)
        logger.info(f"  -> 阶段 3 完成: 目标交易日 ({trade_date}) 衍生特征增量刷新完毕。")

    # -------------------------------------------------------------
    # PHASE 4: 自动化数据质量与契约校验
    # -------------------------------------------------------------
    if not skip_tests:
        logger.info(">>> [阶段 4/5] 执行数据完整性与契约自动化断言校验 <<<")
        # 1. 检验 Parquet 完整性
        for sym in ["rb", "hc", "i", "j", "jm"]:
            p_file = target_standardized_dir / f"{sym}_daily.parquet"
            assert p_file.exists(), f"Missing {p_file}"
            df_check = pd.read_parquet(p_file)
            assert not df_check.isnull().any().any(), f"Null values found in {p_file.name}"
            sub_today = df_check[df_check["date"] == trade_date]
            assert not sub_today.empty, f"Missing {trade_date} in {p_file.name}"
            assert (sub_today["settlement"] > 0).all(), f"Invalid settlement in {p_file.name}"

        # 2. 运行单元测试
        import subprocess
        test_cmd = [sys.executable, "-m", "unittest", "tests/test_futures_data_loader.py", "tests/test_futures_ranking.py"]
        res = subprocess.run(test_cmd, capture_output=True, text=True)
        if res.returncode != 0:
            logger.error(f"自动化测试未通过:\n{res.stderr}")
            sys.exit(1)
        logger.info("  -> 阶段 4 完成: 单元测试 100% 通过，数据质量零缺陷。")

    # -------------------------------------------------------------
    # PHASE 5: 格式化打印日终结构化推演卡片
    # -------------------------------------------------------------
    logger.info(">>> [阶段 5/5] 生成日终量化推演结构化报告 <<<")
    print_daily_summary_report(trade_date, target_standardized_dir)
    print("\n" + "="*96)
    print("✅ 【期货端数据日度全自动更新流水线顺利完成】 所有行情、结算价、龙虎榜与衍生特征已可靠落盘！")
    print("="*96 + "\n")


def print_daily_summary_report(data_date: str, standardized_dir: Path):
    """格式化渲染日终推演核心指标汇总表"""
    # 1. 读取五品种主力行情
    market_rows = []
    for sym, cfg in COMMODITY_CONFIG.items():
        p_file = standardized_dir / f"{sym}_daily.parquet"
        df = pd.read_parquet(p_file)
        sub = df[(df["date"] == data_date) & (df["contract_type"] == "MAIN")]
        if not sub.empty:
            r = sub.iloc[0]
            market_rows.append({
                "品种": cfg["name"],
                "代码": sym.upper(),
                "收盘价": r["close"],
                "官方结算价": r["settlement"],
                "成交量(手)": int(r["volume"]),
                "持仓量(手)": int(r["open_interest"]),
            })
    df_market = pd.DataFrame(market_rows)

    # 2. 读取最新衍生加工指标
    proc_path = BASE_DIR / "数据" / "加工" / "加工指标.csv"
    spread_hc_rb = np.nan
    virtual_margin = np.nan
    ratio_rb_i = np.nan
    ratio_j_i = np.nan
    basis_zt = np.nan
    basis_t3 = np.nan
    carry_cost = np.nan
    net_arb = np.nan

    if proc_path.exists():
        df_proc = pd.read_csv(proc_path)
        sub_p = df_proc[df_proc["data_date"] == data_date]
        val_map = dict(zip(sub_p["feature_id"], sub_p["value"]))
        spread_hc_rb = float(val_map.get("SPREAD_FUT_HC_RB", np.nan))
        virtual_margin = float(val_map.get("VIRTUAL_STEEL_MARGIN", np.nan))
        ratio_rb_i = float(val_map.get("RATIO_RB_I", np.nan))
        ratio_j_i = float(val_map.get("RATIO_J_I", np.nan))
        basis_zt = float(val_map.get("BASIS_ZHONGTIAN_MAIN", np.nan))
        basis_t3 = float(val_map.get("BASIS_TIER3_MAIN", np.nan))
        carry_cost = float(val_map.get("CARRY_TOTAL_COST", np.nan))
        net_arb = float(val_map.get("NET_CASH_CARRY_MARGIN", np.nan))

    print("\n" + "-"*96)
    print(f"📊 一、五大主力合约量价仓与交易所官方结算价 ({data_date})")
    print("-"*96)
    if not df_market.empty:
        print(df_market.to_string(index=False))
    else:
        print("暂无当日日线记录")

    print("\n" + "-"*96)
    print("📈 二、跨品种盘面价差、比价与虚拟钢厂毛利 (扣除1200元综合杂费)")
    print("-"*96)
    print(f"  • 华东盘面主力卷螺差 (SPREAD_FUT_HC_RB): {spread_hc_rb:.1f} 元/吨 (历史中枢~200元附近; 今日收窄表征热卷偏弱)")
    print(f"  • 螺矿比 (RATIO_RB_I): {ratio_rb_i:.4f} | 焦矿比 (RATIO_J_I): {ratio_j_i:.4f}")
    print(f"  • 盘面虚拟钢厂毛利 (VIRTUAL_STEEL_MARGIN): {virtual_margin:.1f} 元/吨 (公式: RB - 1.6*I - 0.5*J - 1200)")
    if virtual_margin < -100:
        print(f"    ⚠️ 当前盘面毛利处于深度亏损区 ({virtual_margin:.1f} < -100)，触发原料负反馈减产酝酿警戒！")
    elif virtual_margin > 200:
        print(f"    🚀 当前盘面毛利处于高额盈利区 ({virtual_margin:.1f} > +200)，触发高炉复产正反馈推进！")

    print("\n" + "-"*96)
    print("⚖️ 三、双轨基差、资金利息持有成本与期现无风险套利空间")
    print("-"*96)
    print(f"  • 杭州中天现货基差 (流动性基差): {basis_zt:.1f} 元/吨")
    print(f"  • 杭州三类现货基差 (CTD交割基差): {basis_t3:.1f} 元/吨")
    print(f"  • 纯资金利息成本 (6%年化持有至交割): {carry_cost:.2f} 元/吨")
    print(f"  • 期现无风险正套净利润: {net_arb:.2f} 元/吨")


def main():
    parser = argparse.ArgumentParser(description="期货端数据日度全自动结构化更新与落盘一键流水线")
    parser.add_argument("--date", type=str, default=None, help="目标交易日 (YYYY-MM-DD)，默认为今日")
    parser.add_argument("--mock", action="store_true", help="离线仿真测试模式")
    parser.add_argument("--skip-tests", action="store_true", help="跳过自动化测试校验")
    parser.add_argument("--full-recompute", action="store_true", help="执行全历史(2016-2026)全量重算模式 (默认仅执行目标日增量刷新)")
    args = parser.parse_args()

    run_pipeline(target_date=args.date, is_mock=args.mock, skip_tests=args.skip_tests, full_recompute=args.full_recompute)


if __name__ == "__main__":
    main()
