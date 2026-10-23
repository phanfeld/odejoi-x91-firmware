"""New program code written in C (design/playlist): the host test, compiling for the player, and placing the code
into the free room at the end of code banks.

Every bank of a program sits in a 1 KB-aligned slot of the file with zeros behind it. Code goes into those tails: a
bank's length in the program's table grows to take it, up to its slot and the most its group may load. The code has
no data of its own and calls the firmware only through fixed addresses (fw.h), so each function is one section that
can go into any tail; functions that call each other often share a bank, since every call into another bank of the
group loads that bank.
"""
import os
import re
import struct

from . import base
from .base import T, fail

SOURCES = ("playlist.c", "library.c", "keys.c", "browse.c", "search.c", "name.c")
LIST_SOURCE = "liststyle.c"                      # list_box: compiled per program on its own (lists.py)
CFLAGS = ["-mcpu=cortex-m4", "-mthumb", "-Os", "-fno-inline", "-ffreestanding", "-fno-builtin", "-nostdlib",
          "-fno-strict-aliasing", "-fno-tree-loop-distribute-patterns", "-ffunction-sections", "-fdata-sections",
          "-fno-common", "-fstack-usage", "-Wall", "-Wextra", "-Werror"]
COLOURS = ("bg", "surface", "line", "text", "text2", "accent", "on_accent")   # passed as -DCOL_BG ... (search, names)
HOST_LIB = os.path.join(base.DUMP, "device_files", "2026-10-21", "M3U.LIB")
BANK_MAX = 0x800                                 # the longest a bank of the 0x1000 group may get
STACK_MAX = 1024                                 # deepest chain of the new code's own frames; the task stack runs from
                                                 # 0x206ac0 down to the engine's stack top 0x205dc0 (3.3 KB)


def theme_flags():
    return ["-DCOL_%s=%#x" % (k.upper(), base.c565(T[k])) for k in COLOURS]


def host_test(work):
    """The new code against a simulated player on the computer (design/playlist/host); stops the build if it fails."""
    exe = os.path.join(work, "host_test")
    src = base.PLAYLIST
    base.run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-DHOST", "-g", "-fsanitize=address,undefined", "-I", src,
              "-o", exe, os.path.join(src, "host", "test.c"), os.path.join(src, "host", "mock.c")]
             + [os.path.join(src, s) for s in SOURCES + (LIST_SOURCE,)], "compiling the host test")
    out = base.run([exe, HOST_LIB], "the host test").strip()
    if "skipped" in out:
        fail("the host test needs the player's M3U.LIB at %s" % HOST_LIB)
    return out.splitlines()[-1]


def sections(obj, what):
    """The object's sections that hold something: (name, size, alignment); only .text.* may."""
    out = []
    for line in base.run(["arm-none-eabi-readelf", "-S", "-W", obj], "readelf").splitlines():
        m = re.match(r"\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+([0-9a-f]+)\s+\S+\s+(\S*)\s+\S+\s+\S+\s+(\d+)", line)
        if not m:
            continue
        name, size, flags, align = m.group(1), int(m.group(3), 16), m.group(4), int(m.group(5))
        if "A" in flags and size:
            if not name.startswith(".text."):
                fail("%s has data the banks cannot hold: %s (%d bytes)" % (what, name, size))
            out.append((name, size, max(align, 4)))
    return out


def compile_code(work):
    """Every source with one section per function, with the theme's colours."""
    objs, secs = [], []
    for src in SOURCES:
        obj = os.path.join(work, src.replace(".c", ".o"))
        base.run(["arm-none-eabi-gcc"] + CFLAGS + theme_flags() + ["-c", os.path.join(base.PLAYLIST, src), "-o", obj],
                 "compiling " + src, cwd=work)
        secs += sections(obj, src)
        objs.append(obj)
    return objs, secs


def stack_depth(work, entries):
    """Deepest chain of the new code's own frames from each entry, from the compiler's per-function figures and the
    call graph (always_inline helpers known by their names: no frame of their own, their calls count for their
    callers)."""
    frames, bodies = {}, {}
    for src in SOURCES:
        for line in open(os.path.join(work, src.replace(".c", ".su"))):
            name, size = line.split()[0].split(":")[-1], int(line.split()[1])
            frames[name.split(".")[0]] = size
        text = open(os.path.join(base.PLAYLIST, src)).read()
        bodies.update(re.findall(r"\n(?:static )?(?:inline __attribute__\(\(always_inline\)\) )?[\w ]+?\**(\w+)\([^;{]*\)"
                                 r"\n\{(.*?)\n\}", text, re.S))
    calls = {f: [g for g in bodies if g != f and re.search(r"\b%s\(" % g, body)] for f, body in bodies.items()}

    def depth(f, seen=()):
        return frames.get(f, 0) + max([depth(g, seen + (f,)) for g in calls.get(f, []) if g not in seen] or [0])
    return {e: depth(e) for e in entries}


def section_base(name):
    return name[len(".text."):].split(".")[0]


def place(b, name, size, align):
    """Put a section into a planned bank tail if it fits."""
    at = (b["at"] + align - 1) & ~(align - 1)
    if at + size > b["top"]:
        return False
    b["secs"].append(name)
    b["at"] = at + size
    return True


