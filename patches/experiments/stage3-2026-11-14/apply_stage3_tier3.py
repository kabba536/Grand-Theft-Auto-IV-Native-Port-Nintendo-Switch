import pathlib
import re

sdk = pathlib.Path('/src/lra35/glue/rexglue-sdk-main')

# 1. switch_audio_fast.cpp: optimize gta4nx_native_829321A0 (biquad2 voice filter)
saf_path = sdk / 'gta4-recomp/src/switch_audio_fast.cpp'
saf_txt = saf_path.read_text()

old_829321a0 = '''extern "C" REX_FUNC(gta4nx_native_829321A0) {
  const uint32_t self = ctx.r3.u32;
  const bool lpf = REX_LOAD_U32(self + 80) < 23900u;
  const bool hpf = REX_LOAD_U32(self + 76) != 0u;
  if (!lpf && !hpf) {
    ctx.r3.s64 = 0;
    return;
  }
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint64_t saved_lr = ctx.lr;
  const uint32_t frame = ctx.r1.u32 - 240;
  REX_STORE_U32(frame, ctx.r1.u32);
  ctx.r1.u64 = frame;
  ctx.r3.u64 = ctx.r4.u64;
  ctx.r4.u64 = frame + 80;
  ctx.lr = 0x829321F8;
  sub_8218FB98(ctx, base);
  // The guest copies both 36-byte blocks to its frame (sub_82A11940) and works there.
  for (uint32_t i = 0; i < 36; i += 4) {
    REX_STORE_U32(frame + 144 + i, REX_LOAD_U32(self + 4 + i));
    REX_STORE_U32(frame + 96 + i, REX_LOAD_U32(self + 40 + i));
  }
  const float zero = gta4nx_ldf(base, 0x82000A34u);
  if (lpf && REX_LOAD_U8(self + 100) != 0) {
    for (uint32_t o : {176u, 168u, 172u, 164u}) gta4nx_stf(base, frame + o, zero);
  }
  if (hpf && REX_LOAD_U8(self + 101) != 0) {
    for (uint32_t o : {128u, 120u, 124u, 116u}) gta4nx_stf(base, frame + o, zero);
  }
  if (REX_LOAD_U32(self + 88) != REX_LOAD_U32(self + 80)) {
    ctx.r5.u64 = REX_LOAD_U32(self + 80);
    ctx.r6.u64 = frame + 144;
    ctx.r4.s64 = 1;
    ctx.r3.u64 = self;
    ctx.lr = 0x829322A0;
    sub_82932090(ctx, base);
    for (uint32_t i = 0; i < 20; i += 4) REX_STORE_U32(self + 4 + i, REX_LOAD_U32(frame + 144 + i));
  }
  if (REX_LOAD_U32(self + 84) != REX_LOAD_U32(self + 76)) {
    ctx.r5.u64 = REX_LOAD_U32(self + 76);
    ctx.r6.u64 = frame + 96;
    ctx.r4.s64 = 0;
    ctx.r3.u64 = self;
    ctx.lr = 0x829322EC;
    sub_82932090(ctx, base);
    for (uint32_t i = 0; i < 20; i += 4) REX_STORE_U32(self + 40 + i, REX_LOAD_U32(frame + 96 + i));
  }
  ctx.lr = saved_lr;
  const uint32_t buffer = REX_LOAD_U32(frame + 88);
  REX_STORE_U32(self + 88, REX_LOAD_U32(self + 80));
  REX_STORE_U32(self + 84, REX_LOAD_U32(self + 76));
  REX_STORE_U8(self + 101, hpf ? 0 : 1);
  REX_STORE_U8(self + 100, lpf ? 0 : 1);

  const float lb0 = gta4nx_ldf(base, frame + 144), lb1 = gta4nx_ldf(base, frame + 148);
  const float lb2 = gta4nx_ldf(base, frame + 152), la1 = gta4nx_ldf(base, frame + 156);
  const float la2 = gta4nx_ldf(base, frame + 160);
  float lz1 = gta4nx_ldf(base, frame + 164), lz2 = gta4nx_ldf(base, frame + 168);
  float lw1 = gta4nx_ldf(base, frame + 172), lw2 = gta4nx_ldf(base, frame + 176);
  const float hb0 = gta4nx_ldf(base, frame + 96), hb1 = gta4nx_ldf(base, frame + 100);
  const float hb2 = gta4nx_ldf(base, frame + 104), ha1 = gta4nx_ldf(base, frame + 108);
  const float ha2 = gta4nx_ldf(base, frame + 112);
  float hz1 = gta4nx_ldf(base, frame + 116), hz2 = gta4nx_ldf(base, frame + 120);
  float hw1 = gta4nx_ldf(base, frame + 124), hw2 = gta4nx_ldf(base, frame + 128);

  // One sample through two cascaded biquads (the guest's exact operation order).
  auto biquad2 = [](float x, float b0, float b1, float b2, float a1, float a2, float& z1,
                    float& z2, float& w1, float& w2) {
    const float y1 = __builtin_fmaf(x, b0, z1);
    const float y2 = __builtin_fmaf(y1, b0, w1);
    const float p1 = y1 * a1;
    const float p2 = y1 * a2;
    const float q1 = y2 * a1;
    const float q2 = y2 * a2;
    const float nz1 = __builtin_fmaf(x, b1, -p1) + z2;
    const float nz2 = __builtin_fmaf(x, b2, -p2);
    const float nw1 = __builtin_fmaf(y1, b1, -q1) + w2;
    const float nw2 = __builtin_fmaf(y1, b2, -q2);
    z1 = nz1;
    z2 = nz2;
    w1 = nw1;
    w2 = nw2;
    return y2;
  };
  for (uint32_t i = 0; i < 256; ++i) {
    const uint32_t ea = buffer + i * 4;
    float x = gta4nx_ldf(base, ea);
    if (lpf) x = biquad2(x, lb0, lb1, lb2, la1, la2, lz1, lz2, lw1, lw2);
    if (hpf) x = biquad2(x, hb0, hb1, hb2, ha1, ha2, hz1, hz2, hw1, hw2);
    gta4nx_stf(base, ea, x);
  }

  // State back to the voice; values with a zero exponent (denormals) become `zero`.
  auto keep = [zero](float v) {
    return (std::bit_cast<uint32_t>(v) & 0x7F800000u) != 0 ? v : zero;
  };
  gta4nx_stf(base, self + 24, keep(lz1));
  gta4nx_stf(base, self + 32, keep(lw1));
  gta4nx_stf(base, self + 28, keep(lz2));
  gta4nx_stf(base, self + 36, keep(lw2));
  gta4nx_stf(base, self + 60, keep(hz1));
  gta4nx_stf(base, self + 68, keep(hw1));
  gta4nx_stf(base, self + 64, keep(hz2));
  gta4nx_stf(base, self + 72, keep(hw2));
  ctx.r3.s64 = 0;
  ctx.r1.u64 = saved_r1;
}'''

