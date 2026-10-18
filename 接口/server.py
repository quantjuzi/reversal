# -*- coding: utf-8 -*-
"""数据接口 server.py —— 把「结果/实盘成交明细.csv」包成 HTTP 查询接口。

本地研究用的小工具（不是生产服务）：只读不写，直接读 CSV——1,365 条规模，
简单、可核对，比上数据库划算。

启动（在 接口/ 目录下）：
    pip install fastapi uvicorn
    uvicorn server:app --reload
然后打开 http://127.0.0.1:8000/docs 可以直接点着试。
"""
from pathlib import Path

import pandas as pd
from fastapi import FastAPI, HTTPException

ROOT = Path(__file__).resolve().parent.parent          # 仓库根目录
TRADES_CSV = ROOT / "结果" / "实盘成交明细.csv"

app = FastAPI(title="本地研究数据接口", version="0.1")


def load_trades() -> pd.DataFrame:
    """读成交明细。日期转 datetime；证券代码按字符串读（000021 不能被吃成 21）。"""
    df = pd.read_csv(TRADES_CSV, dtype={"证券代码": str}, encoding="utf-8-sig")
    df["交易日期"] = pd.to_datetime(df["交易日期"])
    return df


def to_records(df: pd.DataFrame) -> list[dict]:
    """DataFrame -> 可 JSON 化的 list[dict]（numpy 标量转成 Python 标量）。"""
    return [
        {k: (v.item() if hasattr(v, "item") else v) for k, v in rec.items()}
        for rec in df.to_dict("records")
    ]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/trades")
def trades(code: str | None = None, start: str | None = None,
           end: str | None = None, limit: int = 100):
    """按条件查成交流水：code=证券代码；start/end=YYYY-MM-DD。"""
    df = load_trades()
    if code:
        df = df[df["证券代码"] == code]
    if start:
        df = df[df["交易日期"] >= pd.to_datetime(start)]
    if end:
        df = df[df["交易日期"] <= pd.to_datetime(end)]
    df = df.sort_values("交易日期")
    rows = df.head(limit).copy()
    rows["交易日期"] = rows["交易日期"].dt.strftime("%Y-%m-%d")
    return {"count": int(len(df)), "rows": to_records(rows)}


@app.get("/stats/summary")
def summary():
    """总览：笔数、买卖分布、三项费用合计（应与 结果/实盘成交明细.md 一致）。"""
    df = load_trades()
    return {
        "总成交笔数": int(len(df)),
        "买入笔数": int((df["方向"] == "买入").sum()),
        "卖出笔数": int((df["方向"] == "卖出").sum()),
        "佣金合计": round(float(df["手续费"].sum()), 2),
        "印花税合计": round(float(df["印花税"].sum()), 2),
        "过户费合计": round(float(df["过户费"].sum()), 2),
    }


@app.get("/stats/group")
def group(by: str = "方向", metric: str = "成交金额"):
    """按任意列分组统计笔数与合计：by=方向 / by=证券名称 / by=原始业务类型…"""
    df = load_trades()
    for col in (by, metric):
        if col not in df.columns:
            raise HTTPException(status_code=400,
                                detail=f"列名不存在：{col}；可用列：{list(df.columns)}")
    r = df.groupby(by).agg(笔数=(metric, "count"), 合计=(metric, "sum")).round(2)
    return to_records(r.reset_index())
