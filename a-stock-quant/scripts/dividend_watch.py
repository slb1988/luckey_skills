"""红利守望 (dividend_watch): 用户个人红利逆向策略的每日筛查与跨区提醒。
与动量策略平行独立, 只共享 datafeed 缓存层。规则详见 references/dividend-watch.md。

每日五指标: 估值分位(百度) / 股息率TTM+历史中位(巨潮+不复权价) / 量能分位(baostock缓存) /
           股息率-十年国债利差 / 回购公告(akshare)
信号: 🟢买入区 / 🟡观望 / 🟠持有不加 / 🔴减仓提示 + 价值陷阱与数据突变告警
输出: data/reports/dividend_watch_YYYYMMDD.md; 状态跨区时微信 relay -> 飞书 DM 兜底
用法: python dividend_watch.py [--force-notify] [--no-notify] [--watchlist path]
"""
from __future__ import annotations
import argparse, datetime as dt, json, os, sys, time, urllib.request
from pathlib import Path

import pandas as pd

# Clash 等代理会重置东财/百度/巨潮连接, 国内直连即可, 一律剥离
for _k in ("http_proxy", "https_proxy", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY"):
    os.environ.pop(_k, None)
os.environ["no_proxy"] = "*"

sys.path.insert(0, str(Path(__file__).resolve().parent))
import datafeed  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DIV_DIR = ROOT / "data" / "dividend"; DIV_DIR.mkdir(parents=True, exist_ok=True)
REPORT_DIR = ROOT / "data" / "reports"; REPORT_DIR.mkdir(parents=True, exist_ok=True)
TODAY = dt.date.today().strftime("%Y%m%d")

# 信号阈值 (调参在这里)
PARAMS = {
    "buy_val_pct": 30,        # 买入区估值分位主门槛
    "buy_val_pct_relaxed": 40,  # 放宽档: 分位≤40 且 距52周高点回撤≥relax_off_high
    "relax_off_high": 15,     # 放宽档要求的距高点回撤 %
    "dv_min": 4.0,            # 股息率TTM 下限 %
    "spread_min": 1.5,        # 股息率 - 十年国债 利差下限 pct
    "vol_pct_gate": 40,       # 量能分位门槛 (仅非超大盘股卡线)
    "mega_mv_yi": 3000,       # 总市值≥此值(亿) = 超大盘, 量能分位降为参考(被动盘污染)
    "hold_max_pct": 80,       # 估值分位>80 且 股息率跌破自身历史中位 → 🔴减仓提示
    "watch_min_pct": 60,      # 60~80 → 🟠持有不加
    "trap_val_pct": 70,       # 价值陷阱: 分位≥70 且 250日涨幅≤0 (E下滑顶高分位)
    "dv_jump": 2.0,           # 股息率TTM 日环比突变告警 pct (防特别分红干扰)
}

# 通知 (与 investment-monitor 同一套: 微信 relay 主渠道, 飞书 DM 兜底; 密钥只从环境变量读)
FEISHU_APP_ID = "cli_a9bd439c20bd5ceb"
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_BASE = "https://open.feishu.cn/open-apis"
USER_LOOKUP_API = "http://192.168.2.13:5000/user/get_userinfo_by_p4id/sunlaibing"
CHAT_HUB_RELAY_URL = os.environ.get("CHAT_HUB_RELAY_URL", "http://10.77.77.5:7399/send")
CHAT_HUB_RELAY_TOKEN = os.environ.get("CHAT_HUB_RELAY_TOKEN", "")


# ---------- 配置 ----------
def load_watchlist(path: Path) -> list[dict]:
    import yaml
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return [dict(s, code=str(s["code"])) for s in data["stocks"]]


# ---------- 数据获取 (akshare 部分带当日 parquet 缓存) ----------
def _cached(name: str, ttl_sec: int = 6 * 3600):
    fp = DIV_DIR / f"{name}_{TODAY}.parquet"
    if fp.exists() and (time.time() - fp.stat().st_mtime) < ttl_sec:
        try:
            return pd.read_parquet(fp)
        except Exception:
            return None
    return None


def _put_cache(name: str, df: pd.DataFrame):
    try:
        df.to_parquet(DIV_DIR / f"{name}_{TODAY}.parquet")
    except Exception:
        pass


def baidu_valuation(code: str, indicator: str) -> pd.DataFrame:
    """百度股市通估值序列 (近十年), 返回 DataFrame(date, value)。"""
    c = _cached(f"val_{code}_{indicator}")
    if c is not None:
        return c
    import akshare as ak
    df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period="近十年")
    if df is None or df.empty:
        return pd.DataFrame(columns=["date", "value"])
    df = df.iloc[:, :2]
    df.columns = ["date", "value"]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna()
    _put_cache(f"val_{code}_{indicator}", df)
    return df


