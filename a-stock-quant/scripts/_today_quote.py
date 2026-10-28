# -*- coding: utf-8 -*-
"""一次性查询: 大盘指数行情 + 估值(PE/PB/历史分位). 数据源 akshare."""
import sys, io, warnings
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")
warnings.filterwarnings("ignore")
import akshare as ak
import pandas as pd

WATCH = {  # code -> 名称
    "000001": "上证指数", "399001": "深证成指", "399006": "创业板指",
    "000300": "沪深300", "000905": "中证500", "000852": "中证1000",
    "000688": "科创50", "000016": "上证50", "399005": "中小100",
}

print("=" * 60)
print("一、今日大盘行情")
print("=" * 60)
try:
    spot = ak.stock_zh_index_spot_em(symbol="沪深重要指数")
    spot = spot[spot["代码"].isin(WATCH)].copy()
    spot["代码"] = spot["代码"].str[2:]
    spot["名称"] = spot["代码"].map(WATCH)
    cols = [c for c in ["名称", "最新价", "涨跌幅", "涨跌额", "成交额"] if c in spot.columns]
    print(spot[cols].to_string(index=False))
except Exception as e:
    print("东财接口失败:", e)
    try:
        sina = ak.stock_zh_index_spot_sina()
        sina = sina[sina["代码"].isin(list(WATCH))].copy()
        sina["名称"] = sina["代码"].map(WATCH)
        print(sina[["名称", "最新价", "涨跌幅"]].to_string(index=False))
    except Exception as e2:
        print("新浪接口也失败:", e2)

print()
print("=" * 60)
print("二、主要指数估值 (中证指数官网最新收盘数据)")
print("=" * 60)
cs_map = {"沪深300": "000300", "中证500": "000905", "中证1000": "000852",
          "上证50": "000016", "创业板指": "399006", "科创50": "000688"}
for name in cs_map:
    try:
        v = ak.stock_zh_index_value_csindex(symbol=name)
        row = v.iloc[-1]
        print(f"{name:<6} 日期={row['日期']}  市盈率1(TTM)={row['市盈率1']}  市盈率2(静态)={row['市盈率2']}  股息率={row['股息率1']}%")
    except Exception as e:
        print(f"{name}: 获取失败 {e}")

print()
print("=" * 60)
print("三、历史分位 (乐咕乐股, PE-TTM / PB 近十年分位)")
print("=" * 60)
lg_map = ["沪深300", "上证50", "中证500", "上证指数", "上证380", "创业板50"]
for name in lg_map:
    try:
        pe = ak.stock_index_pe_lg(symbol=name)
        pe["日期"] = pd.to_datetime(pe["日期"])
        pe = pe[pe["日期"] >= pd.Timestamp.now() - pd.Timedelta(days=3652)]  # 近10年
        col = "滚动市盈率" if "滚动市盈率" in pe.columns else pe.columns[2]
        latest = pe.iloc[-1]
        cur = float(latest[col])
        pct = (pe[col].astype(float) < cur).mean() * 100
        print(f"{name:<6} PE-TTM={cur:.2f}  近10年分位={pct:.1f}%  (样本{len(pe)}条, 截至{latest['日期'].date()})")
    except Exception as e:
        print(f"{name}: 获取失败 {type(e).__name__} {e}")
try:
    for name in ["沪深300", "上证50", "中证500"]:
        pb = ak.stock_index_pb_lg(symbol=name)
        pb["日期"] = pd.to_datetime(pb["日期"])
        pb = pb[pb["日期"] >= pd.Timestamp.now() - pd.Timedelta(days=3652)]
        col = "市净率" if "市净率" in pb.columns else pb.columns[2]
        latest = pb.iloc[-1]
        cur = float(latest[col])
        pct = (pb[col].astype(float) < cur).mean() * 100
        print(f"{name:<6} PB={cur:.2f}  近10年分位={pct:.1f}%")
except Exception as e:
    print(f"PB获取失败: {e}")
