# -*- coding: utf-8 -*-
"""重建反包策略 A/B/C 的每日资金曲线并计算最大回撤。

资金基数：
    每笔名义资金 20,000 元 × 策略最大并发持仓数。

估值口径：
    - 信号日确认；
    - T+1 开盘买入；
    - T+2 成交均价卖出；
    - 买入日扣除买入金额和买入费用；
    - 卖出日计入卖出金额并扣除卖出费用；
    - 持有期间每个交易日按当日收盘价估值；
    - 停牌日使用最近一个有效收盘价，不使用未来价格。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = ROOT / "脚本"
sys.path.insert(0, str(SCRIPT_DIR))

import 高开均线完整回测 as 策略模块  # noqa: E402
from 连板断板统计 import consecutive_limit_count  # noqa: E402


因子文件 = ROOT / "数据" / "聚宽因子_2026-01-01_2026-09-30.csv"
指数文件 = ROOT / "数据" / "深证成指_2026-01-01_2026-09-30_完整.csv"
输出目录 = ROOT / "结果"
结果文件 = 输出目录 / "反包策略研究_2026_回撤结果.csv"
资金曲线文件 = 输出目录 / "反包策略研究_2026_资金曲线.csv"


def 构建交易() -> tuple[pd.DataFrame, pd.DataFrame, pd.DatetimeIndex]:
    """按 2026 研究口径构建 A/B/C 的逐笔交易。"""

    因子 = pd.read_csv(
        因子文件,
        encoding="utf-8-sig",
        usecols=[
            "time",
            "code",
            "open",
            "close",
            "high",
            "low",
            "high_limit",
            "pre_close",
            "是否涨停",
            "成交额_亿",
            "竞价涨幅",
            "M7",
            "M14",
            "实体涨幅",
            "均价",
        ],
    )
    因子["time"] = pd.to_datetime(因子["time"])
    指数 = pd.read_csv(指数文件, encoding="utf-8-sig")
    指数["time"] = pd.to_datetime(指数["time"])

    数据 = 因子.merge(指数, on="time", how="left")
    分组 = 数据.groupby("code", sort=False)
    数据["连板数"] = 分组["是否涨停"].transform(consecutive_limit_count)
    数据["前一日连板数"] = 分组["连板数"].shift(1)
    数据["前一日涨停"] = 分组["是否涨停"].shift(1)
    数据["涨停日深证成指上涨"] = 分组["深证成指上涨"].shift(1)
    数据["信号"] = (
        数据["前一日涨停"].eq(1) & 数据["是否涨停"].eq(0)
    ).astype(int)

    交易 = 策略模块.确定买卖规则(数据)
    交易 = 策略模块.计算交易成本(
        交易,
        策略模块.策略参数(),
    )
    交易日 = (
        pd.to_datetime(数据["time"])
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )
    return 数据, 交易, pd.DatetimeIndex(交易日)


def 计算每日权益(
    样本: pd.DataFrame,
    日线: pd.DataFrame,
    交易日: pd.DatetimeIndex,
) -> tuple[pd.DataFrame, float, int]:
    """按每日收盘价估值，返回权益曲线、资金基数和最大并发。"""

    if 样本.empty:
        raise ValueError("策略样本为空")

    日期位置 = {日期: 位置 for 位置, 日期 in enumerate(交易日)}
    持仓事件 = np.zeros(len(交易日) + 1, dtype=int)
    for 行 in 样本.itertuples(index=False):
        买入日 = pd.Timestamp(行.买入日期).normalize()
        卖出日 = pd.Timestamp(行.卖出日期).normalize()
        if 买入日 not in 日期位置 or 卖出日 not in 日期位置:
            raise ValueError("买入或卖出日期不在交易日历内")
        持仓事件[日期位置[买入日]] += 1
        持仓事件[日期位置[卖出日] + 1] -= 1

    每日持仓数 = np.cumsum(持仓事件[:-1])
    最大并发 = int(每日持仓数.max())
    资金基数 = float(最大并发 * 20_000)

    现金变动 = pd.Series(0.0, index=交易日)
    for 行 in 样本.itertuples(index=False):
        买入日 = pd.Timestamp(行.买入日期).normalize()
        卖出日 = pd.Timestamp(行.卖出日期).normalize()
        现金变动.loc[买入日] -= float(行.买入金额 + 行.买入费用)
        现金变动.loc[卖出日] += float(行.卖出金额 - 行.卖出费用)

    持仓 = 样本[
        ["code", "买入日期", "卖出日期", "持仓份额"]
    ].copy()
    持仓["买入日期"] = pd.to_datetime(持仓["买入日期"]).dt.normalize()
    持仓["卖出日期"] = pd.to_datetime(持仓["卖出日期"]).dt.normalize()

    日线收盘 = (
        日线[["code", "time", "close"]]
        .dropna(subset=["code", "time", "close"])
        .assign(
            code=lambda frame: frame["code"].astype(str),
            time=lambda frame: pd.to_datetime(frame["time"]).dt.normalize(),
        )
    )
    当日收盘 = {
        日期: dict(
            zip(
                子表["code"],
                子表["close"].astype(float),
            )
        )
        for 日期, 子表 in 日线收盘.groupby("time", sort=False)
    }

    最近收盘: dict[str, float] = {}
    现金 = 资金基数
    曲线: list[dict[str, object]] = []
    for 日期 in 交易日:
        最近收盘.update(当日收盘.get(日期, {}))
        现金 += float(现金变动.loc[日期])
        持仓市值 = 0.0
        for 行 in 持仓.itertuples(index=False):
            if 行.买入日期 <= 日期 < 行.卖出日期:
                收盘价 = 最近收盘.get(str(行.code))
                if 收盘价 is not None:
                    持仓市值 += float(行.持仓份额) * 收盘价
        权益 = 现金 + 持仓市值
        曲线.append(
            {
                "日期": 日期,
                "现金": 现金,
                "持仓市值": 持仓市值,
                "权益": 权益,
                "日收益率": 0.0,
            }
        )

    权益曲线 = pd.DataFrame(曲线)
    权益曲线["日收益率"] = (
        权益曲线["权益"]
        .pct_change()
        .fillna(权益曲线["权益"].div(资金基数).sub(1))
    )
    历史峰值 = 权益曲线["权益"].cummax().clip(lower=资金基数)
    权益曲线["历史峰值"] = 历史峰值
    权益曲线["回撤"] = 权益曲线["权益"].div(历史峰值).sub(1)
    权益曲线["净值"] = 权益曲线["权益"].div(资金基数)
    return 权益曲线, 资金基数, 最大并发


def 计算回撤指标(
    策略名称: str,
    样本: pd.DataFrame,
    日线: pd.DataFrame,
    交易日: pd.DatetimeIndex,
) -> tuple[dict[str, object], pd.DataFrame]:
    """计算一个策略的收益、峰谷回撤和资金曲线。"""

    曲线, 资金基数, 最大并发 = 计算每日权益(
        样本,
        日线,
        交易日,
    )
    谷值位置 = int(曲线["回撤"].idxmin())
    峰值位置 = int(曲线.loc[:谷值位置, "权益"].idxmax())
    期末权益 = float(曲线["权益"].iloc[-1])
    区间收益率 = 期末权益 / 资金基数 - 1
    年化收益率 = (
        ((1 + 区间收益率) ** (252 / len(曲线)) - 1) * 100
        if 区间收益率 > -1
        else np.nan
    )
    最大回撤 = float(曲线["回撤"].min() * 100)
    指标 = {
        "策略": 策略名称,
        "交易数": len(样本),
        "最大并发": 最大并发,
        "资金基数": 资金基数,
        "期末权益": 期末权益,
        "区间收益率": 区间收益率 * 100,
        "年化收益": 年化收益率,
        "最大回撤": 最大回撤,
        "峰值日": 曲线.loc[峰值位置, "日期"].date(),
        "谷值日": 曲线.loc[谷值位置, "日期"].date(),
        "年化/最大回撤": (
            年化收益率 / abs(最大回撤)
            if 最大回撤 < 0
            else np.nan
        ),
    }
    曲线 = 曲线.copy()
    曲线["策略"] = 策略名称
    return 指标, 曲线


def 主程序() -> None:
    """执行 A/B/C 资金曲线和回撤计算。"""

    日线, 交易, 交易日 = 构建交易()
    条件 = {
        "A：2连板 + 成交额10亿 + 实体>2%": (
            交易["前一日连板数"].ge(2)
            & 交易["成交额_亿"].ge(10)
            & 交易["实体涨幅"].gt(2)
        ),
        "B：2连板 + 成交额5亿 + 实体>2%": (
            交易["前一日连板数"].ge(2)
            & 交易["成交额_亿"].ge(5)
            & 交易["实体涨幅"].gt(2)
        ),
        "C：2连板 + 成交额10亿 + 实体>1%": (
            交易["前一日连板数"].ge(2)
            & 交易["成交额_亿"].ge(10)
            & 交易["实体涨幅"].gt(1)
        ),
    }

    指标行 = []
    曲线表 = []
    for 名称, 条件值 in 条件.items():
        指标, 曲线 = 计算回撤指标(
            名称,
            交易.loc[条件值].copy(),
            日线,
            交易日,
        )
        指标行.append(指标)
        曲线表.append(曲线)

    输出目录.mkdir(parents=True, exist_ok=True)
    指标表 = pd.DataFrame(指标行)
    指标表.to_csv(结果文件, index=False, encoding="utf-8-sig")
    pd.concat(曲线表, ignore_index=True).to_csv(
        资金曲线文件,
        index=False,
        encoding="utf-8-sig",
    )
    print(指标表.to_string(index=False))
    print(f"\n回撤结果：{结果文件}")
    print(f"资金曲线：{资金曲线文件}")


if __name__ == "__main__":
    主程序()
