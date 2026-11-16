# Optional v35 engine teleport

Apply `patches/bench/v35-bench-teleport.patch` with `patch -p1` at the v35 RexGlue SDK
root. It includes two new source helpers from the existing Quicksave source;
no generated files or build lists change. It can coexist with the scene probe,
virtual input and telemetry patches. This has host stub coverage, not Switch
validation. Do not treat an applied patch or successful build as a safe console
teleport or performance result.

Write one short ASCII line to `teleport_request.txt` in `RexSwitchLogDir()`:

```
example_unique_id -124.5 456.0 20.0
```

The directory is the existing `logs/rex/` next to the launched NRO in normal v35
launches. Use the directory that already contains `bench_*.csv` / `rex_stderr.log`.
Transfer a temporary file then rename it, so the poll never sees a partial line.
Read back the uploaded request. Every ID must be unique; IDs permit only ASCII
letters, digits, `_`, `-`, with 1–48 characters. Coordinates must be finite and
within world bounds (absolute values <=10,000, Z -100..1,500). Invalid input is
left unclaimed and never moves the player. Never reuse a `.claimed` ID.

Use an exact coordinate previously observed while standing safely on the ground
in the same episode. The code does not locate a navigable point, discover a
floor/interior, or select a dense scene. It teleports only the current player
on foot; the existing conservative Quicksave gate must admit free roam: known
phone program, signed-in player, alive, out of vehicles/ragdoll/air, no mission,
activity, wanted level, phone call, menus, fade, multiplayer or active storage.
The original point must already report world collision ready.

Execution runs in the existing game-thread native-aware poll. Native handlers
are captured from the real registrar by their complete names, not copied from
another executable version. Invocation reuses the existing isolated PPC stack
and native context. Only the engine changes entity state:

1. `FREEZE_CHAR_POSITION(handle, true)` retains collision streaming.
2. `REQUEST_COLLISION_AT_POSN(x,y,z)` and `SET_CHAR_COORDINATES(handle,x,y,z)`
   request the destination and use the game's movement/physics path.
3. For at least one second and at most 15 seconds, poll copied position and
   `IS_CHAR_WAITING_FOR_WORLD_COLLISION`. Require distance <=2 m and collision
   ready before unfreezing.
4. If this times out, one engine teleport returns to the copied original point,
   with another bounded 15-second collision wait. There are no automatic repeated
   teleport attempts. Quicksave requests are rejected while this is pending.

The request becomes `teleport_ID.claimed` before any engine mutation.
`teleport_ID.done` means only that the position/collision checks passed and the
unfreeze native was invoked. It does not prove scene determinism, visual
correctness or performance stability. Capture benchmarks only after the scene
settles and passes the existing player-state gate.

`teleport_ID.failed` records gate failure, world changes or a timeout. A successful
rollback reports `timed-out-returned-to-origin`. If even the original point
cannot recover collision, it reports `rollback-collision-timeout-player-held` and
leaves the player frozen to avoid releasing physics over unloaded collision.
Recovery in that case is a title restart without saving; there is no force-release
command. No stale handle is used for cleanup after a world/player change.

This patch performs no direct entity-position writes, invokes no save native,
and changes no game files, clock/voltage/timing settings or sysmodules. Normal
game behavior, including autosave or scripts triggered by a location, remains
possible; do not regard teleporting as a way to isolate those systems. The patch
avoids blocking `LOAD_SCENE`: its internal wait could not be bounded by this poll.
A 15-second timeout is measured only while the guest keeps executing; a stalled
game cannot service the rollback. Destination residency/physics correctness and
native side effects still require a carefully observed first hardware run.

Local checks:

```
docker run --rm -v "$PWD:/workspace:ro" -w /workspace c130418a889d \
  python3 tools/bench/test_teleport.py
```

The test extracts the actual new helpers from the distributable patch, compiles
with C++20 and `-Wall -Wextra -Werror`, and checks native argument encoding,
parser rejection, the gameplay gate, missing natives, save contention, request
deduplication, minimum wait, success, rollback, held timeout and world changes.
The host macOS compiler in this environment has no usable C++ headers; run this
check in the existing development container. No game build or console run is
performed by this test.

The host runner publishes the request and collects the marker with upload and
claim readback verification:

```
python3 tools/bench/teleport_run.py --host HOST --port 5000 \
  --position X Y Z --output-dir /absolute/output/path --timeout 45
```

It generates a unique ID by default, uses `/switch/gta4nx/logs/rex`, and accepts
`--remote-dir` for another verified launch path. FTP credentials come from
`GTA4NX_FTP_USER` / `GTA4NX_FTP_PASSWORD`, matching the capture runners. Run only
one FTP controller at a time. It preserves remote requests/results on timeout
and writes local `request.txt`, `claimed.txt`, `marker.txt`, and `result.json` as
they become available. Exit zero requires the exact success marker and matching
claimed request. A `.failed` marker returns nonzero with its reason.

Five fake FTP checks pass with:

```
python3 -m unittest discover -s tools/bench -p 'test_teleport_run.py' -v
```
