#!/usr/bin/env python3
"""Unit tests for tools/bench/visual_parity.py (pure-stdlib PPM + Pillow when present)."""

import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import visual_parity


def _make_ppm(width: int, height: int, pixel_fn) -> bytes:
    header = f'P6\n{width} {height}\n255\n'.encode('ascii')
    body = bytearray(width * height * 3)
    for y in range(height):
        for x in range(width):
            r, g, b = pixel_fn(x, y)
            off = (y * width + x) * 3
            body[off] = r
            body[off + 1] = g
            body[off + 2] = b
    return header + bytes(body)


class VisualParityTests(unittest.TestCase):
    def test_identical_frames_pass_with_zero_diff(self):
        img = _make_ppm(100, 70, lambda x, y: ((x * 2) % 256, 100, (y * 3) % 256))
        report = visual_parity.compare_images(img, img)
        self.assertTrue(report['passed'])
        self.assertEqual(report['status'], 'parity_ok')
        self.assertEqual(report['viewport']['mae_rgb'], 0.0)
        self.assertEqual(report['viewport']['pct_pixels_gt_8'], 0.0)
        self.assertEqual(report['full']['max_channel_diff'], 0)

    def test_blackout_candidate_fails_even_if_small_area(self):
        ref = _make_ppm(100, 70, lambda x, y: (120, 120, 120))
        black = _make_ppm(100, 70, lambda x, y: (4, 4, 4))
        report = visual_parity.compare_images(ref, black)
        self.assertFalse(report['passed'])
        self.assertEqual(report['status'], 'parity_drift_or_blackout')
        self.assertLess(report['viewport']['cand_mean_luma'], 20.0)

    def test_hud_status_monitor_diff_ignored_by_viewport_crop(self):
        # Status monitor is in left 0..40% width (x < 40 for width=100); viewport ignores it.
        ref = _make_ppm(100, 70, lambda x, y: (110, 110, 110))
        cand = _make_ppm(100, 70, lambda x, y: (255, 0, 0) if x < 35 else (110, 110, 110))
        report = visual_parity.compare_images(ref, cand)
        self.assertTrue(report['passed'])
        self.assertEqual(report['viewport']['mae_rgb'], 0.0)
        self.assertGreater(report['full']['pct_pixels_gt_24'], 30.0)

    def test_world_artifact_in_viewport_fails_gate(self):
        ref = _make_ppm(100, 70, lambda x, y: (120, 120, 120))
        cand = _make_ppm(100, 70, lambda x, y: (250, 20, 20) if 45 <= x <= 85 and 15 <= y <= 55 else (120, 120, 120))
        report = visual_parity.compare_images(ref, cand)
        self.assertFalse(report['passed'])
        self.assertGreater(report['viewport']['pct_pixels_gt_24'], 15.0)

    def test_resolution_mismatch_raises(self):
        ref = _make_ppm(100, 70, lambda x, y: (80, 80, 80))
        cand = _make_ppm(80, 70, lambda x, y: (80, 80, 80))
        with self.assertRaises(ValueError):
            visual_parity.compare_images(ref, cand)

    def test_diff_sheet_creation_when_pillow_present(self):
        if visual_parity.Image is None:
            return
        ref = _make_ppm(60, 42, lambda x, y: (100, 100, 100))
        cand = _make_ppm(60, 42, lambda x, y: (130, 100, 100))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / 'sheet.png'
            visual_parity.save_side_by_side_diff(ref, cand, out)
            self.assertTrue(out.exists())
            with visual_parity.Image.open(out) as sheet:
                self.assertEqual(sheet.size, (180, 42))


if __name__ == '__main__':
    unittest.main()
