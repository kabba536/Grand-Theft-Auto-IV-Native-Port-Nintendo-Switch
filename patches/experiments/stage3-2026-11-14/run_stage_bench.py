#!/usr/bin/env python3
import argparse
import hashlib
import io
import json
import sys
import time
import uuid
from ftplib import FTP
from pathlib import Path

TOOLS_DIR = Path(r'C:\Users\Dima\Desktop\gta4nx\gta4nx\tools\bench')
sys.path.insert(0, str(TOOLS_DIR))
sys.path.insert(0, str(TOOLS_DIR.parent / 'device'))

import autorun  # noqa: E402
import capture_run  # noqa: E402
import collect_profile  # noqa: E402
import teleport_run  # noqa: E402
import analyze_frame_timeline  # noqa: E402

HOST = '192.168.1.220'
FTP_PORT = 5000
REX_DIR = '/switch/gta4nx/logs/rex'
POS = (900.78, -521.38, 15.04)


def ftp_conn(timeout=15):
    f = FTP(timeout=timeout)
    f.connect(HOST, FTP_PORT)
    f.login()
    return f


def stage_ubo_flag(f, mode='all-three'):
    flag_path = REX_DIR + '/bench_aligned_ubo.flag'
    existing = {n for n, _ in f.mlsd(REX_DIR)}
    backup = None
    if 'bench_aligned_ubo.flag' in existing:
        backup = REX_DIR + '/bench_aligned_ubo.flag.archive-' + uuid.uuid4().hex
        f.rename(flag_path, backup)
    payload = f'{uuid.uuid4().hex} {mode}\n'.encode('ascii')
    f.storbinary('STOR ' + flag_path, io.BytesIO(payload))
    return backup


def restore_ubo_flag(f, backup):
    flag_path = REX_DIR + '/bench_aligned_ubo.flag'
    existing = {n for n, _ in f.mlsd(REX_DIR)}
    if 'bench_aligned_ubo.flag' in existing:
        f.delete(flag_path)
    if backup:
        f.rename(backup, flag_path)


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--sha', required=True)
    p.add_argument('--out-dir', type=Path, required=True)
    p.add_argument('--runs', type=int, default=1)
    p.add_argument('--duration', type=int, default=20)
    p.add_argument('--settle', type=float, default=8.0)
    p.add_argument('--ubo-payload', default='all-three')
    args = p.parse_args()

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    autorun.POS = POS
    autorun.OUT = out_dir

    # Check clean HOME state before launch
    tid = autorun.title_id()
    if tid and not autorun.engine_alive():
        raise RuntimeError(f'Unexpected foreground app open: {tid}')

    ubo_backup = None
    with ftp_conn(20) as f:
        autorun.verify_installed_nro(f, args.sha)
        if args.ubo_payload:
            ubo_backup = stage_ubo_flag(f, args.ubo_payload)

    captures = []
    screens = []
    try:
        autorun.launch()
        autorun.wait_world(120)
        tp_reason = autorun.teleport(90)
        print(f'[bench] teleported: {tp_reason}, settling {args.settle}s', flush=True)
        time.sleep(args.settle)

        for i in range(args.runs):
            img0 = autorun.capture_screenshot_bytes()
            bright0 = autorun.verify_visible_game(img0)
            vp_path = out_dir / f'viewport-{i}.jpg'
            vp_path.write_bytes(img0)
            screens.append(str(vp_path))
            print(f'[bench] viewport-{i}.jpg bright={bright0:.3f}', flush=True)

            cap = autorun.capture(
                args.duration,
                rotate=False,
                build=args.sha[:12],
                require_camera=False,
                gpu_resolve_fast=True,
                resolve_swap=False,
            )
            captures.append(cap)
            print(
                f"[bench] run {i}: samples={cap['samples']} mean={cap['mean_ms']:.3f}ms "
                f"median={cap['median_ms']:.3f}ms p95={cap['p95_ms']:.3f}ms",
                flush=True,
            )

        end_img = autorun.capture_screenshot_bytes()
        (out_dir / 'gameplay-end.jpg').write_bytes(end_img)

        summary = {
            'benchmark_position': list(POS),
            'sha': args.sha,
            'ubo_payload': args.ubo_payload.strip(),
            'teleport': tp_reason,
            'captures': captures,
            'screens': screens,
        }
        (out_dir / 'captures.json').write_text(json.dumps(summary, indent=2))
    finally:
        if autorun.engine_alive():
            try:
                autorun.exit_game(args.sha)
                print('[bench] clean exit completed', flush=True)
            except Exception as e:
                print(f'[bench] exit exception: {e}', file=sys.stderr, flush=True)
        try:
            exit_img = autorun.capture_screenshot_bytes()
            (out_dir / 'exit.jpg').write_bytes(exit_img)
        except Exception:
            pass
        try:
            with ftp_conn(15) as f:
                if args.ubo_payload:
                    restore_ubo_flag(f, ubo_backup)
        except Exception as e:
            print(f'[bench] ubo restore error: {e}', file=sys.stderr, flush=True)

    # Collect rex_perfil.log
    rc = collect_profile.main([
        '--host', HOST,
        '--remote', f'{REX_DIR}/rex_perfil.log',
        '--output-dir', str(out_dir),
    ])
    print(f'[bench] collect_profile rc={rc}', flush=True)

    # Analyze timelines
    for i, c in enumerate(captures):
        tl = c.get('frame_timeline')
        if tl and Path(tl).exists():
            tl_path = Path(tl)
            csvs = sorted(tl_path.parent.glob('*.csv'))
            if csvs:
                sum_path = tl_path.parent / 'summary.json'
                print(f'=== Timeline run {i}: {tl} ===', flush=True)
                old_argv = sys.argv
                try:
                    sys.argv = ['analyze_frame_timeline.py', '--summary', str(sum_path), str(tl_path), str(csvs[0])]
                    analyze_frame_timeline.main()
                finally:
                    sys.argv = old_argv
                if sum_path.exists():
                    print(sum_path.read_text(encoding='utf-8'), flush=True)


if __name__ == '__main__':
    sys.exit(main())
