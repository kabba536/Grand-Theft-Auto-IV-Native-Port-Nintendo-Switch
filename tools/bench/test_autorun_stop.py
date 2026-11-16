import types
import unittest
from pathlib import Path
import tempfile
from unittest.mock import patch
import autorun

class StopTests(unittest.TestCase):
    def test_open_home_primes_pad_and_detaches(self):
        client = object.__new__(autorun.SysBot)
        with patch.object(client, 'query', return_value=b'2.5'), patch.object(client, 'send') as send, patch('sysbot.time.sleep'):
            client.open_home()
        self.assertEqual([call.args[0] for call in send.call_args_list],
                         ['click UNUSED', 'click HOME', 'detachController'])

    def test_open_home_refuses_unknown_button_mapping(self):
        client = object.__new__(autorun.SysBot)
        with patch.object(client, 'query', return_value=b'unknown'), patch.object(client, 'send') as send:
            with self.assertRaises(ValueError):
                client.open_home()
        send.assert_not_called()

    def test_program_running_rejects_ambiguous_response(self):
        client = object.__new__(autorun.SysBot)
        with patch.object(client, 'query', side_effect=[b'1', b'0', b'']) as query:
            self.assertTrue(client.is_program_running(0x03DB163FAA760000))
            self.assertFalse(client.is_program_running(0x03DB163FAA760000))
            with self.assertRaises(ValueError):
                client.is_program_running(0x03DB163FAA760000)
        query.assert_called_with('isProgramRunning 0x03DB163FAA760000')

    def test_clicks_detaches_after_interruption(self):
        class Bot:
            commands = []
            def send(self, command):
                self.commands.append(command)
                if command == 'click HOME': raise RuntimeError('interrupted')
            def close(self): self.closed = True
        b = Bot()
        with patch.object(autorun, 'bot', return_value=b):
            with self.assertRaises(RuntimeError): autorun.clicks('HOME')
        self.assertEqual(b.commands, ['click HOME', 'detachController'])
        self.assertTrue(b.closed)

    def test_unknown_foreground_never_sends_buttons(self):
        with patch.object(autorun, 'engine_alive', return_value=False), patch.object(autorun, 'title_id', return_value='123'), patch.object(autorun, 'clicks') as clicks:
            with self.assertRaises(autorun.Fatal): autorun.launch()
            clicks.assert_not_called()

    def test_readiness_timeout_stops_with_capture_evidence(self):
        with patch.object(autorun, 'ftp'), patch.object(
                autorun.capture_run, 'run', side_effect=TimeoutError('claim unconfirmed; evidence at /tmp/probe')):
            with self.assertRaisesRegex(autorun.Fatal, 'readiness: claim unconfirmed'):
                autorun.ready_probe()

    def test_paired_trial_requires_explicit_hash_before_device_access(self):
        args = ['autorun', '--gpu-resolve-fast-order', 'ABBA', '--verify-build', '--check-visible']
        with patch.object(autorun.sys, 'argv', args), patch.object(autorun, 'title_id') as title, patch.object(
                autorun.sys, 'stderr', new=autorun.io.StringIO()):
            with self.assertRaises(SystemExit) as failure:
                autorun.main()
        self.assertEqual(failure.exception.code, 2)
        title.assert_not_called()

    def test_nro_readback_uses_remaining_deadline(self):
        with patch.object(autorun, 'time') as clock, patch.object(autorun, 'ftp') as ftp:
            connection = ftp.return_value
            connection.timeout = 20
            data = connection.transfercmd.return_value.__enter__.return_value
            clock.monotonic.side_effect = [0, 85, 91]
            data.recv.return_value = b'first chunk'
            with self.assertRaisesRegex(autorun.Fatal, 'readback exceeded'):
                autorun.verify_installed_nro(connection, 'unused')
            data.settimeout.assert_called_once_with(5)

    def test_complete_capture_report_exists_before_exit(self):
        import json
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            def fail_exit(_):
                report = json.loads(next(root.glob('baseline-*.json')).read_text())
                self.assertEqual(report['status'], 'capture_complete_exit_pending')
                raise autorun.Fatal('identity', 'NRO readback timed out')
            with patch.object(autorun, 'OUT', root), patch.object(autorun.sys, 'argv', ['autorun']), patch.object(
                    autorun, 'title_id'), patch.object(autorun, 'ftp') as ftp, patch.object(
                    autorun, 'scenario', return_value=('complete', [{'mean_ms': 50.0}])), patch.object(
                    autorun, 'exit_game', side_effect=fail_exit), patch('builtins.print'):
                ftp.return_value.__enter__.return_value.size.return_value = 123
                self.assertEqual(autorun.main(), 1)
            report = json.loads(next(root.glob('baseline-*.json')).read_text())
            self.assertEqual(report['status'], 'capture_complete_exit_failed')
            self.assertIn('NRO readback timed out', report['exit_error'])

    def test_no_exit_is_respected(self):
        args = types.SimpleNamespace(settle=0, runs=1, duration=30, rotate=False, no_exit=True,
                                     check_visible=False, require_camera=False, build_label='autorun')
        with patch.object(autorun, 'launch'), patch.object(autorun, 'wait_world'), patch.object(autorun, 'teleport'), patch.object(autorun.time, 'sleep'), patch.object(autorun, 'capture', return_value={}), patch.object(autorun, 'engine_alive', return_value=True), patch.object(autorun, 'exit_game') as exit_game:
            autorun.scenario(args)
            exit_game.assert_not_called()

    def test_barrier_trial_checks_mode_and_warms_each_window(self):
        args = types.SimpleNamespace(settle=0, runs=4, duration=20, rotate=False, no_exit=True,
                                     check_visible=False, require_camera=False, build_label='bench',
                                     barrier_order='ABBA')
        def capture(duration, *args, batch_barriers=False, **kwargs):
            return {'duration_s': duration, 'batch_target_barriers': 'on' if batch_barriers else 'off'}
        with patch.object(autorun, 'launch'), patch.object(autorun, 'wait_world'), patch.object(autorun, 'teleport'), patch.object(autorun.time, 'sleep'), patch.object(autorun, 'capture', side_effect=capture) as mocked, patch.object(autorun, 'engine_alive', return_value=True):
            _, result = autorun.scenario(args)
        self.assertEqual([r['mode'] for r in result], list('ABBA'))
        self.assertEqual([r['batch_target_barriers'] for r in result], ['off', 'on', 'on', 'off'])
        self.assertEqual([c.args[0] for c in mocked.call_args_list], [3, 20] * 4)

    def test_resolve_swap_trial_checks_mode_and_warms_each_window(self):
        args = types.SimpleNamespace(settle=0, runs=4, duration=20, rotate=False, no_exit=True,
                                     check_visible=False, require_camera=False, build_label='bench',
                                     resolve_swap_order='BAAB')
        def capture(duration, *args, resolve_swap=False, **kwargs):
            return {'duration_s': duration, 'resolve_swap': 'on' if resolve_swap else 'off'}
        with patch.object(autorun, 'launch'), patch.object(autorun, 'wait_world'), patch.object(autorun, 'teleport'), patch.object(autorun.time, 'sleep'), patch.object(autorun, 'capture', side_effect=capture) as mocked, patch.object(autorun, 'engine_alive', return_value=True):
            _, result = autorun.scenario(args)
        self.assertEqual([r['mode'] for r in result], list('BAAB'))
        self.assertEqual([r['resolve_swap'] for r in result], ['on', 'off', 'off', 'on'])
        self.assertEqual([c.args[0] for c in mocked.call_args_list], [3, 20] * 4)

    def test_gpu_resolve_fast_trial_and_visual_parity(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            args = types.SimpleNamespace(settle=0, runs=4, duration=20, rotate=False, no_exit=True,
                                         check_visible=True, verify_visual=True, require_camera=False,
                                         build_label='bench', gpu_resolve_fast_order='ABBA')
            ppm = b'P6\n10 7\n255\n' + (b'\x80\x80\x80' * 70)
            def capture(duration, *args, gpu_resolve_fast=False, **kwargs):
                return {'path': d, 'duration_s': duration, 'gpu_resolve_mode_persists': True,
                        'gpu_resolve_stats': f'fast_shader:{int(gpu_resolve_fast)}',
                        'gpu_resolve_fast': 'on' if gpu_resolve_fast else 'off'}
            with patch.object(autorun, 'launch'), patch.object(autorun, 'wait_world'), patch.object(autorun, 'teleport'), patch.object(autorun.time, 'sleep'), patch.object(autorun, 'capture_screenshot_bytes', return_value=ppm), patch.object(autorun, '_viewport_bright_fraction', return_value=0.9), patch.object(autorun, 'capture', side_effect=capture) as mocked, patch.object(autorun, 'engine_alive', return_value=True):
                _, result = autorun.scenario(args)
            self.assertEqual([r['mode'] for r in result], list('ABBA'))
            self.assertEqual([r['gpu_resolve_fast'] for r in result], ['off', 'on', 'on', 'off'])
            self.assertEqual(result[1]['visual_parity']['status'], 'parity_ok')
            self.assertEqual([c.args[0] for c in mocked.call_args_list], [3, 20] * 4)

    def test_gpu_resolve_trial_refuses_old_mode_reset(self):
        args = types.SimpleNamespace(settle=0, runs=4, duration=20, rotate=False, no_exit=True,
                                     check_visible=True, require_camera=False, build_label='bench',
                                     gpu_resolve_fast_order='ABBA')
        with patch.object(autorun, 'launch'), patch.object(autorun, 'wait_world'), patch.object(
                autorun, 'teleport'), patch.object(autorun.time, 'sleep'), patch.object(
                autorun, 'verify_visible_game', return_value=0.9), patch.object(
                autorun, 'capture', return_value={'path': '/tmp/capture', 'gpu_resolve_fast': 'off'}) as capture:
            with self.assertRaisesRegex(autorun.Fail, 'mode ends before screen capture'):
                autorun.scenario(args)
            self.assertEqual(capture.call_count, 1)

if __name__ == '__main__': unittest.main()
