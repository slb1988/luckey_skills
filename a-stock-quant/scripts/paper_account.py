"""纸交易账户: 持仓/现金/成交记录, 如实计交易成本 (印花税仅卖出)。
状态落地 data/paper_account.json, 供每日复盘与周一执行共用。
"""
from __future__ import annotations
import json, datetime as dt
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "data" / "paper_account.json"

# 交易成本
COMMISSION = 0.00025   # 佣金 万2.5 双边
COMMISSION_MIN = 5.0   # 最低5元/笔
STAMP = 0.0005         # 印花税 万5, 仅卖出
TRANSFER = 0.00001     # 过户费 万0.1 双边
SLIPPAGE = 0.0015      # 滑点 0.15% 双边(保守)


def _default(init_cash=1_000_000.0):
    return {"cash": init_cash, "init_cash": init_cash,
            "positions": {},  # code -> {shares, cost, peak, sector, open_date}
            "trades": [], "nav_history": [], "updated": ""}


def load() -> dict:
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return _default()


def save(acc: dict):
    acc["updated"] = dt.datetime.now().isoformat(timespec="seconds")
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(acc, ensure_ascii=False, indent=2), encoding="utf-8")


def _buy_cost(amount: float) -> float:
    comm = max(amount * COMMISSION, COMMISSION_MIN)
    return comm + amount * TRANSFER + amount * SLIPPAGE


def _sell_cost(amount: float) -> float:
    comm = max(amount * COMMISSION, COMMISSION_MIN)
    return comm + amount * STAMP + amount * TRANSFER + amount * SLIPPAGE


def buy(acc: dict, code: str, price: float, shares: int, sector: str, date: str) -> bool:
    shares = int(shares // 100 * 100)  # 整手
    if shares <= 0:
        return False
    amount = price * shares
    fee = _buy_cost(amount)
    total = amount + fee
    if total > acc["cash"]:
        return False
    acc["cash"] -= total
    p = acc["positions"].get(code)
    if p:  # 加仓: 重算成本
        new_sh = p["shares"] + shares
        p["cost"] = (p["cost"] * p["shares"] + price * shares) / new_sh
        p["shares"] = new_sh
    else:
        acc["positions"][code] = {"shares": shares, "cost": price, "peak": price,
                                   "sector": sector, "open_date": date}
    acc["trades"].append({"date": date, "code": code, "side": "BUY",
                           "price": price, "shares": shares, "fee": round(fee, 2)})
    return True


def sell(acc: dict, code: str, price: float, date: str, reason: str = "") -> bool:
    p = acc["positions"].get(code)
    if not p:
        return False
    shares = p["shares"]; amount = price * shares
    fee = _sell_cost(amount)
    acc["cash"] += amount - fee
    pnl = (price - p["cost"]) * shares - fee
    acc["trades"].append({"date": date, "code": code, "side": "SELL",
                           "price": price, "shares": shares, "fee": round(fee, 2),
                           "pnl": round(pnl, 2), "reason": reason})
    del acc["positions"][code]
    return True


def mark_to_market(acc: dict, prices: dict, date: str) -> float:
    """用最新价更新峰值并计算总净值。prices: code->price。"""
    equity = acc["cash"]
    for code, p in acc["positions"].items():
        px = prices.get(code, p["cost"])
        p["peak"] = max(p.get("peak", p["cost"]), px)
        equity += px * p["shares"]
    acc["nav_history"].append({"date": date, "nav": round(equity, 2),
                                "cash": round(acc["cash"], 2)})
    return equity
