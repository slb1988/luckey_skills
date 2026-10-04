#!/usr/bin/env python3
"""Read-only tablet connection, timestamped snapshots and offline comparison (stdlib + adb)."""

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

SCHEMA_VERSION = 1
DISCOVERY = (
    "printf '__UID__='; id -u || exit $?; "
    "printf '__TLS__='; getprop service.adb.tls.port || exit $?; "
    "printf '__TCP__='; getprop service.adb.tcp.port || exit $?; ss -lnt"
)
VERSION_PROPERTIES = {
    "manufacturer": "ro.product.manufacturer",
    "product": "ro.product.device",
    "platform": "ro.board.platform",
    "firmware": "ro.build.display.id",
    "android": "ro.build.version.release",
    "api": "ro.build.version.sdk",
    "security_patch": "ro.build.version.security_patch",
}
CAUTION = (
    "瞬时 load、MemFree 和一次采样不能诊断性能故障；看 MemAvailable 并在相近负载下复采。",
    "仅采 /data，不把只读系统镜像占满当故障；HAL 未就绪表示热指标不可用，不表示过热或温度正常。",
    "设备身份依据用户标签与型号，不读序列号，不能证明同型号设备的物理同一性；标签不要复用给别的设备。",
)


def now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def run(argv, timeout=15):
    started = time.monotonic()
    result = {"sampled_at": now(), "returncode": None, "stdout": "", "stderr": ""}
    try:
        process = subprocess.run(argv, capture_output=True, text=True, timeout=timeout,
                                 encoding="utf-8", errors="replace")
        result.update(returncode=process.returncode, stdout=process.stdout, stderr=process.stderr)
    except (OSError, subprocess.TimeoutExpired) as exc:
        result["stderr"] = str(exc)
    result["duration_seconds"] = round(time.monotonic() - started, 3)
    return result


def checked(result, context):
    if result["returncode"] != 0:
        detail = result["stderr"] or result["stdout"] or "no output"
        raise RuntimeError(f"{context}: {detail.strip()}")
    return result["stdout"].strip()


def ip_address(value):
    try:
        return str(ipaddress.ip_address(value))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("请输入设备当前 IP，不接受网段或主机名") from exc


def host(ip):
    return f"[{ip}]" if ":" in ip else ip


def label(value):
    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}", value):
        raise argparse.ArgumentTypeError("设备标签须为 1–64 位字母/数字/下划线/短横线；不要使用个人姓名")
    return value


def candidate_ports(output):
    uid = re.search(r"^__UID__=(\d+)$", output, re.M)
    if not uid or uid[1] != "2000":
        raise RuntimeError("Web 桥未证明 UID 2000 shell；请确认使用已授权的 ADB 命令模式")
    listeners = set()
    for line in output.splitlines():
        fields = line.split()
        if len(fields) < 5 or fields[0] != "LISTEN":
            continue
        address, sep, port = fields[3].rpartition(":")
        if (sep and port.isdecimal() and address.strip("[]") not in {"127.0.0.1", "::1"}
                and 1 <= int(port) <= 65535):
            listeners.add(int(port))
    ports = []
    for key in ("TLS", "TCP"):
        match = re.search(r"^__" + key + r"__=(\d+)$", output, re.M)
        if match and int(match[1]) in listeners and int(match[1]) not in ports:
            ports.append(int(match[1]))
    if not ports:
        raise RuntimeError("没有属性与非回环 LISTEN 一致的 ADB 端口；在设备执行 getprop service.adb.tls.port 和 ss -lnt 核对")
    return ports


def verify(adb, endpoint, expected_model=None):
    state = checked(run([adb, "-s", endpoint, "get-state"]), "ADB 状态验证")
    if state != "device":
        raise RuntimeError(f"{endpoint} 状态为 {state!r}，不是 device；请在设备确认授权")
    model = checked(run([adb, "-s", endpoint, "shell", "getprop ro.product.model"]), "型号验证")
    identity = checked(run([adb, "-s", endpoint, "shell", "id"]), "shell 身份验证")
    uid = re.search(r"\buid=(\d+)\(shell\)", identity)
    if not model or not uid or uid[1] != "2000":
        raise RuntimeError("未得到非空型号及 uid=2000(shell)；拒绝以未知/root/普通应用身份采集")
    if expected_model and model != expected_model:
        raise RuntimeError(f"型号不匹配：预期 {expected_model!r}，实际 {model!r}")
    return {"endpoint": endpoint, "model": model, "shell_uid": 2000, "state": state}


