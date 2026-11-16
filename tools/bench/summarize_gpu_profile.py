#!/usr/bin/env python3
"""Summarize an existing native GPU capture; excludes flagged rows by default."""
import argparse
import csv
import json
import math
from pathlib import Path
import statistics


def summarize(folder):
    meta = json.loads((folder / 'native-performance-meta.json').read_text())
    with (folder / 'native-performance-latest.csv').open(newline='') as f:
        rows = list(csv.DictReader(f))
    if not meta.get('complete') or len(rows) != meta.get('samples'):
        raise ValueError('incomplete or inconsistent native capture')
    if {r.get('capture_id') for r in rows} != {str(meta.get('capture_id'))}:
        raise ValueError('capture identity mismatch')
    clean = [r for r in rows if int(r['flags']) == 0 and r['gpu_frame_ms']]
    values = [float(r['gpu_frame_ms']) for r in clean]
    if not values or any(not math.isfinite(x) or x < 0 for x in values):
        raise ValueError('no valid GPU time samples')
    ordered = sorted(values)
    return {'capture_id': meta['capture_id'], 'total_samples': len(rows),
            'included_samples': len(values), 'excluded_samples': len(rows)-len(values),
            'gpu_frame_mean_ms': statistics.mean(values), 'gpu_frame_median_ms': statistics.median(values),
            'gpu_frame_p95_ms': ordered[math.ceil(.95 * len(ordered))-1],
            'gpu_timing': meta.get('gpu_timing'), 'physical_scanout_measured': meta.get('physical_scanout_measured'),
            'note': 'Instrumented GPU queue intervals, not display FPS; not an optimization comparison.'}


def main():
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('folder', type=Path); a = p.parse_args()
    try: print(json.dumps(summarize(a.folder), indent=2))
    except (ValueError, OSError, KeyError, TypeError) as e:
        p.exit(1, f'GPU summary failed: {e}\n')

if __name__ == '__main__': main()
