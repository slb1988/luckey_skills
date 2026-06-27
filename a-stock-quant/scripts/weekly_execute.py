"""周一执行 (09:35 跑): 按当前信号在模拟盘调仓。
1) 卖出: 触发止损/止盈/破位/板块轮出的持仓
2) 买入: 主线板块内打分Top, 补足至目标持仓
用沪深300+成分股池 (universe.parquet); 成交价用最新收盘价近似 (模拟T+1)。
输出: data/execute_YYYYMMDD.md
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

DATA = ROOT.parent / "data"
P = strat.PARAMS


def _universe():
    fp = DATA / "universe.parquet"
    if fp.exists():
        return pd.read_parquet(fp)
    import backtest
    return backtest.get_universe()


def execute(force: bool = False):
    today = dt.date.today()
    if today.weekday() != 0 and not force:
        print(f"今天非周一 ({today}), 跳过执行 (force=True 可强制)。")
        return
    uni = _universe()
    code2ind = dict(zip(uni["code"], uni["industry"]))
    acc = pa.load()
    log = [f"# A股量化模拟盘 执行 {today}", ""]
    start = (today - dt.timedelta(days=400)).strftime("%Y-%m-%d")

    # 价格面板 (仅成分股)
    panel = {}
    for code in uni["code"]:
        try:
            h = df_mod.get_hist(code, start)
            if h is not None and len(h) > 130:
                panel[code] = h
        except Exception:
            pass
    prices = {c: float(h["close"].iloc[-1]) for c, h in panel.items()}

    # 市场闸门
    idx = df_mod.get_index_hist("000300", start)
    gate = strat.market_gate(idx, P)
    level = gate["level"]
    log += [f"**市场闸门**: {gate['regime']} (仓位上限 {level:.0%})", ""]

    # 板块强度 (价格动量代理; 若有资金流持续性表则融合)
    def industry_strength():
        scores = {}
        for code, h in panel.items():
            c = h["close"]
            if len(c) < P["mom_form"] + P["mom_skip"] + 5:
                continue
            mom = c.iloc[-P["mom_skip"]-1] / c.iloc[-P["mom_form"]-P["mom_skip"]-1] - 1
            scores.setdefault(code2ind.get(code, "其他"), []).append(mom)
        return sorted({k: np.mean(v) for k, v in scores.items() if len(v) >= 2},
                      key=lambda k: np.mean(scores[k]), reverse=True)
    top_all = industry_strength()
    top_inds = top_all[:P["sector_top_n"]]
    log += [f"**主线板块 Top{P['sector_top_n']}**: {', '.join(top_inds)}", ""]

    # 1) 卖出
    log += ["## 卖出", ""]
    sold = 0
    for code in list(acc["positions"].keys()):
        h = panel.get(code)
        pos = acc["positions"][code]
        if h is None:
            continue
        sec_out = pos["sector"] not in top_all[:P["sector_rotate_out_rank"]]
        reasons = strat.exit_signals(pos, h, sec_out, P)
        if level == 0.0:
            reasons.append("市场闸门清仓")
        if reasons:
            px = prices.get(code, pos["cost"])
            pa.sell(acc, code, px, str(today), ";".join(reasons))
            log.append(f"- 卖出 {code} @ {px:.2f} | {';'.join(reasons)}")
            sold += 1
    if sold == 0:
        log.append("无卖出。")

    # 2) 买入: 主线板块内选股
    log += ["", "## 买入", ""]
    cands = []
    for code, h in panel.items():
        if code2ind.get(code, "其他") not in top_inds or code in acc["positions"]:
            continue
        sc = strat.stock_score(h, P)
        if sc:
            cands.append((code, sc["score"], code2ind.get(code, "其他")))
    cands.sort(key=lambda x: x[1], reverse=True)

    equity = acc["cash"] + sum(prices.get(c, p["cost"]) * p["shares"] for c, p in acc["positions"].items())
    budget = equity * level
    bought = 0
    if level > 0 and cands:
        slots = P["positions_max"] - len(acc["positions"])
        per = budget / P["positions_max"]
        sector_amt = {}
        for c, p in acc["positions"].items():
            sector_amt[p["sector"]] = sector_amt.get(p["sector"], 0) + prices.get(c, p["cost"]) * p["shares"]
        for code, score, ind in cands:
            if slots <= 0 or bought >= 3:
                break
            px = prices.get(code)
            if not px or sector_amt.get(ind, 0) + per > equity * P["w_sector_cap"]:
                continue
            alloc = min(per, equity * P["w_single_cap"])
            shares = int(alloc / px // 100 * 100)
            if pa.buy(acc, code, px, shares, ind, str(today)):
                sector_amt[ind] = sector_amt.get(ind, 0) + px * shares
                slots -= 1; bought += 1
                nm = uni[uni["code"] == code]["name"].iloc[0] if (uni["code"] == code).any() else code
                log.append(f"- 买入 {code} {nm} @ {px:.2f} x{shares} | {ind} | score={score:.3f}")
    if bought == 0:
        log.append("无买入 (无符合条件标的 或 闸门空仓)。")

    pa.mark_to_market(acc, prices, str(today))
    pa.save(acc)
    df_mod._BS.close()
    eq = acc["nav_history"][-1]["nav"]
    log += ["", f"**执行后净值**: {eq:,.0f}, 现金 {acc['cash']:,.0f}, 持仓 {len(acc['positions'])} 只"]
    md = "\n".join(log)
    (DATA / f"execute_{today.strftime('%Y%m%d')}.md").write_text(md, encoding="utf-8")
    print(md)
    return md


if __name__ == "__main__":
    force = "--force" in sys.argv
    execute(force=force)