new_829321a0 = '''extern "C" REX_FUNC(gta4nx_native_829321A0) {
  const uint32_t self = ctx.r3.u32;
  const uint32_t lpf_cutoff = REX_LOAD_U32(self + 80);
  const uint32_t hpf_cutoff = REX_LOAD_U32(self + 76);
  const bool lpf = lpf_cutoff < 23900u;
  const bool hpf = hpf_cutoff != 0u;
  if (!lpf && !hpf) {
    ctx.r3.s64 = 0;
    return;
  }
  ctx.fpscr.enableFlushMode();
  const uint64_t saved_r1 = ctx.r1.u64;
  const uint64_t saved_lr = ctx.lr;
  const uint32_t frame = ctx.r1.u32 - 240;
  REX_STORE_U32(frame, ctx.r1.u32);
  ctx.r1.u64 = frame;
  ctx.r3.u64 = ctx.r4.u64;
  ctx.r4.u64 = frame + 80;
  ctx.lr = 0x829321F8;
  sub_8218FB98(ctx, base);
  const float zero = gta4nx_ldf(base, 0x82000A34u);

  if (REX_LOAD_U32(self + 88) != lpf_cutoff) {
    for (uint32_t i = 0; i < 36; i += 4) REX_STORE_U32(frame + 144 + i, REX_LOAD_U32(self + 4 + i));
    ctx.r5.u64 = lpf_cutoff;
    ctx.r6.u64 = frame + 144;
    ctx.r4.s64 = 1;
    ctx.r3.u64 = self;
    ctx.lr = 0x829322A0;
    sub_82932090(ctx, base);
    for (uint32_t i = 0; i < 20; i += 4) REX_STORE_U32(self + 4 + i, REX_LOAD_U32(frame + 144 + i));
  }
  if (REX_LOAD_U32(self + 84) != hpf_cutoff) {
    for (uint32_t i = 0; i < 36; i += 4) REX_STORE_U32(frame + 96 + i, REX_LOAD_U32(self + 40 + i));
    ctx.r5.u64 = hpf_cutoff;
    ctx.r6.u64 = frame + 96;
    ctx.r4.s64 = 0;
    ctx.r3.u64 = self;
    ctx.lr = 0x829322EC;
    sub_82932090(ctx, base);
    for (uint32_t i = 0; i < 20; i += 4) REX_STORE_U32(self + 40 + i, REX_LOAD_U32(frame + 96 + i));
  }
  ctx.lr = saved_lr;
  const uint32_t buffer = REX_LOAD_U32(frame + 88);
  const bool reset_lpf = lpf && REX_LOAD_U8(self + 100) != 0;
  const bool reset_hpf = hpf && REX_LOAD_U8(self + 101) != 0;
  REX_STORE_U32(self + 88, lpf_cutoff);
  REX_STORE_U32(self + 84, hpf_cutoff);
  REX_STORE_U8(self + 101, hpf ? 0 : 1);
  REX_STORE_U8(self + 100, lpf ? 0 : 1);

  float lz1 = reset_lpf ? zero : gta4nx_ldf(base, self + 24);
  float lz2 = reset_lpf ? zero : gta4nx_ldf(base, self + 28);
  float lw1 = reset_lpf ? zero : gta4nx_ldf(base, self + 32);
  float lw2 = reset_lpf ? zero : gta4nx_ldf(base, self + 36);
  float hz1 = reset_hpf ? zero : gta4nx_ldf(base, self + 60);
  float hz2 = reset_hpf ? zero : gta4nx_ldf(base, self + 64);
  float hw1 = reset_hpf ? zero : gta4nx_ldf(base, self + 68);
  float hw2 = reset_hpf ? zero : gta4nx_ldf(base, self + 72);

  uint8_t* __restrict guest_buf = REX_FAST_PTR(uint8_t, buffer);
  alignas(16) float s[256];
  const uint32x4_t abs_mask = vdupq_n_u32(0x7FFFFFFFu);
  uint32x4_t vmax_u = vdupq_n_u32(0);
  for (uint32_t i = 0; i < 256; i += 4) {
    const uint32x4_t swapped = vreinterpretq_u32_u8(vrev32q_u8(vld1q_u8(guest_buf + i * 4)));
    vmax_u = vmaxq_u32(vmax_u, vandq_u32(swapped, abs_mask));
    vst1q_f32(&s[i], vreinterpretq_f32_u32(swapped));
  }
  const uint32_t max_bits = vmaxvq_u32(vmax_u);
  auto quiet4 = [](float a, float b, float c, float d) noexcept {
    const float m = std::max(std::max(std::abs(a), std::abs(b)), std::max(std::abs(c), std::abs(d)));
    return m <= 1e-7f;
  };
  if (max_bits <= 0x33D6BF95u && (!lpf || quiet4(lz1, lz2, lw1, lw2)) &&
      (!hpf || quiet4(hz1, hz2, hw1, hw2))) {
    if (lpf) lz1 = lz2 = lw1 = lw2 = zero;
    if (hpf) hz1 = hz2 = hw1 = hw2 = zero;
    if (max_bits != 0u) {
      const uint8x16_t zvec = vdupq_n_u8(0);
      for (uint32_t i = 0; i < 256; i += 4) vst1q_u8(guest_buf + i * 4, zvec);
    }
  } else {
    // Two independent single-biquad passes keep the guest's exact op order while halving FMA chains.
    auto biquad1_pass = [](float* __restrict samples, float b0, float b1, float b2, float a1,
                           float a2, float& __restrict z1_ref, float& __restrict z2_ref) noexcept {
      float z1 = z1_ref;
      float z2 = z2_ref;
      for (uint32_t i = 0; i < 256; ++i) {
        const float x = samples[i];
        const float y = __builtin_fmaf(x, b0, z1);
        const float p1 = y * a1;
        const float p2 = y * a2;
        const float nz1 = __builtin_fmaf(x, b1, -p1) + z2;
        const float nz2 = __builtin_fmaf(x, b2, -p2);
        samples[i] = y;
        z1 = nz1;
        z2 = nz2;
      }
      z1_ref = z1;
      z2_ref = z2;
    };
    if (lpf) {
      const float lb0 = gta4nx_ldf(base, self + 4), lb1 = gta4nx_ldf(base, self + 8);
      const float lb2 = gta4nx_ldf(base, self + 12), la1 = gta4nx_ldf(base, self + 16);
      const float la2 = gta4nx_ldf(base, self + 20);
      biquad1_pass(s, lb0, lb1, lb2, la1, la2, lz1, lz2);
      biquad1_pass(s, lb0, lb1, lb2, la1, la2, lw1, lw2);
    }
    if (hpf) {
      const float hb0 = gta4nx_ldf(base, self + 40), hb1 = gta4nx_ldf(base, self + 44);
      const float hb2 = gta4nx_ldf(base, self + 48), ha1 = gta4nx_ldf(base, self + 52);
      const float ha2 = gta4nx_ldf(base, self + 56);
      biquad1_pass(s, hb0, hb1, hb2, ha1, ha2, hz1, hz2);
      biquad1_pass(s, hb0, hb1, hb2, ha1, ha2, hw1, hw2);
    }
    for (uint32_t i = 0; i < 256; i += 4) {
      vst1q_u8(guest_buf + i * 4, vrev32q_u8(vreinterpretq_u8_f32(vld1q_f32(&s[i]))));
    }
  }

  // State back to the voice; values with a zero exponent (denormals) become `zero`.
  auto keep = [zero](float v) {
    return (std::bit_cast<uint32_t>(v) & 0x7F800000u) != 0 ? v : zero;
  };
  gta4nx_stf(base, self + 24, keep(lz1));
  gta4nx_stf(base, self + 32, keep(lw1));
  gta4nx_stf(base, self + 28, keep(lz2));
  gta4nx_stf(base, self + 36, keep(lw2));
  gta4nx_stf(base, self + 60, keep(hz1));
  gta4nx_stf(base, self + 68, keep(hw1));
  gta4nx_stf(base, self + 64, keep(hz2));
  gta4nx_stf(base, self + 72, keep(hw2));
  ctx.r3.s64 = 0;
  ctx.r1.u64 = saved_r1;
}'''

