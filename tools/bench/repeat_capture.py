#!/usr/bin/env python3
"""Run a bounded series of guest captures, optionally with input scripts.

Each --input-script defines a scenario; '-' means no script. Scenarios run in
argument order, count times each. Only one runner may use the console at a time.
"""
import argparse
import ftplib
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile
import uuid

import capture_run

NOTE = ('Guest publish captures only. Repetition and input gates do not establish '
        'scene comparability, visual correctness, or performance improvement. '
        'No scene reset is performed between runs.')
ERRORS = (OSError, ValueError, RuntimeError, EOFError, ftplib.Error)


def load_scripts(paths):
    """Read and validate every scenario before any remote operation."""
    scenarios = []
    for path in paths or [None]:
        if path is None or str(path) == '-':
            scenarios.append((None, None))
            continue
        with Path(path).open('rb') as stream:
            data = stream.read(4097)
        capture_run.validate_input_script(data)
        scenarios.append((str(Path(path).resolve()), data))
    return scenarios


def series(ftp, count, duration, build_label, parent, timeout, scripts=None):
    paths = list(scripts or [None])
    if not 1 <= count <= 30 or not 1 <= len(paths) <= 30 or count * len(paths) > 30:
        raise ValueError('series must contain 1..30 total captures')
    if not 1 <= duration <= 300 or not math.isfinite(timeout) or timeout < duration + 3 or timeout > 3600:
        raise ValueError('duration must be 1..300 and timeout duration+3..3600 seconds')
    if not capture_run.TOKEN.fullmatch(build_label):
        raise ValueError('invalid build token')
    scenarios = load_scripts(paths)
    root = Path(tempfile.mkdtemp(prefix='repeat-capture-', dir=parent))
    os.chmod(root, 0o700)
    report = {'status': 'running', 'planned_count': count * len(paths),
              'build_label': build_label, 'duration': duration, 'timeout': timeout,
              'note': NOTE, 'scenarios': [], 'runs': []}

    def save():
        temporary = root / 'series.json.tmp'
        temporary.write_text(json.dumps(report, indent=2) + '\n')
        temporary.replace(root / 'series.json')

    for index, (source, data) in enumerate(scenarios):
        entry = {'index': index, 'source': source, 'input_script': None}
        if data is not None:
            target = root / f'scenario-{index}.input'
            target.write_bytes(data)
            entry.update(input_script=str(target), sha256=hashlib.sha256(data).hexdigest())
        report['scenarios'].append(entry)
    save()
    for index, (_, data) in enumerate(scenarios):
        for repetition in range(count):
            run_id = 'r' + uuid.uuid4().hex
            # The attempt directory also retains any partial capture evidence on failure.
            attempt = root / f'scenario-{index}-run-{repetition}'
            attempt.mkdir(mode=0o700)
            record = {'scenario': index, 'repetition': repetition, 'run_id': run_id,
                      'path': str(attempt), 'status': 'running'}
            report['runs'].append(record)
            save()
            try:
                path, summary = capture_run.run(ftp, run_id, build_label, duration,
                                                attempt, timeout, input_script=data)
                record.update(status='complete', path=str(path), summary=summary)
                save()
            except ERRORS as exc:
                record.update(status='failed', error=str(exc)[:2048])
                report['status'] = 'incomplete'
                save()
                raise RuntimeError(f'series incomplete; evidence at {root}: {str(exc)[:2048]}') from exc
    report['status'] = 'captures_complete'
    save()
    return root, report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--count', type=int, default=3, help='repetitions per scenario; at most 30 total')
    parser.add_argument('--duration', type=int, default=20)
    parser.add_argument('--build-label', required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=90)
    parser.add_argument('--input-script', action='append', help="scenario path, repeatable; '-' for unscripted")
    args = parser.parse_args()
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(args.host, args.port, timeout=8)
            ftp.login(os.environ.get('GTA4NX_FTP_USER', 'anonymous'), os.environ.get('GTA4NX_FTP_PASSWORD', ''))
            root, report = series(ftp, args.count, args.duration, args.build_label,
                                  args.output_dir, args.timeout, args.input_script)
        print(json.dumps({'status': report['status'], 'path': str(root), 'note': NOTE}))
        return 0
    except ERRORS as exc:
        print(json.dumps({'status': 'series_failed', 'error': str(exc)[:4096]}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
