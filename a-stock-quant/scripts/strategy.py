"""策略信号: 三层「主线动量 + 板块轮动」(非短线, 周频)。
①市场闸门 -> 总仓位档  ②板块轮动 -> 选主线行业  ③个股动量 -> 选标的
所有参数集中在 PARAMS, 便于回测调参。
"""
from __future__ import annotations
import numpy as np
import pandas as pd

PARAMS = dict(
    # 市场闸门
    idx_ma_fast=20, idx_ma_mid=60, idx_ma_slow=120,
    # 板块
    sector_top_n=3, sector_rotate_out_rank=6,
    flow_persist_window=10, flow_persist_min_pos=6,   # 近10日≥6日净流入为正
    flow_spike_max_share=0.5,                          # 单日占比>50% 视为一日游剔除
    rotate_hysteresis=0.10,                            # 新板块需高于在持≥10%
    # 个股动量
    mom_form=60, mom_skip=5,                            # 过去60日, 跳过最近5日
    stk_ma_fast=20, stk_ma_mid=60,
    min_amount_20d=1e8,                                # 20日均额≥1亿
    min_price=2.0,
    positions_max=8, positions_min=5,
    w_single_cap=0.20, w_sector_cap=0.40, cash_min=0.10,
    # 风控
    stop_loss=-0.08, take_profit_trigger=0.15, trail_drawdown=-0.10,
    score_w=(0.5, 0.3, 0.2),  # 动量/趋势/风险调整
)


def ma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n).mean()


# ---------- ①市场闸门 ----------
def market_gate(index_df: pd.DataFrame, p=PARAMS) -> dict:
    """返回 {'level': 仓位上限, 'regime': 文字}。index_df 需含 close, 按日期升序。"""
    c = index_df["close"]
    if len(c) < p["idx_ma_slow"] + 1:
        return {"level": 0.5, "regime": "数据不足-保守半仓"}
    ma20, ma60, ma120 = ma(c, p["idx_ma_fast"]), ma(c, p["idx_ma_mid"]), ma(c, p["idx_ma_slow"])
    px = c.iloc[-1]; m20, m60, m120 = ma20.iloc[-1], ma60.iloc[-1], ma120.iloc[-1]
    if px < m120 and m20 < m60:
        return {"level": 0.0, "regime": "确认熊市-清仓观望"}
    if px < m60:
        return {"level": 0.2, "regime": "空头-仅守最强仓"}
    if px > m60 and m20 > m60:
        return {"level": 0.9, "regime": "多头排列-满仓档"}
    return {"level": 0.5, "regime": "弱多/震荡-半仓"}


# ---------- ②板块轮动 ----------
def score_sectors(flow_today: pd.DataFrame, flow_5d: pd.DataFrame,
                  flow_10d_hist: pd.DataFrame | None = None, p=PARAMS) -> pd.DataFrame:
    """对行业打分。flow_today/flow_5d 为 akshare stock_sector_fund_flow_rank 结果。
    flow_10d_hist (可选): 列=[name, date, netflow] 长表, 用于持续性与一日游过滤。
    返回 DataFrame[name, score, rs_ratio, rs_mom, persist, leading] 按 score 降序。"""
    def pick_flow(df):
        col = [c for c in df.columns if "主力净流入-净额" in c]
        return df[["名称", col[0]]].rename(columns={"名称": "name", col[0]: "flow"})
    t = pick_flow(flow_today); f5 = pick_flow(flow_5d).rename(columns={"flow": "flow5"})
    m = t.merge(f5, on="name", how="inner")
    # RS 代理: 用涨跌幅相对; 若有指数历史可换真实 RRG
    pct_col = [c for c in flow_today.columns if "涨跌幅" in c]
    if pct_col:
        m = m.merge(flow_today[["名称", pct_col[0]]].rename(columns={"名称": "name", pct_col[0]: "pct"}), on="name", how="left")
    else:
        m["pct"] = 0.0
    # 标准化
    def z(x):
        x = pd.to_numeric(x, errors="coerce")
        return (x - x.mean()) / (x.std() + 1e-9)
    m["rs_ratio"] = z(m["flow5"])      # 5日资金强度 ~ 相对强度趋势代理
    m["rs_mom"] = z(m["flow"])          # 今日边际 ~ 动量代理
    # 持续性分
    if flow_10d_hist is not None and not flow_10d_hist.empty:
        g = flow_10d_hist.groupby("name")
        persist = g["netflow"].apply(lambda s: (s > 0).sum() / max(len(s), 1))
        spike = g["netflow"].apply(lambda s: (s.max() / (s[s > 0].sum() + 1e-9)) if (s > 0).any() else 1.0)
        m = m.merge(persist.rename("persist"), on="name", how="left")
        m = m.merge(spike.rename("spike_share"), on="name", how="left")
        m["persist"] = m["persist"].fillna(0.0)
        m["spike_share"] = m["spike_share"].fillna(1.0)
        m.loc[m["persist"] < p["flow_persist_min_pos"] / p["flow_persist_window"], "persist"] = 0.0
        m.loc[m["spike_share"] > p["flow_spike_max_share"], "persist"] = 0.0  # 一日游剔除
    else:
        m["persist"] = (m["flow5"] > 0).astype(float)  # 退化: 5日为正
        m["spike_share"] = np.nan
    pz = z(m["persist"])
    m["score"] = 0.4 * m["rs_ratio"] + 0.3 * m["rs_mom"] + 0.3 * pz
    m["leading"] = (m["rs_ratio"] > 0) & (m["rs_mom"] > 0)
    return m.sort_values("score", ascending=False).reset_index(drop=True)


