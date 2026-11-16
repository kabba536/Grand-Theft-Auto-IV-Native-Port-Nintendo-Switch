import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import repeat_capture

SCRIPT = b'start 0 0 0 1\nstep 1 0 0 0 0 0 0 0 1\n'


class Tests(unittest.TestCase):
    def test_different_scenarios_preserved_and_passed_in_order(self):
        with tempfile.TemporaryDirectory() as folder:
            first = Path(folder) / 'first.input'
            second = Path(folder) / 'second.input'
            first.write_bytes(SCRIPT)
            second.write_bytes(SCRIPT.replace(b'step 1 ', b'step 2 '))
            calls = []

            def capture(ftp, run_id, build, duration, parent, timeout, input_script=None):
                calls.append((run_id, input_script))
                (parent / 'capture.csv').write_bytes(b'raw evidence')
                return parent, {'mean_ms': 15}

            with patch.object(repeat_capture.capture_run, 'run', side_effect=capture):
                root, result = repeat_capture.series(None, 2, 10, 'build', folder, 90,
                                                     [first, '-', second])
            self.assertEqual([data for _, data in calls],
                             [SCRIPT, SCRIPT, None, None, second.read_bytes(), second.read_bytes()])
            self.assertEqual(len({token for token, _ in calls}), 6)
            self.assertEqual((root / 'scenario-0.input').read_bytes(), SCRIPT)
            self.assertEqual(result['status'], 'captures_complete')
            self.assertIn('do not establish', result['note'])
            self.assertTrue(all(Path(run['path'], 'capture.csv').exists() for run in result['runs']))
            self.assertEqual(json.loads((root / 'series.json').read_text()), result)

    def test_failure_retains_partial_evidence_and_does_not_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            def capture(ftp, token, build, duration, parent, timeout, input_script=None):
                (parent / 'partial.csv').write_text('raw')
                raise TimeoutError('timed out')
            with patch.object(repeat_capture.capture_run, 'run', side_effect=capture) as runner:
                with self.assertRaisesRegex(RuntimeError, 'series incomplete'):
                    repeat_capture.series(None, 3, 10, 'build', folder, 90)
            self.assertEqual(runner.call_count, 1)
            root = next(Path(folder).iterdir())
            result = json.loads((root / 'series.json').read_text())
            self.assertEqual(result['status'], 'incomplete')
            self.assertEqual(result['runs'][0]['status'], 'failed')
            self.assertEqual(Path(result['runs'][0]['path'], 'partial.csv').read_text(), 'raw')

    def test_all_scripts_validated_before_first_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            invalid = Path(folder) / 'bad.input'
            invalid.write_bytes(b'x' * 4097)
            with patch.object(repeat_capture.capture_run, 'run') as runner:
                with self.assertRaises(ValueError):
                    repeat_capture.series(None, 1, 10, 'build', folder, 90, ['-', invalid])
                runner.assert_not_called()
            self.assertEqual(list(Path(folder).iterdir()), [invalid])

    def test_bounds_reject_without_capture(self):
        with tempfile.TemporaryDirectory() as folder:
            with patch.object(repeat_capture.capture_run, 'run') as runner:
                for count, timeout, scripts in [(0, 90, None), (31, 90, None),
                                                (2, 90, ['-'] * 16), (1, float('nan'), None),
                                                (1, 9, None), (1, 3601, None)]:
                    with self.subTest(count=count, timeout=timeout):
                        with self.assertRaises(ValueError):
                            repeat_capture.series(None, count, 10, 'build', folder, timeout, scripts)
                runner.assert_not_called()
