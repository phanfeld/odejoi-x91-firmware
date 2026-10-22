#!/usr/bin/env python3
"""Stage 20 of the Graphite design, built on the stage 19 image: the playlist library follows the player's own
playlist changes, "Remove from Playlist" for the .m3u playlists, and the Previous key restarts the song.

  1. "Add to playlist" (stage 18) also writes the change into M3U.LIB, the library the Playlists list shows, so
     a new playlist or a new song shows at once, without "Update list?" (design/playlist/library.c).
  2. "Remove from Playlist" is back in the options of the playing screen (lists 42 and 59, row 5; stage 19 had
     hidden the stock one, which served the built-in lists only). It takes the playing song out of a .m3u chosen
     from the same list as "Add to playlist", and out of M3U.LIB.
  3. Pause and resume around the file work used the wrong engine messages in stage 18 (0x313 is "play" and 0x314
     "stop", the status came from 0x32b, which is the play mode). Now pause 0x315, resume 0x316, status 0x32e,
     as the Play key uses them.
  4. Previous key: after 3 seconds of a song it starts that song again (the engine's seek message, 0x317, with a
     break point at 0, as the stock "Resume" plays a bookmark); within the first 3 seconds it goes to the
     previous song as before. MUSIC.AP 0x180a13b6 calls the new code instead of the stock "previous".

The new code (design/playlist: playlist.c, library.c, keys.c) is compiled for the player and placed into the free
room at the end of code banks of MUSIC.AP, the way stage 18 did it; the stage 18 code is taken out of its three
banks first and placed anew with the rest. Before anything is built, the code runs against a simulated disk on
the computer (design/playlist/host), and the library functions also run on the player's own M3U.LIB. The
sources are the frozen copy in design/playlist/stage20 (stage 21 changed the live ones); the host test ran on them
when this stage was built.

usage: build_stage20.py [OUT_DIR]      (default: ../x91_dump/stage20)
"""
import hashlib
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(HERE, "playlist", "stage20")  # the sources as this stage shipped them (stage 21 changed the live ones)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_modify as xm  # noqa: E402
from build_stage18 import CFLAGS, BANK_TABLES, BANK_MAX, run, bank_entry, put_code  # noqa: E402

SOURCES = ("playlist.c", "library.c", "keys.c")
HOST_LIB = os.path.join(ROOT, "x91_dump", "device_files", "2026-10-21", "M3U.LIB")
ENTRIES = ("add_playing_to_playlist", "remove_playing_from_playlist", "previous_key")
STAGE18_BANKS = {0x180e1000: (0x424, 0x744), 0x18321000: (0x448, 0x7e0), 0x18161000: (0x450, 0x7e4)}  # stock, stage 18
# Functions that call each other often share a bank (every call into another bank of the group loads that bank,
# and the return loads the caller's again). Each group goes into the bank whose free room fits it best.
GROUPS = (("remove_line", "line_done", "pause_playing", "file_name"),
          ("add_playing_to_playlist", "append", "create_new"),
          ("pick", "draw", "fill_rows", "new_playlist_text", "append_number"),
          ("rd", "wr", "rd16", "wr16", "find_song", "lib_add_song", "lib_find_list", "record_tail"),
          ("lib_add_list", "lib_remove_song", "write_list"),
          ("entry_name", "playlist_name", "find_playlist", "song_path", "find_new", "choice_name"),
          ("remove_playing_from_playlist", "report", "library_add", "library_remove"),
          ("write_song", "lib_open", "lib_close"))
PINNED = {"previous_key": 0x180a1000}           # beside the key code that calls it
STACK_MAX = 1024                                 # deepest chain of the new code; the task stack runs from 0x206ac0 down to
                                                 # the engine's stack top 0x205dc0 (3.3 KB)
OPTION_LISTS = (42, 59)                          # MUSIC.MCG: options of the playing screen
ADD_ROW, REMOVE_ROW = 4, 5
COMMON_FN = 0x181815a3                           # the rows' shared routine (field 7), as the stock rows have it
PREV_CALL = 0x180a13b6                           # MUSIC.AP: bl to the stock "previous" in the Previous key's code
# what the frozen sources gave when stage 20 went to the player
CODE_SHA = "8308a6959080c0636d5aca48d7df4a87dbc9192d14751adfb8900580d1c078a7"


