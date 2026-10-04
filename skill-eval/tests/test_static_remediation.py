"""Offline regression for the scoped health-report remediation (not Tier 2)."""
import hashlib
import importlib.util
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[2]
BASELINE = "1dee18f"
LONG_ENTRIES = (
    "office-js/SKILL.md", "diagram-design/skills/diagram-design/SKILL.md",
    "huashu-design/SKILL.md", "skill-creator/SKILL.md",
)
PROTECTED = {
    "qnap-perforce/references/p4d-server.md": "bf082f4708c39b37dc3f8801c931ae6ff1dacf8acde3593ed529625f31304b82",
    "frp-tunnel-setup/references/frp-setup-record.md": "29e177febeb6b6b81f5a6b837c42c0df044d6342efe61849da5d40d24b8f8024",
    "frp-tunnel-setup/references/frp-client-binding.md": "6cd09a5adb387bf83453ca25b2fac046a74632cd215976fc839c63e301aecae2",
    "memory-hub/references/deploy.md": "20028be26f8cebcd1c1969ab7e0e81a8a777a21c09369700898ca78799ec7ba6",
}
spec = importlib.util.spec_from_file_location("quick_validate", ROOT / "skill-creator/scripts/quick_validate.py")
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


def text(relative):
    return (ROOT / relative).read_text(encoding="utf-8")


def baseline(relative):
    return subprocess.check_output(
        ["git", "-C", str(ROOT), "show", f"{BASELINE}:{relative}"], text=True
    )


def between(content, start, end):
    return content[content.index(start):content.index(end)]


def frontmatter(content):
    return yaml.safe_load(re.match(r"^---\n(.*?)\n---", content, re.S).group(1))


