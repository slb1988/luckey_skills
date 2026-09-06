"""Rendered pi-memory-hub.ts 的行为级 e2e：真实 Node 进程加载扩展、mock ExtensionAPI。

v5 语义覆盖：
- 主流程：agent_end 立即 enqueue-only（write-ahead marker）、flush AFK 防抖、
  before_agent_start 取消 flush、session_shutdown 收敛后最终 capture。
- catch-up：session_start 扫描遗留 pending marker，补传 + 隔离损坏 marker +
  恰好一次 flush。
- v25 取消：首轮预热检索可被 Esc/Ctrl+C 中断（杀子进程、outcome=cancelled、
  不注入不重试）；memory_search 工具接 pi abort signal。

需要 node（>=22.6，原生 type stripping）可执行；没有 node 的机器跳过。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from install_hooks import PI_TEMPLATE

TESTS_DIR = Path(__file__).resolve().parent
DRIVER = TESTS_DIR / "pi_extension_e2e.mjs"
FAKE_HOOK = TESTS_DIR / "fake_memory_hook.mjs"
NODE = shutil.which("node")

TYPEBOX_STUB_PACKAGE = {
    "name": "typebox",
    "version": "0.0.0",
    "type": "module",
    "main": "index.js",
    "exports": {".": "./index.js"},
}
# 扩展只用 Type.Object/String/Number/Optional 构造工具参数 schema，stub 原样透传即可。
TYPEBOX_STUB_INDEX = (
    "export const Type = new Proxy({}, { get: () => (value) => value ?? {} });\n"
)


def render_extension_for_test(directory: Path) -> Path:
    """渲染模板：memory hook 指向 fake 记录器，python 指向 node 自身。"""
    content = PI_TEMPLATE.read_text(encoding="utf-8")
    content = content.replace("__MEMORY_HOOK_JSON__", json.dumps(str(FAKE_HOOK)))
    content = content.replace("__PYTHON_JSON__", json.dumps(NODE))
    extension_path = directory / "memory-hub.ts"
    extension_path.write_text(content, encoding="utf-8")
    typebox_dir = directory / "node_modules" / "typebox"
    typebox_dir.mkdir(parents=True)
    (typebox_dir / "package.json").write_text(
        json.dumps(TYPEBOX_STUB_PACKAGE), encoding="utf-8"
    )
    (typebox_dir / "index.js").write_text(TYPEBOX_STUB_INDEX, encoding="utf-8")
    return extension_path


@unittest.skipUnless(NODE, "node executable is required for the pi extension e2e")
class PiExtensionE2ETest(unittest.TestCase):
    def run_driver(self, workdir: Path, extra_env=None) -> dict:
        extension = render_extension_for_test(workdir)
        state_dir = workdir / "state"
        state_dir.mkdir()
        hook_log = workdir / "hook-log.jsonl"
        env = os.environ.copy()
        # Default-off assertions must not inherit a developer shell opt-in or fake scenario.
        for key in (
            "MEMORY_HOOK_PI_PERSONA_CARD",
            "PERSONA_MANUAL",
            "PERSONA_OVERSIZE",
            "FAKE_PERSONA_CARD_FAIL",
            "FAKE_PERSONA_OVERSIZE",
            "FAKE_PERSONA_CARD_DELAY_MS",
        ):
            env.pop(key, None)
        env["MEMORY_HOOK_PI_CAPTURE_DELAY_MS"] = "300"
        env["MEMORY_HOOK_PI_BOOTSTRAP_TIMEOUT_MS"] = "200"
        env["MEMORY_HOOK_STATE_DIR"] = str(state_dir)
        env["HOOK_LOG"] = str(hook_log)
        if extra_env:
            env.update(extra_env)
        result = subprocess.run(
            [
                NODE,
                str(DRIVER),
                str(extension),
                str(workdir / "transcript.jsonl"),
                str(hook_log),
            ],
            cwd=str(workdir),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(
            result.returncode,
            0,
            "e2e driver failed:\nstdout: %s\nstderr: %s"
            % (result.stdout, result.stderr),
        )
        return json.loads(result.stdout.strip().splitlines()[-1])

    def test_agent_end_enqueues_durably_and_flush_is_debounced(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory))
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "main")
            # 3 次 agent_end enqueue + 1 次 shutdown 最终 capture
            self.assertEqual(summary["captures"], 4)
            self.assertEqual(summary["enqueues"], 3)
            # 启动冲刷 1 次 + 空闲到期 1 次；prompt/shutdown 各取消一次
            self.assertEqual(summary["flushes"], 2)
            self.assertEqual(summary["cancels"], 2)
            self.assertEqual(summary["markerDeletes"], 3)

    def test_session_start_catches_up_leftover_markers(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"CATCHUP_MARKER": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "catchup")
            # old（成功）/ missing（transcript 缺失，marker 保留）/ extract（终态删除）
            self.assertEqual(summary["captures"], 3)
            self.assertEqual(summary["flushes"], 1)

    def test_catchup_does_not_delete_newer_live_marker(self):
        # 评审 P1：catch-up 与活体 agent_end 并发时，只能删自己读过的那代 marker。
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(
                Path(directory), {"GENRACE": "1", "FAKE_DELAY_MS": "500"}
            )
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "genrace")
            self.assertEqual(summary["captures"], 2)

    def test_flush_busy_is_retried_until_completed(self):
        # 另一进程持 flush.lock（busy）时 flush 请求不得丢弃：有界重试至完成。
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"FLUSH_BUSY_ONCE": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "main-busy")
            # 启动冲刷 busy+重试 2 次 + 空闲到期 1 次
            self.assertEqual(summary["flushes"], 3)
            self.assertEqual(summary["captures"], 4)

    def test_recall_can_be_cancelled_by_escape_or_ctrl_c(self):
        # v25：首轮预热 Esc/Ctrl+C 可中断（取消即杀子进程，不注入、本会话不重试）；
        # memory_search 工具走 pi abort signal，Esc 中断回合时同步杀子进程。
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(
                Path(directory), {"RECALL_CANCEL": "1", "FAKE_SEARCH_DELAY_MS": "500"}
            )
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "recall-cancel")

    def test_project_bootstrap_timeout_fails_open_without_retry(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(
                Path(directory), {"FAKE_SEARCH_DELAY_MS": "500"}
            )
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "main")

    def test_persona_card_default_off_but_manual_command_and_tool_work(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"PERSONA_MANUAL": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "persona-manual")

    def test_persona_card_opt_in_combines_canonical_card_and_recall(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(
                Path(directory), {"MEMORY_HOOK_PI_PERSONA_CARD": "1"}
            )
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "persona-auto")

    def test_persona_card_failure_does_not_block_recall(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(
                Path(directory),
                {
                    "MEMORY_HOOK_PI_PERSONA_CARD": "1",
                    "FAKE_PERSONA_CARD_FAIL": "1",
                },
            )
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "persona-failure")

    def test_recall_failure_does_not_block_opted_in_persona_card(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(
                Path(directory),
                {
                    "MEMORY_HOOK_PI_PERSONA_CARD": "1",
                    "FAKE_SEARCH_DELAY_MS": "500",
                },
            )
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "persona-auto")

    def test_persona_card_all_consumers_enforce_2500_character_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(
                Path(directory),
                {
                    "MEMORY_HOOK_PI_PERSONA_CARD": "1",
                    "PERSONA_OVERSIZE": "1",
                    "FAKE_PERSONA_OVERSIZE": "1",
                },
            )
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "persona-oversize")

    def test_pi_template_is_v27(self):
        template = PI_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn('const EXTENSION_VERSION = "27";', template)

    def test_project_bootstrap_default_timeout_is_two_minutes(self):
        template = PI_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("const defaultBootstrapTimeoutMs = 120 * 1000;", template)

    def test_project_bootstrap_does_not_expose_player_rating_ui(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"SCORE_GATE": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "score-gate")

    def test_legacy_score_env_does_not_restore_player_rating_ui(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"SCORE_ALL_ZERO": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "score-all-zero")

    def test_extraction_subsession_skips_automatic_bootstrap(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"EXTRACTION_BOOTSTRAP": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "extraction-bootstrap")

    def test_skill_invocation_skips_automatic_bootstrap(self):
        # /skill:name 展开注入块与裸 /skill: 命令都跳过首轮自动预热检索
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"SKILL_BOOTSTRAP": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "skill-bootstrap")

    def test_project_bootstrap_accepts_leading_project_directive(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"PROJECT_DIRECTIVE": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "main")

    def test_project_bootstrap_structures_multiline_prompt(self):
        with tempfile.TemporaryDirectory() as directory:
            summary = self.run_driver(Path(directory), {"MULTILINE_PROMPT": "1"})
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["mode"], "main")

    def test_project_bootstrap_uses_backend_llm_gate_instead_of_player_scores(self):
        template = PI_TEMPLATE.read_text(encoding="utf-8")
        self.assertIn("在线正确性由 Hub LLM 同步门禁", template)
        self.assertIn("return false;", template)


if __name__ == "__main__":
    unittest.main()
