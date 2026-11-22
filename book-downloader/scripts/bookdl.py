#!/usr/bin/env python3
"""
bookdl.py - 统一搜书/下书 CLI（book-downloader skill）

后端:
  zlib   Z-Library EAPI（邮箱+密码登录，remix token 缓存；域名自动 failover）
  libgen libgen.com.de 搜索 + get.php 镜像下载（无需账号；镜像宕机时逐个尝试）
  annas  Anna's Archive fast_download API（仅下载，需捐赠会员 key；md5 与 libgen 互通。
         搜索页有 JS 反爬，但 fast_download.json 是纯 JSON API 无挑战）

约定:
  - 全部 stdout 输出 JSON；错误 JSON 走 stderr 并以非 0 退出
  - 账号凭据: 只读 vault 根目录 .env（ZLIB_EMAIL / ZLIB_PASSWORD / ANNAS_SECRET_KEY）
  - 缓存: ~/.config/book-downloader/config.json（登录会话、域名和镜像设置）
"""

import argparse
import json
import re
import sys
import time
import urllib.parse
from pathlib import Path

import requests

CONFIG_DIR = Path.home() / ".config" / "book-downloader"
CONFIG_FILE = CONFIG_DIR / "config.json"
VAULT_ENV_FILE = Path(__file__).resolve().parents[4] / ".env"
ENV_KEYS = {"ZLIB_EMAIL", "ZLIB_PASSWORD", "ANNAS_SECRET_KEY", "ZLIB_DOMAIN"}
DEFAULT_DOWNLOAD_DIR = Path.home() / "Downloads"
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}
TIMEOUT = 20

ZLIB_DOMAINS = ["z-library.sk", "1lib.sk"]
LIBGEN_SEARCH_MIRRORS = ["libgen.com.de", "libgen.co.in"]
LIBGEN_GET_MIRRORS = ["libgen.la", "libgen.is", "libgen.rs", "libgen.st", "libgen.li", "libgen.bz", "libgen.gl", "libgen.vg"]
ANNAS_MIRRORS = ["annas-archive.gl", "annas-archive.org", "annas-archive.se", "annas-archive.in", "annas-archive.pm", "annas-archive.li"]


# ---------------------------------------------------------------- config

def load_env() -> dict:
    env = {}
    if not VAULT_ENV_FILE.is_file():
        return env
    with VAULT_ENV_FILE.open(encoding="utf-8-sig") as stream:
        for line in stream:
            key, sep, value = line.strip().partition("=")
            key = key.strip()
            if sep and key in ENV_KEYS:
                env[key] = value.strip().strip('"').strip("'")
    return env


def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_config(cfg: dict):
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2, ensure_ascii=False))


