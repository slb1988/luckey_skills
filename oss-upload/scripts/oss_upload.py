#!/usr/bin/env python3
"""
OSS 上传脚本 - 跨平台（macOS / Windows / Linux）
用法: python oss_upload.py <本地文件路径>
成功后输出: OSS_URL: https://...
"""

import os
import sys
import platform
import shutil
import subprocess
import urllib.request
import zipfile
import tempfile
import time
from pathlib import Path

OSSUTIL_VERSION = "2.3.0"
OSSUTIL_DOWNLOADS = {
    "Darwin":  "ossutil-{v}-mac-amd64.zip",
    "Windows": "ossutil-{v}-windows-amd64.zip",
    "Linux":   "ossutil-{v}-linux-amd64.zip",
}
OSSUTIL_BASE_URL = "https://gosspublic.alicdn.com/ossutil/v2/{v}/{filename}"

CONFIG_FILE = Path.home() / ".claude" / "oss_config.env"
SKILL_DIR = Path(__file__).parent.parent
TEMPLATE_FILE = SKILL_DIR / "config" / "oss_config.env.template"


def ossutil_bin() -> Path:
    """返回 ossutil 可执行文件路径（含 .exe 后缀处理）。"""
    suffix = ".exe" if platform.system() == "Windows" else ""
    return Path.home() / "bin" / f"ossutil{suffix}"


def find_ossutil() -> Path | None:
    """查找已安装的 ossutil，优先 PATH，再检查 ~/bin。"""
    name = "ossutil.exe" if platform.system() == "Windows" else "ossutil"
    if shutil.which(name):
        return Path(shutil.which(name))
    local = ossutil_bin()
    if local.exists():
        return local
    return None


def install_ossutil() -> Path:
    """下载并安装 ossutil 到 ~/bin/。"""
    system = platform.system()
    if system not in OSSUTIL_DOWNLOADS:
        sys.exit(f"不支持的操作系统: {system}")

    filename = OSSUTIL_DOWNLOADS[system].format(v=OSSUTIL_VERSION)
    url = OSSUTIL_BASE_URL.format(v=OSSUTIL_VERSION, filename=filename)

    print(f"ossutil 未安装，正在下载 {filename} ...")
    with tempfile.TemporaryDirectory() as tmp:
        zip_path = os.path.join(tmp, "ossutil.zip")
        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(tmp)

        # 找到解压出的 ossutil 可执行文件
        suffix = ".exe" if system == "Windows" else ""
        inner_name = f"ossutil{suffix}"
        found = None
        for root, _, files in os.walk(tmp):
            for f in files:
                if f == inner_name or f == "ossutil":
                    found = os.path.join(root, f)
                    break

        if not found:
            sys.exit("解压后未找到 ossutil 可执行文件")

        dest = ossutil_bin()
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(found, dest)
        if system != "Windows":
            dest.chmod(0o755)

    print(f"ossutil 安装完成：{dest}")
    return dest


def load_config() -> dict:
    """读取配置文件，首次运行时从模版复制并提示用户。"""
    if not CONFIG_FILE.exists():
        CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TEMPLATE_FILE, CONFIG_FILE)
        print(f"\n首次使用：已创建配置文件 {CONFIG_FILE}")
        print("请用编辑器填写以下字段后重新运行：")
        print("  OSS_ACCESS_KEY_ID     — 阿里云 AccessKey ID")
        print("  OSS_ACCESS_KEY_SECRET — 阿里云 AccessKey Secret")
        print("  OSS_BUCKET            — Bucket 名称")
        print("  OSS_ENDPOINT          — 地域 Endpoint，如 oss-cn-shanghai.aliyuncs.com")
        print("  OSS_PREFIX            — 存储路径前缀，如 images\n")
        sys.exit(1)

    config = {}
    with open(CONFIG_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                config[k.strip()] = v.strip()

    if any("your_" in v for v in config.values()):
        print(f"\n配置文件尚未填写：{CONFIG_FILE}")
        print("请将 your_* 占位符替换为真实值后重新运行。\n")
        sys.exit(1)

    return config


def make_timestamp_filename(local_path: str) -> str:
    """生成毫秒时间戳文件名，保留原始扩展名。"""
    ext = Path(local_path).suffix  # 含点，如 .png
    ms = int(time.time() * 1000)
    return f"{ms}{ext}"


def extract_region(endpoint: str) -> str:
    """从 endpoint 提取 region，如 oss-cn-shanghai.aliyuncs.com -> cn-shanghai。"""
    region = endpoint.replace("oss-", "", 1)
    region = region.replace(".aliyuncs.com", "")
    return region


def main():
    if len(sys.argv) < 2:
        print(f"用法: python {Path(__file__).name} <本地文件路径>")
        sys.exit(1)

    local_file = sys.argv[1]
    if not os.path.isfile(local_file):
        print(f"错误: 文件不存在: {local_file}")
        sys.exit(1)

    # ossutil 检查与安装
    oss_bin = find_ossutil()
    if not oss_bin:
        oss_bin = install_ossutil()

    # 配置加载
    cfg = load_config()
    bucket   = cfg["OSS_BUCKET"].strip()
    endpoint = cfg["OSS_ENDPOINT"].strip()
    prefix   = cfg.get("OSS_PREFIX", "images").strip()
    key_id   = cfg["OSS_ACCESS_KEY_ID"]
    key_sec  = cfg["OSS_ACCESS_KEY_SECRET"]
    region   = extract_region(endpoint)

    # 生成目标文件名
    remote_filename = make_timestamp_filename(local_file)
    oss_dest = f"oss://{bucket}/{prefix}/{remote_filename}"

    print(f"上传: {local_file} -> {oss_dest}")

    cmd = [
        str(oss_bin), "cp", local_file, oss_dest,
        "--access-key-id",     key_id,
        "--access-key-secret", key_sec,
        "--endpoint",          endpoint,
        "--region",            region,
    ]
    result = subprocess.run(cmd)
    if result.returncode != 0:
        sys.exit(f"上传失败，ossutil 退出码: {result.returncode}")

    url = f"https://{bucket}.{endpoint}/{prefix}/{remote_filename}"
    print(f"OSS_URL: {url}")


if __name__ == "__main__":
    main()
