import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import oss_upload as upload


class ProjectConfigTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        (self.root / '.git').mkdir()
        child = self.root / 'notes'
        child.mkdir()
        self.addCleanup(os.chdir, Path.cwd())
        os.chdir(child)
        no_home = patch.object(Path, 'home', side_effect=AssertionError('unexpected home config lookup'))
        no_home.start()
        self.addCleanup(no_home.stop)
        self.config = self.root / '.env'
        self.body = ('OTHER=your_unrelated_placeholder\nexport OSS_ACCESS_KEY_ID="fixture-id"\n'
                     "OSS_ACCESS_KEY_SECRET='fixture-secret' # local\nOSS_BUCKET=test-bucket\n"
                     'OSS_ENDPOINT=oss-cn-shanghai.aliyuncs.com\nOSS_PREFIX=res/\n')

    def test_missing_config_never_uses_or_creates_another_file(self):
        (Path.cwd() / '.env').write_text(self.body)
        with self.assertRaises(SystemExit):
            upload.load_config()
        self.assertFalse(self.config.exists())

    def test_required_fields_are_not_filled_from_other_sources(self):
        self.config.write_text(self.body.replace('OSS_BUCKET=test-bucket', 'OSS_BUCKET='))
        with patch.dict(os.environ, OSS_BUCKET='not-the-project'), self.assertRaisesRegex(SystemExit, 'OSS_BUCKET'):
            upload.load_config()

    def test_upload_uses_only_project_fields_and_keeps_keys_out_of_argv_and_output(self):
        self.config.write_text(self.body, encoding='utf-8-sig')
        self.assertNotIn('OTHER', upload.load_config())
        image = self.root / 'test.gif'
        image.touch()
        output = io.StringIO()
        with patch.object(sys, 'argv', ['oss_upload.py', str(image)]), patch.object(upload, 'find_ossutil', return_value='ossutil'), \
                patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0)) as run, contextlib.redirect_stdout(output):
            upload.main()
        argv, = run.call_args.args
        for field, expected in [('OSS_ACCESS_KEY_ID', 'fixture-id'), ('OSS_ACCESS_KEY_SECRET', 'fixture-secret')]:
            self.assertEqual(run.call_args.kwargs['env'][field], expected)
            self.assertNotIn(expected, argv)
            self.assertNotIn(expected, output.getvalue())
        self.assertRegex(output.getvalue(), r'OSS_URL: https://test-bucket\.oss-cn-shanghai\.aliyuncs\.com/res/\d+\.gif')


if __name__ == '__main__':
    unittest.main()
