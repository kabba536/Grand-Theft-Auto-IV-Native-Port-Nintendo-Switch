#!/usr/bin/env python3
"""Apply Stage 3 Tier 2 optimizations in Docker /src cleanly with exact assertions."""
from pathlib import Path
import re

SDK = Path("/src/lra35/glue/rexglue-sdk-main")


def patch_exact(path: Path, old: str, new: str, expected_count: int = 1) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count == 0 and new in text:
        print(f"[SKIP] Already patched: {path}")
        return
    assert count == expected_count, f"{path}: expected {expected_count} match(es), found {count}"
    path.write_text(text.replace(old, new, expected_count), encoding="utf-8")
    print(f"[OK] Patched ({expected_count}): {path}")


# 1. xboxkrnl_audio.cpp: remove MaybeYield() when sleep_us == 0
patch_exact(
    SDK / "src/kernel/xboxkrnl/xboxkrnl_audio.cpp",
    """  if (const uint32_t sleep_us = REXCVAR_GET(audio_category_mask_sleep_us)) {
    rex::thread::Sleep(std::chrono::microseconds(sleep_us));
  } else {
    rex::thread::MaybeYield();
  }

  // Checking these bits""",
    """  if (const uint32_t sleep_us = REXCVAR_GET(audio_category_mask_sleep_us)) {
    rex::thread::Sleep(std::chrono::microseconds(sleep_us));
  }

  // Checking these bits""",
)

# 2. gta4-recomp/CMakeLists.txt: upgrade trailing -O2 to -O3 for recompiled game units
patch_exact(
    SDK / "gta4-recomp/CMakeLists.txt",
    """    set_property(SOURCE ${GENERATED_SOURCES} APPEND PROPERTY COMPILE_OPTIONS
        $<$<CONFIG:Release,RelWithDebInfo>:-O2>)""",
    """    set_property(SOURCE ${GENERATED_SOURCES} APPEND PROPERTY COMPILE_OPTIONS
        $<$<CONFIG:Release,RelWithDebInfo>:-O3>)""",
)

# 3. graphics_system.h: add required_streams_mask_memo (plain uint32_t so NativePipelineState stays copyable)
h_path = SDK / "src/graphics/gta4_native/graphics_system.h"
h_text = h_path.read_text(encoding="utf-8")
if "std::atomic<uint32_t> required_streams_mask_memo{0xFFFFFFFFu};" in h_text:
    h_text = h_text.replace(
        "mutable std::atomic<uint32_t> required_streams_mask_memo{0xFFFFFFFFu};",
        "mutable uint32_t required_streams_mask_memo = 0xFFFFFFFFu;",
        1,
    )
    h_path.write_text(h_text, encoding="utf-8")
    print(f"[OK] Updated atomic->uint32_t in {h_path}")
else:
    patch_exact(
        h_path,
        """    mutable uint16_t translucent_range_memo = 0xFFFF;
    mutable uint16_t shader_category_memo = 0xFFFF;
  };""",
        """    mutable uint16_t translucent_range_memo = 0xFFFF;
    mutable uint16_t shader_category_memo = 0xFFFF;
    // Bit 31: computed valid (bits 0..15 = active stream mask); 0x40000000: invalid; 0xFFFFFFFF: unset.
    mutable uint32_t required_streams_mask_memo = 0xFFFFFFFFu;
  };""",
    )

h_path = SDK / "src/graphics/gta4_native/graphics_system.h"
h_text = h_path.read_text(encoding="utf-8")
decl = "  uint32_t GetRequiredVertexStreamMask(const NativePipelineState& state) const;\n"
target_decl = "  bool GetRequiredVertexStreams(const NativePipelineState& state,\n                                std::array<bool, kVertexStreamCount>& required_streams) const;"
# Normalize duplicate declarations if earlier retry stacked them
while h_text.count(decl) > 1:
    h_text = h_text.replace(decl, "", 1)
