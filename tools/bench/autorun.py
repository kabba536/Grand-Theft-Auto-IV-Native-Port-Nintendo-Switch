#!/usr/bin/env python3
"""One-command hands-free GTA4NX hardware scenario (zero screenshots / vision).

    python3 tools/bench/autorun.py [--runs 3] [--duration 20] [--label NAME]

launch -> verify engine alive -> wait world ready -> teleport (verified) ->
settle -> N captures -> exit requested (UI outcome requires verification). Crash / hang / wrong-app handler
retries the whole scenario (bounded). Prints ONE JSON line; evidence is stored
under ~/.local/share/gta4nx/baselines/. State is derived only from protocol:
FTP markers + engine replies, sys-botbase getTitleID and button RPC.
Exit code: 0 ok, 1 scenario failed after retries, 2 preflight failure.
"""
import argparse, hashlib, io, json, statistics, sys, tempfile, time, uuid
from ftplib import FTP, error_perm
from pathlib import Path
import socket

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE)); sys.path.insert(0, str(HERE.parent / 'device'))
import capture_run          # noqa: E402
import teleport_run         # noqa: E402
import visual_parity        # noqa: E402
from sysbot import SysBot   # noqa: E402

HOST, FTP_PORT = '192.168.1.220', 5000
REX = '/switch/gta4nx/logs/rex'
POS = (900.777161, -506.377258, 15.038386)
OUT = Path.home() / '.local/share/gta4nx/baselines'
APPLET_EXIT_NRO_SHA256 = '2aad3f662e1c4a2fe1a80b2569c4cd403ef15c22933ef179413558e2d1255aee'
TRANSIENT = ('screen-not-faded-in', 'loading', 'cutscene', 'frontend', 'no-context',
             'not-playing', 'origin-collision-not-ready', 'quicksave-busy')
T0 = time.monotonic()
OUT.mkdir(parents=True, exist_ok=True)


class Fail(Exception):
    def __init__(self, stage, why): super().__init__(f'{stage}: {why}'); self.stage, self.why = stage, why


class Fatal(Fail):
    """Needs a human (e.g. frozen process the protocol cannot kill); no retries."""


def log(m): print(f'[{time.monotonic()-T0:6.1f}s] {m}', file=sys.stderr, flush=True)


def ftp(timeout=8):
    f = FTP(timeout=timeout); f.connect(HOST, FTP_PORT); f.login(); return f


def bot():
    return SysBot(HOST)


def title_id():
    b = bot()
    try: return b.query('getTitleID', 64).decode()
    finally: b.close()


def program_running(program_id):
    b = bot()
    try: return b.is_program_running(program_id)
    finally: b.close()


def clicks(*btns, gap=0.7):
    b = bot()
    try:
        for x in btns:
            b.send('click ' + x); time.sleep(gap)
    finally:
        try: b.send('detachController')
        finally: b.close()


def engine_alive():
    """Engine holds rex_stderr.log open => FTP refuses it as busy."""
    try:
        f = ftp()
        try: f.sendcmd(f'MDTM {REX}/rex_stderr.log'); return False
        except error_perm as e: return 'busy' in str(e).lower()
        finally: f.close()
    except OSError: return False


def ready_probe(seconds=2):
    """Engine answers & player in free-roam world? -> (alive, in_world, why)"""
    try:
        f = ftp(10)
        try:
            _, s = capture_run.run(f, 'p' + uuid.uuid4().hex, 'probe', seconds, Path(tempfile.gettempdir()), seconds + 20)
        finally: f.close()
        return True, s.get('player_state_gate') == 'passed', s.get('player_state_gate')
    except (TimeoutError, capture_run.CaptureInterrupted) as e:
        raise Fatal('readiness', str(e)) from e
    except Exception as e:
        return engine_alive(), False, str(e)


