import unittest

import analyze_gpu_cadence as cadence


def rows():
    # GPU clock advances 614400 ticks per CPU millisecond. Begin near wrap.
    origin = (1 << 32) - 1000000
    result = []
    for frame in range(5):
        begin = (origin + frame * 30000000) % (1 << 32)
        result.append(dict(frame=frame, native_submission=frame + 10, flags=0,
                           gpu_begin_raw=begin,
                           gpu_end_raw=(begin + 26000000) % (1 << 32),
                           timestamp_valid_bits=32, timestamp_period_ns=1,
                           cpu_frame_interval_ms=30000000 / 614400))
    return result


class CadenceTests(unittest.TestCase):
    def test_clock_scale_and_wrap(self):
        result = cadence.analyze(rows())
        self.assertEqual(result['consecutive_clean_pairs'], 4)
        self.assertAlmostEqual(result['inferred_period_multiplier'], 625 / 384)
        self.assertAlmostEqual(result['gpu_inter_envelope_gap_reported_mean_ms'], 4)

    def test_skip_flagged_frames_and_discontinuities(self):
        data = rows()
        data[0]['flags'] = 1
        result = cadence.analyze(data)
        self.assertEqual(result['consecutive_clean_pairs'], 3)
        data[2]['native_submission'] += 100
        with self.assertRaisesRegex(ValueError, 'at least two'):
            cadence.analyze(data)

    def test_correct_metadata_is_not_scaled_twice(self):
        data = rows()
        for row in data:
            row['timestamp_period_ns'] = 625 / 384
        result = cadence.analyze(data)
        self.assertAlmostEqual(result['gpu_elapsed_over_cpu_elapsed'], 1)
        self.assertAlmostEqual(result['deko3d_period_multiplier'], 1)

    def test_reject_backward_and_invalid_clock(self):
        with self.assertRaises(ValueError):
            cadence.delta(9, 10, 32)
        data = rows()
        data[1]['timestamp_period_ns'] = 0
        with self.assertRaisesRegex(ValueError, 'metadata'):
            cadence.analyze(data)


if __name__ == '__main__':
    unittest.main()
