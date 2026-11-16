import json
import ftplib
from pathlib import Path
import tempfile
import unittest

import capture_gpu_profile as gpu
from capture_run import REMOTE
from test_summarize_capture import PREFIX

DIAG = '/synthetic/Diagnostics'


class FTP:
    def __init__(self, fresh=True, trigger=True, failed=False):
        self.files = {REMOTE + '/bench_gpu_profile.flag': b'',
                      DIAG + '/' + gpu.REPORTS[0]: b'old log\n',
                      DIAG + '/' + gpu.REPORTS[1]: b'old csv\n'}
        self.fresh, self.trigger, self.failed = fresh, trigger, failed
        self.stores = []
    def mlsd(self, path):
        return [(key[len(path) + 1:], {}) for key in self.files
                if key.startswith(path + '/') and '/' not in key[len(path) + 1:]]
    def retrbinary(self, cmd, callback, blocksize=65536):
        callback(self.files[cmd[5:]])
    def storbinary(self, cmd, stream):
        self.stores.append(cmd[5:])
        self.files[cmd[5:]] = stream.read()
    def rename(self, source, target):
        self.files[target] = self.files.pop(source)
        if target == REMOTE + '/bench_request.txt':
            run, duration, build = self.files.pop(target).decode().split()
            base = REMOTE + '/bench_' + run
            if self.trigger:
                self.files[base + '.gpu-requested'] = self.files.pop(base + '.gpu')
            if self.failed:
                self.files[base + '.failed'] = b'failed\n'
                return
            self.files[base + '.done'] = b'complete\n'
            prefix = PREFIX.replace('run_id=fixture', 'run_id=' + run).replace('build_id=synthetic', 'build_id=' + build)
            if base + '.resolve-swap' in self.files:
                prefix = prefix.replace('index,guest_frame,tick', '# resolve_swap=on\nindex,guest_frame,tick')
            self.files[base + '.csv'] = (prefix.replace('index,guest_frame,tick', '# player_state_gate=passed\nindex,guest_frame,tick') + '0,1,0\n1,2,20\n2,3,60\n3,4,160\n').encode()
            if self.fresh:
                self.files[DIAG + '/' + gpu.REPORTS[0]] = b'gta4-native-perf-sample frame=1 domain=meta timestamp-period-ns=1 host-frequency=10\n'
                for name in gpu.DETAILS:
                    self.files[DIAG + '/' + name] = b'{}\n'
                self.files[DIAG + '/native-performance-meta.json'] = b'{"capture_id":99}\n'
                self.files[DIAG + '/' + gpu.REPORTS[1]] = b'frame,capture_index,gpu_frame_ms,flags,capture_id\n1,0,12.3,0,99\n'


