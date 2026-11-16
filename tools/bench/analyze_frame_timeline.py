#!/usr/bin/env python3
"""Join a capture's frame_timeline.txt with its guest-publish CSV.

Each line of the timeline file has the form:
  frame-timeline: N:guest_ns,w_us,h_us,r_us,s_us,p_us [...]
(8 frame entries per line; offsets in microseconds from guest Present; -1 = missing).

Each row of the guest-publish CSV has guest_frame and tick columns.
The tick is in armGetSystemTick units and only identifies the matching row.

Output: tab-separated table of joined rows with absolute ns and stage intervals.

Usage:
  analyze_frame_timeline.py timeline.txt capture.csv [--output out.tsv] [--summary out.json]
"""
import argparse
import csv
import json
import math
import re
import statistics
import sys
from pathlib import Path

import summarize_capture

STAGES = ('worker_present_us', 'worker_handoff_us', 'recorder_start_us',
          'queue_submit_us', 'publish_end_us')
RECORDER_STAMPS = ('slot_wait_begin_us', 'slot_wait_end_us', 'record_begin_us',
                   'record_end_us', 'queue_lock_begin_us', 'queue_lock_end_us',
                   'driver_submit_begin_us')
SLOT_FENCE = 'slot_fence_wait_us'
SUBMISSION_FIELDS = ('slot', 'wait_submission', 'secondary_wait_submission',
                     'completed_before_wait', 'completed_after_wait', 'native_submission')
SUBMISSION_INTERVALS = ('wait_submission_age', 'secondary_wait_submission_age')
RECORDER_INTERVALS = {
    'before_slot_wait': ('recorder_start_us', 'slot_wait_begin_us'),
    'slot_completion': ('slot_wait_begin_us', 'slot_wait_end_us'),
    'prepare_before_record': ('slot_wait_end_us', 'record_begin_us'),
    'record_native_frame': ('record_begin_us', 'record_end_us'),
    'finalize_before_queue_lock': ('record_end_us', 'queue_lock_begin_us'),
    'queue_lock': ('queue_lock_begin_us', 'queue_lock_end_us'),
    'driver_submit': ('driver_submit_begin_us', 'queue_submit_us'),
}
INTERVALS = ('guest_to_worker', 'worker_wait_for_recorder', 'handoff_to_recorder_start',
             'recorder_start_to_submit', 'submit_to_publish_end')
FRAME_INTERVALS = ('guest_present_interval', 'publish_end_interval',
                   'previous_publish_end_to_guest_present')


def parse_timeline(path: str) -> dict:
    """Return {frame: {'guest_ns': int, stage_us: int, ...}}.

    Each entry in a line is "FRAME:GUEST_NS,WP,WH,RS,QS,PE" where the five
    comma-separated values are signed microsecond offsets from guest_ns (-1 missing).
    """
    records = {}
    count = None
    dropped = 0
    stamp_count = None
    for lineno, raw in enumerate(Path(path).read_text().splitlines(), 1):
        raw = raw.strip()
        if raw.startswith('# samples='):
            header = re.fullmatch(r'# samples=(\d+) dropped=(\d+)', raw)
            if not header or count is not None:
                raise ValueError(f'line {lineno}: invalid sample count header')
            count, dropped = map(int, header.groups())
            continue
        if not raw.startswith('frame-timeline:'):
            continue
        for token in raw[len('frame-timeline:'):].split():
            frame_text, _, timing_text = token.partition(':')
            try:
                frame = int(frame_text)
                guest_ns, *offsets = map(int, timing_text.split(','))
            except ValueError:
                raise ValueError(f'line {lineno}: invalid timeline entry {token!r}') from None
            if (frame <= 0 or frame in records or guest_ns <= 0 or
                    len(offsets) not in (len(STAGES), len(STAGES + RECORDER_STAMPS),
                                         len(STAGES + RECORDER_STAMPS) + 1,
                                         len(STAGES + RECORDER_STAMPS + SUBMISSION_FIELDS) + 1) or
                    min(offsets) < -1 or stamp_count not in (None, len(offsets))):
                raise ValueError(f'line {lineno}: duplicate or invalid timeline frame {frame}')
            if len(offsets) == len(STAGES + RECORDER_STAMPS + SUBMISSION_FIELDS) + 1:
                slot, awaited, secondary, before, after, submitted = offsets[-len(SUBMISSION_FIELDS):]
                if slot not in (-1, 0, 1) or min(awaited, secondary, before, after, submitted) < 0 or after < before:
                    raise ValueError(f'line {lineno}: invalid submission metadata for frame {frame}')
            stamp_count = len(offsets)
            records[frame] = {'guest_ns': guest_ns,
                              **dict(zip((*STAGES, *RECORDER_STAMPS, SLOT_FENCE, *SUBMISSION_FIELDS), offsets))}
    if count is not None and count != len(records):
        raise ValueError('timeline sample count mismatch')
    return records, dropped


