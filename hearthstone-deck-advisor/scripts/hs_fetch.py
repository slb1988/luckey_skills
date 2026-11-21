"""Download HSReplay meta data and the user's collection to local JSON files.

HSReplay sits behind a Cloudflare challenge, so plain HTTP clients get 403. This script
drives the system Chrome with a dedicated profile and issues same-origin fetches from the
page, which also carries the login cookie for the collection endpoint.

    python hs_fetch.py login            # one-time: sign in inside the opened window
    python hs_fetch.py fetch            # meta + collection -> ~/.hs-advisor/data/
    python hs_fetch.py fetch --formats standard,wild --no-collection
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import shutil
import sys
import urllib.request

from playwright.sync_api import sync_playwright

from hs_common import DATA_DIR, FORMATS, HOME, LATEST_DIR, PROFILE_DIR, load_config, load_json, save_json

BASE = "https://hsreplay.net"
STATE_PATH = HOME / "storage_state.json"  # login cookies; Chrome may not flush them on close
CARDS_URL = "https://api.hearthstonejson.com/v1/latest/{loc}/cards.collectible.json"
FREE_RANK = "BRONZE_THROUGH_GOLD"
PREMIUM_RANKS = ["DIAMOND_THROUGH_LEGEND", "LEGEND"]
DECK_TIME_RANGES = ["CURRENT_PATCH", "LAST_30_DAYS"]

FETCH_JS = """
async (items) => {
  const out = {};
  for (const [name, url] of items) {
    try {
      const r = await fetch(url, {credentials: 'include', headers: {Accept: 'application/json'}});
      out[name] = {status: r.status, body: await r.text()};
    } catch (e) {
      out[name] = {status: 0, body: String(e)};
    }
    await new Promise(res => setTimeout(res, 700));
  }
  return out;
}
"""


def open_site(p, headless: bool = False):
    ctx = p.chromium.launch_persistent_context(
        str(PROFILE_DIR),
        channel="chrome",
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
        ignore_default_args=["--enable-automation"],
        viewport={"width": 1280, "height": 860},
    )
    if STATE_PATH.exists():
        ctx.add_cookies(load_json(STATE_PATH)["cookies"])
    page = ctx.pages[0] if ctx.pages else ctx.new_page()
    page.goto(BASE + "/", wait_until="domcontentloaded", timeout=60000)
    return ctx, page


def close_site(ctx, logged_in: bool) -> None:
    if logged_in:
        ctx.storage_state(path=str(STATE_PATH))
    ctx.close()


def page_fetch(page, items: list[tuple[str, str]]) -> dict:
    """Run fetches in the page; retry while Cloudflare / redirects are still navigating."""
    last = None
    for _ in range(8):
        page.wait_for_timeout(4000)
        try:
            if "moment" in page.title().lower():
                continue
            return page.evaluate(FETCH_JS, items)
        except Exception as e:  # execution context destroyed by a navigation
            last = e
    raise RuntimeError(f"HSReplay page never became usable: {last}")


def get_account(page) -> dict | None:
    res = page_fetch(page, [("account", "/api/v1/account/")])["account"]
    return json.loads(res["body"]) if res["status"] == 200 else None


def cmd_login(args) -> int:
    with sync_playwright() as p:
        ctx, page = open_site(p)
        acct = get_account(page)
        if acct is None:
            page.goto(BASE + "/account/login/", wait_until="domcontentloaded")
            print(f"请在弹出的 Chrome 窗口里登录 HSReplay（最长等待 {args.timeout}s）…", flush=True)
            waited = 0
            while acct is None and waited < args.timeout:
                page.wait_for_timeout(5000)
                waited += 5
                try:
                    if "hsreplay.net" not in page.url:
                        continue  # still on the OAuth provider
                    acct = get_account(page)
                except Exception:
                    continue
        close_site(ctx, acct is not None)
    if acct is None:
        print("登录超时，未检测到登录状态。")
        return 1
    print("已登录:", json.dumps(acct, ensure_ascii=False)[:600])
    return 0


def meta_queries(fmt: str, rank: str) -> list[tuple[str, str]]:
    gt = FORMATS[fmt]
    q = f"GameType={gt}&LeagueRankRange={rank}&Region=ALL"
    aq = "/analytics/query"
    items = [(f"{fmt}__{rank}__decks__{tr}", f"{aq}/list_decks_by_win_rate_v2/?{q}&TimeRange={tr}")
             for tr in DECK_TIME_RANGES]
    items += [
        (f"{fmt}__{rank}__archetype_popularity", f"{aq}/archetype_popularity_distribution_stats_v2/?{q}&TimeRange=LAST_7_DAYS"),
        (f"{fmt}__{rank}__matchups", f"{aq}/head_to_head_archetype_matchups_v2/?{q}&TimeRange=LAST_7_DAYS"),
    ]
    if rank == FREE_RANK:
        items.append((f"{fmt}__cards", f"{aq}/card_list_free/?GameType={gt}&TimeRange=CURRENT_PATCH"))
    return items


def collection_urls(acct: dict | None, cfg: dict) -> list[tuple[str, str]]:
    accounts = []
    for a in (acct or {}).get("blizzard_accounts", []) or []:
        if a.get("account_lo") is not None and a.get("region") is not None:
            accounts.append((a["region"], a["account_lo"]))
    if not accounts and cfg.get("account_lo"):
        accounts.append((cfg.get("region", 5), cfg["account_lo"]))
    return [(f"collection__{r}_{lo}", f"/api/v1/collection/?region={r}&account_lo={lo}&type=CONSTRUCTED")
            for r, lo in accounts]


def cmd_fetch(args) -> int:
    cfg = load_config()
    stamp = dt.datetime.now().strftime("%Y%m%d")
    snap = DATA_DIR / "snapshots" / stamp
    snap.mkdir(parents=True, exist_ok=True)
    manifest = {"fetched_at": dt.datetime.now().isoformat(timespec="seconds"), "files": {}}
    formats = [f.strip() for f in args.formats.split(",") if f.strip()]

    for loc in ("enUS", "zhCN"):
        req = urllib.request.Request(CARDS_URL.format(loc=loc), headers={"User-Agent": "hs-deck-advisor/1.0"})
        with urllib.request.urlopen(req, timeout=60) as r:
            (snap / f"cards_{loc}.json").write_bytes(r.read())
        manifest["files"][f"cards_{loc}"] = {"status": 200}

    with sync_playwright() as p:
        ctx, page = open_site(p)
        acct = get_account(page)
        manifest["logged_in"] = acct is not None
        if acct is not None:
            save_json(snap / "account.json", acct)

        items = [("archetypes", "/api/v1/archetypes/")]
        for fmt in formats:
            items += meta_queries(fmt, FREE_RANK)
        if not args.no_collection:
            items += collection_urls(acct, cfg)
        results = page_fetch(page, items)

        # Premium rank ranges: probe one query, fetch the rest only if it is allowed.
        if acct is not None and not args.no_premium:
            for rank in PREMIUM_RANKS:
                qs = [q for fmt in formats for q in meta_queries(fmt, rank)]
                first = page_fetch(page, qs[:1])
                results.update(first)
                if next(iter(first.values()))["status"] == 200:
                    results.update(page_fetch(page, qs[1:]))
        close_site(ctx, acct is not None)

    for name, res in results.items():
        ok = res["status"] == 200
        manifest["files"][name] = {"status": res["status"], "bytes": len(res["body"])}
        if ok:
            (snap / f"{name}.json").write_text(res["body"], encoding="utf-8")
        else:
            manifest["files"][name]["error"] = res["body"][:200]
    save_json(snap / "manifest.json", manifest)

    if LATEST_DIR.exists():
        shutil.rmtree(LATEST_DIR)
    shutil.copytree(snap, LATEST_DIR)

    print(f"snapshot: {snap}")
    print(f"logged_in: {manifest['logged_in']}")
    for name, info in manifest["files"].items():
        mark = "ok " if info["status"] == 200 else "ERR"
        print(f"  {mark} {info['status']:>3} {info.get('bytes', ''):>8} {name} {info.get('error', '')}")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    lg = sub.add_parser("login", help="open Chrome and wait for a manual HSReplay sign-in")
    lg.add_argument("--timeout", type=int, default=600)
    lg.set_defaults(fn=cmd_login)
    ft = sub.add_parser("fetch", help="download meta data and the collection")
    ft.add_argument("--formats", default="standard,wild")
    ft.add_argument("--no-collection", action="store_true")
    ft.add_argument("--no-premium", action="store_true")
    ft.set_defaults(fn=cmd_fetch)
    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
