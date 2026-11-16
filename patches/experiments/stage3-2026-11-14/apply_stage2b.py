from pathlib import Path

root = Path('/src/lra35/glue/rexglue-sdk-main')

# 1. DebugOverlayDialog: don't force continuous 60-80fps UI repaints when idle
p_ovr = root / 'include/rex/ui/overlay/debug_overlay.h'
s = p_ovr.read_text()
if 'WantsContinuousRepaint' not in s:
    t = '  void SetStatsProvider(FrameStatsProvider provider) { stats_provider_ = std::move(provider); }'
    r = t + '\n  bool WantsContinuousRepaint() const override { return false; }'
    assert t in s
    p_ovr.write_text(s.replace(t, r, 1))

# 2. WindowSwitch header: add delayed paint tracking & timeout query
p_wh = root / 'include/rex/ui/window_switch.h'
s = p_wh.read_text()
if 'NextPaintTimeoutNs' not in s:
    t1 = '  void HandlePendingPaint();\n  void HandleCloseRequest();'
    r1 = '  void HandlePendingPaint(uint64_t now_ns);\n  uint64_t NextPaintTimeoutNs(uint64_t now_ns) const;\n  void HandleCloseRequest();'
    t2 = '  // May be called from non-UI threads.\n  void RequestPaintImpl() override;'
    r2 = '  // May be called from non-UI threads.\n  void RequestPaintImpl() override;\n  void RequestPaintAfterNanosecondsImpl(uint64_t delay_ns) override;'
    t3 = '  std::atomic<bool> paint_pending_{false};'
    r3 = '  std::atomic<bool> paint_pending_{false};\n  std::atomic<uint64_t> scheduled_paint_due_ns_{0};'
    assert t1 in s and t2 in s and t3 in s
    p_wh.write_text(s.replace(t1, r1, 1).replace(t2, r2, 1).replace(t3, r3, 1))

# 3. WindowSwitch cpp: schedule due_ns without spinning UI thread when called from OnPaint
p_wc = root / 'src/ui/window_switch.cpp'
s = p_wc.read_text()
if 'NextPaintTimeoutNs' not in s:
    inc_t = '#include <rex/ui/window_switch.h>'
    inc_r = '#include <rex/ui/window_switch.h>\n\n#include <algorithm>\n#include <chrono>'
    assert inc_t in s
    if '#include <chrono>' not in s:
        s = s.replace(inc_t, inc_r, 1)
    t_wc = '''void WindowSwitch::RequestPaintImpl() {
  // Coalesce: at most one pending paint at a time.
  if (paint_pending_.exchange(true, std::memory_order_acq_rel)) {
    return;
  }
  switch_app_context().WakeUILoop();
}

void WindowSwitch::HandlePendingPaint() {
  if (!paint_pending_.exchange(false, std::memory_order_acq_rel)) {
    return;
  }
  // Without focus (HOME menu, sleep, an overlay applet) the display stack may
  // stop taking frames, and a present could block the UI thread.
  if (has_focus_) {
    OnPaint();
  }
}'''
    r_wc = '''void WindowSwitch::RequestPaintImpl() {
  // Coalesce: at most one pending paint at a time.
  if (paint_pending_.exchange(true, std::memory_order_acq_rel)) {
    return;
  }
  if (!switch_app_context().IsInUIThread()) {
    switch_app_context().WakeUILoop();
  }
}

void WindowSwitch::RequestPaintAfterNanosecondsImpl(uint64_t delay_ns) {
  if (delay_ns == 0) {
    RequestPaintImpl();
    return;
  }
  const uint64_t clamped_ns = std::min<uint64_t>(delay_ns, 1'000'000'000ull);
  const auto now = std::chrono::steady_clock::now().time_since_epoch();
  const uint64_t now_ns =
      uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(now).count());
  const uint64_t due_ns = now_ns + clamped_ns;
  uint64_t cur = scheduled_paint_due_ns_.load(std::memory_order_acquire);
  bool updated = false;
  while (cur == 0 || due_ns < cur) {
    if (scheduled_paint_due_ns_.compare_exchange_weak(
            cur, due_ns, std::memory_order_acq_rel, std::memory_order_acquire)) {
      updated = true;
      break;
    }
  }
  // Only signal the UEvent from non-UI threads; on the UI thread the loop
  // recalculates waitMulti timeout right before sleeping.
  if (updated && !paint_pending_.load(std::memory_order_relaxed) &&
      !switch_app_context().IsInUIThread()) {
    switch_app_context().WakeUILoop();
  }
}

uint64_t WindowSwitch::NextPaintTimeoutNs(uint64_t now_ns) const {
  if (paint_pending_.load(std::memory_order_acquire)) {
    return 0;
  }
  const uint64_t due = scheduled_paint_due_ns_.load(std::memory_order_acquire);
  if (due == 0) {
    return UINT64_MAX;
  }
  return now_ns >= due ? 0 : (due - now_ns);
}

void WindowSwitch::HandlePendingPaint(uint64_t now_ns) {
  bool do_paint = paint_pending_.exchange(false, std::memory_order_acq_rel);
  uint64_t due = scheduled_paint_due_ns_.load(std::memory_order_acquire);
  if (due != 0 && (do_paint || now_ns >= due)) {
    scheduled_paint_due_ns_.compare_exchange_strong(due, 0, std::memory_order_acq_rel);
    do_paint = true;
  }
  if (!do_paint) {
    return;
  }
  // Without focus (HOME menu, sleep, an overlay applet) the display stack may
  // stop taking frames, and a present could block the UI thread.
  if (has_focus_) {
    OnPaint();
  }
}'''
    assert t_wc in s
    p_wc.write_text(s.replace(t_wc, r_wc, 1))