if decl not in h_text:
    assert target_decl in h_text, "GetRequiredVertexStreams decl missing in graphics_system.h"
    h_text = h_text.replace(target_decl, decl + target_decl, 1)
h_path.write_text(h_text, encoding="utf-8")
print(f"[OK] Normalized GetRequiredVertexStreamMask decl in {h_path}")

# 4. graphics_system.cpp: bitmask memoization + thread core hints
gs_path = SDK / "src/graphics/gta4_native/graphics_system.cpp"
patch_exact(
    gs_path,
    """  const bool off_core3 = RexSwitchExcludeCurrentThreadFromCore(3);
  const bool ok = RexSwitchSetCurrentThreadPriorityOk(int(priority));
  if (ok) RexSwitchMarkRaisedGuestThread();
  REXLOG_WARN("gta4-native: title render thread (draw producer) priority {} ({}), core 3 {}",
              priority, ok ? "set" : "refused", off_core3 ? "excluded" : "unchanged");""",
    """  const bool off_core3 = RexSwitchExcludeCurrentThreadFromCore(3);
  const bool ok = RexSwitchSetCurrentThreadPriorityOk(int(priority));
  const bool core_ok = RexSwitchSetCurrentThreadCore(1);
  if (ok) RexSwitchMarkRaisedGuestThread();
  REXLOG_WARN("gta4-native: title render thread (draw producer) priority {} ({}), core 1 ({}), core 3 {}",
              priority, ok ? "set" : "refused", core_ok ? "set" : "refused",
              off_core3 ? "excluded" : "unchanged");""",
)

patch_exact(
    gs_path,
    """void ApplyNativeRendererThreadPriority(const char* name) {
#if REX_PLATFORM_SWITCH
  const uint32_t priority = REXCVAR_GET(gta4_native_renderer_thread_priority);
  if (priority >= 28 && priority <= 59) {
    const bool ok = RexSwitchSetCurrentThreadPriorityOk(int(priority));
    REXLOG_INFO("gta4-native: {} thread priority {} ({})", name, priority, ok ? "set" : "refused");
  }
#else
  (void)name;
#endif
}""",
    """void ApplyNativeRendererThreadPriority(const char* name) {
#if REX_PLATFORM_SWITCH
  const uint32_t priority = REXCVAR_GET(gta4_native_renderer_thread_priority);
  if (priority >= 28 && priority <= 59) {
    const bool ok = RexSwitchSetCurrentThreadPriorityOk(int(priority));
    int target_core = -1;
    if (std::string_view(name) == "frame recorder") {
      target_core = 2;
    } else if (std::string_view(name) == "render assembler") {
      target_core = 1;
    }
    const bool core_ok = target_core >= 0 ? RexSwitchSetCurrentThreadCore(target_core) : false;
    REXLOG_INFO("gta4-native: {} thread priority {} ({}), core {} ({})", name, priority,
                ok ? "set" : "refused", target_core, core_ok ? "set" : "unchanged");
  }
#else
  (void)name;
#endif
}""",
)

patch_exact(
    gs_path,
    """  snapshot->render_targets = colors;
  snapshot->depth_stencil = depth;
  last_pipeline_snapshot_ = std::move(snapshot);""",
    """  snapshot->render_targets = colors;
  snapshot->depth_stencil = depth;
  snapshot->required_streams_mask_memo = 0xFFFFFFFFu;
  last_pipeline_snapshot_ = std::move(snapshot);""",
)

gs_text = gs_path.read_text(encoding="utf-8")
atomic_old = """  uint32_t cached = state.required_streams_mask_memo.load(std::memory_order_acquire);
  if (cached != kMaskUnset) {
    return cached;
  }"""
atomic_new = """  uint32_t cached = __atomic_load_n(&state.required_streams_mask_memo, __ATOMIC_ACQUIRE);
  if (cached != kMaskUnset) {
    return cached;
  }"""
