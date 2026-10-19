#!/usr/bin/env python3
# GTA4NX v18 - optimizes the recompiled game code for the Switch build (runs on every build,
# inside the patched copy of the sources, before it is synced into the build tree; idempotent).
#
# 1. Direct calls (method of the Need for Speed: Most Wanted port, tools/llamadas_directas.py):
#    every game function sub_X is a weak alias of __imp__sub_X so that a hook can replace it at
#    link time, and GCC never inlines a call through a weak alias. `sub_X(ctx, base);` becomes
#    `__imp__sub_X(ctx, base);` (the same function) when sub_X has no hook. Any 82xxxxxx address
#    that appears in the port's sources, the SDK or the toml files counts as hooked, so hooks and
#    the strong replacements (switch_audio_fast.cpp, android hooks) keep working. The table for
#    indirect calls (gta4_init.cpp / gta4_register.cpp) is not touched.
#
# 2. Loop barriers: on the Switch the guest memory accesses are plain loads and stores (no
#    `volatile`, gta4_init.h REX_GUEST_NONVOLATILE), so GCC can keep guest values in registers.
#    A loop that polls a value another thread writes would then never see the change. Every
#    backward jump (goto to a label already seen in the same function, i.e. every loop) gets a
#    compiler barrier, REX_LOOP_BARRIER(), so each iteration reads memory again. Costs no
#    instruction; only stops the compiler from carrying guest values across iterations.
#
# 3. v18 - cache prefetch: the recompiler turns the PowerPC cache hints `dcbt`/`dcbtst` into
#    comments. The game's programmers placed them where the data is not in the cache: in the
#    audio reverb (sub_82935BD0) one load waiting on memory held 6.5 % of the audio thread's time
#    (sd_logs41), right after eight dcbt of its delay lines that did nothing. Each one becomes
#    REX_DCBT/REX_DCBTST (gta4_init.h): a PRFM on the Switch, which never faults and changes no
#    state, so it can only cost one instruction. dcbz/dcbf are not touched.
#
# Usage: otimizar_codigo_gerado_v18.py <gta4-recomp dir> <repository root>
#        otimizar_codigo_gerado_v18.py --dcbt-only <file.cpp>   (prefetch only, e.g. switch_audio_fast.cpp)
import os
import re
import sys

MARK = "// gta4nx-optimized-v2\n"


def hooked_names(root, recomp):
    sources = [
        os.path.join(recomp, "src"),
        os.path.join(root, "glue", "rexglue-sdk-main", "src"),
        os.path.join(root, "glue", "rexglue-sdk-main", "include"),
        os.path.join(recomp, "gta4_config.toml"),
        os.path.join(recomp, "gta4_manifest.toml"),
        os.path.join(recomp, "CMakeLists.txt"),
        os.path.join(root, "LibertyRecompLib"),
    ]
    names = set()
    for src in sources:
        if os.path.isfile(src):
            paths = [src]
        elif os.path.isdir(src):
            paths = [os.path.join(d, f) for d, _, fs in os.walk(src) for f in fs
                     if f.endswith((".cpp", ".c", ".h", ".hpp", ".inc", ".toml", ".txt", ".cmake"))]
        else:
            continue
        for path in paths:
            try:
                text = open(path, encoding="utf-8", errors="ignore").read()
            except OSError:
                continue
            for m in re.findall(r"(?<![0-9A-Fa-f])(82[0-9A-Fa-f]{6})(?![0-9A-Fa-f])", text):
                names.add(m.upper())
    return names


CALL = re.compile(r"(?<![\w])sub_([0-9A-F]{8})\(ctx, base\);")
FUNC = re.compile(r'^(?:DEFINE_REX_FUNC\(|extern "C" REX_FUNC\()', re.M)
LABEL = re.compile(r"^loc_([0-9A-F]{8}):", re.M)
GOTO = re.compile(r"goto loc_([0-9A-F]{8});")
DCBT = re.compile(r"^([ \t]*)// (dcbt|dcbtst) r(\d+),r(\d+)[ \t]*$", re.M)
LOCAL_REG = re.compile(r"\bPPCRegister r(\d+)\b")


def split_functions(text):
    starts = [m.start() for m in FUNC.finditer(text)]
    if not starts:
        return text, []
    starts.append(len(text))
    return text[:starts[0]], [text[a:b] for a, b in zip(starts, starts[1:])]


def add_loop_barriers_body(body):
    seen = set()
    pieces = []
    pos = 0
    count = 0
    events = sorted([(m.start(), "L", m) for m in LABEL.finditer(body)] +
                    [(m.start(), "G", m) for m in GOTO.finditer(body)], key=lambda e: e[0])
    for at, kind, m in events:
        if kind == "L":
            seen.add(m.group(1))
            continue
        if m.group(1) in seen:
            pieces.append(body[pos:at])
            pieces.append("{ REX_LOOP_BARRIER(); goto loc_%s; }" % m.group(1))
            pos = m.end()
            count += 1
    pieces.append(body[pos:])
    return "".join(pieces), count


def add_prefetch_body(body):
    local = set(LOCAL_REG.findall(body))

    def reg(n):
        return ("r%s.u32" if n in local else "ctx.r%s.u32") % n

    count = [0]

    def repl(m):
        indent, op, ra, rb = m.groups()
        ea = reg(rb) if ra == "0" else "%s + %s" % (reg(ra), reg(rb))
        count[0] += 1
        macro = "REX_DCBT" if op == "dcbt" else "REX_DCBTST"
        return "%s// %s r%s,r%s\n%s%s(%s);" % (indent, op, ra, rb, indent, macro, ea)

    return DCBT.sub(repl, body), count[0]


def prefetch_file(path):
    text = open(path, encoding="utf-8").read()
    if "REX_DCBT(" in text:
        print("%s: prefetch ja aplicado" % path)
        return
    head, funcs = split_functions(text)
    out = [head]
    n = 0
    for body in funcs:
        body, c = add_prefetch_body(body)
        n += c
        out.append(body)
    open(path, "w", encoding="utf-8", newline="\n").write("".join(out))
    print("%s: %d prefetch (dcbt)" % (path, n))


def main():
    if len(sys.argv) == 3 and sys.argv[1] == "--dcbt-only":
        prefetch_file(sys.argv[2])
        return
    recomp, root = sys.argv[1], sys.argv[2]
    gen = os.path.join(recomp, "generated")
    hooked = hooked_names(root, recomp)
    direct = barriers = prefetches = files = 0
    for f in sorted(os.listdir(gen)):
        if not (f.startswith("gta4_recomp.") and f.endswith(".cpp")):
            continue
        path = os.path.join(gen, f)
        text = open(path, encoding="utf-8").read()
        if text.startswith(MARK):
            continue
        n_before = len(CALL.findall(text))
        text = CALL.sub(lambda m: m.group(0) if m.group(1) in hooked
                        else "__imp__sub_%s(ctx, base);" % m.group(1), text)
        direct += n_before - len(CALL.findall(text))
        head, funcs = split_functions(text)
        out = [head]
        for body in funcs:
            body, c = add_loop_barriers_body(body)
            barriers += c
            body, c = add_prefetch_body(body)
            prefetches += c
            out.append(body)
        open(path, "w", encoding="utf-8", newline="\n").write(MARK + "".join(out))
        files += 1
    print("codigo gerado otimizado: %d ficheiros, %d chamadas diretas, %d barreiras de ciclo, "
          "%d prefetch (dcbt), %d enderecos com gancho respeitados"
          % (files, direct, barriers, prefetches, len(hooked)))


if __name__ == "__main__":
    main()