def connect(ip, adb="adb", use_web=True, expected_model=None):
    adb = shutil.which(adb)
    if not adb:
        raise RuntimeError("找不到 adb；把已有 Android SDK platform-tools 加入 PATH，或指定 --adb /path/to/adb")
    devices = checked(run([adb, "devices"]), "列出 ADB 会话")
    notes = []
    for line in devices.splitlines():
        fields = line.split()
        if len(fields) != 2 or not fields[0].startswith(host(ip) + ":"):
            continue
        endpoint, state = fields
        if state != "device":
            notes.append(f"现有 {endpoint}: {state}；未重置/断开会话")
            continue
        try:
            identity = verify(adb, endpoint, expected_model)
            return adb, dict(identity, source="existing-adb", online=True, notes=notes)
        except RuntimeError as exc:
            notes.append(str(exc))
    if not use_web:
        raise RuntimeError("无有效的目标 ADB 会话，且 --no-web 已禁用自举；" + "; ".join(notes))
    bridge = run([
        sys.executable, str(Path(__file__).with_name("web_shell.py")),
        "--base-url", f"http://{host(ip)}:9898", DISCOVERY,
    ], timeout=60)
    try:
        output = checked(bridge, "Web 端口发现未完成（HTTP OK 不算执行成功）")
        ports = candidate_ports(output)
    except RuntimeError as exc:
        raise RuntimeError(
            f"{exc}\n请核对 IP、同一局域网与设备在线状态，并在管家打开“执行命令”页、确认内部 ADB 已授权连接。"
            "未扫描网络或重置 ADB；确认现场后手动重试。\n" + "; ".join(notes)
        ) from exc
    if bridge["stderr"].strip():
        notes.append(bridge["stderr"].strip())
    for port in ports:
        endpoint = f"{host(ip)}:{port}"
        attempt = run([adb, "connect", endpoint])
        try:
            checked(attempt, f"连接 {endpoint}")
            identity = verify(adb, endpoint, expected_model)
            return adb, dict(identity, source="web-discovery", online=True, notes=notes)
        except RuntimeError as exc:
            notes.append(str(exc))
    raise RuntimeError("已发现监听但未通过 device/型号/UID 验证；请核对设备授权及局域网隔离。\n" + "\n".join(notes))


def pairs(text, separator=":"):
    return {key.strip(): value.strip() for line in text.splitlines()
            for key, sep, value in [line.partition(separator)] if sep}


def parse_versions(text):
    values = pairs(text, "=")
    return {"version." + name: values.get(prop) or None
            for name, prop in VERSION_PROPERTIES.items()}


def parse_memory(text):
    values = pairs(text)
    return {"memory." + key + "_kib": int(values[key].split()[0])
            for key in ("MemTotal", "MemAvailable", "MemFree", "Cached", "SwapTotal", "SwapFree")
            if key in values}


def parse_storage(text):
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 6 and all(item.isdecimal() for item in parts[1:4]):
            return dict(zip(("data.total_kib", "data.used_kib", "data.available_kib"),
                            map(int, parts[1:4])))
    return {}


def parse_battery(text):
    values = pairs(text)
    result = {"battery." + key: int(values[key])
              for key in ("level", "scale", "status", "health") if key in values}
    if "temperature" in values:
        result["battery.temperature_c"] = int(values["temperature"]) / 10
    return result


def parse_thermal(text):
    values = pairs(text)
    ready = values.get("HAL Ready")
    return {"thermal.hal_ready": {"true": True, "false": False}.get(ready),
            "thermal.status": int(values["Thermal Status"]) if "Thermal Status" in values else None}