if atomic_old in gs_text:
    gs_text = gs_text.replace(atomic_old, atomic_new, 1)
    gs_text = gs_text.replace(
        "state.required_streams_mask_memo.store(kMaskInvalid, std::memory_order_release);",
        "__atomic_store_n(&state.required_streams_mask_memo, kMaskInvalid, __ATOMIC_RELEASE);",
        1,
    )
    gs_text = gs_text.replace(
        "state.required_streams_mask_memo.store(encoded, std::memory_order_release);",
        "__atomic_store_n(&state.required_streams_mask_memo, encoded, __ATOMIC_RELEASE);",
        1,
    )
    gs_path.write_text(gs_text, encoding="utf-8")
    print(f"[OK] Updated atomic builtins in {gs_path}")
else:
    patch_exact(
        gs_path,
        """bool Gta4NativeGraphicsSystem::GetRequiredVertexStreams(
    const NativePipelineState& state,
    std::array<bool, kVertexStreamCount>& required_streams) const {
  required_streams.fill(false);
  if (!state.vertex_shader_resource || !state.vertex_declaration_resource) {
    return false;
  }

  for (const NativeVertexInput& shader_input : state.vertex_shader_resource->vertex_inputs) {
    const VertexElement* matching_element = nullptr;
    for (const VertexElement& element : state.vertex_declaration_resource->elements) {
      if (ConvertVertexUsageToLocation(element.usage, element.usage_index) ==
          shader_input.location) {
        matching_element = &element;
        break;
      }
    }
    if (!matching_element) {
      continue;
    }
    if (matching_element->stream >= kVertexStreamCount) {
      return false;
    }
    required_streams[matching_element->stream] = true;
  }
  return true;
}""",
        """uint32_t Gta4NativeGraphicsSystem::GetRequiredVertexStreamMask(
    const NativePipelineState& state) const {
  constexpr uint32_t kMaskUnset = 0xFFFFFFFFu;
  constexpr uint32_t kMaskInvalid = 0x40000000u;
  constexpr uint32_t kMaskValidFlag = 0x80000000u;
  uint32_t cached = __atomic_load_n(&state.required_streams_mask_memo, __ATOMIC_ACQUIRE);
  if (cached != kMaskUnset) {
    return cached;
  }
  if (!state.vertex_shader_resource || !state.vertex_declaration_resource) {
    return kMaskInvalid;
  }
  uint32_t mask = 0;
  for (const NativeVertexInput& shader_input : state.vertex_shader_resource->vertex_inputs) {
    const VertexElement* matching_element = nullptr;
    for (const VertexElement& element : state.vertex_declaration_resource->elements) {
      if (ConvertVertexUsageToLocation(element.usage, element.usage_index) ==
          shader_input.location) {
        matching_element = &element;
        break;
      }
    }
    if (!matching_element) {
      continue;
    }
    if (matching_element->stream >= kVertexStreamCount) {
      __atomic_store_n(&state.required_streams_mask_memo, kMaskInvalid, __ATOMIC_RELEASE);
      return kMaskInvalid;
    }
    mask |= (1u << matching_element->stream);
  }
  const uint32_t encoded = kMaskValidFlag | mask;
  __atomic_store_n(&state.required_streams_mask_memo, encoded, __ATOMIC_RELEASE);
  return encoded;
}

bool Gta4NativeGraphicsSystem::GetRequiredVertexStreams(
    const NativePipelineState& state,
    std::array<bool, kVertexStreamCount>& required_streams) const {
  required_streams.fill(false);
  const uint32_t encoded = GetRequiredVertexStreamMask(state);
  if (!(encoded & 0x80000000u)) {
    return false;
  }
  uint32_t mask = encoded & 0xFFFFu;
  while (mask) {
    const uint32_t stream = uint32_t(__builtin_ctz(mask));
    mask &= mask - 1u;
    required_streams[stream] = true;
  }
  return true;
}""",
    )

