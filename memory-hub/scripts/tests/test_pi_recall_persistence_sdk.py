"""Actual installed Pi SDK contract tests; external retrieval/model work is faked."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from test_pi_extension_e2e import NODE, TESTS_DIR, render_extension_for_test

PACKAGE_DIR = os.environ.get("PI_CODING_AGENT_PACKAGE_DIR")


@unittest.skipUnless(NODE and PACKAGE_DIR, "set PI_CODING_AGENT_PACKAGE_DIR to an installed Pi package")
class PiRecallPersistenceSDKTest(unittest.TestCase):
    def test_real_sdk_delivery_persistence_and_recovery(self):
        with tempfile.TemporaryDirectory() as directory:
            workdir = Path(directory)
            extension = render_extension_for_test(workdir)
            state = workdir / "state"
            state.mkdir()
            env = os.environ.copy()
            for key in list(env):
                if key.startswith(("MEMORY_HOOK_", "MEMORY_HUB_", "FAKE_")):
                    env.pop(key)
            env.update({
                "MEMORY_HOOK_STATE_DIR": str(state),
                "MEMORY_HOOK_PI_CAPTURE_DELAY_MS": "3600000",
                "MEMORY_HOOK_PI_BOOTSTRAP_TIMEOUT_MS": "5000",
                "MEMORY_HUB_CLIENT_USER_ID": "sunlaibing",
                "HOOK_LOG": str(workdir / "hook-log.jsonl"),
            })
            result = subprocess.run(
                [NODE, str(TESTS_DIR / "pi_recall_persistence_sdk.mjs"), str(extension), str(workdir)],
                cwd=workdir, env=env, capture_output=True, text=True, encoding="utf-8", timeout=90,
            )
            self.assertEqual(result.returncode, 0, result.stdout + "\n" + result.stderr)
            summary = json.loads(result.stdout.strip().splitlines()[-1])
            self.assertTrue(summary["ok"])
            self.assertEqual(summary["searches"], 1)
            self.assertEqual(summary["real_llm_calls"], 0)
            self.assertEqual(len(summary["passed"]), 15)


if __name__ == "__main__":
    unittest.main()
