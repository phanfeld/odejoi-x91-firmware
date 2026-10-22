#!/usr/bin/env python3
"""Stage 22 of the Graphite design, built on the stage 21 image: the minor items of the to-do list.

  1. The "Searching..." screen of the library builder (PLAYLIST.STY; to-do 11) in the theme: the background and
     the two text strips in the theme's background colour, the text in its text colour, the spinner like the
     Bluetooth search of stage 6 (an accent arc going round a ring, a music note inside, eight frames), the
     progress bar's track in the line colour and its filled part in the accent.
  2. The status bar appears at once in every program that has one (to-dos 13 and 14; stage 14 did it for the
     music program only): the shared "status bar on" routine is the same code everywhere, at one of four
     places, and its timer and drawing routines sit elsewhere in each program. Stage 14's routine
     (patches/music_headbar.S) goes into each, its three calls aimed at that program's routines, and each copy
     passes stage 14's check with that program's addresses. Not CONFIG.AP and FWUPDATE.AP (recovery).
  3. The track counter on the playing screen shows as many digits as the numbers have ("12/186", not
     "0012/0186"): the digit counts of its number box (MUSIC.STY, byte 24) are 0, as in the reader's records
     (to-do 13).
  4. The storage-card marks of the status bar (COMMON.STY 203: card in, 205: card in use) as line icons in the
     status bar's style; black stays almost-black, as stage 14 needs it to cover the playing screen's note.
  5. Screensaver clock: the date digits, their dash and AM/PM in the theme's second text colour, dimmer than
     the time (to-do 17); stage 8 had to keep them bright for the colour key that stage 15 set to 0.

usage: build_stage22.py [OUT_DIR]      (default: ../x91_dump/stage22)
"""
import hashlib
import os
import struct
import subprocess
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
import build_stage4 as s4  # noqa: E402
import build_stage6 as s6  # noqa: E402
import build_stage8 as s8  # noqa: E402
import build_stage11 as s11  # noqa: E402
import build_stage14 as s14  # noqa: E402
from build_stage21 import bl_target  # noqa: E402
from build_stage20 import thumb_bl  # noqa: E402

T = s1.T
SPINNER, SPINNER_SIZE = range(1, 9), 38           # PLAYLIST.STY pictures
BACKGROUND, TEXT_STRIPS, TRACKS, FILL = 0, (11, 12), (10, 13), 9
CARD_IN, CARD_BUSY, CARD_SIZE = 203, 205, (15, 11)
ALMOST_BLACK = s14.ALMOST_BLACK
COUNTER_DIGITS = (0x0244, 0x0200)               # MUSIC.STY number box 0, word 12: digits 4 and 4 -> as needed
HEADBAR_LEN = 0x74
TIMER_CODE = 0x24                               # code bytes of the timer routines it calls (their literals follow)
MUSIC_STRETCH = (0x18c21e74, 0x18c21a20, 0x18a21b80, 0x18a21acc)   # start, draw, timer restart, timer stop
SKIP = ("CONFIG.AP", "FWUPDATE.AP", "MUSIC.AP")  # recovery; MUSIC.AP has it since stage 14


def c565(color):
    r, g, b = s6.rgb(color) if isinstance(color, str) else color
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


def solid(w, h, color):
    return struct.pack("<%dH" % (w * h), *[c565(color)] * (w * h))


# ------------------------------------------------------------------ 1. "Searching..."

def spinner(frame):
    a = frame * 45
    c = SPINNER_SIZE / 2
    return s1.svg(SPINNER_SIZE, SPINNER_SIZE, ['<circle cx="%g" cy="%g" r="15.5" %s/>' % (c, c, s4.stroke(T["line"], 2.4)),
                                               s6.arc(c, c, 15.5, a, a + 100, T["accent"], 2.4),
                                               xd.icon("music", 10, 10, 18, T["text"], 2.0)])


