#!/usr/bin/env python3
"""Collect repeated guest-publish captures; no optimization verdict."""
import argparse
import ftplib
import json
import os
from pathlib import Path
import statistics
import tempfile
import uuid
import capture_run


def suite(ftp, count, duration, build_label, parent, timeout):
    if not 1 <= count <= 30: raise ValueError('count must be in 1..30')
    root=Path(tempfile.mkdtemp(prefix='capture-suite-',dir=parent));os.chmod(root,0o700)
    results=[]
    for i in range(count):
        run_id='r'+uuid.uuid4().hex
        print(f'capture {i+1}/{count}: {run_id}',flush=True)
        try:
            path,result=capture_run.run(ftp,run_id,build_label,duration,root,timeout)
            results.append({'path':str(path),'summary':result})
        except (OSError,ValueError,RuntimeError,EOFError,ftplib.Error) as exc:
            (root/'suite.json').write_text(json.dumps({'status':'incomplete','runs':results,'error':str(exc)},indent=2)+'\n')
            raise RuntimeError(f'suite incomplete, evidence at {root}: {exc}') from exc
    aggregate={'status':'captures_complete','count':len(results),'runs':results,
               'median_of_run_mean_ms':statistics.median(x['summary']['mean_ms'] for x in results),
               'note':'Guest publish intervals only; scene, visual correctness, comparability and optimization are not verified.'}
    (root/'suite.json').write_text(json.dumps(aggregate,indent=2)+'\n')
    return root,aggregate


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--host',required=True);p.add_argument('--port',type=int,default=5000)
    p.add_argument('--count',type=int,default=3);p.add_argument('--duration',type=int,default=20);p.add_argument('--build-label',required=True)
    p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--timeout',type=int,default=90);a=p.parse_args()
    try:
        with ftplib.FTP() as f:
            f.connect(a.host,a.port,timeout=8);f.login(os.environ.get('GTA4NX_FTP_USER','anonymous'),os.environ.get('GTA4NX_FTP_PASSWORD',''))
            root,res=suite(f,a.count,a.duration,a.build_label,a.output_dir,a.timeout)
        print(json.dumps({'status':res['status'],'path':str(root),'count':res['count'],'median_of_run_mean_ms':res['median_of_run_mean_ms'],'note':res['note']}));return 0
    except (OSError,ValueError,RuntimeError,EOFError,ftplib.Error) as exc:
        print(json.dumps({'status':'suite_failed','error':str(exc)}));return 1
if __name__=='__main__':raise SystemExit(main())
