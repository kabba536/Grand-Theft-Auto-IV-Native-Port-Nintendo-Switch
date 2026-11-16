from pathlib import Path
import difflib

sdk = Path('/src/lra35/glue/rexglue-sdk-main')
app_p = sdk / 'gta4-recomp/src/gta4_app.cpp'
gfx_p = sdk / 'src/graphics/gta4_native/graphics_system.cpp'

app_old = app_p.read_text()
app_target = 'REXCVAR_DEFINE_UINT32(gta4_frame_limit, (REX_PLATFORM_ANDROID || REX_PLATFORM_SWITCH) ? 30 : 60, "GTA IV/Graphics/Display",'
app_repl = 'REXCVAR_DEFINE_UINT32(gta4_frame_limit, REX_PLATFORM_ANDROID ? 30 : (REX_PLATFORM_SWITCH ? 0 : 60), "GTA IV/Graphics/Display",'
assert app_old.count(app_target) == 1, 'app target missing'
app_new = app_old.replace(app_target, app_repl, 1)

gfx_old = gfx_p.read_text()
gfx_t1 = 'REXCVAR_DEFINE_BOOL(gta4_native_gpu_resolve_opt, false,'
gfx_r1 = 'REXCVAR_DEFINE_BOOL(gta4_native_gpu_resolve_opt, REX_PLATFORM_SWITCH ? true : false,'
assert gfx_old.count(gfx_t1) == 1, 'gpu resolve opt target missing'
gfx_new = gfx_old.replace(gfx_t1, gfx_r1, 1)

gfx_t2 = '''#if REX_PLATFORM_SWITCH
    const char* log_dir = RexSwitchLogDir();
    std::error_code marker_error;
    if (log_dir && *log_dir && std::filesystem::exists(
            std::filesystem::path(log_dir) / "bench_aligned_ubo.flag", marker_error)) {'''
gfx_r2 = '''#if REX_PLATFORM_SWITCH
    const char* log_dir = RexSwitchLogDir();
    std::error_code marker_error;
    const bool disable_aligned_ubo =
        log_dir && *log_dir &&
        std::filesystem::exists(
            std::filesystem::path(log_dir) / "bench_disable_aligned_ubo.flag", marker_error);
    if (!disable_aligned_ubo) {'''
assert gfx_new.count(gfx_t2) == 1, 'bench_aligned_ubo target missing'
gfx_new = gfx_new.replace(gfx_t2, gfx_r2, 1)

patch = ''.join(
    list(difflib.unified_diff(app_old.splitlines(True), app_new.splitlines(True),
                              fromfile='a/gta4-recomp/src/gta4_app.cpp',
                              tofile='b/gta4-recomp/src/gta4_app.cpp')) +
    list(difflib.unified_diff(gfx_old.splitlines(True), gfx_new.splitlines(True),
                              fromfile='a/src/graphics/gta4_native/graphics_system.cpp',
                              tofile='b/src/graphics/gta4_native/graphics_system.cpp'))
)
Path('/host/patches/experiments/v35-opt-unlock-frame-limit-and-default-ubo-resolve.patch').write_text(patch)
app_p.write_text(app_new)
gfx_p.write_text(gfx_new)
print('Patched OK; patch bytes:', len(patch))