def host_test(work):
    if not os.path.isdir(os.path.join(SRC, "host")):
        return "not run here: the frozen sources were tested when their stage was built (the code is checked instead)"
    exe = os.path.join(work, "host_test")
    run(["cc", "-std=c99", "-Wall", "-Wextra", "-Werror", "-DHOST", "-g", "-fsanitize=address,undefined", "-I", SRC,
         "-o", exe, os.path.join(SRC, "host", "test.c"), os.path.join(SRC, "host", "mock.c")]
        + [os.path.join(SRC, s) for s in SOURCES], "compiling the host test")
    out = run([exe, HOST_LIB], "the host test").strip()
    if "skipped" in out:
        sys.exit("the host test needs the player's M3U.LIB at %s" % HOST_LIB)
    return out.splitlines()[-1]


def compile_code(work):
    objs, secs = [], []
    for src in SOURCES:
        obj = os.path.join(work, src.replace(".c", ".o"))
        run(["arm-none-eabi-gcc"] + CFLAGS + ["-c", os.path.join(SRC, src), "-o", obj], "compiling " + src, cwd=work)
        for line in run(["arm-none-eabi-readelf", "-S", "-W", obj], "readelf").splitlines():
            m = re.match(r"\s*\[\s*\d+\]\s+(\S+)\s+(\S+)\s+\S+\s+\S+\s+([0-9a-f]+)\s+\S+\s+(\S*)\s+\S+\s+\S+\s+(\d+)", line)
            if not m:
                continue
            name, size, flags, align = m.group(1), int(m.group(3), 16), m.group(4), int(m.group(5))
            if "A" in flags and size:
                if not name.startswith(".text."):
                    sys.exit("%s has data the banks cannot hold: %s (%d bytes)" % (src, name, size))
                secs.append((name, size, max(align, 4)))
        objs.append(obj)
    return objs, secs


def stack_depth(work):
    """Deepest chain of the new code's own frames, from the compiler's per-function figures and the call graph."""
    frames, bodies = {}, {}
    for src in SOURCES:
        for line in open(os.path.join(work, src.replace(".c", ".su"))):
            name, size = line.split()[0].split(":")[-1], int(line.split()[1])
            frames[name.split(".")[0]] = size
        text = open(os.path.join(SRC, src)).read()
        bodies.update(re.findall(r"\n(?:static )?[\w ]+?\**(\w+)\([^;{]*\)\n\{(.*?)\n\}", text, re.S))
    calls = {f: [g for g in bodies if g != f and re.search(r"\b%s\(" % g, b)] for f, b in bodies.items()}

    def depth(f, seen=()):
        return frames.get(f, 0) + max([depth(g, seen + (f,)) for g in calls.get(f, []) if g not in seen] or [0])
    return {e: depth(e) for e in ENTRIES}


def take_out_stage18(ap):
    """The stage 18 code leaves its three banks: stock lengths again, zeros behind."""
    for addr, (stock, grown) in STAGE18_BANKS.items():
        hdr, off, ln = bank_entry(ap, addr)
        if ln != grown:
            sys.exit("MUSIC.AP: bank %#x is %#x long, not stage 18's %#x" % (addr, ln, grown))
        ap[off + stock:off + grown] = bytes(grown - stock)
        struct.pack_into("<I", ap, hdr + 8, stock)