def free_tails(ap, window, most):
    """Banks of one group (loaded at 0x10WWWW, address 0x18NNWWWW) whose tail is free, with the room up to their slot
    and `most`: planning entries."""
    out = []
    for hdr, off, addr, ln in base.bank_list(ap):
        if addr >> 24 != 0x18 or addr & 0xffff != window:
            continue
        top = min(base.slot_of(ap, off), most)
        if top <= ln or any(ap[off + ln:off + top]):
            continue
        out.append(dict(addr=addr, hdr=hdr, off=off, len=ln, at=(ln + 3) & ~3, top=top, secs=[]))
    return out


def link(work, objs, banks, entry):
    """Link the planned sections at their banks' ends; each bank's bytes in b["code"]; the symbols' addresses."""
    script = os.path.join(work, "playlist.ld")
    with open(script, "w") as f:
        f.write("ENTRY(%s)\nSECTIONS\n{\n" % entry)
        for bk in sorted(banks, key=lambda bk: bk["addr"]):
            f.write("  .bank_%08x 0x%08x : { %s }\n" % (bk["addr"], bk["addr"] + ((bk["len"] + 3) & ~3),
                                                       " ".join("KEEP(*(%s))" % s for s in bk["secs"])))
        f.write("  /DISCARD/ : { *(.ARM.attributes) *(.comment) *(.note*) }\n}\n")
    elf = os.path.join(work, "playlist.elf")
    base.run(["arm-none-eabi-ld", "-T", script, "-o", elf] + objs + ["--no-undefined"], "linking")
    symbols = {}
    for line in base.run(["arm-none-eabi-nm", elf], "nm").splitlines():
        a, _, name = line.split()
        symbols[name] = int(a, 16)
    open(os.path.join(work, "playlist.dis"), "w").write(base.run(["arm-none-eabi-objdump", "-d", elf], "objdump"))
    for bk in banks:
        raw = os.path.join(work, "bank_%08x.bin" % bk["addr"])
        base.run(["arm-none-eabi-objcopy", "-O", "binary", "--only-section=.bank_%08x" % bk["addr"], elf, raw], "objcopy")
        bk["code"] = open(raw, "rb").read()
        os.remove(raw)
    return symbols


def put_code(ap, banks):
    """Write linked code into its bank tails and grow the banks' lengths."""
    for bk in banks:
        start = (bk["len"] + 3) & ~3
        end = start + len(bk["code"])
        if end > bk["top"] or any(ap[bk["off"] + bk["len"]:bk["off"] + end]):
            fail("bank %#x: the code does not fit its free room" % bk["addr"])
        ap[bk["off"] + start:bk["off"] + end] = bk["code"]
        struct.pack_into("<I", ap, bk["hdr"] + 8, end)
        bk["new_len"] = end


def compile_tail(work, src, func, defines):
    """One function and nothing else, for a bank tail: no data section (no switch tables)."""
    obj = os.path.join(work, func + ".o")
    base.run(["arm-none-eabi-gcc"] + CFLAGS + ["-fno-tree-switch-conversion"] + defines
             + ["-c", os.path.join(base.PLAYLIST, src), "-o", obj], "compiling " + src, cwd=work)
    found = []
    for line in base.run(["arm-none-eabi-readelf", "-S", "-W", obj], "readelf").splitlines():
        f = line.split("]", 1)[1].split() if "] ." in line else []
        if len(f) > 6 and "A" in f[6] and int(f[4], 16):            # name, type, address, offset, size, entry size, flags
            found.append(f[0])
    if found != [".text." + func]:
        fail("%s should give one function and nothing else, not %s" % (src, found))
    frame = int(open(os.path.join(work, func + ".su")).read().split()[1])
    return obj, frame


def put_tail(ap, name, entry, obj, func, work):
    """Link func at the free end of a bank (entry: table offset, file offset, length, room) and put it there."""
    hdr, off, ln, top, bank = entry
    start = (ln + 3) & ~3
    script = os.path.join(work, func + ".ld")
    with open(script, "w") as f:
        f.write("ENTRY(%s)\nSECTIONS\n{\n  .tail 0x%08x : { KEEP(*(.text.%s)) }\n"
                "  /DISCARD/ : { *(.ARM.attributes) *(.comment) *(.note*) }\n}\n" % (func, bank + start, func))
    elf = os.path.join(work, func + ".elf")
    base.run(["arm-none-eabi-ld", "-T", script, "-o", elf, obj, "--no-undefined"], "linking " + func)
    raw = os.path.join(work, func + ".bin")
    base.run(["arm-none-eabi-objcopy", "-O", "binary", "--only-section=.tail", elf, raw], "objcopy")
    code = open(raw, "rb").read()
    open(os.path.join(work, func + ".dis"), "w").write(base.run(["arm-none-eabi-objdump", "-d", elf], "objdump"))
    if start + len(code) > top or any(ap[off + ln:off + top]):
        fail("%s: %s (%d bytes) does not fit the end of bank %#x (%#x of %#x)" % (name, func, len(code), bank, ln, top))
    ap[off + start:off + start + len(code)] = code
    struct.pack_into("<I", ap, hdr + 8, start + len(code))
    return bank + start, len(code)
