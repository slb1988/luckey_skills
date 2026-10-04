import contextlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "tablet_diag", Path(__file__).resolve().parents[1] / "scripts" / "tablet_diag.py"
)
diag = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(diag)

IP = "192.0.2.10"
ENDPOINT = IP + ":41000"
DISCOVERY = """__UID__=2000
__TLS__=41000
__TCP__=5555
State Recv-Q Send-Q Local Address:Port Peer Address:Port
LISTEN 0 4 *:41000 *:*
LISTEN 0 4 *:9898 *:*
"""
IDENTITY = {"endpoint": ENDPOINT, "model": "fixture-tablet", "shell_uid": 2000,
            "state": "device", "source": "existing-adb", "online": True, "notes": []}


def result(stdout="", code=0, stderr=""):
    return {"stdout": stdout, "returncode": code, "stderr": stderr,
            "sampled_at": "2030-01-01T00:00:00+00:00", "duration_seconds": 0.01}


def snapshot():
    return {"schema_version": 1, "device": dict(IDENTITY, label="tablet-a"),
            "started_at": "2030-01-01T00:00:00+00:00", "status": "partial",
            "metrics": {"memory.MemAvailable_kib": 1000, "memory.MemFree_kib": 10,
                        "load.1m": 2.5, "thermal.hal_ready": False, "version.firmware": "fixture-1"},
            "errors": {}, "missing_metrics": {"thermal.cpu_gpu_temperature": "HAL 未就绪"}}


class ConnectionTests(unittest.TestCase):
    def test_tls_requires_listener_and_ignores_stale_tcp_property(self):
        self.assertEqual(diag.candidate_ports(DISCOVERY), [41000])
        output = DISCOVERY + "LISTEN 0 4 0.0.0.0:5555 0.0.0.0:*\n"
        self.assertEqual(diag.candidate_ports(output), [41000, 5555])

    def test_loopback_unknown_listener_and_wrong_uid_are_not_candidates(self):
        for output in (DISCOVERY.replace("*:41000", "127.0.0.1:41000"),
                       DISCOVERY.replace("LISTEN 0 4 *:41000", "ESTAB 0 4 *:41000"),
                       DISCOVERY.replace("__UID__=2000", "__UID__=10088"), "OK"):
            with self.assertRaises(RuntimeError):
                diag.candidate_ports(output)

    def test_reuses_only_target_session_and_verifies_identity(self):
        with patch.object(diag.shutil, "which", return_value="adb"), patch.object(diag, "run") as run:
            run.side_effect = [result("List of devices attached\n192.0.2.11:41000\tdevice\n"
                                      + ENDPOINT + "\tdevice\n"), result("device\n"),
                               result("fixture-tablet\n"), result("uid=2000(shell) gid=2000(shell)\n")]
            _, identity = diag.connect(IP)
        self.assertTrue(identity["online"])
        self.assertEqual(identity["source"], "existing-adb")
        for call in run.call_args_list[1:]:
            self.assertEqual(call.args[0][1:3], ["-s", ENDPOINT])

    def test_web_discovery_connects_discovered_port_not_5555(self):
        with patch.object(diag.shutil, "which", return_value="adb"), patch.object(diag, "run") as run:
            run.side_effect = [result("List of devices attached\n"), result(DISCOVERY),
                               result("connected"), result("device"), result("fixture-tablet"),
                               result("uid=2000(shell) gid=2000(shell)")]
            _, identity = diag.connect(IP)
        self.assertEqual(identity["endpoint"], ENDPOINT)
        self.assertEqual(identity["source"], "web-discovery")
        self.assertEqual(run.call_args_list[2].args[0], ["adb", "connect", ENDPOINT])

    def test_adb_connected_text_is_not_success(self):
        with patch.object(diag.shutil, "which", return_value="adb"), patch.object(diag, "run") as run:
            run.side_effect = [result(""), result(DISCOVERY), result("connected"), result("unauthorized")]
            with self.assertRaisesRegex(RuntimeError, "未通过"):
                diag.connect(IP)

    def test_bridge_timeout_is_not_retried(self):
        with patch.object(diag.shutil, "which", return_value="adb"), patch.object(diag, "run") as run:
            run.side_effect = [result(""), result("", 125, "No completion marker received")]
            with self.assertRaisesRegex(RuntimeError, "执行命令"):
                diag.connect(IP)
        self.assertEqual(run.call_count, 2)

    def test_uid_model_and_state_failures(self):
        for replies in ([result("offline")],
                        [result("device"), result("fixture-tablet"), result("uid=0(root)")],
                        [result("device"), result("other-model"), result("uid=2000(shell)")]):
            with patch.object(diag, "run", side_effect=replies):
                with self.assertRaises(RuntimeError):
                    diag.verify("adb", ENDPOINT, expected_model="fixture-tablet")

    def test_no_web_does_not_submit_or_guess(self):
        with patch.object(diag.shutil, "which", return_value="adb"), patch.object(diag, "run", return_value=result("")) as run:
            with self.assertRaisesRegex(RuntimeError, "no-web"):
                diag.connect(IP, use_web=False)
        self.assertEqual(run.call_count, 1)

    def test_timeout_has_no_fabricated_returncode(self):
        with patch.object(diag.subprocess, "run", side_effect=subprocess.TimeoutExpired("adb", 1)):
            probe = diag.run(["adb"], timeout=1)
        self.assertIsNone(probe["returncode"])
        self.assertIn("timed out", probe["stderr"])


