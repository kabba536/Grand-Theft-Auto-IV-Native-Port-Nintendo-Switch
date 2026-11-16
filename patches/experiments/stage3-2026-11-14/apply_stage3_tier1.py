#!/usr/bin/env python3
from pathlib import Path

ROOT = Path('/src/lra35/glue/rexglue-sdk-main')


def replace_exact(rel_path: str, old: str, new: str) -> None:
    p = ROOT / rel_path
    text = p.read_text(encoding='utf-8')
    count = text.count(old)
    assert count == 1, f'{rel_path}: expected 1 match, got {count}'
    p.write_text(text.replace(old, new, 1), encoding='utf-8')
    print(f'[ok] patched {rel_path}')


# 1. gta4_audio_ramped_mix.cpp: restore -102 dB gta4_audio_skip_inaudible gate
replace_exact(
    'gta4-recomp/src/gta4_audio_ramped_mix.cpp',
    '''#include <rex/hook.h>
#include "gta4_init.h"
#include "gta4_audio_ramped_mix.h"

REX_HOOK_RAW(sub_82199BC8) {''',
    '''#include <rex/cvar.h>
#include <rex/hook.h>
#if defined(__SWITCH__) && defined(__ARM_NEON)
#include <arm_neon.h>
#endif
#include "gta4_init.h"
#include "gta4_audio_ramped_mix.h"

REXCVAR_DECLARE(bool, gta4_audio_skip_inaudible);

REX_HOOK_RAW(sub_82199BC8) {'''
)

replace_exact(
    'gta4-recomp/src/gta4_audio_ramped_mix.cpp',
    '''  REX_STORE_U64(ctx.r1.u32 - 8, ctx.r31.u64);
  ctx.fpscr.enableFlushMode();
  const auto result = gta4::audio::AccumulateRamped256(''',
    '''  ctx.fpscr.enableFlushMode();
  if (REXCVAR_GET(gta4_audio_skip_inaudible)) {
#if defined(__SWITCH__) && defined(__ARM_NEON)
    auto load_gain = [](const uint8_t* p) {
      return vreinterpretq_f32_u8(vrev32q_u8(vld1q_u8(p)));
    };
    const float32x4_t g_start = load_gain(REX_RAW_ADDR(initial_gain));
    const float32x4_t g_step = load_gain(REX_RAW_ADDR(gain_step));
    const float32x4_t g_end = vfmaq_n_f32(g_start, g_step, 63.0f);
    const float32x4_t peak = vmaxq_f32(vabsq_f32(g_start), vabsq_f32(g_end));
    if (vminvq_u32(vcltq_f32(peak, vdupq_n_f32(7.62939453125e-06f))) != 0) {
      return;
    }
#endif
  }
  REX_STORE_U64(ctx.r1.u32 - 8, ctx.r31.u64);
  const auto result = gta4::audio::AccumulateRamped256('''
)

# 2. switch_audio_fast.cpp: native NEON + -102 dB zero-fill for loc_821999F0
replace_exact(
    'gta4-recomp/src/switch_audio_fast.cpp',
    '''#include <arm_neon.h>
#include <climits>
#include <cmath>''',
    '''#include <arm_neon.h>
#include <climits>
#include <cmath>
#include <cstring>

REXCVAR_DECLARE(bool, gta4_audio_skip_inaudible);'''
)

