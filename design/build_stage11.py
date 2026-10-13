#!/usr/bin/env python3
"""Stage 11 of the Graphite design, built on the stage 10 image.

  1. Playing screen laid out after the design mock: track counter top left, play state in the status bar,
     cover, centred title, progress bar below the title with the played part in the accent colour,
     times bottom left, play-mode icons bottom right. Layout and pictures in MUSIC.STY, and the routine in
     MUSIC.AP that draws time and bar is rewritten (patches/music_playing.S, replaces the stage 9 patch).
  2. Settings gets "Sound settings" with Equalizer and Volume limit. The settings program has these
     routines; its menu file lists every item it defines, and the X91 simply did not use them.
  3. Lyrics are switched off (MUSIC_LRC_SUPPORT in CONFIG.BIN).
  4. "Playlist 1" is called "Favorites".

usage: build_stage11.py [OUT_DIR]      (default: ../x91_dump/stage11)
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
import x91_preview as xp  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage2 as s2  # noqa: E402
import build_stage4 as s4  # noqa: E402
import build_stage5 as s5  # noqa: E402
import build_stage6 as s6  # noqa: E402
import build_stage7 as s7  # noqa: E402
import build_stage10 as s10  # noqa: E402

T = s1.T
stroke = s4.stroke
BAR_Y, BAR_X, BAR_LEN = 132, 8, 106                 # must match patches/music_playing.S
FAVORITES = {"English": "Favorites", "German": "Favoriten", "French": "Favoris", "Spanish": "Favoritos",
             "Italian": "Preferiti", "Dutch": "Favorieten", "Portuguese_European": "Favoritos",
             "Portuguese_Brazilian": "Favoritos", "Danish": "Favoritter", "Swedish": "Favoriter", "Norwegian": "Favoritter"}


# ------------------------------------------------------------------ settings: lyrics off

def lyrics_off(lfi):
    cfg = bytearray(lfi.get("CONFIG.BIN"))
    off, ln = struct.unpack_from("<II", cfg, 16 + 76 * 8)          # entry 76: MUSIC_LRC_SUPPORT, a choice of 0 or 1
    s5.patch_bytes(cfg, off, struct.pack("<4H", 1, 2, 0, 1), struct.pack("<4H", 0, 2, 0, 1), "CONFIG.BIN lyrics setting")
    lfi.put("CONFIG.BIN", bytes(cfg))
    txt = lfi.get("CONFIG.TXT")
    a, b = b"MUSIC_LRC_SUPPORT = 1[0,1];", b"MUSIC_LRC_SUPPORT = 0[0,1];"
    if a in txt:
        lfi.put("CONFIG.TXT", txt.replace(a, b))


# ------------------------------------------------------------------ settings menu

def pool_items(mcg):
    """Every menu item the settings program defines, from the editor block of its menu file: number -> fields."""
    start = mcg.find(b"ACTMCGGM01")
    items = {}
    for k in range((len(mcg) - start - 14) // 42):
        idx, _, s_1, s_2, f1, _, f2, w1, icon = struct.unpack_from("<IIHHIIIHH", mcg, start + 14 + k * 42)
        if 0x18000000 <= f2 < 0x19000000:
            items.setdefault(idx, dict(text=s_1, text2=s_2, run=f1, common=f2, radio=w1 & 0xff == 1))
    return items


def menu_item(p, child=None, icon=0):
    first = child if child is not None else 0xffff if p["radio"] else 0x7fff
    return struct.pack("<HHHHIII", first, p["text"], p["text2"], icon, p["run"], 0, p["common"])


def sound_settings(lfi):
    mcg = bytearray(lfi.get("SETTING.MCG"))
    pool = pool_items(bytes(mcg))
    names = {17: 153, 21: 32, 22: 0x8026, 23: 30, 24: 26, 25: 27, 26: 28, 27: 24, 28: 31, 29: 25, 34: 180}   # item -> text id
    if any(pool.get(i, {}).get("text") != t for i, t in names.items()):
        sys.exit("SETTING.MCG: the sound items are not the expected ones")
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    table = [list(struct.unpack_from("<HHII", mcg, hsz + i * 12)) for i in range(n)]
    if n != 18 or table[0][:3] != [0x89, 10, hsz + n * 12]:
        sys.exit("SETTING.MCG: unexpected list table")
    root = [bytes(mcg[table[0][2] + k * 20:table[0][2] + (k + 1) * 20]) for k in range(10)]
    SOUND, EQ, AT = 18, 19, 2                                         # new list numbers; place in the root menu
    root.insert(AT, menu_item(pool[17], child=SOUND, icon=12))
    sound = [menu_item(pool[21], child=EQ, icon=27), menu_item(pool[34], icon=14)]
    eq = [menu_item(pool[i], icon=28 + k) for k, i in enumerate(range(22, 30))]
    for row in table:                                                 # lists that hang off a root item behind the new one
        if row[3] != 0xffffffff and row[3] & 0xffff == 0 and row[3] >> 16 >= AT:
            row[3] += 0x10000
    # the new lists go to the end of the file, over the tail of the editor block (the firmware reads only the
    # list table and the lists); the old root list's room takes the two new table entries
    pos = len(mcg) - 512
    for row_id, items, link in ((None, root, None), (153, sound, AT << 16), (32, eq, SOUND)):
        data = b"".join(items)
        mcg[pos:pos + len(data)] = data
        if row_id is None:
            table[0][1:3] = [len(items), pos]
        else:
            table.append([row_id, len(items), pos, link])
        pos += len(data)
    old_root = hsz + n * 12
    mcg[old_root:old_root + 200] = bytes(200)
    for i, row in enumerate(table):
        struct.pack_into("<HHII", mcg, hsz + i * 12, *row)
    struct.pack_into("<H", mcg, 14, len(table))
    lfi.put("SETTING.MCG", bytes(mcg))
    return len(table)


# ------------------------------------------------------------------ playing screen: layout and pictures

def tables_of(sty):
    style = struct.unpack_from("<I", sty, 8)[0]
    begin = struct.unpack_from("<I", sty, style + 8)[0]
    return [struct.unpack_from("<II", sty, begin + t * 8) for t in range(11)]


def set_fields(sty, table, size, index, **fields):
    """Change 16-bit fields of a layout record; the field number is the word index inside the record."""
    off = tables_of(sty)[table][0] + index * size
    for word, value in fields.items():
        struct.pack_into("<H", sty, off + int(word[1:]) * 2, value)


def pixel_glyph(ch, w, h, color, top=0, left=0):
    """A digit in the shapes of the text font, as picture data."""
    px = [0] * (w * h)
    width, _, pattern = s2.HAND[ch]
    v = s10_colour(color)
    for j, line in enumerate(pattern):
        for i, c in enumerate(line):
            if c == "#":
                px[(j + top) * w + i + left] = v
    return struct.pack("<%dH" % len(px), *px)


def s10_colour(color):
    r, g, b = s6.rgb(color)
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


def dots(w, h, points, color):
    px = [0] * (w * h)
    for x, y in points:
        px[y * w + x] = s10_colour(color)
    return struct.pack("<%dH" % len(px), *px)


def bar(w, color, x0=0, x1=None):
    """A piece of the progress bar: 6 rows, the line on rows 2 and 3 from x0 to x1."""
    x1 = w if x1 is None else x1
    row = [s10_colour(color) if x0 <= x < x1 else 0 for x in range(w)]
    return struct.pack("<%dH" % (w * 6), *([0] * (2 * w) + row * 2 + [0] * (2 * w)))


def state_icon(kind):
    """Play state in the status bar, 16 x 16."""
    c = T["text"]
    shapes = {"play": '<path d="M5 3.500l8 4.500-8 4.500z" fill="%s" stroke="%s" stroke-width="1" stroke-linejoin="round"/>' % (c, c),
              "pause": xd.rect(4, 3.5, 3, 9, 0.8, c) + xd.rect(9, 3.5, 3, 9, 0.8, c),
              "ff": '<path d="M2.500 4l5 4-5 4zM8.500 4l5 4-5 4z" fill="%s" stroke="%s" stroke-width=".800" stroke-linejoin="round"/>' % (c, c),
              "rw": '<path d="M13.500 4l-5 4 5 4zM7.500 4l-5 4 5 4z" fill="%s" stroke="%s" stroke-width=".800" stroke-linejoin="round"/>' % (c, c)}
    return s1.svg(16, 16, [shapes[kind]])


def mode_icon(kind, on):
    """Repeat or shuffle, 13 x 11."""
    c = T["accent"] if on else T["text2"]
    parts = [xd.icon("shuffle" if kind == "shuffle" else "repeat", 0.5, -1, 12, c, 2.4)]
    if kind == "one":
        parts.append(s6.text(6.5, 8.2, "1", 6.5, 700, c))
    return s1.svg(13, 11, parts)


def field_icon(kind):
    """Which tag field the title line is showing, 15 x 16."""
    c = T["text2"]
    if kind == "artist":
        body = '<circle cx="7.500" cy="5.500" r="2.400" %s/><path d="M3 13.500c0-2.800 2-4.300 4.500-4.300s4.500 1.500 4.500 4.300" %s/>' % (stroke(c, 1.3), stroke(c, 1.3))
    else:
        body = '<circle cx="7.500" cy="8" r="5" %s/><circle cx="7.500" cy="8" r="1.300" fill="%s"/>' % (stroke(c, 1.3), c)
    return s1.svg(15, 16, [body])


def tinted(data, color):
    """Keep the shape of a white-on-black picture, in another colour."""
    r0, g0, b0 = s6.rgb(color)
    out = bytearray(len(data))
    for i in range(0, len(data), 2):
        v = data[i] | data[i + 1] << 8
        m = max((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31)
        r, g, b = r0 * m // 255, g0 * m // 255, b0 * m // 255
        struct.pack_into("<H", out, i, (r >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return bytes(out)


def playing_screen(lfi, work):
    sty = bytearray(lfi.get("MUSIC.STY"))
    t = tables_of(sty)
    if (t[1][1], t[2][1], t[3][1], t[4][1]) != (15, 4, 1, 2) or t[2][0] - t[1][0] != 15 * 32 or t[4][0] - t[3][0] != 28:
        sys.exit("MUSIC.STY: the layout tables are not the expected ones")
    put = lambda index, svg_text, w, h, name: s1.set_picture(sty, index, s1.render_565(svg_text, w, h, work, name), w, h)
    raw = lambda index, data, w, h: s1.set_picture(sty, index, data, w, h)

    # --- layout. Picture box: id, x, y, ...; text box: id, x, y, w, h, back x, back y, back id, colour, attributes
    set_fields(sty, 3, 28, 0, w0=24, w8=24)                           # track counter: x and its background's x
    set_fields(sty, 4, 36, 1, w0=8, w1=146, w13=8, w14=146)           # elapsed/total
    set_fields(sty, 2, 20, 0, w1=16, w2=113, w3=96, w5=16, w6=113, w9=0xa7)   # title: centred, 96 wide
    for box, x, y in ((1, 100, 145), (2, 114, 145), (5, 0, 113), (6, 80, 0), (9, 80, 0), (7, 84, 146), (8, 127, 159)):
        set_fields(sty, 1, 32, box, w1=x, w2=y)

    # --- progress bar pieces
    raw(67, bar(128, T["line"], BAR_X, BAR_X + BAR_LEN + 6), 128, 6)
    raw(49, bar(128, T["line"], BAR_X, BAR_X + BAR_LEN + 6), 128, 6)
    raw(65, bar(1, T["accent"]), 1, 6)
    raw(66, bar(1, T["line"]), 1, 6)
    raw(70, bar(6, T["accent"]), 6, 6)
    raw(69, bar(6, T["line"]), 6, 6)
    put(68, s1.svg(6, 6, ['<circle cx="3" cy="3" r="2.800" fill="%s"/>' % T["text"]]), 6, 6, "progress-knob")

    # --- digits: time 51..60 with colon 17 and slash 74/88, track counter 77..86
    for k in range(10):
        raw(51 + k, pixel_glyph(str(k), 6, 8, T["text2"]), 6, 8)
        raw(77 + k, pixel_glyph(str(k), 6, 8, T["text2"]), 6, 8)
    raw(17, dots(4, 8, [(1, 2), (1, 5)], T["text2"]), 4, 8)
    for index in (74, 88):
        raw(index, dots(4, 8, [(2, 1), (2, 2), (1, 3), (1, 4), (0, 5), (0, 6)], T["text2"]), 4, 8)

    # --- icons
    for index, kind in ((63, "play"), (62, "pause"), (27, "ff"), (28, "rw")):
        put(index, state_icon(kind), 16, 16, "state-" + kind)
    for index, label in ((37, "A-B"), (39, "-B"), (40, "A-")):
        put(index, s1.svg(16, 16, [s6.text(8, 11.5, label, 8.5, 700, T["accent"])]), 16, 16, "state-ab-%d" % index)
    put(36, mode_icon("repeat", False), 13, 11, "mode-normal")
    put(33, mode_icon("repeat", True), 13, 11, "mode-repeat")
    put(35, mode_icon("one", True), 13, 11, "mode-repeat-one")
    put(73, mode_icon("shuffle", True), 13, 11, "mode-shuffle")
    put(14, field_icon("artist"), 15, 16, "field-artist")
    put(13, field_icon("album"), 15, 16, "field-album")
    for index, color in ((34, T["text2"]), (89, T["accent"]), (90, T["accent"]), (24, T["text2"]), (30, T["text2"]), (16, T["text2"])):
        data, w, h = s4.picture_bytes(sty, index)
        raw(index, tinted(data, color), w, h)
    for index in range(18, 27):                                       # equaliser name on the playing screen: not shown
        s7.resize_picture(sty, index, 1, 1)
        raw(index, bytes(2), 1, 1)

    # --- "Playlist 1" becomes "Favorites" where the word is known and fits
    names = [lg["name"] for lg in xp.Sty(os.path.join(ROOT, "x91_dump", "unpacked", "MUSIC.STY")).langs]
    renamed = 0
    for name, table in zip(names, s5.language_tables(sty)):
        if name in FAVORITES and s5.set_string(sty, table, 73, FAVORITES[name], []):
            renamed += 1
    lfi.put("MUSIC.STY", bytes(sty))
    return renamed


# ------------------------------------------------------------------ playing screen: the routine

BANK, BANK_LEN, LO, HI = 0x18061000, 0x644, 0x390, 0x476
STAGE9_ROUTINE, STOCK_ROUTINE = "4066924572a550a6", "c92da8f38e364d31"


def disassemble(data, path):
    tmp = path + ".bin"
    open(tmp, "wb").write(data)
    r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                        "--adjust-vma=%#x" % BANK, tmp], capture_output=True, text=True)
    os.remove(tmp)
    open(path, "w").write(r.stdout)
    return path


def patch_music(lfi, work):
    src = os.path.join(HERE, "patches", "music_playing.S")
    text = open(src).read()
    for name, value in (("BAR_Y", BAR_Y), ("BAR_X", BAR_X), ("BAR_LEN", BAR_LEN)):
        if ".equ    %s, %d" % (name, value) not in text:
            sys.exit("%s differs between the patch source and this script" % name)
    obj, raw = os.path.join(work, "playing_patch.o"), os.path.join(work, "playing_patch.bin")
    for cmd in (["arm-none-eabi-as", "-o", obj, src], ["arm-none-eabi-objcopy", "-O", "binary", obj, raw]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit("could not assemble the playing-screen patch: " + r.stderr[-300:])
    built = open(raw, "rb").read()[LO:HI]
    os.remove(raw)
    ap = bytearray(lfi.get("MUSIC.AP"))
    segs, _ = ap_dis.segments(ap)
    base = ap_dis.find(segs, BANK)
    stock_ap = open(os.path.join(ROOT, "x91_dump", "unpacked", "MUSIC.AP"), "rb").read()
    stock_bank = stock_ap[base:base + BANK_LEN]
    digest = lambda b: hashlib.sha256(b[LO:HI]).hexdigest()[:16]
    if digest(ap[base:base + BANK_LEN]) != STAGE9_ROUTINE or digest(stock_bank) != STOCK_ROUTINE:
        sys.exit("MUSIC.AP: the routine to replace is not the expected one")
    word = lambda addr: struct.unpack_from("<I", ap, ap_dis.find(segs, addr))[0]
    if (word(0x1806147c), word(0x18cc1b94), word(0x18cc1b98)) != (0x20002c, 0x200190, 0x200191):
        sys.exit("MUSIC.AP: the variables the patch relies on are not where expected")
    new_bank = stock_bank[:LO] + built + stock_bank[HI:]
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "check_playing_patch.py"),
                        disassemble(stock_bank, os.path.join(work, "playing_stock.dis")),
                        disassemble(new_bank, os.path.join(work, "playing_new.dis"))], capture_output=True, text=True)
    if r.returncode:
        sys.exit("the playing-screen patch failed its check:\n%s%s" % (r.stdout[-600:], r.stderr[-300:]))
    ap[base + LO:base + HI] = built
    lfi.put("MUSIC.AP", bytes(ap))
    return r.stdout.strip()


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage11")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE10") or os.path.join(ROOT, "x91_dump", "stage10", "x91_lfi_stage10.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 10 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    lyrics_off(lfi)
    print("lyrics switched off")
    print("settings menu: %d lists (Sound settings and Equalizer added)" % sound_settings(lfi))
    print("playing screen: layout and pictures; 'Favorites' in %d languages" % playing_screen(lfi, work))
    print("music program patch:", patch_music(lfi, work))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage11.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
