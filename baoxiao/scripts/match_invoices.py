#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""报销发票凑金额: 扫描发票池根目录 PDF, 用 pdftotext 提取价税合计,
选出「合计 >= 目标且超出最少」的发票组合, 可选移动到月报目录。

用法:
  python match_invoices.py 2584.47
  python match_invoices.py 2584.47 --move "D:\\work\\报销\\202609_月报"
  python match_invoices.py 2584.47 --dir "D:\\work\\报销"   # 默认值, 一般不用传
"""
import argparse
import re
import shutil
import subprocess
import sys
from itertools import combinations
from pathlib import Path

POOL_DIR = Path(r"D:\work\报销")


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


def main():
    ap = argparse.ArgumentParser(description="报销发票凑金额")
    ap.add_argument("target", type=float, help="目标报销金额, 如 2584.47")
    ap.add_argument("--dir", default=str(POOL_DIR), help=f"发票池目录(默认 {POOL_DIR})")
    ap.add_argument("--move", metavar="月报目录", help="把选中的发票移动到该目录")
    args = ap.parse_args()

    pool = Path(args.dir)
    pdfs = sorted(p for p in pool.glob("*.pdf") if p.is_file())
    if not pdfs:
        sys.exit(f"{pool} 根目录没有 PDF(注意: 只扫根目录, 不递归子目录)")
    if len(pdfs) > 22:
        sys.exit(f"{len(pdfs)} 张发票超出穷举上限, 请先人工筛掉明显不用的")

    items = []
    print(f"{'金额':>10}  置信依据                 文件")
    for p in pdfs:
        total, how = extract_total(p)
        if total is None:
            print(f"{'?':>10}  {how:<24}  {p.name}")
            continue
        items.append((p, round(total * 100)))
        print(f"{total:>10.2f}  {how:<24}  {p.name}")

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
        dest.mkdir(parents=True, exist_ok=True)
        for i in idxs:
            shutil.move(str(items[i][0]), str(dest / items[i][0].name))
        moved = sorted(p.name for p in dest.glob("*.pdf"))
        print(f"\n已移动 {len(idxs)} 个文件到 {dest}, 目标目录现有 {len(moved)} 个 PDF:")
        for name in moved:
            print(f"  {name}")
    else:
        print("\n(未移动; 加 --move <月报目录> 才会移动)")


if __name__ == "__main__":
    main()