replace_exact(
    'gta4-recomp/src/switch_audio_fast.cpp',
    '''loc_821999F0:
	// mr r9,r3
	ctx.r9.u64 = ctx.r3.u64;
	// li r11,64
	ctx.r11.s64 = 64;
loc_821999F8:
	// mr r8,r10
	ctx.r8.u64 = ctx.r10.u64;
	// vor v13,v0,v0
	simde_mm_store_si128((simde__m128i*)v13.u8, simde_mm_load_si128((simde__m128i*)v0.u8));
	// addi r11,r11,-1
	ctx.r11.s64 = ctx.r11.s64 + -1;
	// vaddfp v0,v0,v12
	ctx.fpscr.enableFlushMode();
	simde_mm_store_ps(v0.f32, simde_mm_add_ps(simde_mm_load_ps(v0.f32), simde_mm_load_ps(v12.f32)));
	// addi r10,r10,16
	ctx.r10.s64 = ctx.r10.s64 + 16;
	// cmplwi cr6,r11,0
	cr6.compare<uint32_t>(ctx.r11.u32, 0, xer);
	// lvx128 v11,r0,r8
	ea = (ctx.r8.u32) & ~0xF;
	simde_mm_store_si128((simde__m128i*)v11.u8, simde_mm_shuffle_epi8(simde_mm_load_si128((simde__m128i*)REX_RAW_ADDR(ea)), simde_mm_load_si128((simde__m128i*)VectorMaskL)));
	// vmulfp128 v13,v11,v13
	simde_mm_store_ps(v13.f32, simde_mm_mul_ps(simde_mm_load_ps(v11.f32), simde_mm_load_ps(v13.f32)));
	// stvx128 v13,r0,r9
	ea = (ctx.r9.u32) & ~0xF;
	simde_mm_store_si128((simde__m128i*)REX_RAW_ADDR(ea), simde_mm_shuffle_epi8(simde_mm_load_si128((simde__m128i*)v13.u8), simde_mm_load_si128((simde__m128i*)VectorMaskL)));
	// addi r9,r9,16
	ctx.r9.s64 = ctx.r9.s64 + 16;
	// bne cr6,0x821999f8
	if (!cr6.eq) goto loc_821999F8;
	// stfs f13,4(r31)''',
    '''loc_821999F0:
#if defined(__ARM_NEON)
	{
		const uint32_t dst_ea = ctx.r3.u32 & ~15u;
		const uint32_t src_ea = ctx.r10.u32 & ~15u;
		const uint64_t dst_end = uint64_t(dst_ea) + 1024;
		const uint64_t src_end = uint64_t(src_ea) + 1024;
		const bool dst_ok = dst_end <= 0x100000000ull && !(dst_ea < 0xE0000000u && dst_end > 0xE0000000ull);
		const bool src_ok = src_end <= 0x100000000ull && !(src_ea < 0xE0000000u && src_end > 0xE0000000ull);
		if (dst_ok && src_ok) {
			ctx.fpscr.enableFlushMode();
			uint8_t* dst_ptr = REX_RAW_ADDR(dst_ea);
			const uint8_t* src_ptr = REX_RAW_ADDR(src_ea);
			const float32x4_t g_start = vld1q_f32(v0.f32);
			const float32x4_t g_step = vld1q_f32(v12.f32);
			if (REXCVAR_GET(gta4_audio_skip_inaudible)) {
				const float32x4_t g_end = vfmaq_n_f32(g_start, g_step, 63.0f);
				const float32x4_t peak = vmaxq_f32(vabsq_f32(g_start), vabsq_f32(g_end));
				if (vminvq_u32(vcltq_f32(peak, vdupq_n_f32(7.62939453125e-06f))) != 0) {
					std::memset(dst_ptr, 0, 1024);
					goto loc_82199A20_done;
				}
			}
			float32x4_t g = g_start;
			for (uint32_t off = 0; off < 1024; off += 64) {
				const float32x4_t g0 = g;
				const float32x4_t g1 = vaddq_f32(g0, g_step);
				const float32x4_t g2 = vaddq_f32(g1, g_step);
				const float32x4_t g3 = vaddq_f32(g2, g_step);
				g = vaddq_f32(g3, g_step);
				const float32x4_t s0 = vreinterpretq_f32_u8(vrev32q_u8(vld1q_u8(src_ptr + off + 0)));
				const float32x4_t s1 = vreinterpretq_f32_u8(vrev32q_u8(vld1q_u8(src_ptr + off + 16)));
				const float32x4_t s2 = vreinterpretq_f32_u8(vrev32q_u8(vld1q_u8(src_ptr + off + 32)));
				const float32x4_t s3 = vreinterpretq_f32_u8(vrev32q_u8(vld1q_u8(src_ptr + off + 48)));
				vst1q_u8(dst_ptr + off + 0, vrev32q_u8(vreinterpretq_u8_f32(vmulq_f32(s0, g0))));
				vst1q_u8(dst_ptr + off + 16, vrev32q_u8(vreinterpretq_u8_f32(vmulq_f32(s1, g1))));
				vst1q_u8(dst_ptr + off + 32, vrev32q_u8(vreinterpretq_u8_f32(vmulq_f32(s2, g2))));
				vst1q_u8(dst_ptr + off + 48, vrev32q_u8(vreinterpretq_u8_f32(vmulq_f32(s3, g3))));
			}
			goto loc_82199A20_done;
		}
	}
#endif
	// mr r9,r3
	ctx.r9.u64 = ctx.r3.u64;
	// li r11,64
	ctx.r11.s64 = 64;
loc_821999F8:
	// mr r8,r10
	ctx.r8.u64 = ctx.r10.u64;
	// vor v13,v0,v0
	simde_mm_store_si128((simde__m128i*)v13.u8, simde_mm_load_si128((simde__m128i*)v0.u8));
	// addi r11,r11,-1
	ctx.r11.s64 = ctx.r11.s64 + -1;
	// vaddfp v0,v0,v12
	ctx.fpscr.enableFlushMode();
	simde_mm_store_ps(v0.f32, simde_mm_add_ps(simde_mm_load_ps(v0.f32), simde_mm_load_ps(v12.f32)));
	// addi r10,r10,16
	ctx.r10.s64 = ctx.r10.s64 + 16;
	// cmplwi cr6,r11,0
	cr6.compare<uint32_t>(ctx.r11.u32, 0, xer);
	// lvx128 v11,r0,r8
	ea = (ctx.r8.u32) & ~0xF;
	simde_mm_store_si128((simde__m128i*)v11.u8, simde_mm_shuffle_epi8(simde_mm_load_si128((simde__m128i*)REX_RAW_ADDR(ea)), simde_mm_load_si128((simde__m128i*)VectorMaskL)));
	// vmulfp128 v13,v11,v13
	simde_mm_store_ps(v13.f32, simde_mm_mul_ps(simde_mm_load_ps(v11.f32), simde_mm_load_ps(v13.f32)));
	// stvx128 v13,r0,r9
	ea = (ctx.r9.u32) & ~0xF;
	simde_mm_store_si128((simde__m128i*)REX_RAW_ADDR(ea), simde_mm_shuffle_epi8(simde_mm_load_si128((simde__m128i*)v13.u8), simde_mm_load_si128((simde__m128i*)VectorMaskL)));
	// addi r9,r9,16
	ctx.r9.s64 = ctx.r9.s64 + 16;
	// bne cr6,0x821999f8
	if (!cr6.eq) goto loc_821999F8;
loc_82199A20_done:
	// stfs f13,4(r31)'''
)

