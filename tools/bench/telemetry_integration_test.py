#!/usr/bin/env python3
"""Extract and exercise the actual patch implementation in a host harness.
Usage: python3 telemetry_integration_test.py <patched switch_perf.cpp>"""
import pathlib, subprocess, sys, tempfile
s = pathlib.Path(sys.argv[1]).read_text()
core = s[s.index('// Explicit, one-shot SD benchmark.'):s.index('void ProfilerMain(void*)')]
record = s[s.index('void RexSwitchBenchRecord(u64 frame)'):s.index('void RexSwitchPerfTiron(u64 inicio')]
harness = r'''
#include <atomic>
#include <cinttypes>
#include <cstdio>
#include <cstring>
#include <string>
#include <unistd.h>
#include <cassert>
#include <fstream>
#include <iterator>
using u64 = uint64_t;
static u64 clock_tick = 100;
u64 armGetSystemTick() { return clock_tick; }
const char* RexSwitchLogDir() { return "./"; }
''' + core + record + r'''
int main() {
  RexSwitchBenchRecord(1);
  { FILE* f = fopen("bench_request.txt", "w"); assert(f); fputs("run1 2 build1\n", f); fclose(f); }
  BenchPoll(100, 100); assert(g_bench_active.load());
  clock_tick = 101; RexSwitchBenchRecord(10);
  clock_tick = 102; RexSwitchBenchRecord(11);
  BenchPoll(300, 100); assert(!g_bench_active.load());
  std::ifstream file("bench_run1.csv"); assert(file);
  std::string data((std::istreambuf_iterator<char>(file)), {});
  assert(data.find("# run_id=run1\n# build_id=build1\n") != std::string::npos);
  assert(data.find("# samples=2\nindex,guest_frame,tick\n0,10,101\n1,11,102\n") != std::string::npos);
  assert(BenchExists("bench_run1.done") && BenchExists("bench_run1.claimed"));
  { FILE* f = fopen("bench_request.txt", "w"); assert(f); fputs("run1 2 build1\n", f); fclose(f); }
  BenchPoll(400, 100); assert(!g_bench_active.load());
}
'''
with tempfile.TemporaryDirectory() as d:
    p = pathlib.Path(d)
    (p/'test.cpp').write_text(harness)
    subprocess.run(['g++','-std=c++17','-Wall','-Wextra','-Werror','-pedantic',str(p/'test.cpp'),'-o',str(p/'test')],check=True)
    subprocess.run([str(p/'test')],cwd=d,check=True)
