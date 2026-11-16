#!/usr/bin/env python3
"""Exercise the actual patched BenchPoll with scene success and failure paths."""

import pathlib
import subprocess
import sys
import tempfile


perf_source = pathlib.Path(sys.argv[1]).read_text()
header = pathlib.Path(sys.argv[2]).read_text()
core = perf_source[perf_source.index('// Explicit, one-shot SD benchmark.'):
                   perf_source.index('void ProfilerMain(void*)')]
record = perf_source[perf_source.index('void RexSwitchBenchRecord(u64 frame)'):
                     perf_source.index('void RexSwitchPerfTiron(u64 inicio, u64 fin)')]

harness = r'''
#include <atomic>
#include <cassert>
#include <cinttypes>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <unistd.h>
#include "gta4_bench_scene_probe.h"
using u64 = uint64_t;
static u64 clock_tick = 100;
u64 armGetSystemTick() { return clock_tick; }
const char* RexSwitchLogDir() { return "./"; }
gta4::bench_scene::Mailbox scene_box;
bool GTA4_BenchSceneRequest(uint64_t id) { return scene_box.Request(id); }
uint32_t GTA4_BenchSceneRead(uint64_t id, GTA4BenchSceneSnapshot* out) {
  return static_cast<uint32_t>(scene_box.Read(id, out));
}
''' + core + record + r'''
GTA4BenchSceneSnapshot Scene(uint64_t epoch, float x, uint32_t flags) {
  GTA4BenchSceneSnapshot value;
  value.flags = flags;
  value.input_poll_epoch = epoch;
  value.guest_input_time = uint32_t(epoch * 10);
  value.episode = 0;
  value.player_generation = 4;
  value.position[0] = x;
  return value;
}
void Request(const char* id) {
  FILE* f = std::fopen("bench_request.txt", "w");
  assert(f);
  std::fprintf(f, "%s 2 build1\n", id);
  std::fclose(f);
}
std::string ReadFile(const char* path) {
  std::ifstream file(path);
  assert(file);
  return {std::istreambuf_iterator<char>(file), {}};
}
int main() {
  constexpr uint32_t good = kBenchSceneValid | kBenchScenePlaying |
                            kBenchSceneGameplayAllowed;
  Request("stable");
  BenchPoll(100, 100);
  assert(g_bench_active.load());
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Scene(10, 1.0f, good)));
  clock_tick = 101;
  RexSwitchBenchRecord(20);
  clock_tick = 102;
  RexSwitchBenchRecord(21);
  BenchPoll(300, 100);  // arms the end observation
  assert(g_bench_finishing && !g_bench_active.load());
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Scene(20, 1.2f, good)));
  BenchPoll(301, 100);
  assert(BenchExists("bench_stable.done"));
  auto stable = ReadFile("bench_stable.csv");
  assert(stable.find("# player_state_gate=passed\n") != std::string::npos);
  assert(stable.find("# scene_start_status=2\n# scene_end_status=2\n") != std::string::npos);
  assert(stable.find("0,20,101\n1,21,102\n") != std::string::npos);

  Request("cutscene");
  BenchPoll(400, 100);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady,
                            Scene(30, 1.0f, good | kBenchSceneCutscene)));
  BenchPoll(600, 100);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Scene(40, 1.0f, good)));
  BenchPoll(601, 100);
  assert(BenchExists("bench_cutscene.failed") && !BenchExists("bench_cutscene.done"));
  assert(ReadFile("bench_cutscene.csv").find("# player_state_gate=failed\n") != std::string::npos);

  Request("no_poll");
  BenchPoll(700, 100);
  BenchPoll(900, 100);
  assert(g_bench_finishing);
  BenchPoll(1101, 100);
  assert(BenchExists("bench_no_poll.failed") && !BenchExists("bench_no_poll.done"));
  assert(ReadFile("bench_no_poll.csv").find("# player_state_gate=failed\n") != std::string::npos);

  Request("menu");
  BenchPoll(1200, 100);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady,
                            Scene(50, 1.0f, good | kBenchSceneFrontend)));
  BenchPoll(1400, 100);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Scene(60, 1.0f, good)));
  BenchPoll(1401, 100);
  assert(BenchExists("bench_menu.failed") && !BenchExists("bench_menu.done"));

  Request("moved");
  BenchPoll(1500, 100);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Scene(70, 1.0f, good)));
  BenchPoll(1700, 100);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Scene(80, 1.8f, good)));
  BenchPoll(1701, 100);
  assert(BenchExists("bench_moved.failed") && !BenchExists("bench_moved.done"));
  assert(ReadFile("bench_moved.csv").find("# player_endpoint_displacement_m=0.800000\n") != std::string::npos);
}
'''

with tempfile.TemporaryDirectory() as temporary:
    work = pathlib.Path(temporary)
    (work / 'gta4_bench_scene_probe.h').write_text(header)
    (work / 'test.cpp').write_text(harness)
    executable = work / 'test'
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-pedantic',
                    '-pthread', '-I', str(work), str(work / 'test.cpp'), '-o', str(executable)],
                   check=True)
    subprocess.run([str(executable)], cwd=work, check=True)