# 3. CaptureBufferResource zero-allocation cache hit
replace_exact(
    'src/graphics/gta4_native/graphics_system.cpp',
    '''  std::vector<uint8_t> payload(data, data + data_size);
  const uint64_t content_hash = XXH3_64bits(payload.data(), payload.size());
  std::lock_guard lock(buffer_resource_mutex_);
  auto existing = buffer_resources_.find(handle);
  if (existing != buffer_resources_.end()) {
    const auto& resource = existing->second;
    if (resource && resource->flags == flags && resource->guest_address == data_address &&
        resource->guest_size == data_size && resource->content_hash == content_hash &&
        resource->payload == payload) {
      cache_slot.changed_streak = 0;
      dirty_buffer_handles_.erase(handle);
      resource->last_used_frame.store(
          g_native_memory_profile_event_frame.load(std::memory_order_relaxed),
          std::memory_order_relaxed);
      remember(resource);
      return resource;
    }
  }

  if (matching_cache_entry && cache_slot.changed_streak < 255) ++cache_slot.changed_streak;
  BumpBufferCaptureStat(4);
  BumpBufferCaptureStat(5, data_size);
  auto resource = std::make_shared<NativeBufferResource>();
  resource->handle = handle;
  resource->flags = flags;
  resource->guest_address = data_address;
  resource->guest_size = data_size;
  resource->content_hash = content_hash;
  resource->generation = next_buffer_generation_++;
  resource->created_frame = g_native_memory_profile_event_frame.load(std::memory_order_relaxed);
  resource->last_used_frame.store(resource->created_frame, std::memory_order_relaxed);
  resource->payload = std::move(payload);''',
    '''  const uint64_t content_hash = XXH3_64bits(data, data_size);
  std::lock_guard lock(buffer_resource_mutex_);
  auto existing = buffer_resources_.find(handle);
  if (existing != buffer_resources_.end()) {
    const auto& resource = existing->second;
    if (resource && resource->flags == flags && resource->guest_address == data_address &&
        resource->guest_size == data_size && resource->content_hash == content_hash &&
        resource->payload.size() == data_size &&
        std::memcmp(resource->payload.data(), data, data_size) == 0) {
      cache_slot.changed_streak = 0;
      dirty_buffer_handles_.erase(handle);
      resource->last_used_frame.store(
          g_native_memory_profile_event_frame.load(std::memory_order_relaxed),
          std::memory_order_relaxed);
      remember(resource);
      return resource;
    }
  }

  if (matching_cache_entry && cache_slot.changed_streak < 255) ++cache_slot.changed_streak;
  BumpBufferCaptureStat(4);
  BumpBufferCaptureStat(5, data_size);
  auto resource = std::make_shared<NativeBufferResource>();
  resource->handle = handle;
  resource->flags = flags;
  resource->guest_address = data_address;
  resource->guest_size = data_size;
  resource->content_hash = content_hash;
  resource->generation = next_buffer_generation_++;
  resource->created_frame = g_native_memory_profile_event_frame.load(std::memory_order_relaxed);
  resource->last_used_frame.store(resource->created_frame, std::memory_order_relaxed);
  resource->payload.assign(data, data + data_size);'''
)

# 4. retain_assembled loop fusion
replace_exact(
    'src/graphics/gta4_native/graphics_system.cpp',
    '''        for (const auto& texture : assembled.textures) {
          if (texture && texture->packed_depth_source &&
              std::find(bound.packed_alias_generations.begin(), bound.packed_alias_generations.end(),
                        texture->generation) == bound.packed_alias_generations.end()) {
            bound.packed_alias_generations.push_back(texture->generation);
          }
        }
        {
          // The same inputs RecordNativeFrame's frontbuffer-reader scan reads.
          const uint32_t read_epoch = assembly_protection_epoch_;
          bound.read_epoch = read_epoch;
          const auto mark_read = [read_epoch](const NativeTextureResource* resource) {
            if (resource)
              std::atomic_ref(resource->assembly_read_epoch).store(read_epoch, std::memory_order_relaxed);
          };
          for (const auto& texture : assembled.textures) {
            if (!texture) continue;
            mark_read(texture.get());
            mark_read(texture->packed_depth_source.get());
          }''',
    '''        {
          // The same inputs RecordNativeFrame's frontbuffer-reader scan reads.
          const uint32_t read_epoch = assembly_protection_epoch_;
          bound.read_epoch = read_epoch;
          const auto mark_read = [read_epoch](const NativeTextureResource* resource) {
            if (resource)
              std::atomic_ref(resource->assembly_read_epoch).store(read_epoch, std::memory_order_relaxed);
          };
          for (const auto& texture : assembled.textures) {
            if (!texture) continue;
            if (texture->packed_depth_source &&
                std::find(bound.packed_alias_generations.begin(),
                          bound.packed_alias_generations.end(),
                          texture->generation) == bound.packed_alias_generations.end()) {
              bound.packed_alias_generations.push_back(texture->generation);
            }
            mark_read(texture.get());
            mark_read(texture->packed_depth_source.get());
          }'''
)

