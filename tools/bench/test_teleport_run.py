import ftplib
import pathlib
import tempfile
import unittest
import teleport_run

class FTP:
    def __init__(self, result=b'position-and-collision-ready\n', corrupt=False, existing=False):
        self.files = {'teleport_request.txt': b'old'} if existing else {}
        self.result = result; self.corrupt = corrupt; self.writes = 0
    def mlsd(self, remote): return [(name, {}) for name in self.files]
    def storbinary(self, command, stream):
        self.files[command.split('/')[-1]] = stream.read(); self.writes += 1
    def retrbinary(self, command, callback, blocksize=65536):
        name = command.split('/')[-1]
        if name not in self.files: raise ftplib.error_perm('550 missing')
        callback(b'corrupt' if self.corrupt else self.files[name])
    def rename(self, source, target):
        data = self.files.pop(source.split('/')[-1]); self.files[target.split('/')[-1]] = data
        if self.result is not None:
            run_id = data.decode().split()[0]
            self.files['teleport_' + run_id + '.claimed'] = self.files.pop(target.split('/')[-1])
            suffix = '.done' if self.result == b'position-and-collision-ready\n' else '.failed'
            self.files['teleport_' + run_id + suffix] = self.result

class Tests(unittest.TestCase):
    def test_success_and_failure_evidence(self):
        for marker, status in ((b'position-and-collision-ready\n','complete'),
                               (b'free-roam-gate-rejected\n','failed')):
            with tempfile.TemporaryDirectory() as parent:
                folder, report = teleport_run.run(FTP(marker), 'test', [1.,2.,3.], parent)
                self.assertEqual(report['status'], status)
                self.assertEqual((folder/'request.txt').read_bytes(), (folder/'claimed.txt').read_bytes())
                self.assertEqual((folder/'marker.txt').read_bytes(), marker)
    def test_refuses_existing_without_writes(self):
        ftp=FTP(existing=True)
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaises(ValueError):teleport_run.run(ftp,'test',[1,2,3],parent)
        self.assertEqual(ftp.writes,0)
    def test_corruption_does_not_publish(self):
        ftp=FTP(corrupt=True)
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(RuntimeError,'readback mismatch'):
                teleport_run.run(ftp,'test',[1,2,3],parent)
        self.assertNotIn('teleport_request.txt',ftp.files)
    def test_timeout_preserves_command(self):
        ftp=FTP(result=None); now=[0]
        with tempfile.TemporaryDirectory() as parent:
            with self.assertRaisesRegex(RuntimeError,'timed out'):
                teleport_run.run(ftp,'test',[1,2,3],parent,35,
                                 clock=lambda:now[0],sleep=lambda n:now.__setitem__(0,now[0]+n))
            self.assertTrue(list(pathlib.Path(parent).glob('*/result.json')))
        self.assertIn('teleport_request.txt',ftp.files)
    def test_validation_before_network(self):
        for position in ([float('nan'),2,3], [1,2,-101], [10001,2,3]):
            with self.assertRaises(ValueError):teleport_run.validate('test',position,45,'/switch/gta4nx/logs/rex')

if __name__=='__main__':unittest.main()
