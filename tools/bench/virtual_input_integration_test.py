#!/usr/bin/env python3
"""Compile the patched profiler bridge and exercise explicit script gates."""

import pathlib
import subprocess
import sys
import tempfile


source = pathlib.Path(sys.argv[1]).read_text()
scene_header = pathlib.Path(sys.argv[2]).read_text()
input_header = pathlib.Path(sys.argv[3]).read_text()
core = source[source.index('// Explicit, one-shot SD benchmark.'):
              source.index('void ProfilerMain(void*)')]
record = source[source.index('void RexSwitchBenchRecord(u64 frame)'):
                source.index('void RexSwitchPerfTiron(u64 inicio, u64 fin)')]

harness = r'''
#include <atomic>
#include <cassert>
#include <cinttypes>
#include <cmath>
#include <cctype>
#include <cstdio>
#include <cstring>
#include <fstream>
#include <iterator>
#include <string>
#include <unistd.h>
#include "gta4_bench_scene_probe.h"
#include "gta4_bench_virtual_input.h"
using u64 = uint64_t;
static u64 clock_tick = 100;
u64 armGetSystemTick() { return clock_tick; }
const char* RexSwitchLogDir() { return "./"; }
gta4::bench_scene::Mailbox scene_box;
gta4::bench_input::Engine replay;
bool GTA4_BenchSceneRequest(uint64_t id) { return scene_box.Request(id); }
uint32_t GTA4_BenchSceneRead(uint64_t id, GTA4BenchSceneSnapshot* out) {
  return static_cast<uint32_t>(scene_box.Read(id, out));
}
bool GTA4_BenchReplayStage(const gta4::bench_input::Plan* plan) {
  return plan && replay.Stage(*plan);
}
void GTA4_BenchReplayCancel() { replay.Cancel(); }
gta4::bench_input::Report GTA4_BenchReplayReport() { return replay.GetReport(); }
''' + core + record + r'''
constexpr uint32_t good = kBenchSceneValid | kBenchScenePlaying |
                          kBenchSceneGameplayAllowed;
GTA4BenchSceneSnapshot Snapshot(uint64_t epoch, float x) {
  GTA4BenchSceneSnapshot value;
  value.flags = good;
  value.input_poll_epoch = epoch;
  value.guest_input_time = uint32_t(epoch * 10);
  value.player_generation = 4;
  value.position[0] = x;
  return value;
}
gta4::bench_input::Scene Scene(uint64_t epoch, float x) {
  return {GTA4BenchSceneStatus::kReady, Snapshot(epoch, x), 0};
}
void Write(const char* path, const char* content) {
  FILE* f = std::fopen(path, "w"); assert(f);
  std::fputs(content, f); std::fclose(f);
}
std::string ReadFile(const char* path) {
  std::ifstream file(path); assert(file);
  return {std::istreambuf_iterator<char>(file), {}};
}
int main() {
  Write("bench_scripted.input", "start 0 0 0 0.2\nstep 2 0 12000 0 0 1 0 0 0.2\n");
  Write("bench_request.txt", "scripted 2 build1\n");
  BenchPoll(100, 100);
  assert(g_bench_script_requested && g_bench_script_staged);
  assert(replay.GetReport().status == gta4::bench_input::Status::kStaged);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Snapshot(1, 0)));
  gta4::bench_input::Pad pad{};
  replay.BeginPoll(Scene(1, 0), 1000);  // valid position gate, neutral
  assert(gta4::bench_input::ReadOverride(0, &pad) && pad.ly == 0);
  replay.EndPoll();
  replay.BeginPoll(Scene(2, 0.5f), 1001);
  assert(gta4::bench_input::ReadOverride(0, &pad) && pad.ly == 12000);
  replay.EndPoll();
  replay.BeginPoll(Scene(3, 0.9f), 1002);
  assert(gta4::bench_input::ReadOverride(0, &pad) && pad.ly == 12000);
  replay.EndPoll();
  replay.BeginPoll(Scene(4, 1.0f), 1003);  // checkpoint and neutral exit
  assert(gta4::bench_input::ReadOverride(0, &pad) && pad.ly == 0);
  replay.EndPoll();
  assert(replay.GetReport().status == gta4::bench_input::Status::kComplete);
  clock_tick = 101; RexSwitchBenchRecord(10);
  clock_tick = 102; RexSwitchBenchRecord(11);
  BenchPoll(300, 100);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Snapshot(5, 1)));
  BenchPoll(301, 100);
  assert(BenchExists("bench_scripted.done"));
  auto csv = ReadFile("bench_scripted.csv");
  assert(csv.find("# input_script_gate=passed\n") != std::string::npos);
  assert(csv.find("# input_script_polls=2\n") != std::string::npos);
  assert(csv.find("# player_endpoint_displacement_m=1.000000\n") != std::string::npos);

  Write("bench_bad.input", "start 0 0 0 0.2\nstep 0 0 12000 0 0 1 0 0 0.2\n");
  Write("bench_request.txt", "bad 2 build1\n");
  BenchPoll(400, 100);
  assert(g_bench_script_requested && !g_bench_script_staged);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Snapshot(10, 0)));
  BenchPoll(600, 100);
  assert(scene_box.Complete(GTA4BenchSceneStatus::kReady, Snapshot(11, 0)));
  BenchPoll(601, 100);
  assert(BenchExists("bench_bad.failed") && !BenchExists("bench_bad.done"));
  assert(ReadFile("bench_bad.csv").find("# input_script_gate=failed\n") != std::string::npos);
}
'''

with tempfile.TemporaryDirectory() as temporary:
    work = pathlib.Path(temporary)
    (work / 'gta4_bench_scene_probe.h').write_text(scene_header)
    (work / 'gta4_bench_virtual_input.h').write_text(input_header)
    (work / 'test.cpp').write_text(harness)
    executable = work / 'test'
    subprocess.run(['g++', '-std=c++20', '-Wall', '-Wextra', '-Werror', '-pedantic',
                    '-pthread', '-I', str(work), str(work / 'test.cpp'), '-o', str(executable)],
                   check=True)
    subprocess.run([str(executable)], cwd=work, check=True)