# 5a. PrepareFrameTextures bitmask + hoisted default descriptor template
replace_exact(
    'src/graphics/gta4_native/graphics_system.cpp',
    '''  const bool prefetch_commands = REXCVAR_GET(gta4_native_recorder_prefetch);
  for (size_t command_index = 0; command_index < texture_commands.size(); ++command_index) {''',
    '''  static_assert(kShaderTextureCount <= 32, "stage mask requires <= 32 stages");
  constexpr uint32_t kShaderStageMask =
      kShaderTextureCount == 32 ? ~0u : ((1u << kShaderTextureCount) - 1u);
  NativeDrawDescriptorKey default_descriptor_key{};
  default_descriptor_key.layout_epoch = next_cached_descriptor_epoch_;
  default_descriptor_key.images_2d.fill(null_texture_2d_.view);
  default_descriptor_key.images_2d_array.fill(null_texture_2d_array_.view);
  default_descriptor_key.images_3d.fill(null_texture_3d_.view);
  default_descriptor_key.images_cube.fill(null_texture_cube_.view);
  default_descriptor_key.samplers.fill(null_sampler_);
  std::array<uint32_t, kShaderTextureCount> cached_stage_indices{};
  for (uint32_t s = 0; s < kShaderTextureCount; ++s) {
    cached_stage_indices[s] = s;
  }
  const bool indexed_non_paging =
      native_descriptor_backend_ == NativeDescriptorBackend::kIndexed && !native_descriptor_paging_;
  if (indexed_non_paging) {
    if (!native_stable_image_descriptor_table_ || !native_stable_sampler_descriptor_table_ ||
        !native_stable_image_descriptor_table_->IsLive(native_null_image_descriptor_) ||
        !native_stable_sampler_descriptor_table_->IsLive(native_null_sampler_descriptor_)) {
      return false;
    }
  }
  const bool prefetch_commands = REXCVAR_GET(gta4_native_recorder_prefetch);
  for (size_t command_index = 0; command_index < texture_commands.size(); ++command_index) {'''
)