class Tests(unittest.TestCase):
    def test_existing_partial_reports_are_not_overwritten(self):
        for cpu_only in (False, True):
            with self.subTest(cpu_only=cpu_only), tempfile.TemporaryDirectory() as d:
                ftp = FTP()
                path = DIAG + '/native-performance-cpu.csv.partial'
                ftp.files[path] = b'incomplete earlier capture'
                with self.assertRaisesRegex(RuntimeError, 'archive existing partial'):
                    self.execute(ftp, d, cpu_reports_only=cpu_only)
                self.assertEqual(ftp.stores, [])
                self.assertEqual(ftp.files[path], b'incomplete earlier capture')

    def test_cpu_reports_only_protects_existing_unselected_reports(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            path = DIAG + '/native-performance-trace.json'
            ftp.files[path] = b'old private trace'
            with self.assertRaisesRegex(RuntimeError, 'archive existing unselected'):
                self.execute(ftp, d, cpu_reports_only=True)
            self.assertEqual(ftp.stores, [])
            self.assertEqual(ftp.files[path], b'old private trace')

    def test_cpu_reports_only_avoids_unrequested_large_files(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            original = ftp.retrbinary
            def read(command, callback, blocksize=65536):
                self.assertFalse(any(command.endswith('/' + name)
                                     for name in set(gpu.DETAILS) - set(gpu.CPU_DETAILS)))
                return original(command, callback, blocksize)
            ftp.retrbinary = read
            _, result = self.execute(ftp, d, cpu_reports_only=True)
            self.assertEqual(result['status'], 'fresh_export_observed')
            self.assertEqual(set(result['details']), set(gpu.CPU_DETAILS))

    def test_cpu_reports_only_rejects_compact_without_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            with self.assertRaisesRegex(ValueError, 'requires a detailed capture'):
                self.execute(ftp, d, compact=True, cpu_reports_only=True)
            self.assertEqual(ftp.stores, [])

    def test_resume_rejects_changed_cpu_report_selection(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            folder, _ = self.execute(ftp, d, cpu_reports_only=True)
            stores = list(ftp.stores)
            with self.assertRaisesRegex(ValueError, 'matching run/build/path'):
                self.execute(ftp, d, resume=folder)
            self.assertEqual(ftp.stores, stores)

    def test_resolve_swap_marker_and_guest_confirmation(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            _, result = self.execute(ftp, d, resolve_swap=True)
            self.assertTrue(result['resolve_swap'])
            self.assertEqual(result['guest_capture']['resolve_swap'], 'on')
            self.assertEqual(ftp.files[REMOTE + '/bench_r1.resolve-swap'], b'resolve-swap\n')

    def test_resolve_swap_without_guest_confirmation_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            original = ftp.rename
            def rename(source, target):
                original(source, target)
                if target == REMOTE + '/bench_request.txt':
                    path = REMOTE + '/bench_r1.csv'
                    ftp.files[path] = ftp.files[path].replace(b'# resolve_swap=on\n', b'')
            ftp.rename = rename
            with self.assertRaisesRegex(RuntimeError, 'resolve_swap mode not confirmed'):
                self.execute(ftp, d, resolve_swap=True)

    def test_resume_rejects_changed_resolve_swap_without_uploads(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            folder, _ = self.execute(ftp, d, resolve_swap=True)
            stores = list(ftp.stores)
            with self.assertRaisesRegex(ValueError, 'matching run/build/path'):
                self.execute(ftp, d, resume=folder)
            self.assertEqual(ftp.stores, stores)

    def test_compact_regions_require_matching_capture_and_complete_rows(self):
        samples = [dict(capture_id='99', frame='1', capture_sequence='7')]
        content = (b'capture_id,frame,sequence,range,vertex_shader,pixel_shader,raw_ticks,reported_gpu_ms\n'
                   b'99,1,7,retail-warp-shadow,ab,cd,100,0.0001\n')
        self.assertEqual(gpu.validate_compact_regions(content, samples), 1)
        with self.assertRaisesRegex(ValueError, 'identity'):
            gpu.validate_compact_regions(content.replace(b'99,1,7', b'98,1,7'), samples)
        with self.assertRaisesRegex(ValueError, 'truncated'):
            gpu.validate_compact_regions(content.rstrip(), samples)
        with self.assertRaisesRegex(ValueError, 'timing'):
            gpu.validate_compact_regions(content.replace(b'0.0001', b'nan'), samples)

    def execute(self, ftp, folder, **kwargs):
        ticks = [0.0]
        return gpu.run(ftp, DIAG, 'b1', 1, folder, timeout=5, run_id='r1',
                       expected_samples=1, clock=lambda: ticks[0],
                       sleep=lambda seconds: ticks.__setitem__(0, ticks[0] + seconds), **kwargs)
    def test_archives_old_reports_and_observes_fresh_export(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            folder, result = self.execute(ftp, d)
            self.assertEqual(result['status'], 'fresh_export_observed')
            self.assertEqual(result['native_samples'], 1)
            self.assertEqual((folder / 'previous' / gpu.REPORTS[1]).read_bytes(), b'old csv\n')
            self.assertEqual(len(ftp.stores), 2)
            self.assertEqual(len(result['details']), 7)
            self.assertTrue((folder / 'capture.csv').exists())
    def test_compact_capture_requires_its_own_claim_and_csv(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP(fresh=False, trigger=False)
            original = ftp.rename
            def rename(source, target):
                original(source, target)
                if target == REMOTE + '/bench_request.txt':
                    base = REMOTE + '/bench_r1'
                    ftp.files[base + '.gpu-flat-requested'] = ftp.files.pop(base + '.gpu-flat')
                    ftp.files[base + '.gpu.csv'] = (
                        b'frame,capture_index,gpu_frame_ms,flags,capture_id\n1,0,12.3,0,99\n')
            ftp.rename = rename
            folder, result = self.execute(ftp, d, compact=True)
            self.assertEqual(result['status'], 'fresh_export_observed')
            self.assertEqual(result['capture_id'], '99')
            self.assertEqual(set(result['fresh']), {'bench_r1.gpu.csv'})
            self.assertTrue((folder / 'bench_r1.gpu.csv').exists())
    def test_stale_export_is_never_success(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, 'no confirmed fresh'):
                self.execute(FTP(fresh=False), d)
            result = json.loads(next(Path(d).glob('*/result.json')).read_text())
            self.assertEqual(result['status'], 'unconfirmed')
            self.assertEqual(result['fresh'], {})
    def test_fresh_files_without_trigger_are_unconfirmed(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, 'no confirmed fresh'):
                self.execute(FTP(trigger=False), d)
    def test_existing_request_prevents_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            ftp.files[REMOTE + '/bench_request.txt'] = b'other'
            with self.assertRaisesRegex(RuntimeError, 'already exists'):
                self.execute(ftp, d)
            self.assertEqual(ftp.stores, [])
    def test_legacy_mode_prevents_mutation(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            ftp.files[REMOTE + '/perfil_gpu.flag'] = b''
            with self.assertRaisesRegex(RuntimeError, 'no legacy'):
                self.execute(ftp, d)
            self.assertEqual(ftp.stores, [])
    def test_missing_details_fail_closed(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            original = ftp.rename
            def rename(source, target):
                original(source, target)
                if target.endswith('/bench_request.txt'):
                    ftp.files.pop(DIAG + '/native-performance-trace.json')
            ftp.rename = rename
            with self.assertRaisesRegex(RuntimeError, 'detail bundle missing'):
                self.execute(ftp, d)
    def test_detail_identity_mismatch_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            original = ftp.rename
            def rename(source, target):
                original(source, target)
                if target.endswith('/bench_request.txt'):
                    ftp.files[DIAG + '/native-performance-meta.json'] = b'{"capture_id":100}\n'
            ftp.rename = rename
            with self.assertRaisesRegex(RuntimeError, 'capture identity mismatch'):
                self.execute(ftp, d)
    def test_previous_report_is_archived_before_first_upload(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP()
            original = ftp.storbinary
            def upload(command, stream):
                self.assertEqual(next(Path(d).glob('*/previous/' + gpu.REPORTS[0])).read_bytes(), b'old log\n')
                original(command, stream)
            ftp.storbinary = upload
            self.execute(ftp, d)
    def test_guest_gate_failure_keeps_unconfirmed_status(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, 'benchmark gate failed'):
                self.execute(FTP(failed=True), d)
            self.assertTrue(next(Path(d).glob('*/failure.txt')).exists())

    def busy_ftp(self, message='550 Device or resource busy', failures=1):
        ftp = FTP()
        original = ftp.retrbinary
        remaining = [failures]
        def read(command, callback, blocksize=65536):
            if (REMOTE + '/bench_r1.done' in ftp.files and DIAG in command
                    and remaining[0]):
                remaining[0] -= 1
                raise ftplib.error_perm(message)
            original(command, callback, blocksize)
        ftp.retrbinary = read
        return ftp

    def test_busy_export_retries_then_succeeds(self):
        with tempfile.TemporaryDirectory() as d:
            _, result = self.execute(self.busy_ftp(), d)
            self.assertEqual(result['status'], 'fresh_export_observed')
            self.assertIn('Device or resource busy', result['export_retry'])

    def test_busy_export_expires_and_resume_does_not_publish(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = self.busy_ftp(failures=3)
            with self.assertRaisesRegex(RuntimeError, 'no confirmed fresh'):
                self.execute(ftp, d)
            folder = next(Path(d).glob('gpu-profile-*'))
            stores = list(ftp.stores)
            resumed_folder, result = self.execute(ftp, d, resume=folder)
            self.assertEqual(resumed_folder, folder)
            self.assertEqual(result['status'], 'fresh_export_observed')
            self.assertEqual(ftp.stores, stores)

    def test_other_550_is_fatal(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaisesRegex(RuntimeError, '550 Permission denied'):
                self.execute(self.busy_ftp('550 Permission denied'), d)

    def test_resume_stale_export_is_never_success(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP(fresh=False)
            with self.assertRaises(RuntimeError):
                self.execute(ftp, d)
            folder = next(Path(d).glob('gpu-profile-*'))
            with self.assertRaisesRegex(RuntimeError, 'no confirmed fresh'):
                self.execute(ftp, d, resume=folder)
            self.assertEqual(len(ftp.stores), 2)

    def test_resume_rejects_unpublished_or_damaged_baseline(self):
        for damage in ('unpublished', 'missing', 'corrupt', 'identity'):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as d:
                ftp = self.busy_ftp(failures=3)
                with self.assertRaises(RuntimeError):
                    self.execute(ftp, d)
                folder = next(Path(d).glob('gpu-profile-*'))
                path = folder / 'result.json'
                report = json.loads(path.read_text())
                if damage == 'unpublished':
                    report['request_published'] = False
                elif damage == 'missing':
                    report['previous'].pop(gpu.REPORTS[0])
                elif damage == 'identity':
                    report['build_label'] = 'other'
                else:
                    (folder / 'previous' / gpu.REPORTS[0]).write_bytes(b'corrupt')
                path.write_text(json.dumps(report))
                with self.assertRaises(ValueError):
                    self.execute(ftp, d, resume=folder)
                self.assertEqual(len(ftp.stores), 2)

    def test_native_validation_still_rejects_bad_exports(self):
        for damage, message in (
                ('truncated', 'truncated'), ('schema', 'schema missing'),
                ('samples', 'missing expected samples'), ('log', 'sample metadata')):
            with self.subTest(damage=damage), tempfile.TemporaryDirectory() as d:
                ftp = FTP()
                original = ftp.rename
                def rename(source, target):
                    original(source, target)
                    if target.endswith('/bench_request.txt'):
                        path = DIAG + '/' + gpu.REPORTS[1]
                        if damage == 'truncated':
                            ftp.files[path] = ftp.files[path].rstrip(b'\n')
                        elif damage == 'schema':
                            ftp.files[path] = ftp.files[path].replace(b'gpu_frame_ms', b'other')
                        elif damage == 'samples':
                            ftp.files[path] = ftp.files[path].split(b'\n')[0] + b'\n'
                        else:
                            ftp.files[DIAG + '/' + gpu.REPORTS[0]] = b'new log without metadata\n'
                ftp.rename = rename
                with self.assertRaisesRegex(RuntimeError, message):
                    self.execute(ftp, d)

    def test_compact_fast_resolve_and_swap_are_confirmed_together(self):
        with tempfile.TemporaryDirectory() as d:
            ftp = FTP(trigger=False)
            original = ftp.rename
            def rename(source, target):
                original(source, target)
                if target.endswith('/bench_request.txt'):
                    csv_path = REMOTE + '/bench_r1.csv'
                    ftp.files[csv_path] = ftp.files[csv_path].replace(
                        b'# player_state_gate=passed\n',
                        b'# player_state_gate=passed\n# gpu_resolve_fast=on\n')
                    ftp.files[REMOTE + '/bench_r1.gpu.csv'] = (
                        b'frame,capture_index,gpu_frame_ms,flags,capture_id\n1,0,12.3,0,99\n')
                    ftp.files[REMOTE + '/bench_r1.gpu-flat-requested'] = ftp.files.pop(REMOTE + '/bench_r1.gpu-flat')
            ftp.rename = rename
            _, result = gpu.run(ftp, REMOTE, 'b1', 1, d, timeout=5, run_id='r1',
                                expected_samples=1, clock=lambda: 0.0, sleep=lambda _: None,
                                compact=True, gpu_resolve_fast=True, resolve_swap=True)
            self.assertEqual(result['status'], 'fresh_export_observed')
            self.assertEqual(ftp.files[REMOTE + '/bench_r1.gpu-resolve-fast'], b'gpu-resolve-fast\n')
            self.assertEqual(result['guest_capture']['resolve_swap'], 'on')


if __name__ == '__main__':
    unittest.main()
