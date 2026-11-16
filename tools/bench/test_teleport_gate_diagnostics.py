#!/usr/bin/env python3
"""Verify the additive diagnostics patch against read-only SDK sources, in /tmp only."""
import argparse
import hashlib
import pathlib
import shutil
import shlex
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HASHES = {
    'gta4_quicksave_hooks.cpp': '76cd71256a241c614e35ef31bb5cf33cca7285e76c9e73e1778ab3a09637c3ba',
    'gta4_bench_teleport.inc': '958f17b4bd47093693ee4df980031d7a20d18d775c6432080329c02b2bcd3d85',
}

def eligibility(text, name):
    start = text.index('Denial Eligibility(')
    end = text.index('#include "gta4_bench_teleport.inc"', start)
    return text[start:end].replace('Denial Eligibility(', 'Denial ' + name + '(', 1)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sdk', type=pathlib.Path, required=True)
    parser.add_argument('--build-dir', type=pathlib.Path, help='Optionally compile the real patched Switch TU into /tmp')
    args = parser.parse_args()
    source = args.sdk / 'gta4-recomp/src'
    for name, expected in HASHES.items():
        assert hashlib.sha256((source / name).read_bytes()).hexdigest() == expected, name + ': preimage drift'
    with tempfile.TemporaryDirectory(prefix='gta4nx-gate-') as directory:
        root = pathlib.Path(directory)
        dest = root / 'gta4-recomp/src'
        dest.mkdir(parents=True)
        for name in (*HASHES, 'gta4_quicksave_policy.h', 'gta4_bench_teleport.h'):
            shutil.copyfile(source / name, dest / name)
        original = (dest / 'gta4_quicksave_hooks.cpp').read_text()
        subprocess.run(['patch', '--batch', '--fuzz=0', '-p1', '-i',
                        str(ROOT / 'patches/bench/v35-bench-teleport-gate-diagnostics.patch')], cwd=root, check=True)
        patched = (dest / 'gta4_quicksave_hooks.cpp').read_text()
        code = (HEADER + eligibility(original, 'Original') + eligibility(patched, 'Patched') + TEST)
        (dest / 'gate.cpp').write_text(code)
        compile_run(dest, 'gate')
        # Run the original transaction harness against the actual patched .inc.
        import test_teleport
        harness = test_teleport.HARNESS.replace(
            'Denial Eligibility(PPCContext&, uint8_t*, const Session&) { return eligible ? Denial::kNone : Denial::kUnavailable; }',
            'Denial Eligibility(PPCContext&, uint8_t*, const Session&, bool, const char** detail) { '
            '*detail = "phone-program-not-installed"; return eligible ? Denial::kNone : Denial::kUnavailable; }')
        harness = harness.replace('reset(); available=false;',
            'assert(std::string(std::istreambuf_iterator<char>(std::ifstream("teleport_gate.failed").rdbuf()), {}) == '
            '"free-roam-gate-rejected\\ngate-detail=phone-program-not-installed\\n");\n  reset(); available=false;')
        (dest / 'transaction.cpp').write_text(harness)
        compile_run(dest, 'transaction')
        if args.build_dir:
            commands = subprocess.check_output(
                ['ninja', '-f', 'build-telemetry.ninja', '-t', 'commands'],
                cwd=args.build_dir, text=True, timeout=30).splitlines()
            original_path = str(source / 'gta4_quicksave_hooks.cpp')
            command = next(line for line in commands if line.endswith(' -c ' + original_path))
            tokens, output, index = shlex.split(command), [], 0
            while index < len(tokens):
                if tokens[index] in ('-MT', '-MF', '-o'):
                    index += 2
                    continue
                if tokens[index] != '-MD':
                    output.append(str(dest / 'gta4_quicksave_hooks.cpp')
                                  if tokens[index] == original_path else tokens[index])
                index += 1
            output[1:1] = ['-I' + str(source)]
            subprocess.run(output + ['-o', str(root / 'quicksave.o')],
                           cwd=args.build_dir, check=True, timeout=60)
            print('Switch cross-compile: patched gta4_quicksave_hooks.cpp passed', flush=True)

def compile_run(directory, name):
    subprocess.run(['c++', '-std=c++20', '-O2', '-Wall', '-Wextra', '-Werror', '-D__SWITCH__',
                    str(directory / (name + '.cpp')), '-o', str(directory / name)], check=True)
    subprocess.run([str(directory / name)], cwd=directory, check=True)