replace_exact(
    'src/graphics/gta4_native/graphics_system.cpp',
    '''    std::array<VkDescriptorImageInfo, kShaderTextureCount> images_2d{};
    std::array<VkDescriptorImageInfo, kShaderTextureCount> images_2d_array{};
    std::array<VkDescriptorImageInfo, kShaderTextureCount> images_3d{};
    std::array<VkDescriptorImageInfo, kShaderTextureCount> images_cube{};
    std::array<VkDescriptorImageInfo, kShaderTextureCount> samplers{};
    std::array<uint64_t, kShaderTextureCount> image_lifetimes{};
    command.descriptor_page = UINT32_MAX;
    command.image_descriptor_epoch = 0;
    command.sampler_descriptor_epoch = 0;
    command.cached_descriptor_epoch = 0;
    command.descriptor_copy = active_descriptor_copy_;
    command.texture_descriptor_indices.fill(0);
    command.sampler_descriptor_indices.fill(0);
    command.draw_descriptor_sets.fill(VK_NULL_HANDLE);
    command.binding_realization.fill(NativeBindingRealization::kUnused);
    command.room_light_input_bindings.reset();
    const bool capture_bulb_bindings = EmissionTraceConfig().pipeline_full_readback &&
        !bulb_full_frame_ && EmissionTraceActive(submitted_frame) && command.pipeline_state &&
        command.pipeline_state->pixel_shader_resource &&
        IsBulbInterferenceFamily(command.pipeline_state->pixel_shader_resource->hash, command.pipeline_state->pixel_shader_resource->filename);
    const bool capture_fire_bindings = FireTraceConfig().enabled &&
        (command.fire_trace || submitted_frame % FireTraceConfig().interval == 0);
    if (capture_fire_bindings || capture_bulb_bindings || TvCommandRole(command) || (PhoneTraceConfig().lineage && command.phone_trace) ||
        (REXCVAR_GET(gta4_native_light_color_delta_probe) == "room" && !room_light_probe_stop_requested_ &&
         command.pipeline_state && command.pipeline_state->pixel_shader_resource &&
         IsDeferredLightShaderFilename(command.pipeline_state->pixel_shader_resource->filename))) {
      command.room_light_input_bindings =
          std::make_shared<std::vector<NativeRoomLightInputBinding>>();
    }
    command.realized_image_mask = 0;
    command.realized_sampler_mask = 0;
    command.guest_null_texture_mask = 0;
    command.failed_texture_mask = 0;
    command.bindings_prepared = false;
    for (uint32_t stage = 0; stage < kShaderTextureCount; ++stage) {
      images_2d[stage] = {VK_NULL_HANDLE, null_texture_2d_.view,
                          VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
      images_2d_array[stage] = {VK_NULL_HANDLE, null_texture_2d_array_.view,
                                VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
      images_3d[stage] = {VK_NULL_HANDLE, null_texture_3d_.view,
                          VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
      images_cube[stage] = {VK_NULL_HANDLE, null_texture_cube_.view,
                            VK_IMAGE_LAYOUT_SHADER_READ_ONLY_OPTIMAL};
      samplers[stage] = {null_sampler_, VK_NULL_HANDLE, VK_IMAGE_LAYOUT_UNDEFINED};
      if (native_descriptor_backend_ == NativeDescriptorBackend::kIndexed && native_descriptor_paging_) {
        command.texture_descriptor_indices[stage] = 0;
        command.sampler_descriptor_indices[stage] = 0;
      } else if (native_descriptor_backend_ == NativeDescriptorBackend::kIndexed) {
        if (!native_stable_image_descriptor_table_ || !native_stable_sampler_descriptor_table_ ||
            !native_stable_image_descriptor_table_->IsLive(native_null_image_descriptor_) ||
            !native_stable_sampler_descriptor_table_->IsLive(native_null_sampler_descriptor_)) {
          return false;
        }
        command.texture_descriptor_indices[stage] = native_null_image_descriptor_.index;
        command.sampler_descriptor_indices[stage] = native_null_sampler_descriptor_.index;
      } else {
        command.texture_descriptor_indices[stage] = stage;
        command.sampler_descriptor_indices[stage] = stage;
      }

      NativeSampler* sampler = nullptr;
      const uint32_t stage_bit = 1u << stage;
      const bool required = (command.used_texture_mask & stage_bit) != 0;
      NativeTextureImage* image = required
          ? prepared_image(command.textures[stage]) : nullptr;
      if (image && command.temporal_scene_binding && command.temporal_scene_stage == stage)
        image = command.temporal_scene_binding;
      if (image == command.temporal_scene_binding && image) {
        image->last_used_frame = active_texture_frame_;
        image->last_use_serial = next_texture_use_serial_++;
        image->last_used_submission = submission_tracker_ ? submission_tracker_->GetCurrentSubmission() : 0;
        StageNativeTextureFlightResources(*image);
      }
      if (image) {
        VkImageView image_view = image->resource.view;
        image_lifetimes[stage] = image->descriptor_lifetime;
        if (!prepared_texture_views_.empty()) {
          if (const auto swapped = prepared_texture_views_.find(image);
              swapped != prepared_texture_views_.end()) {
            image_view = swapped->second.view;
            image_lifetimes[stage] = swapped->second.lifetime;
          }
        }
        switch (image->source->info.dimension) {
          case xenos::DataDimension::k3D:
            images_3d[stage].imageView = image_view;
            break;
          case xenos::DataDimension::kCube:
            images_cube[stage].imageView = image_view;
            break;
          case xenos::DataDimension::k2DOrStacked:
            if (image->source->info.is_stacked) {
              images_2d_array[stage].imageView = image_view;
            } else {
              images_2d[stage].imageView = image_view;
            }
            break;
          default:
            images_2d[stage].imageView = image_view;
            break;
        }
        NativeSamplerKey effective_sampler_key{};
        auto& memo = sampler_memo[stage];
        if (memo.image_lifetime == image->descriptor_lifetime && memo.sampler_index < native_samplers_.size() &&
            std::memcmp(&memo.fetch, &command.texture_fetches[stage], sizeof(memo.fetch)) == 0) {
          sampler = &native_samplers_[memo.sampler_index];
          effective_sampler_key = memo.effective;
        } else {
          sampler = GetOrCreateSampler(command.texture_fetches[stage], image, &effective_sampler_key);
          if (sampler) {
            memo.fetch = command.texture_fetches[stage]; memo.image_lifetime = image->descriptor_lifetime;
            memo.sampler_index = size_t(sampler - native_samplers_.data()); memo.effective = effective_sampler_key;
          }
        }
        if (sampler) {
          samplers[stage].sampler = sampler->sampler;
        }''',
    '''    NativeDrawDescriptorKey descriptor_key = default_descriptor_key;
    command.descriptor_page = UINT32_MAX;
    command.image_descriptor_epoch = 0;
    command.sampler_descriptor_epoch = 0;
    command.cached_descriptor_epoch = 0;
    command.descriptor_copy = active_descriptor_copy_;
    if (native_descriptor_backend_ == NativeDescriptorBackend::kIndexed && native_descriptor_paging_) {
      command.texture_descriptor_indices.fill(0);
      command.sampler_descriptor_indices.fill(0);
    } else if (indexed_non_paging) {
      command.texture_descriptor_indices.fill(native_null_image_descriptor_.index);
      command.sampler_descriptor_indices.fill(native_null_sampler_descriptor_.index);
    } else {
      command.texture_descriptor_indices = cached_stage_indices;
      command.sampler_descriptor_indices = cached_stage_indices;
    }
    command.draw_descriptor_sets.fill(VK_NULL_HANDLE);
    command.binding_realization.fill(NativeBindingRealization::kUnused);
    command.room_light_input_bindings.reset();
    const bool capture_bulb_bindings = EmissionTraceConfig().pipeline_full_readback &&
        !bulb_full_frame_ && EmissionTraceActive(submitted_frame) && command.pipeline_state &&
        command.pipeline_state->pixel_shader_resource &&
        IsBulbInterferenceFamily(command.pipeline_state->pixel_shader_resource->hash, command.pipeline_state->pixel_shader_resource->filename);
    const bool capture_fire_bindings = FireTraceConfig().enabled &&
        (command.fire_trace || submitted_frame % FireTraceConfig().interval == 0);
    if (capture_fire_bindings || capture_bulb_bindings || TvCommandRole(command) || (PhoneTraceConfig().lineage && command.phone_trace) ||
        (REXCVAR_GET(gta4_native_light_color_delta_probe) == "room" && !room_light_probe_stop_requested_ &&
         command.pipeline_state && command.pipeline_state->pixel_shader_resource &&
         IsDeferredLightShaderFilename(command.pipeline_state->pixel_shader_resource->filename))) {
      command.room_light_input_bindings =
          std::make_shared<std::vector<NativeRoomLightInputBinding>>();
    }
    command.realized_image_mask = 0;
    command.realized_sampler_mask = 0;
    command.guest_null_texture_mask = 0;
    command.failed_texture_mask = 0;
    command.bindings_prepared = false;
    for (uint32_t stage_mask = command.used_texture_mask & kShaderStageMask; stage_mask;) {
      const uint32_t stage = uint32_t(__builtin_ctz(stage_mask));
      stage_mask &= stage_mask - 1u;
      const uint32_t stage_bit = 1u << stage;
      const bool required = true;
      NativeSampler* sampler = nullptr;
      NativeTextureImage* image = prepared_image(command.textures[stage]);
      if (image && command.temporal_scene_binding && command.temporal_scene_stage == stage)
        image = command.temporal_scene_binding;
      if (image == command.temporal_scene_binding && image) {
        image->last_used_frame = active_texture_frame_;
        image->last_use_serial = next_texture_use_serial_++;
        image->last_used_submission = submission_tracker_ ? submission_tracker_->GetCurrentSubmission() : 0;
        StageNativeTextureFlightResources(*image);
      }
      if (image) {
        VkImageView image_view = image->resource.view;
        descriptor_key.image_lifetimes[stage] = image->descriptor_lifetime;
        if (!prepared_texture_views_.empty()) {
          if (const auto swapped = prepared_texture_views_.find(image);
              swapped != prepared_texture_views_.end()) {
            image_view = swapped->second.view;
            descriptor_key.image_lifetimes[stage] = swapped->second.lifetime;
          }
        }
        switch (image->source->info.dimension) {
          case xenos::DataDimension::k3D:
            descriptor_key.images_3d[stage] = image_view;
            break;
          case xenos::DataDimension::kCube:
            descriptor_key.images_cube[stage] = image_view;
            break;
          case xenos::DataDimension::k2DOrStacked:
            if (image->source->info.is_stacked) {
              descriptor_key.images_2d_array[stage] = image_view;
            } else {
              descriptor_key.images_2d[stage] = image_view;
            }
            break;
          default:
            descriptor_key.images_2d[stage] = image_view;
            break;
        }
        NativeSamplerKey effective_sampler_key{};
        auto& memo = sampler_memo[stage];
        if (memo.image_lifetime == image->descriptor_lifetime && memo.sampler_index < native_samplers_.size() &&
            std::memcmp(&memo.fetch, &command.texture_fetches[stage], sizeof(memo.fetch)) == 0) {
          sampler = &native_samplers_[memo.sampler_index];
          effective_sampler_key = memo.effective;
        } else {
          sampler = GetOrCreateSampler(command.texture_fetches[stage], image, &effective_sampler_key);
          if (sampler) {
            memo.fetch = command.texture_fetches[stage]; memo.image_lifetime = image->descriptor_lifetime;
            memo.sampler_index = size_t(sampler - native_samplers_.data()); memo.effective = effective_sampler_key;
          }
        }
        if (sampler) {
          descriptor_key.samplers[stage] = sampler->sampler;
        }'''
)

