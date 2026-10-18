# -*- coding: utf-8 -*-
"""反包策略回撤计算测试。"""

from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "脚本" / "反包策略回撤.py"
SPEC = importlib.util.spec_from_file_location("reversal_drawdown", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


def 构造样本(卖出日期: str) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "code": ["000001"],
            "买入日期": [pd.Timestamp("2026-01-05")],
            "卖出日期": [pd.Timestamp(卖出日期)],
            "买入金额": [10_000.0],
            "买入费用": [5.10],
            "卖出金额": [11_000.0],
            "卖出费用": [16.60],
            "持仓份额": [1_000],
        }
    )


class 回撤计算测试(unittest.TestCase):
    """用一笔交易核对权益曲线和最大回撤。"""

    def test_equity_and_drawdown(self) -> None:
        日线 = pd.DataFrame(
            {
                "code": ["000001", "000001"],
                "time": [
                    pd.Timestamp("2026-01-05"),
                    pd.Timestamp("2026-01-06"),
                ],
                "close": [9.0, 11.0],
            }
        )
        交易日 = pd.DatetimeIndex(["2026-01-05", "2026-01-06"])

        曲线, 资金基数, 最大并发 = MODULE.计算每日权益(
            构造样本("2026-01-06"),
            日线,
            交易日,
        )

        self.assertEqual(资金基数, 20_000.0)
        self.assertEqual(最大并发, 1)
        self.assertAlmostEqual(曲线.loc[0, "权益"], 18_994.90, places=2)
        self.assertAlmostEqual(曲线.loc[1, "权益"], 20_978.30, places=2)
        self.assertAlmostEqual(曲线["回撤"].min() * 100, -5.0255, places=4)

    def test_metrics(self) -> None:
        日线 = pd.DataFrame(
            {
                "code": ["000001", "000001"],
                "time": [
                    pd.Timestamp("2026-01-05"),
                    pd.Timestamp("2026-01-06"),
                ],
                "close": [9.0, 11.0],
            }
        )
        交易日 = pd.DatetimeIndex(["2026-01-05", "2026-01-06"])

        指标, 曲线 = MODULE.计算回撤指标(
            "测试",
            构造样本("2026-01-06"),
            日线,
            交易日,
        )

        self.assertAlmostEqual(指标["期末权益"], 20_978.30, places=2)
        self.assertAlmostEqual(指标["最大回撤"], -5.0255, places=4)
        self.assertEqual(指标["最大并发"], 1)
        self.assertEqual(len(曲线), 2)

    def test_suspension_uses_last_close(self) -> None:
        日线 = pd.DataFrame(
            {
                "code": ["000001", "000001"],
                "time": [
                    pd.Timestamp("2026-01-05"),
                    pd.Timestamp("2026-01-07"),
                ],
                "close": [9.0, 11.0],
            }
        )
        交易日 = pd.DatetimeIndex(
            ["2026-01-05", "2026-01-06", "2026-01-07"]
        )

        曲线, _, _ = MODULE.计算每日权益(
            构造样本("2026-01-07"),
            日线,
            交易日,
        )

        # 01-06 没有收盘价，按 01-05 的 9.0 估值，不能用 01-07 的 11.0
        self.assertAlmostEqual(曲线.loc[1, "权益"], 18_994.90, places=2)


if __name__ == "__main__":
    unittest.main()
