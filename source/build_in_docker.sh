#!/bin/bash
# GTA IV for Nintendo Switch - builds gta4nx.nro.
# Runs INSIDE ghcr.io/autorunhq/switch-dev. /src = a Docker volume (Linux file system),
# /host = this repository (with source/ in it). Produces /host/saida/gta4nx.nro.
# Example:
#   docker volume create gta4nx-src
#   docker run --rm -v gta4nx-src:/src -v "$PWD":/host ghcr.io/autorunhq/switch-dev:latest \
#     bash /host/source/build_in_docker.sh
# The recompiled game code is generated from your own default.xex (see the upstream project).
set -o pipefail
LRA_URL=https://github.com/vaduur/LibertyRecompAndroid.git
LRA_COMMIT=7c97c58e1294331dffd617a5eb7267be55debdfc   # android 0.5.9.2
JOBS="${JOBS:-auto}"
if [ "$JOBS" = "auto" ]; then
  # one job per core, but ~2 GB of RAM per job (GCC on a 2 MB generated file)
  memg=$(awk '/MemAvailable/ {print int($2/1048576)}' /proc/meminfo)
  JOBS=$(nproc); byram=$(( memg / 2 )); [ "$byram" -lt "$JOBS" ] && JOBS=$byram; [ "$JOBS" -lt 1 ] && JOBS=1
  echo "JOBS=$JOBS (nucleos $(nproc), RAM livre ${memg} GB)"
fi
SRC=/src/lra18
BUILD=/src/build18
step() { echo; echo "=================== $* ==================="; }

git config --global --add safe.directory '*'
git config --global advice.detachedHead false

step "1/6 codigo fonte ($LRA_COMMIT)"
# A 1a vez a arvore v18 e uma copia da v17 (ja tem os submodulos; nao volta a descarregar nada).
if [ ! -d "$SRC/.git" ] && [ -d /src/lra/.git ]; then
  echo "a copiar /src/lra para $SRC (so na 1a vez)"
  cp -a /src/lra "$SRC" || exit 1
  git -C "$SRC" worktree prune
fi
if [ ! -d "$SRC/.git" ]; then
  git clone --no-checkout "$LRA_URL" "$SRC" || exit 1
fi
cd "$SRC" || exit 1
git cat-file -e "$LRA_COMMIT^{commit}" 2>/dev/null || git fetch origin "$LRA_COMMIT" || git fetch origin || exit 1
if [ "$(cat /src/.base_commit18 2>/dev/null)" != "$LRA_COMMIT" ]; then
  git reset -q --hard "$LRA_COMMIT" || exit 1
  git clean -q -fdx
  echo "$LRA_COMMIT" > /src/.base_commit18
fi

step "2/6 submodulos necessarios"
SUBS=$(git config -f .gitmodules --get-regexp '\.path$' | awk '{print $2}' | grep '^glue/rexglue-sdk-main/thirdparty/')
git submodule update --init --depth 1 --jobs 4 -- $SUBS tools/XenosRecomp thirdparty/msdf-atlas-gen || exit 1
git -C tools/XenosRecomp submodule update --init --depth 1 -- thirdparty/smol-v thirdparty/zstd thirdparty/fmt thirdparty/xxHash thirdparty/dxc-bin || exit 1
# glslang / spirv-tools carry their own nested deps only for tests: not needed.

step "3/6 port Switch (patch)"
# The patch goes into a scratch worktree and only files whose content changed
# are copied into the build tree, so a new patch version does not touch (and
# force a rebuild of) the ~180 MB of recompiled game code.
rm -rf /src/stage18; git worktree prune
git worktree add -f --detach /src/stage18 "$LRA_COMMIT" >/dev/null || exit 1
git -C /src/stage18 apply --whitespace=nowarn /host/source/gta4nx-switch.patch || { echo "ERRO: patch nao aplicou"; exit 1; }
# Recompiled game code: direct calls and loop barriers (nx/otimizar_codigo_gerado.py).
# Done in the scratch copy so the build tree only changes the first time.
python3 /host/source/otimizar_codigo_gerado.py /src/stage18/glue/rexglue-sdk-main/gta4-recomp /src/stage18 || { echo "ERRO: otimizar codigo gerado"; exit 1; }
python3 - <<'PYEOF' || exit 1
import os, shutil, subprocess
src, stage = "/src/lra18", "/src/stage18"
def changed(root):
    out = subprocess.run(["git", "-C", root, "diff", "--name-only", "HEAD", "--ignore-submodules=all"],
                         capture_output=True, text=True, check=True).stdout.split("\n")
    out += subprocess.run(["git", "-C", root, "ls-files", "--others", "--exclude-standard"],
                          capture_output=True, text=True, check=True).stdout.split("\n")
    return {f for f in out if f}