def plan(ap, secs):
    starts = sorted(struct.unpack_from("<I", ap, t + i)[0] for t in BANK_TABLES for i in range(0, 0x800, 12)
                    if struct.unpack_from("<III", ap, t + i)[0] and struct.unpack_from("<III", ap, t + i)[2])
    banks = []
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", ap, t + i)
            if not (off and ln) or addr >> 24 != 0x18 or addr & 0xffff != 0x1000:
                continue                         # only the group that loads at 0x101000 (window up to 0x101800)
            slot = min([s for s in starts if s > off] + [len(ap)]) - off
            top = min(slot, BANK_MAX)
            if top <= ln or any(ap[off + ln:off + top]):
                continue
            banks.append(dict(addr=addr, hdr=t + i, off=off, len=ln, at=(ln + 3) & ~3, top=top, secs=[]))

    def place(b, name, size, align):
        at = (b["at"] + align - 1) & ~(align - 1)
        if at + size > b["top"]:
            return False
        b["secs"].append(name)
        b["at"] = at + size
        return True

    base = lambda name: name[len(".text."):].split(".")[0]
    by = {base(n): (n, s, a) for n, s, a in secs}
    left = dict(by)
    for fn, addr in PINNED.items():
        b = next(b for b in banks if b["addr"] == addr)
        if not place(b, *by[fn]):
            sys.exit("%s does not fit bank %#x" % (fn, addr))
        del left[fn]
    for group in sorted(GROUPS, key=lambda g: -sum(by[f][1] + 3 for f in g if f in by)):
        members = [by[f] for f in group if f in left]
        need = sum((s + 3) & ~3 for _, s, _ in members)
        fits = [b for b in banks if not b["secs"] and b["top"] - b["at"] >= need]
        if not fits:
            continue                             # placed one by one below
        b = min(fits, key=lambda b: b["top"] - b["at"])
        for m in members:
            place(b, *m)
            del left[base(m[0])]
    for name, size, align in sorted(left.values(), key=lambda s: -s[1]):
        if not any(place(b, name, size, align) for b in sorted(banks, key=lambda b: b["top"] - b["at"])):
            sys.exit("no room left for %s (%d bytes)" % (name, size))
    return [b for b in banks if b["secs"]]


def link(work, objs, banks):
    script = os.path.join(work, "playlist.ld")
    with open(script, "w") as f:
        f.write("ENTRY(%s)\nSECTIONS\n{\n" % ENTRIES[0])
        for b in sorted(banks, key=lambda b: b["addr"]):
            f.write("  .bank_%08x 0x%08x : { %s }\n" % (b["addr"], b["addr"] + ((b["len"] + 3) & ~3),
                                                       " ".join("KEEP(*(%s))" % s for s in b["secs"])))
        f.write("  /DISCARD/ : { *(.ARM.attributes) *(.comment) *(.note*) }\n}\n")
    elf = os.path.join(work, "playlist.elf")
    run(["arm-none-eabi-ld", "-T", script, "-o", elf] + objs + ["--no-undefined"], "linking")
    symbols = {}
    for line in run(["arm-none-eabi-nm", elf], "nm").splitlines():
        a, kind, name = line.split()
        symbols[name] = int(a, 16)
    open(os.path.join(work, "playlist.dis"), "w").write(run(["arm-none-eabi-objdump", "-d", elf], "objdump"))
    for b in banks:
        raw = os.path.join(work, "bank_%08x.bin" % b["addr"])
        run(["arm-none-eabi-objcopy", "-O", "binary", "--only-section=.bank_%08x" % b["addr"], elf, raw], "objcopy")
        b["code"] = open(raw, "rb").read()
        os.remove(raw)
    return symbols


def thumb_bl(at, target):
    off = target - (at + 4)
    if not -(1 << 24) <= off < (1 << 24) or off & 1:
        sys.exit("bl from %#x cannot reach %#x" % (at, target))
    s = (off >> 24) & 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~i1 ^ s) & 1, (~i2 ^ s) & 1
    hi = 0xf000 | (s << 10) | ((off >> 12) & 0x3ff)
    lo = 0xd000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7ff)
    return struct.pack("<HH", hi, lo)


def previous_key_call(ap, target):
    segs, _ = ap_dis.segments(bytes(ap))
    at = ap_dis.find(segs, PREV_CALL)
    stock = thumb_bl(PREV_CALL, 0x180a151a)      # the veneer to the resident "previous" (0x1102b5)
    veneer = ap_dis.find(segs, 0x180a151a)
    if at is None or bytes(ap[at:at + 4]) != stock or bytes(ap[veneer:veneer + 10]) != bytes.fromhex("40f2b52cc0f2110c6047"):
        sys.exit("MUSIC.AP: the Previous key's call is not the expected code")
    ap[at:at + 4] = thumb_bl(PREV_CALL, target)


