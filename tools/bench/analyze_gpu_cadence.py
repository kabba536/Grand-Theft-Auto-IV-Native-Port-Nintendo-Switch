#!/usr/bin/env python3
"""Compare consecutive raw GPU timestamp intervals with CPU frame intervals.

This checks timestamp units over a capture; it does not measure presentation.
"""
import argparse
import csv
import json
import math
import statistics
from pathlib import Path


def delta(end, begin, bits):
    if not 1 <= bits <= 64:
        raise ValueError('invalid timestamp valid bits')
    value = (end - begin) & ((1 << bits) - 1)
    if value >= 1 << (bits - 1):
        raise ValueError('backward or ambiguous GPU timestamp interval')
    return value


def analyze(rows):
    pairs = []
    clock_period = None
    for previous, current in zip(rows, rows[1:]):
        if int(previous['flags']) or int(current['flags']):
            continue
        if (int(current['frame']) != int(previous['frame']) + 1 or
                int(current['native_submission']) != int(previous['native_submission']) + 1):
            continue
        period = float(current['timestamp_period_ns'])
        bits = int(current['timestamp_valid_bits'])
        if (period != float(previous['timestamp_period_ns']) or
                bits != int(previous['timestamp_valid_bits']) or
                not math.isfinite(period) or period <= 0):
            raise ValueError('inconsistent timestamp metadata')
        if clock_period is not None and clock_period != period:
            raise ValueError('capture mixes timestamp periods')
        clock_period = period
        cpu_ms = float(current['cpu_frame_interval_ms'])
        begin = int(current['gpu_begin_raw'])
        previous_begin = int(previous['gpu_begin_raw'])
        previous_end = int(previous['gpu_end_raw'])
        end = int(current['gpu_end_raw'])
        gpu_step_ms = delta(begin, previous_begin, bits) * period / 1e6
        gpu_frame_ms = delta(end, begin, bits) * period / 1e6
        gap_ms = delta(begin, previous_end, bits) * period / 1e6
        if not math.isfinite(cpu_ms) or cpu_ms <= 0 or gpu_step_ms <= 0:
            raise ValueError('invalid frame cadence')
        pairs.append((cpu_ms, gpu_step_ms, gpu_frame_ms, gap_ms))
    if len(pairs) < 2:
        raise ValueError('need at least two clean consecutive frame pairs')
    cpu_total = sum(p[0] for p in pairs)
    gpu_total = sum(p[1] for p in pairs)
    correction = cpu_total / gpu_total
    deko_multiplier = 625 / 384 / clock_period
    return {
        'consecutive_clean_pairs': len(pairs),
        'cpu_interval_mean_ms': statistics.mean(p[0] for p in pairs),
        'gpu_begin_interval_reported_mean_ms': statistics.mean(p[1] for p in pairs),
        'gpu_frame_reported_mean_ms': statistics.mean(p[2] for p in pairs),
        'gpu_inter_envelope_gap_reported_mean_ms': statistics.mean(p[3] for p in pairs),
        'gpu_elapsed_over_cpu_elapsed': gpu_total / cpu_total,
        'inferred_period_multiplier': correction,
        'deko3d_timestamp_period_ns': 625 / 384,
        'deko3d_period_multiplier': deko_multiplier,
        'gpu_frame_deko_period_mean_ms': statistics.mean(p[2] for p in pairs) * deko_multiplier,
        'gpu_inter_envelope_gap_deko_period_mean_ms': statistics.mean(p[3] for p in pairs) * deko_multiplier,
        'deko_scaled_gpu_elapsed_over_cpu_elapsed': gpu_total / cpu_total * deko_multiplier,
        'note': 'A short capture has endpoint scheduling noise; repeat before correcting the timer.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    with args.csv.open(newline='') as stream:
        result = analyze(list(csv.DictReader(stream)))
    content = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.write_text(content)
    print(content, end='')


if __name__ == '__main__':
    main()