n = 0
for f in sorted(changed(stage) | changed(src)):
    a, b = os.path.join(stage, f), os.path.join(src, f)
    if os.path.isfile(a):
        if os.path.isfile(b) and open(a, "rb").read() == open(b, "rb").read():
            continue
        os.makedirs(os.path.dirname(b), exist_ok=True)
        shutil.copy2(a, b)
        n += 1
    elif os.path.isfile(b):
        os.remove(b)
        n += 1
print(f"port Switch: {n} ficheiros atualizados")
PYEOF
rm -rf /src/stage18; git worktree prune
chmod +x tools/XenosRecomp/thirdparty/dxc-bin/bin/x64/* 2>/dev/null

step "4/6 ferramentas"
need_cmake=$(python3 - <<'EOF'
import subprocess,re
try:
    v=subprocess.run(['cmake','--version'],capture_output=True,text=True).stdout
    m=re.search(r'(\d+)\.(\d+)',v); print(0 if (int(m[1]),int(m[2]))>=(3,29) else 1)
except Exception: print(1)
EOF
)
if [ "$need_cmake" = "1" ]; then
  pip3 install --break-system-packages -q "cmake>=3.29,<4" || pip3 install -q "cmake>=3.29,<4" || exit 1
  hash -r
fi
cmake --version | head -1; ninja --version; python3 --version; aarch64-none-elf-g++ --version | head -1
ls -la /opt/devkitpro/portlibs/switch/lib/libvulkan.a || exit 1

step "4b/6 NVK (driver Vulkan) com a correcao do compilador de shaders"
bash /host/source/build_nvk.sh || { echo "ERRO: NVK"; exit 1; }
# A new libvulkan.a does not always make ninja relink the NRO: drop the old
# executable so the driver that was just built is the one inside it.
if [ "$(cat /src/nvk/fix_id 2>/dev/null)" != "$(cat /src/.nvk_linked18 2>/dev/null)" ]; then
  find "$BUILD" \( -name gta4nx.nro -o -name gta4nx.elf -o -name gta4nx -o -name gta4nx.nacp \) -type f -delete 2>/dev/null
  cat /src/nvk/fix_id > /src/.nvk_linked18 2>/dev/null
fi

step "5/6 configurar"
# Optional 256x256 icon: put icon.jpg next to README.md.
ICON_ARG=()
[ -f /host/icon.jpg ] && ICON_ARG=(-DGTA4NX_ICON=/host/icon.jpg)
cmake -S "$SRC" -B "$BUILD" -G Ninja \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_TOOLCHAIN_FILE="$SRC/toolchains/switch-devkitA64.cmake" \
  "${ICON_ARG[@]}" || exit 1

step "6/6 compilar (JOBS=$JOBS) - demora (1-3 horas na 1a vez)"
# -k 0: keep compiling after an error so one run shows every error at once
cmake --build "$BUILD" --target gta4nx -j "$JOBS" -- -k 0 || exit 1

# Optional: extract the user's own ISO on the PC (SD cards in FAT32 cannot hold
# a 7.8 GB file). D:\GTA4NX\install\*.iso -> D:\GTA4NX\install\gta4_disc\
ISO=$(ls /host/install/*.iso /isodir/*.iso 2>/dev/null | head -1)
if [ -n "$ISO" ] && [ ! -f /host/install/gta4_disc/default.xex ]; then
  step "extra: extrair a ISO para install/gta4_disc"
  git submodule update --init --depth 1 -- tools/extract-xiso
  cmake -S tools/extract-xiso -B /src/xiso -DCMAKE_BUILD_TYPE=Release -DCMAKE_C_COMPILER=$(command -v gcc || command -v clang) >/dev/null && cmake --build /src/xiso -j "$JOBS" >/dev/null
  XISO=$(find /src/xiso -name extract-xiso -type f | head -1)
  if [ -n "$XISO" ]; then
    mkdir -p /host/install/gta4_disc
    "$XISO" -x "$ISO" -d /host/install/gta4_disc && echo "ISO extraida."
  else
    echo "AVISO: nao consegui compilar o extract-xiso"
  fi
fi

NRO=$(find "$BUILD" -name gta4nx.nro -newer "$SRC/CMakeLists.txt" | head -1)
[ -z "$NRO" ] && NRO=$(find "$BUILD" -name gta4nx.nro | head -1)
if [ -n "$NRO" ]; then
  mkdir -p /host/saida
  cp -f "$NRO" /host/saida/gta4nx.nro
  # unstripped ELF: turns the "imagen+0x..." addresses of the Switch logs into function names
  for e in "${NRO%.nro}.elf" "${NRO%.nro}"; do
    if [ -f "$e" ]; then cp -f "$e" /host/saida/gta4nx.elf; break; fi
  done
  ls -la /host/saida/gta4nx.nro
  echo "NRO_OK"
else
  echo "ERRO: gta4nx.nro nao foi gerado"; exit 1
fi
