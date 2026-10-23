"""The top line of menus and lists, and short menu names.

  1. Menus show no item counter ("position/total"; list styles 0x6001, 0x6002, 0x6004, 0x6006, 0x6007 of COMMON.STY,
     attribute bit 3). The main menus (0x6002) show the menu's name instead, at the top left of the status bar where the
     main menu has its clock (x=22), in the interface font and the second text colour, up to the Bluetooth and battery
     marks (x=98, 76 pixels).
  2. Menu names that were wrong or too long get short English texts, in the title and in the row that leads there
     (RENAMES). The Music menu's lists are titled "Music" (MUSIC.STY text 48, the Audible "Authorization Info", which
     this player never shows); the language list "Language".
  3. The file lists (0x6000) show nothing in the status bar; two copies of their look: 0x6003 (stock MENULIST_HEAD,
     unused) with the counter in the track counter's place and digits (the main menu clock's digits, COMMON.STY 135 to
     144, a slash in picture 125, an unused stock icon declared 4 x 12, over the black picture 250, at (22, 1)), and
     0x6005 (stock MENULIST_TITLE2, unused) with the list's title in the status bar like the menus.
  4. design/playlist/liststyle.c picks the style for every draw of the shared list control (gui_directory at
     0x18661200 in MUSIC.AP, BROWSER.AP, EBOOK.AP, VIDEO.AP and PICTURE.AP; its list box call at 0x18661380): the
     counter inside one album or playlist (music lists and folder view only), else the level's name. It is compiled
     once per program and sits at the free end of the control's own bank (new-code banks load at 0x101000, over the
     list data the control keeps at 0x10116c).
  5. No blink: the styles drawn with the status bar on (CLEARED: 0x6000, 0x6002 to 0x6005) get a background from row 16
     down (picture 126, a view into the black picture 185); the code that draws them first clears the bar's middle
     (x 17 to 97, picture 127): list_box, menu_box (patches/menu_box.S, at the end of every bank with another list box
     call, through that bank's own veneer, checked by patches/check_menu_box.py) and the playlist picker. The other
     styles (0x6001 lists, 0x6006 option menus) keep the whole-screen background: they are drawn without the bar.
"""
import os
import re
import struct
import subprocess
import sys

from . import base, newcode
from .base import T, ap_dis, fail

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
BAR_H = 16                                       # the list background from here down: the bar's marks end at row 15
BAR_X = (17, 98)                                 # the bar's middle: right of the card mark, left of the Bluetooth mark
CLEARED = (0, 2, 3, 4, 5)                        # styles drawn with the bar on and its middle cleared first

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
TOP_NAMES = {"BROWSER.STY": {17: "Folders"}, "EBOOK.STY": {19: "eBook"},
             "MUSIC.STY": {10: "All songs", 8: "Albums", 17: "Artists", 42: "Genres", 72: "Playlists"}}   # liststyle.c's

LIST_BANK = 0x18661200                           # the shared list control (gui_directory), in each program's copy
LIST_CALL = 0x18661380                           # its list box call: bl to the svc veneer, (style, data, mode, 8)
LIST_STUB = 0x186614e2
LIST_BANK_LEN = 0x314                            # its stock length
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
GROUP_MAX = {0x1000: newcode.BANK_MAX, 0x1200: 0x3b8}   # the longest a bank of the group may get (0x1200: its
                                                       # largest stock one)


# ------------------------------------------------------------------ list styles

def records(com):
    off, n = base.tables_of(com)[LISTS]
    if n != 9:
        fail("COMMON.STY: %d list-box records, expected 9" % n)
    return [(off + k * 28, struct.unpack_from("<4I", com, off + k * 28)) for k in range(n)]


