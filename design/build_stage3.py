#!/usr/bin/env python3
"""Stage 3 of the Graphite design, built on the stage 1 image.

  1. Typeface as in stage 2, with M, N, O and Q redrawn.
  2. Main menu reduced to five entries: Music, Folder, Bluetooth, eBook, Settings.
     This changes one list in the compiled settings (CONFIG.BIN); its size and layout stay the same.
  3. Music menu: Playlists moved to the top (the records in MUSIC.MCG are reordered, nothing else).
  4. Lists: new picture for the selected row, selected text in white instead of yellow.

usage: build_stage3.py [OUT_DIR]      (default: ../x91_dump/stage3)
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import x91_design as xd  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage2 as s2  # noqa: E402

T = s1.T
# main-menu entries: (icon, application id in the settings, picture that shows it highlighted)
MENU = [("music", 0, 19), ("folder", 5, 18), ("bluetooth", 11, 17), ("book", 4, 25), ("settings", 10, 23)]
OLD_MENU = [0, 2, 8, 3, 11, 1, 5, 7, 10]


def menu_picture(sel):
    parts = []
    for i, (ic, _, _) in enumerate(MENU):
        x, y = 5 + (i % 3) * 41, 20 + (i // 3) * 46
        on = i == sel
        parts += [xd.rect(x, y, 36, 36, 10, T["accent"] if on else T["surface"]),
                  xd.icon(ic, x + 7, y + 7, 22, T["on_accent"] if on else T["text"])]
    return s1.svg(128, 144, parts)


def row_picture(w):
    """Selected list row: a soft panel with the accent bar at the left."""
    return s1.svg(w, 24, [xd.rect(1, 1.5, w - 3, 21, 6.5, T["surface"]), xd.rect(4, 6.5, 3, 11, 1.5, T["accent"])])


def edit_config(lfi):
    cfg = bytearray(lfi.get("CONFIG.BIN"))
    off, ln = struct.unpack_from("<II", cfg, 16 + 1 * 8)          # second entry: MAINMENU_AP_ID_ARRAY
    old = struct.pack("<HH%dH" % len(OLD_MENU), 0, len(OLD_MENU), *OLD_MENU)
    if ln != len(old) or bytes(cfg[off:off + ln]) != old:
        sys.exit("CONFIG.BIN: the main-menu list is not where it is expected")
    ids = [m[1] for m in MENU]
    new = struct.pack("<HH%dH" % len(OLD_MENU), 0, len(ids), *(ids + [0] * (len(OLD_MENU) - len(ids))))
    cfg[off:off + ln] = new
    lfi.put("CONFIG.BIN", bytes(cfg))
    # keep the readable copy in step; the firmware does not read it
    txt = bytearray(lfi.get("CONFIG.TXT"))
    a = b"MAINMENU_AP_ID_ARRAY = 0[0, 2, 8, 3, 11, 1, 5, 7, 10];"
    b = ("MAINMENU_AP_ID_ARRAY = 0[%s];" % ", ".join(map(str, ids))).encode()
    i = txt.find(a)
    if i >= 0:
        txt[i:i + len(a)] = b + b" " * (len(a) - len(b))
        lfi.put("CONFIG.TXT", bytes(txt))


def playlists_first(lfi):
    """Move the Playlists record (text 0x48) to the front of every music list that starts with All songs."""
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    moved = 0
    for i in range(n):
        eid, cnt, off, _ = struct.unpack_from("<HHII", mcg, hsz + i * 12)
        items = [bytes(mcg[off + k * 20:off + (k + 1) * 20]) for k in range(cnt)]
        texts = [struct.unpack_from("<H", it, 2)[0] for it in items]
        if cnt >= 5 and texts[0] == 0x0A and 0x48 in texts:          # All songs first, Playlists somewhere
            k = texts.index(0x48)
            items.insert(0, items.pop(k))
            mcg[off:off + cnt * 20] = b"".join(items)
            moved += 1
    lfi.put("MUSIC.MCG", bytes(mcg))
    return moved


def edit_lists(lfi, work):
    com = bytearray(lfi.get("COMMON.STY"))
    s1.set_picture(com, 292, s1.render_565(row_picture(125), 125, 24, work, "row-125"), 125, 24)
    s1.set_picture(com, 293, s1.render_565(row_picture(140), 140, 24, work, "row-140"), 140, 24)
    style = struct.unpack_from("<I", com, 8)[0]
    begin = struct.unpack_from("<I", com, style + 8)[0]
    off, cnt = struct.unpack_from("<II", com, begin + 6 * 8)          # list controls
    changed = 0
    for k in range(cnt):
        item = struct.unpack_from("<I", com, off + k * 28 + 8)[0]
        if not item:
            continue
        if struct.unpack_from("<H", com, item + 18 * 2)[0] == 0xFFE0:  # selected text: yellow -> white
            struct.pack_into("<H", com, item + 18 * 2, 0xFFFF)
            changed += 1
    lfi.put("COMMON.STY", bytes(com))
    return changed


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage3")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE1") or os.path.join(ROOT, "x91_dump", "stage1", "x91_lfi_stage1.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 1 image does not pass its checksums")

    done, skipped, wide = s2.new_font(lfi)
    print("typeface: %d glyphs replaced" % done)

    menu = bytearray(lfi.get("MAINMENU.STY"))
    for sel, (ic, _, pic) in enumerate(MENU):
        s1.set_picture(menu, pic, s1.render_565(menu_picture(sel), 128, 144, work, "menu5-%d-%s" % (sel, ic)), 128, 144)
    lfi.put("MAINMENU.STY", bytes(menu))
    edit_config(lfi)
    print("main menu: %d entries" % len(MENU))
    print("music menu: Playlists moved to the top in %d list(s)" % playlists_first(lfi))
    print("lists: selected-text colour changed in %d list styles" % edit_lists(lfi, work))

    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage3.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    names = [n for n in lfi.entries if lfi.get(n) != stock[lfi.entries[n][1]:lfi.entries[n][1] + lfi.entries[n][2]]]
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files that differ from the stock firmware:", ", ".join(sorted(names)))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