class StaticRemediationTests(unittest.TestCase):
    def test_recursive_structure_profiles(self):
        paths = sorted(p for p in ROOT.rglob("SKILL.md")
                       if ".git" not in p.parts and not any("workspace" in part for part in p.relative_to(ROOT).parts)
                       and p.parent.name != "skill-eval")
        self.assertEqual(len(paths), 79)
        strict_failures = []
        for path in paths:
            valid, message = validator.validate_skill(path.parent)
            self.assertTrue(valid, f"{path.relative_to(ROOT)}: {message}")
            if not validator.validate_skill(path.parent, strict=True)[0]:
                strict_failures.append(str(path.relative_to(ROOT)))
        self.assertEqual(strict_failures, ["skill-harvest/SKILL.md"])
        self.assertIs(frontmatter(text("skill-harvest/SKILL.md"))["disable-model-invocation"], True)
        self.assertTrue(validator.validate_skill(ROOT / "skill-eval", strict=True)[0])

    def test_metadata_preserves_original_frontmatter_layout(self):
        names = ["agent-sdk", "drawio-skill", "memory-hub", "merge-engine-skills", "post-to-wechat",
                 "skill-harvest", "skill-index-patrol", "ue-blueprint-reflection", ".claude/skills/add-github-submodule"]
        for name in names:
            rel = name + "/SKILL.md"
            original = re.match(r"^---\n.*?\n---\n", baseline(rel), re.S).group(0)
            current = re.match(r"^---\n.*?\n---\n", text(rel), re.S).group(0)
            self.assertEqual(original, current, rel)

    def test_four_protected_files_are_unchanged(self):
        for rel, expected in PROTECTED.items():
            self.assertEqual(hashlib.sha256((ROOT / rel).read_bytes()).hexdigest(), expected, rel)

    def test_long_entries_are_under_500_lines(self):
        for rel in LONG_ENTRIES:
            self.assertLess(len(text(rel).splitlines()), 500, rel)

    def test_office_and_environment_moves_preserve_all_examples(self):
        old = baseline("office-js/SKILL.md")
        for name, start, end in [("excel", "# Excel API", "# Word API"),
                                 ("word", "# Word API", "# PowerPoint API"),
                                 ("powerpoint", "# PowerPoint API", "# Common Patterns")]:
            expected = between(old, start, end).removesuffix("---\n\n")
            self.assertTrue(expected.rstrip() == text(f"office-js/references/{name}.md").rstrip(), name)
        environment = between(baseline("skill-creator/SKILL.md"), "## Claude.ai-specific instructions", "## Reference files")
        self.assertTrue(environment.rstrip() in text("skill-creator/references/environment-adaptations.md"))

    def test_design_moves_preserve_gates_and_clauses(self):
        diagram = "diagram-design/skills/diagram-design/"
        old = baseline(diagram + "SKILL.md")
        expected = between(old, "### Background", "### Mandatory connector rules") + between(
            old, "### Node box — full pattern", "## 7. Layout & Spacing").removesuffix("---\n\n")
        self.assertTrue(expected.rstrip() in text(diagram + "references/svg-primitives.md"))
        rules = between(old, "### Mandatory connector rules", "### Node box — full pattern")
        self.assertTrue(rules in text(diagram + "SKILL.md"))
        huashu = baseline("huashu-design/SKILL.md")
        direction = between(huashu, "### 完整流程（7 个 Phase", "## App / iOS 原型专属守则")
        direction = direction.replace("references/", "").replace("`assets/", "`../assets/")
        self.assertTrue(direction.rstrip() in text("huashu-design/references/direction-workflow.md"))
        media = between(huashu, "9. **（默认）导出视频", "10. **（可选）专家评审")
        media = media.replace("references/", "").replace("见SECURITY.md", "见 ../SECURITY.md").replace("`assets/", "`../assets/")
        self.assertTrue(media in text("huashu-design/references/media-delivery.md"))
        for start, end in [("## 设计方向顾问（Fallback 模式）", "### 完整流程"),
                           ("### 🔴 Gate文件协议", "### 问问题的要点")]:
            self.assertTrue(between(huashu, start, end) in text("huashu-design/SKILL.md"))

    def test_added_markdown_links_exist(self):
        changed = subprocess.check_output(["git", "-C", str(ROOT), "diff", BASELINE, "--name-only"], text=True).splitlines()
        untracked = subprocess.check_output(["git", "-C", str(ROOT), "ls-files", "--others", "--exclude-standard"], text=True).splitlines()
        for rel in set(changed + untracked):
            if not rel.endswith(".md") or not (ROOT / rel).is_file():
                continue
            current = text(rel)
            if rel in untracked:
                added = current
            else:
                diff = subprocess.check_output(["git", "-C", str(ROOT), "diff", BASELINE, "--", rel], text=True)
                added = "\n".join(line[1:] for line in diff.splitlines() if line.startswith("+") and not line.startswith("+++"))
            for target in re.findall(r"\]\(([^\s)]+)\)", added):
                path = target.split("#", 1)[0]
                if not path or "://" in path or path.startswith("mailto:"):
                    continue
                self.assertTrue((ROOT / rel).parent.joinpath(path).exists(), f"{rel}: missing {path}")

    def test_active_paths_and_commands(self):
        for name in ("cli-anything-obsidian", "investment-analyzer", "learn-10x", "violoop-report"):
            self.assertFalse(re.search(r"002 Cards|003 Books|301 Daily Notes|210 Learning & Reading|110 Utilities/violoop", text(name + "/SKILL.md")), name)
        self.assertNotIn("git -C <parent_submodule_path> git rm", text("git-tool/SKILL.md"))
        self.assertIn("docker pull langfuse/langfuse:3 && docker pull langfuse/langfuse-worker:3", text("langfuse-server/SKILL.md"))
        self.assertNotIn("http://10.77.77.6:9287/v1", text("memory-review/SKILL.md"))
        for name in ("auto-server-backend-deploy", "auto-server-deploy", "auto-server-frontend-deploy"):
            self.assertNotIn("pi 本身就运行在", text(name + "/SKILL.md"))
            self.assertIn("hostname", text(name + "/SKILL.md"))
        self.assertIn("未生成图片", text("luckey-illustration/SKILL.md"))
        self.assertFalse(re.search(r"P4PASSWD\s*=", text("automerge-clean/SKILL.md")))
        self.assertIn("p4 login -s", text("automerge-clean/SKILL.md"))

    def test_flux_grid_and_evaluation_fields(self):
        table = between(text("text-to-image-prompt/SKILL.md"), "### 常用比例换算表", "> Flux 尺寸")
        sizes = re.findall(r"(\d+)×(\d+)", table)
        self.assertEqual(len(sizes), 6)
        for width, height in sizes:
            self.assertEqual(int(width) % 32, 0)
            self.assertEqual(int(height) % 32, 0)
        diagram = "diagram-design/skills/diagram-design/"
        self.assertNotIn("**All values — font sizes", text(diagram + "SKILL.md") + text(diagram + "references/layout-spacing.md"))
        self.assertIn("7px tags, 9px sublabels and 14px asides", text(diagram + "SKILL.md"))
        creator = text("skill-creator/SKILL.md")
        self.assertIn("evals[].expectations", creator)
        self.assertIn("eval_metadata.json.assertions", creator)
        self.assertNotIn("including the `assertions` field", creator)

    def test_busy_gate_with_stubbed_curl_and_clock(self):
        manual = between(text("auto-server-backend-deploy/SKILL.md"), "## 手动部署", "## 部署后验证")
        block = re.search(r"```bash\n(.*?)\n```", manual, re.S).group(1)
        subprocess.run(["bash", "-n"], input=block, text=True, check=True)
        gate = between(block, "wait_for_idle()", "# 2. 停服").strip()
        idle, busy = ('{"busy":false}', 0), ('{"busy":true}', 0)
        cases = [
            ("two_idle", [idle, idle], True, 2),
            ("busy_resets", [idle, busy, idle, idle], True, 4),
            ("missing_resets", [idle, ('{}', 0), idle, idle], True, 4),
            ("http_error_resets", [idle, ('{"busy":false}', 22), idle, idle], True, 4),
            ("always_busy", [busy], False, None),
            ("single_idle", [idle], False, None),
            ("malformed", [('not-json', 0)], False, None),
            ("string_false", [('{"busy":"false"}', 0)] * 32, False, None),
        ]
        for name, responses, success, count in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as directory:
                counter = Path(directory, "counter")
                counter.write_text("0\n")
                arms = "\n".join(f"{i}) printf '%s' {shlex.quote(body)}; return {status} ;;" for i, (body, status) in enumerate(responses))
                stub = """
curl() {
    local n
    read -r n < "$COUNTER"
    printf '%s\n' "$((n + 1))" > "$COUNTER"
    case "$n" in
""" + arms + """
    *) printf '%s' '{"busy":true}'; return 0 ;;
    esac
}
sleep() { SECONDS=$((SECONDS + $1)); }
SECONDS=0
"""
                environment = {"PATH": str(Path(shutil.which("python3")).parent) + os.pathsep + "/usr/bin:/bin", "COUNTER": str(counter)}
                result = subprocess.run(["bash", "--noprofile", "--norc"], input=stub + gate + "\nprintf 'STOP_GATE_REACHED\\n'\n", text=True,
                                        capture_output=True, env=environment, timeout=30)
                self.assertEqual(result.returncode == 0, success, name)
                self.assertEqual("STOP_GATE_REACHED" in result.stdout, success, name)
                if count is not None:
                    self.assertEqual(int(counter.read_text()), count, name)


if __name__ == "__main__":
    unittest.main()
