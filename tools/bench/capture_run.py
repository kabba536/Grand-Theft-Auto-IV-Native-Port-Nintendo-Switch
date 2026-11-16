#!/usr/bin/env python3
"""Request one guest-publish capture from a benchmark-enabled GTA4NX build."""
import argparse
import ftplib
import io
import json
import math
import os
from pathlib import Path
import re
import tempfile
import time
import uuid
import summarize_capture

REMOTE = '/switch/gta4nx/logs/rex'
TOKEN = re.compile(r'^[A-Za-z0-9_-]{1,48}$')


class CaptureInterrupted(RuntimeError):
    """The request was published, but the console connection failed."""


def validate_input_script(data):
    if not data or len(data) > 4096: raise ValueError('input script must be 1-4096 bytes')
    try: lines = [line.split() for line in data.decode('ascii').splitlines() if line.strip()]
    except UnicodeDecodeError as exc: raise ValueError('input script must be ASCII') from exc
    if not 2 <= len(lines) <= 17 or lines[0][0] != 'start' or len(lines[0]) != 5:
        raise ValueError('input script requires start and 1-16 step lines')
    try:
        start = [float(v) for v in lines[0][1:]]
        if not all(map(math.isfinite, start)) or not 0 < start[3] <= 5:
            raise ValueError('invalid start point or tolerance')
        total = 0
        for row in lines[1:]:
            if len(row) != 10 or row[0] != 'step': raise ValueError('invalid step syntax')
            polls, lx, ly, rx, ry = map(int, row[1:6])
            endpoint = [float(v) for v in row[6:]]
            if not 1 <= polls <= 120 or not all(-32768 <= axis <= 32767 for axis in (lx, ly, rx, ry)):
                raise ValueError('step poll or axis out of range')
            if not all(map(math.isfinite, endpoint)) or not 0 < endpoint[3] <= 10:
                raise ValueError('invalid endpoint or tolerance')
            total += polls
        if total > 300: raise ValueError('input script exceeds 300 polls')
    except (TypeError, ValueError) as exc:
        raise ValueError('invalid input script: ' + str(exc)) from exc


def entries(ftp):
    return {n for n, _ in ftp.mlsd(REMOTE)}


def read_file(ftp, path, limit):
    data = bytearray()
    def consume(chunk):
        if len(data) + len(chunk) > limit: raise ValueError('remote result exceeds size limit')
        data.extend(chunk)
    ftp.retrbinary('RETR ' + path, consume, blocksize=65536)
    return bytes(data)


def _stage_marker(ftp, remote_path, payload, label):
    """Upload a short benchmark marker file and verify it via FTP readback."""
    ftp.storbinary('STOR ' + remote_path, io.BytesIO(payload))
    if read_file(ftp, remote_path, 256) != payload:
        raise RuntimeError(f'{label} experiment marker readback mismatch')


