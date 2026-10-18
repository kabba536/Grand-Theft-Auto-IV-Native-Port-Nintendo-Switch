# GTA IV for Nintendo Switch (homebrew)

Grand Theft Auto IV (Xbox 360, USA, Title Update 8) running natively on the Nintendo Switch as a
homebrew NRO. **Private test build: please do not share it outside this repository.**

No game files are included. You need your own copy of the game.

---

## Status

**Playable, still in testing.** Measured on a Switch v1 (Erista) in docked mode, with stock clocks
(CPU 1785 MHz / GPU 768 MHz / RAM 1600 MHz) and the included performance profile:

| Where | Frame rate |
|---|---|
| Interiors, the pier, open roads | ~22–30 fps |
| City on foot | ~12–17 fps |
| Driving through dense city traffic | ~10–16 fps |

The game is capped at 30 fps. Raising performance in the city is the main work in progress.

## How it works (overview)

There is no emulator. The game's original PowerPC code is statically recompiled ahead of time and
built as a native ARM program for the Switch, and its graphics are drawn natively through Vulkan.
The Switch port adds the platform layer, rendering, audio and performance work needed to run it on
the console.

## Requirements

- A Nintendo Switch running custom firmware (Atmosphère).
- Your own **GTA IV Xbox 360 disc image (USA)** and **Title Update 8** (`TU_1A581VI_...`).
- About 10 GB free on the SD card.

## Installation

1. Download `gta4nx.nro` and `native.toml` from this repository.
2. Copy them to the SD card:
   ```
   sdmc:/switch/gta4nx/gta4nx.nro
   sdmc:/switch/gta4nx/LibertyRecomp/native.toml
   ```
3. Extract your disc image and copy the game files and the title update:
   ```
   sdmc:/switch/gta4nx/install/gta4_disc/              <- contents of the disc
   sdmc:/switch/gta4nx/install/TU_1A581VI_...          <- Title Update 8
   ```

## Launching

1. Open any installed **game while holding R** to enter the Homebrew Menu in title mode, which
   gives the game the full memory. Do **not** launch it from the Album.
2. Select **GTA IV**.
3. The first start installs the game data and builds the shader cache. This takes a while, and the
   game stutters for the first few minutes.

## Known issues

- **City frame rate stays under 20 fps,** especially while driving through traffic. The CPU is the limit.
- **One hospital interior drops to ~10 fps.**
- **The performance profile trades looks for speed:** lighter traffic and pedestrians, no sun
  shadows or reflections, shorter view distance.
- **The 640x360 internal resolution** (upscaled with FSR 1) looks soft on a TV.
- **Out of memory:** raising `gta4_streaming_budget_scale` above 1.0 in `native.toml` can make the
  game run out of memory and close after a few minutes. Keep the value from the included profile.
- **Shader stutter:** the first minutes after an update stutter while shaders are rebuilt.
- **Home Menu forwarder:** launching from a forwarder icon shows an error. Use the Homebrew Menu in
  title mode.

## Reporting problems

Open an issue with:
- where you were (city on foot, driving, a mission, an interior) and how the frame rate felt;
- what you were doing if the game closed or froze, and roughly how long after starting;
- the folder `sdmc:/switch/gta4nx/logs/` (zipped).

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

## License

Liberty Recompiled and LibertyRecompAndroid are licensed under the **GNU GPL v3**, and so is this
port. Testers who receive the build can request the source of the Switch modifications from the
repository owner.

Grand Theft Auto IV is © Rockstar Games / Take-Two Interactive. This is a non-commercial fan
project, not affiliated with or endorsed by them. No game data files are distributed here; the
build only works with your own copy of the game.
