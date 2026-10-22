#!/usr/bin/env python3
"""Render the current design's main screens for the documentation.

usage: make_screens.py [OUT_DIR]          (default design/screens/)

Reads each theme's latest build (x91_dump/themes/themes.json, then x91_dump/themes/<theme>/stageN/unpacked/) and
composes the screens the way the firmware draws them: pictures and layout records come from the image, positions of
what the firmware draws by code come from the stage builders (see the constants below and the firmware reference).
Song names, the cover and the book text are samples. Writes:

  berry.png    main menu, Music menu, a playlist, playing screen, screensaver (Berry)
  themes.png   main menu and playing screen in every theme
  reader.png   the eBook reader in landscape (Berry)
"""
import json
import math
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import cairo  # noqa: E402
import x91_preview as xp  # noqa: E402

THEMES = os.path.join(ROOT, "x91_dump", "themes")
W, H = 128, 160
COMMON = 0x8000                                  # bit 15 of a picture id: COMMON.STY

# Status bar (firmware/shared-code, stage 24): parts drawn with black transparent, at fixed places
CARD, BLUETOOTH, BATTERY = (0, 0, 204), (98, 0, 202), (108, 0, 192)   # no card, connected, full
CLOCK_X, CLOCK_Y, CLOCK_DIGITS, CLOCK_KEY = 22, 1, 135, 0x7bcf        # main menu clock (build_stage15)
# Playing screen (build_stage11)
BAR_Y, BAR_X, BAR_LEN = 132, 8, 106
COVER = (19, 19, 90)                             # 110 x 90 area at (9, 19), a square cover centred
# Screensaver clock (shared clock routine, clock_sprite.S)
SAVER_BG, SAVER_TIME, SAVER_COLON, SAVER_DATE, SAVER_DASH = 171, 158, 170, 147, 157
SPRITE = (36, 72, 221)
# eBook reader (build_stage16)
ROWS, ROW_H, TEXT_X, TEXT_W, PAGE_H = 7, 16, 4, 152, 116
EBAR_X, EBAR_LEN, EBAR_Y = 6, 104, 119
NUMBER = dict(x=120, y=112, w=36, h=16)

SONGS = ["Night Drive", "Paper Moon", "Slow Tides", "Orbit", "Late Bloom", "Glass Garden"]
BOOK = ("\"Christmas won't be Christmas without any presents,\" grumbled Jo, lying on the rug. "
        "\"It's so dreadful to be poor!\" sighed Meg, looking down at her old dress. "
        "\"I don't think it's fair for some girls to have plenty of pretty things, and other girls nothing at all,\" "
        "added little Amy, with an injured sniff.")


def to565(r, g, b):
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