def run(ftp, run_id, build, duration, parent, deadline_s, sleep=time.sleep,
        clock=time.monotonic, input_script=None, batch_barriers=False, resolve_swap=False,
        gpu_resolve_fast=False):
    if not TOKEN.fullmatch(run_id) or not TOKEN.fullmatch(build): raise ValueError('invalid run or build token')
    if not 1 <= duration <= 300 or deadline_s < duration + 3: raise ValueError('invalid duration or deadline')
    if input_script is not None: validate_input_script(input_script)
    parent = Path(parent)
    out = Path(tempfile.mkdtemp(prefix='guest-capture-', dir=parent)); os.chmod(out, 0o700)
    request = f'{run_id} {duration} {build}\n'.encode('ascii')
    filename = 'bench_request.txt'; prefix = f'bench_{run_id}'
    existing = entries(ftp)
    if filename in existing or any(n.startswith(prefix + '.') for n in existing):
        raise ValueError('request or run identifier already exists; no remote changes made')
    if batch_barriers:
        _stage_marker(ftp, REMOTE + '/' + prefix + '.barriers', b'batch-target-barriers\n', 'barrier')
    if resolve_swap:
        _stage_marker(ftp, REMOTE + '/' + prefix + '.resolve-swap', b'resolve-swap\n', 'resolve swap')
    if gpu_resolve_fast:
        _stage_marker(ftp, REMOTE + '/' + prefix + '.gpu-resolve-fast', b'gpu-resolve-fast\n', 'gpu resolve fast')
    if input_script is not None:
        script_temp = REMOTE + '/.bench_input_upload_' + uuid.uuid4().hex + '.tmp'
        ftp.storbinary('STOR ' + script_temp, io.BytesIO(input_script))
        if read_file(ftp, script_temp, 4096) != input_script:
            raise RuntimeError('script readback mismatch; temporary retained: ' + script_temp)
        script_target = REMOTE + '/' + prefix + '.input'
        if prefix + '.input' in entries(ftp):
            raise RuntimeError('script target appeared; temporary retained: ' + script_temp)
        ftp.rename(script_temp, script_target)
    tempname = f'.bench_upload_{uuid.uuid4().hex}.tmp'
    temp = REMOTE + '/' + tempname
    ftp.storbinary('STOR ' + temp, io.BytesIO(request))
    if read_file(ftp, temp, 256) != request: raise RuntimeError('request readback mismatch; temporary retained: ' + temp)
    if filename in entries(ftp): raise RuntimeError('another request appeared; temporary retained: ' + temp)
    # FTP has no portable atomic rename-if-absent: only one runner may operate.
    ftp.rename(temp, REMOTE + '/' + filename)
    end = clock() + deadline_s
    (out / 'request.txt').write_bytes(request)
    claimed = False
    while clock() < end:
        try:
            names = entries(ftp)
        except (OSError, EOFError, ftplib.Error) as exc:
            stage = 'claimed' if claimed else 'claim unconfirmed'
            raise CaptureInterrupted(f'capture connection lost ({stage}); {run_id}, evidence at {out}') from exc
        claimed |= prefix + '.claimed' in names
        if prefix + '.failed' in names:
            failure = read_file(ftp, REMOTE + '/' + prefix + '.failed', 256)
            if prefix + '.csv' in names:
                (out/'capture.csv').write_bytes(read_file(ftp, REMOTE + '/' + prefix + '.csv', 16 * 1024 * 1024))
            (out/'failure.txt').write_bytes(failure)
            reason = 'capture gate failed' if input_script is not None else 'player state gate failed'
            raise RuntimeError(reason + '; evidence at ' + str(out))
        if prefix + '.done' in names:
            marker = read_file(ftp, REMOTE + '/' + prefix + '.done', 256)
            if marker != b'complete\n': raise ValueError('invalid completion marker')
            if prefix + '.csv' not in names: raise ValueError('marker exists but capture is missing')
            data = read_file(ftp, REMOTE + '/' + prefix + '.csv', 16 * 1024 * 1024)
            target = out/'capture.csv'; target.write_bytes(data)
            if input_script is not None and (
                b'# input_script=requested\n' not in data or
                b'# input_script_gate=passed\n' not in data or
                b'# input_script_status=4\n' not in data):
                raise ValueError('script completion not confirmed in capture')
            result = summarize_capture.summarize(target)
            if result['run_id'] != run_id or result['build_id_reported'] != build: raise ValueError('capture identity mismatch')
            if result['player_state_gate'] != 'passed': raise ValueError('player state gate not confirmed')
            # Only collect a sidecar published for this run before its marker.
            timeline_name = prefix + '.timeline'
            if timeline_name in names:
                tl_path = out / 'frame_timeline.txt'
                tl_data = read_file(ftp, REMOTE + '/' + timeline_name, 4 * 1024 * 1024)
                tl_path.write_bytes(tl_data)
                result['frame_timeline'] = str(tl_path)
            (out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
            return out,result
        sleep(2)
    stage = 'claimed' if claimed else 'claim unconfirmed'
    raise TimeoutError(f'capture did not complete ({stage}); {run_id}, evidence at {out}')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',required=True);p.add_argument('--port',type=int,default=5000)
    p.add_argument('--duration',type=int,default=20);p.add_argument('--build-label',required=True);p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--timeout',type=int,default=90)
    p.add_argument('--input-script',type=Path,help='ASCII poll-indexed input script to upload before request')
    a=p.parse_args()
    run_id='r'+uuid.uuid4().hex
    try:
        with ftplib.FTP() as ftp:
            ftp.connect(a.host,a.port,timeout=8);ftp.login(os.environ.get('GTA4NX_FTP_USER','anonymous'),os.environ.get('GTA4NX_FTP_PASSWORD',''))
            script = a.input_script.read_bytes() if a.input_script else None
            folder,result=run(ftp,run_id,a.build_label,a.duration,a.output_dir,a.timeout,
                              input_script=script)
        print(json.dumps({'status':'capture_complete','path':str(folder),'summary':result}))
        return 0
    except (OSError,ValueError,RuntimeError,EOFError,ftplib.Error) as e:
        print(json.dumps({'status':'capture_failed','run_id':run_id,'error':str(e)}));return 1

if __name__=='__main__': raise SystemExit(main())
