#!/usr/bin/env python3
"""Explicit one-shot native GPU profile; requires the startup-enabled GPU bench build."""
import argparse
import csv
import ftplib
import hashlib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid

import capture_run
import summarize_capture

REPORTS = ('native-performance-latest.log', 'native-performance-latest.csv')
DETAILS = tuple("native-performance-" + name for name in (
    "cpu.csv", "cpu-shaders.csv", "gpu-passes.csv", "gpu-slices.csv",
    "frames.csv", "trace.json", "meta.json"))
CPU_DETAILS = tuple("native-performance-" + name for name in (
    "cpu.csv", "frames.csv", "meta.json"))
LIMIT = 64 * 1024 * 1024


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_compact_regions(data, samples):
    if not data.endswith(b'\n'):
        raise ValueError('truncated compact GPU regions')
    reader = csv.DictReader(io.StringIO(data.decode('utf-8')))
    required = {'capture_id', 'frame', 'sequence', 'range', 'vertex_shader',
                'pixel_shader', 'raw_ticks', 'reported_gpu_ms'}
    if not required.issubset(reader.fieldnames or ()):
        raise ValueError('compact GPU regions schema missing')
    identities = {(row['capture_id'], int(row['frame']), int(row['capture_sequence']))
                  for row in samples}
    count = 0
    for row in reader:
        if None in row or None in row.values():
            raise ValueError('malformed compact GPU regions')
        if (row['capture_id'], int(row['frame']), int(row['sequence'])) not in identities:
            raise ValueError('compact GPU region capture identity mismatch')
        elapsed = float(row['reported_gpu_ms'])
        if int(row['raw_ticks']) <= 0 or not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError('invalid compact GPU region timing')
        count += 1
    return count


