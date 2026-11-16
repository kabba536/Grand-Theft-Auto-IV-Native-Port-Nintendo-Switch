> Timer correction (2026-11-14): cached Switch NVK reports timestampPeriod1; hardware tick is625/384ns ([deko3d](https://github.com/devkitPro/deko3d/blob/master/include/deko3d.h#L1292)), corroborated by raw console cadence. Old27ms GPU readings were43–44ms in that earlier regime; CPU intervals are unchanged. Later all3 UBO short capture measured34.297685ms nativeGPU/119clean rows, not repeated FPS evidence. Canonical NVK build metadata fix is prepared; cached NVK was not rebuilt. Later app builds carry a reporting-only workaround for NVK reporting1, avoiding double correction. Current goal is paused; see [HANDOFF](../../docs/agents/HANDOFF.md) and [report](../../docs/agents/optimization-2026-11-14.md).

# Explicit one-shot native GPU profile

The capture tool accepts `--resolve-swap` together with `--gpu-resolve-fast`.
It stages and reads back both per-run markers, requires the guest CSV to confirm
the requested modes, and rejects resume if the requested swap mode changed.
This supports a separate GPU cost comparison; it does not establish visual
correctness or an FPS improvement. Defaults preserve the previous behavior.

`--cpu-reports-only` downloads the CPU-operation CSV, frame CSV and metadata
alongside the normal summary files; it does not disable GPU instrumentation.
Existing reports outside that selection must be archived first. New detailed
requests also refuse existing `.partial` reports, preserving incomplete earlier
captures. Resume keeps the original report selection and never republishes.

`patches/bench/v35-bench-gpu-profile.patch` applies at the v35 SDK root after the
telemetry, scene-probe and virtual-input patches. It changes only
`src/ui/switch_perf.cpp` and `src/ui/windowed_app_main_switch.cpp`; it does
not change the large graphics translation unit, clock controls or sysmodules.
It has not been compiled as a full Switch build or run on the console.

Before launching the newly built executable, create the empty file
`sdmc:/switch/gta4nx/logs/rex/bench_gpu_profile.flag`. Do not combine it with
legacy `perfil_gpu.flag`: the legacy flag takes precedence, preserving the
original timed profile behavior. This setting is sampled at startup. Creating
it in an already running game does not enable diagnostics.

For the chosen unique benchmark RUN_ID, create an empty
`bench_RUN_ID.gpu` in the same log directory **before** atomically publishing
that run's ordinary `bench_request.txt`. Ordinary benchmark requests do not
trigger native profiles. The first eligible explicit request per process is
renamed to `bench_RUN_ID.gpu-requested`, then calls the native capture API.
Later explicit requests remain unconsumed; restart the application for a new
native profile. Invalid or duplicate ordinary benchmark requests do not consume
the GPU request. Never reuse RUN_ID.

The `.gpu-requested` file proves only that the trigger was issued. It is not a
completion marker. The native renderer can reject unsupported timestamps, and
the GPU profile may fail to export. The renderer currently writes
`GetUserFolder()/LibertyRecomp/Diagnostics/native-performance-latest.log` and
`.csv`, overwriting the preceding native result. Archive an existing result
before the run, then require both fresh outputs and inspect their sample,
query-availability and partial/overflow data before accepting a GPU result.
Do not infer native-profile completion from `bench_RUN_ID.done`: that marker
belongs to guest-publish telemetry and its scene gate.

The existing renderer prepares 300 native samples. It may continue after the
ordinary benchmark window, so hold the scenario until export completes; a
short benchmark does not bound the GPU capture. GPU timestamp commands,
query pools, CPU instrumentation and asynchronous SD output add work.
This is pass-level native CPU/GPU profiling, not a trace of all threads or
physical display timing. The fence-pressure automatic trigger is suppressed
only in the new startup mode; without the startup flag existing behavior
is preserved. Invasive `perfil_pilas.flag` stack sampling is separate and
pauses sampled threads; it should not be mixed into baseline captures.

Host helper validation:

    python3 tools/bench/gpu_profile_integration_test.py /path/to/patched/src/ui/switch_perf.cpp

The test compiles the actual helper and setter, checks disabled/ordinary/stale
requests, first explicit trigger and one-shot rejection. `--emit-harness`
prints a standalone C++ harness for a container compiler if the host C++
standard library is unavailable. These checks do not validate Vulkan support,
full linking, SD durability, synchronization overhead or Switch behavior.

## Image observation route

Existing SDK `src/ui/vulkan/vulkan_presenter.cpp` has thread-safe
`CaptureGuestOutput(RawImage&)` and an opt-in periodic pixel probe controlled
by `vulkan_presenter_probe_guest_output_pixels` / `_interval`. The probe logs
image hash, RGB sums and black/rgb-present; neither nonblack pixels nor a hash
proves correct graphics. `src/graphics/trace_dump.cpp` shows PNG encoding with
`stbi_write_png_to_func` after a presenter capture.

A next bounded patch could consume one separate screenshot request from the
profiler thread, call the presenter capture, write one PNG plus dimensions,
frame/provenance and checksum, then atomically publish a completion marker.
The GPU readback allocates staging storage and waits for copy completion, so
capture it outside performance windows. Compare stable scene regions against
repeated reference captures to estimate scene noise before setting thresholds;
keep the original PNGs for visual review. This patch does not implement that
capture route or claim image equivalence.

## Host runner

After the startup-enabled build is already running in stable gameplay:

    python3 tools/bench/capture_gpu_profile.py --host CONSOLE_ADDRESS --diagnostics-dir /EXACT/FTP/Diagnostics --build-label BUILD_ID --output-dir /existing/local/directory --duration 20 --timeout 180

Use the actual diagnostics FTP directory; the runner does not guess it or
relaunch the application. Credentials use the existing `GTA4NX_FTP_USER` and
`GTA4NX_FTP_PASSWORD` environment variables. Only one runner may operate.
It archives previous flat and detail outputs locally before uploading anything,
readback-verifies its unique opt-in and request, then waits within a deadline.
It requires the trigger marker, a valid guest capture, changed latest log/CSV
stable over two polls, 300 samples by default, and matching native capture IDs
in the CSV and detail metadata. It collects all seven detail exports including
the JSON trace. An existing unchanged export cannot pass.

`fresh_export_observed` means an export was observed and preserved; inspect
quality flags, unavailable GPU queries and the trace before accepting timing
results. The export's native capture ID links its own files but does not embed
the benchmark RUN_ID. Attribution therefore relies on exclusive use of this
one-shot process. Flag existence cannot prove that this running executable
sampled it at startup. Failure writes `status=unconfirmed` and evidence to
`result.json`, exits nonzero, and leaves remote requests/partial files intact.
The overall deadline is checked during transfers; a blocked FTP operation may
add up to the configured eight-second socket timeout.
