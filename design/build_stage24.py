#!/usr/bin/env python3
"""Stage 24 of the Graphite design, built on the stage 23 image: the top line of the lists (to-do 18).
Rebuilt after the first build was on the player (owner, 2026-10-22: menu names wrong or cut off, empty top lines in
the file lists, no counter in an album folder of the folder view).

  1. Menus no longer show the item counter ("position/total"): list styles 0x6001, 0x6002, 0x6004, 0x6006 and 0x6007
     of COMMON.STY (attribute bit 3 of each list-box record). The main menus (0x6002) show the menu's name instead, at
     the top left of the status bar where the main menu has its clock (x=22), in the interface font and the second
     text colour, up to the Bluetooth and battery marks (x=98, 76 pixels). The shared menu code fills that title (the
     menu list's title text); the style did not show it (attribute bit 1).
  2. Menu names that were wrong or too long get short English texts (owner's choice: in the title and in the row that
     leads there): Settings, Display, Sound, Speaker, Language, Format, Date & time ... (RENAMES). The Music menu's six
     lists had "All songs", "Local folder", "Now playing" or "Resume" as title; they get "Music" (MUSIC.STY text 48,
     the Audible "Authorization Info", which this player never shows). The language list gets "Language".
  3. The file lists (0x6000) show nothing in the status bar; two copies of their look: 0x6003 (stock MENULIST_HEAD,
     which no program uses) with the counter in the track counter's place and digits (the driver's picture form of
     the counter: the main menu clock's digits, COMMON.STY 135 to 144, a slash in picture 125, an unused stock icon
     declared 4 x 12, over the black picture 250, at (22, 1)), and 0x6005 (stock MENULIST_TITLE2, also unused) with the
     list's title in the status bar like the menus.
  4. design/playlist/liststyle.c picks the style for every draw of the shared list control (gui_directory at
     0x18661200 in MUSIC.AP, BROWSER.AP, EBOOK.AP, VIDEO.AP and PICTURE.AP; its list box call at 0x18661380): the
     counter inside one album or playlist (music lists and folder view only), else the level's name (the browser's
     name of the level; at the top, the list's own name). It is compiled once per program (PROGRAMS) and sits at the
     free end of the control's own bank: new-code banks load at 0x101000, over the list data the control keeps at
     0x10116c. A later stage that takes the new code out of MUSIC.AP's banks (build_stage21.take_out_code) stops at
     this bank (only 0x1000-group banks may be longer than stock there): it has to set the bank back to its stock
     length 0x314 first and call place_list_box again afterwards.
  5. The status bar in menus and lists: switched on, it was drawn at once (stage 14) and then painted over by the
     list's full-screen background, so it came back only with its 500 ms timer (owner, 2026-10-22, about a second in
     every sub-menu). The routine that switches it on (patches/headbar_soon.S, in all 15 programs that have the stage
     14 routine) now also moves the timer's next firing back to now: the bar is drawn again as soon as the program
     waits for keys, after the screen is drawn. Checked per program by patches/check_headbar_soon.py.
  6. No blink of the status bar's marks: the list styles painted their full-screen black background over the bar, so
     its marks went out until the bar was drawn again (owner, 2026-10-22: still noticeable after 5.). The styles drawn
     with the bar on (CLEARED: 0x6000, 0x6002 to 0x6005) get a background from row 16 down (picture 126, a view into
     picture 185); the code that draws them first clears the bar's middle (x 17 to 97, picture 127): list_box
     (liststyle.c), menu_box (patches/menu_box.S, at the end of every bank with another list box call, through that
     bank's own veneer, checked by patches/check_menu_box.py) and the playlist picker (playlist.c). The three marks
     (battery, card, Bluetooth; every frame) get a black border out to the bar's edges and middle, which the bar draws
     in its background, so the marks and the middle cover rows 0 to 15 and nothing of the screen before stays (the
     screensaver, the reader's page). The other styles (0x6001 lists, 0x6006 option menus) keep the whole-screen
     background: they are drawn without the bar. MUSIC.AP's playlist code is placed anew (as stage 23 did) to leave
     the ends of the menu banks free for menu_box. CONFIG.AP is never modified: its menus may show what the screen
     before had in the bar's middle.
  Second rebuild (owner, 2026-10-22): 5., and the eBook list's name "eBook" as on the main menu (was "E-book").
  Third rebuild (owner, 2026-10-22, "remove the blink fully"): 6.

usage: build_stage24.py [OUT_DIR]      (default: ../x91_dump/stage24)
"""
import hashlib
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage7 as s7  # noqa: E402
import build_stage11 as s11  # noqa: E402
import build_stage14 as s14  # noqa: E402
import build_stage22 as s22  # noqa: E402
import build_stage23 as s23  # noqa: E402   (sets up build_stage20 for the stage 23 code; only its helpers are used)
from build_stage18 import CFLAGS, BANK_TABLES, BANK_MAX, run, put_code  # noqa: E402

s20 = s23.s20
s21 = s23.s21
T = s1.T
LIVE = os.path.join(HERE, "playlist", "stage24")  # the sources as this stage shipped them (stage 25 changed the live ones)
# what the frozen sources gave when stage 24 (third build) was made: the playlist code's banks (address and bytes, in
# bank order) and the list_box of each program (name, address and bytes)
CODE_SHA = "de939e1462245f3955186682d316800f4e97b02286cfaf0fd9b0846a175c759b"
LIST_BOX_SHA = "c912c515948674cd40c94b6898fcd0fb5875e33225bfc8e7101adcde70b5e902"
ENGLISH = 2

