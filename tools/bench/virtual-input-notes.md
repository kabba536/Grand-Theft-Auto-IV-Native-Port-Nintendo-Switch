# Optional v35 poll-indexed input replay

Apply `patches/bench/v35-bench-virtual-input.patch` at the v35 RexGlue SDK root after
the scene probe patch. It does not touch the graphics translation unit. A new
Switch build is required; host tests do not establish hardware behavior.

The existing `bench_request.txt` syntax remains `RUN_ID DURATION BUILD_ID`.
To opt into replay, first place `bench_RUN_ID.input` in the same profiler log
directory (`/switch/gta4nx/logs/rex/`), then atomically submit that request.
Use a fresh RUN_ID. With no matching `.input`, replay is disabled and normal
physical input is unchanged. A malformed `.input` fails the capture and never
arms virtual input.

Input file syntax (ASCII, one command per line, no comments):

```
start START_X START_Y START_Z START_TOLERANCE_M
step POLLS LEFT_X LEFT_Y RIGHT_X RIGHT_Y END_X END_Y END_Z END_TOLERANCE_M
```

Up to 16 `step` lines are allowed. `POLLS` is 1–120; the total is at most 300.
Axis values are signed XInput int16 values (-32768 to 32767); buttons and
triggers are always neutral. Start tolerance is >0 and ≤5 m; endpoint
tolerances are >0 and ≤10 m. The script has a 15-second monotonic wall limit.
The first eligible GTA input poll validates active gameplay and start position
and sends neutral input. Each step then holds its axes for the named number of
outer GTA input polls; the following poll checks the endpoint. The final
checkpoint poll is neutral. Any invalid context, missing input read, missed
checkpoint, timeout or cancellation fails closed; the current or next poll is
neutral. The profiler also cancels an unfinished script when its timed capture
ends.

The CSV adds `input_script=requested|absent`, `input_script_gate`, status,
error, replayed poll count, checkpoint count, observed `GetState` calls and
maximum position error. A requested script gets `.done` only after the script
completes, both scene reads pass, and start/end player state remains valid.
Otherwise `.failed` is written. The existing `player_state_gate` remains a
preliminary screen/player check. Successful replay does **not** prove a
deterministic or comparable scene: camera, traffic, NPCs, weather and streaming
are not controlled, and outer input polls are not guaranteed simulation frames.
