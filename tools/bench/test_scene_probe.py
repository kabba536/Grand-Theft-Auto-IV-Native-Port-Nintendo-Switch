#!/usr/bin/env python3
"""Apply the v35 scene patch and exercise its one-shot mailbox on the host."""

import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[2]
PATCH = ROOT / "patches/bench/v35-bench-scene-probe.patch"


class SceneProbeTest(unittest.TestCase):
    def test_patch_contract(self):
        with tempfile.TemporaryDirectory() as temporary:
            work = pathlib.Path(temporary)
            source = work / "gta4-recomp" / "src"
            source.mkdir(parents=True)
            # The v35 input file is supplied by the test caller when running
            # against staging. Local contract tests use a fixture containing
            # the exact context lines affected by the patch.
            header_patch = PATCH.read_text().split(
                "diff -ruN a/gta4-recomp/src/gta4_input_hooks.cpp")[0]
            (work / "header.patch").write_text(header_patch)
            subprocess.run(["patch", "-p1", "-i", str(work / "header.patch")], cwd=work,
                           check=True, capture_output=True, text=True)
            header = source / "gta4_bench_scene_probe.h"
            self.assertTrue(header.exists())
            harness = work / "probe_test.cpp"
            harness.write_text(r'''
#include "gta4_bench_scene_probe.h"
#include <cassert>
#include <thread>
int main() {
  gta4::bench_scene::Mailbox box;
  GTA4BenchSceneSnapshot out;
  assert(box.Read(1, &out) == GTA4BenchSceneStatus::kUnknownRequest);
  assert(!box.Request(0));
  assert(box.Request(1));
  assert(box.Pending());
  assert(!box.Request(2));
  assert(box.Read(1, &out) == GTA4BenchSceneStatus::kPending);
  assert(out.request_id == 1 && out.abi_version == 1);
  GTA4BenchSceneSnapshot sample;
  sample.flags = kBenchSceneValid | kBenchSceneGameplayAllowed;
  sample.input_poll_epoch = 7;
  sample.position[0] = 12.5f;
  assert(!box.Complete(GTA4BenchSceneStatus::kBusy, sample));
  std::thread producer([&] {
    while (!box.Complete(GTA4BenchSceneStatus::kReady, sample)) std::this_thread::yield();
  });
  producer.join();
  assert(!box.Pending());
  assert(box.Read(1, &out) == GTA4BenchSceneStatus::kReady);
  assert(out.request_id == 1 && out.input_poll_epoch == 7);
  assert(out.position[0] == 12.5f && out.flags == sample.flags);
  assert(box.Read(2, &out) == GTA4BenchSceneStatus::kUnknownRequest);
  assert(!box.Complete(GTA4BenchSceneStatus::kReady, sample));
  assert(box.Request(2));
  assert(box.Complete(GTA4BenchSceneStatus::kNoPosition, sample));
  assert(box.Read(2, &out) == GTA4BenchSceneStatus::kNoPosition);
  assert(out.request_id == 2 && out.position[0] == 12.5f);
  assert(box.Request(3));
  assert(box.Complete(GTA4BenchSceneStatus::kNoContext, {}));
  assert(box.Read(3, &out) == GTA4BenchSceneStatus::kNoContext);
  assert(out.request_id == 3 && out.flags == 0);
}
''')
            executable = work / "probe_test"
            compile_result = subprocess.run(
                ["c++", "-std=c++20", "-Wall", "-Wextra", "-Werror", "-pedantic",
                 "-pthread", "-I", str(source), str(harness), "-o", str(executable)],
                capture_output=True, text=True)
            self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
            subprocess.run([str(executable)], check=True, capture_output=True, text=True)


if __name__ == "__main__":
    unittest.main()
