#!/usr/bin/env python3
"""Compile the teleport code extracted from the distributable patch against engine stubs."""
import pathlib
import subprocess
import tempfile
import unittest
ROOT = pathlib.Path(__file__).resolve().parents[2]

class TeleportTests(unittest.TestCase):
    def test_actual_patch_transaction(self):
        patch = ROOT / 'patches/bench/v35-bench-teleport.patch'
        files = {}; current = None
        for line in patch.read_text().splitlines(True):
            if line.startswith('+++ b/'):
                current = line[6:].strip(); files[current] = []
            elif current and line.startswith('+') and not line.startswith('+++'):
                files[current].append(line[1:])
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            for name in ('gta4_bench_teleport.h', 'gta4_bench_teleport.inc'):
                (root / name).write_text(''.join(files['gta4-recomp/src/' + name]))
            (root / 'test.cpp').write_text(HARNESS)
            subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-D__SWITCH__',
                            str(root / 'test.cpp'), '-o', str(root / 'test')], check=True)
            subprocess.run([str(root / 'test')], check=True, cwd=root)

    def test_applet_exit_patch_throttles_sd_polls(self):
        def file_diff(patch_path, target):
            out = []; keep = False
            for line in patch_path.read_text().splitlines(True):
                if line.startswith('--- a/'):
                    keep = line.strip() == '--- a/' + target
                if keep:
                    out.append(line)
            return ''.join(out)

        teleport_patch = ROOT / 'patches/bench/v35-bench-teleport.patch'
        diag_patch = ROOT / 'patches/bench/v35-bench-teleport-gate-diagnostics.patch'
        exit_patch = ROOT / 'patches/bench/v35-bench-exit-applet.patch'
        phone_patch = ROOT / 'patches/bench/v35-teleport-phone-gate.patch'
        files = {}; current = None
        for line in teleport_patch.read_text().splitlines(True):
            if line.startswith('+++ b/'):
                current = line[6:].strip(); files[current] = []
            elif current and line.startswith('+') and not line.startswith('+++'):
                files[current].append(line[1:])
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            src = root / 'gta4-recomp/src'
            src.mkdir(parents=True)
            for name in ('gta4_bench_teleport.h', 'gta4_bench_teleport.inc'):
                (src / name).write_text(''.join(files['gta4-recomp/src/' + name]))
            for extra in (diag_patch, exit_patch, phone_patch):
                subprocess.run(
                    ['patch', '-p1', '--forward', '--fuzz=0'],
                    input=file_diff(extra, 'gta4-recomp/src/gta4_bench_teleport.inc'),
                    text=True, cwd=root, check=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
            (src / 'exit_test.cpp').write_text(EXIT_HARNESS)
            subprocess.run(['c++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-D__SWITCH__',
                            str(src / 'exit_test.cpp'), '-o', str(root / 'exit_test')], check=True)
            subprocess.run([str(root / 'exit_test')], check=True, cwd=root)

HARNESS = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <initializer_list>
#include <limits>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include "gta4_bench_teleport.h"
#define REXLOG_INFO(...) ((void)0)
struct PPCContext {};
struct Session { uint64_t epoch = 1; uint32_t ped = 100, player = 0, episode = 0; };
enum class Denial { kNone, kUnavailable };
enum class Phase { kIdle, kBusy };
struct Transaction { Phase value = Phase::kIdle; Phase phase() const { return value; } } transaction;
std::mutex state_mutex;
uint64_t time_now = 1000;
Session current;
bool eligible = true, waiting = false, available = true;
bool frozen = false;
int setter_calls = 0, freeze_calls = 0;
float ped_position[3]{1,2,3};
uint64_t Now() { return time_now; }
Session CurrentSession(uint8_t*) { return current; }
Denial Eligibility(PPCContext&, uint8_t*, const Session&) { return eligible ? Denial::kNone : Denial::kUnavailable; }
bool Span(uint8_t*, uint32_t, size_t, bool = false) { return true; }
uint32_t Read(uint8_t*, uint32_t address) {
  if (address == current.ped + 32) return 0;
  const unsigned axis = (address - current.ped - 16) / 4;
  assert(axis < 3); uint32_t bits; std::memcpy(&bits, &ped_position[axis], 4); return bits;
}
uint32_t NativeAddress(std::string_view) { return available ? 0x1000 : 0; }
std::optional<uint32_t> Invoke(PPCContext&, uint8_t*, std::string_view name,
                             std::initializer_list<uint32_t> values = {}, int = -1) {
  if (!available) return {};
  const auto* p = values.begin();
  if (name == "GET_PLAYER_CHAR") return 123;
  if (name == "IS_CHAR_WAITING_FOR_WORLD_COLLISION") return waiting;
  if (name == "FREEZE_CHAR_POSITION") { assert(values.size() == 2); frozen = p[1]; ++freeze_calls; }
  if (name == "SET_CHAR_COORDINATES") {
    assert(values.size() == 4 && p[0] == 123);
    for (unsigned i=0;i<3;++i) std::memcpy(&ped_position[i], &p[i+1], 4);
    ++setter_calls;
  }
  if (name == "REQUEST_COLLISION_AT_POSN") assert(values.size() == 3);
  return 0;
}
extern "C" const char* RexSwitchLogDir() { return "./"; }
#include "gta4_bench_teleport.inc"
void request(const char* text) { std::ofstream("teleport_request.txt") << text; }
bool exists(const char* path) { return BenchTeleportExists(path); }
void reset() {
  bench_teleport = {}; bench_teleport_busy.store(false); bench_teleport_next_request = 0; current = {};
  eligible = available = true; waiting = frozen = false; setter_calls = freeze_calls = 0;
  time_now += 100000; ped_position[0]=1;ped_position[1]=2;ped_position[2]=3;
}
int main() {
  using namespace gta4::bench_teleport;
  Request parsed;
  assert(Parse("valid_1 -100 200 20\n", parsed));
  for (const auto* bad : {"../bad 1 2 3", "id nan 2 3", "id 1 inf 3", "id 1 2 -101",
                          "id 1 2 1501", "id 10001 2 3", "id 1 2 3 extra", "id 1 2"})
    assert(!Parse(bad, parsed));
  PPCContext ctx;
  reset(); request("success 10 20 30"); BenchTeleportPoll(ctx, nullptr);
  assert(bench_teleport_busy.load());
  assert(frozen && setter_calls == 1 && !exists("teleport_success.done"));
  time_now += 500; BenchTeleportPoll(ctx, nullptr); assert(frozen);
  time_now += 500; BenchTeleportPoll(ctx, nullptr);
  assert(!frozen && !bench_teleport_busy.load() && exists("teleport_success.done"));
  request("success 10 20 30");time_now+=1000;BenchTeleportPoll(ctx,nullptr);assert(setter_calls==1);
  reset(); eligible=false;request("gate 10 20 30");BenchTeleportPoll(ctx,nullptr);
  assert(!frozen && setter_calls==0 && exists("teleport_gate.failed"));
  reset(); available=false;request("missing 10 20 30");BenchTeleportPoll(ctx,nullptr);
  assert(!frozen && setter_calls==0 && exists("teleport_missing.failed"));
  reset();transaction.value=Phase::kBusy;request("busy 10 20 30");BenchTeleportPoll(ctx,nullptr);
  assert(!frozen && setter_calls==0 && exists("teleport_busy.failed"));transaction.value=Phase::kIdle;
  reset();request("rollback 10 20 30");BenchTeleportPoll(ctx,nullptr);waiting=true;
  time_now+=15000;BenchTeleportPoll(ctx,nullptr);assert(setter_calls==2 && frozen);
  assert(ped_position[0]==1 && ped_position[1]==2 && ped_position[2]==3);
  waiting=false;time_now+=1000;BenchTeleportPoll(ctx,nullptr);
  assert(!frozen && exists("teleport_rollback.failed") && !exists("teleport_rollback.done"));
  reset();request("held 10 20 30");BenchTeleportPoll(ctx,nullptr);waiting=true;
  time_now+=15000;BenchTeleportPoll(ctx,nullptr);time_now+=15000;BenchTeleportPoll(ctx,nullptr);
  assert(frozen && setter_calls==2 && bench_teleport.held && exists("teleport_held.failed"));
  time_now+=15000;BenchTeleportPoll(ctx,nullptr);assert(setter_calls==2);
  reset();request("world 10 20 30");BenchTeleportPoll(ctx,nullptr);
  ++current.epoch;time_now+=1000;const auto before=freeze_calls;BenchTeleportPoll(ctx,nullptr);
  assert(exists("teleport_world.failed") && freeze_calls==before && setter_calls==1);
  std::puts("teleport integration: parser, start, collision wait, gate, dedup, rollback, held, world change passed");
}
'''

EXIT_HARNESS = r'''
#include <algorithm>
#include <atomic>
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <initializer_list>
#include <limits>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include "gta4_bench_teleport.h"
#define REXLOG_INFO(...) ((void)0)
using Result = uint32_t;
#define R_FAILED(rc) ((rc) != 0)
enum AppletType { AppletType_Application = 1, AppletType_SystemApplication = 2 };
struct Service { bool active = true; } g_self_controller;
AppletType appletGetAppletType() { return AppletType_Application; }
Service* appletGetServiceSession_SelfController() { return &g_self_controller; }
bool serviceIsActive(Service* s) { return s && s->active; }
int g_exit_dispatches = 0;
Result serviceDispatch(Service*, uint32_t cmd) { assert(cmd == 0); ++g_exit_dispatches; return 0; }

struct PPCContext {};
struct Session { uint64_t epoch = 1; uint32_t ped = 100, player = 0, episode = 0; };
enum class Denial { kNone, kUnavailable };
enum class Phase { kIdle, kBusy };
struct Transaction { Phase value = Phase::kIdle; Phase phase() const { return value; } } transaction;
std::mutex state_mutex;
uint64_t time_now = 1000;
bool bench_active = false;
int log_dir_queries = 0;
Session current;
uint64_t Now() { return time_now; }
Session CurrentSession(uint8_t*) { return current; }
Denial Eligibility(PPCContext&, uint8_t*, const Session&, bool = false, const char** = nullptr, bool = true) {
  return Denial::kNone;
}
bool Span(uint8_t*, uint32_t, size_t, bool = false) { return true; }
uint32_t Read(uint8_t*, uint32_t) { return 0; }
uint32_t NativeAddress(std::string_view) { return 0x1000; }
std::optional<uint32_t> Invoke(PPCContext&, uint8_t*, std::string_view,
                               std::initializer_list<uint32_t> = {}, int = -1) {
  return 0;
}
extern "C" const char* RexSwitchLogDir() { ++log_dir_queries; return "./"; }
extern "C" bool RexSwitchBenchIsActive(void) { return bench_active; }
#include "gta4_bench_teleport.inc"

int main() {
  PPCContext ctx;
  // 1. 50 script-thread polls within <1000 ms must probe SD directory only once.
  for (int i = 0; i < 50; ++i) {
    time_now = 1000 + i * 10;
    BenchTeleportPoll(ctx, nullptr);
  }
  assert(log_dir_queries == 1);

  // 2. Active benchmark capture suppresses all SD directory polls even past 1000 ms.
  bench_active = true;
  std::ofstream("bench_exit_request.txt") << "exit\n";
  for (int i = 0; i < 20; ++i) {
    time_now += 500;
    BenchTeleportPoll(ctx, nullptr);
  }
  assert(log_dir_queries == 1 && g_exit_dispatches == 0);

  // 3. Once capture finishes, the next throttled poll claims exit cleanly.
  bench_active = false;
  BenchTeleportPoll(ctx, nullptr);
  assert(log_dir_queries == 2 && g_exit_dispatches == 1);
  assert(BenchTeleportExists("bench_exit.done") && !BenchTeleportExists("bench_exit_request.txt"));
  std::puts("applet exit poll throttle + active capture suppression passed");
}
'''
if __name__ == '__main__': unittest.main()
