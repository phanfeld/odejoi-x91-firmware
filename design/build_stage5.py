#!/usr/bin/env python3
"""Stage 5 of the Graphite design, built on the stage 4 image.

  1. A Playlists tile in the main menu (six tiles: Music, Playlists, Folder, Bluetooth, eBook, Settings).
     This is the first stage that changes program code:
       MAINMENU.AP  the entry that used to start the alarm now starts the music program with start code 0x40;
                    moving up or down in the grid steps by one row of a two-row grid (it was a three-row grid).
       MUSIC.AP     when started with code 0x40, the root-menu routine skips the menu and continues exactly
                    as if "Playlists" had been chosen there (patches/music_playlists_tile.S).
     Plus the data that goes with it: menu list in CONFIG.BIN, six-tile pictures and the tile's label.
  2. Music menu while something is playing: Playlists moved up to second place, after "Now playing".
  3. Playing screen: black background instead of the red glow, spectrum in the accent colour,
     progress bar in accent on a thin track, new placeholder cover.

usage: build_stage5.py [OUT_DIR]      (default: ../x91_dump/stage5)
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
sys.path.insert(0, os.path.join(HERE, "patches"))
import ap_dis  # noqa: E402
import x91_design as xd  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage4 as s4  # noqa: E402
import check_music_patch  # noqa: E402

T = s1.T
TILE_CODE = 0x40
# main-menu entries: (icon, application id in the settings, picture that shows it highlighted)
MENU = [("music", 0, 19), ("playlist", 1, 16), ("folder", 5, 18),
        ("bluetooth", 11, 17), ("book", 4, 25), ("settings", 10, 23)]
STAGE3_MENU = [0, 5, 11, 4, 10]


# ------------------------------------------------------------------ program patches

def patch_bytes(buf, offset, old, new, what):
    if bytes(buf[offset:offset + len(old)]) != old:
        sys.exit("%s: unexpected bytes at %#x, not patching" % (what, offset))
    buf[offset:offset + len(new)] = new


def patch_mainmenu(lfi):
    ap = bytearray(lfi.get("MAINMENU.AP"))
    segs, _ = ap_dis.segments(ap)
    at = lambda addr: ap_dis.find(segs, addr)
    # the special case for entry 1: was "start program 9 (tools) with code 18 (alarm)"
    patch_bytes(ap, at(0x110168), bytes.fromhex("0920"), bytes.fromhex("0020"), "MAINMENU.AP program number")
    patch_bytes(ap, at(0x11016e), bytes.fromhex("1221"), bytes((TILE_CODE, 0x21)), "MAINMENU.AP start code")
    # grid of two rows instead of three: down = +3 or back to the top row, up = -3 or on to the bottom row
    patch_bytes(ap, at(0x110100), bytes.fromhex("0628"), bytes.fromhex("0328"), "MAINMENU.AP down")
    patch_bytes(ap, at(0x110108), bytes.fromhex("801f"), bytes.fromhex("c01e"), "MAINMENU.AP down")
    patch_bytes(ap, at(0x11012c), bytes.fromhex("801d"), bytes.fromhex("c01c"), "MAINMENU.AP up")
    lfi.put("MAINMENU.AP", bytes(ap))


def patch_music(lfi, work):
    src = os.path.join(HERE, "patches", "music_playlists_tile.S")
    obj, raw = os.path.join(work, "music_patch.o"), os.path.join(work, "music_patch.bin")
    for cmd in (["arm-none-eabi-as", "-o", obj, src], ["arm-none-eabi-objcopy", "-O", "binary", obj, raw]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit("could not assemble the music patch: " + r.stderr[-300:])
    built = open(raw, "rb").read()
    os.remove(raw)
    lo, hi = 0x2dc, 0x35e
    ap = bytearray(lfi.get("MUSIC.AP"))
    segs, _ = ap_dis.segments(ap)
    base = ap_dis.find(segs, 0x18101000)
    old_bank = bytes(ap[base:base + 0x67c])
    if hashlib.sha256(old_bank[lo:hi]).hexdigest()[:16] != "141b217e040863cc":
        sys.exit("MUSIC.AP: the routine to patch is not the expected one (%s)" % hashlib.sha256(old_bank[lo:hi]).hexdigest()[:16])
    if built[0xec:0xf0] != old_bank[0xec:0xf0] or built[0x42c:0x430] != old_bank[0x42c:0x430]:
        sys.exit("MUSIC.AP: the constants the patch relies on are not where expected")
    new_bank = old_bank[:lo] + built[lo:hi] + old_bank[hi:]
    # run the stock and the patched code side by side on every input combination
    dis = []
    for name, data in (("old", old_bank), ("new", new_bank)):
        p = os.path.join(work, "bank_%s.bin" % name)
        open(p, "wb").write(data)
        r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                            "--adjust-vma=0x18101000", p], capture_output=True, text=True)
        dis.append(os.path.join(work, "bank_%s.dis" % name))
        open(dis[-1], "w").write(r.stdout)
        os.remove(p)
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "check_music_patch.py")] + dis,
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("the music patch failed its side-by-side check:\n" + r.stdout[-800:])
    ap[base + lo:base + hi] = built[lo:hi]
    lfi.put("MUSIC.AP", bytes(ap))
    return r.stdout.strip()


# ------------------------------------------------------------------ data that goes with the tile

def edit_config(lfi):
    cfg = bytearray(lfi.get("CONFIG.BIN"))
    off, ln = struct.unpack_from("<II", cfg, 16 + 1 * 8)
    old = struct.pack("<HH9H", 0, len(STAGE3_MENU), *(STAGE3_MENU + [0] * (9 - len(STAGE3_MENU))))
    ids = [m[1] for m in MENU]
    patch_bytes(cfg, off, old, struct.pack("<HH9H", 0, len(ids), *(ids + [0] * (9 - len(ids)))), "CONFIG.BIN menu list")
    lfi.put("CONFIG.BIN", bytes(cfg))
    txt = bytearray(lfi.get("CONFIG.TXT"))
    i = txt.find(b"MAINMENU_AP_ID_ARRAY = 0[")
    j = txt.find(b";", i)
    if i >= 0 and j > i:
        new = ("MAINMENU_AP_ID_ARRAY = 0[%s]" % ", ".join(map(str, ids))).encode()
        k = j + 1
        while txt[k:k + 1] == b" ":
            k += 1                                   # padding left by the earlier edit
        if len(new) + 1 <= k - i:
            txt[i:k] = (new + b";").ljust(k - i)
            lfi.put("CONFIG.TXT", bytes(txt))


def menu_picture(sel):
    parts = []
    for i, (ic, _, _) in enumerate(MENU):
        x, y = 5 + (i % 3) * 41, 20 + (i // 3) * 46
        on = i == sel
        parts += [xd.rect(x, y, 36, 36, 10, T["accent"] if on else T["surface"]),
                  xd.icon(ic, x + 7, y + 7, 22, T["on_accent"] if on else T["text"])]
    return s1.svg(128, 144, parts)


def language_tables(sty):
    so, sc = struct.unpack_from("<IH", sty, 0x20)
    return [struct.unpack_from("<IIHHH", sty, so + k * 16) for k in range(sc)]


def read_strings(sty, table):
    off, ln, _, cnt, _ = table
    out = []
    for j in range(cnt):
        o, n = struct.unpack_from("<II", sty, off + j * 8)
        out.append(bytes(sty[o:o + n]))
    return out


def set_string(sty, table, index, text, donors):
    """Replace one string of a language. The table keeps its place and size; if the new text is longer,
    strings of entries that are not on the menu any more (donors) are emptied to make room."""
    off, ln, _, cnt, _ = table
    strings = read_strings(sty, table)
    strings[index] = text.encode("utf-16-le") + b"\0\0"
    room = ln - cnt * 8
    for d in donors:
        if sum(map(len, strings)) <= room:
            break
        strings[d] = b"\0\0"
    if sum(map(len, strings)) > room:
        return False
    pos = off + cnt * 8
    blob = bytearray(ln)
    for j, s in enumerate(strings):
        struct.pack_into("<II", blob, j * 8, pos, len(s))
        blob[pos - off:pos - off + len(s)] = s
        pos += len(s)
    sty[off:off + ln] = blob
    return True


def edit_mainmenu_resources(lfi, work):
    menu = bytearray(lfi.get("MAINMENU.STY"))
    for sel, (ic, _, pic) in enumerate(MENU):
        s1.set_picture(menu, pic, s1.render_565(menu_picture(sel), 128, 144, work, "menu6-%d-%s" % (sel, ic)), 128, 144)
    # label of entry 1: string 0 ("Alarm") becomes the music program's own word for Playlists in each language
    music = lfi.get("MUSIC.STY")
    theirs = {t[4]: read_strings(music, t)[0x48] for t in language_tables(music)}
    donors = [6, 24, 27, 26, 35, 4, 28, 15]          # Dictionary, Calculator, Stopwatch, Pedometer, wallpaper, ...
    done = 0
    for t in language_tables(menu):
        word = theirs.get(t[4], b"").decode("utf-16-le").split("\0")[0].strip() or "Playlists"
        if set_string(menu, t, 0, word[:1].upper() + word[1:], donors):
            done += 1
    lfi.put("MAINMENU.STY", bytes(menu))
    return done


def playlists_second(lfi):
    """In the music menus that start with "Now playing"/"Last played", move Playlists (text 0x48) to second place."""
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    moved = 0
    for i in range(n):
        eid, cnt, off, _ = struct.unpack_from("<HHII", mcg, hsz + i * 12)
        items = [bytes(mcg[off + k * 20:off + (k + 1) * 20]) for k in range(cnt)]
        texts = [struct.unpack_from("<H", it, 2)[0] for it in items]
        if cnt >= 6 and texts[1] == 0x0A and texts[0] != 0x48 and 0x48 in texts:
            items.insert(1, items.pop(texts.index(0x48)))
            mcg[off:off + cnt * 20] = b"".join(items)
            moved += 1
    lfi.put("MUSIC.MCG", bytes(mcg))
    return moved


# ------------------------------------------------------------------ playing screen

def hex565(color):
    r, g, b = (int(color[i:i + 2], 16) for i in (1, 3, 5))
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


def without_red(data, tint=None):
    """Remove the stock red glow: a pixel keeps only its neutral part. With tint, that part is drawn in the tint colour."""
    out = bytearray(len(data))
    tr, tg, tb = (int(tint[i:i + 2], 16) for i in (1, 3, 5)) if tint else (255, 255, 255)
    for i in range(0, len(data), 2):
        v = data[i] | data[i + 1] << 8
        r, g, b = (v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31
        m = max(g, b)
        if r > m:
            r = g = b = m
        if tint:
            m = max(r, g, b)
            m = 0 if m < 48 else m
            r, g, b = tr * m // 255, tg * m // 255, tb * m // 255
        struct.pack_into("<H", out, i, (r >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return bytes(out)


def line_picture(w, color):
    """Progress bar pieces are 6 pixels high with the line on rows 2 and 3."""
    c = hex565(color)
    return struct.pack("<%dH" % (w * 6), *([0] * (2 * w) + [c] * (2 * w) + [0] * (2 * w)))


def edit_playing_screen(lfi, work):
    sty = bytearray(lfi.get("MUSIC.STY"))
    po, pc = struct.unpack_from("<IH", sty, 0x10)
    for index in range(pc):
        data, w, h = s4.picture_bytes(sty, index)
        s1.set_picture(sty, index, without_red(data, T["accent"] if index <= 10 else None), w, h)
    put = lambda index, svg_text, w, h, name: s1.set_picture(sty, index, s1.render_565(svg_text, w, h, work, name), w, h)
    put(12, s1.svg(40, 40, [xd.rect(0, 0, 40, 40, 9, T["surface"]), xd.icon("music", 8, 8, 24, T["accent"])]), 40, 40, "cover-default")
    put(48, s4.status_icon("music", T["text"]), 20, 16, "status-music")
    put(68, s1.svg(6, 6, ['<circle cx="3" cy="3" r="2.800" fill="%s"/>' % T["text"]]), 6, 6, "progress-knob")
    for index, w, color in ((49, 128, T["line"]), (67, 128, T["line"]), (66, 1, T["line"]), (69, 6, T["line"]),
                            (65, 1, T["accent"]), (70, 6, T["accent"])):
        s1.set_picture(sty, index, line_picture(w, color), w, 6)
    lfi.put("MUSIC.STY", bytes(sty))
    return pc


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage5")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE4") or os.path.join(ROOT, "x91_dump", "stage4", "x91_lfi_stage4.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 4 image does not pass its checksums")

    print("music program patch:", patch_music(lfi, work))
    patch_mainmenu(lfi)
    edit_config(lfi)
    print("main menu: %d tiles; label set in %d languages" % (len(MENU), edit_mainmenu_resources(lfi, work)))
    print("music menu while playing: Playlists moved up in %d list(s)" % playlists_second(lfi))
    print("playing screen: %d pictures reworked" % edit_playing_screen(lfi, work))

    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage5.bin")
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
