"""Offline deck advisor over the JSON downloaded by hs_fetch.py.

    python hs_advisor.py recommend                 # best decks for my collection + dust
    python hs_advisor.py recommend --format wild --dust 3200 --class MAGE
    python hs_advisor.py recommend --field my_field.json   # re-weight for my own ladder
    python hs_advisor.py meta                      # archetype tier list for the scope
    python hs_advisor.py show <deck_id>            # full list with owned / missing marks

Score = archetype win rate expected against the field (popularity x matchup matrix)
        + how much this exact list beats its archetype average (shrunk by sample size).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

from hs_common import (CLASS_ZH, CRAFT_COST, DISENCHANT, FORMAT_ENUM, GOLDEN_DISENCHANT, HERO_DBF,
                       LATEST_DIR, decode_deckstring, encode_deckstring, load_cards, load_json)

RANK_PREFERENCE = ["DIAMOND_THROUGH_LEGEND", "BRONZE_THROUGH_GOLD"]
FS_RANK_PREFERENCE = ["legend-diamond", "legend", "diamond", "top-2000-legend", "platinum", "bronze-gold", "all"]
TIME_PREFERENCE = ["CURRENT_PATCH", "LAST_30_DAYS"]
SHRINK_GAMES = 600      # prior weight when shrinking a list's win rate toward its archetype
MIN_MATCHUP_GAMES = 30  # ignore matchup cells thinner than this
FREE_SETS = {"CORE"}
# HSReplay uses -<class enum> as the id of the catch-all "other" archetype of a class.
CLASS_ENUM = {1: "DEATHKNIGHT", 2: "DRUID", 3: "HUNTER", 4: "MAGE", 5: "PALADIN", 6: "PRIEST", 7: "ROGUE",
              8: "SHAMAN", 9: "WARLOCK", 10: "WARRIOR", 14: "DEMONHUNTER"}


class Scope:
    """All data for one format + rank range, resolved from the data directory."""

    def __init__(self, data_dir: Path, fmt: str, rank: str | None, time_range: str | None, min_games: int,
                 source: str = "auto"):
        self.dir, self.fmt, self.min_games = data_dir, fmt, min_games
        self.cards = load_cards(data_dir)
        self.matchups: dict = {}        # HSReplay: archetype id -> opponent archetype id -> cell
        self.class_matchups: dict = {}  # Firestone: archetype id -> opponent class -> cell
        self.arch_class: dict = {}
        self.manifest = self._load("manifest.json", {})
        has_fs = any(data_dir.glob(f"fs__{fmt}__*.json"))
        # HSReplay rank names are upper case, so an explicit one selects that source.
        if source == "firestone" or (source == "auto" and has_fs and not (rank and rank.isupper())):
            self._init_firestone(rank)
        else:
            self._init_hsreplay(rank, time_range)

    def _init_hsreplay(self, rank, time_range) -> None:
        self.source = "hsreplay"
        ranks = [rank] if rank else RANK_PREFERENCE
        self.rank = next((r for r in ranks if list(self.dir.glob(f"{self.fmt}__{r}__decks__*.json"))), None)
        if self.rank is None:
            raise SystemExit(f"没有 {self.fmt} 的 HSReplay 卡组数据，请先运行 hs_fetch.py fetch")
        self.archetypes = {a["id"]: a for a in self._load("archetypes.json", [])}
        self.decks, self.time_range = self._load_decks(time_range)
        self.field, self.arch_wr = self._load_field()
        series = self._load(f"{self.fmt}__{self.rank}__matchups.json", {}).get("series", {})
        self.matchups = series.get("data", {})
        for aid, meta in series.get("metadata", {}).items():
            if aid.lstrip("-").isdigit():  # the metadata also carries a "totals" row
                self.arch_wr.setdefault(int(aid), meta.get("win_rate"))
        self.updated = self.manifest.get("hsreplay_fetched_at") or self.manifest.get("fetched_at")
        self.label = "HSReplay（全服区）"
        self.weighting = ("该分段近 7 天各卡组类型的出场率 × 卡组类型间对阵胜率" if self.field and self.matchups
                          else "该模式没有出场率/对阵数据，综合分只反映列表自身胜率（按样本量收缩）")

    def _init_firestone(self, rank) -> None:
        self.source = "firestone"
        ranks = [rank] if rank else FS_RANK_PREFERENCE
        self.rank = next((r for r in ranks if (self.dir / f"fs__{self.fmt}__{r}.json").exists()), None)
        if self.rank is None:
            raise SystemExit(f"没有 {self.fmt} 的 Firestone 数据，请先运行 hs_fetch.py fetch --source firestone")
        raw = load_json(self.dir / f"fs__{self.fmt}__{self.rank}.json")
        self.time_range, self.updated = raw["time_period"], raw.get("last_updated")
        total = sum(a["games"] for a in raw["archetypes"]) or 1
        self.archetypes = {a["id"]: a for a in raw["archetypes"]}
        self.field = {a["id"]: 100.0 * a["games"] / total for a in raw["archetypes"]}
        self.arch_wr = {a["id"]: 100.0 * a["wins"] / a["games"] for a in raw["archetypes"] if a["games"]}
        self.arch_class = {a["id"]: a["class"] for a in raw["archetypes"]}
        self.class_matchups = {int(aid): cells for aid, cells in raw["matchups"].items()}
        decks = [{"code": d["code"], "class": d["class"], "archetype_id": d["archetype_id"], "games": d["games"],
                  "wr": 100.0 * d["wins"] / d["games"] if d["games"] else 0.0} for d in raw["decks"]]
        self._fill_arch_wr(decks)
        self.decks = [d for d in decks if d["games"] >= self.min_games]
        for d in self.decks:
            d["cards"], d["sideboard"] = decode_deckstring(d["code"])
            d["id"] = "fs" + hashlib.md5(d["code"].encode()).hexdigest()[:10]
        self.label = f"Firestone（海外玩家为主，共 {raw.get('data_points', 0)} 场）"
        self.weighting = "该分段各卡组类型的出场率 × 对各职业的胜率（Firestone 的对阵只细到职业）"

    def cell(self, aid, opp):
        """Matchup cell {win_rate, total_games} of archetype `aid` against opposing archetype `opp`."""
        if self.source == "firestone":
            return self.class_matchups.get(aid, {}).get(self.arch_class.get(opp))
        return self.matchups.get(str(aid), {}).get(str(opp))

    def _load(self, name: str, default):
        path = self.dir / name
        return load_json(path) if path.exists() else default

    def _parse_decks(self, raw) -> list[dict]:
        out = []
        for cls, rows in raw.get("series", {}).get("data", {}).items():
            for r in rows:
                # Sideboard rows look like [owner_dbf, [card, count], [card, count], ...].
                side = [(c[0], c[1], row[0]) for row in json.loads(r.get("deck_sideboard") or "[]") for c in row[1:]]
                aid = r.get("archetype_id")
                out.append({
                    "id": r["deck_id"],
                    "class": cls,
                    "cards": [tuple(x) for x in json.loads(r["deck_list"])],
                    "sideboard": side,
                    "archetype_id": int(aid) if aid not in (None, "") else None,
                    "games": int(r.get("total_games") or 0),
                    "wr": float(r.get("win_rate") or 0.0),
                })
        return out

    def _load_decks(self, time_range):
        for tr in ([time_range] if time_range else TIME_PREFERENCE):
            path = self.dir / f"{self.fmt}__{self.rank}__decks__{tr}.json"
            if not path.exists():
                continue
            decks = self._parse_decks(load_json(path))
            solid = [d for d in decks if d["games"] >= self.min_games]
            if time_range or len(solid) >= 30:
                self._fill_arch_wr(decks)
                return solid, tr
        raise SystemExit("卡组数据不足（可降低 --min-games 或指定 --time-range）")

    def _fill_arch_wr(self, decks) -> None:
        """Fallback archetype win rate (games-weighted over its lists) where HSReplay gives none."""
        agg: dict = {}
        for d in decks:
            a = agg.setdefault(d["archetype_id"], [0.0, 0])
            a[0] += d["wr"] * d["games"]
            a[1] += d["games"]
        self.deck_arch_wr = {aid: w / n for aid, (w, n) in agg.items() if n}

    def _load_field(self):
        raw = self._load(f"{self.fmt}__{self.rank}__archetype_popularity.json", {})
        field, wr = {}, {}
        for rows in raw.get("series", {}).get("data", {}).values():
            for r in rows:
                field[r["archetype_id"]] = r.get("pct_of_total", 0.0)
                wr[r["archetype_id"]] = r.get("win_rate")
        return field, wr

    def arch_name(self, aid, cls: str = "") -> str:
        a = self.archetypes.get(aid)
        if a:
            return a["name"]
        if isinstance(aid, int) and aid < 0:
            cls = CLASS_ENUM.get(-aid, cls)
        return f"其他{CLASS_ZH.get(cls, cls)}"

    def card_name(self, dbf: int) -> str:
        c = self.cards.get(dbf)
        return c["name_zh"] if c else f"#{dbf}"

    def expected_wr(self, aid, field: dict) -> tuple[float | None, float]:
        """Field-weighted win rate of an archetype, and the share of the field covered."""
        num = den = 0.0
        for opp, pop in field.items():
            cell = self.cell(aid, opp)
            if cell and cell.get("total_games", 0) >= MIN_MATCHUP_GAMES:
                num += pop * cell["win_rate"]
                den += pop
        total = sum(field.values()) or 1.0
        return (num / den if den else None), den / total


def load_field_override(path: str, scope: Scope) -> dict:
    """User field: {archetype name or id: weight}. Names are matched case-insensitively."""
    by_name = {a["name"].lower(): aid for aid, a in scope.archetypes.items()}
    field = {}
    for key, weight in load_json(Path(path)).items():
        aid = int(key) if str(key).lstrip("-").isdigit() else by_name.get(str(key).lower())
        if aid is None:
            raise SystemExit(f"--field 里的卡组类型无法识别: {key}")
        field[aid] = float(weight)
    return field


class Collection:
    def __init__(self, data_dir: Path, path: str | None):
        files = [Path(path)] if path else sorted(data_dir.glob("collection__*.json"))
        self.loaded = bool(files) and files[0].exists()
        self.owned: dict[int, list[int]] = {}
        self.dust = None
        if self.loaded:
            raw = load_json(files[0])
            self.owned = {int(k): v for k, v in raw.get("collection", {}).items()}
            self.dust = raw.get("dust")
            self.modified = raw.get("lastModified")

    def count(self, dbf: int) -> int:
        return sum(self.owned.get(dbf, [0])[:4])

    def spare_dust(self, cards: dict[int, dict]) -> int:
        """Dust from copies beyond the playable maximum (normal copies go first)."""
        total = 0
        for dbf, counts in self.owned.items():
            card = cards.get(dbf)
            if not card or card.get("rarity") not in DISENCHANT or card.get("set") in FREE_SETS:
                continue
            cap = 1 if card["rarity"] == "LEGENDARY" else 2
            extra = sum(counts[:4]) - cap
            normal_extra = min(max(extra, 0), counts[0])
            total += normal_extra * DISENCHANT[card["rarity"]]
            total += max(extra - normal_extra, 0) * GOLDEN_DISENCHANT[card["rarity"]]
        return total


def evaluate(scope: Scope, coll: Collection, field: dict) -> list[dict]:
    exp_cache = {}
    out = []
    for d in scope.decks:
        aid = d["archetype_id"]
        if aid not in exp_cache:
            exp_cache[aid] = scope.expected_wr(aid, field)
        exp, coverage = exp_cache[aid]
        base = scope.arch_wr.get(aid) or scope.deck_arch_wr.get(aid) or 50.0
        shrunk = (d["wr"] * d["games"] + base * SHRINK_GAMES) / (d["games"] + SHRINK_GAMES)
        field_wr = exp if exp is not None and coverage >= 0.5 else base
        cost, missing, notes = 0, [], []
        for dbf, n in d["cards"] + [(s[0], s[1]) for s in d["sideboard"]]:
            card = scope.cards.get(dbf)
            if card is None:  # non-collectible: companion cards that come with a Fabled / sideboard owner
                continue
            lack = n - coll.count(dbf) if coll.loaded else n
            if lack <= 0:
                continue
            if card.get("set") in FREE_SETS or card.get("rarity") not in CRAFT_COST:
                if coll.loaded:
                    notes.append(f"免费/核心卡未在收藏中: {card['name_zh']}")
                continue
            missing.append((dbf, lack))
            cost += lack * CRAFT_COST[card["rarity"]]
        out.append({**d, "name": scope.arch_name(aid, d["class"]), "shrunk_wr": shrunk, "field_wr": field_wr,
                    "coverage": coverage, "score": field_wr + (shrunk - base), "cost": cost,
                    "missing": missing, "notes": notes})
    return sorted(out, key=lambda x: -x["score"])


def best_per_archetype(rows: list[dict]) -> list[dict]:
    seen, out = set(), []
    for r in rows:
        key = (r["class"], r["archetype_id"])
        if key not in seen:
            seen.add(key)
            out.append(r)
    return out


def deck_code(scope: Scope, d: dict) -> str:
    return d.get("code") or encode_deckstring(d["cards"], HERO_DBF[d["class"]], FORMAT_ENUM[scope.fmt], d["sideboard"] or None)


def fmt_missing(scope: Scope, d: dict) -> str:
    if not d["missing"]:
        return "—"
    parts = []
    for dbf, n in sorted(d["missing"], key=lambda m: -CRAFT_COST[scope.cards[m[0]]["rarity"]]):
        parts.append(f"{scope.card_name(dbf)}×{n}")
    return "、".join(parts)


def table(scope: Scope, rows: list[dict], with_cost: bool) -> list[str]:
    head = "| # | 卡组 | 职业 | 综合分 | 该列表胜率 | 场次 |" + (" 需尘 | 缺卡 |" if with_cost else "")
    lines = [head, "|" + "---|" * (head.count("|") - 1)]
    for i, d in enumerate(rows, 1):
        line = (f"| {i} | {d['name']} | {CLASS_ZH.get(d['class'], d['class'])} | {d['score']:.1f} "
                f"| {d['wr']:.1f}% | {d['games']} |")
        if with_cost:
            line += f" {d['cost']} | {fmt_missing(scope, d)} |"
        lines.append(line)
    return lines


def cmd_recommend(args) -> int:
    scope = Scope(Path(args.data), args.format, args.rank, args.time_range, args.min_games, args.source)
    coll = Collection(scope.dir, args.collection)
    field = load_field_override(args.field, scope) if args.field else scope.field
    rows = evaluate(scope, coll, field)
    if args.cls:
        rows = [r for r in rows if r["class"] == args.cls.upper()]
    dust = args.dust if args.dust is not None else (coll.dust or 0)
    spare = coll.spare_dust(scope.cards) if coll.loaded else 0
    budget = dust

    # Tiers by cost. A pricier list is only worth showing if it beats what a cheaper tier
    # already offers for the same archetype by a real margin.
    pick = (lambda rs: rs) if args.all_variants else best_per_archetype
    ready = pick([r for r in rows if r["cost"] == 0])
    ready = [r for r in ready if r["score"] >= args.min_score] or ready[:3]
    shown = {(r["class"], r["archetype_id"]): r["score"] for r in ready}

    def upgrades(cands):
        out = []
        for r in pick(cands):
            key = (r["class"], r["archetype_id"])
            if args.all_variants or r["score"] > shown.get(key, -1e9) + 0.5:
                out.append(r)
                shown[key] = max(r["score"], shown.get(key, -1e9))
        return out

    craft = upgrades([r for r in rows if 0 < r["cost"] <= budget])[: args.top]
    reach = upgrades([r for r in rows if r["cost"] > budget])[: args.top]
    ready = ready[: args.top]

    if args.json:
        print(json.dumps({"scope": {"source": scope.source, "format": scope.fmt, "rank": scope.rank,
                                    "time_range": scope.time_range, "updated": scope.updated},
                          "dust": dust, "spare_dust": spare, "ready": ready, "craftable": craft, "out_of_reach": reach},
                         ensure_ascii=False))
        return 0

    out = [f"# 炉石卡组推荐（{scope.fmt} / {scope.rank} / {scope.time_range}）", ""]
    out.append(f"- 数据源：{scope.label}，更新于 {scope.updated or '未知'}；"
               f"参与排名的卡组列表 {len(rows)} 个（≥{args.min_games} 场）")
    if coll.loaded:
        kinds = sum(1 for v in coll.owned.values() if sum(v[:4]))
        out.append(f"- 收藏：{kinds} 种卡（HDT 同步于 {coll.modified}）；粉尘 {dust}")
        out.append(f"- 多余副本估算可分解约 {spare} 尘（未计入预算；数据分不清哪些副本不可分解，以游戏内“一键分解”数值为准，"
                   "可用 --dust 传入分解后的总尘）")
    else:
        out.append("- **未找到收藏数据**：以下按“一张卡都没有”计算合成成本，请先 `hs_fetch.py login` 再 `fetch`")
    out.append(f"- 环境权重：{'自定义对手分布 ' + args.field if args.field else scope.weighting}")
    out.append("")

    if coll.loaded:
        out += ["## 现在就能组（0 尘）", ""] + (table(scope, ready, False) if ready else ["（没有完全匹配的列表）"]) + [""]
        out += [f"## 粉尘够合成（≤ {budget} 尘）", ""] + (table(scope, craft, True) if craft else ["（没有）"]) + [""]
    out += [f"## {'超出预算' if coll.loaded else '全部卡组'}（参考）", ""]
    out += (table(scope, reach, True) if reach else ["（预算外没有比上面更强的列表）"]) + [""]

    # Which single crafts open up the most strong decks.
    weight: dict[int, list] = {}
    for d in rows[:60]:
        for dbf, n in d["missing"]:
            w = weight.setdefault(dbf, [0, 0.0])
            w[0] += 1
            w[1] = max(w[1], d["score"])
    if weight and coll.loaded:
        out += ["## 合成优先级（综合分前 60 的列表里最常缺的卡）", "", "| 卡牌 | 稀有度 | 单张尘 | 出现列表数 | 所在最高综合分 |", "|---|---|---|---|---|"]
        for dbf, (n, best) in sorted(weight.items(), key=lambda kv: (-kv[1][0], -kv[1][1]))[:12]:
            c = scope.cards[dbf]
            out.append(f"| {c['name_zh']} | {c['rarity']} | {CRAFT_COST[c['rarity']]} | {n} | {best:.1f} |")
        out.append("")

    out += ["## 卡组代码", ""]
    for d in (ready[:3] + craft[:3] if coll.loaded else reach[:5]):
        out.append(f"- **{d['name']}**（{CLASS_ZH.get(d['class'])}，综合分 {d['score']:.1f}，需 {d['cost']} 尘，id `{d['id']}`）")
        out.append(f"  `{deck_code(scope, d)}`")
        for note in d["notes"]:
            out.append(f"  - 注意：{note}")
    print("\n".join(out))
    return 0


def cmd_meta(args) -> int:
    scope = Scope(Path(args.data), args.format, args.rank, None, args.min_games, args.source)
    field = load_field_override(args.field, scope) if args.field else scope.field
    rows = []
    for aid, pop in field.items():
        exp, cov = scope.expected_wr(aid, field)
        rows.append((pop, aid, scope.arch_wr.get(aid), exp, cov))
    print(f"# 环境概览（{scope.fmt} / {scope.rank}）\n")
    print(f"- 数据源：{scope.label}，更新于 {scope.updated or '未知'}\n- 环境权重：{scope.weighting}\n")
    print("| 卡组类型 | 出场率 | 总胜率 | 对当前环境期望胜率 | 最好打 | 最难打 |\n|---|---|---|---|---|---|")
    top_ids = [aid for _, aid, *_ in sorted(rows, reverse=True)[:15]]
    for pop, aid, wr, exp, _ in sorted(rows, reverse=True)[: args.top]:
        if scope.source == "firestone":  # matchups are per opposing class
            cells = [(c["win_rate"], CLASS_ZH.get(cls, cls)) for cls, c in scope.class_matchups.get(aid, {}).items()
                     if c.get("total_games", 0) >= MIN_MATCHUP_GAMES]
        else:
            cells = [(c["win_rate"], scope.arch_name(int(o))) for o, c in scope.matchups.get(str(aid), {}).items()
                     if int(o) in top_ids and int(o) != aid and c.get("total_games", 0) >= MIN_MATCHUP_GAMES]
        best = max(cells, default=None)
        worst = min(cells, default=None)
        show = lambda c: f"{c[1]} {c[0]:.0f}%" if c else "—"
        print(f"| {scope.arch_name(aid)} | {pop:.2f}% | {wr or 0:.1f}% | "
              f"{'%.1f%%' % exp if exp is not None else '—'} | {show(best)} | {show(worst)} |")
    return 0


def cmd_show(args) -> int:
    source = "firestone" if args.deck_id.startswith("fs") and len(args.deck_id) == 12 else "hsreplay"
    scope = Scope(Path(args.data), args.format, args.rank, args.time_range, 0, source)
    coll = Collection(scope.dir, args.collection)
    d = next((x for x in evaluate(scope, coll, scope.field) if x["id"] == args.deck_id), None)
    if d is None:
        raise SystemExit("当前数据范围内找不到这个 deck_id")
    print(f"# {d['name']}（{CLASS_ZH.get(d['class'])}）胜率 {d['wr']:.1f}% / {d['games']} 场 / 需 {d['cost']} 尘\n")
    for dbf, n in sorted(d["cards"], key=lambda x: (scope.cards.get(x[0], {}).get("cost", 0), scope.card_name(x[0]))):
        c = scope.cards.get(dbf)
        if c is None:
            print(f"- [附带] #{dbf} ×{n}  非可收集卡，随本体自动加入")
            continue
        have = coll.count(dbf) if coll.loaded else 0
        mark = "✓" if have >= n else f"缺{n - have}"
        print(f"- [{c.get('cost', '?')}] {scope.card_name(dbf)} ×{n}  {c.get('rarity', '')}  {mark}")
    print(f"\n`{deck_code(scope, d)}`")
    return 0


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=str(LATEST_DIR))
    sub = ap.add_subparsers(dest="cmd", required=True)

    def common(p):
        p.add_argument("--format", default="standard", choices=list(FORMAT_ENUM))
        p.add_argument("--source", default="auto", choices=["auto", "firestone", "hsreplay"],
                       help="auto：有 Firestone 数据就用它（钻石–传说），否则 HSReplay")
        p.add_argument("--rank", help="Firestone：legend-diamond（默认）/ legend / diamond …；"
                                      "HSReplay：BRONZE_THROUGH_GOLD / DIAMOND_THROUGH_LEGEND（需 Premium）")
        p.add_argument("--min-games", type=int, default=200)
        p.add_argument("--top", type=int, default=12)

    rec = sub.add_parser("recommend")
    common(rec)
    rec.add_argument("--time-range", choices=TIME_PREFERENCE)
    rec.add_argument("--dust", type=int, help="覆盖收藏数据里的粉尘数")
    rec.add_argument("--min-score", type=float, default=50.0, help="“现在就能组”只列综合分不低于此值的卡组")
    rec.add_argument("--class", dest="cls")
    rec.add_argument("--collection", help="收藏 JSON 路径（默认取 data 目录里的）")
    rec.add_argument("--field", help="自定义对手分布 JSON：{卡组类型名或 id: 权重}")
    rec.add_argument("--all-variants", action="store_true", help="同一类型不去重")
    rec.add_argument("--json", action="store_true")
    rec.set_defaults(fn=cmd_recommend)

    meta = sub.add_parser("meta")
    common(meta)
    meta.add_argument("--field")
    meta.set_defaults(fn=cmd_meta)

    show = sub.add_parser("show")
    show.add_argument("deck_id")
    common(show)
    show.add_argument("--time-range", choices=TIME_PREFERENCE)
    show.add_argument("--collection")
    show.set_defaults(fn=cmd_show)

    args = ap.parse_args()
    return args.fn(args)


if __name__ == "__main__":
    raise SystemExit(main())
