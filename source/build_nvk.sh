#!/bin/bash
# Runs INSIDE ghcr.io/autorunhq/switch-dev, before the game build.
# Rebuilds NVK (mesa-switch, the same revision the image ships) with one fix to
# its shader compiler, NAK, and installs the resulting libvulkan.a into this
# container's portlibs. The result is cached in the volume (/src/nvk): only the
# first run compiles Mesa (~20-40 min); later runs just copy it.
#
# The fix: on Maxwell (the Switch's GM20B) NAK swaps the sources of a float
# compare when only the second is a register, and flips the comparison to
# match. FloatCmpOp::flip() panics ("Cannot flip unop") for the ordered and
# unordered tests (ford/funord: isnan(a) || isnan(b) and its negation), but
# those are symmetric in a and b, so the flip is the operation itself. GTA IV's
# shaders hit it thousands of times (seen on console), every such pipeline
# failed to compile and nothing was drawn: a black screen with sound.
set -euo pipefail
REV=0ff52079ca9e9e837ed27eb95a8d239f439a1864
FIX_ID=nak-unop-flip-v1+sched-latency-peephole-v2
OUT=/src/nvk
portlibs=/opt/devkitpro/portlibs/switch

if [ -f $OUT/libvulkan.a ] && [ "$(cat $OUT/fix_id 2>/dev/null)" = "$FIX_ID" ]; then
  cp -p $OUT/libvulkan.a $portlibs/lib/libvulkan.a
  echo "NVK corrigido: em cache ($FIX_ID)"
  exit 0
fi

echo "NVK corrigido: a compilar o Mesa (so na 1a vez, 20-40 min)..."
rm -rf /src/mesa-switch
git init -q /src/mesa-switch
cd /src/mesa-switch
git fetch -q --depth 1 https://github.com/danfromtico/mesa-switch.git $REV
git checkout -q FETCH_HEAD

python3 - <<'PYEOF'
p = "src/nouveau/compiler/nak/ir.rs"
s = open(p).read()
old = 'FloatCmpOp::IsNum | FloatCmpOp::IsNan => panic!("Cannot flip unop"),'
new = ('// ford/funord (IsNum/IsNan) are symmetric in their two sources.\n'
       '            FloatCmpOp::IsNum | FloatCmpOp::IsNan => self,')
assert s.count(old) == 1, "NAK fix: pattern not found"
open(p, "w").write(s.replace(old, new))
print("NAK fix applied")

# From the Need for Speed: Most Wanted port (StevensND/nfsmw-nx, mesa/mesa-switch-nfsmw.patch),
# measured there on the same GM20B. The rest of that patch (ZCULL, FADD32I clamp, uncached
# CPU-write memory, UBO deltas, query pools) is already in this mesa-switch revision.
def sub(path, old, new, what):
    t = open(path).read()
    assert t.count(old) == 1, what + ": pattern not found"
    open(path, "w").write(t.replace(old, new))
    print(what + " applied")

# 1. NAK scheduler: a texture or memory read is not 32 cycles on shared LPDDR4 (hundreds on a
#    miss). The higher estimate separates each read from its consumer and keeps more reads in
#    flight. Only the scheduling priority changes; the scoreboard barriers are computed apart.
sched = "src/nouveau/compiler/nak/opt_instr_sched_common.rs"
sub(sched, "        | Op::Txq(_) => 32,", "        | Op::Txq(_) => 200,", "NAK texture latency 200")
sub(sched, "        | Op::MemBar(_) => 32,", "        | Op::MemBar(_) => 200,", "NAK memory latency 200")
# 2. Small ifs become straight-line code (ANV and RADV use 8; NAK used 0, so every if that
#    survived NIR was a real SSY/BRA/SYNC branch on Maxwell).
sub("src/nouveau/compiler/nak_nir.c", "         .limit = 0,\n         .discard_ok = true,",
    "         .limit = 8,\n         .discard_ok = true,", "NAK peephole_select 8")
# 3. New compiler ABI revision: shaders compiled before these changes are not reused.
sub("src/nouveau/vulkan/nvk_shader.c", "(UINT64_C(10) << 16) /* Compiler ABI revision. */",
    "(UINT64_C(11) << 16) /* Compiler ABI revision. */", "NVK compiler ABI revision 11")