LISTS = 6                                        # COMMON.STY table of the list-box records (28 bytes each)
DIRLIST, MENULIST, HEAD, TITLE2 = 0, 2, 3, 5     # records = style ids 0x6000 ...
NO_COUNTER = (0, 1, 2, 4, 6, 7)                  # every stock style that had it; 8 (landscape options) never had one
SUBS = (12, 16, 264, 28)                         # title, scroll bar, rows, counter (sizes in records 0 and 3)
ATTR = 24                                        # record byte: 1 shown, 2 title, 4 scroll bar, 8 counter
TITLE_ON, COUNTER_ON = 2, 8
STOCK_ATTR = {0: 0x0d, 1: 0x0d, 2: 0x0d, 3: 0x0d, 4: 0x0f, 5: 0x0f, 6: 0x0d, 7: 0x0f, 8: 0x05}
STOCK_COUNTER = (0xffff, 0xffff, 0x0a0a, 0, 0, 0, 2, 0x80, 0x10, 0x1e, 0, 0x80fa, 0xffff, 0x7a)
STOCK_TITLE = (0x14, 0x0a, 0x64, 0x19, 0xffff, 6)  # records 0 and 2: a title box their attributes never showed

STATUS_X = 22                                    # right of the card mark: the clock, the track counter
MARKS_X = 98                                     # Bluetooth and battery
TITLE_W = MARKS_X - STATUS_X
TITLE_FONT = 4                                   # title attribute: bits 2-3 = 1 normal font, bits 0-1 = 0 left
DIGITS, SLASH, COUNTER_BG = 135, 125, 250        # COMMON.STY pictures
DIGIT_W, SLASH_W, CELL_H, GLYPH_TOP = 6, 4, 12, 3
COUNTER_Y = 1                                    # with the glyphs on rows 3 to 10 of a cell: screen rows 4 to 11
PICTURE_FORM = 1                                 # counter attribute bits: 0 pictures, 1-2 alignment (0 left)
BLACK, BAR_BG = 185, 249                         # the shared black full-screen picture; the status bar's default background
LIST_BG, BAR_CLEAR = 126, 127                    # unused stock icons, declared as views into picture 185's black pixels
BAR_H = 16                                       # the list background from here down: the bar's marks end at row 14
BAR_X = (17, 98)                                 # the bar's middle: right of the card mark, left of the Bluetooth mark
CLEARED = (0, 2, 3, 4, 5)                        # styles drawn with the bar on and its middle cleared first (list_box, menu_box)
MARKS = {1: ((108, 2), (108, 0), (20, 16)),      # picture box: stock place, new place and size (the battery,
         2: ((2, 3), (0, 0), (17, 16)),          # the card mark, the Bluetooth mark): with the middle, the whole bar
         3: ((98, 2), (98, 0), (10, 16))}
MARK_STORE = 240                                 # free (the stock demo slideshow's): its last rows hold the bordered marks
GROUP_MAX = {0x1000: BANK_MAX, 0x1200: 0x3b8}    # the longest a bank of the group may get (0x1200: largest stock one)

# English menu texts: (old, new); every one is the title of a menu (and mostly the row that leads there)
RENAMES = {
    "SETTING.STY": {137: ("System settings", "Settings"), 20: ("Display settings", "Display"),
                    153: ("Sound settings", "Sound"), 134: ("Speaker on/off", "Speaker"),
                    51: ("Language/Language", "Language"), 38: ("Format device", "Format"),
                    6: ("Date and time", "Date & time"), 171: ("Time settings", "Time"), 12: ("Date settings", "Date"),
                    133: ("Set time format", "Time format"), 128: ("Set date format", "Date format"),
                    1: ("Backlight timer", "Backlight")},
    "BT.STY": {29: ("Bluetooth main menu", "Bluetooth"), 5: ("Bluetooth on/off", "On/off"),
               0: ("Operation interface of available device ", "Device"),
               30: ("Operation interface of pairing device ", "Device"),
               28: ("Operation interface of connecting device", "Device")},
    "RECORD.STY": {3: ("Record menu(card)", "Record"), 4: ("Record menu(no card）", "Record"),
                   1: ("ACT record  menu(card)", "Record"), 2: ("ACT record  menu(card)", "Record"),
                   18: ("Track AVR mode", "AVR mode"), 21: ("set rec bitrate", "Bitrate"),
                   32: ("Record format", "Format"), 39: ("Record settings", "Settings")},
    "RADIO.STY": {18: ("Preset stations", "Presets"), 27: ("Start FM recording", "Record"),
                  5: ("Tuner region ", "Region")},
    "PEDOMETE.STY": {26: ("Personal info", "Profile")},
    "TOOLS.STY": {14: ("Alarm on/off", "On/off")},
    "PICTURE.STY": {0: ("Backlight timer", "Backlight"), 14: ("Slideshow settings", "Slideshow")},
    "EBOOK.STY": {4: ("Ebook background", "Background"), 19: ("E-book", "eBook")},     # 19: the list's name, as the main menu
    "MUSIC.STY": {48: ("Authorization Info", "Music"), 94: ("Sound settings", "Sound")},
    "BROWSER.STY": {17: ("Last played entry menu", "Folders")},      # an option menu's title, never shown
}
MUSIC_TEXT = 48
TITLES = {"MUSIC.MCG": {li: MUSIC_TEXT for li in (0, 1, 55, 56, 57, 58)},    # the Music menu, with card, playing, resume
          "SETTING.MCG": {1: 51}}                                            # the language list
STOCK_TITLES = {"MUSIC.MCG": {0: 10, 1: 0x8000 | 33, 55: 0x8000 | 37, 56: 0x8000 | 37, 57: 67, 58: 67},
                "SETTING.MCG": {1: 137}}

