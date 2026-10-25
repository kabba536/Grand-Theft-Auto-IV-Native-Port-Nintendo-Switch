# GTA IV for Nintendo Switch (homebrew)

Grand Theft Auto IV (Xbox 360, USA, Title Update 8) running natively on the Nintendo Switch as a
homebrew NRO. No game files are included: you need your own copy of the game.

> [!IMPORTANT]
> **This port is still experimental. The final version is still in active development.** The goal
> is a GTA IV port that feels truly worthy of the Nintendo Switch; neither download below is being
> presented as the finished version.

## Download: choose your build

The builds are published as separate releases so their files cannot be confused. **Do not mix an
NRO from one release with the `native.toml` from the other.**

| Build | Recommended for | Status | Main trade-off |
|---|---|---|---|
| **[v35 — Performance Edition](https://github.com/kabba536/Grand-Theft-Auto-IV-Native-Port-Nintendo-Switch/releases/tag/v35-performance)** | The most consistent and established option | Stable test build | Lower nearby detail, but a longer horizon and denser population profile |
| **[v50 RC1 — Quality Edition](https://github.com/kabba536/Grand-Theft-Auto-IV-Native-Port-Nintendo-Switch/releases/tag/v50-quality-rc1)** | Testing newer renderer work and sharper nearby geometry | **Pre-release / release candidate** | Higher nearby detail, but a shorter horizon and lower population profile; final console validation is still in progress |

**Spanish installation guide:** [Guía de instalación en español](INSTALL_ES.md)

### What “Performance” and “Quality” mean here

“Quality” means higher **nearby geometry/detail** and better protection of complete vehicle and
character shadows. It does not mean that every setting is higher. v35 draws the city farther away
and uses more traffic and pedestrians; v50 concentrates more detail near the player and reduces the
horizon/population to control the extra cost.

These are two different tuning choices, not a promise that one build will be faster in every scene.
Frame rate still depends heavily on location, time of day, effects, shader cache and console mode.

### Observed frame-rate ranges

These are approximate results from real Nintendo Switch testing, not fixed guarantees. Performance
can vary with the area, time of day, on-screen effects, shader cache and console mode.

| Situation | v35 Performance | v50 Quality RC1 |
|---|---:|---:|
| General gameplay | **25–30 FPS** | **20–25 FPS** |
| Some interiors | Up to **30 FPS** | Up to **30 FPS**, but may vary |
| Driving through the city | **22–28 FPS**, depending on the in-game time of day | **17–24 FPS** |
| Lowest observed value | Normally within the ranges above | **13 FPS** when a train passes; outside that case, observed minimums have not fallen below **17 FPS** |

## v35 Performance Edition — improvements

v35 is the conservative performance release. Compared with the older build previously on the main
repository page, it keeps the established PGO build, native audio DSP, texture cache and reserved
texture arena, and adds the following renderer-side reductions:

- the small sun-shadow-caster filter now works during normal play, not only while the profiler is
  active;
- three diagnostic fixed-state hashes per draw are disabled on Switch;
- a diagnostic string is read once per frame instead of copied for every command;
- repeated `required-binding-failed` messages are rate-limited instead of synchronously writing
  tens of thousands of lines to the SD card during a session.

The v35 profile favours a longer 150 m horizon and more street population, while keeping nearby
detail at 0.45. It is the recommended starting point when predictability matters more than the
newer visual experiments.

## v50 Quality RC1 — improvements

v50 includes the v35 work and the cumulative v36–v50 renderer changes:

- reuses scratch memory for converted vertex buffers and avoids conversion work when a persistent
  GPU copy already exists;
- moves frame-queue back-pressure outside the command-capture lock and batches attachment barriers;
- releases CPU-side texture copies after GPU upload and handles texture-capture allocation failure
  without terminating the game;
- removes repeated diagnostic-context clearing and reduces cross-core cache-line traffic in the
  command pool;
- adds a Switch lock-free path for compatible multi-object waits;
- avoids re-registering unchanged vertex declarations and removes unnecessary vector-register
  save/reload blocks from generated code where analysis proves they are unused;
- protects vehicle, pedestrian, skinned, wheel, hair and weapon shaders from the small-shadow cut;
- discards eligible small sun-shadow pieces before they cross the full renderer pipeline;
- **v50 fixes the v49 shadow regression** by carrying the dropped draw's dirty-state words into the
  next draw or clear, preventing stale shader constants and flickering/disappearing shadows.

The dirty-state fix was replay-tested on PC over 4 × 20,000 randomized draws: the reference and v50
paths produced zero incorrect draws, while the v49 behaviour produced 53,046. The project tests
available for dirty state, draw-state cache and ownership/retirement also passed. Visual shadow
quality and the final performance benefit must still be confirmed across more real Switch sessions,
which is why this release is explicitly marked as a candidate.

## How it works

There is no emulator. The game's original PowerPC code is statically recompiled ahead of time and
built as a native ARM program for the Switch, while graphics are rendered natively through Vulkan.
The port adds the Switch platform layer, renderer, audio path and performance work needed to run it.

## Requirements

- A Nintendo Switch running custom firmware (Atmosphère).
- Your own **GTA IV Xbox 360 disc image (USA)** and **Title Update 8** (`TU_1A581VI_...`).
- About 10 GB free on the SD card.
- Docked mode is recommended for the higher GPU clock.

## Installation

1. Open the release for the build you want and download its runtime ZIP — not the source-code ZIP.
2. Extract the ZIP to the root of the SD card. It installs:
   ```text
   sdmc:/switch/gta4nx/gta4nx.nro
   sdmc:/switch/gta4nx/LibertyRecomp/native.toml
   ```
3. Extract your own disc image and copy the game files and Title Update 8 to:
   ```text
   sdmc:/switch/gta4nx/install/gta4_disc/
   sdmc:/switch/gta4nx/install/TU_1A581VI_.../
   ```
4. Open any installed game while holding **R** to enter the Homebrew Menu in title mode. Do not
   launch GTA4NX from the Album.
5. Select GTA IV. The first start installs game data and builds the shader cache, so it takes longer
   and may stutter heavily for the first few minutes.

For the complete Spanish walkthrough, updating instructions and troubleshooting, see
[INSTALL_ES.md](INSTALL_ES.md).

## Known limitations

- Busy city areas remain CPU-limited; collisions, smoke, sparks and glass can become GPU-limited.
- Handheld mode is slower because of its lower GPU clock.
- The 640×360 internal resolution, upscaled with FSR 1, can look soft on a TV.
- Raising `gta4_streaming_budget_scale` above 1.25 has not improved performance and has caused
  out-of-memory failures in earlier tests. Keep the included profile.
- The first minutes after an update can stutter while shaders are rebuilt.
- Launching through a Home Menu forwarder currently shows an error; use the Homebrew Menu in title
  mode.
- v50 RC1 still needs wider console validation for long-session memory behaviour, shadow rendering
  and its real-world performance gain.

## Reporting problems

Open an issue and include:

- the exact build name: `v35-performance` or `v50-quality-rc1`;
- where you were and what you were doing;
- whether the game closed, froze, showed broken shadows or only lost frame rate;
- roughly how long the session had been running;
- the folder `sdmc:/switch/gta4nx/logs/`, compressed as a ZIP.

Do not upload game data, your disc image or the title update.

## Support the project

GTA4NX is a free, non-commercial community project. If you would like to support the work, use
PayPal's normal **Send Money** option and enter the recipient email below:

**[Open PayPal Send Money](https://www.paypal.com/pt/digital-wallet/send-receive-money/send-money)**

Recipient: `kabbapaypal@gmail.com`

Any money received will be reinvested in development costs and in future projects requested by the
community. Contributions do not purchase features and do not guarantee a delivery date. See
[SUPPORT.md](SUPPORT.md) for full details.

## Credits

This Switch port is built on the work of these projects and people:

- **[Liberty Recompiled](https://github.com/OZORDI/LibertyRecomp)**: the static recompilation of
  GTA IV for Xbox 360 that this port is based on.
- **[LibertyRecompAndroid](https://github.com/vaduur/LibertyRecompAndroid)** (vaduur): the ARM64
  port this Switch version starts from.
- **ReXGlue** (Tom Clay), derived from **Xenia** (Ben Vanik and contributors): the Xbox 360
  recompilation runtime.
- **mesa-switch** (danfromtico, NaGaa95): the NVK Vulkan driver for the Switch.
- **StevensND**: the Need for Speed: Most Wanted Switch port, a key reference.
- **switchbrew / devkitPro** (libnx and the toolchain) and **FFmpeg** (audio decoding).

## Source code

Each GitHub Release includes a clearly named source-code archive for that exact build. The runtime
is based on LibertyRecompAndroid commit `7c97c58e1294331dffd617a5eb7267be55debdfc`; the corresponding
patch and build tooling are included in the matching source archive. Building requires your own
`default.xex`; neither game files nor generated game code are distributed.

The historical `source/` directory remains available for the earlier repository build, but users
and developers should use the source archive attached to the release they downloaded.

## License

Liberty Recompiled and LibertyRecompAndroid are licensed under the **GNU GPL v3** (see `LICENSE`),
and so is this port.

Grand Theft Auto IV is © Rockstar Games / Take-Two Interactive. This is a non-commercial fan
project, not affiliated with or endorsed by them. No game data files are distributed here; each
build works only with the user's own copy of the game.