assert saf_txt.count(old_829321a0) == 1, 'old_829321a0 not unique'
saf_path.write_text(saf_txt.replace(old_829321a0, new_829321a0, 1))
print('OK: switch_audio_fast.cpp updated')

# 2. graphics_system.h: raise NativeCommand::RecycleInPlace kKeptBytes from 1024 to 8192
gsh_path = sdk / 'src/graphics/gta4_native/graphics_system.h'
gsh_txt = gsh_path.read_text()
old_kept = '      constexpr size_t kKeptBytes = 1024;'
new_kept = '      constexpr size_t kKeptBytes = 8192;'
assert gsh_txt.count(old_kept) == 1, 'kKeptBytes not unique'
gsh_path.write_text(gsh_txt.replace(old_kept, new_kept, 1))
print('OK: graphics_system.h kKeptBytes = 8192')

# 3. command_processor.cpp: wake event in CallInThread & reduce 500 yields -> 16
cp_path = sdk / 'src/graphics/command_processor.cpp'
cp_txt = cp_path.read_text()
old_cit = '''  } else {
    pending_fns_.push(std::move(fn));
  }'''
new_cit = '''  } else {
    pending_fns_.push(std::move(fn));
    if (write_ptr_index_event_) {
      write_ptr_index_event_->Set();
    }
  }'''
