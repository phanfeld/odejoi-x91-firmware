#!/usr/bin/env python3
"""Stage 23 of the Graphite design, built on the stage 22 image: two fixes found on the player.

  1. The playlist picker ("Add to playlist", "Remove from Playlist", "Move song") put six rows on a page, but its
     list style (COMMON.STY list box 4, 0x6004, the stock "Add to playlist" sub-menu) has five lines: the firmware
     drew the sixth row over the first, so with more than five rows the list showed the wrong first row and the
     selection mark jumped to the top (stage 22, owner). Now five rows (design/playlist/playlist.h ROWS); the
     builder checks the style's line count against it.
  2. The Previous key with the screen off: the program's shared key filter (MUSIC.AP 0x18b41a00) handles
     Previous, Next, Play and the volume itself while the screen is off and sent "previous" straight to the
     engine, past the stage 20 code. Its call (0x18b41a6e, to 0x18da1cec with 0) now goes to standby_previous
     (design/playlist/keys.c): the same check as stock (the music engine runs), then restart or previous song as
     with the screen on, by the engine's own playing time (the playing screen's copy stands still while the
     screen is off). Only in the music program: the other programs keep their own filter.

The code is placed the way stage 21 did it: the stage 21 code leaves its banks and everything is placed anew;
the calls and menu rows that led to the old code are pointed at the new.

usage: build_stage23.py [OUT_DIR]      (default: ../x91_dump/stage23)
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage11 as s11  # noqa: E402
import build_stage21 as s21  # noqa: E402   (sets up build_stage20 for the stage 21 code; changed below)
from build_stage18 import BANK_TABLES, put_code  # noqa: E402

s20 = s21.s20
s20.SRC = os.path.join(HERE, "playlist", "stage23")   # the sources as this stage shipped them (stage 24 changed the live ones)
s20.ENTRIES = s20.ENTRIES + ("standby_previous",)

STANDBY_CALL = 0x18b41a6e                         # MUSIC.AP shared key filter: bl to "previous/next" with r0 = 0
STOCK_STANDBY = 0x18da1cec                        # sends 0x31a (r0 = 1) or 0x31b (r0 = 0) while the music engine runs
FILTER_BANK = 0x18b41a00
PICKER_STYLE = 4                                  # COMMON.STY list box record of style 0x6004
LINES_AT = 23                                     # its byte: lines on a page (byte 22: row height)
CODE_SHA = "8ee2f3776eaf5dc2fd4a29cf583fa7472b786cc854c95ba427830d57b609671f"   # the placed code of the frozen sources


def old_code(ap, stock_ap):
    """Address ranges of the code earlier stages put behind the stock banks."""
    stock = {}
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", stock_ap, t + i)
            if off and ln:
                stock[addr] = ln
    out = []
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", ap, t + i)
            if off and ln and ln > stock.get(addr, ln):
                out.append((addr + stock[addr], addr + ln))
    return out


def inside(ranges, a):
    return any(lo <= (a & ~1) < hi for lo, hi in ranges)


def picker_lines(lfi):
    com = lfi.get("COMMON.STY")
    off, n = s11.tables_of(com)[6]
    lines = com[off + PICKER_STYLE * 28 + LINES_AT]
    rows = int(next(l.split()[2] for l in open(os.path.join(s20.SRC, "playlist.h")) if l.startswith("#define ROWS")))
    if lines != rows:
        sys.exit("the picker's list style has %d lines, the code puts %d rows on a page" % (lines, rows))
    return lines


def filter_call(ap, stock_ap):
    """The shared key filter is the stock one and makes the expected call."""
    segs, _ = ap_dis.segments(bytes(ap))
    ssegs, _ = ap_dis.segments(stock_ap)
    o, so = ap_dis.find(segs, FILTER_BANK), ap_dis.find(ssegs, FILTER_BANK)
    if bytes(ap[o:o + 0x434]) != stock_ap[so:so + 0x434]:
        sys.exit("MUSIC.AP: the shared key filter is not the stock one")
    at = ap_dis.find(segs, STANDBY_CALL)
    if bytes(ap[at - 2:at]) != b"\x00\x20" or s21.bl_target(ap, segs, STANDBY_CALL) != STOCK_STANDBY:
        sys.exit("MUSIC.AP: the screen-off Previous is not movs r0, #0; bl %#x" % STOCK_STANDBY)
    o = ap_dis.find(segs, STOCK_STANDBY)
    if bytes(ap[o + 0x22:o + 0x26]) != bytes.fromhex("40f21b30"):
        sys.exit("MUSIC.AP: %#x does not send 0x31b" % STOCK_STANDBY)


def old_targets(ap, mcg, ranges):
    """Where the calls and menu rows into the stage 21 code lead now."""
    segs, _ = ap_dis.segments(bytes(ap))
    calls = {s20.PREV_CALL: "previous_key"}
    calls.update({at: fn for at, (_, fn) in s21.RESULT_CALLS.items()})
    for at in calls:
        if not inside(ranges, s21.bl_target(ap, segs, at)):
            sys.exit("MUSIC.AP %#x: does not call the stage 21 code" % at)
    hsz = struct.unpack_from("<H", mcg, 12)[0]
    rows = []
    for li in s20.OPTION_LISTS:
        _, _, off, _, r = s21.rows_of(mcg, hsz, li)
        for row, text, fn in ((s20.ADD_ROW, 5, "add_playing_to_playlist"), (s20.REMOVE_ROW, 34, "remove_playing_from_playlist")):
            if r[row][:2] != [0x7fff, text] or not inside(ranges, r[row][4]):
                sys.exit("MUSIC.MCG: list %d row %d does not lead to the stage 21 code" % (li, row))
            rows.append((off + row * 20 + 8, fn))
    return calls, rows


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage23")
    work = os.path.join(out, "code")
    os.makedirs(work, exist_ok=True)
    print("host test:", s20.host_test(work))
    objs, secs = s20.compile_code(work)
    depths = s20.stack_depth(work)
    if max(depths.values()) > s20.STACK_MAX:
        sys.exit("the new code's deepest call chain needs %d bytes of stack" % max(depths.values()))

    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    stock_ap = xm.Lfi(stock).get("MUSIC.AP")
    base = os.environ.get("X91_STAGE22") or os.path.join(ROOT, "x91_dump", "stage22", "x91_lfi_stage22.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 22 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    lines = picker_lines(lfi)
    ap = bytearray(lfi.get("MUSIC.AP"))
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    ranges = old_code(ap, stock_ap)
    calls, rows = old_targets(ap, mcg, ranges)
    filter_call(ap, stock_ap)

    grown = s21.take_out_code(ap, stock_ap)
    banks = s20.plan(ap, secs)
    symbols = s20.link(work, objs, banks)
    put_code(ap, banks)
    code_sha = hashlib.sha256(b"".join(struct.pack("<I", b["addr"]) + b["code"] for b in sorted(banks, key=lambda b: b["addr"]))).hexdigest()
    if s20.SRC.endswith("stage23") and code_sha != CODE_SHA:
        sys.exit("the frozen stage 23 sources no longer give the stage 23 code (%s)" % code_sha)
    segs, _ = ap_dis.segments(bytes(ap))
    for e in s20.ENTRIES:
        if ap_dis.find(segs, symbols[e]) is None:
            sys.exit("%s is outside the program's banks" % e)
    for at, fn in list(calls.items()) + [(STANDBY_CALL, "standby_previous")]:
        o = ap_dis.find(segs, at)
        ap[o:o + 4] = s20.thumb_bl(at, symbols[fn])
    for off, fn in rows:
        struct.pack_into("<I", mcg, off, symbols[fn] | 1)
    lfi.put("MUSIC.AP", bytes(ap))
    lfi.put("MUSIC.MCG", bytes(mcg))

    print("picker: %d rows on a page, as its list style" % lines)
    print("stage 21 code taken out of %d banks" % len(grown))
    print("new code: %d bytes in %d banks; deepest stack chain %d bytes (%s)"
          % (sum(len(b["code"]) for b in banks), len(banks), max(depths.values()),
             ", ".join("%s %d" % (e, d) for e, d in depths.items())))
    for b in sorted(banks, key=lambda b: b["addr"]):
        print("  bank %#x: length %#x -> %#x (%s)" % (b["addr"], b["len"], b["new_len"],
                                                    ", ".join(s[6:].split(".")[0] for s in b["secs"])))
    print("entries: %s" % ", ".join("%s %#x" % (e, symbols[e] | 1) for e in s20.ENTRIES))
    print("screen-off Previous: %#x now calls standby_previous" % STANDBY_CALL)
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage23.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