# 4. SwitchWindowedAppContext: bound waitMulti by earliest due paint deadline
p_ac = root / 'src/ui/windowed_app_context_switch.cpp'
s = p_ac.read_text()
if 'NextPaintTimeoutNs' not in s:
    assert '#include <algorithm>' in s
    if '#include <chrono>' not in s:
        s = s.replace('#include <algorithm>', '#include <algorithm>\n#include <chrono>', 1)
    t_ac1 = '''int SwitchWindowedAppContext::RunMainMessageLoop() {
  while (!HasQuitFromUIThread()) {
    s32 index = -1;
    if (impl_->has_display_resolution_event) {
      waitMulti(&index, kWaitTimeoutNs, waiterForUEvent(&impl_->wakeup),
                waiterForEvent(appletGetMessageEvent()),
                waiterForEvent(&impl_->display_resolution_changed));
    } else {
      waitMulti(&index, kWaitTimeoutNs, waiterForUEvent(&impl_->wakeup),
                waiterForEvent(appletGetMessageEvent()));
    }'''
    r_ac1 = '''int SwitchWindowedAppContext::RunMainMessageLoop() {
  auto now_ns_fn = []() -> uint64_t {
    return uint64_t(std::chrono::duration_cast<std::chrono::nanoseconds>(
        std::chrono::steady_clock::now().time_since_epoch()).count());
  };
  while (!HasQuitFromUIThread()) {
    u64 wait_ns = kWaitTimeoutNs;
    const uint64_t pre_now_ns = now_ns_fn();
    for (WindowSwitch* window : windows_) {
      if (IsRegistered(window)) {
        wait_ns = std::min<u64>(wait_ns, window->NextPaintTimeoutNs(pre_now_ns));
      }
    }
    s32 index = -1;
    if (impl_->has_display_resolution_event) {
      waitMulti(&index, wait_ns, waiterForUEvent(&impl_->wakeup),
                waiterForEvent(appletGetMessageEvent()),
                waiterForEvent(&impl_->display_resolution_changed));
    } else {
      waitMulti(&index, wait_ns, waiterForUEvent(&impl_->wakeup),
                waiterForEvent(appletGetMessageEvent()));
    }'''
    t_ac2 = '''    for (WindowSwitch* window : windows) {
      if (IsRegistered(window)) {
        window->HandlePendingPaint();
      }
    }'''
    r_ac2 = '''    const uint64_t paint_now_ns = now_ns_fn();
    for (WindowSwitch* window : windows) {
      if (IsRegistered(window)) {
        window->HandlePendingPaint(paint_now_ns);
      }
    }'''
    assert t_ac1 in s and t_ac2 in s
    p_ac.write_text(s.replace(t_ac1, r_ac1, 1).replace(t_ac2, r_ac2, 1))
print('Stage 2B applied cleanly.')
