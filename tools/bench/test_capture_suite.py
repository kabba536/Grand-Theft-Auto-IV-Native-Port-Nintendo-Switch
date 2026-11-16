import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import capture_suite

class Tests(unittest.TestCase):
 def test_three_runs_no_optimization_claim(self):
  with tempfile.TemporaryDirectory() as d:
   def capture(ftp,run_id,build,duration,root,timeout):
    return Path(root)/run_id,{'mean_ms':20.0}
   with patch.object(capture_suite.capture_run,'run',side_effect=capture):
    root,r=capture_suite.suite(None,3,10,'build',d,90)
   self.assertEqual(r['count'],3);self.assertEqual(r['median_of_run_mean_ms'],20);self.assertIn('not verified',r['note']);self.assertTrue((root/'suite.json').exists())
 def test_error_preserves_previous_results(self):
  with tempfile.TemporaryDirectory() as d:
   with patch.object(capture_suite.capture_run,'run',side_effect=[(Path(d)/'first',{'mean_ms':20}),TimeoutError('timeout')]):
    with self.assertRaisesRegex(RuntimeError,'incomplete'):capture_suite.suite(None,3,10,'build',d,90)
   roots=list(Path(d).iterdir());report=json.loads((roots[0]/'suite.json').read_text());self.assertEqual(report['status'],'incomplete');self.assertEqual(len(report['runs']),1)
