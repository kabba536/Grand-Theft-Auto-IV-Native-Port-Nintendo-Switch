#!/usr/bin/env python3
"""Stage one verified benchmark NRO and restore it using a local journal."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import uuid

import autorun

GAME_DIR = '/switch/gta4nx'
NRO = GAME_DIR + '/gta4nx.nro'
TIMELINE = autorun.REX + '/bench_frame_timeline.flag'
GPU = autorun.REX + '/bench_gpu_profile.flag'
SHA256 = re.compile(r'[0-9a-f]{64}')


def remote_hash(ftp, path):
    digest = hashlib.sha256()
    ftp.retrbinary('RETR ' + path, digest.update, blocksize=262144)
    return digest.hexdigest()


def existing_paths(ftp):
    return {f'{folder}/{name}' for folder in (GAME_DIR, autorun.REX)
            for name, _ in ftp.mlsd(folder)}


def require_hash(ftp, path, expected):
    if remote_hash(ftp, path) != expected:
        raise ValueError(f'unexpected SHA-256 at {path}')


def paths(journal):
    suffix = '.bench-' + journal['id']
    return NRO + suffix + '.previous', NRO + suffix + '.candidate', GPU + suffix, TIMELINE + suffix


def timeline_data(journal):
    return (journal['id'] + '\n').encode('ascii')


def prior_timeline_path(journal):
    return TIMELINE + '.bench-' + journal['id'] + '.previous'


def deploy(ftp, journal, source, *, defer_active_readback=False):
    backup, candidate, gpu_backup, timeline_backup = paths(journal)
    with source.open('rb') as stream:
        ftp.storbinary('STOR ' + candidate, stream, blocksize=262144)
    require_hash(ftp, candidate, journal['candidate'])
    if journal['gpu'] is not None and not journal.get('keep_gpu_marker'):
        ftp.rename(GPU, gpu_backup)
        require_hash(ftp, gpu_backup, journal['gpu'])
    if journal.get('timeline') is not None:
        ftp.rename(TIMELINE, prior_timeline_path(journal))
        require_hash(ftp, prior_timeline_path(journal), journal['timeline'])
    timeline = timeline_data(journal)
    ftp.storbinary('STOR ' + timeline_backup, io.BytesIO(timeline))
    require_hash(ftp, timeline_backup, hashlib.sha256(timeline).hexdigest())
    ftp.rename(timeline_backup, TIMELINE)
    ftp.rename(NRO, backup)
    ftp.rename(candidate, NRO)
    if not defer_active_readback:
        require_hash(ftp, NRO, journal['candidate'])


def restore(ftp, journal, present):
    backup, candidate, gpu_backup, timeline_backup = paths(journal)
    if backup in present:
        require_hash(ftp, backup, journal['previous'])
        if NRO in present:
            require_hash(ftp, NRO, journal['candidate'])
            if candidate in present:
                raise ValueError('candidate archive destination already exists')
            ftp.rename(NRO, candidate)
        ftp.rename(backup, NRO)
    require_hash(ftp, NRO, journal['previous'])
    timeline_active = TIMELINE in present
    if timeline_active and not (
            journal.get('timeline') is not None
            and remote_hash(ftp, TIMELINE) == journal['timeline']):
        require_hash(ftp, TIMELINE, hashlib.sha256(timeline_data(journal)).hexdigest())
        if timeline_backup in present:
            raise ValueError('timeline archive destination already exists')
        ftp.rename(TIMELINE, timeline_backup)
        timeline_active = False
    prior_timeline = prior_timeline_path(journal)
    if journal.get('timeline') is not None:
        if prior_timeline in present:
            if timeline_active:
                raise ValueError('timeline restore destination already exists')
            require_hash(ftp, prior_timeline, journal['timeline'])
            ftp.rename(prior_timeline, TIMELINE)
        require_hash(ftp, TIMELINE, journal['timeline'])
    elif timeline_active:
        raise ValueError('unexpected timeline marker')
    if journal['gpu'] is not None:
        if gpu_backup in present:
            if GPU in present:
                raise ValueError('GPU marker destination already exists')
            require_hash(ftp, gpu_backup, journal['gpu'])
            ftp.rename(gpu_backup, GPU)
        require_hash(ftp, GPU, journal['gpu'])
    elif GPU in present:
        raise ValueError('unexpected GPU marker')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('deploy', 'restore'))
    parser.add_argument('--host', required=True)
    parser.add_argument('--journal', type=Path, required=True)
    parser.add_argument('--nro', type=Path)
    parser.add_argument('--candidate-sha256')
    parser.add_argument('--previous-sha256')
    parser.add_argument('--keep-gpu-marker', action='store_true',
                        help='Preserve an existing explicit GPU bench startup flag')
    parser.add_argument('--defer-active-readback', action='store_true',
                        help='Skip the duplicate post-rename readback; run autorun --verify-build before launch')
    args = parser.parse_args()
    if args.defer_active_readback and args.action != 'deploy':
        parser.error('--defer-active-readback applies only to deploy')
    autorun.HOST = args.host
    try:
        if autorun.title_id() or autorun.program_running(0x03DB163FAA760000):
            raise ValueError('close GTA4NX and confirm HOME before switching binaries')
        with autorun.ftp(25) as ftp:
            present = existing_paths(ftp)
            if args.action == 'deploy':
                if not (args.nro and SHA256.fullmatch(args.previous_sha256 or '')
                        and SHA256.fullmatch(args.candidate_sha256 or '')
                        and args.previous_sha256 != args.candidate_sha256):
                    raise ValueError('deployment requires a candidate NRO and two distinct SHA-256 values')
                with args.nro.open('rb') as stream:
                    if hashlib.file_digest(stream, 'sha256').hexdigest() != args.candidate_sha256:
                        raise ValueError('local NRO hash mismatch')
                blocked = {*(autorun.REX + '/' + name for name in (
                    'bench_request.txt', 'teleport_request.txt', 'bench_exit_request.txt',
                    'bench_aligned_ubo.flag',
                    'bench_guest_poll_yield.flag',
                    'perfil_gpu.flag', 'perfil_pilas.flag', 'bench_pgo_dump.flag'))}
                if present & blocked:
                    raise ValueError(f'conflicting files: {sorted(present & blocked)}')
                if args.keep_gpu_marker and GPU not in present:
                    raise ValueError('explicit GPU benchmark startup flag is missing')
                require_hash(ftp, NRO, args.previous_sha256)
                journal = {'host': args.host, 'id': uuid.uuid4().hex,
                           'previous': args.previous_sha256, 'candidate': args.candidate_sha256,
                           'keep_gpu_marker': args.keep_gpu_marker,
                           'gpu': remote_hash(ftp, GPU) if GPU in present else None,
                           'timeline': remote_hash(ftp, TIMELINE) if TIMELINE in present else None}
                with args.journal.open('x') as stream:
                    json.dump(journal, stream, indent=2)
                    stream.write('\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                deploy(ftp, journal, args.nro, defer_active_readback=args.defer_active_readback)
            else:
                journal = json.loads(args.journal.read_text())
                if journal['host'] != args.host or not re.fullmatch(r'[0-9a-f]{32}', journal['id']):
                    raise ValueError('journal host or deployment ID mismatch')
                restore(ftp, journal, present)
        status = 'deploy_staged_verified' if args.defer_active_readback else args.action + '_verified'
        print(json.dumps({'status': status, **journal}))
        return 0
    except Exception as exc:
        print(json.dumps({'status': args.action + '_incomplete', 'error': str(exc),
                          'journal': str(args.journal)}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