assert cp_txt.count(old_cit) == 1, 'old_cit not unique'
cp_txt = cp_txt.replace(old_cit, new_cit, 1)

old_spin = '        if (loop_count > 500) {'
new_spin = '        if (loop_count > 16) {'
assert cp_txt.count(old_spin) == 1, 'old_spin not unique'
cp_txt = cp_txt.replace(old_spin, new_spin, 1)
cp_path.write_text(cp_txt)
print('OK: command_processor.cpp updated')

# 4. graphics_system.cpp: batch vkCmdBindVertexBuffers in RecordPrimitive & RecordIndexedPrimitive
gsc_path = sdk / 'src/graphics/gta4_native/graphics_system.cpp'
gsc_txt = gsc_path.read_text()

old_prim_vb = '''  for (uint32_t rem_streams = stream_encoded & 0xFFFFu; rem_streams;) {
    const uint32_t stream = uint32_t(__builtin_ctz(rem_streams));
    rem_streams &= rem_streams - 1u;
    const auto& stream_state = command.pipeline_state->vertex_streams[stream];
    const auto& resource = command.vertex_buffers[stream];
    if (!stream_state.stride || !resource || stream_state.offset >= resource->payload.size()) {
      static std::atomic<uint64_t> stream_rejection_count{0};
      const uint64_t count = NextNativeTraceDiagnosticCount(stream_rejection_count);
      if (count <= 64 || !(count % 1024)) {
        REXLOG_WARN(
            "gta4-native-diag: vertex stream reject #{} indexed=false stream={} "
            "state-handle={:08X} snapshot-handle={:08X} stride={} offset={} "
            "resource={} resource-size={}",
            count, stream, stream_state.buffer,
            LoadGuestWord(command.device_snapshot, kStreamBufferBase + stream * sizeof(uint32_t)),
            stream_state.stride, stream_state.offset, resource ? "yes" : "no",
            resource ? resource->payload.size() : 0);
      }
      return fail("vertex-stream-resource");
    }
    const uint64_t vertex_end = uint64_t(draw.start_vertex) + uint64_t(draw.vertex_count);
    const uint64_t required_size =
        uint64_t(stream_state.offset) + vertex_end * uint64_t(stream_state.stride);
    if (required_size > resource->payload.size()) {
      return fail("vertex-stream-bounds");
    }
    NativeUploadAllocation stream_allocation;
    if (!UploadBufferResource(resource, command_buffer, false, false, command.pipeline_state.get(),
                              stream, resources, stream_allocation)) {
      return fail("vertex-stream-upload");
    }
    const VkDeviceSize stream_offset = stream_allocation.offset + stream_state.offset;
    profile::CpuCall(profile::CpuOp::kDriverBind, [&] { return BindNativeVertexBuffer(command_buffer, stream, stream_allocation.buffer, stream_offset); });
  }'''

