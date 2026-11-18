#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报销发票凑金额: 扫描根目录 PDF 和图片, 按 PDF 提取值和看图核实值混合凑单,
选出「合计 >= 目标且超出最少」的发票组合, 可选移动到月报目录。

用法:
  python match_invoices.py 2584.47
  python match_invoices.py 500 --reviewed "餐饮.jpg=128.50" --reviewed "同票截图.png=skip"
  python match_invoices.py 2584.47 --move "D:\\work\\报销\\202609_月报"
  python match_invoices.py 2584.47 --dir "D:\\work\\报销"   # 默认值, 一般不用传
"""
import argparse
import re
import shutil
import subprocess
import sys
from decimal import Decimal
from itertools import combinations
from pathlib import Path

POOL_DIR = Path(r"D:\work\报销")
INVOICE_SUFFIXES = {".pdf", ".jpg", ".jpeg", ".jfif", ".png", ".webp", ".bmp",
                    ".gif", ".tif", ".tiff", ".heic", ".heif", ".avif"}


def pdf_text(pdf: Path) -> str:
    r = subprocess.run(["pdftotext", str(pdf), "-"], capture_output=True, timeout=60)
    return r.stdout.decode("utf-8", errors="ignore")


def filename_amount(name: str):
    """文件名金额只作兜底/交叉验证, 发票号码长数字要排除。"""
    for pat in (r"发票金额\s*(\d+(?:\.\d{1,2})?)\s*元",
                r"^(\d+(?:\.\d{1,2})?)\s*元?",
                r"(\d+(?:\.\d{1,2})?)\s*元"):
        m = re.search(pat, name)
        if m:
            v = float(m.group(1))
            if v < 100000:
                return v
    return None


def extract_total(pdf: Path):
    """返回 (价税合计, 依据说明); 失败返回 (None, 原因)。

    电子发票文本层中文常乱码但数字可靠。「合计」行形态为 `金额 价税合计`
    两个小数一行(¥ 可能丢失), 取后者; 用 金额+税额=价税合计 交叉验证。
    多行明细可能凑出干扰对(如 实付+优惠=原价), 故取文档中最后一个通过
    验证的合计行(合计在票据底部), 并优先采信与文件名一致的值。
    注意多明细带折扣发票(青庖等)尾部有税率分组小计段, 明细数字对会偶然
    通过验证; 真实价税合计常是单独数字行, 此时文件名金额更可靠。
    """
    try:
        text = pdf_text(pdf)
    except FileNotFoundError:
        sys.exit("pdftotext 不在 PATH 中(Git Bash 自带, 请检查环境)")
    nums = [float(x) for x in re.findall(r"\d+\.\d{2}", text)]
    pairs = []
    for line in text.splitlines():
        m = re.fullmatch(r"\s*[¥￥]?\s*(\d+\.\d{2})\s+[¥￥]?\s*(\d+\.\d{2})\s*", line)
        if m:
            a, b = float(m.group(1)), float(m.group(2))
            if b >= a:
                pairs.append((a, b))
    validated = [b for a, b in pairs if any(abs(a + t - b) < 0.01 for t in nums)]
    name_v = filename_amount(pdf.name)
    if validated:
        if name_v is not None and any(abs(v - name_v) < 0.01 for v in validated):
            return name_v, "合计行(已验证,与文件名一致)"
        if name_v is not None and any(abs(name_v - n) < 0.01 for n in nums):
            return name_v, "文件名(正文匹配,验证对疑似小计误读)"
        return validated[-1], "合计行(已验证)"
    if pairs:
        if name_v is not None and any(abs(name_v - n) < 0.01 for n in nums):
            return name_v, "文件名(正文匹配,合计行未验证)"
        return pairs[-1][1], "合计行(未验证,低置信)"
    if name_v is not None:
        if any(abs(name_v - n) < 0.01 for n in nums):
            return name_v, "文件名(正文匹配)"
        return name_v, "仅文件名(低置信)"
    if nums:
        return max(nums), "最大数字兜底(低置信)"
    return None, "未提取到金额"


def best_combo(items, target_cents):
    """items: [(path, cents)]; 返回 (total_cents, [indices]) 或 None。"""
    best = None
    for r in range(1, len(items) + 1):
        for idxs in combinations(range(len(items)), r):
            s = sum(items[i][1] for i in idxs)
            if s >= target_cents and (best is None or s < best[0]):
                best = (s, idxs)
        if best is not None and best[0] == target_cents:
            break
    return best


def parse_reviewed(entries, names, parser):
    reviewed = {}
    for entry in entries:
        name, sep, value = entry.rpartition("=")
        if not sep or name not in names:
            parser.error(f"--reviewed 必须指定根目录候选的完整文件名：{entry}")
        if name in reviewed:
            parser.error(f"同一文件只能核对一次：{name}")
        if value == "skip":
            reviewed[name] = None
            continue
        if not re.fullmatch(r"[0-9]+(?:\.[0-9]{1,2})?", value) or Decimal(value) <= 0:
            parser.error(f"{name}：请填票面正金额（最多两位小数）或 skip")
        reviewed[name] = int(Decimal(value) * 100)
    return reviewed


def main():
    ap = argparse.ArgumentParser(description="报销发票凑金额")
    ap.add_argument("target", type=float, help="目标报销金额, 如 2584.47")
    ap.add_argument("--dir", default=str(POOL_DIR), help=f"发票池目录(默认 {POOL_DIR})")
    ap.add_argument("--move", metavar="月报目录", help="把选中的发票移动到该目录")
    ap.add_argument("--reviewed", action="append", default=[], metavar="文件名=金额|skip",
                    help="票面已核实的金额；重复票或非发票填 skip。每个文件单独传一次")
    args = ap.parse_args()

    pool = Path(args.dir)
    if not pool.is_dir():
        ap.error(f"发票池目录不存在：{pool}")
    files = sorted(p for p in pool.iterdir() if p.is_file() and p.suffix.lower() in INVOICE_SUFFIXES)
    if not files:
        sys.exit(f"{pool} 根目录没有 PDF 或发票图片（不递归子目录）")
    reviewed = parse_reviewed(args.reviewed, {p.name for p in files}, ap)

    items = []
    print(f"{'金额':>10}  置信依据                 文件")
    pending = []
    for p in files:
        if p.name in reviewed:
            cents = reviewed[p.name]
            if cents is None:
                print(f"{'-':>10}  已核实排除               {p.name}")
                continue
            how = "已核对票面价税合计"
        elif p.suffix.lower() == ".pdf":
            total, how = extract_total(p)
            cents = None if total is None else round(total * 100)
        else:
            cents, how = None, "图片待核对价税合计"
        if cents is None:
            pending.append(p.name)
            print(f"{'?':>10}  {how:<24}  {p.name}")
        else:
            items.append((p, cents))
            print(f"{cents/100:>10.2f}  {how:<24}  {p.name}")

    if pending:
        sys.exit(f"有 {len(pending)} 个文件待核实；用 --reviewed 传入票面核对结果后再凑单。未移动。")
    if len(items) > 22:
        sys.exit(f"{len(items)} 张发票超出穷举上限，未移动。")

    total_all = sum(c for _, c in items)
    target_c = round(args.target * 100)
    print(f"\n共 {len(items)} 张, 全部合计 {total_all/100:.2f}; 目标 {args.target:.2f}")

    if total_all < target_c:
        print(f"\n[!] 全部发票合计仍差 {(target_c-total_all)/100:.2f}, 无法凑到目标。"
              f"不要移动, 报告差额等用户补充发票。")
        return

    best = best_combo(items, target_c)
    s, idxs = best
    print(f"\n最优组合: {len(idxs)} 张, 合计 {s/100:.2f} (超出 {(s-target_c)/100:.2f})")
    for i in idxs:
        print(f"  {items[i][1]/100:>10.2f}  {items[i][0].name}")

    if args.move:
        dest = Path(args.move)
        for i in idxs:
            if (dest / items[i][0].name).exists():
                sys.exit(f"目标目录有同名文件，本次未移动：{items[i][0].name}")
        dest.mkdir(parents=True, exist_ok=True)
        for i in idxs:
            shutil.move(str(items[i][0]), str(dest / items[i][0].name))
        moved = sorted(p.name for p in dest.iterdir() if p.is_file() and p.suffix.lower() in INVOICE_SUFFIXES)
        print(f"\n已移动 {len(idxs)} 个文件到 {dest}, 目标目录现有 {len(moved)} 个 PDF/图片:")
        for name in moved:
            print(f"  {name}")
    else:
        print("\n(未移动; 加 --move <月报目录> 才会移动)")


if __name__ == "__main__":
    main()