PYEOF

# Same setup as switch-dev's mesa build (cross wrappers, headers, stubs).
mkdir -p /usr/local/libexec
cp bindgen-switch-wrapper.sh /usr/local/libexec/bindgen
cp rustc-switch-wrapper.sh /usr/local/libexec/rustc
cp bindgen-atomic-shim.h /usr/local/libexec/bindgen-atomic-shim.h
sed -i 's/\r$//' /usr/local/libexec/bindgen /usr/local/libexec/rustc
chmod +x /usr/local/libexec/bindgen /usr/local/libexec/rustc
cp -p src/nouveau/headers/nv_device_info.h $portlibs/include/
[ -d /usr/lib/llvm-15/lib/clang/15/include ] ||
    ln -sf /usr/lib/llvm-15/lib/clang/15.0.6/include /usr/lib/llvm-15/lib/clang/15/include
echo 'void __mesa_switch_stub_lib(void) {}' > /tmp/stub_posix.c
aarch64-none-elf-gcc -c /tmp/stub_posix.c -o /tmp/stub_posix.o
for l in dl rt util; do
    [ -f $portlibs/lib/lib$l.a ] || aarch64-none-elf-ar rcs $portlibs/lib/lib$l.a /tmp/stub_posix.o
done

tools=/src/mesa-native
rm -rf $tools
meson setup $tools \
    -Dvulkan-drivers= -Dgallium-drivers= -Dshader-cache=true -Dplatforms= \
    -Dglx=disabled -Degl=disabled -Dopengl=false -Dgles1=disabled -Dgles2=disabled \
    -Dtools=[] -Dllvm=enabled -Dmesa-clc=enabled -Dprecomp-compiler=enabled -Dinstall-mesa-clc=true
ninja -C $tools src/compiler/clc/mesa_clc src/compiler/spirv/vtn_bindgen2
export PATH="$tools/src/compiler/clc:$tools/src/compiler/spirv:$PATH"
export MESA_SWITCH_RUST_TARGET=aarch64-unknown-linux-gnu

stage=/src/nvk-stage
rm -rf /src/mesa-build $stage
meson setup /src/mesa-build \
    --cross-file switch_cross_file.txt \
    --default-library=static \
    --prefix=$portlibs \
    --libdir=lib \
    --buildtype=release \
    -Doptimization=2 \
    -Db_lto=false \
    -Db_ndebug=true \
    -Dvulkan-drivers=nouveau \
    -Dgallium-drivers= \
    -Dgallium-rusticl=false \
    -Dplatforms=switch \
    -Dglx=disabled \
    -Degl=disabled \
    -Dopengl=false \
    -Dgles1=disabled \
    -Dgles2=disabled \
    -Dvideo-codecs= \
    -Dshader-cache=enabled \
    -Dxmlconfig=enabled \
    -Dexpat=enabled \
    -Dtools=[] \
    -Dllvm=disabled \
    -Dshared-glapi=disabled \
    -Dshared-llvm=disabled \
    -Dmesa-clc=system \
    -Dprecomp-compiler=system \
    -Dcpp_rtti=false \
    -Dbuild-tests=false
ninja -C /src/mesa-build
meson install -C /src/mesa-build --no-rebuild --destdir "$stage"
lib="$stage$portlibs/lib/libvulkan.a"
aarch64-none-elf-ranlib "$lib"
aarch64-none-elf-nm --print-armap "$lib" > /tmp/vulkan-armap
awk '/^Archive index:/ { index_ = 1; next } /^$/ { if (index_) exit }
     index_ && /4core9panicking9panic_fmt / { found = 1 } END { exit !found }' /tmp/vulkan-armap ||
    { echo 'libvulkan.a has no index for Rust core' >&2; exit 1; }
rm -f /tmp/vulkan-armap

mkdir -p $OUT
cp -p "$lib" $OUT/libvulkan.a
echo "$FIX_ID" > $OUT/fix_id
cp -p $OUT/libvulkan.a $portlibs/lib/libvulkan.a
rm -rf /src/mesa-build /src/mesa-native $stage
echo "NVK corrigido: pronto ($FIX_ID)"
