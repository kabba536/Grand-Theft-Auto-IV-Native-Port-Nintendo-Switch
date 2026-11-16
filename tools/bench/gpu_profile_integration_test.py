#!/usr/bin/env python3
"""Test the patched GPU request helper. --emit-harness supports container C++ compilers."""
import argparse
import pathlib
import subprocess
import tempfile

p = argparse.ArgumentParser()
p.add_argument('source', type=pathlib.Path, help='patched switch_perf.cpp')
p.add_argument('--emit-harness', action='store_true')
args = p.parse_args()
s = args.source.read_text()
helper = s[s.index('// Only a request,'):s.index('void BenchPoll(')]
setter = s[s.index('void RexSwitchBenchGpuEnable('):s.index('void RexSwitchBenchRecord(')]
harness = r'''
#include <atomic>
#include <cassert>
#include <cstdio>
#include <string>
std::atomic<bool> g_bench_gpu_mode{false};
static int calls = 0;
extern "C" int rex_gta4_native_profile_start() { ++calls; return 1; }
bool BenchExists(const std::string& path) {
 if (FILE* f=std::fopen(path.c_str(),"r")) { std::fclose(f); return true; }
 return false;
}
void touch(const char* path) { FILE* f=std::fopen(path,"w"); assert(f); std::fclose(f); }
''' + helper + setter + r'''
int main() {
 touch("disabled.gpu");
 BenchRequestGpuProfile("disabled", "disabled"); assert(calls==0);
 assert(BenchExists("disabled.gpu"));
 RexSwitchBenchGpuEnable(true);
 BenchRequestGpuProfile("ordinary", "ordinary"); assert(calls==0);
 touch("stale.gpu"); touch("stale.gpu-requested");
 BenchRequestGpuProfile("stale", "stale"); assert(calls==0);
 assert(BenchExists("stale.gpu"));
 touch("first.gpu");
 BenchRequestGpuProfile("first", "first"); assert(calls==1);
 assert(BenchExists("first.gpu-requested") && !BenchExists("first.gpu"));
 touch("second.gpu");
 BenchRequestGpuProfile("second", "second"); assert(calls==1);
 assert(BenchExists("second.gpu") && !BenchExists("second.gpu-requested"));
 RexSwitchBenchGpuEnable(false);
 BenchRequestGpuProfile("off", "off"); assert(calls==1);
}
'''
assert 'seguidos >= 2 && !g_bench_gpu_mode.load' in s
assert 'BenchRequestGpuProfile(base, run);' in s
assert s.index('std::rename(request.c_str(), (base + ".claimed")') < s.index('BenchRequestGpuProfile(base, run);')
if args.emit_harness:
    print(harness)
else:
    with tempfile.TemporaryDirectory(prefix='bench-gpu-test-') as d:
        root = pathlib.Path(d)
        source = root / 'test.cpp'
        source.write_text(harness)
        binary = root / 'test'
        subprocess.run(['c++', '-std=c++17', '-Wall', '-Wextra', '-Werror', str(source), '-o', str(binary)], check=True)
        subprocess.run([str(binary)], cwd=root, check=True)