replace_exact(
    'src/graphics/gta4_native/graphics_system.cpp',
    '''                fmt::ptr(image->resource.view), fmt::ptr(samplers[stage].sampler), !sampler,''',
    '''                fmt::ptr(image->resource.view), fmt::ptr(descriptor_key.samplers[stage]), !sampler,'''
)

replace_exact(
    'src/graphics/gta4_native/graphics_system.cpp',
    '''        binding.sampler = samplers[stage].sampler;
        binding.image_lifetime = image ? image->descriptor_lifetime : 0;
        if (sampler) binding.sampler_info = sampler->creation_info;
      }
    }

    if (command.failed_texture_mask) {
      // No cached or indexed descriptor tuple is published for a failed draw.
      // BindCommonDrawState rejects it regardless of the selected backend.
      continue;
    }
    if (native_descriptor_backend_ == NativeDescriptorBackend::kIndexed && !native_descriptor_paging_) {
      indexed_draw_commands.push_back(&command);
      continue;
    }

    NativeDrawDescriptorKey descriptor_key{};
    descriptor_key.layout_epoch = next_cached_descriptor_epoch_;
    descriptor_key.image_lifetimes = image_lifetimes;
    for (uint32_t stage = 0; stage < kShaderTextureCount; ++stage) {
      descriptor_key.images_2d[stage] = images_2d[stage].imageView;
      descriptor_key.images_2d_array[stage] = images_2d_array[stage].imageView;
      descriptor_key.images_3d[stage] = images_3d[stage].imageView;
      descriptor_key.images_cube[stage] = images_cube[stage].imageView;
      descriptor_key.samplers[stage] = samplers[stage].sampler;
    }''',
    '''        binding.sampler = descriptor_key.samplers[stage];
        binding.image_lifetime = image ? image->descriptor_lifetime : 0;
        if (sampler) binding.sampler_info = sampler->creation_info;
      }
    }

    if (command.failed_texture_mask) {
      // No cached or indexed descriptor tuple is published for a failed draw.
      // BindCommonDrawState rejects it regardless of the selected backend.
      continue;
    }
    if (native_descriptor_backend_ == NativeDescriptorBackend::kIndexed && !native_descriptor_paging_) {
      indexed_draw_commands.push_back(&command);
      continue;
    }'''
)

