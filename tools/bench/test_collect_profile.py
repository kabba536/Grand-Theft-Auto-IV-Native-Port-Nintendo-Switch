"""Synthetic local tests: no FTP server or console is contacted."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collect_profile
from test_rex_profile import PREFIX, report


class CollectionTests(unittest.TestCase):
    def invoke(self, parent, contents):
        seen = []
        def fake_collect(host, port, user, password, remote, output, timeout, limit):
            seen.append((password, remote))
            Path(output).write_text(contents, encoding='utf-8')
            return {'status': 'collected', 'local_path': str(output)}
        output, error = io.StringIO(), io.StringIO()
        with patch.object(collect_profile.collect, 'collect', side_effect=fake_collect), \
             patch.dict(os.environ, {'GTA4NX_FTP_PASSWORD': 'synthetic-secret'}), \
             contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = collect_profile.main(['--host', 'example.invalid', '--remote', '/logs/rex_perfil.log', '--output-dir', str(parent)])
        return code, output.getvalue(), error.getvalue(), seen

    def test_synthetic_success_creates_unique_directories(self):
        with tempfile.TemporaryDirectory() as tmp:
            first = self.invoke(tmp, PREFIX + report())
            second = self.invoke(tmp, PREFIX + report())
            self.assertEqual(first[0], 0)
            self.assertEqual(second[0], 0)
            a, b = (Path(json.loads(result[1])['output_dir']) for result in (first, second))
            self.assertNotEqual(a, b)
            self.assertEqual((a / 'rex_perfil.log').read_text(), PREFIX + report())
            self.assertEqual(json.loads((a / 'report.json').read_text())['summary']['interval_count'], 1)
            self.assertEqual(first[3], [('synthetic-secret', '/logs/rex_perfil.log')])
            self.assertNotIn('synthetic-secret', first[1] + first[2] + (a / 'collection.json').read_text())

    def test_synthetic_invalid_profile_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            code, output, error, _ = self.invoke(tmp, 'incomplete synthetic log')
            self.assertNotEqual(code, 0)
            folder, = Path(tmp).iterdir()
            self.assertEqual((folder / 'rex_perfil.log').read_text(), 'incomplete synthetic log')
            self.assertTrue((folder / 'collection.json').exists())
            self.assertFalse((folder / 'report.json').exists())
            self.assertIn(str(folder), error)

if __name__ == '__main__':
    unittest.main()
