#!/usr/bin/env python3
"""Stage 16 of the Graphite design, built on the stage 15 image: the eBook reader in landscape.

The reading screen is turned a quarter: the screen's top edge becomes the left edge, the text runs across the
long side, and the only furniture is a thin progress bar with the page number at the bottom.

  How the reader draws (EBOOK.AP, bank 0x180e1000): a painting routine draws a strip with the page number,
  then the page background, then asks the page-layout routine for the lines and draws each with the text
  call. Lines per page and line width are two numbers set when a book is opened (bank 0x180c1000); the
  line's place on screen is three numbers in the line-drawing routine. The display driver can turn the
  screen (function 30); its landscape is the one wanted here.

  1. Layout numbers: 7 lines of 152 pixels (stock 9 of 128), drawn from x=4, y=0 downward, 16 apart.
  2. The painting routine is rewritten (patches/ebook_reader.S): landscape is switched on before the
     drawing and off after it, so menus, notices and the screensaver stay as they are. The strip moves to
     the bottom and gets a progress bar; the mark for automatic page turning is no longer drawn.
  3. Pictures and layout (EBOOK.STY): the five page colours as 160 x 116 pages and 160 x 12 strips with the
     bar's track; two small accent pictures the bar is made of; the page number is drawn as text in the
     reading font (the number boxes are switched from digit pictures to text, one number, right-aligned).
  4. The reader keeps a page index per book, valid for one layout only. Its signature is changed
     (five places), so indexes made with the old layout are rebuilt instead of being trusted.

usage: build_stage16.py [OUT_DIR]      (default: ../x91_dump/stage16)
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
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage5 as s5  # noqa: E402
import build_stage6 as s6  # noqa: E402
import build_stage7 as s7  # noqa: E402
import build_stage11 as s11  # noqa: E402
import build_stage14 as s14  # noqa: E402

T = s1.T
W, H = 160, 128                                  # the screen in landscape
ROWS, ROW_H, TEXT_X, TEXT_W = 7, 16, 4, 152
PAGE_H = ROWS * ROW_H + 4                        # 116: the page picture; the strip below it is 12 high
BAR_X, BAR_LEN, BAR_Y = 6, 104, 119              # must match patches/ebook_reader.S
PIECE, COLUMN = 43, 44                           # pictures the bar's filled part is made of
NUMBER = dict(x=120, y=112, w=36, h=16)          # the page number: text, right-aligned, digits on rows 117 to 124
# page colour number -> page, page number, bar track. The firmware writes white text on pages 1 and 4, black otherwise.
PAGES = [((245, 243, 238), (96, 94, 90), (214, 211, 203)),
         (None, (150, 152, 156), None),                               # the theme's own dark surface
         ((246, 222, 189), (120, 98, 66), (222, 196, 160)),
         ((222, 234, 238), (86, 102, 112), (190, 205, 212)),
         ((0, 0, 0), (150, 152, 156), (52, 54, 58))]
OLD_SIGNATURE, NEW_SIGNATURE = 0x55aaaa55, 0x55aaaa56
SIGNATURE_AT = (0x110224, 0x1804154c, 0x181611ec, 0x18161408, 0x18161530)
BANK, BANK_LEN = 0x180e1000, 0x660
STRETCHES = ((0x0dc, 0x18e, "ee61f3972c90ed78"), (0x3c0, 0x408, "3da77b39945a7c10"), (0x48c, 0x50a, "1c214248031a43e5"))
POOLS = {0x190: 0x200052, 0x194: 0x200051, 0x198: 0x202fbc, 0x19c: 0x2001a0, 0x1a0: 0x200030, 0x1a4: 0x2004f8,
         0x1a8: 0x110e00, 0x50c: 0x2001a0, 0x510: 0x200020, 0x514: 0x200024, 0x518: 0x20004a}
COUNTING_FLAG = 0x200054                         # the page-count flag the patch reads as "full repaint flag + 10"


def c565(rgb):
    return (rgb[0] >> 3) << 11 | (rgb[1] >> 2) << 5 | rgb[2] >> 3


def colours(index):
    page, number, track = PAGES[index]
    return (page or s6.rgb(T["surface"])), number, (track or s6.rgb(T["line"]))


def fill(w, h, rgb):
    return struct.pack("<H", c565(rgb)) * (w * h)


def strip_picture(page, track):
    px = [c565(page)] * (W * (H - PAGE_H))
    for y in range(BAR_Y - PAGE_H, BAR_Y - PAGE_H + 3):
        for x in range(BAR_X, BAR_X + BAR_LEN):
            px[y * W + x] = c565(track)
    return struct.pack("<%dH" % len(px), *px)


def edit_resources(lfi):
    sty = bytearray(lfi.get("EBOOK.STY"))
    t = s11.tables_of(sty)
    recs = s14.pictures(sty)
    if (t[1][1], t[3][1]) != (3, 5) or [r[3:] for r in recs[:5]] != [(128, 145)] * 5 or [r[3:] for r in recs[6:11]] != [(128, 15)] * 5:
        sys.exit("EBOOK.STY: the reader's layout is not the expected one")
    for k in range(5):
        page, number, track = colours(k)
        s7.resize_picture(sty, k, W, PAGE_H)                          # 128 x 145 and 160 x 116 hold the same number of pixels
        s1.set_picture(sty, k, fill(W, PAGE_H, page), W, PAGE_H)
        s7.resize_picture(sty, 6 + k, W, H - PAGE_H)                  # 128 x 15 and 160 x 12 likewise
        s1.set_picture(sty, 6 + k, strip_picture(page, track), W, H - PAGE_H)
        # number box k: x, y, w, h, -, -, -, -, -, -, background colour, text colour, digits and decimals, attributes.
        # Attributes: shown, right-aligned, normal font, one number, drawn as text on a plain colour.
        # "15 decimals" is more than a number has digits, which is how the formatter is told to add no point.
        s11.set_fields(sty, 3, 28, k, w0=NUMBER["x"], w1=NUMBER["y"], w2=NUMBER["w"], w3=NUMBER["h"],
                       w10=c565(page), w11=c565(number), w12=0x0f00, w13=0x0089)
    for index, w in ((PIECE, 8), (COLUMN, 1)):
        s7.resize_picture(sty, index, w, 3)
        s1.set_picture(sty, index, fill(w, 3, s6.rgb(T["accent"])), w, 3)
    s11.set_fields(sty, 1, 32, 0, w1=0, w2=0)                         # page
    s11.set_fields(sty, 1, 32, 2, w1=0, w2=PAGE_H)                    # strip
    s11.set_fields(sty, 1, 32, 1, w3=0x0a00)                          # the automatic-turning mark: not shown
    lfi.put("EBOOK.STY", bytes(sty))


def disassemble(data, path):
    tmp = path + ".bin"
    open(tmp, "wb").write(data)
    r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                        "--adjust-vma=%#x" % BANK, tmp], capture_output=True, text=True)
    os.remove(tmp)
    open(path, "w").write(r.stdout)
    return path


def patch_reader(lfi, work):
    src = open(os.path.join(HERE, "patches", "ebook_reader.S")).read()
    for name, value in (("BAR_X", BAR_X), ("BAR_LEN", BAR_LEN), ("BAR_Y", BAR_Y), ("PIECE", PIECE), ("COLUMN", COLUMN)):
        if ".equ    %s, %d" % (name, value) not in src:
            sys.exit("%s differs between the patch source and this script" % name)
    built = s14.assemble("ebook_reader", work)
    ap = bytearray(lfi.get("EBOOK.AP"))
    segs, _ = ap_dis.segments(ap)
    at = lambda addr: ap_dis.find(segs, addr)
    base = at(BANK)
    old = bytes(ap[base:base + BANK_LEN])
    for lo, hi, digest in STRETCHES:
        if hashlib.sha256(old[lo:hi]).hexdigest()[:16] != digest:
            sys.exit("EBOOK.AP: the reading screen's code is not the expected one (at %#x)" % lo)
    if any(struct.unpack_from("<I", old, off)[0] != value for off, value in POOLS.items()) or \
            POOLS[0x190] != POOLS[0x194] + 1 or POOLS[0x194] != POOLS[0x518] + 7 or COUNTING_FLAG != POOLS[0x518] + 10:
        sys.exit("EBOOK.AP: the reader's variables are not where expected")
    counting = at(0x11022c)                                           # the page counter's "running" flag, as that code names it
    if struct.unpack_from("<I", ap, counting)[0] != COUNTING_FLAG:
        sys.exit("EBOOK.AP: the page-count flag is not where expected")
    new = bytearray(old)
    for lo, hi, _ in STRETCHES:
        new[lo:hi] = built[lo:hi]
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "check_ebook_patch.py"),
                        disassemble(old, os.path.join(work, "reader_stock.dis")),
                        disassemble(bytes(new), os.path.join(work, "reader_new.dis"))], capture_output=True, text=True)
    if r.returncode:
        sys.exit("the reader patch failed its check:\n%s%s" % (r.stdout[-800:], r.stderr[-300:]))
    ap[base:base + BANK_LEN] = new
    # the line's place on screen: x, y = 16 * line + 16, width  ->  x = TEXT_X, y = 16 * line, width = TEXT_W
    s5.patch_bytes(ap, at(0x180e11b2), bytes.fromhex("0020"), bytes([TEXT_X, 0x20]), "EBOOK.AP line x")
    s5.patch_bytes(ap, at(0x180e11b8), bytes.fromhex("20011030"), bytes.fromhex("20010030"), "EBOOK.AP line y")
    s5.patch_bytes(ap, at(0x180e11c0), bytes.fromhex("8020"), bytes([TEXT_W, 0x20]), "EBOOK.AP line width")
    # the page layout: lines per page, pixels per line
    s5.patch_bytes(ap, at(0x180c120a), bytes.fromhex("0920"), bytes([ROWS, 0x20]), "EBOOK.AP lines per page")
    s5.patch_bytes(ap, at(0x180c1210), bytes.fromhex("8021"), bytes([TEXT_W, 0x21]), "EBOOK.AP line width for the layout")
    for addr in SIGNATURE_AT:
        s5.patch_bytes(ap, at(addr), struct.pack("<I", OLD_SIGNATURE), struct.pack("<I", NEW_SIGNATURE), "EBOOK.AP page-index signature")
    if ap.count(struct.pack("<I", OLD_SIGNATURE)):
        sys.exit("EBOOK.AP: the old page-index signature is still somewhere")
    lfi.put("EBOOK.AP", bytes(ap))
    return r.stdout.strip()


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage16")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE15") or os.path.join(ROOT, "x91_dump", "stage15", "x91_lfi_stage15.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 15 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    edit_resources(lfi)
    print("reader pictures and layout: %d x %d page, %d lines of %d pixels, strip with bar and page number" % (W, PAGE_H, ROWS, TEXT_W))
    print("reader program:", patch_reader(lfi, work))
    copies = []
    s14.refresh_copies(lfi, copies)
    print("sideways copies brought in line:", "; ".join(copies) or "none needed")
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage16.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
