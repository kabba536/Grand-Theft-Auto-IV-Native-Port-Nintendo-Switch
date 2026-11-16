# GTA4NX Critical Path & GPU/CPU Hotspot Audit (2026-11-14)

Verified on **Nintendo Switch** (`192.168.1.220`, `1785 MHz CPU / 768 MHz GPU / 2600 MHz RAM`, 3 cores mask `0x7`) using build **Stage 3 Tier 3b** (`sha256: 0509927784cf710926290ce384750a9f09b4d13252aaa465d64a5a196831cb07`), linked with patched NVK `/src/nvk/libvulkan.a` (`nak-unop-flip-v1+sched-latency-peephole-v2`), canonical sidewalk scene `(900.78, -521.38, 15.04)`.

> Baseline -> Target progression:
> `45.284 ms` (Stage 1) -> `43.022 ms` (Stage 3 Tier 2) -> **`42.240 ms`** (`23.67 FPS` mean, `25.2 FPS` peak interval) on **Stage 3 Tier 3b** -> **Target `<= 33.33 ms` (30 FPS)** (`-8.91 ms` remaining).

---

## 1. Frame Critical Path Overview (`stage3-tier3b-05099277-r1`)

From `guest-capture-eyt331gn/summary.json` (`N=473` joined frames, `0` dropped, `viewport-0.jpg` visually clean `bright=0.801`):

| Span | Mean (ms) | p95 (ms) | Notes |
|---|---:|---:|---|
| **`guest_present_interval`** | **42.239** | 50.646 | End-to-end guest cadence (`~23.67 FPS`) |
| `previous_publish_end_to_guest_present` | **16.989** | 28.717 | Serialized outside-publish gap (`Main XThread` + `Render Producer` under 3-core saturation) |
| `guest_to_worker` | 0.951 | 1.393 | `kPresent` -> `RenderWorkerMain` |
| `worker_wait_for_recorder` | 0.363 | 0.002 | Zero wait on >=95% of steady frames |
| `handoff_to_recorder_start` | 0.438 | 0.043 | Worker -> `FrameRecorderMain` wakeup |
| **`recorder_start_to_submit`** | **22.255** | 30.029 | **`FrameRecorderMain` critical path:** |
| — `prepare_before_record` | **2.809** | 4.567 | Driven almost entirely by `PrepareFrameTextures` + periodic `10.2 ms` texture-reclamation spike |
| — `record_native_frame` | **18.808** | 25.552 | `RecordNativeFrame` (**84.5% of recorder time**) |
| — `slot_completion` / `slot_fence_wait_us` | 0.260 / 0.250 | 0.102 / 0.090 | **Not GPU-fence stalled in steady gameplay** (`4.09 ms/s` total `nvFenceWait`) |
| — `queue_lock` / `driver_submit` | 0.001 / 0.081 | 0.001 / 0.073 | Queue & `vkQueueSubmit` are negligible |
| `submit_to_publish_end` | **1.233** | 2.190 | `PaintAndPresent`, `ClearNativeFrameCommands`, dynamic distance |
| `wait_submission_age` | 62.259 | 74.150 | ~2–3 frames in flight |

---

## 2. Live GPU Profile (`stage3-tier3b-gpu-profile`, `VkQueryPool`, 120 frames)

Measured directly on **Tier 3b (`0509927784cf`)** via `bench_gpu_profile.flag` (compact `.gpu-flat` with NVK `625/384` timestamp scaling, `gpu_resolve_fast=on`, `resolve_swap=off`, `720p`, `fsr1 ultra_quality`, `msaa=off`, `shadow_cascade_count=1`):

- **`gpu_frame_ms`**: **`32.670 ms` mean**, `32.672 ms` median, **`33.105 ms` p95**, **`33.387 ms` max** (`GPU 84% @ 768 MHz`).
  - Improved from **`34.298 ms`** (`d0327895` pre-Tier 2/3) to **`32.670 ms`**, clearing `33.33 ms` on average, **but with only `0.66 ms` mean headroom (`p95 = 33.105 ms`)**. Once CPU drops below ~33 ms, GPU becomes an active ceiling unless trimmed by ~2–3 ms too.

