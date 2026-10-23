"""The status bar.

  - Drawn at once, and again right after the screen: the shared "status bar on/off" routine (the same code in every
    program that has a bar) only restarted the bar's 500 ms timer, so the marks came half a second after every full
    repaint, and a list then painted its background over them. patches/headbar_soon.S switches the bar on, draws it
    at once and moves the timer's next firing back to now, so the bar is drawn again as soon as the program waits for
    keys. It goes into all 15 programs with the routine, its calls aimed at each program's own routines, and is
    checked in two steps: patches/music_headbar.S (the bar at once) against the stock routine, then headbar_soon.S
    against that.
  - The "box" at the top left of the playing screen is the storage-card mark, drawn with black as transparent over
    the bar's background picture. The playing screen names its own background (MUSIC.STY 45) as that picture (two
    constants in MUSIC.AP), and that background carries a music note in the corner; the card marks (COMMON.STY 203
    card in, 205 card in use) are line icons whose black is almost-black, so an inserted card covers the note.
  - The main menu's clock sits at x=22 (right of the card mark, where the playing screen has its track counter), in
    the track counter's pixel digits (COMMON.STY 135 to 145; the colon declared 4 wide), with AM/PM after it. The
    keyed draw copies only pixels above 0x7bcf here; the digit colour is checked for that.
  - No blink of the marks: the battery, card and Bluetooth marks (picture boxes 1 to 3, every frame) get a black
    border out to the bar's edges and middle; the bar draws a mark's black pixels in its background, so with the
    middle cleared (lists.py) every pixel of rows 0 to 15 is painted. The bordered marks are stored in the last rows
    of picture 240 (free: the stock demo slideshow's), which is declared that much shorter.
"""
import struct

from . import base
from .base import T, ap_dis, fail, stroke, svg, xd
from .typeface import HAND

# ------------------------------------------------------------------ the playing screen's bar, card marks

NOTE_AT, NOTE_SIZE = (2, 3), (15, 11)            # where the bar draws the card mark (picture box 2 of COMMON.STY)
BACKGROUND = 45                                  # the playing screen's background, picture of MUSIC.STY
PAINTER_SITES = (0x180810ba, 0x180810c6)         # "background picture = the default one" in the playing screen's painter
CARD_IN, CARD_BUSY = 203, 205
ALMOST_BLACK = 0x0020                            # drawn as black, but not treated as transparent

# ------------------------------------------------------------------ the main menu's clock

CLOCK_X = 22
STATUS_KEY = 0x7bcf                              # the status-bar clock draws a pixel only above this value
GLYPH_TOP = 3                                    # the 8-row digits inside their 12-row pictures: screen rows 4 to 11
LETTERS = {"A": [".###.", "#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"],
           "P": ["####.", "#...#", "#...#", "####.", "#....", "#....", "#....", "#...."],
           "M": HAND["M"][2]}

# ------------------------------------------------------------------ the on/off routine

HEADBAR_LEN = 0x74
MUSIC_STRETCH = (0x18c21e74, 0x18c21a20, 0x18a21b80, 0x18a21acc)   # MUSIC.AP: start, draw, timer restart, timer stop
SOURCE_BANK, SOURCE_BASE = 0x18c21a00, 0x18a21a00                # the patches are laid out from the timer bank
HEADBAR_AT = (0x474, 0x4e8)                      # the routine's offsets in SOURCE_BANK
MUSIC_POOL = [0x200163, 0x200162, 0x200668, 0x20015f, 0x200164, 0x200159]   # MUSIC.AP: the routine's variables
TIMER_CODE = 0x24                                # code bytes of the timer routines it calls (their literals follow)
TABLE_LIT = 0x70                                 # headbar_soon.S: its own literal, the timer table pointer
RESTART_CODE = {0x16: "0948", 0x18: "0068", 0x1a: "00eb0415", 0x2e: "6988", 0x30: "0844", 0x32: "a860"}   # the SDK's
PROGRAMS = 15

# ------------------------------------------------------------------ bordered marks

MARKS = {1: ((108, 2), (108, 0), (20, 16)),      # picture box: stock place, new place and size (the battery,
         2: ((2, 3), (0, 0), (17, 16)),          # the card mark, the Bluetooth mark): with the middle, the whole bar
         3: ((98, 2), (98, 0), (10, 16))}