LIST_BANK = 0x18661200                           # the shared list control (gui_directory), in each program's copy
LIST_CALL = 0x18661380                           # its list box call: bl to the svc veneer, (style, data, mode, 8)
LIST_STUB = 0x186614e2
LEVEL_LITERAL = 0x18661400                       # the control's literal: the program's g_dir_browser
BOX_DATA = 0x10116c
MUSIC_PATH = (0x18021478, 0x2003c0)              # MUSIC.AP: the path the list scene is called with (browse_path)
PROGRAMS = {                                     # counter inside an album or playlist; the top level's name
    "MUSIC.AP": dict(counted=True, top=None),    # None: by the list (liststyle.c's own choice)
    "BROWSER.AP": dict(counted=True, top=17),    # "Folders" (renamed above)
    "EBOOK.AP": dict(counted=False, top=19),     # "eBook" (renamed above)
    "VIDEO.AP": dict(counted=False, top=0),      # no text for it: an empty line
    "PICTURE.AP": dict(counted=False, top=0),
}
TOP_NAMES = {"BROWSER.STY": {17: "Folders"}, "EBOOK.STY": {19: "eBook"},
             "MUSIC.STY": {10: "All songs", 8: "Albums", 17: "Artists", 42: "Genres", 72: "Playlists"}}   # liststyle.c's


def records(com):
    off, n = s11.tables_of(com)[LISTS]
    if n != 9:
        sys.exit("COMMON.STY: %d list-box records, expected 9" % n)
    return [(off + k * 28, struct.unpack_from("<4I", com, off + k * 28)) for k in range(n)]