HEADER = r'''
#include <array>
#include <cassert>
#include <cstdio>
#include <initializer_list>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <vector>
#include "gta4_quicksave_policy.h"
using namespace gta4::quicksave;
struct PPCContext {};
constexpr uint32_t kVehicleFlags=572, kInVehicle=0x20000000, kFrontendRequest=50, kFrontendVisible=51;
bool enabled=true, valid_span=true, in_vehicle=false, frontend_request=false, frontend_visible=false;
std::array<bool,3> installed{true,true,true};
std::mutex state_mutex;
#define REXCVAR_GET(x) enabled
constexpr std::array<const char*,16> names{
 "IS_PLAYER_PLAYING", "IS_PLAYER_CONTROL_ON", "GET_MISSION_FLAG", "IS_MINIGAME_IN_PROGRESS",
 "IS_NETWORK_GAME_RUNNING", "NETWORK_IS_SESSION_STARTED", "IS_SYSTEM_UI_SHOWING",
 "IS_MOBILE_PHONE_CALL_ONGOING", "IS_SCREEN_FADED_IN", "IS_WANTED_LEVEL_GREATER",
 "IS_MEMORY_CARD_IN_USE", "IS_AUTO_SAVE_IN_PROGRESS", "GET_PLAYER_CHAR",
 "IS_CHAR_DEAD", "IS_PED_RAGDOLL", "IS_CHAR_IN_AIR"};
std::array<std::optional<uint32_t>,16> values;
std::vector<std::string> calls;
bool Span(uint8_t*,uint32_t,size_t) { return valid_span; }
uint32_t Read(uint8_t*,uint32_t address) { return address==kFrontendRequest ? frontend_request : in_vehicle ? kInVehicle : 0; }
uint8_t Byte(uint8_t*,uint32_t) { return frontend_visible; }
std::optional<uint32_t> Invoke(PPCContext&,uint8_t*,std::string_view name,
                             std::initializer_list<uint32_t> = {},int=-1) {
 calls.emplace_back(name);
 for(unsigned i=0;i<names.size();++i) if(name==names[i]) return values[i];
 assert(false); return {};
}
'''
TEST = r'''
void reset() {
 enabled=valid_span=true; installed.fill(true);
 in_vehicle=frontend_request=frontend_visible=false;
 values.fill(0);values[0]=values[1]=values[8]=1;values[12]=123;
}
PPCContext ctx;
Session session{.epoch=1,.xuid=1,.episode=0,.player=0,.ped=1000};
void compare(const char* expected=nullptr, bool busy=true) {
 calls.clear(); const auto original=Original(ctx,nullptr,session,busy);const auto original_calls=calls;
 calls.clear();const char* detail=nullptr;const auto patched=Patched(ctx,nullptr,session,busy,&detail);
 assert(original==patched && original_calls==calls && detail);
 if(expected) assert(std::string_view(expected)==detail);
 calls.clear();assert(Patched(ctx,nullptr,session,busy)==original && original_calls==calls);
}
int main() {
 reset();compare("none");
 enabled=false;compare("quicksave-disabled");reset();installed[0]=false;compare("phone-program-not-installed");
 reset();valid_span=false;compare("player-memory-not-ready");reset();session.xuid=0;compare("not-signed-in");session.xuid=1;
 for(unsigned i=0;i<names.size();++i) { reset(); values[i]={};compare((std::string("invoke-")+names[i]).c_str()); }
 reset(); values[12]=0;compare("player-handle-zero");
 const std::array<const char*,16> reasons{"player-not-playing","player-control-off","mission-flag","minigame-in-progress",
 "network-game-running","network-session-started","system-ui-showing","phone-call-ongoing","screen-not-faded-in",
 "wanted-level","memory-card-in-use","autosave-in-progress","player-handle-zero","IS_CHAR_DEAD","IS_PED_RAGDOLL","IS_CHAR_IN_AIR"};
 for(unsigned i=0;i<names.size();++i) { reset();values[i]=(i==0||i==1||i==8||i==12)?0:1;compare(reasons[i]); }
 reset();in_vehicle=true;compare("player-in-vehicle");reset();frontend_request=true;compare("frontend-active");compare("none",false);
 reset();frontend_visible=true;compare("frontend-active");compare("none",false);
 // Exhaust all combinations of native Boolean states, plus mixed unavailable
 // results and initial preconditions, against the original evaluator.
 for(uint32_t mask=0;mask<65536;++mask) {
  reset();for(unsigned i=0;i<values.size();++i)values[i]=((mask>>i)&1);
  enabled=(mask%7)!=0;valid_span=(mask%11)!=0;installed[0]=(mask%13)!=0;
  in_vehicle=(mask%3)==0;frontend_request=(mask%5)==0;frontend_visible=(mask%17)==0;
  session.xuid=(mask%19)!=0;session.episode=(mask%23)==0?3:0;session.player=(mask%29)==0?4:0;session.ped=(mask%31)==0?0:1000;
  if(mask%37==0) values[mask%16]={};
  compare(nullptr,mask%2);
 }
 std::puts("gate diagnostics: exact first blocker branches + 65536 evaluator/native-call parity cases passed");
}
'''

if __name__ == '__main__':
    main()
