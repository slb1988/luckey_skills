#!/usr/bin/env python3
"""Seedream (doubao-seedream) text-to-image via Volcengine Ark API.

Reads ARK_API_KEY from environment. Generates N independent images per call
and saves them as <out-dir>/<name>-<i>.png. Prints a JSON summary on stdout.
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ARK_URL = "https://ark.cn-beijing.volces.com/api/v3/images/generations"
DEFAULT_MODEL = "doubao-seedream-4-0-250828"
MAX_RETRIES = 2
REQUEST_TIMEOUT = 180
DOWNLOAD_TIMEOUT = 120


def generate_one(api_key: str, model: str, prompt: str, size: str) -> str:
    """Call Ark images/generations once, return the image URL."""
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model,
        "prompt": prompt,
        "size": size,
        "response_format": "url",
        "watermark": False,
    }
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(ARK_URL, headers=headers, json=payload,
                                 timeout=REQUEST_TIMEOUT)
            if resp.status_code != 200:
                raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:300]}")
            data = resp.json()
            url = data["data"][0]["url"]
            return url
        except Exception as e:  # noqa: BLE001 - retry then surface
            last_err = e
            if attempt < MAX_RETRIES:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"generation failed after {MAX_RETRIES + 1} attempts: {last_err}")


def download(url: str, dest: Path) -> None:
    resp = requests.get(url, timeout=DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    dest.write_bytes(resp.content)


def main() -> int:
    parser = argparse.ArgumentParser(description="Seedream text-to-image via Ark")
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--prompt", help="prompt text")
    src.add_argument("--prompt-file", help="path to a UTF-8 prompt file")
    parser.add_argument("--out-dir", required=True, help="output directory")
    parser.add_argument("--name", default="char", help="filename prefix")
    parser.add_argument("--n", type=int, default=4, help="number of images")
    parser.add_argument("--size", default="2048x2048", help="e.g. 2048x2048 or 1K/2K/4K")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    args = parser.parse_args()

    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        print("ERROR: ARK_API_KEY is not set. Ask the user to set it (never print the key).",
              file=sys.stderr)
        return 2

    prompt = args.prompt
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    prompt = " ".join(prompt.split())
    if not prompt:
        print("ERROR: empty prompt", file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    saved, failed = [], []
    for i in range(1, args.n + 1):
        dest = out_dir / f"{args.name}-{i}.png"
        try:
            url = generate_one(api_key, args.model, prompt, args.size)
            download(url, dest)
            saved.append(str(dest))
            print(f"[{i}/{args.n}] saved {dest}", file=sys.stderr)
        except Exception as e:  # noqa: BLE001 - keep going, report at end
            failed.append({"index": i, "error": str(e)})
            print(f"[{i}/{args.n}] FAILED: {e}", file=sys.stderr)

    print(json.dumps({"saved": saved, "failed": failed}, ensure_ascii=False, indent=2))
    return 0 if saved else 1


if __name__ == "__main__":
    sys.exit(main())