def words(com, at, size):
    return struct.unpack_from("<%dH" % (size // 2), com, at)


def list_styles(lfi):
    com = bytearray(lfi.get("COMMON.STY"))
    recs = records(com)
    for k, (at, subs) in enumerate(recs):
        if com[at + ATTR] != STOCK_ATTR[k]:
            sys.exit("COMMON.STY: list style %d has attributes %#x, not the stock ones" % (k, com[at + ATTR]))
        if k < 8 and words(com, subs[3], 28) != STOCK_COUNTER:
            sys.exit("COMMON.STY: list style %d's counter is not the stock one" % k)
    for k in (DIRLIST, MENULIST):
        if words(com, recs[k][1][0], 12) != STOCK_TITLE:
            sys.exit("COMMON.STY: list style %d's title is not the stock one" % k)
    if [b - a for a, b in zip(recs[HEAD][1], recs[HEAD][1][1:])] != list(SUBS[:3]) or recs[4][1][0] - recs[HEAD][1][3] != SUBS[3]:
        sys.exit("COMMON.STY: list style 3's sub-records are not the sizes of style 0's")
    po = struct.unpack_from("<I", com, 0x10)[0]
    pic = lambda i: struct.unpack_from("<IIHHH", com, po + i * 16)
    if any(pic(DIGITS + d)[3:] != (DIGIT_W, CELL_H) for d in range(10)):
        sys.exit("COMMON.STY: the clock digits are not the stage 15 ones")
    off, ln, _, w, h = pic(COUNTER_BG)
    if any(com[off:off + ln]) or w < 9 * DIGIT_W or h < CELL_H + COUNTER_Y:
        sys.exit("COMMON.STY: picture %d is not a black field for the counter (%dx%d)" % (COUNTER_BG, w, h))

    # 0x6003: a copy of 0x6000 (its own sub-records overwritten with 0x6000's), then the counter in pictures
    (dir_at, dir_subs), (head_at, head_subs) = recs[DIRLIST], recs[HEAD]
    for src, dst, size in zip(dir_subs, head_subs, SUBS):
        com[dst:dst + size] = com[src:src + size]
    com[head_at + 16:head_at + 28] = com[dir_at + 16:dir_at + 28]
    counter = list(STOCK_COUNTER)
    counter[0], counter[1], counter[2] = 0x8000 | DIGITS, 0x8000 | SLASH, DIGIT_W | SLASH_W << 8
    counter[9], counter[10] = STATUS_X, COUNTER_Y
    counter[13] = (counter[13] & ~6) | PICTURE_FORM
    struct.pack_into("<14H", com, head_subs[3], *counter)

    # the title in the status bar: menus (0x6002), and 0x6005 = 0x6000's sub-records with its title shown
    title = (STATUS_X, 0, TITLE_W, 16, s11.s10_colour(T["text2"]), TITLE_FONT)
    for k in (DIRLIST, MENULIST):
        struct.pack_into("<6H", com, recs[k][1][0], *title)
    for k in NO_COUNTER:
        com[recs[k][0] + ATTR] &= ~COUNTER_ON
    com[recs[MENULIST][0] + ATTR] |= TITLE_ON
    named_at = recs[TITLE2][0]
    struct.pack_into("<4I", com, named_at, *dir_subs)
    com[named_at + 16:named_at + 28] = com[dir_at + 16:dir_at + 28]
    com[named_at + ATTR] |= TITLE_ON

    # the styles drawn with the bar's middle cleared get a background below the bar's marks (the others keep the whole
    # screen: they leave the bar alone, so it would keep what the screen before had there); the black field menu_box
    # and list_box clear the bar's middle with
    off, ln, typ, w, h = pic(BLACK)
    if (w, h) != (128, 160) or any(com[off:off + ln]) or any(com[pic(BAR_BG)[0]:pic(BAR_BG)[0] + pic(BAR_BG)[1]]):
        sys.exit("COMMON.STY: pictures %d and %d are not black" % (BLACK, BAR_BG))
    for k in (LIST_BG, BAR_CLEAR):
        if pic(k)[3:] != (12, 12):
            sys.exit("COMMON.STY: picture %d is not the unused stock icon" % k)
    struct.pack_into("<IIHHH", com, po + LIST_BG * 16, off + 128 * BAR_H * 2, 128 * (160 - BAR_H) * 2, typ, 128, 160 - BAR_H)
    bw = BAR_X[1] - BAR_X[0]
    struct.pack_into("<IIHHH", com, po + BAR_CLEAR * 16, off, bw * BAR_H * 2, typ, bw, BAR_H)
    for k in range(8):
        if struct.unpack_from("<3H", com, recs[k][0] + 16) != (0x8000 | BLACK, 0, 0):
            sys.exit("COMMON.STY: list style %d's background is not picture %d at 0, 0" % (k, BLACK))
        if k in CLEARED:
            struct.pack_into("<3H", com, recs[k][0] + 16, 0x8000 | LIST_BG, 0, BAR_H)
    status_marks(com)

    s7.resize_picture(com, SLASH, SLASH_W, CELL_H)
    points = [(x, y + GLYPH_TOP) for x, y in ((2, 1), (2, 2), (1, 3), (1, 4), (0, 5), (0, 6))]   # the track counter's
    s1.set_picture(com, SLASH, s11.dots(SLASH_W, CELL_H, points, T["text2"]), SLASH_W, CELL_H)
    lfi.put("COMMON.STY", bytes(com))
    return {k: com[at + ATTR] for k, (at, _) in enumerate(records(com))}


def status_marks(com):
    """The status bar's three marks (picture boxes 1 to 3, every frame) get a black border out to the bar's edges and
    to its middle. The bar draws a mark's black pixels in its background (driver function 37), so with the middle
    cleared by list_box or menu_box every pixel of rows 0 to 15 is painted, and nothing the screen before left there
    (the screensaver, the reader's page) stays. The marks keep their place on screen; their pictures move to the last
    rows of picture MARK_STORE, which is declared that much shorter."""
    po = struct.unpack_from("<I", com, 0x10)[0]
    entry = lambda i: struct.unpack_from("<IIHHH", com, po + i * 16)
    boxes = s11.tables_of(com)[1][0]
    off, ln, typ, w, h = entry(MARK_STORE)
    if (ln, w, h) != (128 * 160 * 2, 128, 160):
        sys.exit("COMMON.STY: picture %d is not the free full-screen one" % MARK_STORE)
    pieces = []
    for k, ((x0, y0), (x1, y1), (bw, bh)) in sorted(MARKS.items()):
        rec = struct.unpack_from("<16H", com, boxes + k * 32)
        n = rec[3] >> 8
        frames = rec[4:4 + n]
        if rec[1:3] != (x0, y0) or rec[3] & 0xff != 1 or any(f & 0x8000 == 0 or f == 0xffff for f in frames):
            sys.exit("COMMON.STY: picture box %d is not the stock status bar mark" % k)
        dx, dy = x0 - x1, y0 - y1
        for f in frames:
            p_off, p_ln, p_typ, pw, ph = entry(f & 0x7fff)
            if p_ln != pw * ph * 2 or dx + pw > bw or dy + ph > bh:
                sys.exit("COMMON.STY: mark picture %d (%dx%d) does not fit %dx%d" % (f & 0x7fff, pw, ph, bw, bh))
            canvas = bytearray(bw * bh * 2)
            for row in range(ph):
                at = ((dy + row) * bw + dx) * 2
                canvas[at:at + pw * 2] = com[p_off + row * pw * 2:p_off + (row + 1) * pw * 2]
            pieces.append((f & 0x7fff, bytes(canvas), p_typ, bw, bh))
        struct.pack_into("<2H", com, boxes + k * 32 + 2, x1, y1)
    cells = [(x, y) for (x1, y1), (bw, bh) in (v[1:] for v in MARKS.values()) for x in range(x1, x1 + bw) for y in range(y1, y1 + bh)]
    cells += [(x, y) for x in range(*BAR_X) for y in range(BAR_H)]
    if sorted(cells) != [(x, y) for x in range(128) for y in range(BAR_H)]:
        sys.exit("the marks and the bar's middle do not cover rows 0 to %d exactly once" % (BAR_H - 1))
    rows = -(-sum(len(c) for _, c, *_ in pieces) // (w * 2))
    s7.resize_picture(com, MARK_STORE, w, h - rows)
    at = off + (h - rows) * w * 2
    for index, canvas, p_typ, bw, bh in pieces:
        com[at:at + len(canvas)] = canvas
        struct.pack_into("<IIHHH", com, po + index * 16, at, len(canvas), p_typ, bw, bh)
        at += len(canvas)


def width(lfi, text):
    fon = lfi.get("UNICODE.FON")
    return sum(fon[ord(c) * 33 + 32] for c in text)


def english(sty):
    so, sc = struct.unpack_from("<IH", sty, 0x20)
    for k in range(sc):
        off, ln, _, cnt, lid = struct.unpack_from("<IIHHH", sty, so + k * 16)
        if lid == ENGLISH:
            return off, cnt
    sys.exit("no English texts")


def text_of(sty, off, idx):
    o, n = struct.unpack_from("<II", sty, off + idx * 8)
    return bytes(sty[o:o + n]).decode("utf-16-le").rstrip("\0"), o, n


def menu_texts(lfi):
    done = []
    for name, changes in RENAMES.items():
        sty = bytearray(lfi.get(name))
        off, cnt = english(sty)
        for idx, (old, new) in sorted(changes.items()):
            have, o, n = text_of(sty, off, idx)
            raw = (new + "\0").encode("utf-16-le")
            if have != old or len(raw) > n:
                sys.exit("%s: English text %d is %r, or the new one is longer" % (name, idx, have))
            if width(lfi, new) > TITLE_W:
                sys.exit("%s: %r is %d pixels wide, the status bar has %d" % (name, new, width(lfi, new), TITLE_W))
            sty[o:o + n] = raw + bytes(n - len(raw))
            struct.pack_into("<I", sty, off + idx * 8 + 4, len(raw))
        lfi.put(name, bytes(sty))
        done.append("%s %d" % (name[:-4], len(changes)))
    for name, lists in TITLES.items():
        mcg = bytearray(lfi.get(name))
        hsz = struct.unpack_from("<H", mcg, 12)[0]
        for li, eid in lists.items():
            if struct.unpack_from("<H", mcg, hsz + li * 12)[0] != STOCK_TITLES[name][li]:
                sys.exit("%s: list %d's title is not the stock one" % (name, li))
            struct.pack_into("<H", mcg, hsz + li * 12, eid)
        lfi.put(name, bytes(mcg))
    return done


def titles_too_wide(lfi):
    """Menu titles (English) that still do not fit the status bar, for the report."""
    out = []
    for name in sorted(n for n in lfi.entries if n.endswith(".MCG")):
        sty_name = name[:-4] + ".STY"
        if sty_name not in lfi.entries:
            continue
        sty, com = lfi.get(sty_name), lfi.get("COMMON.STY")
        (off, cnt), (coff, ccnt) = english(sty), english(com)
        mcg = lfi.get(name)
        hsz, n = struct.unpack_from("<HH", mcg, 12)
        for eid in sorted({struct.unpack_from("<H", mcg, hsz + li * 12)[0] for li in range(n)} - {0xffff}):
            t = text_of(com, coff, eid & 0x7fff)[0] if eid & 0x8000 else text_of(sty, off, eid)[0] if eid < cnt else ""
            if width(lfi, t) > TITLE_W:
                out.append("%s %r" % (name[:-4], t))
    return out


def compile_tail(work, src, func, defines):
    """One function and nothing else: the code goes into a bank tail, without a data section (no switch tables)."""
    obj = os.path.join(work, func + ".o")
    run(["arm-none-eabi-gcc"] + CFLAGS + ["-fno-tree-switch-conversion"] + defines + ["-c", os.path.join(LIVE, src), "-o", obj],
        "compiling " + src, cwd=work)
    sections = []
    for line in run(["arm-none-eabi-readelf", "-S", "-W", obj], "readelf").splitlines():
        f = line.split("]", 1)[1].split() if "] ." in line else []
        if len(f) > 6 and "A" in f[6] and int(f[4], 16):            # name, type, address, offset, size, entry size, flags
            sections.append(f[0])
    if sections != [".text." + func]:
        sys.exit("%s should give one function and nothing else, not %s" % (src, sections))
    frame = int(open(os.path.join(work, func + ".su")).read().split()[1])
    return obj, frame


def bank_entry(ap, addr):
    """The bank's table entry, file offset, length, and the room its file slot and group allow."""
    starts = sorted(struct.unpack_from("<I", ap, t + i)[0] for t in BANK_TABLES for i in range(0, 0x800, 12)
                    if struct.unpack_from("<III", ap, t + i)[0] and struct.unpack_from("<III", ap, t + i)[2])
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            o, a, n = struct.unpack_from("<III", ap, t + i)
            if o and n and a == addr:
                slot = min([x for x in starts if x > o] + [len(ap)]) - o
                return t + i, o, n, min(slot, GROUP_MAX[a & 0xffff])
    sys.exit("no bank at %#x" % addr)


def put_tail(ap, name, bank, obj, func, work):
    """Link func at the free end of the bank, put it there; its address."""
    hdr, off, ln, top = bank_entry(ap, bank)
    start = (ln + 3) & ~3
    script = os.path.join(work, func + ".ld")
    with open(script, "w") as f:
        f.write("ENTRY(%s)\nSECTIONS\n{\n  .tail 0x%08x : { KEEP(*(.text.%s)) }\n"
                "  /DISCARD/ : { *(.ARM.attributes) *(.comment) *(.note*) }\n}\n" % (func, bank + start, func))
    elf = os.path.join(work, func + ".elf")
    run(["arm-none-eabi-ld", "-T", script, "-o", elf, obj, "--no-undefined"], "linking " + func)
    raw = os.path.join(work, func + ".bin")
    run(["arm-none-eabi-objcopy", "-O", "binary", "--only-section=.tail", elf, raw], "objcopy")
    code = open(raw, "rb").read()
    open(os.path.join(work, func + ".dis"), "w").write(run(["arm-none-eabi-objdump", "-d", elf], "objdump"))
    if start + len(code) > top or any(ap[off + ln:off + top]):
        sys.exit("%s: %s (%d bytes) does not fit the end of bank %#x (%#x of %#x)" % (name, func, len(code), bank, ln, top))
    ap[off + start:off + start + len(code)] = code
    struct.pack_into("<I", ap, hdr + 8, start + len(code))
    return bank + start, len(code)


def ui_entry(ap, segs, veneer):
    """The resident svc 6 entry a veneer (movw ip, #entry; movt ip, #0x11; bx ip) leads to, or None."""
    v = ap_dis.find(segs, veneer)
    if v is None:
        return None
    hw = struct.unpack_from("<5H", ap, v)
    entry = 0x110000 | (hw[0] & 15) << 12 | (hw[0] >> 10 & 1) << 11 | (hw[1] >> 12 & 7) << 8 | (hw[1] & 0xff)
    svc = ap_dis.find(segs, entry & ~1)
    if (hw[0] & 0xfbf0 != 0xf240 or hw[1] & 0x8f00 != 0x0c00 or hw[2:] != (0xf2c0, 0x0c11, 0x4760) or not entry & 1
            or svc is None or bytes(ap[svc:svc + 2]) != b"\x06\xdf"):
        return None
    return entry


def list_calls(ap, segs):
    """The list box calls of a program: movs r3, #8; ldr r1, [pc, ...]; add r0, sp, ... or mov r0, sp; bl to a veneer
    to the display driver. (call address, bank, driver entry)"""
    out = []
    for kind, addr, off, n in segs:
        if kind != "bank":
            continue
        for i in range(0, n - 10, 2):
            o = off + i
            if ap[o:o + 2] != b"\x08\x23" or ap[o + 3] != 0x49 or not (ap[o + 5] == 0xa8 or ap[o + 4:o + 6] == b"\x68\x46"):
                continue
            hi, lo = struct.unpack_from("<HH", ap, o + 6)
            if hi >> 11 != 0x1e or lo >> 14 != 3:
                continue
            entry = ui_entry(ap, segs, bl_at(bytes(ap[o + 6:o + 10]), 0, addr + i + 6))
            if entry:
                out.append((addr + i + 6, addr, entry))
    return out


def place_list_box(ap, name, work, counted=True, top=None):
    """Put list_box at the free end of the list control's bank of one program and point the control's call to it."""
    segs, _ = ap_dis.segments(bytes(ap))
    if bank_entry(ap, LIST_BANK)[2] != 0x314:
        sys.exit("%s: the list control's bank is not the stock one" % name)
    at = ap_dis.find(segs, LIST_CALL)
    if bytes(ap[at - 6:at]) != bytes.fromhex("0823254903a8") or s21.bl_target(ap, segs, LIST_CALL) != LIST_STUB:
        sys.exit("%s: the list control's list box call is not the expected one" % name)
    word = lambda a: struct.unpack_from("<I", ap, ap_dis.find(segs, a))[0]
    if word((LIST_CALL & ~3) + 0x94) != BOX_DATA:              # the ldr r1 at LIST_CALL - 4: pc-relative, #148
        sys.exit("%s: the list control's list data is not at %#x" % (name, BOX_DATA))
    entry = ui_entry(ap, segs, LIST_STUB)
    if entry is None:
        sys.exit("%s: %#x is not a veneer to the display driver's svc 6" % (name, LIST_STUB))
    level = word(LEVEL_LITERAL)
    if bytes(ap[ap_dis.find(segs, 0x18661280):ap_dis.find(segs, 0x18661280) + 2]) != bytes.fromhex("5f48") or not 0x200000 <= level < 0x200800:
        sys.exit("%s: the list control's browser state is not where expected (%#x)" % (name, level))
    defines = ["-DLIST_LEVEL_AT=%#x" % level, "-DLIST_COUNTED=%d" % counted, "-DUI_ENTRY=%#x" % entry]
    if top is None:
        if name != "MUSIC.AP" or word(MUSIC_PATH[0]) != MUSIC_PATH[1]:
            sys.exit("%s: the names by list read the music program's browse path" % name)
    else:
        defines.append("-DTOP_TEXT=%d" % top)
    work = os.path.join(work, name[:-3].lower())
    os.makedirs(work, exist_ok=True)
    obj, frame = compile_tail(work, "liststyle.c", "list_box", defines)
    addr, size = put_tail(ap, name, LIST_BANK, obj, "list_box", work)
    ap[at:at + 4] = s20.thumb_bl(LIST_CALL, addr)
    return addr, size, frame, level, entry


def place_menu_boxes(ap, name, work):
    """Every other list box call of the program goes to menu_box (patches/menu_box.S), one copy at the end of each bank
    with such a call, reaching the driver through that bank's veneer; each copy checked in the simulator."""
    segs, _ = ap_dis.segments(bytes(ap))
    calls = list_calls(ap, segs)
    if not calls:
        sys.exit("%s: no list box calls found" % name)
    work = os.path.join(work, name[:-3].lower())
    os.makedirs(work, exist_ok=True)
    done = []
    for bank in sorted({b for _, b, _ in calls}):
        sites = [at for at, b, _ in calls if b == bank]
        veneers = {bl_at(bytes(ap[ap_dis.find(segs, at):ap_dis.find(segs, at) + 4]), 0, at) for at in sites}
        if len(veneers) != 1:
            sys.exit("%s: the list box calls in bank %#x use different veneers" % (name, bank))
        veneer = veneers.pop()
        hdr, off, ln, top = bank_entry(ap, bank)
        start = (ln + 3) & ~3
        if not 0 <= veneer - bank < ln:
            sys.exit("%s: the veneer of bank %#x is not inside it" % (name, bank))
        tag = os.path.join(work, "menu_box_%08x" % bank)
        src = os.path.join(HERE, "patches", "menu_box.S")
        run(["arm-none-eabi-as", "--defsym", "VENEER_OFF=%#x" % (veneer - bank), "--defsym", "TAIL_OFF=%#x" % start,
             "-o", tag + ".o", src], "assembling menu_box.S")
        run(["arm-none-eabi-objcopy", "-O", "binary", tag + ".o", tag + ".bin"], "objcopy")
        code = open(tag + ".bin", "rb").read()[start:]
        if start + len(code) > top or any(ap[off + ln:off + top]):
            sys.exit("%s: menu_box (%d bytes) does not fit the end of bank %#x (%#x of %#x)" % (name, len(code), bank, ln, top))
        ap[off + start:off + start + len(code)] = code
        struct.pack_into("<I", ap, hdr + 8, start + len(code))
        for at in sites:
            o = ap_dis.find(segs, at)
            ap[o:o + 4] = s20.thumb_bl(at, bank + start)
        dis = s14.disassemble(bytes(ap[off:off + start + len(code)]), bank, tag + ".dis")
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "check_menu_box.py"), dis,
                            "%x" % (bank + start), "%x" % veneer], capture_output=True, text=True)
        if r.returncode:
            sys.exit("%s: menu_box in bank %#x failed its check:\n%s%s" % (name, bank, r.stdout[-600:], r.stderr[-300:]))
        done.append((bank, bank + start, len(code), r.stdout.split()[0], sites))
    return done


