import csv
import json
from pathlib import Path
import tempfile
import unittest

import summarize_gpu_hotspots as hotspots


class Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.flat = [dict(frame=10 + i, capture_sequence=i + 1, capture_index=i,
                          capture_id=99, flags=0, gpu_frame_ms=10) for i in range(4)]
        self.slices = [dict(frame=11, sequence=2, slice=0, range='resolve', status='approximate', duration_ms=2),
                       dict(frame=11, sequence=2, slice=1, range='resolve', status='approximate', duration_ms=3),
                       dict(frame=12, sequence=3, slice=0, range='resolve', status='approximate', duration_ms=7)]
        self.passes = [dict(frame=11, sequence=2, region=0, range='resolve', status='approximate', gpu_ms=4)]

    def write(self, name, values):
        with (self.folder / ('native-performance-' + name + '.csv')).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(values[0]))
            writer.writeheader()
            writer.writerows(values)

    def execute(self):
        (self.folder / 'native-performance-meta.json').write_text(json.dumps(
            {'capture_id': 99, 'samples': len(self.flat), 'complete': True}))
        self.write('latest', self.flat)
        self.write('gpu-slices', self.slices)
        self.write('gpu-passes', self.passes)
        return hotspots.summarize(self.folder)

    def test_repeated_ranges_are_summed_per_frame_not_averaged_as_rows(self):
        result = self.execute()
        item = result['slices']['top_by_total_observed_ms'][0]
        self.assertEqual(item['frame_total_ms'], {'mean': 6, 'p95': 7, 'max': 7})
        self.assertEqual(item['comparable_frames'], 2)
        self.assertEqual(item['missing_frames'], 1)
        self.assertEqual(item['mean_occurrences_per_comparable_frame'], 1.5)
        self.assertEqual(result['passes']['top_by_total_observed_ms'][0]['frame_total_ms']['mean'], 4)

    def test_partial_range_is_excluded_instead_of_becoming_a_low_total(self):
        self.slices[1]['status'] = 'unavailable'
        self.slices[1]['duration_ms'] = ''
        item = self.execute()['slices']['top_by_total_observed_ms'][0]
        self.assertEqual(item['frame_total_ms']['mean'], 7)
        self.assertEqual(item['comparable_frames'], 1)
        self.assertEqual(item['excluded_partial_or_unavailable_frames'], 1)
        self.assertEqual(item['unavailable_or_invalid_rows'], 1)

    def test_first_flagged_and_mismatched_sequence_rows_excluded(self):
        self.flat[2]['flags'] = 4
        self.slices += [dict(self.slices[0], frame=10, sequence=1, duration_ms=999),
                        dict(self.slices[0], frame=13, sequence=999, duration_ms=999)]
        result = self.execute()
        self.assertEqual(result['comparable_samples'], 2)
        self.assertEqual(result['slices']['excluded_rows']['ineligible_or_unmatched_frame_rows'], 3)
        self.assertEqual(result['slices']['top_by_total_observed_ms'][0]['frame_total_ms']['mean'], 5)

    def test_nonfinite_negative_and_unavailable_rows_do_not_enter_timings(self):
        for invalid in ('nan', 'inf', '-1', ''):
            with self.subTest(invalid=invalid):
                self.slices[1]['duration_ms'] = invalid
                result = self.execute()
                self.assertEqual(result['slices']['top_by_total_observed_ms'][0]['frame_total_ms']['mean'], 7)

    def test_unavailable_only_pass_range_has_no_timing(self):
        self.passes[0]['status'] = 'unavailable'
        result = self.execute()['passes']
        self.assertEqual(result['top_by_total_observed_ms'], [])
        self.assertEqual(result['top_unavailable_ranges'][0]['comparable_frames'], 0)

    def test_duplicate_detail_identity_fails_closed(self):
        self.slices.append(self.slices[0].copy())
        with self.assertRaisesRegex(ValueError, 'duplicate detail identity'):
            self.execute()

    def test_duplicate_flat_identity_fails_closed(self):
        self.flat[2]['capture_sequence'] = 2
        self.flat[2]['frame'] = 11
        with self.assertRaisesRegex(ValueError, 'duplicate native sample identity'):
            self.execute()

    def test_wrong_capture_identity_fails_closed(self):
        self.flat[2]['capture_id'] = 98
        with self.assertRaisesRegex(ValueError, 'capture identity mismatch'):
            self.execute()

    def test_zero_intervals_are_retained_with_caveat(self):
        for row in self.slices:
            row['duration_ms'] = 0
        result = self.execute()
        self.assertEqual(result['slices']['top_by_total_observed_ms'][0]['frame_total_ms']['mean'], 0)
        self.assertIn('Collapsed timestamps', result['note'])


if __name__ == '__main__':
    unittest.main()
