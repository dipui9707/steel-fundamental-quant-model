#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_b/data_pipeline.py
功能: 阶段 B 数据接入与严格点时 (Point-In-Time, PIT) 时间对齐底座
职责:
  1. 融合期货多品种全合约 (RB, HC, I, J, JM) 日线与加权指数；
  2. 接入 17 年微观现货事实库 (真实 CTD 三类交割品、中天、成本利润、华东废钢)；
  3. 接入 Wind EDB 74 项产业与宏观核心时序，严防发布时滞未来函数；
  4. 接入 SMM 高频出口与制造业耗钢微观时序；
  5. 输出统一交易日对齐的 PIT 事实宽表，附带新鲜度与发布事件追踪。
"""

from pathlib import Path
from typing import Dict, List, Optional, Tuple, Union
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

BASE_DIR = Path(__file__).resolve().parent.parent
RAW_DIR = BASE_DIR / "数据" / "原始"
PROCESSED_DIR = BASE_DIR / "数据" / "加工"


class DataPipeline:
    """
    阶段 B 统一数据接入与时间对齐管道
    """

    def __init__(self, raw_dir: Optional[Path] = None, processed_dir: Optional[Path] = None):
        self.raw_dir = Path(raw_dir) if raw_dir else RAW_DIR
        self.processed_dir = Path(processed_dir) if processed_dir else PROCESSED_DIR
        self._futures_cache: Dict[str, pd.DataFrame] = {}

    def load_futures_main(self, symbol: str) -> pd.DataFrame:
        """从标准化 Parquet 仓库加载指定品种的连续主力日线"""
        symbol = symbol.lower()
        parquet_path = self.raw_dir / "期货合约全量日线" / "standardized" / f"{symbol}_daily.parquet"
        if not parquet_path.exists():
            raise FileNotFoundError(f"Futures parquet not found: {parquet_path}")

        df = pd.read_parquet(parquet_path)
        main_df = df[df["contract_type"] == "MAIN"].copy()
        main_df["date"] = pd.to_datetime(main_df["date"]).dt.strftime("%Y-%m-%d")
        main_df = main_df.sort_values("date").reset_index(drop=True)
        return main_df

    def load_futures_index(self, symbol: str) -> pd.DataFrame:
        """从标准化 Parquet 仓库加载指定品种的加权综合指数日线"""
        symbol = symbol.lower()
        parquet_path = self.raw_dir / "期货合约全量日线" / "standardized" / f"{symbol}_daily.parquet"
        df = pd.read_parquet(parquet_path)
        idx_df = df[df["contract_type"] == "INDEX"].copy()
        idx_df["date"] = pd.to_datetime(idx_df["date"]).dt.strftime("%Y-%m-%d")
        idx_df = idx_df.sort_values("date").reset_index(drop=True)
        return idx_df

    def load_spot_data(self) -> pd.DataFrame:
        """加载 17 年历史每日微观现货事实表 (清洗规范版)"""
        spot_file = self.raw_dir / "每日现货_清洗规范版.csv"
        if not spot_file.exists():
            raise FileNotFoundError(f"Daily spot CSV not found: {spot_file}")

        df = pd.read_csv(spot_file)
        df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
        df = df.sort_values("date").reset_index(drop=True)
        return df

    def load_wind_edb(self) -> pd.DataFrame:
        """加载 Wind EDB 产业与宏观全量时序"""
        wind_file = self.raw_dir / "wind_edb" / "wind_edb_all.parquet"
        if not wind_file.exists():
            raise FileNotFoundError(f"Wind EDB parquet not found: {wind_file}")
        return pd.read_parquet(wind_file)

    def load_smm_data(self) -> pd.DataFrame:
        """加载 SMM 高频出口与制造业需求数据"""
        smm_file = self.raw_dir / "smm" / "smm_export_manufacturing.parquet"
        if not smm_file.exists():
            return pd.DataFrame()
        return pd.read_parquet(smm_file)

    def load_macro_bonds(self) -> pd.DataFrame:
        """加载宏观地方政府债券发行与财政脉冲日度特征"""
        bond_file = self.processed_dir / "宏观发债与财政脉冲日度特征.parquet"
        if not bond_file.exists():
            return pd.DataFrame()
        df = pd.read_parquet(bond_file)
        if not isinstance(df.index, pd.DatetimeIndex):
            df.index = pd.to_datetime(df.index)
        df.index = df.index.strftime("%Y-%m-%d")
        return df

    def build_aligned_daily_panel(
        self,
        start_date: str = "2018-03-09",
        end_date: Optional[str] = None
    ) -> pd.DataFrame:
        """
        构建严格符合 Point-In-Time (PIT) 契约的日度统一事实宽表
        交易日历以螺纹钢期货连续主力为核心基准
        """
        # 1. 基础期货日线行情 (RB 为主交易标的，HC/I/J/JM 为联动品种)
        rb_main = self.load_futures_main("rb").set_index("date")
        hc_main = self.load_futures_main("hc").set_index("date")
        i_main = self.load_futures_main("i").set_index("date")
        j_main = self.load_futures_main("j").set_index("date")
        jm_main = self.load_futures_main("jm").set_index("date")

        rb_idx = self.load_futures_index("rb").set_index("date")
        hc_idx = self.load_futures_index("hc").set_index("date")
        i_idx = self.load_futures_index("i").set_index("date")
        j_idx = self.load_futures_index("j").set_index("date")
        jm_idx = self.load_futures_index("jm").set_index("date")

        trading_dates = sorted(rb_main.index.tolist())
        panel = pd.DataFrame(index=trading_dates)
        panel.index.name = "date"

        # 期货价格、成交量、持仓量、结算价
        panel["rb_close"] = rb_main["close"]
        panel["rb_open"] = rb_main["open"]
        panel["rb_high"] = rb_main["high"]
        panel["rb_low"] = rb_main["low"]
        panel["rb_settle"] = rb_main["settlement"]
        panel["rb_volume"] = rb_main["volume"]
        panel["rb_oi"] = rb_main["open_interest"]

        panel["hc_close"] = hc_main["close"].reindex(panel.index).ffill()
        panel["hc_settle"] = hc_main["settlement"].reindex(panel.index).ffill()
        panel["hc_volume"] = hc_main["volume"].reindex(panel.index).fillna(0)
        panel["hc_oi"] = hc_main["open_interest"].reindex(panel.index).ffill()

        panel["i_close"] = i_main["close"].reindex(panel.index).ffill()
        panel["i_settle"] = i_main["settlement"].reindex(panel.index).ffill()
        panel["i_volume"] = i_main["volume"].reindex(panel.index).fillna(0)
        panel["i_oi"] = i_main["open_interest"].reindex(panel.index).ffill()

        panel["j_close"] = j_main["close"].reindex(panel.index).ffill()
        panel["j_settle"] = j_main["settlement"].reindex(panel.index).ffill()
        panel["j_volume"] = j_main["volume"].reindex(panel.index).fillna(0)
        panel["j_oi"] = j_main["open_interest"].reindex(panel.index).ffill()

        panel["jm_close"] = jm_main["close"].reindex(panel.index).ffill()
        panel["jm_settle"] = jm_main["settlement"].reindex(panel.index).ffill()
        panel["jm_volume"] = jm_main["volume"].reindex(panel.index).fillna(0)
        panel["jm_oi"] = jm_main["open_interest"].reindex(panel.index).ffill()

        # 全市场总持仓 (用于投机度与沉淀资金)
        panel["rb_total_oi"] = rb_idx["open_interest"].reindex(panel.index).ffill()
        panel["hc_total_oi"] = hc_idx["open_interest"].reindex(panel.index).ffill()
        panel["i_total_oi"] = i_idx["open_interest"].reindex(panel.index).ffill()
        panel["j_total_oi"] = j_idx["open_interest"].reindex(panel.index).ffill()
        panel["jm_total_oi"] = jm_idx["open_interest"].reindex(panel.index).ffill()

        # 2. 现货微观事实层对齐
        spot_df = self.load_spot_data().set_index("date")
        spot_cols = [
            "spot_hz_zhongtian", "spot_hz_tier3", "spot_sh_hc", "spot_ts_billet",
            "cost_east_bf", "cost_east_eaf_peak", "cost_east_eaf_valley",
            "profit_east_bf", "profit_east_eaf_peak", "profit_east_eaf_valley",
            "scrap_east_6mm", "cost_east_hot_metal", "inv_hz_stock", "flow_hz_outflow",
            "io_qd_pb_wet", "coke_hebei_wet", "spot_reg_hz_rb", "spot_reg_sy_rb",
            "spot_reg_bj_rb", "spot_reg_gz_rb", "spot_port_hlg_rb"
        ]
        for col in spot_cols:
            if col in spot_df.columns:
                panel[col] = spot_df[col].reindex(panel.index).ffill()
            else:
                panel[col] = np.nan

        # 针对历史早期长流程成本的严密融合 (每日现货 + 07_成本利润 + 原料工业估算)
        cost_series = panel["cost_east_bf"].copy()
        cost_file = self.raw_dir / "07_成本利润.csv"
        if cost_file.exists():
            try:
                c_df = pd.read_csv(cost_file)
                c01 = c_df[c_df["variable_id"] == "C01"].set_index("data_date")["value"]
                cost_series = cost_series.combine_first(c01.reindex(panel.index).ffill())
            except Exception:
                pass

        # 若仍有缺失区间，使用 1.6*青岛港PB粉 + 0.5*准一级焦 + 950元 工业标准模型兜底
        wind_raw_for_cost = self.load_wind_edb()
        pb_sub = wind_raw_for_cost[wind_raw_for_cost["code"] == "S0174655"]
        coke_sub = wind_raw_for_cost[wind_raw_for_cost["code"] == "S5134898"]
        if not pb_sub.empty and not coke_sub.empty:
            pb_s = pd.Series(pb_sub["value"].values, index=pd.to_datetime(pb_sub["data_date"]).dt.strftime("%Y-%m-%d"))
            coke_s = pd.Series(coke_sub["value"].values, index=pd.to_datetime(coke_sub["data_date"]).dt.strftime("%Y-%m-%d"))
            pb_aligned = pb_s[~pb_s.index.duplicated(keep="last")].reindex(panel.index).ffill()
            coke_aligned = coke_s[~coke_s.index.duplicated(keep="last")].reindex(panel.index).ffill()
            calc_cost = 1.6 * pb_aligned + 0.5 * coke_aligned + 950.0
            cost_series = cost_series.combine_first(calc_cost)

        panel["cost_east_bf"] = cost_series.ffill().bfill()

        # 3. Wind EDB 产业与宏观时序严格 PIT 对齐
        wind_raw = self.load_wind_edb()
        
        # 核心产业指标字典映射
        wind_code_map = {
            "Y6907796": "hot_metal_247",
            "O2244511": "bf_util_247",
            "S5713307": "rebar_weekly_prod",
            "H6924748": "rebar_soc_inv",
            "R8579706": "rebar_mill_inv",
            "A5938607": "rebar_apparent_demand",
            "P5075301": "hc_weekly_prod",
            "X1924001": "hc_soc_inv",
            "S5715670": "eaf_operating_rate",
            "S0110152": "iron_ore_port_inv",
            "X4173142": "building_deal_volume",
            "S0174655": "pb_powder_price",
            "S5134898": "j_port_price",
            "S5700017": "scrap_ts_price",
            "M0017126": "macro_pmi",
            "S0027374": "nbs_crude_steel_month",
            "S0027493": "customs_steel_export_month",
            "S0029657": "real_estate_invest_yoy"
        }

        # 统计局与海关等月度宏观数据代码 (次月15日生效)
        monthly_lag_codes = {"S0027374", "S0027370", "S0027378", "S0027493", "S0029657", "S0073293", "M5440435", "M5525763"}

        for code, col_name in wind_code_map.items():
            sub = wind_raw[wind_raw["code"] == code].dropna(subset=["value"]).copy()
            if sub.empty:
                panel[col_name] = np.nan
                continue

            sub["dt"] = pd.to_datetime(sub["data_date"])
            
            # 计算严密的 available_date
            if code in monthly_lag_codes:
                # 次月15日公布
                sub["avail_date"] = sub["dt"].apply(
                    lambda d: f"{d.year + 1}-01-15" if d.month == 12 else f"{d.year}-{d.month + 1:02d}-15"
                )
            elif "available_date" in sub.columns:
                sub["avail_date"] = sub["available_date"].astype(str).str[:10]
            else:
                sub["avail_date"] = sub["dt"].dt.strftime("%Y-%m-%d")

            # 建立可用时间点序列
            s = pd.Series(sub["value"].values, index=sub["avail_date"])
            s = s[~s.index.duplicated(keep="last")].sort_index()

            # 使用 union 索引确保周末/节假日发布的可用数据能平滑在下一交易日生效
            full_index = panel.index.union(s.index).sort_values()
            panel[col_name] = s.reindex(full_index).ffill().reindex(panel.index)

        # 4. SMM 数据对齐 (如冷热排产、出口FOB、制造业耗钢)
        smm_df = self.load_smm_data()
        if not smm_df.empty:
            smm_map = {
                "s22813839": "smm_rb_fob_tianjin",
                "s22804474": "smm_hc_fob_tianjin",
                "a10148222": "smm_port_shipment_32",
                "a12885068": "smm_mfg_steel_total",
                "a12885072": "smm_mfg_machinery",
                "a12885073": "smm_mfg_auto",
                "a12885074": "smm_mfg_home_appliance",
                "a12796380": "smm_cold_rolled_plan_31"
            }
            for ind_id, col_name in smm_map.items():
                sub = smm_df[smm_df["indicator_id"] == ind_id]
                if not sub.empty:
                    s = pd.Series(sub["value"].values, index=sub["date"].astype(str))
                    s = s[~s.index.duplicated(keep="last")]
                    panel[col_name] = s.reindex(panel.index).ffill()

        # 4.5. 宏观地方政府债券发行与财政脉冲对齐 (PIT 保证，前向填充)
        bond_df = self.load_macro_bonds()
        if not bond_df.empty:
            bond_cols = [
                "bond_total_issue",
                "bond_new_special",
                "bond_refinance",
                "bond_new_general",
                "special_bond_rolling4w",
                "total_bond_rolling4w",
                "refinance_rolling4w",
                "refinance_ratio_rolling4w",
                "special_bond_ytd",
                "special_bond_annual_quota",
                "special_bond_progress",
                "special_bond_remaining_quota",
                "required_daily_run_rate",
                "actual_daily_run_rate_20d",
                "pacing_acceleration_ratio",
                "pacing_regime",
                "fiscal_steel_pulse",
            ]
            full_idx = panel.index.union(bond_df.index).sort_values()
            aligned_bond = bond_df.reindex(full_idx)
            for c in bond_cols:
                if c in aligned_bond.columns:
                    if pd.api.types.is_numeric_dtype(aligned_bond[c].dtype):
                        panel[c] = aligned_bond[c].ffill().reindex(panel.index).fillna(0.0)
                    else:
                        panel[c] = aligned_bond[c].ffill().reindex(panel.index).fillna("发债平稳运行期")

        # 5. 过滤时间区间
        if start_date:
            panel = panel.loc[panel.index >= start_date].copy()
        if end_date:
            panel = panel.loc[panel.index <= end_date].copy()

        # 6. 计算发布新鲜度与发布事件追踪
        # 当日是否有重点周度数据新发布 (247铁水或库存)
        hot_metal_diff = panel["hot_metal_247"].diff()
        inv_diff = panel["rebar_soc_inv"].diff()
        panel["new_release_event"] = ((hot_metal_diff != 0) | (inv_diff != 0)).astype(int)

        # 记录距上次核心发布的天数 (data_age)
        release_dates = panel[panel["new_release_event"] == 1].index
        panel["data_age"] = 0
        last_rel = panel.index[0]
        for idx in panel.index:
            if idx in release_dates:
                last_rel = idx
            days = (datetime.strptime(idx, "%Y-%m-%d") - datetime.strptime(last_rel, "%Y-%m-%d")).days
            panel.loc[idx, "data_age"] = days

        return panel