def replace_music_code(lfi, work, stock_ap):
    """The playlist code of stages 18 to 23 out of its banks and placed anew (as stage 23 did), avoiding the banks that
    draw lists: their ends are for menu_box, which has to sit in the same bank as its caller."""
    objs, secs = s20.compile_code(work)
    depths = s20.stack_depth(work)
    if max(depths.values()) > s20.STACK_MAX:
        sys.exit("the new code's deepest call chain needs %d bytes of stack" % max(depths.values()))
    ap = bytearray(lfi.get("MUSIC.AP"))
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    ranges = s23.old_code(ap, stock_ap)
    calls, rows = s23.old_targets(ap, mcg, ranges)
    segs, _ = ap_dis.segments(bytes(ap))
    if not s23.inside(ranges, s21.bl_target(ap, segs, s23.STANDBY_CALL)):
        sys.exit("MUSIC.AP %#x: does not call the stage 23 code" % s23.STANDBY_CALL)
    calls[s23.STANDBY_CALL] = "standby_previous"
    s21.take_out_code(ap, stock_ap)
    segs, _ = ap_dis.segments(bytes(ap))
    avoid = sorted({b for _, b, _ in list_calls(ap, segs) if b & 0xffff == 0x1000})
    planning = bytearray(ap)                          # the planner takes a bank whose end is free: these look full
    for bank in avoid:
        _, off, ln, top = bank_entry(planning, bank)
        planning[off + ln:off + top] = b"\xff" * (top - ln)
    banks = s20.plan(planning, secs)
    symbols = s20.link(work, objs, banks)
    put_code(ap, banks)
    segs, _ = ap_dis.segments(bytes(ap))
    for e in s20.ENTRIES:
        if ap_dis.find(segs, symbols[e]) is None:
            sys.exit("%s is outside the program's banks" % e)
    for at, fn in calls.items():
        o = ap_dis.find(segs, at)
        ap[o:o + 4] = s20.thumb_bl(at, symbols[fn])
    for off, fn in rows:
        struct.pack_into("<I", mcg, off, symbols[fn] | 1)
    lfi.put("MUSIC.AP", bytes(ap))
    lfi.put("MUSIC.MCG", bytes(mcg))
    return banks, depths, avoid


