# -*- coding: utf-8 -*-
"""在聚宽研究环境下载 2025-01-01 至 2025-09-30 反包研究数据。

最终输出字段与 2026-01-01 至 2026-09-30 的标准因子文件一致。

运行环境:
    JoinQuant 研究环境（Jupyter）

输出:
    数据/聚宽实盘分类日线_2024-12-01_2025-09-30.csv
    数据/聚宽因子_2025-01-01_2025-09-30.csv

说明:
    原始下载从 2024-12-01 开始，是为了让 2025 年初的 M7、M14
    有足够历史数据；标准化文件的最终日期只保留 2025-01-01 至 2025-09-30。
"""

from __future__ import annotations

import os
import time
from pathlib import Path

import pandas as pd
from jqdata import get_all_securities, get_price


START = "2025-01-01"
END = "2025-09-30"
WARMUP_START = "2024-12-01"
CHUNK_SIZE = 200

OUTPUT_DIR = Path(os.environ.get("FANBAO_DATA_DIR", "数据"))
RAW_PATH = OUTPUT_DIR / "聚宽实盘分类日线_2024-12-01_2025-09-30.csv"
FACTOR_PATH = OUTPUT_DIR / "聚宽因子_2025-01-01_2025-09-30.csv"
FAILURE_PATH = OUTPUT_DIR / "下载失败_2024-12-01_2025-09-30_聚宽.csv"

FIELDS = [
    "open",
    "high",
    "low",
    "close",
    "volume",
    "money",
    "pre_close",
    "high_limit",
    "low_limit",
    "paused",
    "avg",
]


def is_a_share(code: str) -> bool:
    """只保留沪深北 A 股，排除 B 股等非目标证券。"""

    if code.endswith(".XSHG"):
        return code.startswith("6")
    if code.endswith(".XSHE"):
        return code.startswith(("0", "3"))
    if code.endswith(".XBSE"):
        return code.startswith(("4", "8", "9"))
    return False


def get_a_share_codes() -> list[str]:
    """获取研究区间内可能存在的沪深北 A 股代码。"""

    securities = get_all_securities(types=["stock"]).copy()
    securities.index = securities.index.astype(str)
    securities["start_date"] = pd.to_datetime(securities["start_date"])
    securities["end_date"] = pd.to_datetime(securities["end_date"])

    start = pd.Timestamp(START)
    end = pd.Timestamp(END)
    active = securities[
        securities["start_date"].le(end)
        & securities["end_date"].ge(start)
    ]
    return sorted(code for code in active.index if is_a_share(code))


def fetch_chunk(codes: list[str]) -> pd.DataFrame:
    """下载一批股票，返回聚宽原始字段。"""

    data = get_price(
        codes,
        start_date=WARMUP_START,
        end_date=END,
        frequency="daily",
        fields=FIELDS,
        skip_paused=False,
        fq=None,
        panel=False,
    )
    data = data.reset_index()

    if "time" not in data.columns:
        if "date" in data.columns:
            data = data.rename(columns={"date": "time"})
        else:
            raise ValueError("get_price 返回结果缺少 time/date 字段")

    if "code" not in data.columns:
        if len(codes) == 1:
            data["code"] = codes[0]
        else:
            raise ValueError("批量下载结果缺少 code 字段")

    data["time"] = pd.to_datetime(data["time"], errors="coerce")
    data = data.dropna(subset=["time", "code"]).copy()

    for column in [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "money",
        "pre_close",
        "high_limit",
        "low_limit",
        "paused",
        "avg",
    ]:
        if column not in data.columns:
            data[column] = pd.NA
        data[column] = pd.to_numeric(data[column], errors="coerce")

    data["avg"] = data["avg"].fillna(
        data["money"].div(data["volume"].where(data["volume"].gt(0)))
    )
    valid = (
        data["paused"].fillna(0).eq(0)
        & data["close"].notna()
        & data["high_limit"].notna()
    )
    data["is_limit_up"] = (
        valid & data["close"].ge(data["high_limit"] - 1e-6)
    ).astype(int)
    data["date"] = data["time"].dt.strftime("%Y-%m-%d")

    return data[
        [
            "date",
            "code",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "money",
            "pre_close",
            "high_limit",
            "low_limit",
            "paused",
            "avg",
            "is_limit_up",
        ]
    ]


