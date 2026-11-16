from pathlib import Path
import tempfile
import unittest

from analyze_frame_timeline import describe, intervals, parse_timeline


class TimelineTests(unittest.TestCase):
    def parse(self, text):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'timeline.txt'
            path.write_text(text)
            return parse_timeline(path)

    def test_stage_intervals_and_overlap(self):
        timeline, dropped = self.parse(
            '# samples=3 dropped=1\n'
            'frame-timeline: 40:1000000,100,200,300,1000,2000\n'
            'frame-timeline: 41:2500000,120,240,350,-1,1900\n'
            'frame-timeline: 43:6900000,50,80,100,1000,1500\n'
        )
        self.assertEqual(dropped, 1)
        rows = intervals(timeline, {40: 200, 41: 300, 43: 400})
        self.assertEqual(rows[0]['recorder_start_to_submit'], 700)
        self.assertIsNone(rows[1]['recorder_start_to_submit'])
        self.assertEqual(rows[1]['previous_publish_end_to_guest_present'], -500)
        self.assertEqual(rows[1]['publish_end_interval'], 1400)
        self.assertIsNone(rows[2]['guest_present_interval'])
        self.assertEqual(describe(rows)['publish_end_interval']['mean_ms'], 1.4)

    def test_rejects_incomplete_and_duplicate_exports(self):
        entry = 'frame-timeline: 40:1000000,100,200,300,1000,2000\n'
        with self.assertRaisesRegex(ValueError, 'count mismatch'):
            self.parse('# samples=2 dropped=0\n' + entry)
        with self.assertRaisesRegex(ValueError, 'duplicate'):
            self.parse(entry + entry)

    def test_recorder_breakdown_keeps_missing_intervals_blank(self):
        timeline, _ = self.parse(
            'frame-timeline: 40:1000000,100,200,300,2000,2100,'
            '400,900,1000,1700,-1,1800,1900\n'
        )
        row = intervals(timeline, {40: 200})[0]
        self.assertEqual(row['slot_completion'], 500)
        self.assertEqual(row['record_native_frame'], 700)
        self.assertEqual(row['driver_submit'], 100)
        self.assertIsNone(row['queue_lock'])

    def test_slot_fence_wait_is_subtracted_only_when_consistent(self):
        timeline, _ = self.parse(
            'frame-timeline: 40:1000000,100,200,300,2000,2100,400,900,1000,1700,1750,1800,1900,460\n'
            'frame-timeline: 41:2000000,100,200,300,2000,2100,400,900,1000,1700,1750,1800,1900,510\n'
        )
        rows = intervals(timeline, {40: 200, 41: 400})
        self.assertEqual(rows[0]['slot_other'], 40)
        self.assertIsNone(rows[1]['slot_other'])
        self.assertEqual(describe(rows)['slot_fence_wait_us']['samples'], 1)

    def test_wait_joins_exact_submission_even_without_a_publication_row(self):
        timeline, _ = self.parse(
            'frame-timeline: 40:1000000,100,200,300,2000,2100,400,900,1000,1700,1750,1800,1900,460,0,0,0,0,0,90\n'
            'frame-timeline: 41:2000000,100,200,300,2000,2100,400,900,1000,1700,1750,1800,1900,460,1,0,0,0,0,91\n'
            'frame-timeline: 42:5000000,100,200,300,2000,2100,400,900,1000,1700,1750,1800,1900,460,0,90,91,89,91,92\n'
        )
        row = intervals(timeline, {42: 200})[0]
        self.assertEqual(row['wait_submission'], 90)
        self.assertEqual(row['completed_before_wait'], 89)
        self.assertEqual(row['completed_after_wait'], 91)
        self.assertEqual(row['wait_submission_age'], 2400)
        self.assertEqual(row['secondary_wait_submission_age'], 1400)