BAR_H = 16
BAR_X = (17, 98)                                 # the bar's middle: right of the card mark, left of the Bluetooth mark
MARK_STORE = 240


def note_picture(work):
    w, h = NOTE_SIZE
    return base.render_565(svg(w, h, [xd.icon("music", -1.2, -2.85, 16.5, T["text"], 2.3)]), w, h, work, "status-note")


def card(color):
    """Storage card, 15 x 11: outline with the cut corner, three contacts."""
    return svg(15, 11, ['<path d="M5.4 1.6H12.4V9.4H2.6V4.4z" %s/>' % stroke(color, 1.2)]
               + ['<path d="M%g 3.6V5.4" %s/>' % (x, stroke(color, 0.9)) for x in (6.5, 8.5, 10.5)])


def playing_bar(b, work):
    sty = b.get("MUSIC.STY")
    data, w, h = base.picture_bytes(sty, BACKGROUND)
    if (w, h) != (128, 160):
        fail("MUSIC.STY: the playing background is not the expected picture")
    back = bytearray(data)
    note, (nw, nh), (nx, ny) = note_picture(work), NOTE_SIZE, NOTE_AT
    for row in range(nh):
        o = ((ny + row) * w + nx) * 2
        back[o:o + nw * 2] = note[row * nw * 2:(row + 1) * nw * 2]
    base.set_picture(sty, BACKGROUND, bytes(back), w, h)
    b.put("MUSIC.STY", sty)

    ap = b.get("MUSIC.AP")
    segs, _ = ap_dis.segments(ap)
    for site in PAINTER_SITES:                                        # movw r2, #0xffff  ->  movw r2, #BACKGROUND
        base.patch_bytes(ap, ap_dis.find(segs, site), bytes.fromhex("4ff6ff72"),
                         struct.pack("<HH", 0xf240, 0x0200 | BACKGROUND), "MUSIC.AP playing-screen painter")
    b.put("MUSIC.AP", ap)

    com = b.get("COMMON.STY")
    box = struct.unpack_from("<16H", com, base.tables_of(com)[1][0] + 2 * 32)
    if box[1:3] != NOTE_AT or box[4:7] != (0x8000 | 204, 0x8000 | CARD_IN, 0x8000 | CARD_BUSY):
        fail("COMMON.STY: the card mark is not where expected")
    pics = base.pictures(com)
    for index, color in ((CARD_IN, T["text2"]), (CARD_BUSY, T["accent"])):
        if pics[index][3:] != NOTE_SIZE:
            fail("COMMON.STY: card mark %d has an unexpected size" % index)
        data = base.render_565(card(color), 15, 11, work, "card-%d" % index)
        px = [v or ALMOST_BLACK for v in struct.unpack("<%dH" % (15 * 11), data)]
        base.set_picture(com, index, struct.pack("<%dH" % len(px), *px), 15, 11)
    b.put("COMMON.STY", com)


def word_picture(word, w, h, color, top):
    px, x, v = [0] * (w * h), 0, base.c565(color)
    for ch in word:
        for j, line in enumerate(LETTERS[ch]):
            for i, c in enumerate(line):
                if c == "#":
                    px[(j + top) * w + x + i] = v
        x += len(LETTERS[ch][0]) + 1
    if x - 1 > w:
        fail("'%s' does not fit into %d pixels" % (word, w))
    return struct.pack("<%dH" % len(px), *px)


def menu_clock(b):
    com = b.get("COMMON.STY")
    if base.c565(T["text2"]) <= STATUS_KEY:
        fail("the status-bar clock would not draw this theme's second text colour")
    for k in range(10):
        base.set_picture(com, 135 + k, base.pixel_glyph(str(k), 6, 12, T["text2"], top=GLYPH_TOP), 6, 12)
    base.resize_picture(com, 145, 4, 12)
    base.set_picture(com, 145, base.dots(4, 12, [(1, GLYPH_TOP + 2), (1, GLYPH_TOP + 5)], T["text2"]), 4, 12)
    for index, word in ((411, "AM"), (413, "PM")):
        base.set_picture(com, index, word_picture(word, 17, 10, T["text2"], 1), 17, 10)
    box = struct.unpack_from("<16H", com, base.tables_of(com)[1][0] + 4 * 32)
    if box[1:3] != (77, 2) or box[4:7] != (0x8000 | 412, 0x8000 | 411, 0x8000 | 413):
        fail("COMMON.STY: the AM/PM mark is not where expected")
    base.set_fields(com, 1, 32, 4, w1=CLOCK_X + 4 * 6 + 4 + 3, w2=3)   # behind "hh:mm", its letters on the digits' rows
    b.put("COMMON.STY", com)

    ap = b.get("MAINMENU.AP")
    segs, _ = ap_dis.segments(ap)
    rest = "adf802000121adf8041048f2870a"                              # ..., y = 1, digits from picture 135 of COMMON.STY
    base.patch_bytes(ap, ap_dis.find(segs, 0x18c21c0e), bytes.fromhex("2d20" + rest),
                     bytes([CLOCK_X, 0x20]) + bytes.fromhex(rest), "MAINMENU.AP status-bar clock")
    b.put("MAINMENU.AP", ap)


