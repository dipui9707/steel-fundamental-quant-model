#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模块: stage_e/trade_recorder.py
功能: 阶段 E 交易记录归档与导出器 (Trade Recorder)
职责:
  1. 严格契合《交易/README.md》与《交易记录.csv》的标准字段规范:
     - trade_id: 交易唯一流水号;
     - prediction_id: 对应状态预测快照 ID;
     - contract: 成交具体合约;
     - side: 买卖开平方向;
     - quantity: 手数;
     - entry_time: 开仓时点;
     - entry_price: 开仓价格;
     - exit_time: 平仓时点;
     - exit_price: 平仓价格;
     - fees: 交易费用与滑点;
     - risk_plan: 预设风控计划;
     - execution_deviation: 执行滑点偏差;
     - note: 触发说明或强平原因;
  2. 导出至独立研究实验目录，禁止覆盖真实交易台账。
"""

from pathlib import Path
from uuid import uuid4
from typing import List, Dict, Any, Optional
import pandas as pd


CSV_COLUMNS = [
    "trade_id",
    "prediction_id",
    "contract",
    "side",
    "quantity",
    "entry_time",
    "entry_price",
    "exit_time",
    "exit_price",
    "fees",
    "pnl",
    "risk_plan",
    "execution_deviation",
    "note",
]


class TradeRecorder:
    """
    交易台账记录与导出器
    """

    def __init__(self, target_csv_path: Optional[str] = None):
        if target_csv_path is None:
            base_dir = Path(__file__).resolve().parent.parent
            target_csv_path = str(base_dir / "研究" / "回测实验" / f"simulation_{uuid4().hex}" / "trades.csv")
        self.target_csv_path = target_csv_path
        live = Path(__file__).resolve().parent.parent / "交易" / "交易记录.csv"
        if Path(target_csv_path).resolve() == live:
            raise ValueError("回测流水禁止写入真实交易台账")

    def export_trade_records(self, trades_df: pd.DataFrame, overwrite: bool = True) -> str:
        """
        导出格式化交易明细至指定 CSV 文件
        """
        Path(self.target_csv_path).parent.mkdir(parents=True, exist_ok=True)
        if trades_df.empty:
            if not overwrite and Path(self.target_csv_path).exists():
                return self.target_csv_path
            empty_df = pd.DataFrame(columns=CSV_COLUMNS)
            empty_df.to_csv(self.target_csv_path, index=False, encoding="utf-8")
            return self.target_csv_path

        out_df = pd.DataFrame()
        for col in CSV_COLUMNS:
            if col in trades_df.columns:
                out_df[col] = trades_df[col]
            else:
                out_df[col] = ""

        # 格式化数值字段
        out_df["quantity"] = out_df["quantity"].astype(int)
        out_df["entry_price"] = out_df["entry_price"].round(2)
        out_df["exit_price"] = out_df["exit_price"].round(2)
        out_df["fees"] = out_df["fees"].round(2)
        out_df["execution_deviation"] = out_df["execution_deviation"].round(2)

        p = Path(self.target_csv_path)
        p.parent.mkdir(parents=True, exist_ok=True)

        if overwrite or not p.exists():
            out_df.to_csv(self.target_csv_path, index=False, encoding="utf-8")
        else:
            out_df.to_csv(self.target_csv_path, mode="a", header=False, index=False, encoding="utf-8")

        return str(p)
