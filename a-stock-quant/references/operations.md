# 常用操作速查

工作目录: `C:\Users\admin\.violoop\skills\a-stock-quant\scripts`
Python: 3.11.8 (系统 python)

## 日常
```powershell
cd C:\Users\admin\.violoop\skills\a-stock-quant\scripts
python daily_collect.py            # 采集今日热点+行业资金流 (累积持续性表)
python daily_review.py             # 复盘: 持仓预警+主线变化 (周五自动出名单)
python weekly_execute.py           # 周一才执行 (非周一直接跳过)
python weekly_execute.py --force   # 强制立即调仓 (测试/手动)
```

## 回测与调参
```powershell
python backtest.py 2019-01-01 2026-06-26   # 含牛熊样本回测
python backtest.py 2024-01-01 2026-06-26   # 近2年
# 调参: 编辑 strategy.py 的 PARAMS, 重跑 backtest.py
# 结果: data/backtest_result.json, data/backtest_nav.parquet
```

## 查看模拟盘状态
```powershell
Get-Content ..\data\paper_account.json | ConvertFrom-Json | Select cash, init_cash
Get-Content ..\data\review_*.md | Select-Object -Last 40   # 最新复盘
```

## 重置模拟盘
```powershell
Remove-Item ..\data\paper_account.json   # 下次执行会重建为100万初始
```

## 缓存管理
- 历史日线: data/hist/*.parquet (增量, 不用手动清)
- 当日缓存: data/cache/*.parquet (按日, 可定期清理旧文件)
- 资金流持续性: data/flow_history.parquet (滚动保留最近30采集日)
- 股票池: data/universe.parquet (沪深300成分+行业, 删除可重建)

## 依赖
```powershell
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple baostock akshare adata pandas numpy pyarrow duckdb
# akshare 接口失效时: pip install --upgrade akshare
```

## 故障排查
- baostock 拉空: 检查指数代码映射 (沪深300=sh.000300), 见 datafeed._INDEX_MAP
- akshare RemoteDisconnected/封IP: 降低频率, 盘后跑, 或等几分钟重试
- parquet 读出 RangeIndex: datafeed 已自动恢复 DatetimeIndex
- agenda 任务用绝对路径 + cwd 指向 scripts 目录
