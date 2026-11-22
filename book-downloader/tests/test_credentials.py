import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import Mock, patch


class CredentialTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name).resolve()
        self.vault = root / 'vault'
        self.env = self.vault / '.env'
        script = self.vault / '.claude/skills/book-downloader/scripts/bookdl.py'
        script.parent.mkdir(parents=True)
        shutil.copyfile(Path(__file__).resolve().parents[1] / 'scripts/bookdl.py', script)
        home = root / 'home'
        config_dir = home / '.config/book-downloader'
        config_dir.mkdir(parents=True)
        old_env = config_dir / '.env'
        old_env.write_text('ZLIB_EMAIL=old@example.invalid\nZLIB_PASSWORD=old\nANNAS_SECRET_KEY=old\n')
        (config_dir / 'config.json').write_text(json.dumps({
            'zlib': {'email': 'old@example.invalid', 'password': 'old', 'remix_userid': 'cached-id', 'remix_userkey': 'cached-token'},
            'annas': {'secret_key': 'old'},
        }))
        overrides = patch.dict(os.environ, HOME=str(home), USERPROFILE=str(home))
        overrides.start()
        self.addCleanup(overrides.stop)
        spec = importlib.util.spec_from_file_location('bookdl_fixture', script)
        self.cli = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.cli)
        self.assertEqual(self.cli.VAULT_ENV_FILE, self.env)
        original_open = Path.open

        def checked_open(path, *args, **kwargs):
            self.assertNotEqual(path, old_env, 'the retired credential file must not even be opened')
            return original_open(path, *args, **kwargs)

        check = patch.object(Path, 'open', checked_open)
        check.start()
        self.addCleanup(check.stop)

    def test_only_vault_credentials_reach_the_clients(self):
        self.env.write_text('ZLIB_EMAIL=root@example.invalid\nZLIB_PASSWORD="fixture"\nANNAS_SECRET_KEY=root-key\nUNRELATED=value\n')
        self.assertNotIn('UNRELATED', self.cli.load_env())
        zlib = self.cli.Zlib()
        self.addCleanup(zlib.session.close)
        self.assertEqual((zlib.email, zlib.password), ('root@example.invalid', 'fixture'))
        self.assertEqual(self.cli._annas_key(), 'root-key')

    def test_missing_and_partial_vault_file_do_not_merge_other_sources(self):
        for contents in [None, 'ZLIB_EMAIL=root@example.invalid\nZLIB_PASSWORD=\n']:
            with self.subTest(contents=contents):
                if contents is not None:
                    self.env.write_text(contents)
                zlib = self.cli.Zlib()
                self.addCleanup(zlib.session.close)
                self.assertEqual(zlib.email, None if contents is None else 'root@example.invalid')
                self.assertFalse(zlib.password)
                with contextlib.redirect_stderr(io.StringIO()) as err, self.assertRaises(SystemExit):
                    self.cli._annas_key()
                self.assertIn(str(self.env), json.loads(err.getvalue())['hint'])

    def test_preflight_distinguishes_cached_session_from_configured_credentials(self):
        with patch.object(self.cli.Zlib, '_pick_domain'), patch.object(self.cli, '_annas_base', return_value='test.invalid'), \
                patch.object(self.cli.requests, 'get', return_value=Mock(status_code=503)), contextlib.redirect_stdout(io.StringIO()) as out:
            self.cli.cmd_preflight(None)
        data = json.loads(out.getvalue())
        self.assertEqual(data['env_file'], str(self.env))
        self.assertTrue(data['ready'])
        self.assertTrue(data['backends']['zlib']['cached_session'])
        self.assertFalse(data['backends']['zlib']['credentials'])
        self.assertFalse(data['backends']['annas']['credentials'])
        self.assertNotIn('cached-token', out.getvalue())


if __name__ == '__main__':
    unittest.main()
