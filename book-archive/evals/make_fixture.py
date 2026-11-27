"""Create one synthetic Books directory. Copy the trusted tool only, never actual books or catalogues."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

TITLE = '松针索引手册'
LEAF = '10_样本技术/数据库与存储'
OTHER = '10_样本技术/编程语言/Python'
BOOK = f'{LEAF}/{TITLE}'
REL_TEXT = f'{BOOK}/{TITLE}.txt'


def make_epub(path, edition):
    with ZipFile(path, 'x') as z:
        z.writestr('mimetype', 'application/epub+zip', compress_type=ZIP_STORED)
        for name, body in {
            'META-INF/container.xml': '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="book.opf" media-type="application/oebps-package+xml"/></rootfiles></container>',
            'book.opf': f'<package xmlns="http://www.idpf.org/2007/opf" version="2.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:title>{TITLE}</dc:title><dc:creator>林岸（虚构作者）</dc:creator><dc:language>zh</dc:language><dc:identifier id="id">fixture-{edition}</dc:identifier></metadata><manifest><item id="chap" href="chapter.xhtml" media-type="application/xhtml+xml"/><item id="toc" href="toc.ncx" media-type="application/x-dtbncx+xml"/></manifest><spine toc="toc"><itemref idref="chap"/></spine></package>',
            'toc.ncx': f'<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1"><head/><docTitle><text>{TITLE}</text></docTitle><navMap><navPoint id="c" playOrder="1"><navLabel><text>数据库索引</text></navLabel><content src="chapter.xhtml"/></navPoint></navMap></ncx>',
            'chapter.xhtml': f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{TITLE}</title></head><body><h1>{TITLE}</h1><p>林岸（虚构作者） · {edition}</p><p>主题是数据库索引的选择与查找成本；Python 只是演示用的语言。</p></body></html>',
        }.items():
            z.writestr(name, body.encode('utf8'), compress_type=ZIP_DEFLATED)


def build(root, tool, case):
    root = Path(root).resolve()
    tool = Path(tool).resolve(strict=True)
    if root.exists() or any((p / '00_书库指南').exists() for p in root.parents):
        raise ValueError('需要现有书库以外、尚不存在的样本目录')
    root.mkdir(parents=True, exist_ok=False)
    g = root / '00_书库指南'; g.mkdir(); (g / '迁移记录').mkdir()
    local = g / '书库工具.py'; shutil.copyfile(tool, local)
    for leaf in (LEAF, OTHER, '01_待入库/待辨识'):
        (root / leaf).mkdir(parents=True)
    (g / '主题目录.json').write_text(json.dumps([LEAF, OTHER, '01_待入库/待辨识'], ensure_ascii=False), encoding='utf8')
    for name, header in [('书目.csv', ['唯一主题','书名或资料名','相对Books路径','对象']), ('文件指纹.csv', ['相对Books路径','大小_bytes','写入时间_UTC','mtime_ns','sha256'])]:
        with (g / name).open('x', encoding='utf-8-sig', newline='') as f:
            csv.writer(f).writerow(header)
    (root / 'AGENTS.md').write_text('这是合成样本；只处理这个 Books。先读 00_书库指南/分类规则.md。', encoding='utf8')
    (g / '分类规则.md').write_text('一书一主类，以主要用途为准。复用已有主题和书名包；同名不覆盖也不去重删除。编号文件核实后改名，记录旧新路径、字节数与原写入时间。工具命令见 --help。', encoding='utf8')
    (root / BOOK).mkdir(); old = root / REL_TEXT; old.write_bytes(b'fixture original!\n')
    make_epub(root / BOOK / (TITLE + '.epub'), '初版')
    subprocess.run([sys.executable, '-B', str(local), 'register', BOOK, '--分类', LEAF, '--书名', TITLE], cwd=root, check=True, capture_output=True)
    if case == 'intake':
        make_epub(root / '01_待入库' / '0007.epub', '修订版')
    elif case == 'replace':
        st = old.stat(); changed = b'fixture replaced!\n'; assert len(changed) == st.st_size
        old.write_bytes(changed); os.utime(old, ns=(st.st_atime_ns, st.st_mtime_ns))
    elif case == 'index':
        (root / LEAF / '索引.md').write_text('# 手写导航\n\n请勿覆盖。\n', encoding='utf8')
    return root


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('case', choices=['intake', 'replace', 'index']); parser.add_argument('new_root', type=Path)
    parser.add_argument('--tool', type=Path, required=True, help='可信书库工具.py 的路径（仅复制程序）')
    a = parser.parse_args(); print(build(a.new_root, a.tool, a.case))