new_prim_vb = '''  {
    std::array<VkBuffer, kVertexStreamCount> pending_buffers{};
    std::array<VkDeviceSize, kVertexStreamCount> pending_offsets{};
    uint32_t dirty_bind_mask = 0;
    const bool dedupe_vb = REXCVAR_GET(gta4_native_dedupe_vertex_bindings);
    const uint64_t cmd_identity = NativeVulkanHandleIdentity(command_buffer);
    for (uint32_t rem_streams = stream_encoded & 0xFFFFu; rem_streams;) {
      const uint32_t stream = uint32_t(__builtin_ctz(rem_streams));
      rem_streams &= rem_streams - 1u;
      const auto& stream_state = command.pipeline_state->vertex_streams[stream];
      const auto& resource = command.vertex_buffers[stream];
      if (!stream_state.stride || !resource || stream_state.offset >= resource->payload.size()) {
        static std::atomic<uint64_t> stream_rejection_count{0};
        const uint64_t count = NextNativeTraceDiagnosticCount(stream_rejection_count);
        if (count <= 64 || !(count % 1024)) {
          REXLOG_WARN(
              "gta4-native-diag: vertex stream reject #{} indexed=false stream={} "
              "state-handle={:08X} snapshot-handle={:08X} stride={} offset={} "
              "resource={} resource-size={}",
              count, stream, stream_state.buffer,
              LoadGuestWord(command.device_snapshot, kStreamBufferBase + stream * sizeof(uint32_t)),
              stream_state.stride, stream_state.offset, resource ? "yes" : "no",
              resource ? resource->payload.size() : 0);
        }
        return fail("vertex-stream-resource");
      }
      const uint64_t vertex_end = uint64_t(draw.start_vertex) + uint64_t(draw.vertex_count);
      const uint64_t required_size =
          uint64_t(stream_state.offset) + vertex_end * uint64_t(stream_state.stride);
      if (required_size > resource->payload.size()) {
        return fail("vertex-stream-bounds");
      }
      NativeUploadAllocation stream_allocation;
      if (!UploadBufferResource(resource, command_buffer, false, false, command.pipeline_state.get(),
                                stream, resources, stream_allocation)) {
        return fail("vertex-stream-upload");
      }
      const VkDeviceSize stream_offset = stream_allocation.offset + stream_state.offset;
      const bool changed = native_draw_state_cache_.UpdateVertexBuffer(
          cmd_identity, stream, NativeVulkanHandleIdentity(stream_allocation.buffer),
          uint64_t(stream_offset));
      if (changed || !dedupe_vb) {
        pending_buffers[stream] = stream_allocation.buffer;
        pending_offsets[stream] = stream_offset;
        dirty_bind_mask |= (1u << stream);
      }
    }
    if (dirty_bind_mask) {
      profile::CpuCall(profile::CpuOp::kDriverBind, [&] {
        FlushDirtyVertexBufferRuns(dfn, command_buffer, pending_buffers.data(),
                                   pending_offsets.data(), dirty_bind_mask);
      });
    }
  }'''

