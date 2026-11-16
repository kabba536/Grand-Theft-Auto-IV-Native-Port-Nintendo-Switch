import hashlib
from pathlib import Path
import tempfile
import unittest

import bench_deploy as bench


class MemoryFTP:
    def __init__(self, files, fail_after=None):
        self.files = files.copy()
        self.fail_after = fail_after
        self.writes = 0
        self.reads = []

    def changed(self):
        self.writes += 1
        if self.writes == self.fail_after:
            raise ConnectionError('interrupted after remote change')

    def retrbinary(self, command, callback, blocksize):
        name = command.removeprefix('RETR ')
        self.reads.append(name)
        callback(self.files[name])

    def storbinary(self, command, stream, blocksize=None):
        self.files[command.removeprefix('STOR ')] = stream.read()
        self.changed()

    def rename(self, old, new):
        if new in self.files:
            raise ValueError('destination exists')
        self.files[new] = self.files.pop(old)
        self.changed()


class BenchDeployTests(unittest.TestCase):
    def test_defer_reads_staged_nro_and_restores_verified_original(self):
        previous, candidate = b'original NRO', b'diagnostic NRO'
        journal = {'id': '3' * 32, 'gpu': None,
                   'previous': hashlib.sha256(previous).hexdigest(),
                   'candidate': hashlib.sha256(candidate).hexdigest()}
        ftp = MemoryFTP({bench.NRO: previous})
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'gta4nx.nro'
            source.write_bytes(candidate)
            bench.deploy(ftp, journal, source, defer_active_readback=True)
        self.assertIn(bench.paths(journal)[1], ftp.reads)
        self.assertNotIn(bench.NRO, ftp.reads)
        self.assertEqual(ftp.files[bench.NRO], candidate)
        bench.restore(ftp, journal, set(ftp.files))
        self.assertEqual(ftp.files[bench.NRO], previous)

    def test_restore_after_any_deployment_write(self):
        previous, candidate, gpu = b'original NRO', b'diagnostic NRO', b'GPU marker'
        initial = {bench.NRO: previous, bench.GPU: gpu}
        def digest(data):
            return hashlib.sha256(data).hexdigest()
        journal = {'id': '1' * 32, 'previous': digest(previous),
                   'candidate': digest(candidate), 'gpu': digest(gpu)}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'gta4nx.nro'
            source.write_bytes(candidate)
            for failure in (*range(1, 7), None):
                with self.subTest(failure=failure):
                    ftp = MemoryFTP(initial, fail_after=failure)
                    if failure is None:
                        bench.deploy(ftp, journal, source)
                    else:
                        with self.assertRaises(ConnectionError):
                            bench.deploy(ftp, journal, source)
                    ftp.fail_after = None
                    bench.restore(ftp, journal, set(ftp.files))
                    self.assertEqual(ftp.files[bench.NRO], previous)
                    self.assertEqual(ftp.files[bench.GPU], gpu)
                    self.assertNotIn(bench.TIMELINE, ftp.files)
                    bench.restore(ftp, journal, set(ftp.files))

    def test_restore_can_resume_after_its_own_renames(self):
        previous, candidate, gpu = b'original NRO', b'diagnostic NRO', b'GPU marker'
        journal = {'id': '2' * 32,
                   'previous': hashlib.sha256(previous).hexdigest(),
                   'candidate': hashlib.sha256(candidate).hexdigest(),
                   'gpu': hashlib.sha256(gpu).hexdigest()}
        backup, _, gpu_backup, _ = bench.paths(journal)
        for failure in range(1, 5):
            with self.subTest(failure=failure):
                ftp = MemoryFTP({backup: previous, bench.NRO: candidate,
                                 gpu_backup: gpu, bench.TIMELINE: bench.timeline_data(journal)},
                                fail_after=failure)
                with self.assertRaises(ConnectionError):
                    bench.restore(ftp, journal, set(ftp.files))
                bench.restore(ftp, journal, set(ftp.files))
                self.assertEqual(ftp.files[bench.NRO], previous)
                self.assertEqual(ftp.files[bench.GPU], gpu)
                self.assertNotIn(bench.TIMELINE, ftp.files)

    def test_existing_timeline_survives_every_interrupted_deploy(self):
        previous, candidate, timeline = b'original NRO', b'diagnostic NRO', b'old marker'
        digest = lambda data: hashlib.sha256(data).hexdigest()
        journal = {'id': '4' * 32, 'previous': digest(previous),
                   'candidate': digest(candidate), 'gpu': None,
                   'timeline': digest(timeline)}
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / 'gta4nx.nro'
            source.write_bytes(candidate)
            for failure in (*range(1, 7), None):
                with self.subTest(failure=failure):
                    ftp = MemoryFTP({bench.NRO: previous, bench.TIMELINE: timeline},
                                    fail_after=failure)
                    if failure is None:
                        bench.deploy(ftp, journal, source)
                    else:
                        with self.assertRaises(ConnectionError):
                            bench.deploy(ftp, journal, source)
                    ftp.fail_after = None
                    bench.restore(ftp, journal, set(ftp.files))

                    self.assertEqual(ftp.files[bench.NRO], previous)
                    self.assertEqual(ftp.files[bench.TIMELINE], timeline)
                    bench.restore(ftp, journal, set(ftp.files))

    def test_existing_timeline_restore_resumes_after_each_rename(self):
        previous, candidate, timeline = b'original NRO', b'diagnostic NRO', b'old marker'
        digest = lambda data: hashlib.sha256(data).hexdigest()
        journal = {'id': '5' * 32, 'previous': digest(previous),
                   'candidate': digest(candidate), 'gpu': None,
                   'timeline': digest(timeline)}
        backup, _, _, _ = bench.paths(journal)
        for failure in range(1, 5):
            with self.subTest(failure=failure):
                ftp = MemoryFTP({backup: previous, bench.NRO: candidate,
                                 bench.TIMELINE: bench.timeline_data(journal),
                                 bench.prior_timeline_path(journal): timeline},
                                fail_after=failure)
                with self.assertRaises(ConnectionError):
                    bench.restore(ftp, journal, set(ftp.files))
                ftp.fail_after = None
                bench.restore(ftp, journal, set(ftp.files))
                self.assertEqual(ftp.files[bench.NRO], previous)
                self.assertEqual(ftp.files[bench.TIMELINE], timeline)
