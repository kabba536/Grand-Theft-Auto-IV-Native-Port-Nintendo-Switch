# Guest publish telemetry

`patches/bench/v35-bench-telemetry.patch` targets the v35 SDK files and is disabled
until a request is placed in the profiler log directory after entering the world.
Create `bench_request.txt` atomically (write elsewhere, then rename into place),
containing one line `RUN_ID DURATION_SECONDS BUILD_ID`. Both identifiers must be
1–48 ASCII letters, digits, `_` or `-`; duration is 1–300 seconds. RUN_ID must
be unique. BUILD_ID is an operator-supplied label, not verified against the binary.
The profiler polls once per second after its initial warmup. It renames a valid
request to `bench_RUN_ID.claimed` before starting. Existing result, claim, or CSV
temporary files prevent reuse. Invalid requests are left in place.

On completion, the profiler writes and syncs a CSV temporary file then renames it
to `bench_RUN_ID.csv`; a separately synced and renamed `bench_RUN_ID.done` is the
completion marker. A claim without a marker denotes an incomplete run; use a fresh
ID for a retry. Sudden power loss and filesystem durability have not been tested.

The CSV records ticks and guest frame IDs at `PublishFrame` entry for non-internal
presents (`present.device != 0`). It does not measure physical display presentation.
One interval requires two timestamps. A fixed 65,536-slot buffer keeps the earliest
samples; rejected counts full-buffer and lock-contention events. The producer never
waits, performs no allocation, IO or system calls; it reads the ARM system counter.
Lock contention during stop can make the reported rejected count approximate.
No frequency settings are changed. The Switch build and console behavior have not
been verified. The normal profiler's periodic reporting still runs during capture.

`telemetry_integration_test.py` extracts the actual implementation from a patched
switch_perf.cpp and tests request, capture, output, marker and duplicate handling on
a host with g++ and Python 3. The separate `telemetry.h` is an earlier standalone
prototype and is not compiled into the patch.
