# rex_perfil.log summary

Current hardware state and paused work: [HANDOFF](../../docs/agents/HANDOFF.md), [results](../../docs/agents/optimization-2026-11-14.md), [PGO](../../docs/agents/pgo-comparison-2026-11-13.md). Do not resume unattended runs while the user goal is paused.

The latest matched sidewalk protocol uses FIRST20s per independent launch at(900.78,−521.38,15.04), owned/readback all3 UBO marker and fastresolveB; a changed point needs a new control. NPC movement failures are excluded, not relaxed. The last memo run failed6.014294m movement and exited normally. A prior descriptor-only candidate stalled both capture and cooperative exit; it is quarantined. Never issue concurrent UI input during runner cleanup. After an exit failure stop retries, inspect fresh state, preserve evidence and pending requests before any next launch.

`--cpu-reports-only` limits report downloads, not GPU instrumentation. Detailed capture refuses existing partial reports. Host tests and instrumented elapsed scopes are not ordinary hardware FPS evidence. The benchmark feature modes are not the preserved normal TOML defaults.

Read an existing local log without changing it or connecting to the console:

    python3 tools/bench/rex_profile.py /path/to/rex_perfil.log > report.json
    python3 -m unittest discover -s tools/bench -v

The JSON contains each measured interval's duration, mode, FPS, total CPU, fence waits, clocks and temperatures, plus duration-weighted FPS and interval extrema. FPS and durations are already rounded by the game; the weighted result is approximate. Extrema are interval averages, not individual frame rates or frame-time percentiles. `arranque` is a very short initialization report and is excluded. Unavailable clock and temperature services are represented as `null`, not zero.

The parser targets the format emitted by `switch_perf.cpp` in `source/gta4nx-switch.patch`. It rejects missing required fields, unrecognized headers and reports lacking a final blank line. Other builds or truncated logs may need a different parser. It does not infer a performance improvement from a single run; meaningful comparison requires repeated runs under comparable conditions.

Tests use **synthetic** examples derived from the source format; they are not console measurements.

To collect one existing log over FTP and analyze it in one step, provide the known host, exact remote path and an existing local output parent:

    python3 tools/bench/collect_profile.py --host CONSOLE_ADDRESS --remote /exact/path/to/rex_perfil.log --output-dir /existing/local/directory

If needed, provide the password via `GTA4NX_FTP_PASSWORD` without saving it in shell history; `GTA4NX_FTP_USER` or `--user` selects the username. Every invocation creates a unique subdirectory containing the original log, collection metadata (including SHA-256), and `report.json`. If analysis fails, the original log and metadata remain in that directory and the command exits nonzero. FTP transport itself does not encrypt credentials or data. Use this only over a trusted network.

## Guest-publish capture on Switch

With the instrumented no-clock build running and the player stationary in active gameplay, an existing output directory, and sys-ftp already running:

    python3 tools/bench/capture_suite.py --host CONSOLE_ADDRESS --count 3 --duration 20 --build-label BUILD_ID --output-dir /existing/local/directory

The tool makes unique requests, waits with a deadline, retrieves raw CSV and markers, and creates `suite.json`; it stops on failure. The player gate checks only the start and end state. Results measure guest publish-entry intervals, not display presentation, and do not establish equivalent visual quality or scene reproducibility. `BUILD_ID` is a host-supplied label, not proof of the executable's identity. The console must already be running the instrumented build; this command does not start or deploy it.

`autorun.py` saves a completed capture report before cooperative exit. After an exit failure, the report includes `capture_complete_exit_failed` and the failure reason. On a capture timeout or lost FTP connection after publishing the request, keep the reported local `request.txt` and match its ID against the console's `.claimed` and result files after recovery.

## Stage and restore a timeline build

From a verified HOME state with one console operator, use a new journal path:

    python3 tools/bench/bench_deploy.py deploy --host CONSOLE_ADDRESS --journal deploy.json --nro /path/to/gta4nx.nro --candidate-sha256 CANDIDATE_SHA --previous-sha256 INSTALLED_SHA

The helper writes the local journal before staging the binary. It verifies the installed baseline, preserves it, enables the timeline and temporarily archives the explicit GPU profiler flag if present. An existing timeline marker is hashed and archived separately, then restored with its original bytes. Run the existing `autorun.py --verify-build --check-visible` scenario with the candidate SHA. After confirming that the game has closed, restore the prior NRO and flags using the same journal:

    python3 tools/bench/bench_deploy.py restore --host CONSOLE_ADDRESS --journal deploy.json

The restore command can also recover a partially completed deployment. It checks expected hashes and stops on ambiguous ownership. If a failed run leaves the application open, follow the verified HOME procedure in the handoff before restoring.

When immediately chaining a single operator's `deploy` and `autorun --verify-build`, `deploy --defer-active-readback` removes one 84 MiB FTP read. Deployment still verifies the staged upload. `autorun` reads and hashes the active path before launch. The deploy result is `deploy_staged_verified` until that preflight succeeds.

For a build with `v35-bench-compact-gpu-profile.patch`, use `--keep-gpu-marker` during deployment to retain the existing explicit GPU startup flag. After the ordinary timeline capture has passed, keep the game in the same scene and request one compact GPU capture:

    python3 tools/bench/capture_gpu_profile.py --host CONSOLE_ADDRESS --compact --build-label BUILD_ID --output-dir /existing/local/directory --duration 20 --timeout 100

The compact mode captures 120 native frames once per process and publishes only the run-specific `bench_<run>.gpu.csv`. It checks the request claim, player-state gate, row count and capture identity. GPU timestamps add instrumentation overhead, so use the preceding timeline capture for unprofiled frame intervals.

The optional `v35-bench-slot-submission-timeline.patch` extends the timeline with the slot and native submission IDs. The analyzer joins the wait to the actual earlier submit and reports its age at the start of the slot wait. The tracker snapshots report completions already observed by the CPU, without polling the device. With one effective slot, the secondary wait ID is exported separately and the fence duration still covers both waits.
