#!/usr/bin/env python3
"""Collect one existing profile over FTP and summarize it locally."""
import argparse
import ftplib
import json
import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'device'))
import collect
import rex_profile


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--host', required=True, help='known FTP host; no discovery')
    parser.add_argument('--port', type=int, default=5000)
    parser.add_argument('--user', default=os.environ.get('GTA4NX_FTP_USER', 'anonymous'))
    parser.add_argument('--remote', required=True, help='exact absolute remote path to rex_perfil.log')
    parser.add_argument('--output-dir', type=Path, required=True, help='existing local parent for a new unique directory')
    parser.add_argument('--timeout', type=float, default=10)
    parser.add_argument('--max-bytes', type=int, default=16 * 1024 * 1024)
    args = parser.parse_args(argv)
    try:
        folder = Path(tempfile.mkdtemp(prefix='rex-profile-', dir=args.output_dir)).resolve()
    except OSError as exc:
        print(f'error creating output directory: {exc}', file=sys.stderr)
        return 1
    log = folder / 'rex_perfil.log'
    print(f'output directory: {folder}', file=sys.stderr)
    try:
        metadata = collect.collect(args.host, args.port, args.user, os.environ.get('GTA4NX_FTP_PASSWORD', ''),
                                   args.remote, log, args.timeout, args.max_bytes)
        with (folder / 'collection.json').open('x', encoding='utf-8') as stream:
            json.dump(metadata, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        summary = rex_profile.parse(log.read_text(encoding='utf-8'))
        with (folder / 'report.json').open('x', encoding='utf-8') as stream:
            json.dump(summary, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
    except (OSError, ValueError, UnicodeError, EOFError, ftplib.Error, collect.LimitExceeded) as exc:
        print(f'error: {exc}; output directory: {folder}', file=sys.stderr)
        return 1
    print(json.dumps({'status': 'collected_and_analyzed', 'output_dir': str(folder),
                      'log': str(log), 'report': str(folder / 'report.json')}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    sys.exit(main())