def download_all(codes: list[str]) -> tuple[pd.DataFrame, list[str]]:
    """分块下载，失败块重试三次并记录未能下载的代码。"""

    chunks: list[pd.DataFrame] = []
    failed_codes: list[str] = []
    for offset in range(0, len(codes), CHUNK_SIZE):
        chunk = codes[offset : offset + CHUNK_SIZE]
        last_error: Exception | None = None
        for attempt in range(3):
            try:
                part = fetch_chunk(chunk)
                if part.empty:
                    raise RuntimeError("返回空数据")
                chunks.append(part)
                print(
                    f"下载 {offset + len(chunk)}/{len(codes)}，"
                    f"本块 {len(part)} 行"
                )
                break
            except Exception as error:
                last_error = error
                wait = 2 * (attempt + 1)
                print(f"第 {attempt + 1} 次失败：{error}，{wait} 秒后重试")
                time.sleep(wait)
        else:
            failed_codes.extend(chunk)
            print(f"本块最终失败：{chunk[0]} 至 {chunk[-1]}，{last_error}")

    if not chunks:
        raise RuntimeError("没有下载到任何数据")

    raw = pd.concat(chunks, ignore_index=True)
    raw = raw.drop_duplicates(["date", "code"]).sort_values(["code", "date"])
    return raw, failed_codes


def make_factor(raw: pd.DataFrame) -> pd.DataFrame:
    """生成与现有 2026 标准因子文件一致的表。"""

    factor = raw.rename(
        columns={
            "date": "time",
            "avg": "均价原始",
            "is_limit_up": "是否涨停",
        }
    ).copy()
    factor["time"] = pd.to_datetime(factor["time"])
    factor["code"] = factor["code"].astype(str)

    numeric_columns = [
        "open",
        "high",
        "low",
        "close",
        "volume",
        "money",
        "pre_close",
        "high_limit",
        "low_limit",
        "paused",
        "是否涨停",
    ]
    for column in numeric_columns:
        factor[column] = pd.to_numeric(factor[column], errors="coerce")

    factor["paused"] = factor["paused"].fillna(0)
    factor["是否涨停"] = factor["是否涨停"].fillna(0).astype(int)
    factor["成交额_亿"] = factor["money"] / 100_000_000
    factor["竞价涨幅"] = (
        factor["open"] / factor["pre_close"] - 1
    ) * 100
    factor["均价"] = factor["money"] / factor["volume"]
    factor = factor.sort_values(["code", "time"]).reset_index(drop=True)

    close_by_code = factor.groupby("code", sort=False)["close"]
    factor["M7"] = close_by_code.transform(
        lambda series: series.rolling(7, min_periods=7).mean()
    )
    factor["M14"] = close_by_code.transform(
        lambda series: series.rolling(14, min_periods=14).mean()
    )
    factor["实体涨幅"] = (
        factor["close"] / factor["open"] - 1
    ) * 100

    factor = factor[
        factor["time"].between(pd.Timestamp(START), pd.Timestamp(END))
    ].copy()
    factor = factor.drop(columns=["均价原始"])
    factor["time"] = factor["time"].dt.strftime("%Y-%m-%d")

    return factor[
        [
            "time",
            "code",
            "open",
            "close",
            "high",
            "low",
            "volume",
            "money",
            "pre_close",
            "high_limit",
            "low_limit",
            "paused",
            "是否涨停",
            "成交额_亿",
            "竞价涨幅",
            "均价",
            "M7",
            "M14",
            "实体涨幅",
        ]
    ]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    codes = get_a_share_codes()
    print(f"研究区间：{START} 至 {END}")
    print(f"下载预热：{WARMUP_START} 至 {END}")
    print(f"A 股代码：{len(codes)}")

    raw, failed_codes = download_all(codes)
    raw.to_csv(RAW_PATH, index=False, encoding="utf-8-sig")
    print(f"原始日线：{RAW_PATH}，{len(raw)} 行")

    factor = make_factor(raw)
    factor.to_csv(FACTOR_PATH, index=False, encoding="utf-8-sig")
    print(f"标准因子：{FACTOR_PATH}，{len(factor)} 行")
    print(f"股票数：{factor['code'].nunique()}")

    if failed_codes:
        pd.DataFrame({"code": sorted(failed_codes)}).to_csv(
            FAILURE_PATH,
            index=False,
            encoding="utf-8-sig",
        )
        print(f"下载失败：{len(failed_codes)} 支，清单：{FAILURE_PATH}")


if __name__ == "__main__":
    main()
