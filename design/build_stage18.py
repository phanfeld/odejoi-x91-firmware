#!/usr/bin/env python3
"""Stage 18 of the Graphite design, built on the stage 17 image: "Add to playlist" writes the .m3u files.

In the options of the playing screen, "Add to playlist" no longer offers the three built-in lists. It opens a list
of the .m3u files in the root folder with "New playlist" on top (new code, design/playlist/playlist.c); choosing
one appends the playing song's path to that file in the form the sync writes, or creates "New playlist N.m3u".

How the code gets in:
  - playlist.c is compiled for the player (Cortex-M4, Thumb) with one section per function, and the functions are
    placed into the free room at the end of code banks of MUSIC.AP: every bank sits in a 1 KB-aligned slot of the
    file and the rest of its slot is zeros. A bank's length in the program header grows to take the new code; no
    bank grows past its slot or past 0x800 bytes (banks of this group reach 0xa88 in SETTING.AP).
  - The code calls the firmware only through fixed addresses (design/playlist/fw.h) and has no data of its own.
  - In MUSIC.MCG the "Add to playlist" row of both option lists of the playing screen (lists 42 and 59) becomes
    a leaf that runs the new code, like "Delete" next to it.
  - PLAYLIST.AP, the library builder, reads the .m3u files only when it runs after power-up (entry mode 14) or
    after USB mode (15), as in the SDK (plist_main.c); "Update list?" in the music menu (mode 2) left the
    playlists as they were. One instruction makes every run read them (0x180210b2: movs r7, #0 -> #1).
Before anything is built, the code runs against a simulated disk on the computer (host/). The sources are the
frozen copy in design/playlist/stage18; design/playlist itself holds the later version (stage 20).

usage: build_stage18.py [OUT_DIR]      (default: ../x91_dump/stage18)
"""
import hashlib
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "playlist", "stage18")  # the sources as this stage shipped them; stage 20 changed the live ones
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_modify as xm  # noqa: E402

CFLAGS = ["-mcpu=cortex-m4", "-mthumb", "-Os", "-fno-inline", "-ffreestanding", "-fno-builtin", "-nostdlib",
          "-fno-strict-aliasing", "-fno-tree-loop-distribute-patterns", "-ffunction-sections", "-fdata-sections",
          "-fno-common", "-fstack-usage", "-Wall", "-Wextra", "-Werror"]
BANKS = (0x180e1000, 0x18321000, 0x18161000, 0x182a1000, 0x18461000)   # MUSIC.AP banks whose tails take the code
BANK_MAX = 0x800
GROUPS = (("pick", "draw", "fill_rows", "new_playlist_text"),                 # the list; BANKS[0]
          ("entry_name", "playlist_name", "find_playlist", "song_path", "append_number", "choice_name", "report_added"),
          ("add_playing_to_playlist", "append", "create_new"))
BANK_TABLES = (0x800, 0x1000, 0x1800, 0x2000)
ENTRY = "add_playing_to_playlist"
OPTION_LISTS = (42, 59)                          # MUSIC.MCG: options of the playing screen
ADD_ROW = 4                                      # "Add to playlist" in those lists
STACK_MAX = 1024                                 # deepest chain of the new code; the task stack runs from 0x206ac0 down to
                                                 # the engine's stack top 0x205dc0 (3.3 KB)


def run(cmd, what, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        sys.exit("%s failed:\n%s%s" % (what, r.stdout[-1500:], r.stderr[-1500:]))
    return r.stdout


def host_test(work):
    exe = os.path.join(work, "host_test")
    run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-DHOST", "-g", "-fsanitize=address,undefined", "-I", SRC,
         "-o", exe, os.path.join(SRC, "host", "test.c"), os.path.join(SRC, "host", "mock.c"), os.path.join(SRC, "playlist.c")],
        "compiling the host test")
    return run([exe], "the host test").strip()


