"""The eBook reader in landscape, with lines that end between words.

The reading screen is turned a quarter: the screen's top edge becomes the left edge, the text runs across the long
side, and the only furniture is a thin progress bar with the page number at the bottom.

  How the reader draws (EBOOK.AP, bank 0x180e1000): a painting routine draws a strip with the page number, then the
  page background, then asks the page-layout routine for the lines and draws each with the text call. Lines per page,
  line width and the line-measuring mode are numbers set when a book is opened (bank 0x180c1000); the line's place on
  screen is three numbers in the line-drawing routine. The display driver can turn the screen (function 30).

  1. Layout numbers: 7 lines of 152 pixels (stock 9 of 128), drawn from x=4, y=0 downward, 16 apart.
  2. The painting routine is rewritten (patches/ebook_reader.S): landscape is switched on before the drawing and off
     after it, so menus, notices and the screensaver stay as they are. The strip moves to the bottom and gets a
     progress bar; the mark for automatic page turning is no longer drawn.
  3. Pictures and layout (EBOOK.STY): the five page colours as 160 x 116 pages and 160 x 12 strips with the bar's
     track; two small accent pictures the bar is made of; the page number as text in the reading font.
  4. Line breaks: the driver's line measuring (function 24) ends a line before a word that does not fit when bit 1 of
     its mode is set; the reader passed 0, now 2. A word, for the driver, is a run of A to Z, a to z and the straight
     apostrophe. Limits that come with that rule: a word wider than a line (in UTF-16 about 127 characters are skipped
     there, in a one-byte text the reader cannot get past it); accented letters and the curly apostrophe do not count
     as letters; in UTF-16 a line broken this way starts with the space before the word.
  5. The reader keeps a page index per book, valid for one layout only; its signature (five places) changes, so
     indexes made with the stock layout are rebuilt instead of being trusted.
"""
import hashlib
import os
import struct

from . import base
from .base import T, ap_dis, fail, rgb

W, H = 160, 128                                  # the screen in landscape
ROWS, ROW_H, TEXT_X, TEXT_W = 7, 16, 4, 152
PAGE_H = ROWS * ROW_H + 4                        # 116: the page picture; the strip below it is 12 high
BAR_X, BAR_LEN, BAR_Y = 6, 104, 119              # must match patches/ebook_reader.S
PIECE, COLUMN = 43, 44                           # pictures the bar's filled part is made of
NUMBER = dict(x=120, y=112, w=36, h=16)          # the page number: text, right-aligned, digits on rows 117 to 124
WORD_BREAKS = 2                                  # mode bit 1 of the driver's line measuring
# page colour number -> page, page number, bar track. The firmware writes white text on pages 1 and 4, black otherwise.
PAGES = [((245, 243, 238), (96, 94, 90), (214, 211, 203)),
         (None, (150, 152, 156), None),                               # the theme's own dark surface
         ((246, 222, 189), (120, 98, 66), (222, 196, 160)),
         ((222, 234, 238), (86, 102, 112), (190, 205, 212)),
         ((0, 0, 0), (150, 152, 156), (52, 54, 58))]
OLD_SIGNATURE, NEW_SIGNATURE = 0x55aaaa55, 0x55aaaa57
SIGNATURE_AT = (0x110224, 0x1804154c, 0x181611ec, 0x18161408, 0x18161530)
BANK, BANK_LEN = 0x180e1000, 0x660
STRETCHES = ((0x0dc, 0x18e, "ee61f3972c90ed78"), (0x3c0, 0x408, "3da77b39945a7c10"), (0x48c, 0x50a, "1c214248031a43e5"))
POOLS = {0x190: 0x200052, 0x194: 0x200051, 0x198: 0x202fbc, 0x19c: 0x2001a0, 0x1a0: 0x200030, 0x1a4: 0x2004f8,
         0x1a8: 0x110e00, 0x50c: 0x2001a0, 0x510: 0x200020, 0x514: 0x200024, 0x518: 0x20004a}
COUNTING_FLAG = 0x200054                         # the page-count flag the patch reads as "full repaint flag + 10"


def colours(index):
    page, number, track = PAGES[index]
    return (page or rgb(T["surface"])), number, (track or rgb(T["line"]))


def strip_picture(page, track):
    c = base.c565
    px = [c(page)] * (W * (H - PAGE_H))
    for y in range(BAR_Y - PAGE_H, BAR_Y - PAGE_H + 3):
        for x in range(BAR_X, BAR_X + BAR_LEN):
            px[y * W + x] = c(track)
    return struct.pack("<%dH" % len(px), *px)