def run(ftp, diagnostics_dir, build, duration, parent, timeout=180, run_id=None,
        sleep=time.sleep, clock=time.monotonic, expected_samples=300, resume=None,
        compact=False, gpu_resolve_fast=False, resolve_swap=False, cpu_reports_only=False):
    if compact and cpu_reports_only:
        raise ValueError('CPU report selection requires a detailed capture')
    resumed = None
    if resume is not None:
        folder = Path(resume)
        resumed = json.loads((folder / 'result.json').read_text())
        if (resumed.get('request_published') is not True
                or resumed.get('build_label') != build
                or resumed.get('diagnostics_dir') != diagnostics_dir
                or resumed.get('compact', False) != compact
                or resumed.get('gpu_resolve_fast', False) != gpu_resolve_fast
                or resumed.get('resolve_swap', False) != resolve_swap
                or resumed.get('cpu_reports_only', False) != cpu_reports_only
                or (run_id is not None and run_id != resumed.get('run_id'))):
            raise ValueError('resume requires a published request with matching run/build/path')
        run_id = resumed.get('run_id')
        if not isinstance(run_id, str):
            raise ValueError('resume has no valid run ID')
    run_id = run_id or 'g' + uuid.uuid4().hex
    if not capture_run.TOKEN.fullmatch(run_id) or not capture_run.TOKEN.fullmatch(build):
        raise ValueError('invalid run/build token')
    if (not diagnostics_dir.startswith('/') or any(c in diagnostics_dir for c in '\r\n')
            or not 1 <= duration <= 300 or timeout < duration + 3 or expected_samples < 1):
        raise ValueError('invalid diagnostics path, duration, timeout or sample count')
    if resumed is None:
        folder = Path(tempfile.mkdtemp(prefix='gpu-profile-', dir=parent))
    os.chmod(folder, 0o700)
    deadline = clock() + timeout
    prefix = 'bench_' + run_id
    reports = (prefix + '.gpu.csv',) if compact else REPORTS
    selected_details = CPU_DETAILS if cpu_reports_only else DETAILS
    expected_files = reports if compact else REPORTS + selected_details
    opt_in = '.gpu-flat' if compact else '.gpu'
    export_dir = capture_run.REMOTE if compact else diagnostics_dir
    report = {'status': 'unconfirmed', 'run_id': run_id, 'build_label': build,
              'path': str(folder), 'diagnostics_dir': diagnostics_dir,
              'compact': compact, 'gpu_resolve_fast': gpu_resolve_fast,
              'resolve_swap': resolve_swap,
              'cpu_reports_only': cpu_reports_only,
              'attribution': 'per-run export filename' if compact else
                  'single-runner assumption; export does not embed benchmark run ID',
              'previous': {}, 'fresh': {}}
    baseline = {}
    if resumed is not None:
        previous = resumed.get('previous')
        if not isinstance(previous, dict) or set(previous) != set(expected_files):
            raise ValueError('resume baseline manifest is incomplete')
        for name, info in previous.items():
            if info is None:
                continue
            data = (folder / 'previous' / name).read_bytes()
            if not isinstance(info, dict) or info != {'sha256': digest(data), 'bytes': len(data)}:
                raise ValueError('resume baseline integrity mismatch: ' + name)
            baseline[name] = data
        report['previous'] = previous
        report['request_published'] = True

    def save():
        (folder / 'result.json').write_text(json.dumps(report, indent=2) + '\n')

    def names(path):
        if clock() >= deadline:
            raise TimeoutError('overall GPU profile deadline exceeded')
        return {n for n, _ in ftp.mlsd(path)}

    def read(path, limit=LIMIT):
        data = bytearray()
        def consume(chunk):
            if clock() >= deadline:
                raise TimeoutError('overall GPU profile deadline exceeded during transfer')
            if len(data) + len(chunk) > limit:
                raise ValueError('remote file exceeds limit: ' + path)
            data.extend(chunk)
        ftp.retrbinary('RETR ' + path, consume, blocksize=65536)
        return bytes(data)

    def upload_atomic(data, target):
        temp = capture_run.REMOTE + '/.gpu_upload_' + uuid.uuid4().hex + '.tmp'
        ftp.storbinary('STOR ' + temp, io.BytesIO(data))
        if read(temp, 4096) != data:
            raise RuntimeError('upload readback mismatch; temporary retained: ' + temp)
        if target.rsplit('/', 1)[-1] in names(capture_run.REMOTE):
            raise RuntimeError('target appeared; temporary retained: ' + temp)
        ftp.rename(temp, target)

    save()
    try:
        if resumed is None:
            existing = names(capture_run.REMOTE)
            if ('bench_request.txt' in existing or any(n.startswith(prefix + '.') for n in existing)):
                raise RuntimeError('request/run already exists; no remote changes made')
            if 'bench_gpu_profile.flag' not in existing or 'perfil_gpu.flag' in existing:
                raise RuntimeError('requires bench_gpu_profile.flag and no legacy perfil_gpu.flag; startup enablement cannot be verified remotely')
            old_names = names(export_dir)
            if not compact and old_names.intersection(name + '.partial' for name in REPORTS + DETAILS):
                raise RuntimeError('archive existing partial native reports before a new capture; no request published')
            if cpu_reports_only and old_names.intersection(set(DETAILS) - set(CPU_DETAILS)):
                raise RuntimeError('archive existing unselected native reports before a CPU-only transfer; no request published')
            previous = folder / 'previous'
            previous.mkdir()
            for name in expected_files:
                if name in old_names:
                    data = read(export_dir.rstrip('/') + '/' + name)
                    (previous / name).write_bytes(data)
                    baseline[name] = data
                    report['previous'][name] = {'sha256': digest(data), 'bytes': len(data)}
                else:
                    report['previous'][name] = None
            save()  # Existing report bytes are safely local before any request upload.
            if gpu_resolve_fast:
                upload_atomic(b'gpu-resolve-fast\n', capture_run.REMOTE + '/' + prefix + '.gpu-resolve-fast')
            if resolve_swap:
                upload_atomic(b'resolve-swap\n', capture_run.REMOTE + '/' + prefix + '.resolve-swap')
            upload_atomic(b'gpu_profile_request\n', capture_run.REMOTE + '/' + prefix + opt_in)
            upload_atomic(f'{run_id} {duration} {build}\n'.encode(), capture_run.REMOTE + '/bench_request.txt')
            report['request_published'] = True
            save()
        guest = None
        stable = None
        while clock() < deadline:
            try:
                remote = names(capture_run.REMOTE)
                report['trigger_observed'] = prefix + opt_in + '-requested' in remote
                if prefix + '.failed' in remote:
                    (folder / 'failure.txt').write_bytes(read(capture_run.REMOTE + '/' + prefix + '.failed', 4096))
                    if prefix + '.csv' in remote:
                        (folder / 'capture.csv').write_bytes(read(capture_run.REMOTE + '/' + prefix + '.csv'))
                    raise RuntimeError('guest benchmark gate failed; GPU result remains unconfirmed')
                if guest is None and prefix + '.done' in remote:
                    if read(capture_run.REMOTE + '/' + prefix + '.done', 256) != b'complete\n':
                        raise ValueError('invalid benchmark completion marker')
                    raw = read(capture_run.REMOTE + '/' + prefix + '.csv')
                    (folder / 'capture.csv').write_bytes(raw)
                    guest = summarize_capture.summarize(folder / 'capture.csv')
                    if guest['run_id'] != run_id or guest['build_id_reported'] != build or guest['player_state_gate'] != 'passed':
                        raise ValueError('benchmark identity/player gate not confirmed')
                    if gpu_resolve_fast and guest.get('gpu_resolve_fast') != 'on':
                        raise ValueError('gpu_resolve_fast mode not confirmed in guest capture')
                    if resolve_swap and guest.get('resolve_swap') != 'on':
                        raise ValueError('resolve_swap mode not confirmed in guest capture')
                    report['guest_capture'] = guest
                current = remote if compact else names(export_dir)
                fresh = {}
                for name in reports:
                    if name in current:
                        data = read(export_dir.rstrip('/') + '/' + name)
                        if data and data != baseline.get(name):
                            fresh[name] = data
                            (folder / name).write_bytes(data)
                            report['fresh'][name] = {'sha256': digest(data), 'bytes': len(data)}
                signature = tuple(digest(fresh[n]) for n in reports) if len(fresh) == len(reports) else None
                if signature is not None and signature == stable and guest is not None and report['trigger_observed']:
                    raw_csv = fresh[reports[-1]]
                    if not raw_csv.endswith(b'\n'):
                        raise ValueError('native CSV is truncated')
                    rows = list(csv.DictReader(io.StringIO(raw_csv.decode('utf-8'))))
                    if len(rows) < expected_samples or any(None in row or None in row.values() for row in rows):
                        raise ValueError('native CSV missing expected samples or malformed columns')
                    for field in ('frame', 'capture_index', 'gpu_frame_ms', 'flags'):
                        if field not in rows[0]:
                            raise ValueError('native CSV schema missing ' + field)
                    if compact:
                        ids = {row.get('capture_id', '') for row in rows}
                        if len(rows) != expected_samples or len(ids) != 1 or not next(iter(ids)).isdigit():
                            raise ValueError('compact capture size or ID mismatch')
                        if [int(row['capture_index']) for row in rows] != list(range(len(rows))):
                            raise ValueError('compact capture indices are not consecutive')
                        if len({int(row['frame']) for row in rows}) != len(rows):
                            raise ValueError('compact capture contains duplicate frames')
                        regions_name = prefix + '.gpu.csv.regions.csv'
                        if regions_name in remote:
                            regions = read(capture_run.REMOTE + '/' + regions_name,
                                           16 * 1024 * 1024)
                            region_count = validate_compact_regions(regions, rows)
                            (folder / regions_name).write_bytes(regions)
                            report['gpu_regions'] = {
                                'file': regions_name, 'sha256': digest(regions),
                                'bytes': len(regions), 'timed_rows': region_count,
                                'coverage': 'only already-timed available regions; not exhaustive',
                            }
                        timeline_name = prefix + '.timeline'
                        if timeline_name in remote:
                            (folder / 'frame_timeline.txt').write_bytes(
                                read(capture_run.REMOTE + '/' + timeline_name, 4 * 1024 * 1024))
                        report.update(status='fresh_export_observed', native_samples=len(rows),
                                      capture_id=next(iter(ids)),
                                      samples_with_gpu_time=sum(bool(row['gpu_frame_ms']) for row in rows),
                                      samples_with_flags=sum(int(row['flags']) != 0 for row in rows))
                        save()
                        return folder, report
                    if fresh[REPORTS[0]].count(b' domain=meta ') < len(rows):
                        raise ValueError('native log does not contain all CSV sample metadata')
                    # Flat CSV is published after all detail files have been renamed.
                    # Preserve the requested bundle, with metadata identity verification.
                    report['details'] = {}
                    for name in selected_details:
                        if name not in current:
                            raise ValueError('native detail bundle missing ' + name)
                        data = read(diagnostics_dir.rstrip('/') + '/' + name)
                        (folder / name).write_bytes(data)
                        report['details'][name] = {'sha256': digest(data), 'bytes': len(data)}
                    metadata = json.loads((folder / 'native-performance-meta.json').read_text())
                    capture_ids = {row.get('capture_id') for row in rows}
                    if capture_ids != {str(metadata.get('capture_id'))}:
                        raise ValueError('native CSV/detail capture identity mismatch')
                    report.update(status='fresh_export_observed', native_samples=len(rows),
                                  samples_with_gpu_time=sum(bool(row['gpu_frame_ms']) for row in rows),
                                  samples_with_flags=sum(int(row['flags']) != 0 for row in rows),
                                  quality='not established; inspect flags, unavailable queries and detailed exports')
                    save()
                    return folder, report
                stable = signature
                save()
            except ftplib.error_perm as exc:
                # libnx FTP can expose an in-progress export as EBUSY. Other
                # 550 responses (permissions, missing paths) remain fatal.
                if not (str(exc).startswith('550 ') and 'device or resource busy' in str(exc).lower()):
                    raise
                stable = None
                report['export_retry'] = str(exc)
                save()
            sleep(min(2, max(0, deadline - clock())))
        raise TimeoutError('no confirmed fresh native export before deadline; existing/partial files retained')
    except Exception as exc:
        report['error'] = str(exc)
        save()
        raise RuntimeError(f'{exc}; evidence: {folder}') from exc


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--resume', type=Path, help='resume a published request in an existing GPU profile folder; never uploads commands')
    p.add_argument('--host', required=True)
    p.add_argument('--port', type=int, default=5000)
    p.add_argument('--diagnostics-dir', help='exact FTP directory containing native-performance-latest.*')
    p.add_argument('--build-label', required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--duration', type=int, default=20)
    p.add_argument('--timeout', type=int, default=180)
    p.add_argument('--expected-samples', type=int)
    p.add_argument('--compact', action='store_true', help='request the per-run 120-frame CSV')
    p.add_argument('--gpu-resolve-fast', action='store_true', help='enable fast GPU resolve mode for this capture')
    p.add_argument('--resolve-swap', action='store_true', help='enable zero-copy resolve swap for this capture')
    p.add_argument('--cpu-reports-only', action='store_true',
                   help='download CPU/frame/metadata reports without the large trace; GPU instrumentation remains enabled')
    a = p.parse_args()
    if not a.compact and not a.diagnostics_dir:
        p.error('--diagnostics-dir is required for detailed export')
    if a.compact:
        a.diagnostics_dir = capture_run.REMOTE
    expected = a.expected_samples if a.expected_samples is not None else (120 if a.compact else 300)
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(a.host, a.port, timeout=8)
            ftp.login(os.environ.get('GTA4NX_FTP_USER', 'anonymous'), os.environ.get('GTA4NX_FTP_PASSWORD', ''))
            _, result = run(ftp, a.diagnostics_dir, a.build_label, a.duration, a.output_dir,
                            a.timeout, expected_samples=expected, resume=a.resume, compact=a.compact,
                            gpu_resolve_fast=a.gpu_resolve_fast, resolve_swap=a.resolve_swap,
                            cpu_reports_only=a.cpu_reports_only)
        print(json.dumps(result))
        return 0
    except (OSError, ValueError, RuntimeError, EOFError, ftplib.Error) as exc:
        print(json.dumps({'status': 'unconfirmed', 'error': str(exc)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