HEADBAR_AT = (0x474, 0x4e8)                      # the routine in patches/*.S (laid out from the timer bank)
TABLE_LIT = 0x70                                 # headbar_soon.S: its own literal, the timer table pointer
NEVER = ("CONFIG.AP", "FWUPDATE.AP")             # recovery depends on these
RESTART_CODE = {0x16: "0948", 0x18: "0068", 0x1a: "00eb0415", 0x2e: "6988", 0x30: "0844", 0x32: "a860"}   # the entry's use


def bl_offsets(code):
    """Offsets of the bl instructions in a stretch of code (walked as build_stage22.masked does)."""
    out, i = [], 0
    while i < len(code) - 2:
        hi, lo = struct.unpack_from("<HH", code, i)
        if hi >> 11 == 0x1e and lo >> 14 == 3:
            out.append(i)
            i += 4
        else:
            i += 2
    return out


def bl_at(code, k, at):
    hi, lo = struct.unpack_from("<HH", code, k)
    s = hi >> 10 & 1
    off = s << 24 | (~(lo >> 13 ^ s) & 1) << 23 | (~(lo >> 11 ^ s) & 1) << 22 | (hi & 0x3ff) << 12 | (lo & 0x7ff) << 1
    return at + 4 + (off - (1 << 25) if s else off)