def dividend_detail(code: str) -> pd.DataFrame:
    """巨潮分红明细, 返回 DataFrame(除权除息日, 派息[每10股])。"""
    c = _cached(f"div_{code}")
    if c is not None:
        return c
    import akshare as ak
    df = ak.stock_history_dividend_detail(symbol=code, indicator="分红")
    if df is None or df.empty:
        return pd.DataFrame(columns=["ex_date", "div10"])
    df = df[["除权除息日", "派息"]].copy()
    df.columns = ["ex_date", "div10"]
    df["ex_date"] = pd.to_datetime(df["ex_date"], errors="coerce")
    df["div10"] = pd.to_numeric(df["div10"], errors="coerce").fillna(0)
    df = df.dropna(subset=["ex_date"])
    _put_cache(f"div_{code}", df)
    return df


def buyback_set() -> set[str]:
    c = _cached("buyback")
    if c is not None:
        return set(c["code"].astype(str))
    import akshare as ak
    try:
        df = ak.stock_repurchase_em()
        col = [c2 for c2 in df.columns if "代码" in c2][0]
        df = df[[col]].rename(columns={col: "code"})
        _put_cache("buyback", df)
        return set(df["code"].astype(str))
    except Exception as e:
        print(f"[warn] 回购名单获取失败: {e}")
        return set()


def bond_10y() -> float | None:
    import akshare as ak
    try:
        df = ak.bond_zh_us_rate()
        return round(float(df["中国国债收益率10年"].dropna().iloc[-1]), 2)
    except Exception as e:
        print(f"[warn] 十年国债收益率获取失败: {e} (利差门槛跳过)")
        return None


def raw_closes(code: str, years: int = 10) -> pd.Series:
    """不复权日线收盘价 (算历史股息率必须用不复权价; 不走 parquet 缓存,
    datafeed 缓存按代码命名不含复权方式, 混入会污染前复权底仓)。"""
    bs = datafeed._BS.ensure()
    rs = bs.query_history_k_data_plus(
        datafeed._bs_code(code), "date,close",
        start_date=str(dt.date.today() - dt.timedelta(days=years * 365)),
        end_date=str(dt.date.today()), frequency="d", adjustflag="3")
    rows = []
    while rs.error_code == "0" and rs.next():
        rows.append(rs.get_row_data())
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["date", "close"])
    df["close"] = pd.to_numeric(df["close"], errors="coerce")
    return df.set_index(pd.to_datetime(df["date"]))["close"].dropna().sort_index()


