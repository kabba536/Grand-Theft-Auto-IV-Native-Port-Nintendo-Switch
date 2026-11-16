# Optional v35 player state gate

Apply `patches/bench/v35-bench-scene-probe.patch` at the v35 RexGlue SDK root **after**
`patches/bench/v35-bench-telemetry.patch`. It adds the scene reader to GTA's outer
input poll and a bridge to the existing `bench_request.txt` capture. It does
not change the graphics translation unit, input, game saves, settings, clocks,
or the runtime image until a new build is made.

The request format remains `RUN_ID DURATION_SECONDS BUILD_ID`. At the start and
end of capture, the profiler requests one copied scene observation. Each
observation contains an input poll epoch, game input time, screen, episode,
player generation, context flags and player position. It reads position with
the same matrix or inline selection as the existing Sony observation, but does
not require a Sony controller. No guest data is written. When there is no
request, the guest poll performs only one atomic load.

The CSV adds `player_state_gate=passed|failed`, start/end statuses and flags,
and player endpoint positions and displacement. `bench_RUN_ID.done` appears
only when both reads succeeded, both showed active gameplay outside loading,
cutscene, frontend, map and phone, the episode and player generation matched,
the input poll epoch and game input time advanced, and endpoint displacement
was at most 0.5 m. Otherwise `bench_RUN_ID.failed` appears, with details in
the CSV. A missing result marker or a `.failed` marker is a failed capture.
The end observation waits up to two profiler seconds for another guest input
poll; a stopped game therefore fails closed. Request IDs must be unique so
existing artifacts cannot be reused.

The gate is preliminary. It does not establish scene comparability or
determinism: camera, NPCs, traffic, weather, streaming and intermediate player
motion are not checked. Input poll epoch and game input time are not a fixed
simulation frame count. On 2026-11-12, one capture and a three-run suite passed this gate on the Switch in a stationary scene. Those runs validate this limited gate, not scene determinism or visual correctness.

Host checks: `test_scene_probe.py` compiles and exercises the mailbox from the
actual patch; `scene_probe_integration_test.py` compiles the patched `BenchPoll`
and tests stable gameplay, cutscene, menu, missing poll and endpoint movement.
