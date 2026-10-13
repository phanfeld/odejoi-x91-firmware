#!/usr/bin/env python3
"""Stage 15 of the Graphite design, built on the stage 14 image.

  1. Main menu: the time sits at the top left in the lettering of the track counter.
     The shared status-bar code draws the time only while the main menu is the running program (program 19),
     digit by digit through the display driver's keyed draw: pictures 135 to 144 of COMMON.STY, colon 145,
     starting at a position that is fixed in the code (x=45, y=1). In MAINMENU.AP that x becomes 22: the
     place right of the card mark, where the playing screen has its track counter. The digits are redrawn as
     the pixel digits of the track counter, the colon is declared 4 wide, and the AM/PM mark (picture box 4,
     pictures 411 and 413) follows the time and gets the same lettering.
     The keyed draw copies only pixels whose value is above 0x7bcf here; the digit colour is checked for that.
  2. Screensaver clock: the colon has the accent colour in every theme.
     The clock routine sets the key 0xb5b6, which only bright pixels pass; of the accents only amber's did,
     so stage 8 gave the other themes a white colon. The key becomes 0 (every pixel that is not black is
     drawn) in every program that has the routine, except CONFIG.AP and FWUPDATE.AP, which are never
     modified. All clock pictures are black or bright already, so nothing else changes on that screen.

usage: build_stage15.py [OUT_DIR]      (default: ../x91_dump/stage15)
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
import x91_design as xd  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage2 as s2  # noqa: E402
import build_stage5 as s5  # noqa: E402
import build_stage6 as s6  # noqa: E402
import build_stage7 as s7  # noqa: E402
import build_stage8 as s8  # noqa: E402
import build_stage11 as s11  # noqa: E402
import build_stage14 as s14  # noqa: E402

T = s1.T
CLOCK_X = 22                                     # as the track counter on the playing screen
STATUS_KEY = 0x7bcf                              # the status-bar clock draws a pixel only above this value
GLYPH_TOP = 3                                    # the 8-row digits inside their 12-row pictures: screen rows 4 to 11
LETTERS = {"A": [".###.", "#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
           "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#....", "#...."],
           "M": s2.HAND["M"][2]}
OLD_KEY, NEW_KEY = 0xb5b6, 0
CLOCK_BANK = 0x18ce1a00
KEY_OFFSETS = (0x8a, 0xa6)                       # in the stock routine, and in the one stage 7 put in
NEVER = ("CONFIG.AP", "FWUPDATE.AP")             # recovery depends on these


def movw(reg, value):
    return struct.pack("<HH", 0xf240 | (value >> 11 & 1) << 10 | value >> 12, (value >> 8 & 7) << 12 | reg << 8 | value & 0xff)


def word_picture(word, w, h, color, top):
    px, x, v = [0] * (w * h), 0, s11.s10_colour(color)
    for ch in word:
        for j, line in enumerate(LETTERS[ch]):
            for i, c in enumerate(line):
                if c == "#":
                    px[(j + top) * w + x + i] = v
        x += len(LETTERS[ch][0]) + 1
    if x - 1 > w:
        sys.exit("'%s' does not fit into %d pixels" % (word, w))
    return struct.pack("<%dH" % len(px), *px)


def status_clock(lfi):
    com = bytearray(lfi.get("COMMON.STY"))
    if s11.s10_colour(T["text2"]) <= STATUS_KEY:
        sys.exit("the status-bar clock would not draw this theme's digit colour")
    for k in range(10):
        s1.set_picture(com, 135 + k, s11.pixel_glyph(str(k), 6, 12, T["text2"], top=GLYPH_TOP), 6, 12)
    s7.resize_picture(com, 145, 4, 12)
    s1.set_picture(com, 145, s11.dots(4, 12, [(1, GLYPH_TOP + 2), (1, GLYPH_TOP + 5)], T["text2"]), 4, 12)
    for index, word in ((411, "AM"), (413, "PM")):
        s1.set_picture(com, index, word_picture(word, 17, 10, T["text2"], 1), 17, 10)
    box = struct.unpack_from("<16H", com, s11.tables_of(com)[1][0] + 4 * 32)
    if box[1:3] != (77, 2) or box[4:7] != (0x8000 | 412, 0x8000 | 411, 0x8000 | 413):
        sys.exit("COMMON.STY: the AM/PM mark is not where expected")
    s11.set_fields(com, 1, 32, 4, w1=CLOCK_X + 4 * 6 + 4 + 3, w2=3)   # behind "hh:mm", its letters on the digits' rows
    lfi.put("COMMON.STY", bytes(com))

    ap = bytearray(lfi.get("MAINMENU.AP"))
    segs, _ = ap_dis.segments(ap)
    rest = "adf802000121adf8041048f2870a"                              # ..., y = 1, digits from picture 135 of COMMON.STY
    s5.patch_bytes(ap, ap_dis.find(segs, 0x18c21c0e), bytes.fromhex("2d20" + rest),
                   bytes([CLOCK_X, 0x20]) + bytes.fromhex(rest), "MAINMENU.AP status-bar clock")
    lfi.put("MAINMENU.AP", bytes(ap))


def screensaver_colon(lfi, work):
    com = bytearray(lfi.get("COMMON.STY"))
    cov = s8.coverage(s8.white_svg(13, 20, [xd.rect(5, 6, 3, 3, 0.4, "#ffffff"), xd.rect(5, 13, 3, 3, 0.4, "#ffffff")]),
                      13, 20, work, "time-colon")
    s1.set_picture(com, 170, s8.solid(cov, s6.rgb(T["accent"])), 13, 20)
    po = struct.unpack_from("<I", com, 0x10)[0]
    for index in range(147, 171):                                     # with the new key: black or drawn, nothing in between
        off, ln = struct.unpack_from("<II", com, po + index * 16)
        if any(0 < v <= NEW_KEY for v in struct.unpack_from("<%dH" % (ln // 2), com, off)):
            sys.exit("picture %d has pixels the firmware would drop" % index)
    lfi.put("COMMON.STY", bytes(com))

    done = []
    for name in sorted(lfi.entries):
        if not name.endswith(".AP") or name in NEVER:
            continue
        ap = bytearray(lfi.get(name))
        segs, _ = ap_dis.segments(ap)
        bank = [(off, ln) for kind, addr, off, ln in segs if addr == CLOCK_BANK]
        if not bank:
            continue
        off, ln = bank[0]
        code = bytes(ap[off:off + ln])
        at = [i for i in range(0, ln - 3, 2) if code[i:i + 4] == movw(0, OLD_KEY)]
        if not at:
            continue
        if len(at) != 1 or at[0] not in KEY_OFFSETS or ap.count(movw(0, OLD_KEY)) != 1:
            sys.exit("%s: the screensaver clock's key is not where expected" % name)
        ap[off + at[0]:off + at[0] + 4] = movw(0, NEW_KEY)
        lfi.put(name, bytes(ap))
        done.append(name[:-3])
    return done


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage15")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE14") or os.path.join(ROOT, "x91_dump", "stage14", "x91_lfi_stage14.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 14 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    status_clock(lfi)
    print("main menu clock: x=%d, digits, colon and AM/PM in the track counter's lettering" % CLOCK_X)
    programs = screensaver_colon(lfi, work)
    print("screensaver clock: colon in the accent colour; key %#x -> %#x in %d programs: %s"
          % (OLD_KEY, NEW_KEY, len(programs), ", ".join(programs)))
    copies = []
    s14.refresh_copies(lfi, copies)
    print("sideways copies brought in line:", "; ".join(copies) or "none needed")
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage15.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