# ---------- 指标计算 ----------
def metrics_for(stock: dict, bond: float | None, bb: set[str]) -> dict:
    code, name = stock["code"], stock["name"]
    m: dict = {"code": code, "name": name, "bucket": stock["bucket"],
               "tags": stock.get("tags", []), "flags": []}
    if stock.get("short_history"):
        m["flags"].append("分位数据<5年")

    # 价格轴 (复用 datafeed 前复权缓存)
    hist = datafeed.get_hist(code, str(dt.date.today() - dt.timedelta(days=400)))
    if hist.empty:
        m["flags"].append("价格数据缺失")
        return m
    close = float(hist["close"].iloc[-1])
    px250 = hist["close"].tail(250)
    m["close"] = close
    m["date"] = str(hist.index[-1].date())
    m["off_high"] = round((close / float(px250.max()) - 1) * 100, 1)
    lo, hi = float(px250.min()), float(px250.max())
    m["range_pos"] = round((close - lo) / (hi - lo) * 100, 0) if hi > lo else None
    vol = hist["volume"].dropna().tail(250)
    m["vol_pct"] = round(float((vol < vol.iloc[-1]).mean()) * 100, 0) if len(vol) > 30 else None
    m["ret_250d"] = round((close / float(px250.iloc[0]) - 1) * 100, 1) if len(px250) > 200 else None

    # 估值轴: 周期桶看 PB 分位, 红利桶看 PE 分位 (E 波动大时 PE 分位误导)
    ind = "市净率" if stock["bucket"] == "cyclical" else "市盈率(TTM)"
    try:
        v = baidu_valuation(code, ind)
        if not v.empty:
            val_now = float(v["value"].iloc[-1])
            hist_v = v["value"][(v["value"] > 0) & (v["value"] < 300)]
            m["val_kind"] = "PB" if ind == "市净率" else "PE"
            m["val_now"] = round(val_now, 2)
            m["val_pct"] = round(float((hist_v < val_now).mean()) * 100, 0)
            m["val_median"] = round(float(hist_v.median()), 2)
            span = (pd.to_datetime(v["date"].iloc[-1]) - pd.to_datetime(v["date"].iloc[0])).days / 365
            if span < 5 and "分位数据<5年" not in m["flags"]:
                m["flags"].append("分位数据<5年")
    except Exception as e:
        m["flags"].append(f"估值获取失败")
        print(f"[warn] {code} 估值失败: {e}")
    try:
        mv = baidu_valuation(code, "总市值")
        if not mv.empty:
            m["total_mv_yi"] = round(float(mv["value"].iloc[-1]), 0)
    except Exception:
        pass

    # 股息轴
    try:
        div = dividend_detail(code)
        ttm = div[div["ex_date"] >= pd.Timestamp(dt.date.today() - dt.timedelta(days=365))]
        m["dv_ttm"] = round(float(ttm["div10"].sum()) / 10 / close * 100, 2)
        m["div_years"] = int(div[div["div10"] > 0]["ex_date"].dt.year.nunique())
        raw = raw_closes(code)
        if not raw.empty:
            pts = []
            for _, r in div[(div["div10"] > 0)].iterrows():
                s = raw.loc[:r["ex_date"]]
                if not s.empty:
                    pts.append(float(r["div10"]) / 10 / float(s.iloc[-1]) * 100)
            if len(pts) >= 5:
                m["dv_median"] = round(float(pd.Series(pts).median()), 2)
    except Exception as e:
        m["flags"].append("分红数据缺失")
        print(f"[warn] {code} 分红失败: {e}")

    m["buyback"] = code in bb
    if bond is not None and m.get("dv_ttm") is not None:
        m["spread"] = round(m["dv_ttm"] - bond, 2)
    # 价值陷阱: 估值分位高但股价没涨 = E 下滑把分位顶高, 不是变贵
    if m.get("val_pct") is not None and m["val_pct"] >= PARAMS["trap_val_pct"] \
            and m.get("ret_250d") is not None and m["ret_250d"] <= 0:
        m["flags"].append("疑似价值陷阱(E下滑)")
    return m


# ---------- 分区判定 ----------
ZONES = {"buy": ("🟢", "买入区"), "watch": ("🟡", "观望"), "hold": ("🟠", "持有不加"),
         "trim": ("🔴", "减仓提示"), "unknown": ("⚪", "数据缺失")}


def judge(m: dict) -> tuple[str, list[str]]:
    if m.get("val_pct") is None or m.get("dv_ttm") is None:
        return "unknown", []
    fails = []
    vp, dv = m["val_pct"], m["dv_ttm"]
    if not (vp <= PARAMS["buy_val_pct"]
            or (vp <= PARAMS["buy_val_pct_relaxed"] and m.get("off_high", 0) <= -PARAMS["relax_off_high"])):
        fails.append("估值分位")
    if dv < PARAMS["dv_min"]:
        fails.append("股息率")
    if m.get("spread") is not None and m["spread"] < PARAMS["spread_min"]:
        fails.append("利差")
    mega = (m.get("total_mv_yi") or 0) >= PARAMS["mega_mv_yi"]
    if not mega and m.get("vol_pct") is not None and m["vol_pct"] > PARAMS["vol_pct_gate"]:
        fails.append("量能分位")
    if not fails:
        return "buy", []
    if vp > PARAMS["hold_max_pct"] and m.get("dv_median") is not None and dv < m["dv_median"]:
        return "trim", fails
    if vp > PARAMS["watch_min_pct"]:
        return "hold", fails
    return "watch", fails