class Screen(xp.Canvas):
    def __init__(self, fw, w=W, h=H):
        super().__init__(w, h)
        self.fw = fw

    def pic(self, sty, rid):
        return self.fw.picture(self.fw.sty[sty], rid)

    def put(self, x, y, sty, rid, mode="plain", key=0):
        """mode: plain, black (black is transparent), key (only pixels whose RGB565 value is above key)."""
        p = self.pic(sty, rid)
        if not p:
            return
        w, h, rgb = p
        if mode == "plain":
            self.blit(x, y, w, h, rgb)
            return
        for j in range(h):
            for i in range(w):
                k = (j * w + i) * 3
                v = to565(*rgb[k:k + 3])
                if (v != 0) if mode == "black" else (v > key):
                    xx, yy = x + i, y + j
                    if 0 <= xx < self.w and 0 <= yy < self.h:
                        o = (yy * self.w + xx) * 3
                        self.px[o:o + 3] = rgb[k:k + 3]

    def slice(self, x, y, w, h, sty, rid):
        """The part of a full-screen picture that lies at (x, y, w, h)."""
        pw, ph, rgb = self.pic(sty, rid)
        for j in range(h):
            src = ((y + j) * pw + x) * 3
            dst = ((y + j) * self.w + x) * 3
            self.px[dst:dst + w * 3] = rgb[src:src + w * 3]

    def write(self, x, y, s, color565, clip=None, align="left", width=0, font=None):
        font = font or self.fw.font16
        if align != "left":
            tw = font.text_width(s)
            x += (width - tw) // 2 if align == "centre" else width - tw
        self.text(font, x, y, s, xp.RGB[color565], clip)

    def digits(self, x, y, sty, first, text, widths, mode="black", key=0, extra=None):
        """A row of digit pictures: '0'..'9' are first + digit, other characters from `extra`."""
        for ch in text:
            if ch.isdigit():
                self.put(x, y, sty, first + int(ch), mode, key)
                x += widths[0]
            else:
                rid, w = extra[ch]
                self.put(x, y, sty, rid, mode, key)
                x += w

    def status_marks(self):
        for x, y, rid in (CARD, BLUETOOTH, BATTERY):
            self.put(x, y, "COMMON.STY", COMMON | rid, "black")

    def surface(self, scale):
        s = cairo.ImageSurface(cairo.FORMAT_RGB24, self.w, self.h)
        st, buf = s.get_stride(), s.get_data()
        for y in range(self.h):
            for x in range(self.w):
                i = (y * self.w + x) * 3
                buf[y * st + x * 4:y * st + x * 4 + 4] = bytes((self.px[i + 2], self.px[i + 1], self.px[i], 0))
        s.mark_dirty()
        big = cairo.ImageSurface(cairo.FORMAT_RGB24, self.w * scale, self.h * scale)
        c = cairo.Context(big)
        c.scale(scale, scale)
        c.set_source_surface(s, 0, 0)
        c.get_source().set_filter(cairo.FILTER_NEAREST)
        c.paint()
        return big


# ------------------------------------------------------------------ layout records

def tables(sty):
    d = sty.data if hasattr(sty, "data") else sty
    style = struct.unpack_from("<I", d, 8)[0]
    begin = struct.unpack_from("<I", d, style + 8)[0]
    return [struct.unpack_from("<II", d, begin + t * 8) for t in range(11)]


def raw(fw, name):
    return open(os.path.join(fw.folder, name), "rb").read()


ITEM = ("list_back head head_act head_x head_y back back_act back_x back_y tail tail_act tail_x tail_y "
        "data_x data_y data_w data_h color act_color attrib str_attrib reserve").split()


def list_style(fw, style_id):
    """COMMON.STY list-box record (SDK listbox_t) with its sub-records."""
    d = raw(fw, "COMMON.STY")
    off = tables(d)[6][0] + (style_id & 0xfff) * 28
    ta, sa, ia, ra = struct.unpack_from("<IIII", d, off)
    bid, bx, by = struct.unpack_from("<HHH", d, off + 16)
    rec = dict(back=(bid, bx, by), inc=d[off + 22], lines=d[off + 23], parts=d[off + 24])
    rec["title"] = struct.unpack_from("<6H", d, ta)
    rec["slider"] = struct.unpack_from("<8H", d, sa)
    rec["row"] = dict(zip(ITEM, struct.unpack_from("<22H", d, ia)))
    if ra != 0xffffffff:
        r = struct.unpack_from("<HHBBHHHHHHHHHHH", d, ra)
        rec["counter"] = dict(first=r[0], sep=r[1], dw=r[2], sw=r[3], bx=r[10], by=r[11], back=r[12], attrib=r[14])
    return rec


def menu(fw, program, index):
    """Title and rows (text, icon) of a menu list."""
    d = raw(fw, program + ".MCG")
    sty = fw.sty[program + ".STY"]
    hsz = struct.unpack_from("<H", d, 12)[0]
    tid, cnt, off, _ = struct.unpack_from("<HHII", d, hsz + index * 12)
    rows = [struct.unpack_from("<HHHH", d, off + k * 20) for k in range(cnt)]
    return fw.string(sty, tid, "English"), [(fw.string(sty, r[1], "English"), r[3]) for r in rows]