def parse_pressure(text):
    result = {}
    for line in text.splitlines():
        if line.startswith("some "):
            fields = pairs(line[5:].replace(" ", "\n"), "=")
            result = {"avg" + period: float(fields["avg" + period])
                      for period in ("10", "60", "300") if "avg" + period in fields}
    return result


def probes():
    memory = tuple("memory." + key + "_kib" for key in
                   ("MemTotal", "MemAvailable", "MemFree", "Cached", "SwapTotal", "SwapFree"))
    specs = {
        "versions": ("for p in " + " ".join(VERSION_PROPERTIES.values())
                     + "; do printf '%s=' \"$p\"; getprop \"$p\" || exit $?; done",
                     parse_versions, tuple("version." + key for key in VERSION_PROPERTIES)),
        "kernel": ("uname -r", lambda text: {"version.kernel": text.strip() or None}, ("version.kernel",)),
        "uptime": ("cat /proc/uptime", lambda text: {"uptime_seconds": float(text.split()[0])}, ("uptime_seconds",)),
        "load": ("cat /proc/loadavg", lambda text: dict(zip(("load.1m", "load.5m", "load.15m"),
                 map(float, text.split()[:3]))), ("load.1m", "load.5m", "load.15m")),
        "cpus": ("grep -c '^processor' /proc/cpuinfo", lambda text: {"cpu.logical_count": int(text.strip())},
                 ("cpu.logical_count",)),
        "memory": ("cat /proc/meminfo", parse_memory, memory),
        "storage": ("df -k /data", parse_storage, ("data.total_kib", "data.used_kib", "data.available_kib")),
        "battery": ("dumpsys battery", parse_battery, ("battery.level", "battery.scale", "battery.status",
                    "battery.health", "battery.temperature_c")),
        "thermal": ("dumpsys thermalservice", parse_thermal, ("thermal.hal_ready", "thermal.status")),
        "boot": ("getprop sys.boot_completed", lambda text: {"boot_completed": text.strip() or None}, ("boot_completed",)),
    }
    for resource in ("cpu", "memory", "io"):
        prefix = "pressure." + resource + "."
        specs["pressure_" + resource] = (
            "cat /proc/pressure/" + resource,
            lambda text, prefix=prefix: {prefix + key: value for key, value in parse_pressure(text).items()},
            tuple(prefix + "avg" + period for period in ("10", "60", "300")),
        )
    return specs


def collect_probe(adb, endpoint, item):
    name, (command, parse, expected) = item
    result = run([adb, "-s", endpoint, "shell", command])
    output = result.pop("stdout")
    error = result.pop("stderr").strip()
    values = dict.fromkeys(expected)
    if result["returncode"] == 0:
        try:
            values.update(parse(output))
        except (ValueError, IndexError, KeyError) as exc:
            error = f"解析失败（不是设备故障结论）：{exc}; {error}".strip()
    elif not error:
        error = output.strip()[:1000] or "命令没有返回可用输出"
    missing = [key for key, value in values.items() if value is None]
    result.update(command=command, error=error or None, missing=missing,
                  status="ok" if result["returncode"] == 0 and not error and not missing else "partial")
    return name, values, result