def headbar_soon(lfi, work):
    """Replace the stage 14 status-bar routine with headbar_soon.S in every program that has it."""
    shift = s14.HEADBAR["bank"] - s14.HEADBAR_SOURCE_BASE
    lo, hi = shift + HEADBAR_AT[0], shift + HEADBAR_AT[1]
    old_code = s14.assemble("music_headbar", work)[lo:hi]
    new_code = s14.assemble("headbar_soon", work)[lo:hi]
    start, draw, restart, stop = s22.MUSIC_STRETCH
    old_order = [bl_at(old_code, k, start + k) for k in bl_offsets(old_code)]
    if old_order != [restart, draw, stop]:
        sys.exit("music_headbar.S does not call restart, draw, stop: %s" % [hex(t) for t in old_order])
    pattern = s22.masked(old_code)
    done = []
    for name in sorted(lfi.entries):
        if not name.endswith(".AP") or name in NEVER:
            continue
        ap = bytearray(lfi.get(name))
        try:
            segs, _ = ap_dis.segments(bytes(ap))
        except Exception:
            continue
        here = s22.find_all(ap, segs, pattern)
        if not here:
            continue
        if len(here) != 1:
            sys.exit("%s: the stage 14 status-bar routine is there %d times" % (name, len(here)))
        p_start = here[0]
        calls = [t for _, t in s22.bls(bytes(ap), segs, p_start, s22.HEADBAR_LEN)]
        if len(calls) != 3:
            sys.exit("%s: the status-bar routine makes %d calls" % (name, len(calls)))
        aim = dict(zip((restart, draw, stop), calls))
        r = ap_dis.find(segs, aim[restart])
        if any(bytes(ap[r + k:r + k + len(v) // 2]) != bytes.fromhex(v) for k, v in RESTART_CODE.items()):
            sys.exit("%s: the timer restart at %#x is not the SDK's" % (name, aim[restart]))
        table = struct.unpack_from("<I", ap, r + 0x3c)[0]
        if not 0x200000 <= table < 0x200800:
            sys.exit("%s: the timer table pointer %#x is not in the program's RAM" % (name, table))
        code = bytearray(new_code)
        for k in bl_offsets(new_code):
            code[k:k + 4] = s20.thumb_bl(p_start + k, aim[bl_at(new_code, k, start + k)])
        struct.pack_into("<I", code, TABLE_LIT, table)
        base = [sg for sg in segs if sg[0] == "bank" and sg[1] <= p_start < sg[1] + sg[3]][0]
        bank, boff, blen = base[1], base[2], base[3]
        old = bytes(ap[boff:boff + blen])
        k0 = p_start - bank
        new = old[:k0] + bytes(code) + old[k0 + len(code):]
        args = ["%x" % v for v in (p_start, aim[draw], aim[restart], aim[stop])]
        res = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "check_headbar_soon.py"),
                              s14.disassemble(old, bank, os.path.join(work, name + "_headbar_14.dis")),
                              s14.disassemble(new, bank, os.path.join(work, name + "_headbar_24.dis"))] + args,
                             capture_output=True, text=True)
        if res.returncode:
            sys.exit("%s: the status-bar routine failed its check:\n%s%s" % (name, res.stdout[-600:], res.stderr[-300:]))
        ap[boff + k0:boff + k0 + len(code)] = code
        lfi.put(name, bytes(ap))
        done.append(name[:-3])
    if len(done) != 15:
        sys.exit("the stage 14 status-bar routine was found in %d programs, not 15: %s" % (len(done), ", ".join(done)))
    return done