class SnapshotTests(unittest.TestCase):
    def test_parsers_keep_units_and_do_not_store_unselected_fields(self):
        self.assertEqual(diag.parse_storage("Filesystem 1K-blocks Used Available Use% Mounted on\n"
                                          "/dev/test 1000 100 900 10% /data\n"),
                         {"data.total_kib": 1000, "data.used_kib": 100, "data.available_kib": 900})
        values = diag.parse_battery("level: 46\nscale: 100\nstatus: 3\nhealth: 2\ntemperature: 265\nserial: secret\n")
        self.assertEqual(values["battery.temperature_c"], 26.5)
        self.assertNotIn("secret", json.dumps(values))
        self.assertEqual(diag.parse_thermal("HAL Ready: false\nThermal Status: 0\n"),
                         {"thermal.hal_ready": False, "thermal.status": 0})
        self.assertEqual(diag.parse_pressure("some avg10=0.00 avg60=0.05 avg300=0.09 total=900\n"),
                         {"avg10": 0.0, "avg60": 0.05, "avg300": 0.09})

    def test_failed_probe_records_real_status_and_missing_not_zero(self):
        with patch.object(diag, "run", return_value=result("", 1, "Permission denied")):
            name, metrics, probe = diag.collect_probe("adb", ENDPOINT, ("memory", diag.probes()["memory"]))
        self.assertEqual(name, "memory")
        self.assertEqual(probe["returncode"], 1)
        self.assertIn("Permission denied", probe["error"])
        self.assertIsNone(metrics["memory.MemAvailable_kib"])
        self.assertNotIn("stdout", probe)

    def test_malformed_probe_is_explicit(self):
        with patch.object(diag, "run", return_value=result("not-a-number")):
            _, metrics, probe = diag.collect_probe("adb", ENDPOINT, ("uptime", diag.probes()["uptime"]))
        self.assertEqual(probe["status"], "partial")
        self.assertIn("解析失败", probe["error"])
        self.assertIsNone(metrics["uptime_seconds"])

    def test_partial_snapshot_saved_with_errors_and_ignored_private_files(self):
        with patch.object(diag, "run", side_effect=lambda *a, **kw: result("", 1, "Permission denied")):
            data = diag.collect("adb", IDENTITY, "tablet-a")
        self.assertEqual(data["status"], "partial")
        self.assertIn("thermal.cpu_gpu_temperature", data["missing_metrics"])
        self.assertIn("memory", data["errors"])
        with tempfile.TemporaryDirectory() as root:
            folder = diag.save(data, root)
            self.assertEqual(json.loads((folder / "snapshot.json").read_text()), data)
            self.assertIn("Permission denied", (folder / "summary.md").read_text())
            self.assertEqual((Path(root) / ".gitignore").read_text(), "*\n")
            self.assertEqual((folder / "snapshot.json").stat().st_mode & 0o777, 0o600)

    def test_collect_cli_returns_partial_exit_code_and_retains_snapshot(self):
        with tempfile.TemporaryDirectory() as root, patch.object(diag, "connect", return_value=("adb", IDENTITY)), \
                patch.object(diag, "run", side_effect=lambda *a, **kw: result("", 1, "Permission denied")), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(diag.main(["collect", IP, "--label", "tablet-a", "--output-dir", root]), 3)
            self.assertEqual(len(list(Path(root).glob("tablet-a/*/snapshot.json"))), 1)

    def test_default_output_uses_outer_repo_not_legacy_nested_skills(self):
        with tempfile.TemporaryDirectory() as root:
            repo = Path(root)
            (repo / ".git").mkdir()
            skills = repo / ".claude" / "skills"
            (skills / ".claude" / "skills").mkdir(parents=True)
            (skills / ".git").touch()
            with patch.object(diag, "__file__", str(skills / "tablet" / "scripts" / "diag.py")):
                self.assertEqual(diag.default_output_dir(), repo.resolve() / ".local" / "iflytek-learning-tablet" / "snapshots")

    def test_compare_changes_and_firmware_warning(self):
        old, new = snapshot(), snapshot()
        new["started_at"] = "2030-01-02T00:00:00+00:00"
        new["metrics"]["memory.MemAvailable_kib"] = 800
        new["metrics"]["version.firmware"] = "fixture-2"
        diff = diag.compare(old, new)
        memory = next(item for item in diff["changes"] if item["metric"] == "memory.MemAvailable_kib")
        self.assertEqual(memory["delta"], -200)
        self.assertIn("固件", diff["warnings"][0])
        self.assertEqual(diff["missing_metrics"]["after"], new["missing_metrics"])

    def test_cross_device_suppresses_deltas(self):
        old, new = snapshot(), snapshot()
        new["device"]["label"] = "tablet-b"
        new["metrics"]["load.1m"] = 10
        diff = diag.compare(old, new)
        self.assertFalse(diff["same_device_candidate"])
        self.assertTrue(all("delta" not in item for item in diff["changes"]))

    def test_missing_and_hal_changes_are_not_numeric_deltas(self):
        old, new = snapshot(), snapshot()
        new["metrics"]["memory.MemAvailable_kib"] = None
        new["metrics"]["thermal.hal_ready"] = True
        diff = diag.compare(old, new)
        self.assertEqual(len(diff["changes"]), 2)
        self.assertTrue(all("delta" not in item for item in diff["changes"]))
        self.assertIn("瞬时", diag.comparison_text(diff))

    def test_schema_mismatch_is_rejected(self):
        old, new = snapshot(), snapshot()
        new["schema_version"] = 2
        with self.assertRaises(ValueError):
            diag.compare(old, new)


if __name__ == "__main__":
    unittest.main()