# ------------------------------------------------------------------ screens

def main_menu(fw, time="10:42"):
    sty = fw.sty["MAINMENU.STY"]
    scr = Screen(fw)
    uri, _ = fw.render_scene(sty, sty.scenes[0], "English")       # the Music tile, its label, the bar background
    scr.px = bytearray(decode_uri(uri))
    scr.digits(CLOCK_X, CLOCK_Y, "COMMON.STY", COMMON | CLOCK_DIGITS, time, (6,), "key", CLOCK_KEY,
               {":": (COMMON | (CLOCK_DIGITS + 10), 6)})
    scr.status_marks()
    return scr


def list_screen(fw, style_id, rows, active, title=None, total=None):
    """A list as the display driver draws it (firmware/display-driver, List boxes). rows: (text, icon number)."""
    rec = list_style(fw, style_id)
    scr = Screen(fw)
    bid, bx, by = rec["back"]
    scr.put(bx, by, "COMMON.STY", bid)
    r = rec["row"]
    for i, (text, icon) in enumerate(rows[:rec["lines"]]):
        dy = i * rec["inc"]
        on = i == active
        scr.slice(0, r["back_y"] + dy, W, rec["inc"], "COMMON.STY", r["list_back"])
        scr.put(r["back_x"], r["back_y"] + dy, "COMMON.STY", r["back_act"] if on else r["back"])
        if icon is not None:
            scr.put(r["head_x"], r["head_y"] + dy, "COMMON.STY", (r["head_act"] if on else r["head"]) + icon)
        x, y = r["data_x"], r["data_y"] + dy
        scr.write(x, y, text, r["act_color"] if on else r["color"], (x, y, x + r["data_w"], y + r["data_h"]))
    total = total or len(rows)
    if rec["parts"] & 4:                                           # scroll bar
        back, sx, sy, knob, _, kx, ky, length = rec["slider"]
        scr.put(sx, sy, "COMMON.STY", back)
        scr.put(kx, ky + (length * active // (total - 1) if total > 1 else 0), "COMMON.STY", knob)
    if rec["parts"] & 2 and title:                                 # title, in the status bar since stage 24
        x, y, w, h, color, attrib = rec["title"]
        scr.write(x, y, title, color, (x, y, x + w, y + h))
    if rec["parts"] & 8:                                           # counter in picture form (stage 24)
        c = rec["counter"]
        scr.put(c["bx"], c["by"], "COMMON.STY", c["back"])
        scr.digits(c["bx"], c["by"], "COMMON.STY", c["first"], "%d/%d" % (active + 1, total), (c["dw"],),
                   extra={"/": (c["sep"], c["sw"])})
    scr.status_marks()
    return scr


def cover_art(size):
    """A sample cover: dusk over hills."""
    s = cairo.ImageSurface(cairo.FORMAT_RGB24, size, size)
    c = cairo.Context(s)
    g = cairo.LinearGradient(0, 0, 0, size)
    for stop, rgb in ((0, (0.16, 0.12, 0.38)), (0.6, (0.62, 0.24, 0.45)), (1, (0.95, 0.55, 0.42))):
        g.add_color_stop_rgb(stop, *rgb)
    c.set_source(g)
    c.paint()
    c.set_source_rgb(1.0, 0.82, 0.55)
    c.arc(size * 0.62, size * 0.52, size * 0.17, 0, 6.2832)
    c.fill()
    for k, (rgb, top) in enumerate((((0.30, 0.13, 0.30), 0.64), ((0.17, 0.08, 0.20), 0.74), ((0.08, 0.05, 0.11), 0.85))):
        c.set_source_rgb(*rgb)
        c.move_to(0, size)
        for x in range(0, size + 1, 2):
            c.line_to(x, size * (top + 0.04 * math.sin(x / size * (5 + 2 * k) + k * 1.7)))
        c.line_to(size, size)
        c.close_path()
        c.fill()
    s.flush()
    st, buf = s.get_stride(), bytes(s.get_data())
    out = bytearray()
    for y in range(size):
        for x in range(size):
            b, g_, r, _ = buf[y * st + x * 4:y * st + x * 4 + 4]
            out += xp.RGB[to565(r, g_, b)]                         # as the panel shows it
    return size, size, bytes(out)


def playing(fw, title="Night Drive", elapsed=(1, 12), length=(3, 47), track=(3, 12)):
    """The playing screen: MUSIC.STY scene 0 and the routines of stages 11 and 14."""
    sty = fw.sty["MUSIC.STY"]
    d = raw(fw, "MUSIC.STY")
    t = tables(d)
    scr = Screen(fw)
    scr.put(0, 0, "MUSIC.STY", 45)                                 # background with the bar's music note
    x, y, size = COVER
    scr.blit(x, y, *cover_art(size))
    tb = struct.unpack_from("<10H", d, t[2][0])                    # text box 0: the title line
    scr.put(tb[5], tb[6], "MUSIC.STY", tb[7])
    scr.write(tb[1], tb[2], title, tb[8], (tb[1], tb[2], tb[1] + tb[3], tb[2] + tb[4]), "centre", tb[3])
    scr.put(0, BAR_Y, "MUSIC.STY", 67)                             # progress: track, played part, knob
    done = BAR_X + BAR_LEN * (elapsed[0] * 60 + elapsed[1]) // (length[0] * 60 + length[1])
    for xx in range(BAR_X, done):
        scr.put(xx, BAR_Y, "MUSIC.STY", 65)
    scr.put(done, BAR_Y, "MUSIC.STY", 68, "black")
    tm = struct.unpack_from("<18H", d, t[4][0] + 36)               # time box 1: elapsed/total
    scr.digits(tm[0], tm[1], "MUSIC.STY", tm[4], "%02d:%02d/%02d:%02d" % (elapsed + length), (6,), "plain",
               extra={":": (tm[5], 4), "/": (tm[6], 4)})
    pb = lambda i: struct.unpack_from("<16H", d, t[1][0] + i * 32)
    for box, frame in ((1, 2), (9, 0)):                            # play mode: repeat all; state: playing
        r = pb(box)
        scr.put(r[1], r[2], "MUSIC.STY", r[4 + frame])
    nb = struct.unpack_from("<14H", d, t[3][0])                    # number box 0: the track counter
    scr.put(nb[8], nb[9], "MUSIC.STY", nb[10])
    scr.digits(nb[0], nb[1], "MUSIC.STY", nb[4], "%d/%d" % track, (nb[6] & 0xff,),
               extra={"/": (nb[5], nb[6] >> 8)})
    scr.status_marks()
    return scr


def screensaver(fw, time="10:42", date="22-10-2026"):
    """The shared clock routine: background, time at y=18, date at y=43, an animation frame (key 0)."""
    scr = Screen(fw)
    scr.put(0, 0, "COMMON.STY", COMMON | SAVER_BG)
    scr.digits(32, 18, "COMMON.STY", COMMON | SAVER_TIME, time, (13,), "key", 0,
               {":": (COMMON | SAVER_COLON, 13)})
    scr.digits(19, 43, "COMMON.STY", COMMON | SAVER_DATE, date, (9,), "key", 0, {"-": (COMMON | SAVER_DASH, 9)})
    x, y, rid = SPRITE
    scr.put(x, y, "COMMON.STY", COMMON | rid, "key", 0)
    return scr


def reader(fw, page=37, progress=0.31):
    """The eBook reader in landscape, page colour 0 (paper)."""
    scr = Screen(fw, 160, 128)
    scr.put(0, 0, "EBOOK.STY", 0)
    scr.put(0, PAGE_H, "EBOOK.STY", 6)
    font = fw.font16
    lines = xp.wrap(font, BOOK, TEXT_W)[:ROWS]
    for k, line in enumerate(lines):
        scr.write(TEXT_X, k * ROW_H, line, 0)
    filled = int(EBAR_LEN * progress)
    for x in range(EBAR_X, EBAR_X + filled):
        scr.put(x, EBAR_Y, "EBOOK.STY", 44)
    d = raw(fw, "EBOOK.STY")
    nb = struct.unpack_from("<14H", d, tables(d)[3][0])            # number box 0: the page number as text
    scr.write(NUMBER["x"], NUMBER["y"], str(page), nb[11], align="right", width=NUMBER["w"])
    return scr


def decode_uri(uri):
    import base64
    import zlib
    data = base64.b64decode(uri.split(",", 1)[1])
    pos, idat = 8, b""
    while pos < len(data):
        n = struct.unpack(">I", data[pos:pos + 4])[0]
        if data[pos + 4:pos + 8] == b"IDAT":
            idat += data[pos + 8:pos + 8 + n]
        pos += 12 + n
    px = zlib.decompress(idat)
    return b"".join(px[y * (W * 3 + 1) + 1:(y + 1) * (W * 3 + 1)] for y in range(H))


# ------------------------------------------------------------------ sheets

BG, LABEL = (0.08, 0.08, 0.09), (0.62, 0.62, 0.66)


def sheet(path, columns, scale=2, gap=24, pad=24, labels=None):
    """columns: lists of screens, stacked top to bottom; labels: one per column."""
    cw = max(s.w for col in columns for s in col) * scale
    top = 34 if labels else 0
    ch = [sum(s.h * scale for s in col) + gap * (len(col) - 1) for col in columns]
    out = cairo.ImageSurface(cairo.FORMAT_RGB24, pad * 2 + len(columns) * cw + gap * (len(columns) - 1),
                             pad * 2 + top + max(ch))
    c = cairo.Context(out)
    c.set_source_rgb(*BG)
    c.paint()
    for k, col in enumerate(columns):
        x, y = pad + k * (cw + gap), pad + top
        if labels:
            c.select_font_face("Ubuntu", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
            c.set_font_size(17)
            ext = c.text_extents(labels[k])
            c.set_source_rgb(*LABEL)
            c.move_to(x + (cw - ext.width) / 2 - ext.x_bearing, pad + 16)
            c.show_text(labels[k])
        for s in col:
            c.set_source_surface(s.surface(scale), x + (cw - s.w * scale) // 2, y)
            c.paint()
            y += s.h * scale + gap
    out.write_to_png(path)
    print("wrote", os.path.relpath(path, ROOT))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(HERE, "screens")
    os.makedirs(out, exist_ok=True)
    themes = json.load(open(os.path.join(THEMES, "themes.json")))
    fws = {t["id"]: xp.Firmware(os.path.join(THEMES, t["id"], "stage%d" % t["stage"], "unpacked")) for t in themes}
    print("stage", ", ".join("%s %d" % (t["name"], t["stage"]) for t in themes))

    fw = fws["berry"]
    title, rows = menu(fw, "MUSIC", 0)
    music = list_screen(fw, 0x6002, rows, 0, title=title)
    songs = list_screen(fw, 0x6003, [(s, 2) for s in SONGS], 2, total=12)
    sheet(os.path.join(out, "berry.png"),
          [[main_menu(fw)], [music], [songs], [playing(fw)], [screensaver(fw)]])
    sheet(os.path.join(out, "themes.png"), [[main_menu(fws[t["id"]]), playing(fws[t["id"]])] for t in themes],
          labels=[t["name"] for t in themes])
    sheet(os.path.join(out, "reader.png"), [[reader(fw)]])


if __name__ == "__main__":
    main()
