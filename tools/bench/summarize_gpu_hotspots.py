#!/usr/bin/env python3
"""Compact, read-only hotspot summary of an existing native GPU capture."""
import argparse
from collections import Counter, defaultdict
import csv
import json
import math
from pathlib import Path
import statistics


def rows(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        for row in reader:
            if None in row or None in row.values():
                raise ValueError('malformed CSV: ' + path.name)
            yield row


def number(value):
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise ValueError('invalid nonnegative finite timing')
    return result


def stats(values):
    ordered = sorted(values)
    return {key: round(value, 6) for key, value in (
        ('mean', statistics.mean(values)),
        ('p95', ordered[math.ceil(.95 * len(ordered)) - 1]),
        ('max', ordered[-1]))}


def summarize_detail(path, eligible, kind, top):
    timing = 'gpu_ms' if kind == 'passes' else 'duration_ms'
    identity = 'region' if kind == 'passes' else 'slice'
    groups = defaultdict(lambda: defaultdict(list))
    excluded = Counter()
    seen = set()
    statuses = Counter()
    for row in rows(path):
        key = (int(row['frame']), int(row['sequence']))
        if key not in eligible:
            excluded['ineligible_or_unmatched_frame_rows'] += 1
            continue
        unique = (*key, int(row[identity]))
        if unique in seen:
            raise ValueError('duplicate detail identity: ' + path.name)
        seen.add(unique)
        statuses[row['status']] += 1
        try:
            value = number(row[timing]) if row['status'] == 'approximate' else None
        except (ValueError, TypeError):
            value = None
        # A partially unavailable repeated range cannot be treated as a full sum.
        groups[row['range']][key].append(value)
    ranked = []
    unavailable = []
    for name, frames in groups.items():
        complete = [values for values in frames.values() if None not in values]
        valid_rows = sum(value is not None for values in frames.values() for value in values)
        unavailable_rows = sum(value is None for values in frames.values() for value in values)
        coverage = {'range': name, 'observed_frames': len(frames),
                    'comparable_frames': len(complete),
                    'missing_frames': len(eligible) - len(frames),
                    'excluded_partial_or_unavailable_frames': len(frames) - len(complete),
                    'valid_rows': valid_rows, 'unavailable_or_invalid_rows': unavailable_rows}
        if unavailable_rows:
            unavailable.append(coverage.copy())
        if complete:
            totals = [sum(values) for values in complete]
            coverage.update(frame_total_ms=stats(totals),
                            mean_occurrences_per_comparable_frame=round(
                                statistics.mean(len(values) for values in complete), 3))
            ranked.append((sum(totals), coverage))
    ranked.sort(key=lambda item: (-item[0], item[1]['range']))
    unavailable.sort(key=lambda item: (-item['unavailable_or_invalid_rows'], item['range']))
    return {'eligible_row_statuses': dict(statuses), 'excluded_rows': dict(excluded),
            'range_count': len(groups), 'timed_ranges': len(ranked),
            'top_by_total_observed_ms': [item[1] for item in ranked[:top]],
            'top_unavailable_ranges': unavailable[:top]}


def summarize(folder, top=8):
    folder = Path(folder)
    if top < 1:
        raise ValueError('top must be positive')
    meta = json.loads((folder / 'native-performance-meta.json').read_text())
    flat = list(rows(folder / 'native-performance-latest.csv'))
    if meta.get('complete') is not True or len(flat) != meta.get('samples') or not flat:
        raise ValueError('incomplete or inconsistent native capture')
    if {row['capture_id'] for row in flat} != {str(meta['capture_id'])}:
        raise ValueError('capture identity mismatch')
    first = min(int(row['capture_index']) for row in flat)
    eligible = set()
    all_keys = set()
    indices = set()
    frame_times = []
    exclusions = Counter()
    for row in flat:
        key = (int(row['frame']), int(row['capture_sequence']))
        index = int(row['capture_index'])
        if key in all_keys or index in indices:
            raise ValueError('duplicate native sample identity')
        all_keys.add(key)
        indices.add(index)
        if index == first:
            exclusions['first_sample'] += 1
        elif int(row['flags']) != 0:
            exclusions['flagged'] += 1
        else:
            try:
                value = number(row['gpu_frame_ms'])
            except (ValueError, TypeError):
                exclusions['invalid_or_unavailable_gpu_frame'] += 1
                continue
            eligible.add(key)
            frame_times.append(value)
    if not eligible:
        raise ValueError('no comparable GPU samples')
    return {'capture_id': meta['capture_id'], 'total_samples': len(flat),
            'comparable_samples': len(eligible), 'excluded_samples': dict(exclusions),
            'gpu_frame_ms': stats(frame_times),
            'slices': summarize_detail(folder / 'native-performance-gpu-slices.csv', eligible, 'slices', top),
            'passes': summarize_detail(folder / 'native-performance-gpu-passes.csv', eligible, 'passes', top),
            'note': 'Approximate GPU queue timing, not display FPS or an optimization comparison. '
                    'Repeated ranges are summed per frame before statistics; only fully available '
                    'frame/range groups enter timings. Missing ranges are not assumed zero. '
                    'Slices partition the queue; passes are separate drill-down and must not be added. '
                    'Collapsed timestamps can yield zero intervals without proving zero execution cost.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--top', type=int, default=8)
    args = parser.parse_args()
    try:
        print(json.dumps(summarize(args.folder, args.top), separators=(',', ':')))
    except (ValueError, OSError, KeyError, TypeError) as exc:
        parser.exit(1, f'GPU hotspot summary failed: {exc}\n')


if __name__ == '__main__':
    main()