def pick_main_sectors(sector_scores: pd.DataFrame, held_sectors: list[str] | None = None, p=PARAMS):
    """选 Top N 主线 (优先 leading 象限), 含轮换钝化。返回 (买入主线 list, 轮出 set)。"""
    held = set(held_sectors or [])
    df = sector_scores.copy()
    lead = df[df["leading"]].head(p["sector_top_n"] * 2)
    chosen = lead.head(p["sector_top_n"])["name"].tolist()
    if len(chosen) < p["sector_top_n"]:
        for n in df["name"].tolist():
            if n not in chosen:
                chosen.append(n)
            if len(chosen) >= p["sector_top_n"]:
                break
    # 轮出: 持仓板块跌出 Top6
    rank = {n: i for i, n in enumerate(df["name"].tolist())}
    rotate_out = {s for s in held if rank.get(s, 999) >= p["sector_rotate_out_rank"]}
    return chosen, rotate_out


# ---------- ③个股动量打分 ----------
def stock_score(hist: pd.DataFrame, p=PARAMS) -> dict | None:
    """对单只股票算综合分。hist 含 open/high/low/close/volume/amount, 升序。
    不满足趋势/流动性硬条件 -> None (淘汰)。"""
    if hist is None or len(hist) < p["mom_form"] + p["mom_skip"] + 5:
        return None
    c = hist["close"]
    if c.iloc[-1] < p["min_price"]:
        return None
    if "amount" in hist and hist["amount"].tail(20).mean() < p["min_amount_20d"]:
        return None
    m20, m60 = ma(c, p["stk_ma_fast"]), ma(c, p["stk_ma_mid"])
    if not (m20.iloc[-1] > m60.iloc[-1] and c.iloc[-1] > m20.iloc[-1]):
        return None  # 趋势硬条件
    # 中期动量: 跳过最近 skip 日
    end = -p["mom_skip"] - 1; start = -p["mom_form"] - p["mom_skip"] - 1
    mom = c.iloc[end] / c.iloc[start] - 1.0
    ret = c.pct_change().tail(p["mom_form"])
    vol = ret.std() * np.sqrt(252) + 1e-9
    trend = (c.iloc[-1] / m60.iloc[-1] - 1.0)
    risk_adj = mom / vol
    wm, wt, wr = p["score_w"]
    score = wm * mom + wt * trend + wr * risk_adj
    return dict(score=float(score), mom=float(mom), trend=float(trend),
                vol=float(vol), risk_adj=float(risk_adj),
                ma20=float(m20.iloc[-1]), ma60=float(m60.iloc[-1]), close=float(c.iloc[-1]))


# ---------- 卖出判定 ----------
def exit_signals(pos: dict, hist: pd.DataFrame, sector_rotate_out: bool, p=PARAMS) -> list[str]:
    """pos: {cost, peak, sector}. 返回触发的卖出原因列表 (空=继续持有)。"""
    reasons = []
    c = hist["close"]; px = c.iloc[-1]
    ret = px / pos["cost"] - 1.0
    if ret <= p["stop_loss"]:
        reasons.append(f"止损 {ret:.1%}")
    peak = max(pos.get("peak", pos["cost"]), px)
    if (peak / pos["cost"] - 1.0) > p["take_profit_trigger"] and (px / peak - 1.0) <= p["trail_drawdown"]:
        reasons.append(f"移动止盈 自峰值{px/peak-1:.1%}")
    m20 = ma(c, p["stk_ma_fast"])
    if px < m20.iloc[-1] and m20.iloc[-1] < m20.iloc[-2]:
        reasons.append("趋势破位 跌破MA20且拐头")
    if sector_rotate_out:
        reasons.append("板块轮出")
    return reasons
