#!/usr/bin/env python3
"""Send one authorized shell command through 应用管家 and retrieve its result."""

import argparse
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid

MAX_OUTPUT = 2 * 1024 * 1024


def base_url(value):
    url = urllib.parse.urlsplit(value)
    if (url.scheme not in {"http", "https"} or not url.hostname
            or url.username or url.password or url.path not in {"", "/"}
            or url.query or url.fragment):
        raise argparse.ArgumentTypeError("Use a device origin such as http://DEVICE_IP:9898")
    return value.rstrip("/")


def form_data(mode, command):
    prefix = {"adb": "1", "local": "0"}[mode]
    return urllib.parse.urlencode({"shareUrl": prefix + command}).encode()


def capture_command(command, remote_path, marker):
    script = (
        "{ sh -c " + shlex.quote(command)
        + "; result=$?; printf '\\n" + marker + "%s\\n' \"$result\"; } > "
        + shlex.quote(remote_path) + " 2>&1"
    )
    return "sh -c " + shlex.quote(script)


def parse_result(text, marker):
    output, found, status = text.rpartition("\n" + marker)
    if not found or not status.endswith("\n"):
        return None
    status = status.strip()
    if not status.isdecimal() or not 0 <= int(status) <= 255:
        return None
    return output, int(status)


def post_command(opener, origin, mode, command):
    request = urllib.request.Request(origin + "/cmd", data=form_data(mode, command))
    with opener.open(request, timeout=10) as response:
        if response.status != 200 or response.read(1024).strip() != b"OK":
            raise RuntimeError("Unexpected /cmd acknowledgement; execution is unconfirmed")


def wait_result(opener, url, marker, wait_seconds):
    deadline = time.monotonic() + wait_seconds
    while time.monotonic() < deadline:
        try:
            timeout = min(5, max(0.1, deadline - time.monotonic()))
            with opener.open(url, timeout=timeout) as response:
                body = response.read(MAX_OUTPUT + 1)
            if len(body) > MAX_OUTPUT:
                raise RuntimeError("Result exceeds 2 MiB; retrieve the diagnostic file manually")
            result = parse_result(body.decode("utf-8", errors="replace"), marker)
            if result is not None:
                return result
        except urllib.error.HTTPError as exc:
            if exc.code not in {404, 500}:
                raise
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    raise TimeoutError("No completion marker received; remote command may still be running")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True, type=base_url)
    parser.add_argument("--mode", choices=("adb", "local"), default="adb")
    parser.add_argument("--wait-seconds", type=float, default=30)
    parser.add_argument("command", help="Device shell command, without adb shell prefix")
    args = parser.parse_args()
    if args.wait_seconds <= 0:
        parser.error("--wait-seconds must be positive")

    token = uuid.uuid4().hex
    name = "mac-webshell-" + token + ".txt"
    remote_path = "/sdcard/Download/" + name
    marker = "__WEB_SHELL_" + token + "_EXIT__="
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    stage = "submitting"
    try:
        # Never resend a command after an ambiguous acknowledgement or timeout.
        post_command(opener, args.base_url, args.mode,
                     capture_command(args.command, remote_path, marker))
        stage = "waiting for device output"
        output, status = wait_result(opener, args.base_url + "/down/Download/" + name,
                                     marker, args.wait_seconds)
    except (OSError, RuntimeError) as exc:
        print(f"Unconfirmed ({stage}): {exc}\nDevice result file: {remote_path}\nCommand was not retried.",
              file=sys.stderr)
        return 125

    sys.stdout.write(output)
    try:
        post_command(opener, args.base_url, args.mode, "rm -f -- " + shlex.quote(remote_path))
    except (OSError, RuntimeError) as exc:
        print(f"Cleanup unconfirmed: {remote_path}: {exc}", file=sys.stderr)
    return status


if __name__ == "__main__":
    sys.exit(main())
