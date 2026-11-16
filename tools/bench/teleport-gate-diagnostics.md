# Teleport free-roam denial diagnostics

`free-roam-gate-rejected` in the original v35 teleport patch loses the returned
`Denial` value. Even preserving `ReasonKey(denial)` would be insufficient:
`kUnavailable` combines an unrecognized or uninstalled phone integration, absent player
or sign-in state, native invocation failure and a zero player handle. `kActivity`
combines minigame, dead, ragdoll and airborne conditions. A captured generic
marker cannot establish which condition actually rejected that hardware run.

Apply `patches/bench/v35-bench-teleport-gate-diagnostics.patch` after
`patches/bench/v35-bench-teleport.patch`, in a disposable SDK copy. It is based on the
read-only `gta4nx_v35_scratch_20261111_2028` sources. The verifier pins the two
modified preimages by SHA-256 and refuses drift. No existing build volume or
console files are changed by verification.

The patch adds an optional diagnostic output to the same `Eligibility`
evaluation. The policy, Boolean tests, native invocations and their ordering
remain unchanged. The returned denial is preserved. It does not rerun the gate,
invoke a save, modify native registration, or bypass an unavailable check.
Only failed teleport markers gain a second line, for example:

```
free-roam-gate-rejected
gate-detail=phone-program-not-installed
```

`gate-detail` is the first observed blocking fact in the existing check order,
not an inventory of all blockers. Initial checks distinguish disabled quicksave,
phone-program-not-installed, player-memory-not-ready and not-signed-in. Later
checks distinguish individual failed native invocations, multiplayer, mission,
minigame, storage, autosave, system UI, frontend, phone call, vehicle, wanted,
control, fade, zero player handle and the dead/ragdoll/airborne predicates.
`invoke-NAME` means that `Invoke` returned no value for that native; it does not
claim whether registrar capture, dispatcher lookup or PPC stack validation was
the underlying problem. `phone-program-not-installed` means the current episode
has no installed recognized phone program; it alone does not distinguish an
unknown script fingerprint from a script not yet loaded or another install
failure. Existing `rex_stderr.log` quicksave warnings can help resolve that.
No user ID, memory address or game data is written to the marker.

The existing `teleport_run.py` collects the complete failed marker in
`marker.txt` and its JSON `reason`; its 256-byte read cap is sufficient for all
static diagnostic strings. Success marker semantics stay unchanged.

Reproduce local checks with pinned image and read-only inputs:

```sh
docker run --rm \
  --mount type=volume,src=gta4nx_v35_scratch_20261111_2028,dst=/src,readonly \
  --mount "type=bind,src=$PWD,dst=/repo,readonly" \
  --entrypoint python3 \
  ghcr.io/autorunhq/switch-dev@sha256:c130418a889d8f9afc3d80c5bda699dfcc83741a22d2f15f800ca5afba17fca1 \
  /repo/tools/bench/test_teleport_gate_diagnostics.py \
  --sdk /src/lra/glue/rexglue-sdk-main --build-dir /src/build-no-clock
```

The test applies the patch only in a temporary directory, compiles the actual
original and patched `Eligibility` with the real policy header against host
stubs, checks every diagnostic branch and 65,536 mixed state scenarios for equal
denial and identical native call sequence (also with diagnostic output omitted).
It runs the prior teleport transaction harness against the actual patched
include and checks the full two-line failed marker. The optional build-dir
argument reads the existing Ninja command and cross-compiles the full patched
Switch translation unit to a temporary object. It does not link an NRO, install
anything or validate hardware behavior.

After a separately reviewed build/installation, the next ordinary failed request
will carry the detail. Existing generic hardware evidence cannot be recovered
into an exact reason retroactively. A successful gate still starts the normal
teleport operation; this patch does not add a diagnostics-only console command.