def words(com, at, size):
    return struct.unpack_from("<%dH" % (size // 2), com, at)


def list_styles(b):
    com = b.get("COMMON.STY")
    recs = records(com)
    for k, (at, subs) in enumerate(recs):
        if com[at + ATTR] != STOCK_ATTR[k]:
            fail("COMMON.STY: list style %d has attributes %#x, not the stock ones" % (k, com[at + ATTR]))
        if k < 8 and words(com, subs[3], 28) != STOCK_COUNTER:
            fail("COMMON.STY: list style %d's counter is not the stock one" % k)
    for k in (DIRLIST, MENULIST):
        if words(com, recs[k][1][0], 12) != STOCK_TITLE:
            fail("COMMON.STY: list style %d's title is not the stock one" % k)
    if [y - x for x, y in zip(recs[HEAD][1], recs[HEAD][1][1:])] != list(SUBS[:3]) or recs[4][1][0] - recs[HEAD][1][3] != SUBS[3]:
        fail("COMMON.STY: list style 3's sub-records are not the sizes of style 0's")
    po = struct.unpack_from("<I", com, 0x10)[0]
    pic = lambda i: struct.unpack_from("<IIHHH", com, po + i * 16)
    if any(pic(DIGITS + d)[3:] != (DIGIT_W, CELL_H) for d in range(10)):
        fail("COMMON.STY: the clock digits are not the status bar's")
    off, ln, _, w, h = pic(COUNTER_BG)
    if any(com[off:off + ln]) or w < 9 * DIGIT_W or h < CELL_H + COUNTER_Y:
        fail("COMMON.STY: picture %d is not a black field for the counter (%dx%d)" % (COUNTER_BG, w, h))

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
    title = (STATUS_X, 0, TITLE_W, 16, base.c565(T["text2"]), TITLE_FONT)
    for k in (DIRLIST, MENULIST):
        struct.pack_into("<6H", com, recs[k][1][0], *title)
    for k in NO_COUNTER:
        com[recs[k][0] + ATTR] &= ~COUNTER_ON
    com[recs[MENULIST][0] + ATTR] |= TITLE_ON
    named_at = recs[TITLE2][0]
    struct.pack_into("<4I", com, named_at, *dir_subs)
    com[named_at + 16:named_at + 28] = com[dir_at + 16:dir_at + 28]
    com[named_at + ATTR] |= TITLE_ON

    # backgrounds below the bar's marks for the styles drawn with the bar's middle cleared (the others keep the whole
    # screen: they leave the bar alone, so it would keep what the screen before had there); the black field menu_box
    # and list_box clear the bar's middle with
    off, ln, typ, w, h = pic(BLACK)
    if (w, h) != (128, 160) or any(com[off:off + ln]) or any(com[pic(BAR_BG)[0]:pic(BAR_BG)[0] + pic(BAR_BG)[1]]):
        fail("COMMON.STY: pictures %d and %d are not black" % (BLACK, BAR_BG))
    for k in (LIST_BG, BAR_CLEAR):
        if pic(k)[3:] != (12, 12):
            fail("COMMON.STY: picture %d is not the unused stock icon" % k)
    struct.pack_into("<IIHHH", com, po + LIST_BG * 16, off + 128 * BAR_H * 2, 128 * (160 - BAR_H) * 2, typ, 128, 160 - BAR_H)
    bw = BAR_X[1] - BAR_X[0]
    struct.pack_into("<IIHHH", com, po + BAR_CLEAR * 16, off, bw * BAR_H * 2, typ, bw, BAR_H)
    for k in range(8):
        if struct.unpack_from("<3H", com, recs[k][0] + 16) != (0x8000 | BLACK, 0, 0):
            fail("COMMON.STY: list style %d's background is not picture %d at 0, 0" % (k, BLACK))
        if k in CLEARED:
            struct.pack_into("<3H", com, recs[k][0] + 16, 0x8000 | LIST_BG, 0, BAR_H)

    base.resize_picture(com, SLASH, SLASH_W, CELL_H)
    points = [(x, y + GLYPH_TOP) for x, y in ((2, 1), (2, 2), (1, 3), (1, 4), (0, 5), (0, 6))]   # the track counter's
    base.set_picture(com, SLASH, base.dots(SLASH_W, CELL_H, points, T["text2"]), SLASH_W, CELL_H)
    b.put("COMMON.STY", com)
    return {k: com[at + ATTR] for k, (at, _) in enumerate(records(com))}


# ------------------------------------------------------------------ menu texts

def menu_texts(b):
    done = []
    for name, changes in RENAMES.items():
        sty = b.get(name)
        base.set_english(sty, changes, name, wider=(TITLE_W, lambda t: base.text_width(b, t)))
        b.put(name, sty)
        done.append("%s %d" % (name[:-4], len(changes)))
    for name, lists in TITLES.items():
        mcg = b.get(name)
        hsz = struct.unpack_from("<H", mcg, 12)[0]
        for li, eid in lists.items():
            if struct.unpack_from("<H", mcg, hsz + li * 12)[0] != STOCK_TITLES[name][li]:
                fail("%s: list %d's title is not the stock one" % (name, li))
            struct.pack_into("<H", mcg, hsz + li * 12, eid)
        b.put(name, mcg)
    for name, want in TOP_NAMES.items():
        sty = b.lfi.get(name)
        off, _ = base.english(sty)
        for idx, value in want.items():
            if base.text_of(sty, off, idx)[0] != value or base.text_width(b, value) > TITLE_W:
                fail("%s: English text %d is not %r, or it is too wide" % (name, idx, value))
    return done


def titles_too_wide(b):
    """Menu titles (English) that still do not fit the status bar, for the report."""
    out = []
    com = b.lfi.get("COMMON.STY")
    coff, _ = base.english(com)
    for name in sorted(n for n in b.lfi.entries if n.endswith(".MCG")):
        sty_name = name[:-4] + ".STY"
        if sty_name not in b.lfi.entries:
            continue
        sty = b.lfi.get(sty_name)
        off, cnt = base.english(sty)
        mcg = b.lfi.get(name)
        hsz, n = base.menu_heads(mcg)
        for eid in sorted({struct.unpack_from("<H", mcg, hsz + li * 12)[0] for li in range(n)} - {0xffff}):
            t = base.text_of(com, coff, eid & 0x7fff)[0] if eid & 0x8000 else base.text_of(sty, off, eid)[0] if eid < cnt else ""
            if base.text_width(b, t) > TITLE_W:
                out.append("%s %r" % (name[:-4], t))
    return out


# ------------------------------------------------------------------ list_box and menu_box

def bank_entry(ap, addr):
    """The bank's table entry, file offset, length, the room its file slot and group allow, and its address."""
    for hdr, off, a, ln in base.bank_list(ap):
        if a == addr:
            return hdr, off, ln, min(base.slot_of(ap, off), GROUP_MAX[a & 0xffff]), a
    fail("no bank at %#x" % addr)


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
            entry = ui_entry(ap, segs, base.bl_at(bytes(ap[o + 6:o + 10]), 0, addr + i + 6))
            if entry:
                out.append((addr + i + 6, addr, entry))
    return out


def place_list_box(ap, name, work, counted=True, top=None):
    """list_box at the free end of the list control's bank of one program; the control's call pointed at it."""
    segs, _ = ap_dis.segments(bytes(ap))
    if bank_entry(ap, LIST_BANK)[2] != LIST_BANK_LEN:
        fail("%s: the list control's bank is not the stock one" % name)
    at = ap_dis.find(segs, LIST_CALL)
    if bytes(ap[at - 6:at]) != bytes.fromhex("0823254903a8") or base.bl_target(ap, segs, LIST_CALL) != LIST_STUB:
        fail("%s: the list control's list box call is not the expected one" % name)
    word = lambda a: base.word_at(ap, segs, a)
    if word((LIST_CALL & ~3) + 0x94) != BOX_DATA:              # the ldr r1 at LIST_CALL - 4: pc-relative, #148
        fail("%s: the list control's list data is not at %#x" % (name, BOX_DATA))
    entry = ui_entry(ap, segs, LIST_STUB)
    if entry is None:
        fail("%s: %#x is not a veneer to the display driver's svc 6" % (name, LIST_STUB))
    level = word(LEVEL_LITERAL)
    o = ap_dis.find(segs, 0x18661280)
    if bytes(ap[o:o + 2]) != bytes.fromhex("5f48") or not 0x200000 <= level < 0x200800:
        fail("%s: the list control's browser state is not where expected (%#x)" % (name, level))
    defines = ["-DLIST_LEVEL_AT=%#x" % level, "-DLIST_COUNTED=%d" % counted, "-DUI_ENTRY=%#x" % entry]
    if top is None:
        if name != "MUSIC.AP" or word(MUSIC_PATH[0]) != MUSIC_PATH[1]:
            fail("%s: the names by list read the music program's browse path" % name)
    else:
        defines.append("-DTOP_TEXT=%d" % top)
    obj, frame = newcode.compile_tail(work, newcode.LIST_SOURCE, "list_box", defines)
    addr, size = newcode.put_tail(ap, name, bank_entry(ap, LIST_BANK), obj, "list_box", work)
    ap[at:at + 4] = base.thumb_bl(LIST_CALL, addr)
    return addr, size, frame


def place_menu_boxes(ap, name, work):
    """Every other list box call of the program goes to menu_box (patches/menu_box.S), one copy at the end of each bank
    with such a call, reaching the driver through that bank's veneer; each copy checked in the simulator."""
    segs, _ = ap_dis.segments(bytes(ap))
    calls = list_calls(ap, segs)
    done = []
    for bank in sorted({bk for _, bk, _ in calls}):
        sites = [at for at, bk, _ in calls if bk == bank]
        veneers = {base.bl_at(bytes(ap[ap_dis.find(segs, at):ap_dis.find(segs, at) + 4]), 0, at) for at in sites}
        if len(veneers) != 1:
            fail("%s: the list box calls in bank %#x use different veneers" % (name, bank))
        veneer = veneers.pop()
        hdr, off, ln, top, _ = bank_entry(ap, bank)
        start = (ln + 3) & ~3
        if not 0 <= veneer - bank < ln:
            fail("%s: the veneer of bank %#x is not inside it" % (name, bank))
        code = base.assemble("menu_box", work, defsym=(("VENEER_OFF", veneer - bank), ("TAIL_OFF", start)))[start:]
        if start + len(code) > top or any(ap[off + ln:off + top]):
            fail("%s: menu_box (%d bytes) does not fit the end of bank %#x (%#x of %#x)" % (name, len(code), bank, ln, top))
        ap[off + start:off + start + len(code)] = code
        struct.pack_into("<I", ap, hdr + 8, start + len(code))
        for at in sites:
            o = ap_dis.find(segs, at)
            ap[o:o + 4] = base.thumb_bl(at, bank + start)
        dis = base.disassemble(bytes(ap[off:off + start + len(code)]), bank, os.path.join(work, "menu_box_%08x.dis" % bank))
        r = subprocess.run([sys.executable, "-I", os.path.join(base.PATCHES, "check_menu_box.py"), dis,
                            "%x" % (bank + start), "%x" % veneer], capture_output=True, text=True)
        if r.returncode:
            fail("%s: menu_box in bank %#x failed its check:\n%s%s" % (name, bank, r.stdout[-600:], r.stderr[-300:]))
        done.append((bank, bank + start, len(code), r.stdout.split()[0], sites))
    return done


def constants():
    """The picture and place fw.h's clear_bar and menu_box.S use must be the ones this module declares."""
    fw = open(os.path.join(base.PLAYLIST, "fw.h")).read()
    want = {"BAR_CLEAR": "(0x8000 | %d)" % BAR_CLEAR, "BAR_CLEAR_X": str(BAR_X[0]), "STYLE_COUNTED": "0x%x" % (0x6000 + HEAD),
            "STYLE_NAMED": "0x%x" % (0x6000 + TITLE2)}
    asm = open(os.path.join(base.PATCHES, "menu_box.S")).read()
    for k, v in {"BAR_CLEAR": "0x8000 | %d" % BAR_CLEAR, "BAR_X": str(BAR_X[0]), "BAR_STYLES": "0x%x" % sum(1 << k for k in CLEARED)}.items():
        if not re.search(r"\.equ\s+%s,\s*%s\s*$" % (k, re.escape(v)), asm, re.M):
            fail("patches/menu_box.S: %s is not %s" % (k, v))
    for k, v in want.items():
        m = re.search(r"#define %s\s+(\(0x8000 \| \d+\)|\S+)" % k, fw)
        if not m or m.group(1) != v:
            fail("fw.h: %s is %s, the build uses %s" % (k, m and m.group(1), v))


def build(b):
    constants()
    attrs = list_styles(b)
    texts = menu_texts(b)
    placed, menus = [], {}
    for name in b.programs():
        ap = b.get(name)
        try:
            segs, _ = ap_dis.segments(bytes(ap))
        except Exception:
            continue
        work = b.folder("lists", name[:-3].lower())
        if name in PROGRAMS:
            placed.append((name,) + place_list_box(ap, name, work, **PROGRAMS[name]))
        if list_calls(ap, ap_dis.segments(bytes(ap))[0]):
            menus[name] = place_menu_boxes(ap, name, work)
        b.put(name, ap)
    if sorted(n for n, *_ in placed) != sorted(PROGRAMS):
        fail("list_box was not placed in every program of PROGRAMS")
    b.menu_boxes = {name: [bank for bank, *_ in done] for name, done in menus.items()}
    b.note("list styles (attribute bits: 1 shown, 2 title, 4 scroll bar, 8 counter): %s",
           ", ".join("%#x %#x" % (0x6000 + k, a) for k, a in attrs.items()))
    b.note("menu texts shortened: %s; Music menu titled by MUSIC.STY text %d", ", ".join(texts), MUSIC_TEXT)
    for name, addr, size, frame in placed:
        b.note("list_box in %s: %d bytes at %#x (frame %d bytes)", name, size, addr | 1, frame)
    b.note("menu_box: %d copies in %d programs", sum(len(v) for v in menus.values()), len(menus))
    b.note("menu titles still wider than the status bar (never shown, or option menus): %s",
           "; ".join(titles_too_wide(b)) or "none")