# 5b. native_working_set.h & native_descriptor_working_set.inc active_mask + page check
replace_exact(
    'src/graphics/gta4_native/native_working_set.h',
    '''  std::optional<Assignment> Assign(const std::array<uint64_t, Stages>& images,
                                   const std::array<uint64_t, Stages>& samplers) {
    if (!maximum_pages_)
      return std::nullopt;
    if (!active_pages_ && !StartPage())
      return std::nullopt;
    auto fits = [&](const Page& page) {
      return page.image_lookup.size() + Missing(page.image_lookup, images) <= image_capacity_ &&
             page.sampler_lookup.size() + Missing(page.sampler_lookup, samplers) <= sampler_capacity_;
    };
    if (!fits(pages_[active_pages_ - 1])) {
      if (!StartPage() || !fits(pages_[active_pages_ - 1]))
        return std::nullopt;
    }
    Assignment out;
    out.page = uint32_t(active_pages_ - 1);
    Page& page = pages_[out.page];
    for (size_t i = 0; i < Stages; ++i) {
      out.images[i] = Insert(page.image_lookup, page.previous_images, page.images, images[i],
                             image_capacity_, page.image_free_cursor);
      out.samplers[i] = Insert(page.sampler_lookup, page.previous_samplers, page.samplers, samplers[i],
                               sampler_capacity_, page.sampler_free_cursor);
      if (out.images[i] == UINT32_MAX || out.samplers[i] == UINT32_MAX)
        return std::nullopt;
    }
    return out;
  }''',
    '''  static constexpr uint32_t kAllStagesMask =
      Stages >= 32 ? ~0u : ((1u << Stages) - 1u);
  std::optional<Assignment> Assign(const std::array<uint64_t, Stages>& images,
                                   const std::array<uint64_t, Stages>& samplers,
                                   uint32_t active_mask = kAllStagesMask) {
    if (!maximum_pages_)
      return std::nullopt;
    if (!active_pages_ && !StartPage())
      return std::nullopt;
    active_mask &= kAllStagesMask;
    auto fits = [&](const Page& page) {
      return page.image_lookup.size() + Missing(page.image_lookup, images, active_mask) <= image_capacity_ &&
             page.sampler_lookup.size() + Missing(page.sampler_lookup, samplers, active_mask) <= sampler_capacity_;
    };
    if (!fits(pages_[active_pages_ - 1])) {
      if (!StartPage() || !fits(pages_[active_pages_ - 1]))
        return std::nullopt;
    }
    Assignment out{};
    out.page = uint32_t(active_pages_ - 1);
    Page& page = pages_[out.page];
    for (uint32_t m = active_mask; m;) {
      const size_t i = size_t(__builtin_ctz(m));
      m &= m - 1u;
      out.images[i] = Insert(page.image_lookup, page.previous_images, page.images, images[i],
                             image_capacity_, page.image_free_cursor);
      out.samplers[i] = Insert(page.sampler_lookup, page.previous_samplers, page.samplers, samplers[i],
                               sampler_capacity_, page.sampler_free_cursor);
      if (out.images[i] == UINT32_MAX || out.samplers[i] == UINT32_MAX)
        return std::nullopt;
    }
    return out;
  }'''
)