def launch():
    """Start GTA from Sphaira; success only when the engine answers."""
    if engine_alive():
        ok, world, _ = ready_probe()
        if ok: log('engine already running'); return
        raise Fail('launch', 'engine alive but unresponsive (hang)')
    if title_id():
        raise Fatal('launch', 'foreground application is already open; launch GTA manually or close it safely')
    log('launch attempt 1')
    clicks('B'); time.sleep(1)
    clicks('A'); time.sleep(5)
    clicks('DUP', 'DUP', 'DUP', 'DUP', 'DLEFT', 'DLEFT', 'DLEFT', 'DLEFT', gap=0.35)
    clicks('DRIGHT', 'A'); log('GTA launch requested; waiting for engine')
    end = time.monotonic() + 75
    while time.monotonic() < end:
        time.sleep(3)
        if engine_alive():
            ok, _, _ = ready_probe()
            if ok: log('engine answering'); return
    raise Fatal('launch', 'engine did not respond; stopped without further button presses')


def wait_world(limit=120):
    end = time.monotonic() + limit; why = ''
    while time.monotonic() < end:
        if not engine_alive(): raise Fail('world', 'engine died while loading')
        ok, world, why = ready_probe()
        if ok and world: log('world ready (player gate passed)'); return
        time.sleep(3)
    raise Fail('world', f'not in free-roam in {limit}s ({why})')


def teleport(limit=90):
    deadline = time.monotonic() + limit
    last = ''
    for _ in range(2):
        remaining = deadline - time.monotonic()
        if remaining < 35:
            break
        if not engine_alive():
            raise Fail('teleport', 'engine died before teleporting')
        with ftp(10) as f:
            out, result = teleport_run.run(
                f, 't' + uuid.uuid4().hex, POS, OUT, timeout=min(45, remaining))
        last = result['reason']
        if result['status'] == 'complete':
            log('teleport done: ' + last)
            return last
        if not any(reason in last for reason in TRANSIENT):
            raise Fail('teleport', f'gate: {last}, evidence at {out}')
        log('teleport gate transient: ' + last)
        time.sleep(3)
    raise Fail('teleport', f'gate stayed closed ({last})')


def rotate_script(strength=9000):
    """Camera-only input: neutral left stick, steady right-stick X (smooth turn in place)."""
    x, y, z = POS
    rows = ['start %.6f %.6f %.6f 3.0' % (x, y, z)]
    rows += ['step 90 0 0 %d 0 %.6f %.6f %.6f 5.0' % (strength, x, y, z)] * 2   # 180 polls ~11s; engine aborts scripts >15s wall (~16 polls/s)
    return ('\n'.join(rows) + '\n').encode()


def capture_screenshot_bytes():
    """Capture one screenshot JPEG/PNG payload from sys-botbase."""
    b = bot()
    try:
        return b.screenshot_bytes()
    finally:
        b.close()