def compile_code(work):
    obj = os.path.join(work, "playlist.o")
    run(["arm-none-eabi-gcc"] + CFLAGS + ["-c", os.path.join(SRC, "playlist.c"), "-o", obj], "compiling playlist.c", cwd=work)
    secs = []
    for line in run(["arm-none-eabi-readelf", "-S", "-W", obj], "readelf").splitlines():
        m = re.match(r"\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+([0-9a-f]+)\s+\S+\s+(\S*)\s+\S+\s+\S+\s+(\d+)", line)
        if not m:
            continue
        name, kind, size, flags, align = m.group(1), m.group(2), int(m.group(3), 16), m.group(4), int(m.group(5))
        if "A" in flags and size:
            if not name.startswith(".text."):
                sys.exit("playlist.c has data the banks cannot hold: %s (%d bytes)" % (name, size))
            secs.append((name, size, max(align, 4)))
    if run(["arm-none-eabi-nm", "-u", obj], "nm").strip():
        sys.exit("playlist.c needs outside symbols")
    return obj, secs


def stack_depth(work):
    """Deepest chain of the new code's own frames, from the compiler's per-function figures and the call graph."""
    frames = {}
    for line in open(os.path.join(work, "playlist.su")):
        name, size = line.split()[0].split(":")[-1], int(line.split()[1])
        frames[name.split(".")[0]] = size
    src = open(os.path.join(SRC, "playlist.c")).read()
    bodies = dict(re.findall(r"\n(?:static )?[\w ]+?\**(\w+)\([^;{]*\)\n\{(.*?)\n\}", src, re.S))
    calls = {f: [g for g in bodies if g != f and re.search(r"\b%s\(" % g, b)] for f, b in bodies.items()}

    def depth(f, seen=()):
        return frames.get(f, 0) + max([depth(g, seen + (f,)) for g in calls.get(f, []) if g not in seen] or [0])
    return depth(ENTRY)


def bank_entry(ap, addr):
    for table in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, a, ln = struct.unpack_from("<III", ap, table + i)
            if off and ln and a == addr:
                return table + i, off, ln
    sys.exit("MUSIC.AP has no bank at %#x" % addr)


def plan(ap, secs):
    """Functions that call each other often share a bank: every call into another bank of the group swaps banks."""
    starts = sorted(struct.unpack_from("<I", ap, t + i)[0] for t in BANK_TABLES for i in range(0, 0x800, 12)
                    if struct.unpack_from("<III", ap, t + i)[0] and struct.unpack_from("<III", ap, t + i)[2])
    banks = []
    for addr in BANKS:
        hdr, off, ln = bank_entry(ap, addr)
        slot = min([s for s in starts if s > off] + [len(ap)]) - off
        top = min(slot, BANK_MAX)
        if any(ap[off + ln:off + top]):
            sys.exit("MUSIC.AP: the end of bank %#x is not free" % addr)
        banks.append(dict(addr=addr, hdr=hdr, off=off, len=ln, at=(ln + 3) & ~3, top=top, secs=[]))

    def place(b, name, size, align):
        at = (b["at"] + align - 1) & ~(align - 1)
        if at + size > b["top"]:
            return False
        b["secs"].append(name)
        b["at"] = at + size
        return True

    base = lambda name: name[len(".text."):].split(".")[0]
    rest = []
    for name, size, align in secs:
        k = [i for i, group in enumerate(GROUPS) if base(name) in group]
        if not k or not place(banks[k[0]], name, size, align):
            rest.append((name, size, align))
    for name, size, align in sorted(rest, key=lambda s: -s[1]):           # anything else: first fit
        if not any(place(b, name, size, align) for b in banks):
            sys.exit("no room left for %s (%d bytes)" % (name, size))
    return [b for b in banks if b["secs"]]