def on_off_routine(b, work):
    """headbar_soon.S in every program with the stock on/off routine, found by its bytes with the calls masked."""
    stock_music = b.stock_file("MUSIC.AP")
    segs, _ = ap_dis.segments(stock_music)
    start, draw, restart, stop = MUSIC_STRETCH
    o = ap_dis.find(segs, start)
    routine = base.masked(stock_music[o:o + HEADBAR_LEN])
    o = ap_dis.find(segs, draw)
    drawer = base.masked(stock_music[o:o + 96])
    stock_calls = [t for _, t in base.bls(stock_music, segs, start, HEADBAR_LEN)]
    if sorted(stock_calls) != sorted([restart, stop]):
        fail("MUSIC.AP: the stock status-bar routine does not call the timer as expected")
    if [base.word_at(stock_music, segs, SOURCE_BANK + HEADBAR_AT[1] + 4 * k) for k in range(6)] != MUSIC_POOL:
        fail("MUSIC.AP: the status bar's variables are not where expected")
    shift = SOURCE_BANK - SOURCE_BASE
    lo, hi = shift + HEADBAR_AT[0], shift + HEADBAR_AT[1]
    at_once = base.assemble("music_headbar", work)[lo:hi]
    soon = base.assemble("headbar_soon", work)[lo:hi]
    for code, what in ((at_once, "music_headbar.S"), (soon, "headbar_soon.S")):
        if [base.bl_at(code, k, start + k) for k in base.bl_offsets(code)] != [restart, draw, stop]:
            fail("%s does not call restart, draw, stop" % what)

    def aimed(code, p_start, aim):
        out = bytearray(code)
        for k in base.bl_offsets(code):
            out[k:k + 4] = base.thumb_bl(p_start + k, aim[base.bl_at(code, k, start + k)])
        return out

    done = []
    for name in b.programs():
        ap = b.get(name)
        try:
            psegs, _ = ap_dis.segments(bytes(ap))
        except Exception:
            continue
        here, drawers = base.find_all(ap, psegs, routine), base.find_all(ap, psegs, drawer)
        if not here:
            continue
        if len(here) != 1 or len(drawers) != 1:
            fail("%s: the status-bar routines are not found once each (%d, %d)" % (name, len(here), len(drawers)))
        p_start, p_draw = here[0], drawers[0]
        calls = [t for _, t in base.bls(ap, psegs, p_start, HEADBAR_LEN)]
        for mine, theirs in zip(calls, stock_calls):                  # the timer routines are the music program's
            a, c = ap_dis.find(psegs, mine), ap_dis.find(segs, theirs)
            if bytes(ap[a:a + TIMER_CODE]) != stock_music[c:c + TIMER_CODE]:
                fail("%s: the status bar's timer routine at %#x is not the music program's" % (name, mine))
        aim = {restart: calls[stock_calls.index(restart)], stop: calls[stock_calls.index(stop)], draw: p_draw}
        r = ap_dis.find(psegs, aim[restart])
        if any(bytes(ap[r + k:r + k + len(v) // 2]) != bytes.fromhex(v) for k, v in RESTART_CODE.items()):
            fail("%s: the timer restart at %#x is not the SDK's" % (name, aim[restart]))
        table = struct.unpack_from("<I", ap, r + 0x3c)[0]
        if not 0x200000 <= table < 0x200800:
            fail("%s: the timer table pointer %#x is not in the program's RAM" % (name, table))
        _, bank, boff, blen = [sg for sg in psegs if sg[0] == "bank" and sg[1] <= p_start < sg[1] + sg[3]][0]
        k0 = p_start - bank
        old = bytes(ap[boff:boff + blen])
        step1 = old[:k0] + bytes(aimed(at_once, p_start, aim)) + old[k0 + HEADBAR_LEN:]
        code = aimed(soon, p_start, aim)
        struct.pack_into("<I", code, TABLE_LIT, table)
        step2 = old[:k0] + bytes(code) + old[k0 + HEADBAR_LEN:]
        args = ["%x" % v for v in (p_start, p_draw, aim[restart], aim[stop])]
        tag = "headbar_" + name[:-3]
        base.check("check_headbar_patch.py", old, step1, bank, work, tag + "_at_once", args)
        base.check("check_headbar_soon.py", step1, step2, bank, work, tag + "_soon", args)
        ap[boff + k0:boff + k0 + HEADBAR_LEN] = code
        b.put(name, ap)
        done.append(name[:-3])
    if len(done) != PROGRAMS:
        fail("the status-bar routine was found in %d programs, not %d: %s" % (len(done), PROGRAMS, ", ".join(done)))
    return done


def bordered_marks(b):
    """The three marks (every frame) on a black canvas out to the bar's edges and middle; stored in picture 240."""
    com = b.get("COMMON.STY")
    po = struct.unpack_from("<I", com, 0x10)[0]
    entry = lambda i: struct.unpack_from("<IIHHH", com, po + i * 16)
    boxes = base.tables_of(com)[1][0]
    off, ln, typ, w, h = entry(MARK_STORE)
    if (ln, w, h) != (128 * 160 * 2, 128, 160):
        fail("COMMON.STY: picture %d is not the free full-screen one" % MARK_STORE)
    pieces = []
    for k, ((x0, y0), (x1, y1), (bw, bh)) in sorted(MARKS.items()):
        rec = struct.unpack_from("<16H", com, boxes + k * 32)
        n = rec[3] >> 8
        frames = rec[4:4 + n]
        if rec[1:3] != (x0, y0) or rec[3] & 0xff != 1 or any(f & 0x8000 == 0 or f == 0xffff for f in frames):
            fail("COMMON.STY: picture box %d is not the stock status bar mark" % k)
        dx, dy = x0 - x1, y0 - y1
        for f in frames:
            p_off, p_ln, p_typ, pw, ph = entry(f & 0x7fff)
            if p_ln != pw * ph * 2 or dx + pw > bw or dy + ph > bh:
                fail("COMMON.STY: mark picture %d (%dx%d) does not fit %dx%d" % (f & 0x7fff, pw, ph, bw, bh))
            canvas = bytearray(bw * bh * 2)
            for row in range(ph):
                at = ((dy + row) * bw + dx) * 2
                canvas[at:at + pw * 2] = com[p_off + row * pw * 2:p_off + (row + 1) * pw * 2]
            pieces.append((f & 0x7fff, bytes(canvas), p_typ, bw, bh))
        struct.pack_into("<2H", com, boxes + k * 32 + 2, x1, y1)
    cells = [(x, y) for (x1, y1), (bw, bh) in (v[1:] for v in MARKS.values()) for x in range(x1, x1 + bw) for y in range(y1, y1 + bh)]
    cells += [(x, y) for x in range(*BAR_X) for y in range(BAR_H)]
    if sorted(cells) != [(x, y) for x in range(128) for y in range(BAR_H)]:
        fail("the marks and the bar's middle do not cover rows 0 to %d exactly once" % (BAR_H - 1))
    rows = -(-sum(len(c) for _, c, *_ in pieces) // (w * 2))
    base.resize_picture(com, MARK_STORE, w, h - rows)
    at = off + (h - rows) * w * 2
    for index, canvas, p_typ, bw, bh in pieces:
        com[at:at + len(canvas)] = canvas
        struct.pack_into("<IIHHH", com, po + index * 16, at, len(canvas), p_typ, bw, bh)
        at += len(canvas)
    b.put("COMMON.STY", com)
    return len(pieces)


def build(b):
    work = b.folder("statusbar")
    playing_bar(b, work)
    menu_clock(b)
    done = on_off_routine(b, work)
    marks = bordered_marks(b)
    b.note("status bar: drawn at once and right after the screen in %d programs (%s); the playing screen's own "
           "background with a note; card marks; main menu clock at x=%d; %d mark pictures with a black border",
           len(done), ", ".join(done), CLOCK_X, marks)
