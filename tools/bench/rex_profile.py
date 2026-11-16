#!/usr/bin/env python3
"""Summarize the interval reports emitted by switch_perf.cpp in gta4nx-switch.patch."""
import argparse
import json
import re
import sys
from pathlib import Path

NUMBER = r'\d+(?:\.\d+)?'
HEADER = re.compile(
    rf'^==== (?P<seconds>{NUMBER}) s \| modo: (?P<mode>[^|]+?) \| juego (?P<fps>{NUMBER}) fps'
    rf' \| CPU total (?P<cpu>{NUMBER})% \(400% = 4 nucleos\) \| fallos/s: .+ \| '
    r'invitado .+ \| limite de mapeo .+ \| muestras \d+ \| vigilancia: .+ \| samplers: .+$'
)
CLOCK = re.compile(rf'^     relojes: CPU (?P<cpu>{NUMBER}) MHz, GPU (?P<gpu>{NUMBER}) MHz, memoria (?P<mem>{NUMBER}) MHz(?P<unavailable> \(clkrst no disponible\))? \| nucleos del proceso \d+ \(mascara 0x[0-9A-F]+\) \| SoC (?P<soc>{NUMBER}) C, placa (?P<board>{NUMBER}) C(?P<ts_unavailable> \(ts no disponible\))?$')
FENCES = re.compile(rf'^     libnx por segundo \(llamadas y ms dentro\): fences consultadas {NUMBER} \({NUMBER} ms\), esperadas (?P<count>{NUMBER}) \((?P<ms>{NUMBER}) ms\) \| .+$')

class FormatError(ValueError):
    pass


def parse(text):
    if not text.endswith('\n\n'):
        raise FormatError('log is empty or ends with an incomplete report (expected final blank line)')
    lines = text.splitlines()
    if len(lines) < 4 or not re.fullmatch(r'imagen 0x[0-9a-f]+, codigo hasta 0x[0-9a-f]+', lines[0]):
        raise FormatError('unknown log header')
    if lines[2] not in ('Muestreo de pilas: activo (1 ms)', 'Muestreo de pilas: desactivado'):
        raise FormatError('unknown or missing stack sampling mode')
    starts = [i for i, line in enumerate(lines) if line.startswith('====')]
    if not starts or any(line.strip() for line in lines[3:starts[0]]):
        raise FormatError('missing report or unexpected text before first report')
    reports = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(lines)
        block = lines[start:end]
        if not block[-1] == '':
            raise FormatError(f'report {index + 1} has no terminating blank line')
        h = HEADER.fullmatch(block[0])
        if not h:
            raise FormatError(f'report {index + 1}: unknown or incomplete header')
        def one(pattern, label):
            matches = [pattern.fullmatch(line) for line in block if line.startswith('     ' + label)]
            if len(matches) != 1 or not matches[0]:
                raise FormatError(f'report {index + 1}: missing, duplicate or malformed {label}')
            return matches[0]
        clocks = one(CLOCK, 'relojes:')
        fences = one(FENCES, 'libnx por segundo')
        if sum(line.startswith('     audio: ') for line in block) != 1:
            raise FormatError(f'report {index + 1}: missing or duplicate audio line')
        duration, fps, cpu = (float(h[x]) for x in ('seconds', 'fps', 'cpu'))
        if h['mode'] != 'arranque' and duration <= 0:
            raise FormatError(f'report {index + 1}: non-positive interval duration')
        reports.append({'duration_s': duration, 'mode': h['mode'], 'fps': fps, 'cpu_percent': cpu,
                        'fence_waits_per_s': float(fences['count']), 'fence_wait_ms_per_s': float(fences['ms']),
                        'clocks_mhz': None if clocks['unavailable'] else {k: float(clocks[k]) for k in ('cpu', 'gpu', 'mem')},
                        'temperature_c': None if clocks['ts_unavailable'] else {k: float(clocks[k]) for k in ('soc', 'board')}})
    measured = [r for r in reports if r['mode'] != 'arranque']
    if not measured:
        raise FormatError('no measured intervals (startup report is not a benchmark)')
    duration = sum(r['duration_s'] for r in measured)
    return {'stack_sampling': lines[2].split(': ', 1)[1], 'startup_reports_excluded': len(reports) - len(measured),
            'intervals': measured, 'summary': {'interval_count': len(measured), 'duration_s': round(duration, 1),
            'duration_weighted_fps': round(sum(r['fps'] * r['duration_s'] for r in measured) / duration, 2),
            'min_interval_fps': min(r['fps'] for r in measured), 'max_interval_fps': max(r['fps'] for r in measured)},
            'note': 'FPS values are interval averages rounded in the source log; this is not a frame-time percentile or a comparison between runs.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path, help='local rex_perfil.log; read only')
    args = parser.parse_args(argv)
    try:
        result = parse(args.log.read_text(encoding='utf-8'))
    except (OSError, UnicodeError, FormatError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0

if __name__ == '__main__':
    sys.exit(main())