assert gsc_txt.count(old_prim_vb) == 1, 'old_prim_vb not unique'
gsc_txt = gsc_txt.replace(old_prim_vb, new_prim_vb, 1)

helper_anchor = 'void Gta4NativeGraphicsSystem::BindNativeVertexBuffer('
helper_code = '''template <typename VulkanFunctions>
static inline void FlushDirtyVertexBufferRuns(const VulkanFunctions& dfn,
                                              VkCommandBuffer command_buffer,
                                              const VkBuffer* buffers,
                                              const VkDeviceSize* offsets,
                                              uint32_t dirty_bind_mask) {
  while (dirty_bind_mask) {
    const uint32_t first = uint32_t(__builtin_ctz(dirty_bind_mask));
    const uint32_t count = uint32_t(__builtin_ctz(~(dirty_bind_mask >> first)));
    dfn.vkCmdBindVertexBuffers(command_buffer, first, count, buffers + first, offsets + first);
    const uint32_t clear_mask = (count >= 32u) ? ~0u : (((1u << count) - 1u) << first);
    dirty_bind_mask &= ~clear_mask;
  }
}

'''
assert gsc_txt.count(helper_anchor) == 1, 'helper_anchor not unique'
gsc_txt = gsc_txt.replace(helper_anchor, helper_code + helper_anchor, 1)

old_idx_vb = '''  for (uint32_t rem_streams = stream_encoded & 0xFFFFu; rem_streams;) {
    const uint32_t stream = uint32_t(__builtin_ctz(rem_streams));
    rem_streams &= rem_streams - 1u;
    const auto& stream_state = command.pipeline_state->vertex_streams[stream];
    const auto& resource = command.vertex_buffers[stream];
    if (!stream_state.stride || !resource || stream_state.offset >= resource->payload.size()) {
      static std::atomic<uint64_t> stream_rejection_count{0};
      const uint64_t count = NextNativeTraceDiagnosticCount(stream_rejection_count);
      if (count <= 64 || !(count % 1024)) {
        REXLOG_WARN(
            "gta4-native-diag: vertex stream reject #{} indexed=true stream={} "
            "state-handle={:08X} snapshot-handle={:08X} stride={} offset={} "
            "resource={} resource-size={}",
            count, stream, stream_state.buffer,
            LoadGuestWord(command.device_snapshot, kStreamBufferBase + stream * sizeof(uint32_t)),
            stream_state.stride, stream_state.offset, resource ? "yes" : "no",
            resource ? resource->payload.size() : 0);
      }
      return fail("vertex-stream-resource");
    }
    NativeUploadAllocation stream_allocation;
    if (!UploadBufferResource(resource, command_buffer, false, false, command.pipeline_state.get(),
                              stream, resources, stream_allocation)) {
      return fail("vertex-stream-upload");
    }
    const VkDeviceSize stream_offset = stream_allocation.offset + stream_state.offset;
    profile::CpuCall(profile::CpuOp::kDriverBind, [&] { return BindNativeVertexBuffer(command_buffer, stream, stream_allocation.buffer, stream_offset); });
  }'''