def output(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def die(msg: str, hint: str = "", code: int = 1, **extra):
    payload = {"error": msg, "hint": hint or msg}
    payload.update(extra)
    print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
    sys.exit(code)


def sanitize_filename(name: str) -> str:
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    return name[:180] or "book"


# ---------------------------------------------------------------- zlib

class Zlib:
    """最小 Z-Library EAPI 客户端。域名腐化应对: 多域名 failover + 配置覆盖。"""

    def __init__(self):
        cfg = load_config().get("zlib", {})
        env = load_env()
        self.email = env.get("ZLIB_EMAIL")
        self.password = env.get("ZLIB_PASSWORD")
        self.remix_userid = cfg.get("remix_userid")
        self.remix_userkey = cfg.get("remix_userkey")
        override = env.get("ZLIB_DOMAIN") or cfg.get("domain")
        self.domains = ([override] if override else []) + ZLIB_DOMAINS
        self.domain = None
        self.cookies = {"siteLanguageV2": "en"}
        self.session = requests.Session()
        self.session.headers.update(UA)

    def _url(self, path: str) -> str:
        if not self.domain:
            self._pick_domain()
        return f"https://{self.domain}{path}"

    def _pick_domain(self):
        cached = load_config().get("zlib", {}).get("working_domain")
        candidates = ([cached] if cached else []) + self.domains
        seen, ordered = set(), []
        for d in candidates:
            if d and d not in seen:
                seen.add(d)
                ordered.append(d)
        last_err = None
        for d in ordered:
            try:
                r = self.session.post(f"https://{d}/eapi/user/login",
                                      data={"email": "__probe__", "password": "__probe__"},
                                      timeout=TIMEOUT)
                if r.headers.get("content-type", "").startswith("application/json") or r.text.strip().startswith("{"):
                    self.domain = d
                    cfg = load_config()
                    cfg.setdefault("zlib", {})["working_domain"] = d
                    save_config(cfg)
                    return
            except requests.RequestException as e:
                last_err = e
        die("Z-Library 所有域名均不可达", hint=f"tried={ordered} last={last_err}")

    def login(self):
        if self.remix_userid and self.remix_userkey:
            self.cookies.update(remix_userid=str(self.remix_userid), remix_userkey=self.remix_userkey)
            try:
                r = self.session.get(self._url("/eapi/user/profile"), cookies=self.cookies, timeout=TIMEOUT)
                if r.json().get("success"):
                    return
            except (requests.RequestException, ValueError):
                pass
            self.cookies.pop("remix_userid", None)
            self.cookies.pop("remix_userkey", None)
        if not (self.email and self.password):
            die("Z-Library 未配置凭据",
                hint=f"在 {VAULT_ENV_FILE} 写入 ZLIB_EMAIL 和 ZLIB_PASSWORD（没有账号可在 z-library.sk 注册，免费账号有每日额度）")
        try:
            r = self.session.post(self._url("/eapi/user/login"),
                                  data={"email": self.email, "password": self.password}, timeout=TIMEOUT)
            data = r.json()
        except (requests.RequestException, ValueError) as e:
            die("Z-Library 登录请求失败", hint=str(e))
        if not data.get("success"):
            die("Z-Library 登录失败", hint=data.get("error", str(data)))
        user = data["user"]
        self.remix_userid = str(user["id"])
        self.remix_userkey = user["remix_userkey"]
        self.cookies.update(remix_userid=self.remix_userid, remix_userkey=self.remix_userkey)
        cfg = load_config()
        cfg.setdefault("zlib", {}).update(remix_userid=self.remix_userid, remix_userkey=self.remix_userkey)
        save_config(cfg)

    def search(self, query, limit=10, lang=None, ext=None, year_from=None, year_to=None):
        payload = {"message": query, "limit": limit}
        if lang:
            payload["languages"] = lang
        if ext:
            payload["extensions[]"] = ext
        if year_from:
            payload["yearFrom"] = year_from
        if year_to:
            payload["yearTo"] = year_to
        r = self.session.post(self._url("/eapi/book/search"), data=payload, cookies=self.cookies, timeout=TIMEOUT)
        data = r.json()
        if not data.get("success"):
            die("Z-Library 搜索失败", hint=str(data)[:300])
        books = [{
            "source": "zlib", "id": b.get("id"), "hash": b.get("hash"),
            "title": b.get("title", ""), "author": b.get("author", ""),
            "publisher": b.get("publisher", ""), "year": b.get("year", ""),
            "language": b.get("language", ""), "extension": b.get("extension", ""),
            "filesize": b.get("filesizeString", ""),
        } for b in data.get("books", [])]
        return books

    def downloads_left(self):
        r = self.session.get(self._url("/eapi/user/profile"), cookies=self.cookies, timeout=TIMEOUT)
        user = r.json().get("user", {})
        return user.get("downloads_limit", 10) - user.get("downloads_today", 0)

    def download(self, bookid, hashid, out_dir: Path):
        r = self.session.get(self._url(f"/eapi/book/{bookid}/{hashid}/file"),
                             cookies=self.cookies, timeout=TIMEOUT)
        data = r.json()
        info = data.get("file") or {}
        ddl = info.get("downloadLink")
        if not ddl:
            die("Z-Library 取下载链接失败",
                hint=data.get("message", str(data)[:300]) + "（免费账号每日额度有限，可用 quota 子命令查看）")
        desc = info.get("description") or info.get("title") or f"zlibrary-{bookid}"
        author = info.get("author")
        ext = info.get("extension") or "bin"
        filename = sanitize_filename(f"{desc} ({author}).{ext}" if author else f"{desc}.{ext}")
        resp = self.session.get(ddl, timeout=120, stream=True)
        if resp.status_code != 200:
            die("Z-Library 文件下载失败", hint=f"HTTP {resp.status_code}")
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / filename
        path.write_bytes(resp.content)
        return {"source": "zlib", "status": "ok", "path": str(path), "size": path.stat().st_size}


# ---------------------------------------------------------------- libgen

def _libgen_search_once(query):
    """返回 (books_html, busy)。busy=True 表示后端搜索集群临时不可用。"""
    last_err = None
    for host in LIBGEN_SEARCH_MIRRORS:
        try:
            r = requests.get(f"https://{host}/search.php", params={"q": query}, headers=UA, timeout=TIMEOUT)
        except requests.RequestException as e:
            last_err = e
            continue
        if r.status_code != 200:
            last_err = f"{host} HTTP {r.status_code}"
            continue
        if "did not respond" in r.text or "Search servers are busy" in r.text:
            return None, True
        return r.text, False
    if last_err:
        die("libgen 搜索请求失败", hint=str(last_err))
    return None, True


def libgen_search(query, limit=10):
    html = None
    for attempt in range(4):
        html, busy = _libgen_search_once(query)
        if not busy:
            break
        if attempt < 3:
            time.sleep(5)
    else:
        die("libgen 后端搜索集群繁忙（多次重试仍不可用）", hint="稍等几分钟重试；这是 libgen 服务端状态，非本机问题")
    if html is None:
        die("libgen 后端搜索集群繁忙（多次重试仍不可用）", hint="稍等几分钟重试；这是 libgen 服务端状态，非本机问题")
    books = []
    for block in re.findall(r'<div class="book-item">(.*?)(?=<div class="book-item">|$)', html, re.S):
        md5_m = re.search(r'(?:book|download)\.php\?md5=([a-f0-9]{32})', block)
        if not md5_m:
            continue
        def field(label):
            m = re.search(label + r':\s*<strong>(.*?)</strong>', block, re.S)
            return re.sub(r"<[^>]+>", "", m.group(1)).strip() if m else ""
        title_m = re.search(r'class="book-title"[^>]*>\s*<a[^>]*>(.*?)</a>', block, re.S)
        title = re.sub(r"<[^>]+>", "", title_m.group(1)).strip() if title_m else ""
        author_m = re.search(r'class="book-author"[^>]*>(.*?)</div>', block, re.S)
        size_m = re.search(r'<strong>([\d.]+\s*[KMGT]B)</strong>', block)
        books.append({
            "source": "libgen", "md5": md5_m.group(1), "title": title,
            "author": re.sub(r"<[^>]+>", "", author_m.group(1)).strip() if author_m else "",
            "year": field("Year"),
            "language": field("Language"), "extension": field("File"),
            "filesize": size_m.group(1) if size_m else "",
        })
        if len(books) >= limit:
            break
    return books


def _libgen_download_coin(md5, out_dir: Path):
    """libgen.co.in 流程（2026-11-15 实测可用）: GET download.php?md5= 拿表单 → POST md5+action=get。
    返回文件 bytes；后端繁忙时 503，调用方负责重试。"""
    try:
        form = requests.get("https://libgen.co.in/download.php", params={"md5": md5}, headers=UA, timeout=TIMEOUT)
    except requests.RequestException as e:
        return None, f"co.in form {type(e).__name__}"
    if form.status_code != 200:
        return None, f"co.in form HTTP {form.status_code}"
    if 'name="action" value="get"' not in form.text:
        return None, "co.in 未返回下载表单"
    try:
        resp = requests.post("https://libgen.co.in/download.php", data={"md5": md5, "action": "get"},
                             headers=UA, timeout=180)
    except requests.RequestException as e:
        return None, f"co.in POST {type(e).__name__}"
    ct = resp.headers.get("content-type", "")
    if resp.status_code == 200 and "text/html" not in ct and len(resp.content) > 10000:
        return resp.content, None
    return None, f"co.in POST HTTP {resp.status_code} {ct.split(';')[0]}"


def _libgen_download_comde(md5, out_dir: Path):
    """libgen.com.de 流程: download.php 302 到 get.php?md5=&key=（或 ads.php 中转页），提取 key 后换镜像重试。"""
    try:
        r = requests.get("https://libgen.com.de/download.php?md5=" + md5,
                         headers=UA, timeout=TIMEOUT, allow_redirects=False)
    except requests.RequestException as e:
        return None, f"com.de {type(e).__name__}"
    loc = r.headers.get("location", "")
    m = re.search(r"get\.php\?md5=([a-f0-9]{32})&key=(\w+)", loc)
    if not m:
        return None, f"com.de 未取得 get.php 直链 (HTTP {r.status_code} location={loc[:120]})"
    key = m.group(2)
    attempts = []
    for host in LIBGEN_GET_MIRRORS:
        try:
            resp = requests.get(f"https://{host}/get.php?md5={md5}&key={key}",
                                headers=UA, timeout=60, allow_redirects=True)
            ct = resp.headers.get("content-type", "")
            if resp.status_code == 200 and "text/html" not in ct and len(resp.content) > 10000:
                return resp.content, None
            attempts.append(f"{host}: HTTP {resp.status_code}")
        except requests.RequestException as e:
            attempts.append(f"{host}: {type(e).__name__}")
    return None, "; ".join(attempts)


def detect_ext(content: bytes) -> str:
    if content[:5] == b"%PDF-":
        return "pdf"
    if content[:2] == b"PK":
        return "epub"
    return "bin"


def libgen_download(md5, out_dir: Path, filename: str = None):
    """多流程 + 重试。libgen 后端集群经常临时 503/繁忙，单次失败不代表不可用。"""
    attempts = []
    for round_ in range(3):
        for label, fn in (("co.in", _libgen_download_coin), ("com.de", _libgen_download_comde)):
            content, err = fn(md5, out_dir)
            if content:
                out_dir.mkdir(parents=True, exist_ok=True)
                ext = detect_ext(content)
                name = sanitize_filename(filename) if filename else md5
                if not name.lower().endswith("." + ext):
                    name += "." + ext
                path = out_dir / name
                path.write_bytes(content)
                return {"source": "libgen", "status": "ok", "path": str(path),
                        "size": len(content), "mirror": label,
                        "note": "请核对 PDF 元数据标题与目标书目一致"}
            attempts.append(f"[round {round_ + 1}] {label}: {err}")
        if round_ < 2:
            time.sleep(10)
    die("libgen 下载失败（重试 3 轮后仍不行，可能镜像整体宕机，稍后重试）",
        hint="; ".join(attempts)[-600:], md5=md5)


# ---------------------------------------------------------------- annas

def _annas_key():
    key = load_env().get("ANNAS_SECRET_KEY")
    if not key:
        die("Anna's Archive 未配置 key",
            hint=f"捐赠会员后在账号设置里取 key，写入 {VAULT_ENV_FILE} 的 ANNAS_SECRET_KEY")
    return key


def _annas_base():
    cached = load_config().get("annas", {}).get("working_domain")
    for d in ([cached] if cached else []) + ANNAS_MIRRORS:
        try:
            # 用 fast_download API 探活: 真镜像无 key 也返回 JSON 401；parked/假冒域名没有此端点
            r = requests.get(f"https://{d}/dyn/api/fast_download.json",
                             params={"md5": "0" * 32, "key": "probe"}, headers=UA, timeout=10)
            if "json" in r.headers.get("content-type", "") and "download_url" in r.text:
                cfg = load_config()
                cfg.setdefault("annas", {})["working_domain"] = d
                save_config(cfg)
                return f"https://{d}"
        except requests.RequestException:
            continue
    die("Anna's Archive 全部镜像不可达", hint=f"tried={ANNAS_MIRRORS}（当前代理节点可能断连，换节点重试）")


def annas_download(md5, out_dir: Path):
    key = _annas_key()
    base = _annas_base()
    r = requests.get(f"{base}/dyn/api/fast_download.json",
                     params={"md5": md5, "key": key, "path_index": 0, "domain_index": 0},
                     headers=UA, timeout=30)
    try:
        data = r.json()
    except ValueError:
        die("annas fast_download 返回非 JSON", hint=r.text[:200])
    if data.get("error"):
        die("annas fast_download 失败", hint=str(data["error"]))
    url = data.get("download_url")
    if not url:
        die("annas 未返回 download_url", hint=str(data)[:300])
    resp = requests.get(url, headers=UA, timeout=180)
    if resp.status_code != 200:
        die("annas 文件下载失败", hint=f"HTTP {resp.status_code}")
    filename = sanitize_filename(urllib.parse.unquote(url.split("/")[-1].split("?")[0]) or f"{md5}.pdf")
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_bytes(resp.content)
    return {"source": "annas", "status": "ok", "path": str(path), "size": len(resp.content)}


# ---------------------------------------------------------------- commands

def cmd_search(args):
    errors = []
    order = [args.source] if args.source != "auto" else ["zlib", "libgen"]
    for src in order:
        try:
            if src == "zlib":
                z = Zlib()
                z.login()
                books = z.search(args.query, limit=args.limit, lang=args.lang,
                                 ext=args.ext, year_from=args.year_from, year_to=args.year_to)
            else:
                books = libgen_search(args.query, limit=args.limit)
            for i, b in enumerate(books, 1):
                b["n"] = i
            output({"source": src, "count": len(books), "books": books,
                    "hint": f"下载: download --source {src} " + ("--id <id> --hash <hash>" if src == "zlib" else "--md5 <md5>（md5 也可交给 annas 后端下载）")})
            return
        except SystemExit:
            errors.append(f"{src}: 不可用")
            if args.source != "auto":
                raise
    die("所有后端均不可用", hint="; ".join(errors))


def cmd_download(args):
    out_dir = Path(args.output).expanduser() if args.output else DEFAULT_DOWNLOAD_DIR
    if args.source == "zlib":
        if not args.id or not args.hash:
            die("zlib 下载需要 --id 和 --hash")
        z = Zlib()
        z.login()
        result = z.download(args.id, args.hash, out_dir)
    elif args.source == "libgen":
        result = libgen_download(args.md5, out_dir, filename=args.filename)
    else:
        result = annas_download(args.md5, out_dir)
    output(result)


def cmd_quota(_args):
    z = Zlib()
    z.login()
    output({"source": "zlib", "downloads_left": z.downloads_left()})


def cmd_preflight(_args):
    env = load_env()
    zlib_cfg = load_config().get("zlib", {})
    zlib_cred = bool(env.get("ZLIB_EMAIL") and env.get("ZLIB_PASSWORD"))
    cached_session = bool(zlib_cfg.get("remix_userid") and zlib_cfg.get("remix_userkey"))
    annas_key = bool(env.get("ANNAS_SECRET_KEY"))

    zlib_ok = False
    try:
        z = Zlib()
        z._pick_domain()
        zlib_ok = True
        auth_status = "凭据已配置" if zlib_cred else ("仅有缓存会话" if cached_session else "缺凭据")
        zlib_hint = f"EAPI 可达 (domain={z.domain})，{auth_status}"
    except SystemExit:
        zlib_hint = "EAPI 不可达"
    try:
        r = requests.get("https://libgen.com.de/search.php", params={"q": "test"}, headers=UA, timeout=TIMEOUT)
        libgen_hint = f"搜索可达 (HTTP {r.status_code})；下载镜像可用性以实际下载为准"
        libgen_ok = r.status_code == 200
    except requests.RequestException as e:
        libgen_ok, libgen_hint = False, f"不可达: {e}"
    annas_ok = False
    try:
        base = _annas_base()
        annas_ok = True
        annas_hint = f"可达 ({base})" + ("，key 已配置" if annas_key else "，缺 key（下载需捐赠会员）")
    except SystemExit:
        annas_hint = "镜像均不可达（可能是代理节点问题）"

    ready = libgen_ok or (zlib_ok and (zlib_cred or cached_session))
    output({
        "ready": ready,
        "backends": {
            "zlib": {"reachable": zlib_ok, "credentials": zlib_cred, "cached_session": cached_session, "hint": zlib_hint},
            "libgen": {"reachable": libgen_ok, "credentials": "无需账号", "hint": libgen_hint},
            "annas": {"reachable": annas_ok, "credentials": annas_key, "hint": annas_hint},
        },
        "env_file": str(VAULT_ENV_FILE),
    })
    if not ready:
        sys.exit(1)


def main():
    p = argparse.ArgumentParser(prog="bookdl.py", description="统一搜书/下书 CLI (zlib + libgen + annas)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("search", help="搜索书籍")
    s.add_argument("query")
    s.add_argument("--source", choices=["zlib", "libgen", "auto"], default="auto")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--lang", help="语言过滤 (zlib, 如 english/chinese)")
    s.add_argument("--ext", help="格式过滤 (pdf/epub)")
    s.add_argument("--year-from", type=int)
    s.add_argument("--year-to", type=int)
    s.set_defaults(func=cmd_search)

    d = sub.add_parser("download", help="下载书籍")
    d.add_argument("--source", choices=["zlib", "libgen", "annas"], required=True)
    d.add_argument("--id", help="zlib 书籍 id")
    d.add_argument("--hash", help="zlib 书籍 hash")
    d.add_argument("--md5", help="libgen/annas 的 md5")
    d.add_argument("--filename", help="输出文件名（libgen；缺省用 md5+自动识别的扩展名）")
    d.add_argument("-o", "--output", help="输出目录 (默认 ~/Downloads)")
    d.set_defaults(func=cmd_download)

    q = sub.add_parser("quota", help="zlib 今日剩余额度")
    q.set_defaults(func=cmd_quota)

    pf = sub.add_parser("preflight", help="环境自检 (JSON)")
    pf.set_defaults(func=cmd_preflight)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