| GPU Pass | Mean (ms/frame) | % GPU |
|---|---:|---:|
| `gpu_resolve_ms` | **8.510** | 26.0% |
| `gpu_retail_warp_shadow_ms` | **7.801** | 23.9% |
| `gpu_retail_scene_to_gbuffer_ms` | **5.293** | 16.2% |
| `gpu_retail_lights_to_screen_ms` | **2.996** | 9.2% |
| `gpu_retail_draw_scene_ms` | **1.992** | 6.1% |
| `gpu_composite_ms` | **1.935** | 5.9% |
| `gpu_environment_reflections_ms` | 1.036 | 3.2% |
| `gpu_deferred_light_volumes_ms` | 0.984 | 3.0% |
| `gpu_present_ms` | 0.630 | 1.9% |
| `gpu_unattributed_ms` + `depth_resolve` + `water_reflections` + `light_setup` + translucent/radar | 1.493 | 4.6% |

Instrumented CPU phase spikes observed in the same GPU capture:
- `cpu_texture_preparation_ms`: **`2.995 ms`** every frame (`prepare_before_record`).
- `cpu_housekeeping_texture_reclamation_ms`: **spikes up to `10.204 ms`** (`cpu_housekeeping_ms` max **`10.672 ms`**) every 120 frames.

---

## 3. CPU Saturation & Thread Distribution (3 Cores Max = `300.0%`)

In steady gameplay (`rex_perfil.log`), total process CPU is saturated at **`293.69% / 300%`** (`97.9%` of all 3 cores), `sched_yield` fires `3,128/s` (`ceder`), `<=1 ms` sleeps consume `355.48 ms/s`:

| Thread | Pref Core | Prio | Steady CPU% | Role |
|---|---:|---:|---:|---|
| Render Producer (`XThread558C3EC0` / `88907140`) | 1 | `0x2C` | **55.5–56.0%** | Guest render submission (`SubmitTitleCommand`, `CaptureBufferResource`, `BuildDirtyStateDeltaUnchecked`) |
| `FrameRecorderMain` | 2 | `0x2D` | **45.4–45.9%** | `PrepareFrameTextures` + `RecordNativeFrame` -> Vulkan submit (`Prio` lower than Producer/Main audio!) |
| `Main XThread` | 0 | `0x2E` | **44.8–45.8%** | Game logic, AI, physics, script + `gta4::quicksave::Poll` SD `fopen` + `sub_823193D8` |
| Audio DSP (`XThread595AC7C0` / `8B0633C0`) | -1 | `0x3B` | **37.6–39.2%** | `gta4nx_native_829321A0` scalar biquads + `sub_821A47C0` resampler fallback |
| `RenderWorkerMain` | 1 | `0x2D` | **24.9–26.1%** | Shares Core 1 with Producer! `SnapshotPipeline`, `SnapshotDrawConstants`, `ApplyShaderConstantDelta` |
| `XThread55BDEEC0` / `958033A0` | -1 | `0x3B` | **17.0–19.0%** | `audEngine` (`sub_82902420`/`sub_82931700` + `1 ms` `KeDelayExecutionThread` sleeps, `sched_yield`) |
| `XMA Decoder` | -1 | `0x2B` | **14.9–15.6%** | `wmaprodec_rex.c` (`ff_wma_run_level_decode`) |
| `NativeCommandRetirer` | -1 | `0x3B` | **11.7–11.9%** | `~NativeCommand`, `~NativePipelineState`, `~NativeShaderState`, `ConstantStateVersion` frees |
| Guest Job Pools A (3 threads) + B (4 threads) | -1 | `0x3B` | **~36.2%** | Combined guest worker jobs + `ObjectTable::LookupObject` locks |

---

## 4. Exact `FrameRecorderMain` Breakdown (`native-performance-cpu.csv`, 12 detailed frames)

