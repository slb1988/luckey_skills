"""
Discover all skills in a skills root directory.

A skill lives at exactly depth 2: <root>/<skill-name>/SKILL.md
Prints a JSON array of absolute paths to each SKILL.md found.

Usage:
    python scan_skills.py [--root /path/to/skills] [--exclude skill-name ...]
"""

import argparse
import json
import os
import sys


def scan(root: str, exclude: list[str]) -> list[str]:
    root = os.path.abspath(root)
    results = []
    try:
        entries = os.listdir(root)
    except OSError as e:
        print(f"Error reading root directory: {e}", file=sys.stderr)
        sys.exit(1)

    for entry in sorted(entries):
        if entry in exclude:
            continue
        entry_path = os.path.join(root, entry)
        # Only first-level subdirectories can be skills — skip files
        # (.git, .gitmodules, .DS_Store, etc.) and other non-directory entries.
        if not os.path.isdir(entry_path):
            continue
        skill_md = os.path.join(entry_path, "SKILL.md")
        if os.path.isfile(skill_md):
            results.append(skill_md)

    return results


def main() -> None:
    default_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    parser = argparse.ArgumentParser(description="Discover skill SKILL.md files.")
    parser.add_argument(
        "--root",
        default=default_root,
        help=f"Skills root directory (default: {default_root})",
    )
    parser.add_argument(
        "--exclude",
        nargs="*",
        default=[],
        metavar="SKILL_NAME",
        help="Skill directory names to exclude",
    )
    args = parser.parse_args()

    paths = scan(args.root, args.exclude)
    print(json.dumps(paths, indent=2))


if __name__ == "__main__":
    main()
