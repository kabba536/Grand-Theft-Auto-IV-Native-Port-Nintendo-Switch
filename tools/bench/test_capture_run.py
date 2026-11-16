import io
import tempfile
import unittest
from pathlib import Path
from capture_run import run, REMOTE
from test_summarize_capture import PREFIX

class FakeFTP:
 def __init__(self): self.files={};self.calls=[];self.polls=0
 def mlsd(self,p):
  self.polls+=1
  if self.polls==3:
   self.files[REMOTE+'/bench_r1.done']=b'complete\n'
   self.files[REMOTE+'/bench_r1.csv']=(PREFIX.replace('run_id=fixture','run_id=r1').replace('build_id=synthetic','build_id=b1').replace('index,guest_frame,tick', '# player_state_gate=passed\nindex,guest_frame,tick')+'0,1,0\n1,2,20\n2,3,60\n3,4,160\n').encode()
  return [(p.rsplit('/',1)[-1],{}) for p in self.files if p.startswith(REMOTE+'/')]
 def storbinary(self,cmd,fp): self.calls.append('store');self.files[cmd[5:]]=fp.read()
 def retrbinary(self,cmd,cb,blocksize=8192):cb(self.files[cmd[5:]])
 def rename(self,a,b):self.files[b]=self.files.pop(a)

class Tests(unittest.TestCase):
 def test_complete_request_and_capture(self):
  with tempfile.TemporaryDirectory() as d:
   ftp=FakeFTP();folder,result=run(ftp,'r1','b1',1,d,5,sleep=lambda _:None)
   self.assertEqual(result['status'],'valid_capture');self.assertTrue((folder/'capture.csv').exists());self.assertEqual(ftp.calls,['store'])
 def test_collects_only_the_current_runs_timeline(self):
  with tempfile.TemporaryDirectory() as d:
   ftp=FakeFTP()
   ftp.files[REMOTE+'/bench_frame_timeline.txt']=b'old shared file'
   ftp.files[REMOTE+'/bench_r0.timeline']=b'old run'
   listing=ftp.mlsd
   def publish_with_marker(path):
    entries=listing(path)
    if ftp.polls==3:
     ftp.files[REMOTE+'/bench_r1.timeline']=b'fresh run'
     entries.append(('bench_r1.timeline',{}))
    return entries
   ftp.mlsd=publish_with_marker
   folder,result=run(ftp,'r1','b1',1,d,5,sleep=lambda _:None)
   self.assertEqual(Path(result['frame_timeline']),folder/'frame_timeline.txt')
   self.assertEqual((folder/'frame_timeline.txt').read_bytes(),b'fresh run')
 def test_existing_request_is_not_overwritten(self):
  with tempfile.TemporaryDirectory() as d:
   ftp=FakeFTP();ftp.files[REMOTE+'/bench_request.txt']=b'other'
   with self.assertRaisesRegex(ValueError,'already exists'):run(ftp,'r1','b1',1,d,5)
   self.assertEqual(ftp.files[REMOTE+'/bench_request.txt'],b'other');self.assertEqual(ftp.calls,[])
 def test_timeout_is_failure(self):
  with tempfile.TemporaryDirectory() as d:
   ftp=FakeFTP();ftp.polls=-100
   t=iter([0,0,6])
   with self.assertRaisesRegex(TimeoutError,r'\(claim unconfirmed\); r1, evidence at'):
    run(ftp,'r1','b1',1,d,5,sleep=lambda _:None,clock=lambda:next(t))
   self.assertEqual(next(Path(d).glob('guest-capture-*/request.txt')).read_bytes(),b'r1 1 b1\n')

 def test_scene_failure_returns_immediately_and_preserves_evidence(self):
  with tempfile.TemporaryDirectory() as d:
   ftp=FakeFTP()
   def listing(path):
    ftp.polls+=1
    if ftp.polls==3:
     ftp.files[REMOTE+'/bench_r1.failed']=b'player_state_gate_failed\n'
     ftp.files[REMOTE+'/bench_r1.csv']=b'partial trace\n'
    return [(p.rsplit('/',1)[-1],{}) for p in ftp.files if p.startswith(REMOTE+'/')]
   ftp.mlsd=listing
   with self.assertRaisesRegex(RuntimeError,'player state gate failed'):run(ftp,'r1','b1',1,d,5,sleep=lambda _:None)
   evidence=list(Path(d).glob('guest-capture-*/capture.csv'))
   self.assertEqual(evidence[0].read_bytes(),b'partial trace\n')

 def test_resolve_swap_marker_uploaded_when_requested(self):
  with tempfile.TemporaryDirectory() as d:
   ftp=FakeFTP()
   run(ftp,'r1','b1',1,d,5,sleep=lambda _:None,resolve_swap=True)
   self.assertEqual(ftp.files[REMOTE+'/bench_r1.resolve-swap'],b'resolve-swap\n')

 def test_gpu_resolve_fast_marker_uploaded_when_requested(self):
  with tempfile.TemporaryDirectory() as d:
   ftp=FakeFTP()
   run(ftp,'r1','b1',1,d,5,sleep=lambda _:None,gpu_resolve_fast=True)
   self.assertEqual(ftp.files[REMOTE+'/bench_r1.gpu-resolve-fast'],b'gpu-resolve-fast\n')
