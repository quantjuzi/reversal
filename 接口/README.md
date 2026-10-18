# 本地数据接口

把 `结果/实盘成交明细.csv` 包成一个本地查询接口，给复盘和研究脚本用。
纯本地、只读、不接交易通道，不是生产服务。

## 跑起来

在仓库根目录：

```bash
pip install -r requirements.txt
cd 接口
uvicorn server:app --reload
```

打开 <http://127.0.0.1:8000/docs>，可以直接点着试。
如果 `uvicorn` 不在 PATH，用 `python -m uvicorn server:app --reload`。

## 端点

| 端点 | 作用 |
| --- | --- |
| `GET /health` | 存活检查 |
| `GET /trades?code=&start=&end=&limit=` | 按代码/日期区间查成交，默认最多 100 条 |
| `GET /stats/summary` | 总览：笔数、买卖分布、佣金/印花税/过户费合计 |
| `GET /stats/group?by=方向&metric=成交金额` | 按任意列分组统计 |

## 设计口径

- 直接读 `结果/实盘成交明细.csv`，不上数据库：1,365 条，简单、可核对。
- 只读，不写文件；没有登录，只在本机跑。
- `/stats/summary` 的数字和 `结果/实盘成交明细.md` 一致：1,365 笔、买 716、卖 649，
  佣金 9,216.89、印花税 8,740.86、过户费 86.73。
- 证券代码按字符串读，`000021` 不会变成 `21`；CSV 用 `utf-8-sig` 读。
- 这是数据查询接口，不是交易接口；不接 CTP/QMT/PTrade，不下单。

## 测试

```bash
python 测试/接口测试.py
```

测试用内存里的 TestClient，不占端口；检查健康检查、过滤、汇总数字和非法列名。