def searching(lfi, work):
    sty = bytearray(lfi.get("PLAYLIST.STY"))
    pics = s14.pictures(sty)
    sizes = {k: pics[k][3:] for k in [BACKGROUND, FILL] + list(SPINNER) + list(TEXT_STRIPS) + list(TRACKS)}
    want = {BACKGROUND: (128, 160), FILL: (1, 3)}
    want.update({k: (38, 38) for k in SPINNER})
    want.update({k: (110, 16) for k in TEXT_STRIPS})
    want.update({k: (118, 3) for k in TRACKS})
    if sizes != want:
        sys.exit("PLAYLIST.STY: the pictures are not the expected ones: %s" % sizes)
    s1.set_picture(sty, BACKGROUND, solid(128, 160, T["bg"]), 128, 160)
    for k in TEXT_STRIPS:
        s1.set_picture(sty, k, solid(110, 16, T["bg"]), 110, 16)
    for k in TRACKS:
        s1.set_picture(sty, k, solid(118, 3, T["line"]), 118, 3)
    s1.set_picture(sty, FILL, solid(1, 3, T["accent"]), 1, 3)
    for n, k in enumerate(SPINNER):
        s1.set_picture(sty, k, s1.render_565(spinner(n), SPINNER_SIZE, SPINNER_SIZE, work, "searching-%d" % n),
                       SPINNER_SIZE, SPINNER_SIZE)
    t = s11.tables_of(sty)
    if t[2][1] != 2:
        sys.exit("PLAYLIST.STY: not two text boxes")
    for k in range(2):
        s11.set_fields(sty, 2, 20, k, w8=c565(T["text"]))
    lfi.put("PLAYLIST.STY", bytes(sty))


# ------------------------------------------------------------------ 2. the status bar at once

def masked(code):
    """Bytes of a stretch of code with its bl instructions masked out."""
    mask = bytearray(b"\xff" * len(code))
    i = 0
    while i < len(code) - 2:
        hi, lo = struct.unpack_from("<HH", code, i)
        if hi >> 11 == 0x1e and lo >> 14 == 3:
            mask[i:i + 4] = bytes(4)
            i += 4
        else:
            i += 2
    return code, mask


def find_all(data, segs, pattern):
    code, mask = pattern
    hits = []
    for kind, addr, off, n in segs:
        if kind != "bank":
            continue
        for at in range(off, off + n - len(code), 2):
            if all(not mask[k] or data[at + k] == code[k] for k in range(len(code))):
                hits.append(addr + at - off)
    return hits


def bls(data, segs, start, length):
    """The bl instructions of a stretch: (address, target)."""
    out, o = [], ap_dis.find(segs, start)
    i = 0
    while i < length - 2:
        hi, lo = struct.unpack_from("<HH", data, o + i)
        if hi >> 11 == 0x1e and lo >> 14 == 3:
            out.append((start + i, bl_target(data, segs, start + i)))
            i += 4
        else:
            i += 2
    return out


def headbars(lfi, stock_music, work):
    segs, _ = ap_dis.segments(stock_music)
    start, draw, restart, stop = MUSIC_STRETCH
    o = ap_dis.find(segs, start)
    routine = masked(stock_music[o:o + HEADBAR_LEN])
    o = ap_dis.find(segs, draw)
    drawer = masked(stock_music[o:o + 96])
    stock_calls = [t for _, t in bls(stock_music, segs, start, HEADBAR_LEN)]
    if sorted(stock_calls) != sorted([restart, stop]):
        sys.exit("MUSIC.AP: the stock status-bar routine does not call the timer as expected")
    shift = s14.HEADBAR["bank"] - s14.HEADBAR_SOURCE_BASE
    built = s14.assemble("music_headbar", work)[shift + s14.HEADBAR["lo"]:shift + s14.HEADBAR["hi"]]
    music_new = bytearray(stock_music)
    music_new[ap_dis.find(segs, start):ap_dis.find(segs, start) + HEADBAR_LEN] = built
    new_calls = bls(bytes(music_new), segs, start, HEADBAR_LEN)
    if sorted(t for _, t in new_calls) != sorted([restart, stop, draw]):
        sys.exit("the stage 14 routine does not make the expected calls")
    done = []
    for name in sorted(lfi.entries):
        if not name.endswith(".AP") or name in SKIP:
            continue
        ap = bytearray(lfi.get(name))
        try:
            psegs, _ = ap_dis.segments(bytes(ap))
        except Exception:
            continue
        here, drawers = find_all(ap, psegs, routine), find_all(ap, psegs, drawer)
        if not here:
            continue
        if len(here) != 1 or len(drawers) != 1:
            sys.exit("%s: the status-bar routines are not found once each (%d, %d)" % (name, len(here), len(drawers)))
        p_start, p_draw = here[0], drawers[0]
        calls = [t for _, t in bls(bytes(ap), psegs, p_start, HEADBAR_LEN)]
        for mine, theirs in zip(calls, stock_calls):                  # the timer routines, without their literals
            a, b = ap_dis.find(psegs, mine), ap_dis.find(segs, theirs)
            if masked(bytes(ap[a:a + TIMER_CODE]))[0] != masked(stock_music[b:b + TIMER_CODE])[0]:
                sys.exit("%s: the status bar's timer routine at %#x is not the music program's" % (name, mine))
        aim = {restart: calls[stock_calls.index(restart)], stop: calls[stock_calls.index(stop)], draw: p_draw}
        code = bytearray(built)
        for at, target in new_calls:
            k = at - start
            code[k:k + 4] = thumb_bl(p_start + k, aim[target])
        base = [s for s in psegs if s[0] == "bank" and s[1] <= p_start < s[1] + s[3]][0]
        bank, boff, blen = base[1], base[2], base[3]
        old = bytes(ap[boff:boff + blen])
        lo = p_start - bank
        new = old[:lo] + bytes(code) + old[lo + HEADBAR_LEN:]
        args = ["%x" % v for v in (p_start, p_draw, aim[restart], aim[stop])]
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "check_headbar_patch.py"),
                            s14.disassemble(old, bank, os.path.join(work, name + "_headbar_stock.dis")),
                            s14.disassemble(new, bank, os.path.join(work, name + "_headbar_new.dis"))] + args,
                           capture_output=True, text=True)
        if r.returncode:
            sys.exit("%s: the status-bar patch failed its check:\n%s%s" % (name, r.stdout[-600:], r.stderr[-300:]))
        ap[boff + lo:boff + lo + HEADBAR_LEN] = code
        lfi.put(name, bytes(ap))
        done.append("%s %#x" % (name[:-3], p_start))
    return done


