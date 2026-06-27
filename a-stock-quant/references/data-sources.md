# 数据源对比与接口清单

## 选型 (全免费, 2026已验证)

| 层 | 源 | 角色 | 注意 |
|---|---|---|---|
| L0 历史底仓 | baostock | 全history日线/财务, 最稳免token | 需bs.login(); 指数代码需显式映射 |
| L1 盘后增强 | akshare | 行业资金流/涨停池/人气榜/概念成分/news | 15:00后跑, 本地缓存, 防封IP |
| L2 准实时 | adata→efinance→akshare | 延迟快照, 多源失败转移 | adata带代理切换抗封 |

## 反爬现实 (2025-2026)
akshare/efinance/adata 共用东财/新浪源, 被激进反爬(封IP/滑块)。
缓解: 本地parquet缓存+增量更新(datafeed内置), 请求间隔, 多源失败转移, 盘后低频跑。
**不做日内高频实时**, 盘后批量最稳 (也符合非短线定位)。

## 关键接口 (datafeed.py 封装)
- get_hist(code, start, end) — 单股前复权日线, parquet缓存
- get_index_hist(code, start, end) — 指数日线 (000300沪深300/000985中证全指)
- sector_fund_flow(indicator, sector_type) — 行业/概念资金流排名
- zt_pool(date) — 涨停股池
- hot_rank() — 人气榜
- realtime(codes) — 准实时, 多源失败转移

## baostock 指数代码映射 (易错点)
个股前缀映射: 60/68/9→sh, 00/30/20→sz, 4/8→bj
但**指数前缀不同**, 必须用 _INDEX_MAP:
- 沪深300 = sh.000300 (不是sz!)
- 中证全指 = sh.000985
- 中证500 = sh.000905
- 上证50 = sh.000016
- 创业板指 = sz.399006

## 升级路径 (可选)
- tushare pro (¥200-500/yr): 更稳的财务/龙虎榜/资金流, 需token+积分
- 券商QMT/Ptrade: 真实实时+实盘执行, 需实盘账户(常见¥50万门槛)
