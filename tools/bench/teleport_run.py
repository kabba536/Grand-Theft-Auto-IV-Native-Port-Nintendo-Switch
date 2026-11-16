#!/usr/bin/env python3
"""Upload one engine teleport request, verify FTP readback, and collect its result."""
import argparse
import ftplib
import io
import json
import math
import os
from pathlib import Path
import tempfile
import time
import uuid
from capture_run import REMOTE, TOKEN, read_file


def validate(run_id, position, timeout, remote):
    if not TOKEN.fullmatch(run_id): raise ValueError('invalid request identifier')
    if len(position) != 3 or not all(math.isfinite(v) and abs(v) <= 10000 for v in position):
        raise ValueError('coordinates must be finite and within +/-10000')
    if not -100 <= position[2] <= 1500: raise ValueError('Z must be -100..1500')
    if not math.isfinite(timeout) or not 35 <= timeout <= 300: raise ValueError('timeout must be 35..300 seconds')
    if not remote.startswith('/') or any(v in remote for v in ('\r', '\n')) or '..' in remote.split('/'):
        raise ValueError('invalid remote directory')


def run(ftp, run_id, position, parent, timeout=45, remote=REMOTE,
        sleep=time.sleep, clock=time.monotonic):
    remote = remote.rstrip('/')
    validate(run_id, position, timeout, remote)
    request = (run_id + ' ' + ' '.join(format(v, '.9g') for v in position) + '\n').encode('ascii')
    filename = 'teleport_request.txt'; prefix = 'teleport_' + run_id
    names = lambda: {name for name, _ in ftp.mlsd(remote)}
    existing = names()
    if filename in existing or any(name.startswith(prefix + '.') for name in existing):
        raise ValueError('request or identifier already exists; no remote changes made')
    parent = Path(parent); parent.mkdir(parents=True, exist_ok=True)
    out = Path(tempfile.mkdtemp(prefix='teleport-', dir=parent)); os.chmod(out, 0o700)
    (out / 'request.txt').write_bytes(request)
    temporary = remote + '/.teleport_upload_' + uuid.uuid4().hex + '.tmp'
    report = {'run_id': run_id, 'position': position, 'status': 'uploading', 'remote': remote}
    def save():
        (out / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
    try:
        save()
        ftp.storbinary('STOR ' + temporary, io.BytesIO(request))
        if read_file(ftp, temporary, 256) != request:
            raise RuntimeError('request readback mismatch; temporary retained: ' + temporary)
        if filename in names(): raise RuntimeError('another request appeared; temporary retained: ' + temporary)
        # FTP offers no portable rename-if-absent: run one controller at a time.
        ftp.rename(temporary, remote + '/' + filename)
        report['status'] = 'waiting'; save()
        deadline = clock() + timeout
        claim_verified = False
        while clock() < deadline:
            available = names()
            if prefix + '.claimed' in available and not claim_verified:
                claim = read_file(ftp, remote + '/' + prefix + '.claimed', 256)
                if claim != request: raise RuntimeError('claimed request identity/readback mismatch')
                (out / 'claimed.txt').write_bytes(claim); claim_verified = True
            for suffix, status in (('.failed', 'failed'), ('.done', 'complete')):
                if prefix + suffix not in available: continue
                if not claim_verified: raise RuntimeError('result exists without a verified request claim')
                result = read_file(ftp, remote + '/' + prefix + suffix, 256)
                (out / 'marker.txt').write_bytes(result)
                if status == 'complete' and result != b'position-and-collision-ready\n':
                    raise RuntimeError('unexpected success marker')
                report.update(status=status, reason=result.decode('ascii').strip()); save()
                return out, report
            sleep(min(1, max(0, deadline - clock())))
        raise TimeoutError('teleport result timed out; remote request and evidence preserved')
    except (OSError, ValueError, RuntimeError, EOFError, ftplib.Error) as exc:
        report.update(status='runner_error', error=str(exc)); save()
        raise RuntimeError(f'{exc}; evidence at {out}') from exc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True)
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--position', nargs=3, type=float, required=True, metavar=('X', 'Y', 'Z'))
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--timeout', type=float, default=45)
    parser.add_argument('--remote-dir', default=REMOTE)
    parser.add_argument('--run-id', default='t' + uuid.uuid4().hex)
    args = parser.parse_args()
    try:
        validate(args.run_id, args.position, args.timeout, args.remote_dir)
        with ftplib.FTP() as ftp:
            ftp.connect(args.host, args.port, timeout=8)
            ftp.login(os.environ.get('GTA4NX_FTP_USER', 'anonymous'), os.environ.get('GTA4NX_FTP_PASSWORD', ''))
            out, report = run(ftp, args.run_id, args.position, args.output_dir, args.timeout, args.remote_dir)
        print(json.dumps({'path': str(out), **report}))
        return 0 if report['status'] == 'complete' else 1
    except (OSError, ValueError, RuntimeError, EOFError, ftplib.Error) as exc:
        print(json.dumps({'status': 'runner_error', 'run_id': args.run_id, 'error': str(exc)})); return 1

if __name__ == '__main__': raise SystemExit(main())
