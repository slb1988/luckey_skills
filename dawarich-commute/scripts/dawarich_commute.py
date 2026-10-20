#!/usr/bin/env python3
"""dawarich_commute.py — 从 Dawarich 轨迹点计算每日通勤情况（上下班时间/用时/路程）

锚点优先取 Dawarich web 端 Places（名称 home/家 → 家，公司/work → 公司）；
未设置时才自动检测（家 = 23-6 点位置中位数，公司 = 工作日 10-16 点且离家 >800m 的中位数），
报告期之前自动回看 6 天用于锚定。
"""

import argparse
import json
import math
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
WEEKDAY_CN = "一二三四五六日"
LOOKBACK_DAYS = 6        # 锚定回看的额外天数
SPARSE_GAP_S = 1200      # 路段内超过 20 分钟无轨迹点 -> 标记数据稀疏


def load_dotenv():
    """进程环境变量优先；文件按 就近 -> 仓库根 顺序取第一个存在的 .env"""
    here = SCRIPT_DIR
    candidates = [here / ".env", here.parent / ".env"]
    candidates += [a / ".env" for a in list(here.parents)[1:4]]
    for path in candidates:
        if not path.exists():
            continue
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip()
            if k and k not in os.environ:
                os.environ[k] = v
        return


def get_cfg():
    return {
        "base": os.environ.get("DAWARICH_BASE_URL", "http://10.77.77.6:3000").rstrip("/"),
        "key": os.environ.get("DAWARICH_API_KEY", ""),
        "radius": float(os.environ.get("DAWARICH_RADIUS_M") or 300),
    }


# 10.77.77.x 走 WireGuard 直连，必须绕过系统代理
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api_get(cfg, path, params=None):
    q = dict(params or {})
    q["api_key"] = cfg["key"]
    url = cfg["base"] + path + "?" + urllib.parse.urlencode(q)
    req = urllib.request.Request(url, headers={"Authorization": "Bearer " + cfg["key"]})
    try:
        with _OPENER.open(req, timeout=60) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers or {}), e.read()
    except urllib.error.URLError as e:
        return -1, {}, str(e).encode()


def _day_bounds_utc(day, ndays=1):
    tz = datetime.now().astimezone().tzinfo
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=ndays)
    fmt = lambda d: d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return fmt(start), fmt(end)


def fetch_points(cfg, start_day, ndays):
    start_iso, end_iso = _day_bounds_utc(start_day, ndays)
    points, page, total_pages = [], 1, None
    while True:
        st, hdr, body = api_get(cfg, "/api/v1/points", {
            "start_at": start_iso, "end_at": end_iso,
            "per_page": 1000, "page": page, "order": "asc"})
        if st != 200:
            raise RuntimeError("points API HTTP %s: %s" % (st, body[:200].decode("utf-8", "replace")))
        batch = json.loads(body)
        if not isinstance(batch, list):
            raise RuntimeError("points API 返回非数组: %r" % body[:200])
        points.extend(batch)
        if total_pages is None:
            try:
                total_pages = int(hdr.get("X-Total-Pages") or 1)
            except (TypeError, ValueError):
                total_pages = 1
        if page >= total_pages or not batch:
            break
        page += 1
    out = []
    for p in points:
        try:
            acc = p.get("accuracy")
            out.append({"ts": int(p["timestamp"]),
                        "lat": float(p["latitude"]),
                        "lon": float(p["longitude"]),
                        "acc": float(acc) if acc not in (None, "") else None})
        except (KeyError, TypeError, ValueError):
            continue
    out.sort(key=lambda p: p["ts"])
    return out


