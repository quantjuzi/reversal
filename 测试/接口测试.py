# -*- coding: utf-8 -*-
"""数据接口的核心端点测试。"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

from fastapi.testclient import TestClient


ROOT = Path(__file__).resolve().parents[1]
SERVER_PATH = ROOT / "接口" / "server.py"
SPEC = importlib.util.spec_from_file_location("接口server", SERVER_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class InterfaceTests(unittest.TestCase):
    """检查四个端点的核心行为。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.client = TestClient(MODULE.app)

    def test_health(self) -> None:
        response = self.client.get("/health")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_summary_matches_ledger(self) -> None:
        response = self.client.get("/stats/summary")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["总成交笔数"], 1365)
        self.assertEqual(data["买入笔数"], 716)
        self.assertEqual(data["卖出笔数"], 649)
        self.assertAlmostEqual(data["佣金合计"], 9216.89, places=2)
        self.assertAlmostEqual(data["印花税合计"], 8740.86, places=2)
        self.assertAlmostEqual(data["过户费合计"], 86.73, places=2)

    def test_trades_filter_by_code(self) -> None:
        response = self.client.get("/trades", params={"code": "000021"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertGreaterEqual(data["count"], 2)
        self.assertTrue(data["rows"])
        self.assertTrue(
            all(row["证券代码"] == "000021" for row in data["rows"])
        )
        self.assertEqual(data["rows"][0]["交易日期"], "2025-10-13")

    def test_trades_limit(self) -> None:
        response = self.client.get("/trades", params={"limit": 5})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["rows"]), 5)
        self.assertGreater(data["count"], 5)

    def test_trades_date_range(self) -> None:
        response = self.client.get(
            "/trades",
            params={
                "start": "2026-01-01",
                "end": "2026-01-31",
                "limit": 1000,
            },
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertTrue(data["rows"])
        self.assertTrue(
            all(
                "2026-01-01" <= row["交易日期"] <= "2026-01-31"
                for row in data["rows"]
            )
        )

    def test_group_by_direction(self) -> None:
        response = self.client.get(
            "/stats/group",
            params={"by": "方向", "metric": "成交金额"},
        )
        self.assertEqual(response.status_code, 200)
        rows = {row["方向"]: row for row in response.json()}
        self.assertEqual(rows["买入"]["笔数"], 716)
        self.assertEqual(rows["卖出"]["笔数"], 649)
        self.assertAlmostEqual(
            rows["买入"]["合计"], 17433152.79, places=2
        )
        self.assertAlmostEqual(
            rows["卖出"]["合计"], 17467443.88, places=2
        )

    def test_group_invalid_column(self) -> None:
        response = self.client.get(
            "/stats/group",
            params={"by": "不存在"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("列名不存在", response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