def collect(adb, identity, device_label):
    started = now()
    clock = time.monotonic()
    metrics, results = {}, {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        for name, values, result in pool.map(
                lambda item: collect_probe(adb, identity["endpoint"], item), probes().items()):
            metrics.update(values)
            results[name] = result
    missing = {key: f"{name}: {result['error'] or '输出无此字段'}"
               for name, result in results.items() for key in result["missing"]}
    if metrics.get("thermal.hal_ready") is not True:
        missing["thermal.cpu_gpu_temperature"] = "HAL 未就绪或状态未知，不能验证 CPU/GPU 温度及热降频"
    errors = {name: result["error"] for name, result in results.items() if result["error"]}
    return {
        "schema_version": SCHEMA_VERSION, "started_at": started, "finished_at": now(),
        "duration_seconds": round(time.monotonic() - clock, 3),
        "device": dict(identity, label=device_label, identity_basis="user-label+model; no hardware identifier"),
        "status": "partial" if errors or missing else "complete", "metrics": metrics,
        "probes": results, "errors": errors, "missing_metrics": missing,
        "notes": list(CAUTION) + ["CPU/GPU 温度、应用日志和硬件功能不在默认采集范围；未执行压力测试。"],
    }


def summary(snapshot):
    device = snapshot["device"]
    metrics = snapshot["metrics"]

    def show(key):
        value = metrics.get(key)
        if value is None:
            return "不可用"
        return f"{value / 1048576:.2f} GiB" if key.endswith("_kib") else str(value)

    groups = {
        "系统": ("version.firmware", "version.android", "version.api", "version.security_patch", "version.kernel"),
        "启动": ("boot_completed", "uptime_seconds", "cpu.logical_count"),
        "内存": ("memory.MemAvailable_kib", "memory.MemTotal_kib", "memory.MemFree_kib", "memory.SwapFree_kib"),
        "用户数据分区": ("data.available_kib", "data.total_kib"),
        "Load": ("load.1m", "load.5m", "load.15m"),
        "PSI some avg10 (%)": ("pressure.cpu.avg10", "pressure.memory.avg10", "pressure.io.avg10"),
        "电池": ("battery.level", "battery.scale", "battery.status", "battery.health", "battery.temperature_c"),
        "热服务（非 CPU/GPU 测温）": ("thermal.hal_ready", "thermal.status"),
    }
    lines = ["# 学习机只读快照", f"采样 UTC: {snapshot['started_at']} → {snapshot['finished_at']}",
             f"设备标签: {device['label']} | 型号: {device['model']} | shell UID: {device['shell_uid']}",
             f"连接: {device['endpoint']} ({device['source']}) | 采集状态: {snapshot['status']}", ""]
    lines.extend("- " + name + ": " + "; ".join(f"{key.split('.', 1)[-1].removesuffix('_kib')}={show(key)}" for key in keys)
                 for name, keys in groups.items())
    lines += ["", "## 错误与缺失"]
    lines.extend(f"- {key}: {value}" for key, value in snapshot["errors"].items())
    lines.extend(f"- {key}: {value}" for key, value in snapshot["missing_metrics"].items())
    if not snapshot["errors"] and not snapshot["missing_metrics"]:
        lines.append("- 无采集错误；不等于没有设备故障")
    lines += ["", "## 解释边界"] + ["- " + note for note in snapshot["notes"] + device["notes"]]
    return "\n".join(lines) + "\n"


def default_output_dir():
    for parent in reversed(Path(__file__).resolve().parents):
        if (parent / ".git").exists() and (parent / ".claude" / "skills").is_dir():
            return parent / ".local" / "iflytek-learning-tablet" / "snapshots"
    return Path.home() / ".local" / "iflytek-learning-tablet" / "snapshots"


def save(snapshot, root):
    root = Path(root).expanduser().resolve()
    root.mkdir(parents=True, exist_ok=True)
    ignore = root / ".gitignore"
    if not ignore.exists():
        ignore.write_text("*\n", encoding="utf-8")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    folder = root / snapshot["device"]["label"] / stamp
    folder.mkdir(parents=True, mode=0o700)
    for name, content in (("snapshot.json", json.dumps(snapshot, ensure_ascii=False, indent=2) + "\n"),
                          ("summary.md", summary(snapshot))):
        file = folder / name
        with file.open("x", encoding="utf-8") as stream:
            file.chmod(0o600)
            stream.write(content)
    return folder


def compare(before, after):
    if any(item.get("schema_version") != SCHEMA_VERSION for item in (before, after)):
        raise ValueError("不支持的快照 schema_version；不要把未知格式当作同一口径")
    same = all(before["device"].get(key) == after["device"].get(key) for key in ("label", "model"))
    warnings = list(CAUTION)
    if not same:
        warnings.insert(0, "设备标签或型号不同：可能跨设备，禁止将资源差值视为同设备趋势（已省略差值）")
    versions = {key for key in set(before["metrics"]) | set(after["metrics"]) if key.startswith("version.")}
    if any(before["metrics"].get(key) != after["metrics"].get(key) for key in versions):
        warnings.insert(0, "固件/系统/平台版本变化或缺失：采样口径可能变化，不直接归因为性能退化")
    old_uptime, new_uptime = (item["metrics"].get("uptime_seconds") for item in (before, after))
    if old_uptime is not None and new_uptime is not None and new_uptime < old_uptime:
        warnings.insert(0, "uptime 下降：可能重启或比较顺序反向；不能直接比较累计计数")
    if after["started_at"] <= before["started_at"]:
        warnings.insert(0, "当前快照时间不晚于历史快照；请确认 OLD NEW 顺序及 Mac 时钟")
    changes = []
    for key in sorted(set(before["metrics"]) | set(after["metrics"])):
        old, new = before["metrics"].get(key), after["metrics"].get(key)
        if old == new:
            continue
        item = {"metric": key, "before": old, "after": new}
        if same and all(type(value) in (int, float) for value in (old, new)):
            item["delta"] = round(new - old, 3)
        changes.append(item)
    return {"same_device_candidate": same, "before": before["started_at"], "after": after["started_at"],
            "changes": changes, "warnings": warnings,
            "collection_status": {"before": before["status"], "after": after["status"]},
            "errors": {"before": before["errors"], "after": after["errors"]},
            "missing_metrics": {"before": before["missing_metrics"], "after": after["missing_metrics"]}}


def comparison_text(result):
    lines = [f"快照对比 UTC: {result['before']} → {result['after']}",
             f"采集状态: {result['collection_status']}"] + ["注意: " + item for item in result["warnings"]]
    for item in result["changes"]:
        delta = f" (Δ {item['delta']:+g})" if "delta" in item else ""
        lines.append(f"- {item['metric']}: {item['before']} → {item['after']}{delta}")
    if not result["changes"]:
        lines.append("无已采指标变化（不代表硬件/应用已全面验证）")
    for side in ("before", "after"):
        lines.append(f"{side} 采集错误: {json.dumps(result['errors'][side], ensure_ascii=False)}")
        lines.append(f"{side} 缺失指标: {json.dumps(result['missing_metrics'][side], ensure_ascii=False)}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for command in ("connect", "collect"):
        sub = commands.add_parser(command)
        sub.add_argument("ip", type=ip_address, help="设备当前 IP，仅对这个目标操作")
        sub.add_argument("--adb", default="adb", help="已有 adb 可执行文件路径")
        sub.add_argument("--no-web", action="store_true", help="只复用已验证的 ADB 会话，不使用 Web 自举")
        sub.add_argument("--expect-model", help="可选型号防误连校验，不匹配即失败")
        if command == "collect":
            sub.add_argument("--label", required=True, type=label, help="长期固定的本地设备别名，不是序列号")
            sub.add_argument("--output-dir", type=Path, default=default_output_dir())
    sub = commands.add_parser("compare")
    sub.add_argument("old", type=Path)
    sub.add_argument("new", type=Path)
    sub.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "compare":
            result = compare(json.loads(args.old.read_text(encoding="utf-8")),
                             json.loads(args.new.read_text(encoding="utf-8")))
            print(json.dumps(result, ensure_ascii=False, indent=2) if args.json else comparison_text(result))
            return 0 if result["same_device_candidate"] else 3
        adb, identity = connect(args.ip, args.adb, not args.no_web, args.expect_model)
        if args.command == "connect":
            print(json.dumps(identity, ensure_ascii=False, indent=2))
            return 0
        snapshot = collect(adb, identity, args.label)
        folder = save(snapshot, args.output_dir)
        print(summary(snapshot), end="")
        print(f"\nJSON: {folder / 'snapshot.json'}\n摘要: {folder / 'summary.md'}")
        return 0 if snapshot["status"] == "complete" else 3
    except (OSError, RuntimeError, ValueError, KeyError, TypeError) as exc:
        print(f"失败（未宣称连接/采集成功）：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