replace_exact(
    'src/graphics/gta4_native/native_working_set.h',
    '''  static size_t Missing(const FrameGenerationMap<uint64_t, uint32_t>& lookup,
                        const std::array<uint64_t, Stages>& keys) {
    size_t count = 0;
    for (size_t i = 0; i < Stages; ++i)
      if (keys[i] != 0 && !lookup.Find(keys[i]) &&
          std::find(keys.begin(), keys.begin() + i, keys[i]) == keys.begin() + i)
        ++count;
    return count;
  }''',
    '''  static size_t Missing(const FrameGenerationMap<uint64_t, uint32_t>& lookup,
                        const std::array<uint64_t, Stages>& keys,
                        uint32_t active_mask) {
    size_t count = 0;
    for (uint32_t m = active_mask; m;) {
      const size_t i = size_t(__builtin_ctz(m));
      m &= m - 1u;
      const uint64_t k = keys[i];
      if (!k || lookup.Find(k)) continue;
      bool dup = false;
      for (uint32_t p = active_mask & ((1u << i) - 1u); p;) {
        const size_t j = size_t(__builtin_ctz(p));
        p &= p - 1u;
        if (keys[j] == k) {
          dup = true;
          break;
        }
      }
      if (!dup) ++count;
    }
    return count;
  }'''
)

replace_exact(
    'src/graphics/gta4_native/native_descriptor_working_set.inc',
    '''  std::array<uint64_t, kShaderTextureCount> sampler_ids{};
  for (size_t i = 0; i < sampler_ids.size(); ++i)
    sampler_ids[i] =
        key.samplers[i] == null_sampler_ ? 0 : NativeVulkanHandleIdentity(key.samplers[i]);
  const auto assignment = planner.Assign(key.image_lifetimes, sampler_ids);
  if (!assignment) {
    // This is a real per-frame device-budget overflow, not history exhaustion.
    // PrepareFrameTextures will replay its preparation once with exact cached
    // tuples, retaining every draw rather than publishing partial bindings.
    return ActivateCachedDescriptorFallback(NativeDescriptorStatus::kCapacityExhausted,
                                            "per-frame-working-set-overflow");
  }
  const uint32_t page_index =
      assignment->page * NativeFrameContextRing::kSlotCount + active_frame_slot_;
  if (!EnsureIndexedDescriptorPages(page_index + 1))
    return ActivateCachedDescriptorFallback(NativeDescriptorStatus::kCapacityExhausted,
                                            "working-set-page-allocation");
  auto& page = native_descriptor_pages_[page_index];
  const NativeDescriptorImageSlot null_image{1,
                                             {null_texture_2d_.view, null_texture_2d_array_.view,
                                              null_texture_3d_.view, null_texture_cube_.view}};
  if (!(page.image_slots[0] == null_image)) {
    page.image_slots[0] = null_image;
    page.images_dirty = true;
  }
  const NativeDescriptorSamplerSlot null_sampler{1, null_sampler_};
  if (!(page.sampler_slots[0] == null_sampler)) {
    page.sampler_slots[0] = null_sampler;
    page.samplers_dirty = true;
  }
  for (size_t i = 0; i < kShaderTextureCount; ++i) {''',
    '''  constexpr uint32_t kStageMask =
      kShaderTextureCount == 32 ? ~0u : ((1u << kShaderTextureCount) - 1u);
  const uint32_t active_mask = command.used_texture_mask & kStageMask;
  std::array<uint64_t, kShaderTextureCount> sampler_ids{};
  for (uint32_t m = active_mask; m;) {
    const size_t i = size_t(__builtin_ctz(m));
    m &= m - 1u;
    sampler_ids[i] =
        key.samplers[i] == null_sampler_ ? 0 : NativeVulkanHandleIdentity(key.samplers[i]);
  }
  const auto assignment = planner.Assign(key.image_lifetimes, sampler_ids, active_mask);
  if (!assignment) {
    // This is a real per-frame device-budget overflow, not history exhaustion.
    // PrepareFrameTextures will replay its preparation once with exact cached
    // tuples, retaining every draw rather than publishing partial bindings.
    return ActivateCachedDescriptorFallback(NativeDescriptorStatus::kCapacityExhausted,
                                            "per-frame-working-set-overflow");
  }
  const uint32_t page_index =
      assignment->page * NativeFrameContextRing::kSlotCount + active_frame_slot_;
  if (page_index >= native_descriptor_pages_.size() && !EnsureIndexedDescriptorPages(page_index + 1))
    return ActivateCachedDescriptorFallback(NativeDescriptorStatus::kCapacityExhausted,
                                            "working-set-page-allocation");
  auto& page = native_descriptor_pages_[page_index];
  if (page.frame_epoch != planner.epoch()) {
    const NativeDescriptorImageSlot null_image{1,
                                               {null_texture_2d_.view, null_texture_2d_array_.view,
                                                null_texture_3d_.view, null_texture_cube_.view}};
    if (!(page.image_slots[0] == null_image)) {
      page.image_slots[0] = null_image;
      page.images_dirty = true;
    }
    const NativeDescriptorSamplerSlot null_sampler{1, null_sampler_};
    if (!(page.sampler_slots[0] == null_sampler)) {
      page.sampler_slots[0] = null_sampler;
      page.samplers_dirty = true;
    }
  }
  for (uint32_t m = active_mask; m;) {
    const size_t i = size_t(__builtin_ctz(m));
    m &= m - 1u;'''
)
