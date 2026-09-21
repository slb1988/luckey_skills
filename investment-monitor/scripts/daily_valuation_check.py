#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""每日指数估值监控 (investment-monitor)

数据流:
  蛋卷估值 API → PE 百分位分区判定 → 与昨日状态对比 → 状态变化时飞书 DM 通知
  akshare → QDII ETF 场内溢价 (可选, 失败不阻塞)

分区标准与 investment-analyzer/references/估值判断标准.md 一致:
  PE 百分位 <10% 极度低估 | 10-30% 低估 | 30-60% 合理 | 60-80% 偏贵 | >80% 高估

通知策略: 只在状态变化时推送 (进入/离开低估、进入高估、溢价跨阈值), 避免每日骚扰。
         --force-notify 可强制发送当日全览 (测试/手动查看用)。
"""
import argparse
import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

CST = timezone(timedelta(hours=8))
TODAY = datetime.now(CST).strftime("%Y-%m-%d")

# ── 监控配置 (调参在这里) ──────────────────────────────────────────────
# 监控名 -> 蛋卷指数的确切名称 (exact match)
WATCHLIST = {
    "沪深300": "沪深300",
    "中证500": "中证500",
    "中证红利": "中证红利",
    "创业板指": "创业板",
    "科创50": "科创50",
    "恒生指数": "恒生指数",
    "恒生科技": "恒生科技",
    "标普500": "标普500",
    "纳指100": "纳指100",
}
MARKET_OF = {"沪深300": "A股", "中证500": "A股", "中证红利": "A股", "创业板指": "A股",
             "科创50": "A股", "恒生指数": "港股", "恒生科技": "港股",
             "标普500": "美股", "纳指100": "美股"}

# QDII 场内 ETF 溢价监控 (溢价高时场内买入 = 多付钱)
QDII_ETFS = {
    "513100": "纳指ETF国泰",
    "513500": "标普500ETF博时",
    "159941": "纳指ETF广发",
    "513300": "纳斯达克ETF华夏",
    "159509": "纳指科技ETF景顺",
}
PREMIUM_ALERT = 5.0   # 溢价 > 5%: 告警, 不适合场内买入
PREMIUM_OK = 2.0      # 溢价 < 2%: 恢复正常, 可以场内买

DANJUAN_API = "https://danjuanapp.com/djapi/index_eva/dj"

# 飞书通知 (复用 skill-index-patrol 的 bot; 密钥只从环境变量读, 不入库)
FEISHU_APP_ID = "cli_a9bd439c20bd5ceb"
FEISHU_APP_SECRET = os.environ.get("FEISHU_APP_SECRET", "")
FEISHU_BASE = "https://open.feishu.cn/open-apis"
USER_LOOKUP_API = "http://192.168.2.13:5000/user/get_userinfo_by_p4id/sunlaibing"

DEFAULT_DATA_DIR = Path(__file__).resolve().parent.parent / "data"


# ── 数据获取 ──────────────────────────────────────────────────────────
def _http_json(url, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def fetch_danjuan():
    """返回 {监控名: {pe, pe_pct, pb_pct, date}}; 未找到的指数进 missing 列表。"""
    data = _http_json(DANJUAN_API)
    by_name = {it["name"]: it for it in data["data"]["items"]}
    result, missing = {}, []
    for watch_name, dj_name in WATCHLIST.items():
        it = by_name.get(dj_name)
        if not it:
            missing.append(watch_name)
            continue
        pe = it.get("pe") or 0
        result[watch_name] = {
            "pe": round(pe, 2),
            "pe_pct": it.get("pe_percentile") if pe > 0 else None,
            "pb_pct": it.get("pb_percentile"),
            "date": it.get("date", ""),
        }
    return result, missing


def fetch_qdii_premium():
    """akshare 东财 ETF 实时行情, 返回 {代码: {name, price, iopv, premium_pct}}。失败返回 None。"""
    try:
        import akshare as ak
    except ImportError:
        print("[warn] akshare 未安装, 跳过 QDII 溢价监控")
        return None
    try:
        df = ak.fund_etf_spot_em()
        df = df[df["代码"].isin(QDII_ETFS.keys())]
        out = {}
        for _, row in df.iterrows():
            price, iopv = float(row["最新价"]), float(row["IOPV实时估值"])
            if iopv <= 0:
                continue
            out[row["代码"]] = {
                "name": QDII_ETFS[row["代码"]],
                "price": price,
                "iopv": iopv,
                "premium_pct": round((price - iopv) / iopv * 100, 2),
            }
        return out
    except Exception as e:  # 东财接口偶尔抽风, 不阻塞主流程
        print(f"[warn] QDII 溢价获取失败: {e}")
        return None


# ── 分区判定 ──────────────────────────────────────────────────────────
def zone_of(pct):
    """pct: 0..1。返回 (zone_key, emoji, 中文名)"""
    if pct is None:
        return ("unknown", "⚪", "数据缺失")
    if pct < 0.10:
        return ("deep_low", "🟢⭐", "极度低估")
    if pct < 0.30:
        return ("low", "🟢", "低估")
    if pct < 0.60:
        return ("fair", "🟡", "合理")
    if pct < 0.80:
        return ("high", "🔴", "偏贵")
    return ("very_high", "🔴🚫", "高估")


LOW_ZONES = {"deep_low", "low"}


def detect_transitions(current, state):
    """对比当前分区与 state 中的昨日分区, 返回需要通知的事件列表。"""
    events = []
    prev_zones = state.get("zones", {})
    for name, info in current.items():
        zone, emoji, zone_cn = zone_of(info["pe_pct"])
        prev = prev_zones.get(name)
        pct_txt = f"{info['pe_pct']*100:.0f}%" if info["pe_pct"] is not None else "N/A"
        if prev is None:
            continue  # 首日基线不通知
        if zone in LOW_ZONES and prev not in LOW_ZONES:
            events.append(f"{emoji} 新进入低估: {name} (PE {info['pe']}, 百分位 {pct_txt})")
        elif zone not in LOW_ZONES and prev in LOW_ZONES:
            events.append(f"⬆️ 退出低估: {name} (百分位 {pct_txt}, 现为{zone_cn})")
        elif zone == "deep_low" and prev == "low":
            events.append(f"{emoji} 低估加深: {name} 进入极度低估 (百分位 {pct_txt})")
        elif zone == "very_high" and prev != "very_high":
            events.append(f"🔴🚫 新进入高估: {name} (PE {info['pe']}, 百分位 {pct_txt}), 注意止盈纪律")
    return events


def premium_events(premiums, state):
    """QDII 溢价跨阈值事件。"""
    if not premiums:
        return []
    events = []
    prev = state.get("premium_flag", {})
    for code, p in premiums.items():
        flag = "high" if p["premium_pct"] > PREMIUM_ALERT else ("ok" if p["premium_pct"] < PREMIUM_OK else "mid")
        old = prev.get(code)
        if old is None:
            continue
        if flag == "high" and old != "high":
            events.append(f"💸 {p['name']}({code}) 场内溢价升至 {p['premium_pct']}%, 暂不适合场内买入, 走场外联接基金")
        elif flag == "ok" and old != "ok":
            events.append(f"✅ {p['name']}({code}) 场内溢价回落至 {p['premium_pct']}%, 场内买入窗口恢复")
    return events


# ── 飞书通知 ──────────────────────────────────────────────────────────
def feishu_token():
    data = _http_json_post(f"{FEISHU_BASE}/auth/v3/tenant_access_token/internal",
                           {"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET})
    return data.get("tenant_access_token", "")


def _http_json_post(url, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode("utf-8"))


def get_user_open_id(token, state):
    cached = state.get("feishu_open_id")
    if cached:
        return cached
    data = _http_json(USER_LOOKUP_API, timeout=8)
    if data.get("status", {}).get("code") == 0:
        open_id = data.get("result", {}).get("userid")
        if open_id:
            state["feishu_open_id"] = open_id
            return open_id
    raise RuntimeError("飞书 open_id 查询失败")


def send_feishu_dm(text, state):
    if not FEISHU_APP_SECRET:
        print("[warn] 未设置 FEISHU_APP_SECRET, 跳过通知 (快照仍会落盘)")
        return False
    token = feishu_token()
    open_id = get_user_open_id(token, state)
    resp = _http_json_post(f"{FEISHU_BASE}/im/v1/messages?receive_id_type=open_id",
                           {"receive_id": open_id, "msg_type": "text",
                            "content": json.dumps({"text": text})}, token)
    ok = resp.get("code") == 0
    print(f"[notify] 飞书 DM 发送{'成功' if ok else '失败: ' + str(resp)}")
    return ok


# ── 输出 ──────────────────────────────────────────────────────────────
def build_overview_line(current):
    parts = []
    for name, info in current.items():
        _, emoji, _ = zone_of(info["pe_pct"])
        pct = f"{info['pe_pct']*100:.0f}%" if info["pe_pct"] is not None else "N/A"
        parts.append(f"{name} {pct}{emoji}")
    return " | ".join(parts)


def write_snapshot(data_dir, current, missing, premiums, events):
    lines = [f"# 每日估值监控 {TODAY}", ""]
    lines.append("| 指数 | 市场 | PE | PE百分位 | PB百分位 | 分区 |")
    lines.append("|---|---|---|---|---|---|")
    for name, info in current.items():
        _, emoji, zone_cn = zone_of(info["pe_pct"])
        pe_pct = f"{info['pe_pct']*100:.1f}%" if info["pe_pct"] is not None else "N/A"
        pb_pct = f"{info['pb_pct']*100:.1f}%" if info["pb_pct"] is not None else "N/A"
        lines.append(f"| {name} | {MARKET_OF[name]} | {info['pe']} | {pe_pct} | {pb_pct} | {emoji} {zone_cn} |")
    if missing:
        lines.append(f"\n⚠️ 蛋卷未覆盖: {', '.join(missing)}")
    if premiums:
        lines += ["", "## QDII ETF 场内溢价", "", "| ETF | 代码 | 价格 | IOPV | 溢价 | 状态 |",
                  "|---|---|---|---|---|---|"]
        for code, p in premiums.items():
            flag = "🚫 勿场内买" if p["premium_pct"] > PREMIUM_ALERT else (
                "✅ 正常" if p["premium_pct"] < PREMIUM_OK else "⚠️ 偏高")
            lines.append(f"| {p['name']} | {code} | {p['price']} | {p['iopv']} | {p['premium_pct']}% | {flag} |")
    if events:
        lines += ["", "## 今日事件", ""] + [f"- {e}" for e in events]
    path = data_dir / f"valuation_{TODAY}.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


# ── 主流程 ────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", default=str(DEFAULT_DATA_DIR))
    ap.add_argument("--force-notify", action="store_true", help="无视状态变化, 强制发送当日全览")
    ap.add_argument("--no-notify", action="store_true", help="只落盘不通知")
    args = ap.parse_args()

    data_dir = Path(args.data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    state_path = data_dir / "monitor_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8")) if state_path.exists() else {}

    print(f"[1/3] 拉取蛋卷估值 ({TODAY}) ...")
    current, missing = fetch_danjuan()
    print(f"  覆盖 {len(current)}/{len(WATCHLIST)} 个指数" + (f", 缺失: {missing}" if missing else ""))

    print("[2/3] 拉取 QDII 溢价 ...")
    premiums = fetch_qdii_premium()

    events = detect_transitions(current, state) + premium_events(premiums, state)

    print("[3/3] 写快照 ...")
    snap = write_snapshot(data_dir, current, missing, premiums, events)
    print(f"  快照: {snap}")

    # 更新状态
    state["zones"] = {n: zone_of(i["pe_pct"])[0] for n, i in current.items()}
    if premiums:
        state["premium_flag"] = {c: ("high" if p["premium_pct"] > PREMIUM_ALERT else
                                     "ok" if p["premium_pct"] < PREMIUM_OK else "mid")
                                 for c, p in premiums.items()}
    state["last_run"] = TODAY
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    # 通知
    should_notify = not args.no_notify and (events or args.force_notify)
    if should_notify:
        lines = [f"📊 估值监控 {TODAY}", ""]
        lines += events if events else ["(无状态变化, 此为强制全览)"]
        lines += ["", "全览: " + build_overview_line(current)]
        send_feishu_dm("\n".join(lines), state)
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print("[notify] 无状态变化, 静默 (快照已落盘)")

    print("done.")


if __name__ == "__main__":
    main()
