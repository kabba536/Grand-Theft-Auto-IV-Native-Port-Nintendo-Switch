#pragma once
#include <array>
#include <cstddef>
#include <cstdint>
#include <ostream>

// Single producer and owner: Start, Record, Stop and Export must never overlap.
// The caller supplies monotonic ticks from one clock; no clock or IO is used here.
namespace bench_telemetry {
enum class State { disabled, recording, stopped };
template <std::size_t Capacity> class Capture {
  static_assert(Capacity > 0, "capacity must be positive");
 public:
  bool Start(uint64_t ticks_per_second) {
    if (state_ == State::recording || ticks_per_second == 0) return false;
    size_ = 0; rejected_ = 0; frequency_ = ticks_per_second;
    state_ = State::recording; return true;
  }
  void Record(uint64_t tick, uint64_t guest_frame) {
    if (state_ != State::recording) return;
    if (size_ && tick < samples_[size_ - 1].tick) { ++rejected_; return; }
    if (size_ == Capacity) { ++rejected_; return; }
    samples_[size_++] = {tick, guest_frame};
  }
  bool Stop() {
    if (state_ != State::recording) return false;
    state_ = State::stopped; return true;
  }
  bool Export(std::ostream& out) const {
    if (state_ != State::stopped) return false;
    out << "# schema=guest_publish_ticks_v1\n# event=guest_publish_entry\n"
        << "# physical_display=false\n# ticks_per_second=" << frequency_
        << "\n# capacity=" << Capacity << "\n# rejected=" << rejected_
        << "\n# samples=" << size_ << "\nindex,guest_frame,tick\n";
    for (std::size_t i = 0; i < size_; ++i)
      out << i << ',' << samples_[i].frame << ',' << samples_[i].tick << '\n';
    return static_cast<bool>(out);
  }
  State state() const { return state_; }
  std::size_t size() const { return size_; }
 private:
  struct Sample { uint64_t tick, frame; };
  std::array<Sample, Capacity> samples_{};
  std::size_t size_ = 0;
  uint64_t rejected_ = 0, frequency_ = 0;
  State state_ = State::disabled;
};
}