# ---------- 通知 ----------
def _http_json(url, payload=None, token=None, timeout=15):
    headers = {"User-Agent": "Mozilla/5.0"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
        if token:
            headers["Authorization"] = f"Bearer {token}"
        req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                     headers=headers, method="POST")
    else:
        req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def send_weixin(text: str) -> bool:
    if not CHAT_HUB_RELAY_TOKEN:
        print("[warn] 未设置 CHAT_HUB_RELAY_TOKEN, 跳过微信通知")
        return False
    try:
        resp = _http_json(CHAT_HUB_RELAY_URL, {"token": CHAT_HUB_RELAY_TOKEN, "text": text})
        ok = bool(resp.get("ok"))
        print(f"[notify] 微信推送{'成功' if ok else '失败: ' + str(resp)}")
        return ok
    except Exception as e:
        print(f"[notify] 微信推送异常: {e}")
        return False


def send_feishu_dm(text: str, state: dict) -> bool:
    if not FEISHU_APP_SECRET:
        print("[warn] 未设置 FEISHU_APP_SECRET, 跳过飞书通知 (报告仍会落盘)")
        return False
    try:
        data = _http_json(f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
                          {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET})
        token = data.get("tenant_access_token", "")
        open_id = state.get("feishu_open_id")
        if not open_id:
            info = _http_json(USER_LOOKUP_API, timeout=8)
            if info.get("status", {}).get("code") == 0:
                open_id = info.get("result", {}).get("userid")
                state["feishu_open_id"] = open_id
        if not open_id:
            raise RuntimeError("飞书 open_id 查询失败")
        resp = _http_json(f"{FEISHU_BASE}/im/v1/messages?receive_id_type=open_id",
                          {"receive_id": open_id, "msg_type": "text",
                           "content": json.dumps({"text": text})}, token)
        ok = resp.get("code") == 0
        print(f"[notify] 飞书 DM 发送{'成功' if ok else '失败: ' + str(resp)}")
        return ok
    except Exception as e:
        print(f"[notify] 飞书发送异常: {e}")
        return False