def parse_csv(path: str) -> dict:
    """Return {frame: tick_int} from the guest-publish CSV."""
    frames: dict = {}
    with open(path, newline='') as f:
        reader = csv.DictReader(row for row in f if not row.startswith('#'))
        for row in reader:
            frame = int(row['guest_frame'])
            if frame in frames:
                raise ValueError(f'duplicate captured frame {frame}')
            frames[frame] = int(row['tick'])
    return frames


def intervals(timeline, publish):
    rows = []
    submitted = {r['native_submission']: r for r in timeline.values() if r.get('native_submission', 0)}
    previous_frame = None
    previous = None
    for frame, tick in publish.items():
        current = timeline.get(frame)
        if current is None:
            continue
        offsets = [0, *(current[stage] for stage in STAGES)]
        deltas = [end - start if 0 <= start <= end else None
                  for start, end in zip(offsets, offsets[1:])]
        frame_deltas = [None] * len(FRAME_INTERVALS)
        if previous_frame == frame - 1:
            guest_interval = (current['guest_ns'] - previous['guest_ns']) / 1000
            if guest_interval >= 0:
                frame_deltas[0] = guest_interval
                if previous['publish_end_us'] >= 0:
                    # A negative gap means the next guest frame was already in flight.
                    gap = guest_interval - previous['publish_end_us']
                    frame_deltas[2] = gap
                    if current['publish_end_us'] >= 0 and gap + current['publish_end_us'] >= 0:
                        frame_deltas[1] = gap + current['publish_end_us']
        rows.append({'frame': frame, 'tick': tick, **current,
                     **dict(zip(INTERVALS, deltas)),
                     **dict(zip(FRAME_INTERVALS, frame_deltas))})
        for name, (begin, end) in RECORDER_INTERVALS.items():
            start, finish = current.get(begin, -1), current.get(end, -1)
            rows[-1][name] = finish - start if 0 <= start <= finish else None
        slot = rows[-1]['slot_completion']
        wait = current.get(SLOT_FENCE, -1)
        rows[-1]['slot_other'] = slot - wait if slot is not None and 0 <= wait <= slot else None
        for age, key in zip(SUBMISSION_INTERVALS, SUBMISSION_FIELDS[1:3]):
            older = submitted.get(current.get(key))
            wait_begin = current.get('slot_wait_begin_us', -1)
            delta = None
            if older and older['queue_submit_us'] >= 0 and wait_begin >= 0:
                delta = (current['guest_ns'] - older['guest_ns']) / 1000 + wait_begin - older['queue_submit_us']
            rows[-1][age] = delta if delta is not None and delta >= 0 else None
        previous_frame, previous = frame, current
    return rows


def describe(rows):
    result = {}
    for name in (*INTERVALS, *FRAME_INTERVALS, *RECORDER_INTERVALS, SLOT_FENCE, 'slot_other',
                 *SUBMISSION_INTERVALS):
        values = sorted(row[name] / 1000 for row in rows
                        if row.get(name) is not None and (name != SLOT_FENCE or row['slot_other'] is not None))
        if values:
            result[name] = {'samples': len(values), 'mean_ms': statistics.fmean(values),
                            'p95_ms': values[math.ceil(len(values) * .95) - 1]}
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('timeline', help='frame_timeline.txt for this capture')
    parser.add_argument('capture_csv', help='guest-publish capture CSV')
    parser.add_argument('--output', '-o', help='TSV output path (default: stdout)')
    parser.add_argument('--summary', help='write JSON stage statistics')
    args = parser.parse_args()

    try:
        capture = summarize_capture.summarize(args.capture_csv)
        timeline, dropped = parse_timeline(args.timeline)
        publish = parse_csv(args.capture_csv)
        rows = intervals(timeline, publish)
        if not rows:
            raise ValueError(f'no frames matched ({len(timeline)} timeline, {len(publish)} CSV)')
        summary = {'run_id': capture['run_id'], 'build_id_reported': capture['build_id_reported'],
                   'timeline_frames': len(timeline), 'capture_frames': len(publish),
                   'joined_frames': len(rows), 'dropped_timeline_frames': dropped,
                   'stages': describe(rows)}
        header = ['frame', 'tick', 'guest_ns', *STAGES, *INTERVALS, *FRAME_INTERVALS,
                  *RECORDER_STAMPS, *RECORDER_INTERVALS, SLOT_FENCE, 'slot_other',
                  *SUBMISSION_FIELDS, *SUBMISSION_INTERVALS]
        out = open(args.output, 'w', newline='') if args.output else sys.stdout
        try:
            writer = csv.DictWriter(out, fieldnames=header, delimiter='\t', lineterminator='\n')
            writer.writeheader()
            writer.writerows(rows)
        finally:
            if args.output:
                out.close()
        if args.summary:
            Path(args.summary).write_text(json.dumps(summary, indent=2) + '\n')
    except (OSError, ValueError, KeyError) as exc:
        print(f'Timeline analysis failed: {exc}', file=sys.stderr)
        return 1
    print(f'Joined {len(rows)} of {len(publish)} capture frames; '
          f'{len(timeline)} timeline frames, {dropped} dropped.', file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
