#!/usr/bin/env python3
"""Summarize guest-publish tick captures; never infer an optimization win."""
import argparse
import csv
import json
import math
from pathlib import Path
import re
import statistics
import sys

ID = re.compile(r'^[A-Za-z0-9_-]{1,48}$')


def summarize_camera(meta, samples):
    try:
        valid = int(meta['camera_samples'])
        advances = int(meta['camera_advances'])
        regressions = int(meta['camera_regressions'])
        if (not 0 <= valid <= samples or min(advances, regressions) < 0 or
                advances + regressions > max(0, valid - 1)):
            raise ValueError('inconsistent camera sample counts')
        camera = {'valid_samples': valid, 'advances': advances, 'regressions': regressions}
        if not valid:
            return camera
        for key in ('first_sequence', 'last_sequence'):
            camera[key] = int(meta['camera_' + key])
            if camera[key] <= 0:
                raise ValueError('invalid camera sequence')
        for key in ('position_drift_m', 'view_drift', 'projection_drift'):
            camera[key] = float(meta['camera_' + key])
            if not math.isfinite(camera[key]) or camera[key] < 0:
                raise ValueError('invalid camera drift')
        for key, width in (('position', 3), ('view_axes', 9), ('projection', 16)):
            values = [float(value) for value in meta['camera_' + key].split(',')]
            if len(values) != width or not all(math.isfinite(value) for value in values):
                raise ValueError('invalid camera transform')
            camera[key] = values
        return camera
    except KeyError as exc:
        raise ValueError('incomplete camera metadata') from exc


def summarize(path):
    meta = {}
    rows = []
    with Path(path).open(encoding='utf-8', newline='') as stream:
        lines = iter(stream)
        for line in lines:
            if not line.startswith('# '):
                header = next(csv.reader([line]))
                break
            key, sep, value = line[2:].strip().partition('=')
            if not sep or key in meta: raise ValueError('invalid or duplicate metadata')
            meta[key] = value
        else:
            raise ValueError('missing CSV header')
        if header != ['index', 'guest_frame', 'tick']: raise ValueError('unknown CSV columns')
        for row in csv.reader(lines):
            if len(row) != 3: raise ValueError('malformed sample')
            try: index, frame, tick = map(int, row)
            except ValueError: raise ValueError('noninteger sample') from None
            if index != len(rows) or frame < 0 or tick < 0: raise ValueError('invalid sample order or value')
            if rows and tick < rows[-1][1]: raise ValueError('nonmonotonic ticks')
            rows.append((frame, tick))
    required = {'schema','event','physical_display','run_id','build_id','ticks_per_second','capacity','rejected','samples'}
    if not required.issubset(meta): raise ValueError('missing metadata')
    if (meta['schema'],meta['event'],meta['physical_display']) != ('guest_publish_ticks_v1','guest_publish_entry','false'):
        raise ValueError('unknown event semantics')
    if not ID.fullmatch(meta['run_id']) or not ID.fullmatch(meta['build_id']): raise ValueError('invalid identifiers')
    if 'player_state_gate' in meta and meta['player_state_gate'] != 'passed': raise ValueError('player state gate failed')
    try: freq, capacity, rejected, samples = (int(meta[x]) for x in ('ticks_per_second','capacity','rejected','samples'))
    except ValueError: raise ValueError('invalid numeric metadata') from None
    if freq <= 0 or capacity <= 0 or rejected < 0 or samples != len(rows) or samples > capacity:
        raise ValueError('inconsistent sample metadata')
    if samples < 2: raise ValueError('fewer than two samples')
    if rejected: raise ValueError('capture has dropped or invalid samples')
    delta = [(b[1]-a[1])*1000.0/freq for a,b in zip(rows,rows[1:])]
    duration = sum(delta)
    if duration <= 0: raise ValueError('zero capture duration')
    ordered = sorted(delta)
    def percentile(p): return ordered[max(0,math.ceil(p*len(ordered))-1)]
    result = {'status':'valid_capture', 'run_id':meta['run_id'], 'build_id_reported':meta['build_id'],
            'event':meta['event'], 'physical_display':False, 'player_state_gate':meta.get('player_state_gate','not_available'), 'samples':samples, 'duration_s':duration/1000,
            'mean_ms':statistics.fmean(delta), 'median_ms':statistics.median(delta), 'p95_ms':percentile(.95),
            'p99_ms':percentile(.99), 'max_ms':max(delta), 'events_per_second':len(delta)*1000/duration,
            'intervals_over_50ms':sum(x>50 for x in delta), 'intervals_over_100ms':sum(x>100 for x in delta),
            'note':'Guest publish-entry intervals, not display presentation or a repeatability/visual-quality verdict.'}
    if 'camera_samples' in meta:
        result['camera'] = summarize_camera(meta, samples)
    for key, label in (('batch_target_barriers', 'target barrier'), ('resolve_swap', 'resolve swap'),
                       ('gpu_resolve_fast', 'gpu resolve fast')):
        if key in meta:
            if meta[key] not in ('on', 'off'):
                raise ValueError(f'invalid {label} mode')
            result[key] = meta[key]
    for stats_key in ('resolve_stats', 'gpu_resolve_stats'):
        if stats_key in meta:
            result[stats_key] = meta[stats_key]
    if 'gpu_resolve_mode_persists' in meta:
        if meta['gpu_resolve_mode_persists'] != 'true' or 'gpu_resolve_fast' not in result:
            raise ValueError('invalid GPU resolve mode persistence')
        result['gpu_resolve_mode_persists'] = True
    return result


def compare(reference, candidate):
    camera = []
    for capture in (reference, candidate):
        view = capture.get('camera')
        if view and view['valid_samples']:
            camera.append(view)
    result = {
        'reference': reference['run_id'],
        'candidate': candidate['run_id'],
        'frame_time_delta_ms': {key: candidate[key] - reference[key]
                                for key in ('mean_ms', 'median_ms', 'p95_ms', 'p99_ms')},
        'camera': None,
    }
    if len(camera) == 2:
        first, second = camera
        position_delta = math.dist(first['position'], second['position'])
        view_delta = max(abs(a - b) for a, b in zip(first['view_axes'], second['view_axes']))
        projection_delta = max(abs(a - b) for a, b in zip(first['projection'], second['projection']))
        result['camera'] = {
            'valid_samples': [view['valid_samples'] for view in camera],
            'total_samples': [capture['samples'] for capture in (reference, candidate)],
            'advances': [view['advances'] for view in camera],
            'regressions': [view['regressions'] for view in camera],
            # Triangle inequality over the observed snapshots in both windows.
            'position_difference_bound_m': position_delta + sum(view['position_drift_m'] for view in camera),
            'view_difference_bound': view_delta + sum(view['view_drift'] for view in camera),
            'projection_difference_bound': projection_delta + sum(view['projection_drift'] for view in camera),
        }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    parser.add_argument('--reference', type=Path, help='Compare this capture against an existing reference CSV')
    args = parser.parse_args()
    try:
        result = summarize(args.capture)
        if args.reference:
            result = compare(summarize(args.reference), result)
    except (OSError,UnicodeError,ValueError) as e:
        print(json.dumps({'status':'invalid_capture','error':str(e)}),file=sys.stderr);return 1
    print(json.dumps(result,ensure_ascii=False));return 0

if __name__=='__main__':sys.exit(main())