def _viewport_bright_fraction(data):
    from PIL import Image
    with Image.open(io.BytesIO(data)) as image:
        width, height = image.size
        # Exclude the side occupied by Status Monitor and the HUD at the edges.
        viewport = image.crop((width * 2 // 5, height // 7, width * 9 // 10, height * 6 // 7))
        histogram = viewport.convert('L').histogram()
    return sum(histogram[24:]) / sum(histogram)


def verify_visible_game(data=None):
    """Reject a dark viewport with one in-memory pixelPeek sample."""
    if data is None:
        data = capture_screenshot_bytes()
    bright_fraction = _viewport_bright_fraction(data)
    if bright_fraction < 0.01:
        raise Fail('visibility', f'black or near-black viewport ({bright_fraction:.2%} above luma 24)')
    return bright_fraction


def capture(duration, rotate=False, build='autorun', require_camera=False,
            batch_barriers=False, resolve_swap=False, gpu_resolve_fast=False):
    f = ftp(15)
    try:
        folder, s = capture_run.run(f, 'r' + uuid.uuid4().hex, build, duration, OUT, duration + 40,
                               input_script=rotate_script() if rotate else None,
                               batch_barriers=batch_barriers, resolve_swap=resolve_swap,
                               gpu_resolve_fast=gpu_resolve_fast)
    finally: f.close()
    if s.get('player_state_gate') != 'passed': raise Fail('capture', 'player gate ' + str(s.get('player_state_gate')))
    camera = s.get('camera', {})
    if require_camera and (not camera.get('advances') or camera.get('regressions')):
        raise Fail('capture', f'fresh camera snapshots unavailable, evidence at {folder}')
    metrics = ('samples', 'duration_s', 'mean_ms', 'median_ms', 'p95_ms', 'p99_ms',
               'max_ms', 'intervals_over_100ms', 'camera', 'frame_timeline',
               'batch_target_barriers', 'resolve_swap', 'resolve_stats',
               'gpu_resolve_fast', 'gpu_resolve_stats', 'gpu_resolve_mode_persists')
    return {'path': str(folder), **{key: s[key] for key in metrics if key in s}}


def verify_installed_nro(f, expected, timeout=90):
    digest = hashlib.sha256()
    deadline = time.monotonic() + timeout
    f.voidcmd('TYPE I')
    with f.transfercmd('RETR /switch/gta4nx/gta4nx.nro') as data:
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise Fatal('identity', f'NRO readback exceeded {timeout}s')
            data.settimeout(min(f.timeout or remaining, remaining))
            try:
                block = data.recv(262144)
            except socket.timeout as exc:
                raise Fatal('identity', 'NRO readback timed out') from exc
            if not block:
                break
            digest.update(block)
    f.voidresp()
    actual = digest.hexdigest()
    if actual != expected:
        raise Fatal('identity', f'installed NRO SHA-256 mismatch: expected {expected}, got {actual}')


def exit_game(expected=APPLET_EXIT_NRO_SHA256):
    """Request the verified candidate only; UI success still requires observation."""
    active_title = title_id()
    if len(active_title) != 16 or any(c not in '0123456789ABCDEFabcdef' for c in active_title):
        raise Fatal('exit', 'application identity unavailable')
    program_id = int(active_title, 16)
    if not program_running(program_id) or not engine_alive():
        raise Fatal('exit', 'GTA process was not confirmed')
    with ftp(20) as f:
        verify_installed_nro(f, expected)
        if title_id() != active_title or not engine_alive():
            raise Fatal('exit', 'application changed during NRO verification')
        names = {n for n, _ in f.mlsd(REX)}
        if 'bench_exit_request.txt' in names:
            raise Fatal('exit', 'an exit request is already pending; game left running')
        for n in ('bench_exit.done', 'bench_exit.failed'):
            if n in names:
                f.rename(f'{REX}/{n}', f'{REX}/{n}.prior-{uuid.uuid4().hex}')
        stage = f'{REX}/.bench-exit-{uuid.uuid4().hex}.tmp'
        f.storbinary('STOR ' + stage, io.BytesIO(b'exit\n'))
        result = io.BytesIO(); f.retrbinary('RETR ' + stage, result.write)
        if result.getvalue() != b'exit\n': raise Fatal('exit', 'request readback mismatch')
        f.rename(stage, f'{REX}/bench_exit_request.txt')
    end = time.monotonic() + 30
    while time.monotonic() < end:
        time.sleep(1.5)
        with ftp() as f:
            names = {n for n, _ in f.mlsd(REX)}
            if 'bench_exit.failed' in names:
                result = io.BytesIO(); f.retrbinary(f'RETR {REX}/bench_exit.failed', result.write)
                raise Fatal('exit', 'request refused: ' + result.getvalue().decode(errors='replace').strip())
        if not program_running(program_id):
            log('process gone; HOME/error dialog state unverified for this run')
            return
    raise Fatal('exit', 'request did not terminate process in 30s; no retries')


def _active_trial(a):
    """Return `(order, kwarg_name, meta_key, label)` for the selected paired trial."""
    trials = (
        (getattr(a, 'barrier_order', None), 'batch_barriers', 'batch_target_barriers', 'barrier'),
        (getattr(a, 'resolve_swap_order', None), 'resolve_swap', 'resolve_swap', 'resolve swap'),
        (getattr(a, 'gpu_resolve_fast_order', None), 'gpu_resolve_fast', 'gpu_resolve_fast', 'gpu resolve fast'),
    )
    return next((t for t in trials if t[0]), (None, None, None, None))


def scenario(a):
    launch(); wait_world(); tp = teleport(); time.sleep(a.settle)
    verify_visual = getattr(a, 'verify_visual', False)
    ref_screenshot = None
    if a.check_visible:
        ref_screenshot = capture_screenshot_bytes() if verify_visual else None
        log(f'visible viewport ({verify_visible_game(ref_screenshot):.1%} above luma 24)')
    caps = []
    order, kwarg_name, meta_key, label = _active_trial(a)
    checked_candidate = False
    verified_visual_pair = False
    for i, mode in enumerate(order or 'A' * a.runs):
        log(f'capture {i+1}/{a.runs}' + (f' ({mode})' if order else ''))
        kw = {kwarg_name: mode == 'B'} if order else {}
        expected = 'on' if mode == 'B' else 'off'
        cand_screenshot = None
        if order:
            # The warm-up capture applies the mode before the timed window.
            warmup = capture(3, build=a.build_label, **kw)
            if warmup.get(meta_key) != expected:
                raise Fail('capture', f'{label} mode unconfirmed, evidence at {warmup["path"]}')
            if (kwarg_name == 'gpu_resolve_fast' and (a.check_visible or verify_visual) and
                    not warmup.get('gpu_resolve_mode_persists')):
                raise Fail('visibility', f'GPU resolve mode ends before screen capture, evidence at {warmup["path"]}')
            if mode == 'A' and verify_visual and ref_screenshot is None:
                ref_screenshot = capture_screenshot_bytes()
            if a.check_visible and mode == 'B' and not checked_candidate:
                cand_screenshot = capture_screenshot_bytes() if verify_visual else None
                log(f'candidate viewport ({verify_visible_game(cand_screenshot):.1%} above luma 24)')
                checked_candidate = True
        result = capture(a.duration, a.rotate, a.build_label, a.require_camera, **kw)
        if order and result.get(meta_key) != expected:
            raise Fail('capture', f'{label} mode unconfirmed, evidence at {result["path"]}')
        if kwarg_name == 'gpu_resolve_fast' and mode == 'B':
            stats = dict(item.split(':', 1) for item in result.get('gpu_resolve_stats', '').split(',')
                         if ':' in item)
            if not stats.get('fast_shader', '').isdigit() or int(stats['fast_shader']) == 0:
                raise Fail('capture', f'no fast resolve shader draws, evidence at {result["path"]}')
        if verify_visual and order and mode == 'B' and not verified_visual_pair:
            if cand_screenshot is None:
                cand_screenshot = capture_screenshot_bytes()
            if ref_screenshot is None:
                raise Fail('visual_parity', 'missing baseline reference screenshot')
            parity = visual_parity.compare_images(ref_screenshot, cand_screenshot)
            run_dir = Path(result['path'])
            (run_dir / 'ref_screen.bin').write_bytes(ref_screenshot)
            (run_dir / 'cand_screen.bin').write_bytes(cand_screenshot)
            if visual_parity.Image is not None:
                diff_path = run_dir / 'visual_diff.png'
                visual_parity.save_side_by_side_diff(ref_screenshot, cand_screenshot, diff_path)
                parity['diff_sheet'] = str(diff_path)
            result['visual_parity'] = parity
            verified_visual_pair = True
            log(f"visual parity {parity['status']} mae={parity['viewport']['mae_rgb']} "
                f"gt24={parity['viewport']['pct_pixels_gt_24']}%")
            if not parity['passed']:
                raise Fail('visual_parity', f"regression or blackout, evidence at {run_dir}")
        caps.append(dict(result, mode=mode) if order else result)
        if not engine_alive(): raise Fail('capture', 'engine died between captures')
    return tp, caps


def main():
    global HOST
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default=HOST, help='Switch address for FTP and sys-botbase')
    p.add_argument('--runs', type=int, default=3); p.add_argument('--duration', type=int, default=20)
    p.add_argument('--settle', type=float, default=8); p.add_argument('--retries', type=int, choices=[0], default=0)
    p.add_argument('--rotate', action='store_true', help='slow in-place camera rotation during captures')
    p.add_argument('--label', default='baseline'); p.add_argument('--no-exit', action='store_true')
    p.add_argument('--nro-sha256', '--exit-nro-sha256', dest='nro_sha256',
                   help='Exact SHA-256 of the installed NRO for identity verification')
    p.add_argument('--verify-build', action='store_true',
                   help='Check installed SHA-256 before launch and tag fresh captures with it')
    p.add_argument('--check-visible', action='store_true',
                   help='Check viewport brightness once in memory before timing')
    p.add_argument('--require-camera', action='store_true',
                   help='Require fresh camera snapshots in each timed capture')
    p.add_argument('--barrier-order', choices=('ABBA', 'BAAB'),
                   help='Compare baseline and batched target barriers on the patched NRO')
    p.add_argument('--resolve-swap-order', choices=('ABBA', 'BAAB'),
                   help='Compare baseline and zero-copy resolve swaps on the patched NRO')
    p.add_argument('--gpu-resolve-fast-order', choices=('ABBA', 'BAAB'),
                   help='Compare baseline and fast GPU resolve shaders on the patched NRO')
    p.add_argument('--verify-visual', action='store_true',
                   help='Capture paired screenshots and check visual parity in paired trials')
    a = p.parse_args()
    HOST = a.host
    if sum(bool(x) for x in (a.barrier_order, a.resolve_swap_order, a.gpu_resolve_fast_order)) > 1:
        p.error('--barrier-order, --resolve-swap-order, and --gpu-resolve-fast-order are mutually exclusive')
    order, _, _, _ = _active_trial(a)
    if order:
        if not a.verify_build or not a.nro_sha256 or not a.check_visible or a.rotate:
            p.error('paired trial orders require --verify-build, --nro-sha256 and --check-visible without rotation')
        a.runs = len(order)
    a.nro_sha256 = a.nro_sha256 or APPLET_EXIT_NRO_SHA256
    if len(a.nro_sha256) != 64 or any(c not in '0123456789abcdef' for c in a.nro_sha256):
        p.error('--nro-sha256 must be 64 lowercase hexadecimal digits')
    if a.runs < 1 or not 1 <= a.duration <= 300:
        p.error('--runs must be positive and --duration must be 1 to 300 seconds')
    a.build_label = a.nro_sha256[:12] if a.verify_build else 'autorun'
    try:
        title_id()
        with ftp(20) as f:
            size = f.size('/switch/gta4nx/gta4nx.nro')
            if a.verify_build:
                verify_installed_nro(f, a.nro_sha256)
    except Exception as e:
        print(json.dumps({'status': 'preflight_failed', 'error': str(e)[:200]})); return 2
    failures = []
    for attempt in range(a.retries + 1):
        try:
            tp, caps = scenario(a)
            m = [c['mean_ms'] for c in caps]
            res = {'status': 'capture_complete_exit_pending' if not a.no_exit else 'capture_complete_no_exit', 'label': a.label, 'nro_size': size, 'attempts': attempt + 1, 'teleport': tp,
                   'verified_nro_sha256': a.nro_sha256 if a.verify_build else None,
                   'position': POS, 'rotate': a.rotate, 'duration': a.duration, 'captures': caps, 'mean_ms_of_means': round(statistics.mean(m), 3),
                   'run_to_run_range_ms': round(max(m) - min(m), 3) if len(m) > 1 else None, 'failures_recovered': failures,
                   'note': 'guest publish-entry intervals, not display FPS; multiple runs are needed to estimate within-session spread'}
            OUT.mkdir(parents=True, exist_ok=True)
            report = OUT / f'{a.label}-{time.strftime("%Y%m%dT%H%M%S")}.json'
            report.write_text(json.dumps(res, indent=2))
            if not a.no_exit:
                try:
                    log(f'capture complete; report at {report}; verifying NRO before exit')
                    exit_game(a.nro_sha256)
                    res['status'] = 'capture_complete_exit_unconfirmed'
                except Exception as exc:
                    res['status'] = 'capture_complete_exit_failed'
                    res['exit_error'] = str(exc)
                    log(f'exit failed: {exc}')
                report.write_text(json.dumps(res, indent=2))
            print(json.dumps(res)); return 1 if not a.no_exit else 0
        except Fatal as e:
            log(f'FATAL {e}'); failures.append(str(e)); break
        except Fail as e:
            log(f'FAIL {e}'); failures.append(str(e))
        except Exception as e:
            log(f'ERROR {e!r}'); failures.append(repr(e)[:200])
    print(json.dumps({'status': 'failed', 'label': a.label, 'failures': failures})); return 1


if __name__ == '__main__':
    sys.exit(main())