Vulkan driver work is **not** the CPU bottleneck:
- `vk-draw` (`765.7` draws): **`1.054 ms`**
- `vk-bind` (`2,379` calls): **`1.250 ms`**
- `vk-dynamic-state` (`2,275` calls): **`0.605 ms`**
- `vk-render-pass-boundary` (`188` calls): **`0.309 ms`**
- `vk-barrier` (`160` calls): **`0.172 ms`**
- `vk-queue-submit`: **`0.046 ms`**

Over **`16 ms`** of `FrameRecorderMain`'s `22.95 ms` (`18.81 ms` uninstrumented + `2.81 ms` prep) sits in **our C++ glue logic**:

1. **`record-command` self = `4.746 ms`** (`812.9 calls/frame`, `~5.8 us/call`):
   - Unconditional `gpu_flight::Record("native.command", ...)` on **every command** (`graphics_system.cpp:32657`, no `native_flight_enabled_` guard).
   - `HasCurrentPlacementContent` (`27549`) & `ClaimSurfaceContent` (`27566`) on every render-pass break, draw, and clear (`36006, 36062, 37627-37710`) calling `DecodeGuestSurfaceView` repeatedly + `reflection_resources_.find` + `native_placement_owners_` (`std::unordered_map`) lookups/inserts.
   - Forward-scanning `PrepareProducerDepthResolve` (`36153`, `26889-26995`) on scope breaks (`GetRenderingTargetUsage` + `native_texture_images_` hash lookups) without caching/fast-skip.
   - Per-draw `gta4_native_skip_pixel_shaders` string check (`34686`) + `gta4_native_skip_invisible_draws` looping `DecodeNativeBlendControl` (`34713`).
   - Uninstrumented draw-merging forward scans across ~3 KB `NativeCommand` structs (`37095-37245`, `std::memcmp` + `shared_ptr` array compares).

2. **`record-frame` self = `4.525 ms`** (outside child timers):
   - Detailed-GPU pre-pass (`31999`, when GPU profiling active) building `attribution_observations` over all 800+ commands + `XXH3_64bits`.
   - Pre-loop construction/destruction of node-based `std::set` / `std::unordered_map` containers (`30782-32065`: `artificial_light_renderer_instances`, `artificial_light_setup_lineage`, `scene_write_checkpoint_ordinals`, `gbuffer_write_checkpoint_ordinals`, `phone_probe_commands`) EVERY frame.
   - `AcquireNativePresenterImage` (`temporal/native_renderer.inc:514`), `RecordPresent` (`37988`), and `vkFlushMappedMemoryRanges` (`38051-38071`) + per-command loop prelude (`32334-32443`).

3. **`common-draw-bindings` (`BindCommonDrawState`) self = `3.901 ms`** (`748.4 calls/frame`, `5.555 ms` inc):
   - `BindUboConstantBanks` (`24443`, `23655`) calls `vkCmdBindDescriptorSets` on dynamic-offset changes (unwrapped by `kDriverBind`).
   - `NativeSharedConstantSemanticKey` (`23999-24188`): 1-entry `last_shared_key` misses frequently; on miss, `NativeSharedKeyWords` materializes **976 bytes (`122 x uint64_t`)** on the stack and hashes all 976 bytes via **`XXH3_64bits`** in `Find` **and again** in `Insert`, followed by a second `FrameGenerationMap` lookup (`FindFrameConstantBuffer`).
   - `NativeDrawStateCache::UpdatePipeline` (`native_draw_state_cache.h:18-31`) wipes all 6 dynamic caches (`viewport`, `scissor`, `depth_bias`, `stencil`, `blend_constants`, `push_constants`) on **every** pipeline change, forcing recomputation and `2,275` `vkCmdSet*` calls/frame.

4. **`pipeline-lookup` (`0.831 ms`) + `pipeline-key-and-build` (`0.742 ms`, `162.5 calls/frame`!)**:
   - `draw_pipeline_cache_` (`4096` entries, `graphics_system.cpp:22432`) is **1-way direct-mapped**, while hash `h` (`:22436-22451`) omits >25 fields checked by `==` (`strides[1..16]`, `color_formats[1..3]`, `blend_controls[1..3]`, stencil ops/masks, clip planes, polygon/sample/alpha state) and `NativePipelineMemoState` keeps uncanonicalized disabled state. Related draws collide on the exact same bucket and force `162.5` `GetOrCreatePipeline` rebuilds/lookups per frame (**21.7% miss rate!**).

