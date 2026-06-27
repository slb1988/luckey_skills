"""盘后采集 (15:30 跑): 抓当日热点 + 行业资金流, 累积进10日持续性表。只采集不交易。
输出: data/flow_history.parquet (长表 name,date,netflow,pct), data/hotspots_YYYYMMDD.json
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import datafeed as df_mod

DATA = ROOT.parent / "data"
FLOW_HIST = DATA / "flow_history.parquet"


def collect():
    today = dt.date.today().strftime("%Y%m%d")
    out = {"date": today, "collected_at": dt.datetime.now().isoformat(timespec="seconds")}

    # 1) 行业资金流 (今日)
    try:
        sff = df_mod.sector_fund_flow(indicator="今日", sector_type="行业资金流")
        flow_col = [c for c in sff.columns if "主力净流入-净额" in c][0]
        pct_col = [c for c in sff.columns if "涨跌幅" in c][0]
        rows = sff[["名称", flow_col, pct_col]].copy()
        rows.columns = ["name", "netflow", "pct"]
        rows["date"] = today
        rows["netflow"] = pd.to_numeric(rows["netflow"], errors="coerce")
        # 累积进历史长表
        if FLOW_HIST.exists():
            hist = pd.read_parquet(FLOW_HIST)
            hist = hist[hist["date"] != today]  # 去重当日
            hist = pd.concat([hist, rows], ignore_index=True)
        else:
            hist = rows
        # 仅保留最近30个采集日
        keep_dates = sorted(hist["date"].unique())[-30:]
        hist = hist[hist["date"].isin(keep_dates)]
        hist.to_parquet(FLOW_HIST)
        out["sector_top5_inflow"] = rows.nlargest(5, "netflow")[["name", "netflow", "pct"]].to_dict("records")
        out["sector_count"] = len(rows)
    except Exception as e:
        out["sector_error"] = f"{type(e).__name__}: {e}"

    # 2) 涨停股池 (强势梯队)
    try:
        zt = df_mod.zt_pool(today)
        out["zt_count"] = len(zt)
        if "连板数" in zt.columns:
            out["zt_max_boards"] = int(pd.to_numeric(zt["连板数"], errors="coerce").max())
    except Exception as e:
        out["zt_error"] = f"{type(e).__name__}: {e}"

    # 3) 人气榜 Top10
    try:
        hot = df_mod.hot_rank()
        namecol = [c for c in hot.columns if "名称" in c or "股票" in c]
        if namecol:
            out["hot_top10"] = hot[namecol[0]].head(10).tolist()
    except Exception as e:
        out["hot_error"] = f"{type(e).__name__}: {e}"

    # 4) 资金流持续性快照 (近10采集日)
    try:
        if FLOW_HIST.exists():
            hist = pd.read_parquet(FLOW_HIST)
            recent = sorted(hist["date"].unique())[-10:]
            h10 = hist[hist["date"].isin(recent)]
            g = h10.groupby("name")["netflow"]
            persist = (g.apply(lambda s: (s > 0).sum() / max(len(s), 1)))
            cum5 = h10[h10["date"].isin(recent[-5:])].groupby("name")["netflow"].sum()
            strong = persist[persist >= 0.6].index
            sustained = cum5[cum5.index.isin(strong)].nlargest(8)
            out["sustained_inflow_sectors"] = [
                {"name": n, "persist": round(float(persist[n]), 2), "cum5_netflow": float(sustained[n])}
                for n in sustained.index]
            out["collect_days"] = len(recent)
    except Exception as e:
        out["persist_error"] = f"{type(e).__name__}: {e}"

    df_mod._BS.close()
    fp = DATA / f"hotspots_{today}.json"
    fp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return out


if __name__ == "__main__":
    collect()
