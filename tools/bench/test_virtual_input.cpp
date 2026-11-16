#include "gta4_bench_virtual_input.h"

#include <cassert>

using namespace gta4::bench_input;

Scene At(uint64_t epoch, float x, uint32_t flags = kBenchSceneValid |
                                                kBenchScenePlaying |
                                                kBenchSceneGameplayAllowed) {
  Scene s;
  s.status = GTA4BenchSceneStatus::kReady;
  s.user = 0;
  s.snapshot.flags = flags;
  s.snapshot.input_poll_epoch = epoch;
  s.snapshot.player_generation = 7;
  s.snapshot.episode = 0;
  s.snapshot.position[0] = x;
  return s;
}

void Consume(Engine& engine, uint32_t expected_user, int16_t expected_ly) {
  Pad pad{};
  assert(!ReadOverride(1, &pad));
  assert(ReadOverride(expected_user, &pad));
  assert(pad.ly == expected_ly);
  engine.EndPoll();
}

int main() {
  Plan plan;
  plan.start_tolerance = 0.25f;
  plan.count = 2;
  plan.steps[0] = {.polls = 2, .pad = {.ly = 12000},
                   .endpoint = {1.0f, 0.0f, 0.0f}, .tolerance = 0.2f};
  plan.steps[1] = {.polls = 1, .pad = {.rx = 9000},
                   .endpoint = {1.0f, 0.0f, 0.0f}, .tolerance = 0.2f};
  Engine engine;
  assert(engine.Stage(plan));
  assert(!engine.Stage(plan));
  engine.BeginPoll(At(1, 0), 100);
  Consume(engine, 0, 0);  // start gate is neutral, not step zero
  assert(engine.GetReport().polls_replayed == 0);
  engine.BeginPoll(At(2, 0.5f), 101);
  Consume(engine, 0, 12000);
  engine.BeginPoll(At(3, 0.9f), 102);
  Consume(engine, 0, 12000);
  engine.BeginPoll(At(4, 1.0f), 103);  // first endpoint, then camera step
  Pad camera{};
  assert(ReadOverride(0, &camera) && camera.rx == 9000);
  engine.EndPoll();
  engine.BeginPoll(At(5, 1.0f), 104);  // final endpoint and neutral exit
  Consume(engine, 0, 0);
  const Report done = engine.GetReport();
  assert(done.status == Status::kComplete && done.error == Error::kNone);
  assert(done.polls_replayed == 3 && done.checkpoints_passed == 3);
  assert(done.observed_get_state == 5);
  assert(!current_override.active);

  assert(engine.Stage(plan));
  engine.BeginPoll(At(10, 10.0f), 200);
  Consume(engine, 0, 0);
  assert(engine.GetReport().error == Error::kStartPosition);
  assert(engine.GetReport().status == Status::kAborted);

  assert(engine.Stage(plan));
  engine.BeginPoll(At(20, 0, kBenchSceneValid | kBenchSceneFrontend), 300);
  Consume(engine, 0, 0);
  assert(engine.GetReport().error == Error::kStartGate);

  assert(engine.Stage(plan));
  engine.BeginPoll(At(30, 0), 400);
  Consume(engine, 0, 0);
  engine.BeginPoll(At(31, 0), 15402);
  Consume(engine, 0, 0);
  assert(engine.GetReport().error == Error::kTimeout);

  assert(engine.Stage(plan));
  engine.BeginPoll(At(40, 0), 500);
  Consume(engine, 0, 0);
  engine.Cancel();
  engine.BeginPoll(At(41, 0), 501);
  Consume(engine, 0, 0);
  assert(engine.GetReport().status == Status::kCancelled);
  assert(!current_override.active);
}
