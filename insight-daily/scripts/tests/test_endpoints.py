"""HTTPS Hub subpath and Dashboard URL compatibility, without reading diary data."""

import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from insight_daily import client_config, derive_dashboard_url


PUBLIC_HUB_URL = "https://luckeyhome.site/memory-hub/agent-api"


class EndpointTest(unittest.TestCase):
    def test_default_client_uses_public_hub_and_dashboard(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {}, clear=True
        ), patch("insight_daily.read_persisted_env_var", return_value=None):
            config = client_config(Path(directory), require_auth=False)
            self.assertEqual(config.base_url, PUBLIC_HUB_URL)
            self.assertEqual(config.dashboard_url, "https://luckeyhome.site/memory-hub/")

    def test_explicit_private_hub_override_still_works(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(
            os.environ, {"MEMORY_HUB_URL": "http://localhost:9287/"}, clear=True
        ), patch("insight_daily.read_persisted_env_var", return_value=None):
            config = client_config(Path(directory), require_auth=False)
            self.assertEqual(config.base_url, "http://localhost:9287")
            self.assertEqual(config.dashboard_url, "http://localhost:9288/")

    def test_public_dashboard_derivation_keeps_the_mount_prefix(self):
        with patch.dict(os.environ, {}, clear=True):
            for base in (PUBLIC_HUB_URL, PUBLIC_HUB_URL + "/"):
                self.assertEqual(derive_dashboard_url(base), "https://luckeyhome.site/memory-hub/")
            self.assertEqual(
                derive_dashboard_url("https://custom.test:443/team/agent-api/"),
                "https://custom.test:443/team/",
            )

    def test_explicit_dashboard_override_wins(self):
        with patch.dict(os.environ, {"MEMORY_HUB_DASHBOARD_URL": "https://dashboard.test/ui"}):
            self.assertEqual(derive_dashboard_url(PUBLIC_HUB_URL), "https://dashboard.test/ui/")


if __name__ == "__main__":
    unittest.main()