# ---------- 报告 ----------
def write_report(rows: list[dict], events: list[str], bond: float | None) -> Path:
    lines = [f"# 红利守望 {TODAY}", ""]
    lines.append(f"十年国债收益率: {bond}% | 买入门槛: 分位≤{PARAMS['buy_val_pct']}"
                 f"(或≤{PARAMS['buy_val_pct_relaxed']}且距高点-{PARAMS['relax_off_high']}%)"
                 f" + 股息≥{PARAMS['dv_min']}% + 利差≥{PARAMS['spread_min']}pct"
                 f" + 量能分位≤{PARAMS['vol_pct_gate']}(超大盘豁免)" if bond else "")
    lines += ["", "| 股票 | 桶 | 收盘 | 股息TTM | 利差 | 估值分位 | 距高点 | 量能分位 | 回购 | 分红年 | 判定 | 备注 |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m, zone, fails in rows:
        emoji, zn = ZONES[zone]
        val = f"{m.get('val_kind','?')} {m.get('val_now','?')} / {m.get('val_pct','?')}%"
        note = "; ".join(m["flags"])
        if fails and zone != "buy":
            note = ("未过: " + "/".join(fails)) + (("; " + note) if note else "")
        lines.append(
            f"| {m['name']} | {'周期' if m['bucket']=='cyclical' else '红利'} "
            f"| {m.get('close','?')} | {m.get('dv_ttm','?')}% | {m.get('spread','—')} "
            f"| {val} | {m.get('off_high','?')}% | {m.get('vol_pct','?')}% "
            f"| {'✅' if m.get('buyback') else '—'} | {m.get('div_years','?')} "
            f"| {emoji}{zn} | {note or '—'} |")
    if events:
        lines += ["", "## 今日事件", ""] + [f"- {e}" for e in events]
    path = REPORT_DIR / f"dividend_watch_{TODAY}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def overview_line(rows: list[dict]) -> str:
    return " | ".join(f"{m['name']} {ZONES[z][0]}" for m, z, _ in rows)


# ---------- 主流程 ----------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--watchlist", default=str(Path(__file__).resolve().parent / "watchlist.yaml"))
    ap.add_argument("--force-notify", action="store_true", help="无视状态变化, 强制推送当日全览")
    ap.add_argument("--no-notify", action="store_true", help="只落盘不通知")
    args = ap.parse_args()

    watch = load_watchlist(Path(args.watchlist))
    state_path = DIV_DIR / "state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    print(f"[1/4] 公共数据 (国债/回购) ...")
    bond = bond_10y()
    bb = buyback_set()
    print(f"  十年国债 {bond}%, 回购名单 {len(bb)} 条")

    print(f"[2/4] 逐只计算 ({len(watch)} 只) ...")
    rows = []
    for s in watch:
        try:
            m = metrics_for(s, bond, bb)
            zone, fails = judge(m)
            rows.append((m, zone, fails))
            print(f"  {m['name']}: {ZONES[zone][0]}{ZONES[zone][1]}"
                  f" (分位{m.get('val_pct','?')}% 股息{m.get('dv_ttm','?')}%)")
        except Exception as e:
            print(f"  [warn] {s['name']} 失败: {e}")
    order = {"buy": 0, "watch": 1, "hold": 2, "trim": 3, "unknown": 4}
    rows.sort(key=lambda r: (order[r[1]], -(r[0].get("dv_ttm") or 0)))

    print("[3/4] 对比昨日状态 ...")
    events = []
    prev_zones = state.get("zones", {})
    prev_dv = state.get("dv", {})
    prev_traps = state.get("traps", {})
    for m, zone, _ in rows:
        prev = prev_zones.get(m["code"])
        if prev and prev != zone:
            events.append(f"{ZONES[zone][0]} {m['name']} 跨区: {ZONES[prev][1]} → {ZONES[zone][1]}"
                          f" (分位{m.get('val_pct','?')}% 股息{m.get('dv_ttm','?')}%)")
        prev_d = prev_dv.get(m["code"])
        if prev_d is not None and m.get("dv_ttm") is not None \
                and abs(m["dv_ttm"] - prev_d) >= PARAMS["dv_jump"]:
            events.append(f"⚠️ {m['name']} 股息率TTM突变 {prev_d}% → {m['dv_ttm']}%, 人工复核(防特别分红干扰)")
        trap = any("价值陷阱" in f for f in m["flags"])
        if trap and not prev_traps.get(m["code"]):
            events.append(f"⚠️ {m['name']} 出现价值陷阱形态(分位高+股价未涨, 疑 E 下滑)")

    print("[4/4] 写报告 ...")
    path = write_report(rows, events, bond)
    print(f"  报告: {path}")

    state["zones"] = {m["code"]: z for m, z, _ in rows}
    state["dv"] = {m["code"]: m.get("dv_ttm") for m, _, _ in rows}
    state["traps"] = {m["code"]: any("价值陷阱" in f for f in m["flags"]) for m, _, _ in rows}
    state["last_run"] = TODAY
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    if not args.no_notify and (events or args.force_notify):
        lines = [f"💰 红利守望 {TODAY}", ""] + (events or ["(无状态变化, 此为强制全览)"])
        lines += ["", "全览: " + overview_line(rows)]
        text = "\n".join(lines)
        if not send_weixin(text):
            send_feishu_dm(text, state)
            state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print("[notify] 无状态变化, 静默 (报告已落盘)")
    datafeed._BS.close()
    print("done.")


if __name__ == "__main__":
    main()