5. **`prepare-textures` self = `1.823 ms`** (`2.536 ms` inc, `443.7` texture lookups + `620` sampler lookups):
   - `prepared_draw_cache` (`20137`) is only a **16-entry direct-mapped array**, and **every `PlanResolveSwap` wipes it completely** (`20316-20320`).
   - `AssignIndexedWorkingSet` (`native_descriptor_working_set.inc:18-90`) runs uninstrumented per non-reused draw with `FrameGenerationMap::Find` + **`O(active_stages^2)` duplicate-key scans** (`native_working_set.h:123-144`) + `std::unordered_set<uint64_t> packed_alias_generations` + `std::unordered_map` view lookups.

6. **`record-indexed` self = `1.567 ms`** (`646.1 calls/frame`) + **`target-realization`/`surface-image-lookup` (`1.234 ms`)**:
   - `SnapshotPipeline` resets `required_streams_mask_memo = 0xFFFFFFFFu` on any state fork (`8081`), forcing `GetRequiredVertexStreamMask` to rescan vertex elements.
   - Every index-cacheable draw probes `std::unordered_map<uint64_t, shared_ptr<NativeVertexCacheRange>> vertex_cache_ranges` (`25371`).
   - `GetOrCreateSurfaceImage` (`1,720 calls/frame`) probes `pending_surface_release_ids_.contains(...)` (`std::unordered_set`) **even on cache hits** (`21658`) and calls `MarkNativeSurfaceImageUsed`.

---

## 5. Additional Cross-Thread CPU & Allocator Bottlenecks Found in Tier 3b Stack Samples

1. **`sub_823193D8` / `sub_823F70E8` (`gta4-recomp/src/gta4_multiplayer_64_hooks.cpp:3975-4064`, `Main XThread`)**:
   - Intercepts population dispatch **even in single-player** with no multiplayer guard, allocating/freeing `align=64` `PPCContext` (`2,688` bytes) in `g_population_dispatch_capture.calls`.
   - Because `switch_malloc_cache.c` only handles `align <= 32` in `TCache` and `>= 64 KB` in `ArenaAlloc`, `align=64, 2688B` **bypasses the thread malloc cache completely** and hits `__real__memalign_r` -> **newlib global `rmutexLock`** (`svcArbitrateLock`).
2. **`EvictNativeTextureImages` -> `QueryNativeTextureHeapBudgets` -> NVK `mallinfo()` (`graphics_system.cpp:21076-21119`)**:
   - Calls `vkGetPhysicalDeviceMemoryProperties2` -> NVK `nvk_get_sysmem_heap_available` -> `os_get_available_system_memory` -> **`mallinfo()`** (walks ~1.3 GB heap under global `__malloc_lock`, causing **`10.20 ms` recorder spikes** and blocking Producer/Main in `svcArbitrateLock`), even though **`configured_limit_bytes` immediately overwrites `budgets` on Switch** (`21112-21119`)!
3. **`gta4::quicksave::Poll` synchronous SD card I/O on `Main XThread`**:
   - Caught in **`2.8%` (`1.6% + 1.2%`) of `Main XThread` 1ms stack samples** inside `fsdev_open <- _open_r <- _fopen_r <- gta4::quicksave::Poll` — blocking `Main XThread` directly on Switch SD I/O!
4. **`SubmitTitleCommand` (`0x76dc94`) & `NativeCommandRetirer` (`11.88%` CPU)**:
   - `SubmitTitleCommand` (`graphics_system.cpp:4495`) swaps `producer_pending_state_` with `native_command.pending_state`, receiving 0 capacity back if fresh or trimmed (`>8192B`), causing repeated `operator new` allocations on `CoalesceStateCommand` (`8166`). Meanwhile `NativeCommand::RecycleInPlace()` (`graphics_system.h:489-509`) drops `payload` capacity and ~45 `shared_ptr`s, keeping `NativeCommandRetirer` at `11.88%` CPU freeing objects across threads (`switch_malloc_cache` depot spills).