def accuracy_filter(pts, limit=150.0):
    good = [p for p in pts if p["acc"] is None or p["acc"] <= limit]
    # 过滤太狠说明 tracker 精度口径不同，放弃过滤
    return good if len(good) >= max(10, len(pts) // 2) else pts


def haversine_m(lat1, lon1, lat2, lon2):
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def ldt(p):
    return datetime.fromtimestamp(p["ts"])


def median_coord(coords):
    lats = sorted(c[0] for c in coords)
    lons = sorted(c[1] for c in coords)
    n = len(coords)
    return (lats[n // 2], lons[n // 2])


def detect_home(pts):
    c = [(p["lat"], p["lon"]) for p in pts if ldt(p).hour >= 23 or ldt(p).hour < 6]
    if len(c) < 5:
        c = [(p["lat"], p["lon"]) for p in pts if ldt(p).hour < 8]
    return median_coord(c) if c else None


def detect_work(pts, home, radius):
    far = max(800.0, 2 * radius)
    c = [(p["lat"], p["lon"]) for p in pts
         if ldt(p).weekday() < 5 and 10 <= ldt(p).hour < 16
         and haversine_m(p["lat"], p["lon"], home[0], home[1]) > far]
    return median_coord(c) if len(c) >= 3 else None


PLACE_NAMES = {
    "home": {"home", "家"},
    "work": {"公司", "work", "company", "office"},
}


def anchors_from_places(cfg):
    """从 web 端 Places 取家/公司锚点，返回 (home, work)，未设置的为 None"""
    st, _, body = api_get(cfg, "/api/v1/places")
    if st != 200:
        return None, None
    try:
        places = json.loads(body)
    except ValueError:
        return None, None
    home = work = None
    for p in places if isinstance(places, list) else []:
        name = (p.get("name") or "").strip().lower()
        try:
            coord = (float(p["latitude"]), float(p["longitude"]))
        except (KeyError, TypeError, ValueError):
            continue
        if name in PLACE_NAMES["home"] and home is None:
            home = coord
        if name in PLACE_NAMES["work"] and work is None:
            work = coord
    return home, work


def classify(pts, home, work, radius):
    labels = []
    for p in pts:
        if haversine_m(p["lat"], p["lon"], home[0], home[1]) <= radius:
            labels.append("H")
        elif work and haversine_m(p["lat"], p["lon"], work[0], work[1]) <= radius:
            labels.append("W")
        else:
            labels.append(".")
    return labels


def runs_of(labels):
    out, i = [], 0
    while i < len(labels):
        j = i
        while j + 1 < len(labels) and labels[j + 1] == labels[i]:
            j += 1
        out.append((labels[i], i, j))
        i = j + 1
    return out


def find_legs(pts, labels, work_confident):
    """返回 (morning, evening, m_partial, e_partial)，leg 为 (dep_idx, arr_idx)。
    partial：锚点一端无轨迹（出门早于记录/离开时间落在轨迹空洞里），用最近可观测点起算。"""
    hw_runs = [r for r in runs_of(labels) if r[0] in ("H", "W")]

    def usable(run):
        if work_confident:
            return True
        _, i0, i1 = run
        return (i1 - i0 + 1) >= 2 or (pts[i1]["ts"] - pts[i0]["ts"]) >= 180

    morning = evening = None
    m_partial = e_partial = False
    for k, run in enumerate(hw_runs):
        if run[0] != "W" or not usable(run):
            continue
        h = next((r for r in reversed(hw_runs[:k]) if r[0] == "H"), None)
        if h:
            morning = (h[2], run[1])  # 最后一个在家点 -> 第一个到公司点
        elif work_confident and run[1] > 0:
            morning = (0, run[1])  # 轨迹起点已在路上
            m_partial = True
        if morning:
            break
    for k in range(len(hw_runs) - 1, -1, -1):
        run = hw_runs[k]
        if run[0] != "W" or not usable(run):
            continue
        h = next((r for r in hw_runs[k + 1:] if r[0] == "H"), None)
        if h:
            w_end = run[2]
            nxt = w_end + 1
            # 最后在公司点与下一个轨迹点间隔过大：离开时间不可知，从首个路上点起算
            if nxt < h[1] and pts[nxt]["ts"] - pts[w_end]["ts"] > SPARSE_GAP_S:
                evening = (nxt, h[1])
                e_partial = True
            else:
                evening = (w_end, h[1])  # 最后一个在公司点 -> 第一个到家点
        if evening:
            break
    return morning, evening, m_partial, e_partial


def home_outings(pts, labels):
    """无公司行程时的降级：首次离家 / 最后回家"""
    h_runs = [r for r in runs_of(labels) if r[0] == "H"]
    if not h_runs:
        return None
    first_h, last_h = h_runs[0], h_runs[-1]
    leave = first_h[2] if first_h[2] < len(pts) - 1 else None
    back = last_h[1] if last_h[1] > 0 else None
    return (leave, back) if (leave is not None and back is not None and leave < back) else None


def leg_stats(pts, dep, arr):
    seg = pts[dep:arr + 1]
    dist = 0.0
    max_gap = 0
    for a, b in zip(seg, seg[1:]):
        dt = b["ts"] - a["ts"]
        max_gap = max(max_gap, dt)
        if dt <= 0:
            continue
        d = haversine_m(a["lat"], a["lon"], b["lat"], b["lon"])
        if d / dt * 3.6 > 180:  # GPS 跳点
            continue
        if d < 15:  # 静止抖动
            continue
        dist += d
    return {"depart_ts": seg[0]["ts"], "arrive_ts": seg[-1]["ts"],
            "duration_s": seg[-1]["ts"] - seg[0]["ts"],
            "distance_km": round(dist / 1000, 1),
            "max_gap_s": max_gap, "sparse": max_gap > SPARSE_GAP_S}


def fmt_t(ts):
    return datetime.fromtimestamp(ts).strftime("%H:%M")


def fmt_dur(s):
    m = round(s / 60)
    return "%d小时%d分钟" % (m // 60, m % 60) if m >= 60 else "%d分钟" % m


def analyze(cfg, days, args):
    """days: 要报告的日期列表（升序）。锚定额外回看 LOOKBACK_DAYS 天。"""
    first = days[0] - timedelta(days=LOOKBACK_DAYS)
    ndays = (days[-1] - first).days + 1
    pts = accuracy_filter(fetch_points(cfg, first, ndays))
    if args.dump:
        dump_dir = SCRIPT_DIR / "dump"
        dump_dir.mkdir(exist_ok=True)
        (dump_dir / ("points-%s_%s.json" % (first, days[-1]))).write_text(
            json.dumps(pts, ensure_ascii=False), encoding="utf-8")

    p_home, p_work = anchors_from_places(cfg)
    home = args.home or p_home
    home_src = ("手动" if args.home else "Places") if home else None
    if not home and pts:
        home, home_src = detect_home(pts), "自动"
    work = args.work or p_work
    work_src = ("手动" if args.work else "Places") if work else None
    if not work and home and pts:
        work, work_src = detect_work(pts, home, cfg["radius"]), "自动"

    by_day = defaultdict(list)
    for p in pts:
        by_day[ldt(p).date()].append(p)

    anchors = {"home": ({"lat": round(home[0], 5), "lon": round(home[1], 5), "source": home_src}
                        if home else None),
               "work": ({"lat": round(work[0], 5), "lon": round(work[1], 5), "source": work_src}
                        if work else None)}

    results = []
    for day in days:
        res = {"date": day.isoformat(), "weekday_cn": WEEKDAY_CN[day.weekday()]}
        dpts = by_day.get(day, [])
        res["points"] = len(dpts)
        if not dpts:
            res["status"] = "无轨迹数据"
            results.append(res)
            continue
        if not home:
            res["status"] = "无法识别家锚点（数据不足）"
            results.append(res)
            continue

        labels = classify(dpts, home, work, cfg["radius"])
        n_w = labels.count("W")
        morning = evening = None
        partials = {}
        if work and n_w > 0:
            morning, evening, m_p, e_p = find_legs(dpts, labels, work_confident=(work_src in ("手动", "Places") or n_w >= 3))
            partials = {"morning": m_p, "evening": e_p}
        for key, leg in (("morning", morning), ("evening", evening)):
            if leg:
                s = leg_stats(dpts, *leg)
                res[key] = {**s, "depart": fmt_t(s["depart_ts"]), "arrive": fmt_t(s["arrive_ts"]),
                            "duration": fmt_dur(s["duration_s"]), "partial": partials.get(key, False)}
        notes = []
        if partials.get("morning"):
            notes.append("出门早于轨迹起点，早段从 %s（首个轨迹点）起算" % fmt_t(dpts[0]["ts"]))
        if partials.get("evening"):
            notes.append("离开公司时间落在轨迹空洞里，晚段从首个路上点起算")
        if work and not evening and n_w > 0 and labels[-1] != "H":
            notes.append("截至最后轨迹点 %s 未记录到家" % fmt_t(dpts[-1]["ts"]))
        if not morning and not evening:
            out = home_outings(dpts, labels)
            if out:
                res["outing"] = {"leave": fmt_t(dpts[out[0]]["ts"]), "back": fmt_t(dpts[out[1]]["ts"])}
                notes.append("无公司行程，仅识别外出" if work else "无公司锚点，仅识别外出")
            elif not notes:
                notes.append("全天在家范围内" if labels[-1] == "H" else "未检测到通勤")
        if notes:
            res["notes"] = notes
        results.append(res)
    return anchors, results


def print_report(anchors, results, radius):
    h, w = anchors.get("home"), anchors.get("work")
    if h:
        print("家 (%.5f, %.5f) [%s]" % (h["lat"], h["lon"], h["source"]), end="")
        print("   公司 (%.5f, %.5f) [%s]" % (w["lat"], w["lon"], w["source"]) if w
              else "   公司 未识别", end="")
        print("   半径 %dm" % radius)
    for res in results:
        print("%s 周%s | 轨迹点 %s" % (res["date"], res["weekday_cn"], res.get("points", 0)))
        for key, label in (("morning", "早"), ("evening", "晚")):
            leg = res.get(key)
            if leg:
                gap = " ≈（中间最长 %d 分钟无轨迹）" % round(leg["max_gap_s"] / 60) if leg["sparse"] else ""
                print("  %s: %s → %s | 用时 %s | 路程 %.1f km%s"
                      % (label, leg["depart"], leg["arrive"], leg["duration"], leg["distance_km"], gap))
        if res.get("outing"):
            print("  外出: %s 离家 → %s 回家" % (res["outing"]["leave"], res["outing"]["back"]))
        for n in res.get("notes", []):
            print("  " + n)
        if res.get("status"):
            print("  " + res["status"])


def selfcheck(cfg):
    st, _, body = api_get(cfg, "/api/v1/stats")
    if st == 200:
        d = json.loads(body)
        print("API key 有效 ✓")
        print("  总里程 %.1f km | 轨迹点 %s | 国家 %s | 城市 %s"
              % (d.get("totalDistanceKm", 0), d.get("totalPointsTracked", 0),
                 d.get("totalCountriesVisited", 0), d.get("totalCitiesVisited", 0)))
        return 0
    print("selfcheck 失败 HTTP %s: %s" % (st, body[:200].decode("utf-8", "replace")))
    return 1


def probe(cfg, day):
    dump_dir = SCRIPT_DIR / "dump" / ("probe-%s" % day)
    dump_dir.mkdir(parents=True, exist_ok=True)
    start_iso, end_iso = _day_bounds_utc(day)
    targets = {
        "stats.json": ("/api/v1/stats", {}),
        "timeline.json": ("/api/v1/timeline", {"start_at": day.isoformat(), "end_at": day.isoformat()}),
        "visits.json": ("/api/v1/visits", {"start_at": start_iso, "end_at": end_iso}),
    }
    for name, (path, params) in targets.items():
        st, _, body = api_get(cfg, path, params)
        (dump_dir / name).write_bytes(body)
        print("probe %-14s HTTP %s -> %s" % (path, st, dump_dir / name))
    return 0


def parse_coord(s):
    la, lo = s.split(",")
    return (float(la.strip()), float(lo.strip()))


def main():
    load_dotenv()
    ap = argparse.ArgumentParser(description="Dawarich 每日通勤情况")
    ap.add_argument("date", nargs="?", help="YYYY-MM-DD，默认今天")
    ap.add_argument("--days", type=int, default=1, help="向前覆盖 N 天（含当天/指定日）")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--selfcheck", action="store_true", help="验证 API key 与服务连通")
    ap.add_argument("--probe", action="store_true", help="导出 stats/timeline/visits 原始响应到 dump/")
    ap.add_argument("--dump", action="store_true", help="保存轨迹点原始 JSON 到 dump/")
    ap.add_argument("--radius", type=float, help="锚点半径（米），默认 300")
    ap.add_argument("--home", type=parse_coord, help="家坐标 lat,lon（覆盖 Places/自动）")
    ap.add_argument("--work", type=parse_coord, help="公司坐标 lat,lon（覆盖 Places/自动）")
    args = ap.parse_args()

    cfg = get_cfg()
    if not cfg["key"]:
        print("缺少 DAWARICH_API_KEY：配到仓库根 .env 或 skill 目录 .env（模板见 .env.example）", file=sys.stderr)
        return 2
    if args.radius:
        cfg["radius"] = args.radius

    if args.selfcheck:
        return selfcheck(cfg)

    day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else datetime.now().date()
    if args.probe:
        return probe(cfg, day)

    days = [day - timedelta(days=i) for i in range(args.days - 1, -1, -1)]
    try:
        anchors, results = analyze(cfg, days, args)
    except RuntimeError as e:
        print("错误: %s" % e, file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps({"anchors": anchors, "days": results}, ensure_ascii=False, indent=2))
    else:
        print_report(anchors, results, cfg["radius"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
