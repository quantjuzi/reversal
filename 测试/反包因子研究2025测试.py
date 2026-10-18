# -*- coding: utf-8 -*-
"""2025 反包研究流程测试。"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "脚本" / "反包因子研究_2025.py"
SPEC = importlib.util.spec_from_file_location(
    "reversal_research_2025",
    MODULE_PATH,
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class ReversalResearch2025Tests(unittest.TestCase):
    """验证 2025 区间、买卖对齐和 A/B/C 条件。"""

    def sample_data(self) -> pd.DataFrame:
        dates = pd.to_datetime(
            [
                "2024-12-30",
                "2024-12-31",
                "2025-01-02",
                "2025-01-03",
                "2025-01-06",
                "2025-01-07",
            ]
        )
        return pd.DataFrame(
            {
                "time": dates,
                "code": ["000001.XSHE"] * len(dates),
                "open": [10.0, 10.2, 10.5, 10.8, 11.0, 11.2],
                "close": [11.0, 10.1, 10.7, 11.1, 11.2, 11.4],
                "high": [11.0, 10.5, 10.9, 11.2, 11.3, 11.5],
                "low": [10.0, 9.9, 10.2, 10.6, 10.9, 11.0],
                "volume": [1e8] * len(dates),
                "money": [
                    11.0e8,
                    10.1e8,
                    10.7e8,
                    11.1e8,
                    11.2e8,
                    11.4e8,
                ],
                "pre_close": [10.0, 11.0, 10.1, 10.7, 11.1, 11.2],
                "paused": [0] * len(dates),
                "是否涨停": [0, 0, 1, 0, 0, 0],
                "成交额_亿": [11.0, 10.1, 10.7, 11.1, 11.2, 11.4],
                "竞价涨幅": [1.0, -2.0, 1.0, 1.0, 1.0, 1.0],
            }
        )

    def test_signal_uses_2025_t_plus_one_and_t_plus_two(self) -> None:
        _, 交易, 交易日历 = MODULE.构建研究数据(
            self.sample_data(),
            MODULE.通用研究.研究参数(),
        )

        self.assertEqual(len(交易), 1)
        self.assertEqual(
            pd.Timestamp(交易.iloc[0]["time"]),
            pd.Timestamp("2025-01-03"),
        )
        self.assertEqual(
            pd.Timestamp(交易.iloc[0]["买入日期"]),
            pd.Timestamp("2025-01-06"),
        )
        self.assertEqual(
            pd.Timestamp(交易.iloc[0]["卖出日期"]),
            pd.Timestamp("2025-01-07"),
        )
        self.assertTrue(
            pd.to_datetime(交易日历).between(
                MODULE.研究开始,
                MODULE.研究结束,
            ).all()
        )

    def test_strategy_membership_columns_exist(self) -> None:
        _, 交易, _ = MODULE.构建研究数据(
            self.sample_data(),
            MODULE.通用研究.研究参数(),
        )

        for 名称 in MODULE.策略定义:
            self.assertIn(名称, 交易.columns)

    def test_fixed_capital_flag(self) -> None:
        指标 = {
            "交易数": 10,
            "平均资金年化": 20.0,
            "累计净盈亏": 10_000.0,
            "最高资金占用": 120_000.0,
        }
        结果 = MODULE.补全指标(指标, 181, 100_000.0)

        self.assertEqual(结果["复利年化"], 20.0)
        self.assertEqual(结果["固定账户资金是否足够"], "否")

    def test_save_results_creates_expected_files(self) -> None:
        参数 = MODULE.通用研究.研究参数()
        _, 交易, 交易日历 = MODULE.构建研究数据(
            self.sample_data(),
            参数,
        )
        策略汇总 = MODULE.生成策略汇总(
            交易,
            交易日历,
            参数,
            100_000.0,
        )
        因子总表 = pd.DataFrame(columns=["因子", *MODULE.报告列])

        with tempfile.TemporaryDirectory() as directory:
            输出目录 = Path(directory)
            MODULE.保存结果(
                输出目录,
                交易,
                策略汇总,
                因子总表,
                {},
            )

            self.assertTrue(
                (输出目录 / "反包策略汇总_2025.csv").exists()
            )
            self.assertTrue(
                (输出目录 / "反包交易明细_2025.csv").exists()
            )
            self.assertTrue(
                (输出目录 / "反包测试报告_2025.md").exists()
            )


if __name__ == "__main__":
    unittest.main()
