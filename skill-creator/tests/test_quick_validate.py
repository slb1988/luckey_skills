"""Project frontmatter and Pi boolean compatibility fixtures; no business operations."""
import importlib.util
from pathlib import Path
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/quick_validate.py"
spec = importlib.util.spec_from_file_location("quick_validate", SCRIPT)
validator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(validator)


class QuickValidateTests(unittest.TestCase):
    def validate(self, extra="", *, strict=False):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "SKILL.md").write_text(
                "---\nname: example-skill\ndescription: A local fixture for skill validation.\n"
                + extra + "---\n\n# Example\n", encoding="utf-8"
            )
            return validator.validate_skill(directory, strict=strict)

    def test_baseline_passes_both_profiles(self):
        for strict in (False, True):
            self.assertTrue(self.validate(strict=strict)[0])

    def test_pi_booleans_are_accepted(self):
        for value in ("true", "false"):
            with self.subTest(value=value):
                valid, message = self.validate(f"disable-model-invocation: {value}\n")
                self.assertTrue(valid)
                self.assertIn("project Pi compatibility", message)

    def test_strict_rejects_pi_extension(self):
        valid, message = self.validate("disable-model-invocation: true\n", strict=True)
        self.assertFalse(valid)
        self.assertIn("Unexpected key", message)

    def test_pi_extension_requires_boolean(self):
        for value in ('"true"', "0", "1", "null", "[]", "{}"):
            with self.subTest(value=value):
                valid, message = self.validate(f"disable-model-invocation: {value}\n")
                self.assertFalse(valid)
                self.assertIn("must be a boolean", message)

    def test_unknown_keys_still_fail(self):
        for strict in (False, True):
            valid, message = self.validate("unrecognized-behavior: true\n", strict=strict)
            self.assertFalse(valid)
            self.assertIn("Unexpected key", message)

    def test_project_metadata_preserves_top_level_and_existing_metadata(self):
        extra = (
            "title: Example\ntags: [local, regression]\nversion: 1.2.3\n"
            "homepage: https://example.com\nplatforms: [macos, linux]\n"
            "metadata:\n  author: Existing author\ncompatibility: CUPS lp and lpstat\n"
        )
        for strict in (False, True):
            with self.subTest(strict=strict):
                self.assertTrue(self.validate(extra, strict=strict)[0])
                self.assertFalse(self.validate("compatibility: [lp, lpstat]\n", strict=strict)[0])


if __name__ == "__main__":
    unittest.main()
