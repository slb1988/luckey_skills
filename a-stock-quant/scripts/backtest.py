"""回测引擎: 周频调仓, 三层策略, 如实计成本。
股票池: 用 baostock 沪深300成分 (或传入 code 列表), 行业用 baostock 行业分类映射。
用法: python backtest.py 2019-01-01 2026-06-26
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import datafeed as df_mod
import strategy as strat
import paper_account as pa

ROOTDIR = ROOT.parent
DATA = ROOTDIR / "data"


def get_universe() -> pd.DataFrame:
    """沪深300成分 + baostock 行业分类。返回 DataFrame[code, name, industry]。"""
    fp = DATA / "universe.parquet"
    if fp.exists():
        return pd.read_parquet(fp)
    bs = df_mod._BS.ensure()
    rs = bs.query_hs300_stocks()
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())  # [updateDate, code, code_name]
    hs = pd.DataFrame(rows, columns=["upd", "bscode", "name"])
    # 行业分类
    rs2 = bs.query_stock_industry()
    irows = []
    while rs2.error_code == "0" and rs2.next():
        irows.append(rs2.get_row_data())  # [updateDate, code, code_name, industry, industryClassification]
    ind = pd.DataFrame(irows, columns=["upd", "bscode", "name2", "industry", "cls"])
    m = hs.merge(ind[["bscode", "industry"]], on="bscode", how="left")
    m["code"] = m["bscode"].str.split(".").str[1]
    m["industry"] = m["industry"].replace("", "其他").fillna("其他")
    out = m[["code", "name", "industry", "bscode"]]
    out.to_parquet(fp)
    return out


def load_panel(universe: pd.DataFrame, start: str, end: str) -> dict:
    """预加载所有成分股历史 -> {code: df}。带 parquet 缓存(datafeed内置)。"""
    panel = {}
    pre_start = (pd.Timestamp(start) - pd.Timedelta(days=260)).strftime("%Y-%m-%d")
    for i, row in universe.iterrows():
        try:
            h = df_mod.get_hist(row["code"], pre_start, end)
            if h is not None and len(h) > 130:
                panel[row["code"]] = h
        except Exception:
            pass
        if (i + 1) % 50 == 0:
            print(f"  loaded {i+1}/{len(universe)}")
    return panel


def run(start: str, end: str, init_cash=1_000_000.0):
    P = strat.PARAMS
    uni = get_universe()
    code2ind = dict(zip(uni["code"], uni["industry"]))
    print(f"universe: {len(uni)} stocks, {uni['industry'].nunique()} industries")
    print("loading price panel (cached after first run)...")
    panel = load_panel(uni, start, end)
    print(f"panel: {len(panel)} stocks have data")
    idx = df_mod.get_index_hist("000300", (pd.Timestamp(start) - pd.Timedelta(days=260)).strftime("%Y-%m-%d"), end)

    # 交易日历 = 指数日期, 取每周最后一个交易日做调仓
    idx = idx[~idx.index.duplicated(keep="last")].sort_index()
    idx.index = pd.to_datetime(idx.index)
    cal = pd.DatetimeIndex(idx.loc[start:end].index)
    iso = cal.isocalendar()
    weekly = pd.Series(cal, index=range(len(cal))).groupby(
        [iso.year.values, iso.week.values]).last().tolist()
    weekly = [d for d in weekly if d in set(cal)]

    acc = pa._default(init_cash)
    bench0 = float(idx.loc[start:end]["close"].iloc[0])

    def industry_momentum(d):
        """用成分股按行业聚合的中期动量作为板块强度 (回测内代理 RRG, 不依赖实时资金流接口)。"""
        scores = {}
        for code, h in panel.items():
            hh = h.loc[:d]
            if len(hh) < P["mom_form"] + P["mom_skip"] + 5:
                continue
            c = hh["close"]
            mom = c.iloc[-P["mom_skip"]-1] / c.iloc[-P["mom_form"]-P["mom_skip"]-1] - 1
            ind = code2ind.get(code, "其他")
            scores.setdefault(ind, []).append(mom)
        agg = {k: np.mean(v) for k, v in scores.items() if len(v) >= 2}
        return sorted(agg, key=agg.get, reverse=True)

    for d in weekly:
        prices = {c: float(h.loc[:d]["close"].iloc[-1]) for c, h in panel.items() if d in h.index or (h.loc[:d].shape[0] > 0)}
        # 市场闸门
        gate = strat.market_gate(idx.loc[:d], P)
        level = gate["level"]
        # 卖出检查
        for code in list(acc["positions"].keys()):
            h = panel.get(code)
            if h is None:
                continue
            hh = h.loc[:d]
            if hh.empty:
                continue
            pos = acc["positions"][code]
            top_inds = industry_momentum(d)[:P["sector_rotate_out_rank"]]
            sec_out = pos["sector"] not in top_inds
            reasons = strat.exit_signals(pos, hh, sec_out, P)
            if level == 0.0:
                reasons.append("市场闸门清仓")
            if reasons:
                pa.sell(acc, code, float(hh["close"].iloc[-1]), str(d.date()), ";".join(reasons))
        # 选主线板块
        top_inds = industry_momentum(d)[:P["sector_top_n"]]
        # 选股: 主线板块内打分
        cands = []
        for code, h in panel.items():
            if code2ind.get(code, "其他") not in top_inds:
                continue
            hh = h.loc[:d]
            sc = strat.stock_score(hh, P)
            if sc:
                cands.append((code, sc["score"], code2ind.get(code, "其他")))
        cands.sort(key=lambda x: x[1], reverse=True)
        # 目标持仓
        equity = acc["cash"] + sum(prices.get(c, p["cost"]) * p["shares"] for c, p in acc["positions"].items())
        target_n = P["positions_max"]
        budget = equity * level
        if level > 0 and budget > 0 and cands:
            held = set(acc["positions"].keys())
            slots = target_n - len(held)
            per = budget / target_n
            sector_amt = {}
            for c, p in acc["positions"].items():
                sector_amt[p["sector"]] = sector_amt.get(p["sector"], 0) + prices.get(c, p["cost"]) * p["shares"]
            bought = 0
            for code, score, ind in cands:
                if slots <= 0 or bought >= 3:  # 单日最多新开3只
                    break
                if code in held:
                    continue
                px = prices.get(code)
                if not px:
                    continue
                if sector_amt.get(ind, 0) + per > equity * P["w_sector_cap"]:
                    continue
                alloc = min(per, equity * P["w_single_cap"])
                shares = int(alloc / px // 100 * 100)
                if pa.buy(acc, code, px, shares, ind, str(d.date())):
                    sector_amt[ind] = sector_amt.get(ind, 0) + px * shares
                    slots -= 1; bought += 1
        pa.mark_to_market(acc, prices, str(d.date()))

    # 绩效
    nav = pd.DataFrame(acc["nav_history"])
    nav["date"] = pd.to_datetime(nav["date"])
    nav = nav.set_index("date")
    rets = nav["nav"].pct_change().dropna()
    total_ret = nav["nav"].iloc[-1] / init_cash - 1
    bench_ret = float(idx.loc[start:end]["close"].iloc[-1]) / bench0 - 1
    years = max((nav.index[-1] - nav.index[0]).days / 365.25, 0.1)
    cagr = (1 + total_ret) ** (1 / years) - 1
    sharpe = rets.mean() / (rets.std() + 1e-9) * np.sqrt(52)
    cummax = nav["nav"].cummax()
    mdd = ((nav["nav"] - cummax) / cummax).min()
    sells = [t for t in acc["trades"] if t["side"] == "SELL"]
    wins = [t for t in sells if t.get("pnl", 0) > 0]
    winrate = len(wins) / len(sells) if sells else 0
    total_fee = sum(t["fee"] for t in acc["trades"])

    result = dict(
        period=f"{start}~{end}", weeks=len(weekly),
        final_nav=round(nav["nav"].iloc[-1], 2), total_return=round(total_ret, 4),
        cagr=round(cagr, 4), bench_return_hs300=round(bench_ret, 4),
        excess=round(total_ret - bench_ret, 4), sharpe=round(float(sharpe), 3),
        max_drawdown=round(float(mdd), 4), trades=len(acc["trades"]),
        sells=len(sells), winrate=round(winrate, 3), total_fee=round(total_fee, 2),
    )
    print("\n=== 回测结果 ===")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    nav.to_parquet(DATA / "backtest_nav.parquet")
    (DATA / "backtest_result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    df_mod._BS.close()
    return result


if __name__ == "__main__":
    s = sys.argv[1] if len(sys.argv) > 1 else "2019-01-01"
    e = sys.argv[2] if len(sys.argv) > 2 else dt.date.today().strftime("%Y-%m-%d")
    run(s, e)