def resources(b):
    sty = b.get("EBOOK.STY")
    t = base.tables_of(sty)
    recs = base.pictures(sty)
    if (t[1][1], t[3][1]) != (3, 5) or [r[3:] for r in recs[:5]] != [(128, 145)] * 5 or [r[3:] for r in recs[6:11]] != [(128, 15)] * 5:
        fail("EBOOK.STY: the reader's layout is not the expected one")
    for k in range(5):
        page, number, track = colours(k)
        base.resize_picture(sty, k, W, PAGE_H)                        # 128 x 145 and 160 x 116 hold the same number of pixels
        base.set_picture(sty, k, base.fill(W, PAGE_H, page), W, PAGE_H)
        base.resize_picture(sty, 6 + k, W, H - PAGE_H)                # 128 x 15 and 160 x 12 likewise
        base.set_picture(sty, 6 + k, strip_picture(page, track), W, H - PAGE_H)
        # number box k: x, y, w, h, -, -, -, -, -, -, background colour, text colour, digits and decimals, attributes.
        # Attributes: shown, right-aligned, normal font, one number, drawn as text on a plain colour.
        # "15 decimals" is more than a number has digits, which is how the formatter is told to add no point.
        base.set_fields(sty, 3, 28, k, w0=NUMBER["x"], w1=NUMBER["y"], w2=NUMBER["w"], w3=NUMBER["h"],
                        w10=base.c565(page), w11=base.c565(number), w12=0x0f00, w13=0x0089)
    for index, w in ((PIECE, 8), (COLUMN, 1)):
        base.resize_picture(sty, index, w, 3)
        base.set_picture(sty, index, base.fill(w, 3, T["accent"]), w, 3)
    base.set_fields(sty, 1, 32, 0, w1=0, w2=0)                        # page
    base.set_fields(sty, 1, 32, 2, w1=0, w2=PAGE_H)                   # strip
    base.set_fields(sty, 1, 32, 1, w3=0x0a00)                         # the automatic-turning mark: not shown
    b.put("EBOOK.STY", sty)


def program(b, work):
    src = open(os.path.join(base.PATCHES, "ebook_reader.S")).read()
    for name, value in (("BAR_X", BAR_X), ("BAR_LEN", BAR_LEN), ("BAR_Y", BAR_Y), ("PIECE", PIECE), ("COLUMN", COLUMN)):
        if ".equ    %s, %d" % (name, value) not in src:
            fail("%s differs between patches/ebook_reader.S and this script" % name)
    built = base.assemble("ebook_reader", work)
    ap = b.get("EBOOK.AP")
    segs, _ = ap_dis.segments(ap)
    at = lambda addr: ap_dis.find(segs, addr)
    start = at(BANK)
    old = bytes(ap[start:start + BANK_LEN])
    for lo, hi, digest in STRETCHES:
        if hashlib.sha256(old[lo:hi]).hexdigest()[:16] != digest:
            fail("EBOOK.AP: the reading screen's code is not the expected one (at %#x)" % lo)
    if any(struct.unpack_from("<I", old, off)[0] != value for off, value in POOLS.items()) or \
            POOLS[0x190] != POOLS[0x194] + 1 or POOLS[0x194] != POOLS[0x518] + 7 or COUNTING_FLAG != POOLS[0x518] + 10:
        fail("EBOOK.AP: the reader's variables are not where expected")
    if struct.unpack_from("<I", ap, at(0x11022c))[0] != COUNTING_FLAG:     # the page counter's "running" flag
        fail("EBOOK.AP: the page-count flag is not where expected")
    new = bytearray(old)
    for lo, hi, _ in STRETCHES:
        new[lo:hi] = built[lo:hi]
    result = base.check("check_ebook_patch.py", old, bytes(new), BANK, work, "reader")
    ap[start:start + BANK_LEN] = new
    # the line's place on screen: x, y = 16 * line + 16, width  ->  x = TEXT_X, y = 16 * line, width = TEXT_W
    base.patch_bytes(ap, at(0x180e11b2), bytes.fromhex("0020"), bytes([TEXT_X, 0x20]), "EBOOK.AP line x")
    base.patch_bytes(ap, at(0x180e11b8), bytes.fromhex("20011030"), bytes.fromhex("20010030"), "EBOOK.AP line y")
    base.patch_bytes(ap, at(0x180e11c0), bytes.fromhex("8020"), bytes([TEXT_W, 0x20]), "EBOOK.AP line width")
    # the page layout: lines per page, pixels per line, line-measuring mode (movs r1, #0 ; strh.w r1, [r0, #568])
    base.patch_bytes(ap, at(0x180c120a), bytes.fromhex("0920"), bytes([ROWS, 0x20]), "EBOOK.AP lines per page")
    base.patch_bytes(ap, at(0x180c1210), bytes.fromhex("8021"), bytes([TEXT_W, 0x21]), "EBOOK.AP line width for the layout")
    base.patch_bytes(ap, at(0x180c1218), bytes.fromhex("0021a0f83812"), bytes([WORD_BREAKS]) + bytes.fromhex("21a0f83812"),
                     "EBOOK.AP line-measuring mode")
    for addr in SIGNATURE_AT:
        base.patch_bytes(ap, at(addr), struct.pack("<I", OLD_SIGNATURE), struct.pack("<I", NEW_SIGNATURE),
                         "EBOOK.AP page-index signature")
    if ap.count(struct.pack("<I", OLD_SIGNATURE)):
        fail("EBOOK.AP: the old page-index signature is still somewhere")
    b.put("EBOOK.AP", ap)
    return result


def build(b):
    work = b.folder("reader")
    resources(b)
    checked = program(b, work)
    b.note("reader: landscape, %d lines of %d pixels, lines end between words, progress bar and page number (%s); "
           "page-index signature %#x", ROWS, TEXT_W, checked, NEW_SIGNATURE)
