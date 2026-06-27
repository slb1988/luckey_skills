"""每日复盘 (21:30 跑): 持仓盈亏 + 止损/止盈预警 + 主线变化; 周五额外出下周调仓名单。
输出: data/review_YYYYMMDD.md (供日报/通知引用), 并打印。
"""
from __future__ import annotations
import sys, json, datetime as dt
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
import datafeed as df_mod
import strategy as strat
import paper_account as pa

DATA = ROOT.parent / "data"
P = strat.PARAMS


def _latest_close(code):
    h = df_mod.get_hist(code, (dt.date.today() - dt.timedelta(days=400)).strftime("%Y-%m-%d"))
    if h is None or h.empty:
        return None, None
    return float(h["close"].iloc[-1]), h


def review():
    today = dt.date.today()
    is_friday = today.weekday() == 4
    acc = pa.load()
    lines = [f"# A股量化模拟盘复盘 {today}", ""]

    # 市场闸门
    idx = df_mod.get_index_hist("000300", (today - dt.timedelta(days=400)).strftime("%Y-%m-%d"))
    gate = strat.market_gate(idx, P) if not idx.empty else {"level": 0.5, "regime": "无指数数据"}
    lines += [f"**市场闸门**: {gate['regime']} (建议总仓位上限 {gate['level']:.0%})", ""]

    # 持仓盈亏 + 预警
    prices = {}
    lines += ["## 持仓盈亏与预警", ""]
    if not acc["positions"]:
        lines.append("当前空仓。")
    else:
        lines.append("| 代码 | 成本 | 现价 | 盈亏% | 状态/预警 |")
        lines.append("|---|---|---|---|---|")
        for code, pos in acc["positions"].items():
            px, h = _latest_close(code)
            if px is None:
                lines.append(f"| {code} | {pos['cost']:.2f} | - | - | 无数据 |")
                continue
            prices[code] = px
            ret = px / pos["cost"] - 1
            warn = []
            if ret <= P["stop_loss"] + 0.02:
                warn.append(f"⚠️临近止损({P['stop_loss']:.0%})")
            peak = max(pos.get("peak", pos["cost"]), px)
            if (peak / pos["cost"] - 1) > P["take_profit_trigger"] and (px / peak - 1) <= P["trail_drawdown"] + 0.02:
                warn.append("⚠️临近移动止盈")
            reasons = strat.exit_signals(pos, h, False, P)
            if reasons:
                warn.append("🔴触发卖出:" + ";".join(reasons))
            lines.append(f"| {code} | {pos['cost']:.2f} | {px:.2f} | {ret:+.1%} | {' '.join(warn) or '正常持有'} |")

    # 账户净值
    equity = acc["cash"] + sum(prices.get(c, p["cost"]) * p["shares"] for c, p in acc["positions"].items())
    tot_ret = equity / acc["init_cash"] - 1
    lines += ["", f"**账户净值**: {equity:,.0f} (初始 {acc['init_cash']:,.0f}, 累计 {tot_ret:+.1%}), 现金 {acc['cash']:,.0f}", ""]

    # 主线板块持续性 (来自采集表)
    fh = DATA / "flow_history.parquet"
    lines += ["## 主线板块 (资金流持续性)", ""]
    if fh.exists():
        hist = pd.read_parquet(fh)
        recent = sorted(hist["date"].unique())[-10:]
        h10 = hist[hist["date"].isin(recent)]
        g = h10.groupby("name")["netflow"]
        persist = g.apply(lambda s: (s > 0).sum() / max(len(s), 1))
        cum5 = h10[h10["date"].isin(recent[-5:])].groupby("name")["netflow"].sum()
        strong = persist[persist >= 0.6]
        top = cum5[cum5.index.isin(strong.index)].nlargest(5)
        for n in top.index:
            lines.append(f"- {n}: 持续性 {persist[n]:.0%}, 近5日净流入 {top[n]/1e8:.2f}亿")
        if len(recent) < 6:
            lines.append(f"\n> 注: 仅采集 {len(recent)} 日, 持续性需≥6采集日才稳健, 继续积累中。")
    else:
        lines.append("尚无资金流历史 (盘后采集任务跑几天后生成)。")

    # 周五: 下周调仓建议
    if is_friday:
        lines += ["", "## 📋 下周调仓建议名单 (周五)", ""]
        lines.append("> 完整选股需全市场扫描, 此处给主线板块方向; 周一执行任务自动生成具体标的。")
        if fh.exists() and gate["level"] > 0:
            for n in (top.index[:P["sector_top_n"]] if 'top' in dir() else []):
                lines.append(f"- 关注主线: **{n}**")
        elif gate["level"] == 0:
            lines.append("- 市场闸门=清仓档, 下周建议空仓观望。")

    df_mod._BS.close()
    md = "\n".join(lines)
    fp = DATA / f"review_{today.strftime('%Y%m%d')}.md"
    fp.write_text(md, encoding="utf-8")
    print(md)
    return md


if __name__ == "__main__":
    review()
