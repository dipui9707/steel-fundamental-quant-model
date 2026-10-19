#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_c/state_spot.py
功能: 阶段 C 现货微观确认与蓄水池流动性状态引擎 (Spot State Engine)
职责:
  严格遵循《实施手册》第 4.3 节、第 7 节与 A05/A05.1/A02.4 规范:
  1. 现货真实确认状态推断 (Spot Confirmation: Confirmed / Mixed / Rejected / Unknown);
  2. 双轨基差形态定性 (Basis Regime: 极度升水 / 常规升水Back / 平水震荡 / 显著贴水Contango);
  3. 微观出库与蓄水池去库真实度识别 (真去库强消化 / 蓄水池承压滞销 / 常态流转);
  4. 期现无风险正套套利机会识别 (Cash and Carry Arbitrage Net Profit);
  5. 严格坚持 State != Position，绝不产生买卖交易订单。
"""

from typing import Dict, Any, List, Optional
import pandas as pd
import numpy as np


class SpotStateClassifier:
    """
    现货状态与微观蓄水池流动性分类器
    """

    def __init__(self):
        pass

    def classify_row(self, row: pd.Series, fund_dir: str = "Neutral") -> Dict[str, Any]:
        """
        对单日截面推断现货确认与微观状态
        """
        basis_t3 = row.get("basis_tier3", np.nan)
        basis_zt = row.get("basis_zhongtian", np.nan)
        stock_sales = row.get("hz_stock_to_sales", np.nan)
        outflow = row.get("flow_hz_outflow", np.nan)
        deal_vol = row.get("building_deal_volume", np.nan)
        net_carry = row.get("net_cash_carry", np.nan)

        pct_basis_t3 = row.get("pct_basis_tier3", np.nan)
        pct_stock_sales = row.get("pct_hz_stock_to_sales", np.nan)
        pct_outflow = row.get("pct_flow_hz_outflow", np.nan)
        pct_deal_vol = row.get("pct_building_deal_volume", np.nan)

        # ---------------------------------------------------------
        # 1. Spot Confirmation (现货对产业基本面的物理确认: 历史分位数自适应)
        # ---------------------------------------------------------
        if pd.isna(basis_t3) or fund_dir == "Unknown":
            spot_conf = "Unknown"
        elif fund_dir == "Bullish":
            # 产业偏多：现货升水 (分位 >= 55% 或基差 > 25元) 且出库活跃/库销比健康 -> Confirmed
            # 若大幅贴水 (分位 <= 15% 或基差 < -50元，期货虚高，现货不认) -> Rejected
            has_pct_basis = not pd.isna(pct_basis_t3)
            is_basis_bull = (pct_basis_t3 >= 0.55) if has_pct_basis else (basis_t3 > 25.0)
            is_basis_reject = (pct_basis_t3 <= 0.15) if has_pct_basis else (basis_t3 < -50.0)

            has_flow_support = False
            if not pd.isna(pct_stock_sales) or not pd.isna(pct_deal_vol):
                has_flow_support = (
                    (not pd.isna(pct_stock_sales) and pct_stock_sales <= 0.70) or
                    (not pd.isna(pct_deal_vol) and pct_deal_vol >= 0.45)
                )
            else:
                has_flow_support = pd.isna(stock_sales) or stock_sales < 22.0 or deal_vol > 140000

            if (is_basis_bull or basis_t3 > 25.0) and has_flow_support:
                spot_conf = "Confirmed"
            elif is_basis_reject or basis_t3 < -50.0:
                spot_conf = "Rejected"
            else:
                spot_conf = "Mixed"
        elif fund_dir == "Bearish":
            # 产业偏空：现货贴水 (分位 <= 35% 或基差 < -15元) 或库销比显著攀升滞销 -> Confirmed
            # 若现货大幅升水 (分位 >= 85% 或基差 > 90元，实物偏紧、逼仓抗跌) -> Rejected
            has_pct_basis = not pd.isna(pct_basis_t3)
            is_basis_bear = (pct_basis_t3 <= 0.35) if has_pct_basis else (basis_t3 < -15.0)
            is_basis_reject = (pct_basis_t3 >= 0.85) if has_pct_basis else (basis_t3 > 90.0)

            is_stock_stagnant = False
            if not pd.isna(pct_stock_sales):
                is_stock_stagnant = (pct_stock_sales >= 0.75)
            else:
                is_stock_stagnant = stock_sales > 24.0

            if is_basis_bear or basis_t3 < -15.0 or (basis_t3 < 30.0 and is_stock_stagnant):
                spot_conf = "Confirmed"
            elif is_basis_reject or basis_t3 > 90.0:
                spot_conf = "Rejected"
            else:
                spot_conf = "Mixed"
        else: # Neutral
            spot_conf = "Mixed"

        # ---------------------------------------------------------
        # 2. Basis Regime (双轨基差期限结构形态: 历史分位数自适应)
        # ---------------------------------------------------------
        if pd.isna(basis_t3):
            basis_regime = "Unknown"
        elif not pd.isna(pct_basis_t3):
            if pct_basis_t3 >= 0.85 or basis_t3 > 150.0:
                basis_regime = "极度升水(现货逼仓)"
            elif pct_basis_t3 >= 0.55 or basis_t3 > 30.0:
                basis_regime = "常规升水(Back结构)"
            elif pct_basis_t3 <= 0.20 or basis_t3 < -40.0:
                basis_regime = "显著贴水(Contango结构)"
            else:
                basis_regime = "平水震荡"
        else:
            if basis_t3 > 150.0:
                basis_regime = "极度升水(现货逼仓)"
            elif basis_t3 > 30.0:
                basis_regime = "常规升水(Back结构)"
            elif -40.0 <= basis_t3 <= 30.0:
                basis_regime = "平水震荡"
            else:
                basis_regime = "显著贴水(Contango结构)"

        # ---------------------------------------------------------
        # 3. Spot Inventory Liquidity (真假去库与蓄水池流动性: 历史分位数自适应)
        # ---------------------------------------------------------
        if not pd.isna(pct_stock_sales) and not pd.isna(pct_outflow):
            if pct_stock_sales <= 0.25 and pct_outflow >= 0.70:
                inv_liquidity = "真去库强消化"
            elif pct_outflow <= 0.25 and pct_stock_sales >= 0.75:
                inv_liquidity = "蓄水池承压滞销"
            elif (not pd.isna(stock_sales) and stock_sales < 16.0) and (not pd.isna(outflow) and outflow > 3.0):
                inv_liquidity = "真去库强消化"
            elif (not pd.isna(outflow) and outflow < 1.6) and (not pd.isna(stock_sales) and stock_sales > 24.0):
                inv_liquidity = "蓄水池承压滞销"
            else:
                inv_liquidity = "常态流转"
        elif not pd.isna(stock_sales) and not pd.isna(outflow):
            if stock_sales < 16.0 and outflow > 3.0:
                inv_liquidity = "真去库强消化"
            elif outflow < 1.6 and stock_sales > 24.0:
                inv_liquidity = "蓄水池承压滞销"
            else:
                inv_liquidity = "常态流转"
        else:
            inv_liquidity = "常态流转"

        # ---------------------------------------------------------
        # 4. Cash and Carry Arbitrage (期现无风险套利利润)
        # ---------------------------------------------------------
        if pd.isna(net_carry):
            arbitrage_state = "Unknown"
        elif net_carry > 0.0:
            arbitrage_state = "正套套利有利润"
        else:
            arbitrage_state = "无正套利润"

        return {
            "spot_confirmation": spot_conf,
            "basis_regime": basis_regime,
            "spot_inventory_liquidity": inv_liquidity,
            "cash_carry_arbitrage": arbitrage_state,
        }

    def classify_all(self, df: pd.DataFrame, fund_directions: Optional[pd.Series] = None) -> pd.DataFrame:
        """批量推断现货状态宽表"""
        records = []
        for idx, row in df.iterrows():
            fund_dir = fund_directions.loc[idx] if fund_directions is not None else "Neutral"
            rec = self.classify_row(row, fund_dir=fund_dir)
            records.append(rec)

        res_df = pd.DataFrame(records, index=df.index)
        return res_df
