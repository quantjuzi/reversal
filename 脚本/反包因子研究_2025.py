# -*- coding: utf-8 -*-
"""用聚宽 2025 标准因子数据做反包基准、策略复现和单因子分组测试。

默认输入：
    数据/聚宽因子_2025-01-01_2025-09-30.csv

默认输出：
    结果/反包因子研究_2025/

复现对象：
    2026 年确定的 A/B/C 三套策略，规则未改。

研究口径：
    - 信号日：前一日涨停，当日断板
    - 买入：下一交易日开盘
    - 卖出：再下一交易日成交均价
    - 成本：整手、佣金、印花税、过户费、双边滑点
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd


项目目录 = Path(__file__).resolve().parents[1]
脚本目录 = 项目目录 / "脚本"
数据目录 = 项目目录 / "数据"

sys.path.insert(0, str(脚本目录))

import 反包因子研究_通用版 as 通用研究  # noqa: E402


研究开始 = pd.Timestamp("2025-01-01")
研究结束 = pd.Timestamp("2025-09-30")

默认数据文件 = (
    数据目录 / "聚宽因子_2025-01-01_2025-09-30.csv"
)
默认输出目录 = 项目目录 / "结果" / "反包因子研究_2025"

因子列表 = [
    "成交额_亿",
    "实体涨幅",
    "断板日涨跌幅",
    "竞价涨幅",
    "连板数",
]

策略定义 = {
    "A：2连板 + 成交额10亿以上 + 实体>2%": (
        lambda 样本: 样本["前一日连板数"].ge(2)
        & 样本["成交额_亿"].ge(10)
        & 样本["实体涨幅"].gt(2)
    ),
    "B：2连板 + 成交额5亿以上 + 实体>2%": (
        lambda 样本: 样本["前一日连板数"].ge(2)
        & 样本["成交额_亿"].ge(5)
        & 样本["实体涨幅"].gt(2)
    ),
    "C：2连板 + 成交额10亿以上 + 实体>1%": (
        lambda 样本: 样本["前一日连板数"].ge(2)
        & 样本["成交额_亿"].ge(10)
        & 样本["实体涨幅"].gt(1)
    ),
}

报告列 = [
    "策略",
    "交易数",
    "净胜率",
    "平均净收益率",
    "平均盈利",
    "平均亏损",
    "盈亏比",
    "复利年化",
    "最高资金占用",
    "平均资金占用",
    "平均资金年化",
    "最高资金年化",
    "固定10万元账户年化",
    "固定账户资金是否足够",
    "累计净盈亏",
]


def 年化(区间收益率: float, 交易日数: int) -> float:
    """把区间收益率按 252 个交易日折算成复利年化。"""

    if 交易日数 <= 0 or 区间收益率 <= -1:
        return np.nan
    return ((1 + 区间收益率) ** (252 / 交易日数) - 1) * 100


def 补全指标(
    指标: dict[str, object],
    交易日数: int,
    固定账户资金: float,
) -> dict[str, object]:
    """补齐固定账户年化和统一报表列。"""

    结果 = dict(指标)
    for 列 in 报告列:
        结果.setdefault(列, np.nan)

    if 结果.get("交易数", 0) == 0:
        return 结果

    平均资金年化 = float(结果["平均资金年化"])
    结果["复利年化"] = 平均资金年化

    累计净盈亏 = float(结果["累计净盈亏"])
    固定账户收益率 = 累计净盈亏 / 固定账户资金
    结果["固定10万元账户年化"] = 年化(
        固定账户收益率,
        交易日数,
    )
    最高资金占用 = float(结果["最高资金占用"])
    结果["固定账户资金是否足够"] = (
        "是" if 最高资金占用 <= 固定账户资金 else "否"
    )
    return 结果


def 构建研究数据(
    原始数据: pd.DataFrame,
    参数: 通用研究.研究参数,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series]:
    """构建 2025 反包交易、交易日历和策略标记。"""

    通用研究.研究开始 = 研究开始
    通用研究.研究结束 = 研究结束

    数据 = 通用研究.清洗数据(原始数据)
    交易 = 通用研究.构建反包交易(数据)
    交易 = 通用研究.限定研究区间(交易)
    交易 = 通用研究.计算交易成本(交易, 参数)

    交易日历 = (
        数据.loc[
            数据["time"].between(研究开始, 研究结束),
            "time",
        ]
        .drop_duplicates()
        .sort_values()
        .reset_index(drop=True)
    )
    if 交易.empty:
        return 数据, 交易, 交易日历

    for 名称, 条件 in 策略定义.items():
        交易[名称] = 条件(交易).astype(int)
    return 数据, 交易, 交易日历


def 生成策略汇总(
    交易: pd.DataFrame,
    交易日历: pd.Series,
    参数: 通用研究.研究参数,
    固定账户资金: float,
) -> pd.DataFrame:
    """计算基准和 A/B/C 三套历史反包条件。"""

    样本列表 = [("全部反包", 交易)]
    for 名称, 条件 in 策略定义.items():
        样本列表.append((名称, 交易.loc[条件(交易)]))

    交易日数 = int(pd.to_datetime(交易日历).nunique())
    行 = []
    for 名称, 样本 in 样本列表:
        指标 = 通用研究.计算分组指标(
            名称,
            样本,
            交易日历,
            参数,
        )
        指标["策略"] = 名称
        指标 = 补全指标(指标, 交易日数, 固定账户资金)
        行.append(指标)
    return pd.DataFrame(行)[报告列]


def 生成因子分组(
    交易: pd.DataFrame,
    交易日历: pd.Series,
    参数: 通用研究.研究参数,
    固定账户资金: float,
) -> tuple[pd.DataFrame, dict[str, pd.DataFrame]]:
    """逐个因子分组，返回总表和单因子表。"""

    交易日数 = int(pd.to_datetime(交易日历).nunique())
    总表 = []
    单因子表: dict[str, pd.DataFrame] = {}
    for 因子 in 因子列表:
        行 = []
        for 名称, 样本 in 通用研究.因子分组(
            交易,
            因子,
            参数,
        ):
            指标 = 通用研究.计算分组指标(
                名称,
                样本,
                交易日历,
                参数,
            )
            指标["因子"] = 因子
            指标["分组"] = 名称
            指标 = 补全指标(指标, 交易日数, 固定账户资金)
            行.append(指标)
        表格 = pd.DataFrame(行)
        单因子表[因子] = 表格
        总表.append(表格.assign(因子=因子))
    return pd.concat(总表, ignore_index=True), 单因子表


def 写Markdown(表格: pd.DataFrame) -> str:
    """把结果表写成 Markdown。"""

    列 = [str(列名) for 列名 in 表格.columns]
    内容 = [
        "| " + " | ".join(列) + " |",
        "| " + " | ".join("---" for _ in 列) + " |",
    ]
    for 行 in 表格.itertuples(index=False, name=None):
        内容.append(
            "| "
            + " | ".join(
                "" if pd.isna(值) else str(值)
                for 值 in 行
            )
            + " |"
        )
    return "\n".join(内容)


def 保存结果(
    输出目录: Path,
    交易: pd.DataFrame,
    策略汇总: pd.DataFrame,
    因子总表: pd.DataFrame,
    单因子表: dict[str, pd.DataFrame],
) -> None:
    """保存 CSV 和 Markdown 报表。"""

    输出目录.mkdir(parents=True, exist_ok=True)

    策略汇总.to_csv(
        输出目录 / "反包策略汇总_2025.csv",
        index=False,
        encoding="utf-8-sig",
    )
    因子总表.to_csv(
        输出目录 / "反包因子分组汇总_2025.csv",
        index=False,
        encoding="utf-8-sig",
    )

    明细列 = [
        "code",
        "time",
        "前一日连板数",
        "成交额_亿",
        "实体涨幅",
        "断板日涨跌幅",
        "竞价涨幅",
        "买入日期",
        "买入价格",
        "卖出日期",
        "卖出价格",
        "股数",
        "净收益率",
        "净盈亏",
    ] + list(策略定义)
    可用列 = [列 for 列 in 明细列 if 列 in 交易.columns]
    交易[可用列].to_csv(
        输出目录 / "反包交易明细_2025.csv",
        index=False,
        encoding="utf-8-sig",
    )

    for 因子, 表格 in 单因子表.items():
        表格.to_csv(
            输出目录 / f"{因子}_分组统计.csv",
            index=False,
            encoding="utf-8-sig",
        )

    说明 = [
        "# 2025 反包策略与因子测试",
        "",
        "- 研究区间：2025-01-01 至 2025-09-30",
        "- 买入：信号日下一交易日开盘",
        "- 卖出：再下一交易日成交均价",
        "- 成本：整手、佣金、印花税、过户费、双边滑点",
        "- `复利年化` 使用平均资金年化口径，不等于固定账户收益率。",
        "- 固定账户年化按 10 万元计算；资金是否足够见对应列。",
        "",
        "## 策略汇总",
        "",
        写Markdown(策略汇总),
        "",
        "## 单因子文件",
        "",
    ]
    for 因子 in 单因子表:
        说明.append(f"- `{因子}_分组统计.csv`")
    说明.extend(
        [
            "",
            "## 文件",
            "",
            "- `反包策略汇总_2025.csv`",
            "- `反包因子分组汇总_2025.csv`",
            "- `反包交易明细_2025.csv`",
            "",
        ]
    )
    (输出目录 / "反包测试报告_2025.md").write_text(
        "\n".join(说明),
        encoding="utf-8",
    )


def 解析参数() -> argparse.Namespace:
    """读取命令行参数。"""

    解析器 = argparse.ArgumentParser(description=__doc__)
    解析器.add_argument(
        "--factor-file",
        type=Path,
        default=默认数据文件,
    )
    解析器.add_argument(
        "--output-dir",
        type=Path,
        default=默认输出目录,
    )
    解析器.add_argument(
        "--fixed-capital",
        type=float,
        default=100_000.0,
        help="固定账户参考资金，默认 10 万元。",
    )
    解析器.add_argument(
        "--no-groups",
        action="store_true",
        help="只跑基准和 A/B/C，不做单因子分组。",
    )
    return 解析器.parse_args()


def main() -> None:
    """执行 2025 反包测试。"""

    参数值 = 解析参数()
    if not 参数值.factor_file.exists():
        raise FileNotFoundError(
            f"未找到 2025 标准因子文件：{参数值.factor_file}\n"
            "请先在聚宽研究环境运行：python 脚本/下载聚宽2025反包数据.py"
        )

    原始数据 = 通用研究.读取数据(参数值.factor_file)
    参数 = 通用研究.研究参数()
    数据, 交易, 交易日历 = 构建研究数据(原始数据, 参数)
    if 交易.empty:
        raise ValueError("2025 区间没有可统计的反包交易。")

    策略汇总 = 生成策略汇总(
        交易,
        交易日历,
        参数,
        参数值.fixed_capital,
    )

    if 参数值.no_groups:
        因子总表 = pd.DataFrame(columns=["因子", *报告列])
        单因子表: dict[str, pd.DataFrame] = {}
    else:
        因子总表, 单因子表 = 生成因子分组(
            交易,
            交易日历,
            参数,
            参数值.fixed_capital,
        )

    保存结果(
        参数值.output_dir,
        交易,
        策略汇总,
        因子总表,
        单因子表,
    )

    print("2025 反包测试完成")
    print(策略汇总.to_string(index=False))
    print(f"\n输出目录：{参数值.output_dir}")


if __name__ == "__main__":
    main()
