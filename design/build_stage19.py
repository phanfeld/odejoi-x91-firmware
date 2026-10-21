#!/usr/bin/env python3
"""Stage 19 of the Graphite design, built on the stage 18 image.

  1. Glyphs. Stage 2 drew the font with a typeface that lacks some characters; for those it drew the typeface's
     "missing" box. Tags use some of them: "alt‐J" and "The All‐American Rejects" are written with U+2010 HYPHEN
     and showed "alt[]J". Each such glyph becomes a copy of the drawn glyph that looks like it (hyphens: "-",
     figure dash: en dash, reversed quotes: the plain ones, and so on). Three unassigned Greek code points keep
     the box.
  2. Playlists: only the .m3u playlists. The Playlists view is the file browser over the .m3u list with the menu
     list 49 of MUSIC.MCG (the built-in Favorites, Playlist 2, Playlist 3) as extra rows on top; MUSIC.AP
     0x181011ca sets that up for list type 8. Setting only its row count to 0 (first build of stage 19) left the
     rows on the player: the browser goes by the menu pointer. Now the whole branch is skipped (0x181011ce
     bne -> b), so the browser keeps its defaults: no menu pointer, no rows, no "menu rows only" flag.
  3. Menu rows that only serve the built-in playlists are hidden: "Remove from Playlist" in the options of the
     playing screen (lists 42 and 59, row 5) and "Add to playlist" in the options of the song lists (lists 21
     to 25, last row). The links of the sub-menus behind the rows that move up are adjusted.

usage: build_stage19.py [OUT_DIR]      (default: ../x91_dump/stage19)
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
import build_stage5 as s5  # noqa: E402

G = 33                                           # bytes per glyph of UNICODE.FON
GLYPH_COPIES = {0x2010: 0x2D, 0x2011: 0x2D, 0x2012: 0x2013, 0x2016: 0x7C, 0x2017: 0x5F, 0x201B: 0x2018,
                0x201F: 0x201C, 0x2023: 0x2022, 0x2024: 0x2E, 0x2025: 0x2026, 0x0387: 0xB7}
BOX_KEPT = (0x038B, 0x038D, 0x03A2)              # not characters at all
OPTION_LISTS, REMOVE_ROW = (42, 59), 5
SONG_OPTION_LISTS = (21, 22, 23, 24, 25)


def glyphs(lfi):
    font = bytearray(lfi.get("UNICODE.FON"))
    box = bytes(font[0x2010 * G:(0x2010 + 1) * G])
    boxed = sorted(cp for cp in range(0x20, 0x10000) if font[cp * G:(cp + 1) * G] == box)
    if boxed != sorted(list(GLYPH_COPIES) + list(BOX_KEPT)):
        sys.exit("UNICODE.FON: the glyphs drawn as boxes are not the expected ones: %s" % [hex(c) for c in boxed])
    for cp, src in GLYPH_COPIES.items():
        if font[src * G:(src + 1) * G] == box:
            sys.exit("UNICODE.FON: U+%04X would be copied from a box" % cp)
        font[cp * G:(cp + 1) * G] = font[src * G:(src + 1) * G]
    lfi.put("UNICODE.FON", bytes(font))
    return len(GLYPH_COPIES)


def playlists_only(lfi):
    ap = bytearray(lfi.get("MUSIC.AP"))
    segs, _ = ap_dis.segments(bytes(ap))
    at = ap_dis.find(segs, 0x181011ca)
    # ldrb r0, [r4] ; cmp r0, #8 ; bne.n 0x181011f2 ; movs r0, #0 ; strb.w r0, [sp] ; movs r0, #49
    old = bytes.fromhex("2078082810d100208df800003120")
    new = old[:4] + bytes.fromhex("10e0") + old[6:]                 # b.n 0x181011f2
    s5.patch_bytes(ap, at, old, new, "MUSIC.AP menu rows of the Playlists view")
    lfi.put("MUSIC.AP", bytes(ap))


def remove_row(mcg, hsz, n, li, row):
    """Takes row `row` out of list `li`; rows behind it move up, links to them follow."""
    eid, cnt, off, link = struct.unpack_from("<HHII", mcg, hsz + li * 12)
    rows = [bytes(mcg[off + k * 20:off + (k + 1) * 20]) for k in range(cnt)]
    del rows[row]
    mcg[off:off + cnt * 20] = b"".join(rows) + bytes(20)
    struct.pack_into("<HHII", mcg, hsz + li * 12, eid, cnt - 1, off, link)
    for j in range(n):
        e, c, o, lk = struct.unpack_from("<HHII", mcg, hsz + j * 12)
        if lk != 0xffffffff and lk & 0xffff == li and lk >> 16 > row:
            struct.pack_into("<HHII", mcg, hsz + j * 12, e, c, o, lk - 0x10000)


def hide_rows(lfi):
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    row_text = lambda li, k: struct.unpack_from("<HHHH", mcg, struct.unpack_from("<HHII", mcg, hsz + li * 12)[2] + k * 20)
    for li in OPTION_LISTS:
        first, text, _, icon = row_text(li, REMOVE_ROW)
        if text != 34 or icon != 16:
            sys.exit("MUSIC.MCG: list %d row %d is not \"Remove from Playlist\"" % (li, REMOVE_ROW))
        remove_row(mcg, hsz, n, li, REMOVE_ROW)
    for li in SONG_OPTION_LISTS:
        cnt = struct.unpack_from("<HHII", mcg, hsz + li * 12)[1]
        first, text, _, _ = row_text(li, cnt - 1)
        if text != 5 or not 60 <= first <= 64:
            sys.exit("MUSIC.MCG: the last row of list %d is not \"Add to playlist\"" % li)
        remove_row(mcg, hsz, n, li, cnt - 1)
    lfi.put("MUSIC.MCG", bytes(mcg))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage19")
    os.makedirs(out, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE18") or os.path.join(ROOT, "x91_dump", "stage18", "x91_lfi_stage18.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 18 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    print("glyphs: %d placeholder boxes replaced by drawn glyphs" % glyphs(lfi))
    playlists_only(lfi)
    print("Playlists view: only the .m3u playlists")
    hide_rows(lfi)
    print("menus: \"Remove from Playlist\" (lists %s) and \"Add to playlist\" (lists %s) hidden"
          % (", ".join(map(str, OPTION_LISTS)), ", ".join(map(str, SONG_OPTION_LISTS))))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage19.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