new_idx_vb = '''  {
    std::array<VkBuffer, kVertexStreamCount> pending_buffers{};
    std::array<VkDeviceSize, kVertexStreamCount> pending_offsets{};
    uint32_t dirty_bind_mask = 0;
    const bool dedupe_vb = REXCVAR_GET(gta4_native_dedupe_vertex_bindings);
    const uint64_t cmd_identity = NativeVulkanHandleIdentity(command_buffer);
    for (uint32_t rem_streams = stream_encoded & 0xFFFFu; rem_streams;) {
      const uint32_t stream = uint32_t(__builtin_ctz(rem_streams));
      rem_streams &= rem_streams - 1u;
      const auto& stream_state = command.pipeline_state->vertex_streams[stream];
      const auto& resource = command.vertex_buffers[stream];
      if (!stream_state.stride || !resource || stream_state.offset >= resource->payload.size()) {
        static std::atomic<uint64_t> stream_rejection_count{0};
        const uint64_t count = NextNativeTraceDiagnosticCount(stream_rejection_count);
        if (count <= 64 || !(count % 1024)) {
          REXLOG_WARN(
              "gta4-native-diag: vertex stream reject #{} indexed=true stream={} "
              "state-handle={:08X} snapshot-handle={:08X} stride={} offset={} "
              "resource={} resource-size={}",
              count, stream, stream_state.buffer,
              LoadGuestWord(command.device_snapshot, kStreamBufferBase + stream * sizeof(uint32_t)),
              stream_state.stride, stream_state.offset, resource ? "yes" : "no",
              resource ? resource->payload.size() : 0);
        }
        return fail("vertex-stream-resource");
      }
      NativeUploadAllocation stream_allocation;
      if (!UploadBufferResource(resource, command_buffer, false, false, command.pipeline_state.get(),
                                stream, resources, stream_allocation)) {
        return fail("vertex-stream-upload");
      }
      const VkDeviceSize stream_offset = stream_allocation.offset + stream_state.offset;
      const bool changed = native_draw_state_cache_.UpdateVertexBuffer(
          cmd_identity, stream, NativeVulkanHandleIdentity(stream_allocation.buffer),
          uint64_t(stream_offset));
      if (changed || !dedupe_vb) {
        pending_buffers[stream] = stream_allocation.buffer;
        pending_offsets[stream] = stream_offset;
        dirty_bind_mask |= (1u << stream);
      }
    }
    if (dirty_bind_mask) {
      profile::CpuCall(profile::CpuOp::kDriverBind, [&] {
        FlushDirtyVertexBufferRuns(dfn, command_buffer, pending_buffers.data(),
                                   pending_offsets.data(), dirty_bind_mask);
      });
    }
  }'''

assert gsc_txt.count(old_idx_vb) == 1, 'old_idx_vb not unique'
gsc_txt = gsc_txt.replace(old_idx_vb, new_idx_vb, 1)
gsc_path.write_text(gsc_txt)
print('OK: graphics_system.cpp batched vkCmdBindVertexBuffers updated')

# 5. build-pgo-ubo-audio-sync-base9.ninja: upgrade 22 hot non-PGO TUs from -O2 to -O3
hot_o3_tus = {5, 7, 12, 13, 16, 24, 30, 39, 44, 46, 50, 60, 62, 64, 65, 66, 72, 76, 77, 83, 85, 86}
pgo_tus = {0, 3, 10, 29, 70, 71, 73, 78}
assert hot_o3_tus.isdisjoint(pgo_tus)

ninja_path = pathlib.Path('/src/build_combo/build-pgo-ubo-audio-sync-base9.ninja')
lines = ninja_path.read_text().splitlines(keepends=True)
changed_tus = []
i = 0
while i < len(lines):
    m = re.search(r'gta4_recomp\.(\d+)\.cpp\.obj:', lines[i])
    if m:
        tu = int(m.group(1))
        if tu in hot_o3_tus:
            for j in range(i + 1, min(len(lines), i + 7)):
                if lines[j].startswith('  FLAGS ='):
                    assert '-fprofile-use' not in lines[j], f'PGO unexpected in TU {tu}'
                    if lines[j].rstrip().endswith(' -O2'):
                        lines[j] = lines[j].rstrip()[:-3] + '-O3\n'
                        changed_tus.append(tu)
                    break
    i += 1
ninja_path.write_text(''.join(lines))
print(f'OK: ninja upgraded {len(changed_tus)} TUs to -O3: {sorted(changed_tus)}')
