import tempfile
import unittest
from pathlib import Path
from summarize_capture import summarize

PREFIX = '''# schema=guest_publish_ticks_v1
# event=guest_publish_entry
# physical_display=false
# run_id=fixture
# build_id=synthetic
# ticks_per_second=1000
# capacity=10
# rejected=0
# samples=4
index,guest_frame,tick
'''

class Tests(unittest.TestCase):
 def check(self, text):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'capture.csv';p.write_text(text);return summarize(p)
 def test_synthetic_series(self):
  r=self.check(PREFIX+'0,1,0\n1,2,20\n2,3,60\n3,4,160\n')
  self.assertEqual(r['median_ms'],40);self.assertEqual(r['p95_ms'],100);self.assertEqual(r['intervals_over_50ms'],1);self.assertFalse(r['physical_display'])
 def test_rejects_corrupt_or_incomplete(self):
  data=PREFIX+'0,1,0\n1,2,20\n2,3,60\n3,4,160\n'
  for bad in [data.replace('rejected=0','rejected=1'),data.replace('samples=4','samples=5'),data.replace('3,4,160','3,4,10'),data.replace('physical_display=false','physical_display=true'),data.replace('# samples=4', '# player_state_gate=failed\n# samples=4'),data.replace('# samples=4', '# resolve_swap=maybe\n# samples=4')]:
   with self.subTest(bad=bad),self.assertRaises(ValueError):self.check(bad)
 def test_resolve_swap_and_stats_metadata(self):
  data=PREFIX.replace('# samples=4','# resolve_swap=on\n# resolve_stats=fast:12,planned:12,lazy:0,present:1,r4:3\n# gpu_resolve_fast=on\n# gpu_resolve_stats=fast_shader:20,mat_no_wfi:5,alias_no_wfi:1,props_cached:2\n# samples=4')+'0,1,0\n1,2,20\n2,3,60\n3,4,160\n'
  r=self.check(data)
  self.assertEqual(r['resolve_swap'],'on')
  self.assertEqual(r['resolve_stats'],'fast:12,planned:12,lazy:0,present:1,r4:3')
  self.assertEqual(r['gpu_resolve_fast'],'on')
  self.assertEqual(r['gpu_resolve_stats'],'fast_shader:20,mat_no_wfi:5,alias_no_wfi:1,props_cached:2')
