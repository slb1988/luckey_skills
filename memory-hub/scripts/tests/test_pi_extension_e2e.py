"""Rendered pi-memory-hub.ts 的行为级 e2e：真实 Node 进程加载扩展、mock ExtensionAPI，
验证 agent_end 的 AFK 防抖上传（延时触发、新 prompt 取消、session_shutdown 立即归档）。

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
    def test_agent_end_capture_is_debounced_until_idle(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            extension = render_extension_for_test(workdir)
            state_dir = workdir / "state"
            state_dir.mkdir()
            hook_log = workdir / "hook-log.jsonl"
            env = os.environ.copy()
            env["MEMORY_HOOK_PI_CAPTURE_DELAY_MS"] = "300"
            env["MEMORY_HOOK_STATE_DIR"] = str(state_dir)
            env["HOOK_LOG"] = str(hook_log)
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
            summary = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(summary["ok"])
            # 2 次 idle 定时触发 + 1 次 shutdown 立即归档；中途 prompt/shutdown 各取消一次
            self.assertEqual(summary["captures"], 3)
            self.assertEqual(summary["recalls"], 2)
            self.assertEqual(summary["cancels"], 2)


if __name__ == "__main__":
    unittest.main()