# ------------------------------------------------------------------ 3. to 5.

def counter(lfi):
    sty = bytearray(lfi.get("MUSIC.STY"))
    off = s11.tables_of(sty)[3][0]
    if struct.unpack_from("<H", sty, off + 24)[0] != COUNTER_DIGITS[0]:
        sys.exit("MUSIC.STY: the track counter's digit counts are not the stock ones")
    s11.set_fields(sty, 3, 28, 0, w12=COUNTER_DIGITS[1])
    lfi.put("MUSIC.STY", bytes(sty))


def card(color):
    """Storage card, 15 x 11: outline with the cut corner, three contacts."""
    return s1.svg(15, 11, ['<path d="M5.4 1.6H12.4V9.4H2.6V4.4z" %s/>' % s4.stroke(color, 1.2)]
                  + ['<path d="M%g 3.6V5.4" %s/>' % (x, s4.stroke(color, 0.9)) for x in (6.5, 8.5, 10.5)])


def common(lfi, work):
    com = bytearray(lfi.get("COMMON.STY"))
    pics = s14.pictures(com)
    for index, color in ((CARD_IN, T["text2"]), (CARD_BUSY, T["accent"])):
        if pics[index][3:] != CARD_SIZE:
            sys.exit("COMMON.STY: card mark %d has an unexpected size" % index)
        data = s1.render_565(card(color), 15, 11, work, "card-%d" % index)
        px = [v or ALMOST_BLACK for v in struct.unpack("<%dH" % (15 * 11), data)]
        s1.set_picture(com, index, struct.pack("<%dH" % len(px), *px), 15, 11)
    dim = s6.rgb(T["text2"])
    for k in range(11):                           # date digits 147 to 156, dash 157
        px = [0] * (9 * 11)
        if k == 10:
            for x in range(2, 7):
                px[6 * 9 + x] = s8.v565(dim)
        else:
            _, _, pattern = s2.HAND[str(k)]
            for j, line in enumerate(pattern):
                for i, c in enumerate(line):
                    if c == "#":
                        px[(j + 2) * 9 + i + 2] = s8.v565(dim)
        s1.set_picture(com, 147 + k, struct.pack("<%dH" % len(px), *px), 9, 11)
    for index, word in ((168, "AM"), (169, "PM")):
        cov = s8.coverage(s8.white_svg(28, 20, [s8.white_text(14, 17, word, 11.5, 700)]), 28, 20, work, "clock-%s" % word.lower())
        s1.set_picture(com, index, s8.solid(cov, dim, full=0.5, part=0.5), 28, 20)
    lfi.put("COMMON.STY", bytes(com))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage22")
    work = os.path.join(out, "work")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    stock_music = xm.Lfi(stock).get("MUSIC.AP")
    base = os.environ.get("X91_STAGE21") or os.path.join(ROOT, "x91_dump", "stage21", "x91_lfi_stage21.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 21 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}

    searching(lfi, work)
    print("Searching screen: theme background, spinner (%d frames), bar, text colour" % len(SPINNER))
    done = headbars(lfi, stock_music, work)
    print("status bar at once in %d more programs: %s" % (len(done), ", ".join(done)))
    counter(lfi)
    print("track counter: as many digits as needed")
    common(lfi, work)
    print("card marks 203 and 205; screensaver date and AM/PM in the second text colour")
    copies = []
    s14.refresh_copies(lfi, copies)
    print("sideways copies brought in line:", "; ".join(copies) or "none needed")

    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage22.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