def menu_rows(lfi, add, remove):
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    for li in OPTION_LISTS:
        eid, cnt, off, link = struct.unpack_from("<HHII", mcg, hsz + li * 12)
        rows = [list(struct.unpack_from("<HHHHIII", mcg, off + k * 20)) for k in range(cnt)]
        a = rows[ADD_ROW]
        if cnt != 7 or a[0] != 0x7fff or a[1] != 5 or a[3] != 15 or a[6] != COMMON_FN or rows[REMOVE_ROW][1] != 36 or any(mcg[off + cnt * 20:off + cnt * 20 + 20]):
            sys.exit("MUSIC.MCG: list %d is not stage 19's options of the playing screen" % li)
        a[4] = add | 1
        rows.insert(REMOVE_ROW, [0x7fff, 34, 88, 16, remove | 1, 0, COMMON_FN])     # "Remove from Playlist", its icon
        mcg[off:off + (cnt + 1) * 20] = b"".join(struct.pack("<HHHHIII", *r) for r in rows)
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, cnt + 1, off, link)
        for j in range(n):                       # sub-menus behind the new row: their parent row moves down (the
            e, c, o, lk = struct.unpack_from("<HHII", mcg, hsz + j * 12)          # inverse of stage 19's remove_row)
            if lk != 0xffffffff and lk & 0xffff == li and lk >> 16 > REMOVE_ROW:
                struct.pack_into("<HHII", mcg, hsz + j * 12, e, c, o, lk + 0x10000)
    lfi.put("MUSIC.MCG", bytes(mcg))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage20")
    work = os.path.join(out, "code")
    os.makedirs(work, exist_ok=True)
    print("host test:", host_test(work))
    objs, secs = compile_code(work)
    depths = stack_depth(work)
    if max(depths.values()) > STACK_MAX:
        sys.exit("the new code's deepest call chain needs %d bytes of stack" % max(depths.values()))

    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE19") or os.path.join(ROOT, "x91_dump", "stage19", "x91_lfi_stage19.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 19 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    ap = bytearray(lfi.get("MUSIC.AP"))
    take_out_stage18(ap)
    banks = plan(ap, secs)
    symbols = link(work, objs, banks)
    put_code(ap, banks)
    code_sha = hashlib.sha256(b"".join(struct.pack("<I", b["addr"]) + b["code"] for b in sorted(banks, key=lambda b: b["addr"]))).hexdigest()
    if SRC.endswith("stage20") and code_sha != CODE_SHA:
        sys.exit("the frozen stage 20 sources no longer give the stage 20 code (%s)" % code_sha)
    segs, _ = ap_dis.segments(bytes(ap))
    for e in ENTRIES:
        if ap_dis.find(segs, symbols[e]) is None:
            sys.exit("%s is outside the program's banks" % e)
    previous_key_call(ap, symbols["previous_key"])
    lfi.put("MUSIC.AP", bytes(ap))
    menu_rows(lfi, symbols["add_playing_to_playlist"], symbols["remove_playing_from_playlist"])

    print("new code: %d bytes in %d banks; deepest stack chain %d bytes (%s)"
          % (sum(len(b["code"]) for b in banks), len(banks), max(depths.values()),
             ", ".join("%s %d" % (e, d) for e, d in depths.items())))
    for b in sorted(banks, key=lambda b: b["addr"]):
        print("  bank %#x: length %#x -> %#x (%s)" % (b["addr"], b["len"], b["new_len"],
                                                    ", ".join(s[6:].split(".")[0] for s in b["secs"])))
    print("entries: add %#x, remove %#x, previous key %#x" % tuple(symbols[e] | 1 for e in ENTRIES))
    print("menus: \"Remove from Playlist\" in lists %s, row %d" % (", ".join(map(str, OPTION_LISTS)), REMOVE_ROW))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage20.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
