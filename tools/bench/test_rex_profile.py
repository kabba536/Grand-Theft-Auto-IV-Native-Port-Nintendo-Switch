"""Synthetic examples based on the fprintf format in source/gta4nx-switch.patch."""
import unittest
from rex_profile import FormatError, parse

PREFIX = 'imagen 0x0000000000001234, codigo hasta 0x0000000000005678\n\nMuestreo de pilas: desactivado\n'

def report(seconds='10.0', mode='normal', fps='20.0', clock_extra='', temp_extra=''):
    return (f'==== {seconds} s | modo: {mode} | juego {fps} fps | CPU total 100% (400% = 4 nucleos) | fallos/s: lectura emulada 0 | invitado 1/2 MB (respaldo/mapeado) | limite de mapeo 1/2 MB, proceso 1/2 MB | muestras 0 | vigilancia: sin probar | samplers: 0 nuevos/s, 0 parones/s\n'
            '     audio: synthetic\n'
            f'     relojes: CPU 1020.0 MHz, GPU 307.2 MHz, memoria 1600.0 MHz{clock_extra} | nucleos del proceso 4 (mascara 0xF) | SoC 50.0 C, placa 40.0 C{temp_extra}\n'
            '     libnx por segundo (llamadas y ms dentro): fences consultadas 3 (1.0 ms), esperadas 2 (100.0 ms) | kickoff 0 (0.0 ms)\n\n')

class ParserTests(unittest.TestCase):
    def test_synthetic_weighted_intervals_and_startup(self):
        result = parse(PREFIX + report('0.0', 'arranque', '0.0') + report('10.0', fps='20.0') + report('20.0', fps='10.0'))
        self.assertEqual(result['startup_reports_excluded'], 1)
        self.assertEqual(result['summary']['duration_weighted_fps'], 13.33)
        self.assertEqual(result['intervals'][0]['fence_wait_ms_per_s'], 100.0)

    def test_synthetic_unavailable_sensors(self):
        result = parse(PREFIX + report(clock_extra=' (clkrst no disponible)', temp_extra=' (ts no disponible)'))
        self.assertIsNone(result['intervals'][0]['clocks_mhz'])
        self.assertIsNone(result['intervals'][0]['temperature_c'])

    def test_synthetic_incomplete_and_unknown_logs_are_errors(self):
        for value in ('garbage\n\n', PREFIX + report()[:-1], PREFIX + report().replace('     relojes:', '     unknown:'), PREFIX + report('0.0', 'arranque')):
            with self.subTest(value=value[:60]), self.assertRaises(FormatError):
                parse(value)

if __name__ == '__main__':
    unittest.main()
