"""Shared paths, card database access and deck-code encoding for the deck advisor."""
from __future__ import annotations

import base64
import json
import os
from pathlib import Path

HOME = Path(os.environ.get("HS_ADVISOR_HOME", Path.home() / ".hs-advisor"))
PROFILE_DIR = HOME / "chrome-profile"
DATA_DIR = HOME / "data"
LATEST_DIR = DATA_DIR / "latest"
CONFIG_PATH = HOME / "config.json"

FORMATS = {"standard": "RANKED_STANDARD", "wild": "RANKED_WILD"}
FORMAT_ENUM = {"standard": 2, "wild": 1}

CRAFT_COST = {"COMMON": 40, "RARE": 100, "EPIC": 400, "LEGENDARY": 1600}
DISENCHANT = {"COMMON": 5, "RARE": 20, "EPIC": 100, "LEGENDARY": 400}
GOLDEN_DISENCHANT = {"COMMON": 50, "RARE": 100, "EPIC": 400, "LEGENDARY": 1600}

# Default hero card per class, needed to build an importable deck code.
HERO_DBF = {
    "DEATHKNIGHT": 78065,
    "DEMONHUNTER": 56550,
    "DRUID": 274,
    "HUNTER": 31,
    "MAGE": 637,
    "PALADIN": 671,
    "PRIEST": 813,
    "ROGUE": 930,
    "SHAMAN": 1066,
    "WARLOCK": 893,
    "WARRIOR": 7,
}

CLASS_ZH = {
    "DEATHKNIGHT": "死亡骑士",
    "DEMONHUNTER": "恶魔猎手",
    "DRUID": "德鲁伊",
    "HUNTER": "猎人",
    "MAGE": "法师",
    "PALADIN": "圣骑士",
    "PRIEST": "牧师",
    "ROGUE": "潜行者",
    "SHAMAN": "萨满",
    "WARLOCK": "术士",
    "WARRIOR": "战士",
    "NEUTRAL": "中立",
}


def load_json(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)


def load_config() -> dict:
    return load_json(CONFIG_PATH) if CONFIG_PATH.exists() else {}


def load_cards(data_dir: Path = LATEST_DIR) -> dict[int, dict]:
    """dbfId -> card record, with the Chinese name merged in as `name_zh`."""
    en = load_json(data_dir / "cards_enUS.json")
    zh_path = data_dir / "cards_zhCN.json"
    zh = {c["dbfId"]: c.get("name") for c in load_json(zh_path)} if zh_path.exists() else {}
    cards = {}
    for c in en:
        c["name_zh"] = zh.get(c["dbfId"]) or c.get("name")
        cards[c["dbfId"]] = c
    return cards


def _varint(n: int) -> bytes:
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def encode_deckstring(cards: list[tuple[int, int]], hero_dbf: int, fmt: int,
                      sideboards: list[tuple[int, int, int]] | None = None) -> str:
    """Blizzard deck code. `sideboards` items are (card_dbf, count, owner_dbf)."""
    buf = bytearray(b"\x00")
    buf += _varint(1) + _varint(fmt) + _varint(1) + _varint(hero_dbf)

    def groups(items, key_len):
        ones = sorted(i for i in items if i[1] == 1)
        twos = sorted(i for i in items if i[1] == 2)
        many = sorted(i for i in items if i[1] > 2)
        out = bytearray()
        for grp, with_count in ((ones, False), (twos, False), (many, True)):
            out += _varint(len(grp))
            for it in grp:
                out += _varint(it[0])
                if with_count:
                    out += _varint(it[1])
                if key_len == 3:
                    out += _varint(it[2])
        return out

    buf += groups(cards, 2)
    if sideboards:
        buf += b"\x01" + groups(sideboards, 3)
    else:
        buf += b"\x00"
    return base64.b64encode(bytes(buf)).decode("ascii")