5. **Audio DSP (`XThread595AC7C0` / `8B0633C0`, `37.6–39.2%` CPU)**:
   - ~43% blocked in `KeWaitForSingleObject`, remaining compute dominated by `gta4nx_native_829321A0` scalar 4-pass 256-sample `biquad1_pass` loops (`switch_audio_fast.cpp:5975-5992`), `sub_82199BC8`, `sub_82934F00`, and `sub_821AD520 -> sub_821A47C0` (`gta4_recomp.3.cpp` still compiled with `-O2`).

---

## 6. Prioritized Roadmap for Next Optimization Session (Tier 4+)

To bridge **`42.24 ms` -> `<= 33.33 ms`** cleanly (and ensure GPU stays comfortably under `30–31 ms`):

1. **Tier 4A — Remove Global Lock Storms & Single-Player / Main-Thread Waste (Low Risk, High Upside):**
   - Guard `sub_823F70E8` / `sub_823193D8` (`gta4_multiplayer_64_hooks.cpp:3975-4064`) when single-player (or use persistent non-heap `std::vector` capacity + `align<=32` / pooled array) -> eliminates `align=64` global `rmutexLock` stalls on `Main XThread`.
   - Skip `QueryNativeTextureHeapBudgets()` in `EvictNativeTextureImages()` (`graphics_system.cpp:21076-21119`) when `!allocation_recovery && configured_limit_bytes != 0` -> eliminates `10.2 ms` `mallinfo()` spikes & `__malloc_lock` stalls on Producer/Main.
   - Throttle or move `gta4::quicksave::Poll` SD `fopen()` checks off `Main XThread` (`2.8%` of Main Thread samples!).
   - Retain `producer_pending_state_` capacity on `SubmitTitleCommand` swap miss (or reserve before reuse) and cache `required_streams_mask` across unrelated state-version forks (`SnapshotPipeline` `8081`).
   - Set Switch default `gta4_frame_limit` to `60` in `gta4-recomp/src/gta4_app.cpp` (already set in live `/switch/gta4nx/LibertyRecomp/native.toml`).

2. **Tier 4B — Cut `FrameRecorderMain` C++ Glue (`22.26 ms` -> `< 12 ms`):**
   - Guard `gpu_flight::Record("native.command")` behind `native_flight_enabled_` (`graphics_system.cpp:32657`); avoid constructing empty `std::set` / `std::unordered_map` containers per frame when diagnostics/traces are off; add fast O(1) empty checks for `pending_surface_release_ids_` (`21658`) instead of hashing `unordered_set` 1,720 times/frame.
   - Make `draw_pipeline_cache_` 2-way/4-way associative (or hash all canonicalized `==` fields & strip inert state in `NativePipelineMemoState`) to eliminate the **162.5/frame** pipeline-cache misses (`1.57 ms`).
   - Shrink/hash `NativeSharedConstantSemanticKey` incrementally (dirty-tracked active stages instead of hashing 976 bytes twice per miss) and avoid resetting compatible dynamic states in `NativeDrawStateCache::UpdatePipeline`.
   - Enlarge `prepared_draw_cache` (or index without resolve-wipe) and eliminate O(`stages^2`) scans in `AssignIndexedWorkingSet` (`2.54 ms` -> `< 1.0 ms`).

3. **Tier 5 — CPU Scheduler & GPU Margin (`32.67 ms` -> `<= 29 ms`):**
   - Vectorize `gta4nx_native_829321A0` biquad passes (`switch_audio_fast.cpp:5975`) and check `FrameRecorderMain` priority (`0x2B` vs audio `0x2B`/`0x3B`) + core placement so Producer & `RenderWorker` don't starve each other on Core 1.
   - Test `resolve-swap` + `warp-shadow` optimizations once CPU reaches `< 33 ms`, with full `viewport-*.jpg` visual parity checks and `3x20s` verification.