def link(work, obj, banks):
    script = os.path.join(work, "playlist.ld")
    with open(script, "w") as f:
        f.write("ENTRY(%s)\nSECTIONS\n{\n" % ENTRY)
        for b in banks:
            f.write("  .bank_%08x 0x%08x : { %s }\n" % (b["addr"], b["addr"] + ((b["len"] + 3) & ~3),
                                                       " ".join("KEEP(*(%s))" % s for s in b["secs"])))
        f.write("  /DISCARD/ : { *(.ARM.attributes) *(.comment) *(.note*) }\n}\n")
    elf = os.path.join(work, "playlist.elf")
    run(["arm-none-eabi-ld", "-T", script, "-o", elf, obj, "--no-undefined"], "linking")
    symbols = {}
    for line in run(["arm-none-eabi-nm", elf], "nm").splitlines():
        a, _, name = line.split()
        symbols[name] = int(a, 16)
    run(["arm-none-eabi-objdump", "-d", elf], "objdump")
    open(os.path.join(work, "playlist.dis"), "w").write(run(["arm-none-eabi-objdump", "-d", elf], "objdump"))
    for b in banks:
        raw = os.path.join(work, "bank_%08x.bin" % b["addr"])
        run(["arm-none-eabi-objcopy", "-O", "binary", "--only-section=.bank_%08x" % b["addr"], elf, raw], "objcopy")
        b["code"] = open(raw, "rb").read()
        os.remove(raw)
    return symbols


def put_code(ap, banks):
    for b in banks:
        start = (b["len"] + 3) & ~3
        end = start + len(b["code"])
        if end > b["top"] or any(ap[b["off"] + b["len"]:b["off"] + end]):
            sys.exit("bank %#x: the code does not fit its free room" % b["addr"])
        ap[b["off"] + start:b["off"] + end] = b["code"]
        struct.pack_into("<I", ap, b["hdr"] + 8, end)
        b["new_len"] = end


def builder_reads_playlists(lfi):
    ap = bytearray(lfi.get("PLAYLIST.AP"))
    segs, _ = ap_dis.segments(bytes(ap))
    at = ap_dis.find(segs, 0x180210a8)
    old = bytes.fromhex("04f0600008b1012700e00027")      # and.w r0, r4, #0x60; cbz; movs r7, #1; b; movs r7, #0
    if at is None or bytes(ap[at:at + len(old)]) != old:
        sys.exit("PLAYLIST.AP: the playlist decision is not the expected code")
    ap[at + len(old) - 2] = 0x01
    lfi.put("PLAYLIST.AP", bytes(ap))


def menu_rows(lfi, entry):
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    for li in OPTION_LISTS:
        _, cnt, off, _ = struct.unpack_from("<HHII", mcg, hsz + li * 12)
        row = off + ADD_ROW * 20
        first, text, text2, icon, run_fn, z, common = struct.unpack_from("<HHHHIII", mcg, row)
        if cnt != 8 or text != 5 or icon != 15 or run_fn != 0x18201121 or first == 0x7fff:
            sys.exit("MUSIC.MCG: list %d row %d is not the stock \"Add to playlist\"" % (li, ADD_ROW))
        struct.pack_into("<HHHHIII", mcg, row, 0x7fff, text, text2, icon, entry | 1, z, common)
    lfi.put("MUSIC.MCG", bytes(mcg))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage18")
    work = os.path.join(out, "code")
    os.makedirs(work, exist_ok=True)
    print("host test:", host_test(work))
    obj, secs = compile_code(work)
    deepest = stack_depth(work)
    if deepest > STACK_MAX:
        sys.exit("the new code's deepest call chain needs %d bytes of stack" % deepest)

    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE17") or os.path.join(ROOT, "x91_dump", "stage17", "x91_lfi_stage17.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 17 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    ap = bytearray(lfi.get("MUSIC.AP"))
    banks = plan(ap, secs)
    symbols = link(work, obj, banks)
    put_code(ap, banks)
    segs, _ = ap_dis.segments(bytes(ap))
    entry = symbols[ENTRY]
    if ap_dis.find(segs, entry) is None:
        sys.exit("the entry point is outside the program's banks")
    lfi.put("MUSIC.AP", bytes(ap))
    menu_rows(lfi, entry)
    builder_reads_playlists(lfi)

    print("playlist code: %d bytes in %d banks, entry %#x, deepest stack chain %d bytes"
          % (sum(len(b["code"]) for b in banks), len(banks), entry | 1, deepest))
    for b in banks:
        print("  bank %#x: length %#x -> %#x (%s)" % (b["addr"], b["len"], b["new_len"],
                                                    ", ".join(s[6:] for s in b["secs"])))
    print("menus: \"Add to playlist\" of lists %s runs the new code" % ", ".join(map(str, OPTION_LISTS)))
    print("library builder: reads the .m3u files on every run, \"Update list?\" included")
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage18.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