# Optimize RecordPrimitive & RecordIndexedPrimitive stream loops to iterate set bits only
patch_exact(
    gs_path,
    """  std::array<bool, kVertexStreamCount> required_streams{};
  if (!GetRequiredVertexStreams(*command.pipeline_state, required_streams)) {
    return fail("vertex-input-layout");
  }
  for (uint32_t stream = 0; stream < kVertexStreamCount; ++stream) {
    if (!required_streams[stream]) {
      continue;
    }""",
    """  const uint32_t stream_encoded = GetRequiredVertexStreamMask(*command.pipeline_state);
  if (!(stream_encoded & 0x80000000u)) {
    return fail("vertex-input-layout");
  }
  for (uint32_t rem_streams = stream_encoded & 0xFFFFu; rem_streams;) {
    const uint32_t stream = uint32_t(__builtin_ctz(rem_streams));
    rem_streams &= rem_streams - 1u;""",
    expected_count=2,
)

patch_exact(
    gs_path,
    """    for (uint32_t stream = 0; stream < kVertexStreamCount; ++stream) {
      if (!required_streams[stream]) {
        continue;
      }""",
    """    for (uint32_t stream = 0; stream < kVertexStreamCount; ++stream) {
      if (!(stream_encoded & (1u << stream))) {
        continue;
      }""",
)

patch_exact(
    gs_path,
    """    for (uint32_t stream = 0; stream < kVertexStreamCount; ++stream) {
      if (!required_streams[stream]) continue;""",
    """    for (uint32_t stream = 0; stream < kVertexStreamCount; ++stream) {
      if (!(stream_encoded & (1u << stream))) continue;""",
)

# 5. src/system/xthread.cpp: prefer core 0 for Main XThread (mask stays 0x7)
patch_exact(
    SDK / "src/system/xthread.cpp",
    """      if (raise_main) {
        switch_priority = int(main_priority);
        RexSwitchExcludeCurrentThreadFromCore(3);
      }""",
    """      if (raise_main) {
        switch_priority = int(main_priority);
        RexSwitchExcludeCurrentThreadFromCore(3);
        RexSwitchSetCurrentThreadCore(0);
      }""",
)

# 6. Patch build-pgo-ubo-audio-sync-base9.ninja: keep -O2 on PGO units (matches .gcda arcs), upgrade non-PGO hot TUs to -O3
ninja_path = Path("/src/build_combo/build-pgo-ubo-audio-sync-base9.ninja")
ninja_text = ninja_path.read_text(encoding="utf-8")
pgo_units = {0, 3, 10, 29, 70, 71, 73, 78}
non_pgo_hot_units = {2, 4, 6, 59, 74}
lines = ninja_text.splitlines(keepends=True)
cur_unit = None
upgraded = 0
restored = 0
for idx, line in enumerate(lines):
    m = re.match(r"^build glue/gta4-recomp/CMakeFiles/gta4nx\.dir/generated/gta4_recomp\.(\d+)\.cpp\.obj:", line)
    if m:
        cur_unit = int(m.group(1))
    elif line.startswith("build "):
        cur_unit = None
    elif cur_unit is not None and line.startswith("  FLAGS = "):
        if cur_unit in pgo_units and "-std=gnu++23 -O3" in line:
            lines[idx] = line.replace("-std=gnu++23 -O3", "-std=gnu++23 -O2", 1)
            restored += 1
        elif cur_unit in non_pgo_hot_units and "-std=gnu++23 -O2" in line:
            lines[idx] = line.replace("-std=gnu++23 -O2", "-std=gnu++23 -O3", 1)
            upgraded += 1
if upgraded or restored:
    ninja_path.write_text("".join(lines), encoding="utf-8")
print(f"[OK] Ninja TUs updated: {upgraded} non-PGO -> -O3, {restored} PGO restored -> -O2")