def fw_constants():
    """The picture and place fw.h's clear_bar uses must be the ones this builder declares."""
    fw = open(os.path.join(LIVE, "fw.h")).read()
    want = {"BAR_CLEAR": "(0x8000 | %d)" % BAR_CLEAR, "BAR_CLEAR_X": str(BAR_X[0]), "STYLE_COUNTED": "0x%x" % (0x6000 + HEAD),
            "STYLE_NAMED": "0x%x" % (0x6000 + TITLE2)}
    asm = open(os.path.join(HERE, "patches", "menu_box.S")).read()
    for k, v in {"BAR_CLEAR": "0x8000 | %d" % BAR_CLEAR, "BAR_X": str(BAR_X[0]), "BAR_STYLES": "0x%x" % sum(1 << k for k in CLEARED)}.items():
        if not re.search(r"\.equ\s+%s,\s*%s\s*$" % (k, re.escape(v)), asm, re.M):
            sys.exit("patches/menu_box.S: %s is not %s" % (k, v))
    for k, v in want.items():
        m = re.search(r"#define %s\s+(\(0x8000 \| \d+\)|\S+)" % k, fw)
        if not m or m.group(1) != v:
            sys.exit("fw.h: %s is %s, the builder uses %s" % (k, m and m.group(1), v))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage24")
    work = os.path.join(out, "code")
    os.makedirs(work, exist_ok=True)
    fw_constants()
    s20.SRC = LIVE
    sources = s20.SOURCES
    s20.SOURCES = sources + ("liststyle.c",)
    print("host test:", s20.host_test(work))
    s20.SOURCES = sources                         # the playlist code; liststyle.c is placed on its own

    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    stock_ap = xm.Lfi(stock).get("MUSIC.AP")
    base = os.environ.get("X91_STAGE23") or os.path.join(ROOT, "x91_dump", "stage23", "x91_lfi_stage23.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 23 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    attrs = list_styles(lfi)
    texts = menu_texts(lfi)
    for name, want in TOP_NAMES.items():
        sty = lfi.get(name)
        off, _ = english(sty)
        for idx, text in want.items():
            if text_of(sty, off, idx)[0] != text or width(lfi, text) > TITLE_W:
                sys.exit("%s: English text %d is not %r, or it is too wide" % (name, idx, text))
    music_banks, depths, avoid = replace_music_code(lfi, work, stock_ap)
    placed, menus = [], []
    for name in sorted(lfi.entries):
        if not name.endswith(".AP") or name in NEVER:
            continue
        ap = bytearray(lfi.get(name))
        try:
            segs, _ = ap_dis.segments(bytes(ap))
        except Exception:
            continue
        if name in PROGRAMS:
            placed.append((name,) + place_list_box(ap, name, work, **PROGRAMS[name]))
        if list_calls(ap, ap_dis.segments(bytes(ap))[0]):
            menus.append((name, place_menu_boxes(ap, name, work)))
        lfi.put(name, bytes(ap))
    if sorted(n for n, *_ in placed) != sorted(PROGRAMS):
        sys.exit("list_box was not placed in every program of PROGRAMS")
    code_sha = hashlib.sha256(b"".join(struct.pack("<I", b["addr"]) + b["code"]
                                       for b in sorted(music_banks, key=lambda b: b["addr"]))).hexdigest()
    box_sha = hashlib.sha256()
    for name, addr, size, *_ in sorted(placed):
        ap = lfi.get(name)
        o = ap_dis.find(ap_dis.segments(ap)[0], addr)
        box_sha.update(name.encode() + struct.pack("<I", addr) + ap[o:o + size])
    if (code_sha, box_sha.hexdigest()) != (CODE_SHA, LIST_BOX_SHA):
        sys.exit("the frozen stage 24 sources no longer give the stage 24 code (%s, %s)" % (code_sha, box_sha.hexdigest()))
    bars = headbar_soon(lfi, work)
    copies = []
    s14.refresh_copies(lfi, copies)

    print("list styles (attribute bits: 1 shown, 2 title, 4 scroll bar, 8 counter): %s"
          % ", ".join("%#x %#x" % (0x6000 + k, a) for k, a in attrs.items()))
    print("titles at (%d, 0), %d wide; counter in pictures %d.. and %d at (%d, %d); backgrounds of %s: picture %d from row %d;"
          " the bar's middle cleared with picture %d (x %d to %d)"
          % (STATUS_X, TITLE_W, DIGITS, SLASH, STATUS_X, COUNTER_Y, ", ".join("%#x" % (0x6000 + k) for k in CLEARED), LIST_BG,
             BAR_H, BAR_CLEAR, BAR_X[0], BAR_X[1] - 1))
    print("status bar marks with a black border out to the bar's edges: %s (pictures in the last rows of %d)"
          % ("; ".join("box %d %dx%d at (%d, %d)" % (k, s[0], s[1], p[0], p[1]) for k, (_, p, s) in sorted(MARKS.items())), MARK_STORE))
    print("menu texts shortened: %s; Music menu titled by MUSIC.STY text %d" % (", ".join(texts), MUSIC_TEXT))
    print("playlist code placed anew: %d bytes in %d banks, deepest stack chain %d bytes; banks left for menu_box: %s"
          % (sum(len(b["code"]) for b in music_banks), len(music_banks), max(depths.values()), ", ".join("%#x" % b for b in avoid)))
    for name, addr, size, frame, level, entry in placed:
        print("list_box in %s: %d bytes at %#x (frame %d bytes), browser state %#x, display driver %#x"
              % (name, size, addr | 1, frame, level, entry))
    for name, banks in menus:
        print("menu_box in %s: %s" % (name, "; ".join("%d bytes at %#x for %s (%s cases checked)"
                                                      % (size, addr | 1, ", ".join("%#x" % c for c in sites), cases)
                                                      for bank, addr, size, cases, sites in banks)))
    print("menu titles still wider than the status bar (menus whose title is never shown, or option menus): %s"
          % ("; ".join(titles_too_wide(lfi)) or "none"))
    print("status bar drawn again right after the screen: %s" % ", ".join(bars))
    print("text-background copies refreshed: %s" % (", ".join(copies) or "none"))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage24.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
