import re
import unittest
from pathlib import Path

PATCH = Path(__file__).resolve().parents[2] / 'patches' / 'experiments' / 'v35-opt-gpu-resolve.patch'


class OptGpuResolvePatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = PATCH.read_text(encoding='utf-8')

    def test_patch_exists_and_touches_expected_files(self):
        files = re.findall(r'^diff --git a/(\S+) b/(\S+)$', self.text, re.MULTILINE)
        self.assertEqual(
            [a for a, _ in files],
            [
                'src/graphics/gta4_native/graphics_system.cpp',
                'src/graphics/gta4_native/graphics_system.h',
                'src/graphics/gta4_native/resolve_convert_fast_ps.h',
                'src/ui/switch_perf.cpp',
            ],
        )

    def test_specialized_spirv_shaders_present_and_nonzero(self):
        for symbol in (
            'gta4_native_resolve_copy_1x_ps',
            'gta4_native_resolve_copy_1x_f16_ps',
            'gta4_native_resolve_scale_1x_ps',
            'gta4_native_resolve_scale_1x_hdr_ps',
            'gta4_native_resolve_fast_msaa_ps',
            'gta4_native_resolve_fast_msaa_hdr_ps',
            'gta4_native_materialize_fast_msaa_ps',
        ):
            self.assertIn(f'const uint32_t {symbol}[] = {{', self.text)
        # SPIR-V magic word 0x07230203u in little-endian header.
        self.assertGreaterEqual(self.text.count('0x07230203u'), 7)

    def test_runtime_toggle_defaults_off_and_persists_until_next_request(self):
        self.assertIn('REXCVAR_DEFINE_BOOL(gta4_native_gpu_resolve_opt, false', self.text)
        self.assertIn('BenchExists(base + ".gpu-resolve-fast")', self.text)
        self.assertNotIn('RexSwitchBenchGpuResolveFast(false);', self.text)
        self.assertIn('# gpu_resolve_mode_persists=true\\n', self.text)
        self.assertIn('# gpu_resolve_fast=%s\\n', self.text)
        self.assertIn('# gpu_resolve_stats=fast_shader:', self.text)

    def test_candidate_preserves_materialization_and_alias_image_barriers(self):
        self.assertIn('const bool bypass_materialize_copy = gpu_resolve_opt &&', self.text)
        self.assertNotIn('barriers[1].srcAccessMask =', self.text)
        self.assertNotIn('barriers[1].oldLayout =', self.text)


if __name__ == '__main__':
    unittest.main()
