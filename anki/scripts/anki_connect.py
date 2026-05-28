#!/usr/bin/env python3
"""
Minimal AnkiConnect client for local automation.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://127.0.0.1:8765"
DEFAULT_VERSION = 6


def load_json_text(raw: str, source: str) -> Any:
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SystemExit(f"Invalid JSON in {source}: {exc}") from exc


def load_json_file(path: str) -> Any:
    file_path = Path(path)
    try:
        return load_json_text(file_path.read_text(encoding="utf-8"), str(file_path))
    except OSError as exc:
        raise SystemExit(f"Unable to read {file_path}: {exc}") from exc


def request(payload: dict[str, Any], url: str, timeout: float) -> dict[str, Any]:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8")
    except urllib.error.URLError as exc:
        raise ConnectionError(str(exc)) from exc

    data = load_json_text(raw, "response body")
    if not isinstance(data, dict):
        raise SystemExit("Unexpected response: expected a JSON object")
    return data


def execute_with_retry(
    payload: dict[str, Any],
    url: str,
    timeout: float,
    retries: int,
    retry_delay: float,
) -> dict[str, Any]:
    attempt = 0
    while True:
        try:
            return request(payload, url=url, timeout=timeout)
        except ConnectionError as exc:
            if attempt >= retries:
                raise SystemExit(
                    "Unable to reach AnkiConnect at "
                    f"{url}: {exc}. Start Anki and retry."
                ) from exc
            time.sleep(retry_delay)
            attempt += 1


def build_payload(args: argparse.Namespace) -> dict[str, Any]:
    if args.payload_file:
        payload = load_json_file(args.payload_file)
        if not isinstance(payload, dict):
            raise SystemExit("Payload file must contain a JSON object")
        if "action" not in payload:
            raise SystemExit("Payload file must include an 'action'")
        payload.setdefault("version", args.version)
        return payload

    if not args.action:
        raise SystemExit("Either an action or --payload-file is required")

    params: dict[str, Any] = {}
    if args.params and args.params_file:
        raise SystemExit("Use either --params or --params-file, not both")
    if args.params:
        parsed = load_json_text(args.params, "--params")
        if not isinstance(parsed, dict):
            raise SystemExit("--params must decode to a JSON object")
        params = parsed
    elif args.params_file:
        parsed = load_json_file(args.params_file)
        if not isinstance(parsed, dict):
            raise SystemExit("--params-file must contain a JSON object")
        params = parsed

    payload = {"action": args.action, "version": args.version}
    if params:
        payload["params"] = params
    return payload


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Call the local AnkiConnect API.")
    parser.add_argument("action", nargs="?", help="AnkiConnect action name")
    parser.add_argument("--params", help="JSON object for the params field")
    parser.add_argument("--params-file", help="Path to a JSON file for params")
    parser.add_argument(
        "--payload-file",
        help="Path to a full JSON payload containing action/version/params",
    )
    parser.add_argument("--url", default=DEFAULT_URL, help="AnkiConnect endpoint URL")
    parser.add_argument(
        "--version",
        type=int,
        default=DEFAULT_VERSION,
        help="AnkiConnect API version",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds",
    )
    parser.add_argument(
        "--retries",
        type=int,
        default=0,
        help="Retry count for connection failures",
    )
    parser.add_argument(
        "--retry-delay",
        type=float,
        default=1.0,
        help="Delay between retries in seconds",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Print compact JSON instead of pretty JSON",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = build_payload(args)
    response = execute_with_retry(
        payload,
        url=args.url,
        timeout=args.timeout,
        retries=args.retries,
        retry_delay=args.retry_delay,
    )
    if response.get("error") is not None:
        print(json.dumps(response, ensure_ascii=False, indent=2), file=sys.stderr)
        return 1

    if args.compact:
        print(json.dumps(response, ensure_ascii=False, separators=(",", ":")))
    else:
        print(json.dumps(response, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
