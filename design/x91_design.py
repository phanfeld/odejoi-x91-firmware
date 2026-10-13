#!/usr/bin/env python3
"""Design generator for the X91's 128x160 screen.

Each screen is described once: a picture layer written as SVG (rendered by VectorCraft's command
line tool, so the same files open in VectorCraft for editing) and the texts the firmware would draw
on top. The texts are drawn here the way the player draws them: 1-bit glyphs in one colour. The
result is reduced to the display's 16-bit colour so the mock-ups show what the panel can show.

usage: x91_design.py OUT_DIR
"""
import os
import struct
import subprocess
import sys

import cairo

W, H = 128, 160
UI_FONT, UI_SIZE = "Ubuntu", 12      # proposed replacement for the stock 16-row bitmap font
NUM_FONT, NUM_SIZE = "Ubuntu", 10    # numbers are pictures in the firmware, so they may be smaller

THEMES = {
    "amber": dict(bg="#0b0d10", surface="#181c22", raised="#232830", line="#2b313a", text="#f2f4f7",
                  text2="#8d96a3", accent="#ffb000", on_accent="#0b0d10"),
    "mint": dict(bg="#0a0e0d", surface="#161d1b", raised="#202a27", line="#28332f", text="#f0f5f3",
                 text2="#869690", accent="#35e0a1", on_accent="#06110d"),
    "ice": dict(bg="#0a0c11", surface="#161a23", raised="#202634", line="#2a3040", text="#f1f4f9",
                text2="#8a93a6", accent="#5cb8ff", on_accent="#07101a"),
    "berry": dict(bg="#0d0a0b", surface="#1d171a", raised="#2a2126", line="#342a2f", text="#f6f1f3",
                  text2="#9a8b91", accent="#710630", on_accent="#f6f1f3"),      # a dark accent: what sits on it is light
}


# ---------------------------------------------------------------- icons (24 x 24 grid)

def icon(name, x, y, size, color, weight=2.0):
    s = size / 24.0
    st = 'fill="none" stroke="%s" stroke-width="%.2f" stroke-linecap="round" stroke-linejoin="round"' % (color, weight)
    fl = 'fill="%s"' % color
    body = {
        "music": '<path d="M9 17.5V6.6l10-2.4v11" %s/><path d="M9 6.6l10-2.4v3.2L9 9.8z" %s/>'
                 '<circle cx="6.6" cy="17.5" r="2.6" %s/><circle cx="16.6" cy="15.2" r="2.6" %s/>' % (st, fl, fl, fl),
        "playlist": '<path d="M4 6.5h12M4 11.5h12M4 16.5h6.5" %s/><path d="M15.5 13.2l5.5 3.3-5.5 3.3z" %s stroke="%s" '
                    'stroke-width="1.2" stroke-linejoin="round"/>' % (st, fl, color),
        "folder": '<path d="M3 8.2A2.2 2.2 0 0 1 5.2 6h3.6c.6 0 1.2.25 1.6.7L11.6 8h7.2A2.2 2.2 0 0 1 21 10.2v6.6'
                  'A2.2 2.2 0 0 1 18.8 19H5.2A2.2 2.2 0 0 1 3 16.8z" %s/>' % st,
        "bluetooth": '<path d="M7 7.6l9.4 8.8L12 20.8V3.2l4.4 4.4L7 16.4" %s/>' % st,
        "book": '<path d="M12 6.6C9.8 5.2 7 4.7 4 5.1v13c3-.4 5.8.1 8 1.5 2.2-1.4 5-1.900 8-1.5v-13c-3-.4-5.8.1-8 1.500z'
                'M12 6.6v13" %s/>' % st,
        "settings": '<path d="M4 7h8.500M17.500 7H20M4 12h2.500M11.500 12H20M4 17h9.500M18.500 17H20" %s/>'
                    '<circle cx="15" cy="7" r="2.3" %s/><circle cx="9" cy="12" r="2.3" %s/><circle cx="16" cy="17" r="2.3" %s/>'
                    % (st, st, st, st),
        "video": '<rect x="3" y="5.5" width="18" height="13" rx="2.6" %s/><path d="M10 9l5.2 3-5.2 3z" %s stroke="%s" '
                 'stroke-width="1.2" stroke-linejoin="round"/>' % (st, fl, color),
        "radio": '<rect x="3" y="9" width="18" height="11" rx="2.3" %s/><path d="M7 9l9-5" %s/>'
                 '<circle cx="8.4" cy="14.5" r="2.2" %s/><path d="M14 13h3.5M14 16h3.5" %s/>' % (st, st, st, st),
        "picture": '<rect x="3" y="5" width="18" height="14" rx="2.3" %s/><circle cx="8.3" cy="9.8" r="1.7" %s/>'
                   '<path d="M4.5 17l4.8-4.3 3.4 2.9 2.8-2.3 4 3.7" %s/>' % (st, fl, st),
        "alarm": '<circle cx="12" cy="13" r="7" %s/><path d="M12 9.4V13l2.6 1.7" %s/>'
                 '<path d="M4.4 6.6l3-2.6M19.6 6.6l-3-2.6" %s/>' % (st, st, st),
        "mic": '<rect x="9" y="3.4" width="6" height="10.6" rx="3" %s/>'
               '<path d="M6 11.6a6 6 0 0 0 12 0M12 17.6v3M9 20.6h6" %s/>' % (st, st),
        "play": '<path d="M8 5.5l11 6.5-11 6.500z" %s stroke="%s" stroke-width="1.500" stroke-linejoin="round"/>' % (fl, color),
        "pause": '<rect x="6.500" y="5" width="4" height="14" rx="1.200" %s/><rect x="13.500" y="5" width="4" height="14" rx="1.200" %s/>' % (fl, fl),
        "shuffle": '<path d="M3 7h3.500c2 0 3.200 1 4.300 2.800l2.400 4.400C14.300 16 15.500 17 17.500 17H21M3 17h3.500c1.300 0 2.300-.5 3.100-1.400'
                   'M21 7h-3.500c-1.300 0-2.300.5-3.100 1.400M18.500 4.500L21 7l-2.500 2.500M18.500 14.500L21 17l-2.500 2.500" %s/>' % st,
        "repeat": '<path d="M6 9.500V9a3 3 0 0 1 3-3h10M16.500 3.500L19 6l-2.500 2.500M18 14.500v.5a3 3 0 0 1-3 3H5M7.500 20.500L5 18l2.500-2.500" %s/>' % st,
        "chevron": '<path d="M9.500 6l6 6-6 6" %s/>' % st,
        "bars": '<rect x="5" y="10" width="3.200" height="9" rx="1" %s/><rect x="10.400" y="5" width="3.200" height="14" rx="1" %s/>'
                '<rect x="15.800" y="12" width="3.200" height="7" rx="1" %s/>' % (fl, fl, fl),
        "speaker": '<path d="M4 9.500h3.500L12 6v12l-4.500-3.500H4z" %s stroke="%s" stroke-width="1.500" stroke-linejoin="round"/>'
                   '<path d="M15.500 9a4.200 4.200 0 0 1 0 6M18 6.500a7.500 7.500 0 0 1 0 11" %s/>' % (fl, color, st),
    }[name]
    return '<g transform="translate(%.2f %.2f) scale(%.4f)">%s</g>' % (x, y, s, body)


def rect(x, y, w, h, r, fill, extra=""):
    return '<rect x="%g" y="%g" width="%g" height="%g" rx="%g" fill="%s" %s/>' % (x, y, w, h, r, fill, extra)


class Screen:
    def __init__(self, name, title, t):
        self.name, self.title, self.t = name, title, t
        self.svg = [rect(0, 0, W, H, 0, t["bg"])]
        self.texts = []      # (x, y_top, string, colour, role, align, width)
        self.notes = []

    def add(self, *parts):
        self.svg.extend(parts)

    def text(self, x, y, s, color=None, role="ui", align="L", width=None):
        self.texts.append((x, y, s, color or self.t["text"], role, align, width))

    def status(self, left="12:40", playing=False, bt=True):
        t = self.t
        self.text(5, 2, left, t["text2"], "num")
        x = 123 - 17
        self.add(rect(x, 5, 15, 7.500, 2, "none", 'stroke="%s" stroke-width="1"' % t["text2"]),
                 rect(x + 15.500, 7, 1.500, 3.500, .6, t["text2"]), rect(x + 1.500, 6.500, 9, 4.500, 1, t["text"]))
        if bt:
            self.add(icon("bluetooth", x - 12, 3.500, 10, t["accent"], 2.400))
        if playing:
            self.add(icon("play", x - (24 if bt else 12), 3.500, 10, t["text2"]))

    def svg_doc(self, with_text=False):
        body = list(self.svg)
        if with_text:
            for x, y, s, color, role, align, width in self.texts:
                size = UI_SIZE if role == "ui" else NUM_SIZE
                anchor = {"L": "start", "C": "middle", "R": "end"}[align]
                ax = x + (width or 0) / 2 if align == "C" else x + (width or 0) if align == "R" else x
                body.append('<text x="%g" y="%g" font-family="%s" font-size="%d" fill="%s" text-anchor="%s">%s</text>'
                            % (ax, y + (12 if role == "ui" else 9), UI_FONT, size, color, anchor,
                               s.replace("&", "&amp;").replace("<", "&lt;")))
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">%s</svg>'
                % (W, H, W, H, "".join(body)))


# ---------------------------------------------------------------- screens

MENU = [("music", "Music"), ("playlist", "Playlists"), ("folder", "Folder"),
        ("bluetooth", "Bluetooth"), ("book", "eBook"), ("settings", "Settings")]


def main_grid(t, sel=0, name="main-grid"):
    s = Screen(name, "Main menu, grid", t)
    s.status()
    for i, (ic, label) in enumerate(MENU):
        x, y = 5 + (i % 3) * 41, 36 + (i // 3) * 46
        on = i == sel
        s.add(rect(x, y, 36, 36, 10, t["accent"] if on else t["surface"]),
              icon(ic, x + 7, y + 7, 22, t["on_accent"] if on else t["text"]))
    s.text(2, 134, MENU[sel][1], t["text"], "ui", "C", 124)
    s.notes = ["Six full-screen pictures, one per highlighted entry.",
               "The label is the firmware's own text box; only its position moves."]
    return s


def main_focus(t, sel=1):
    s = Screen("main-focus", "Main menu, one at a time", t)
    s.status()
    ic, label = MENU[sel]
    s.add(rect(-22, 48, 40, 40, 11, t["surface"]), icon(MENU[sel - 1][0], -22 + 9, 57, 22, t["text2"]),
          rect(110, 48, 40, 40, 11, t["surface"]), icon(MENU[sel + 1][0], 119, 57, 22, t["text2"]),
          rect(32, 36, 64, 64, 18, t["accent"]), icon(ic, 32 + 12, 48, 40, t["on_accent"], 1.900))
    for i in range(len(MENU)):
        on = i == sel
        s.add(rect(64 - 27 + i * 9 + (0 if on else 1.500), 112 + (0 if on else 1), 6 if on else 3, 3 if on else 2, 1.500,
                   t["accent"] if on else t["line"]))
    s.text(2, 124, label, t["text"], "ui", "C", 124)
    s.notes = ["Uses the firmware's existing single-entry menu style; left and right step through the entries."]
    return s


def list_screen(t, name, title, rows, sel=0, values=None, chevrons=True, playing=None):
    s = Screen(name, title, t)
    s.status(left=title, playing=playing is not None)
    for i, label in enumerate(rows[:6]):
        y = 18 + i * 23.500
        on = i == sel
        if on:
            s.add(rect(3, y, 122, 21, 6.500, t["surface"]), rect(7, y + 5, 3, 11, 1.500, t["accent"]))
        if playing == i:
            s.add(icon("bars", 104, y + 3.500, 14, t["accent"]))
        elif values:
            s.text(70, y + 3, values[i], t["text2"], "ui", "R", 50)
        elif chevrons:
            s.add(icon("chevron", 111, y + 4.500, 12, t["text2"] if not on else t["text"], 2.400))
        s.text(15, y + 3, label, t["text"] if on else "#c4cad3", "ui", "L", 86 if (values or playing == i) else 94)
    if len(rows) > 6:
        s.add(rect(126, 20, 1.500, 136, .75, t["line"]), rect(126, 20, 1.500, 136 * 6 / len(rows), .75, t["text2"]))
    s.notes = ["List rows are two background pictures (normal and selected) plus text colours in the layout table."]
    return s


def cover(x, y, size, r, t):
    cid = "c%d" % x
    return ('<defs><clipPath id="%s"><rect x="%g" y="%g" width="%g" height="%g" rx="%g"/></clipPath>'
            '<linearGradient id="g%s" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#2b1d52"/>'
            '<stop offset="1" stop-color="#0f4c5c"/></linearGradient></defs>'
            '<g clip-path="url(#%s)"><rect x="%g" y="%g" width="%g" height="%g" fill="url(#g%s)"/>'
            '<circle cx="%g" cy="%g" r="%g" fill="#ff7a59"/><circle cx="%g" cy="%g" r="%g" fill="#ffd166" opacity=".9"/>'
            '<path d="M%g %g q%g -%g %g 0 t%g 0 v%g h-%g z" fill="#0b132b" opacity=".85"/></g>'
            % (cid, x, y, size, size, r, cid, cid, x, y, size, size, cid,
               x + size * .68, y + size * .36, size * .26, x + size * .3, y + size * .3, size * .1,
               x, y + size * .74, size * .25, size * .16, size * .5, size * .5, size * .3, size))


def now_playing(t):
    s = Screen("now-playing", "Now playing", t)
    s.status(left="12/186", playing=True)
    s.add(cover(29, 20, 70, 7, t))
    s.text(6, 93, "One More Time", t["text"], "ui", "C", 116)
    s.text(6, 108, "Daft Punk", t["text2"], "ui", "C", 116)
    s.add(rect(10, 131, 108, 3, 1.500, t["line"]), rect(10, 131, 45, 3, 1.500, t["accent"]),
          '<circle cx="55" cy="132.500" r="3.200" fill="%s"/>' % t["text"])
    s.text(10, 140, "2:13", t["text2"], "num")
    s.text(88, 140, "5:20", t["text2"], "num", "R", 30)
    s.add(icon("shuffle", 48, 140, 12, t["accent"], 2.200), icon("repeat", 68, 140, 12, t["text2"], 2.200))
    s.notes = ["Background picture, progress bar pictures and digit pictures are redrawn; positions come from the layout table.",
               "The cover comes from the file's tag. Its real size and position on this firmware still have to be read from the layout."]
    return s


def volume(t):
    s = now_playing(t)
    s.name, s.title = "volume", "Volume"
    s.add(rect(0, 0, W, H, 0, "#000000", 'opacity=".55"'), rect(10, 58, 108, 44, 10, t["raised"]),
          icon("speaker", 17, 71, 18, t["text"]), rect(42, 78.500, 52, 4, 2, t["line"]), rect(42, 78.500, 31, 4, 2, t["accent"]))
    s.texts = [x for x in s.texts if x[1] < 16]
    s.text(96, 73, "19", t["text"], "ui", "R", 16)
    s.notes = ["The volume bar is a set of pictures in the common resource file."]
    return s


def bluetooth(t):
    s = Screen("bluetooth", "Bluetooth", t)
    s.status(left="Bluetooth")
    s.add('<circle cx="64" cy="52" r="22" fill="none" stroke="%s" stroke-width="1.500"/>' % t["line"],
          '<circle cx="64" cy="52" r="15" fill="%s"/>' % t["accent"], icon("bluetooth", 54, 42, 20, t["on_accent"], 2.200))
    s.text(6, 82, "Searching ...", t["text2"], "ui", "C", 116)
    for i, (label, on) in enumerate([("WH-1000XM4", True), ("JBL Flip 6", False)]):
        y = 104 + i * 23.500
        if on:
            s.add(rect(3, y, 122, 21, 6.500, t["surface"]), rect(7, y + 5, 3, 11, 1.500, t["accent"]))
        s.text(15, y + 3, label, t["text"] if on else "#c4cad3", "ui", "L", 100)
    s.notes = ["The animated search picture has six frames; each is redrawn."]
    return s


def boot(t):
    s = Screen("boot", "Start-up picture", t)
    s.add(rect(46, 44, 36, 36, 10, t["accent"]), icon("music", 53, 51, 22, t["on_accent"]),
          '<text x="64" y="107" font-family="Ubuntu" font-weight="700" font-size="17" letter-spacing="1.500" fill="%s" '
          'text-anchor="middle">X91</text>' % t["text"],
          rect(54, 116, 20, 2, 1, t["line"]), rect(54, 116, 9, 2, 1, t["accent"]))
    s.notes = ["One picture. Being a picture, its lettering can be smooth, unlike the firmware's own text."]
    return s


def build_screens(t):
    return [
        boot(t), main_grid(t, 0), main_grid(t, 1, "main-grid-2"), main_focus(t),
        list_screen(t, "music-menu", "Music", ["Playlists", "Artists", "Albums", "Genres", "All songs", "Shuffle all"], 0),
        list_screen(t, "playlist", "Focus", ["01 - 4-30", "09 - Miami Showdown", "01 - Highway", "02 - 07-41 The Beginn",
                                             "10 - 0-59", "03 - Black Magic", "x", "x", "x", "x"], 1, chevrons=False, playing=1),
        now_playing(t), volume(t), bluetooth(t),
        list_screen(t, "settings", "Settings", ["Language", "Backlight", "Sleep timer", "Equalizer", "Repeat", "Information"],
                    2, values=["English", "30 s", "Off", "Off", "All", ""], chevrons=False),
    ]


# ---------------------------------------------------------------- rendering

FO = cairo.FontOptions()
FO.set_antialias(cairo.ANTIALIAS_NONE)
FO.set_hint_style(cairo.HINT_STYLE_FULL)
FO.set_hint_metrics(cairo.HINT_METRICS_ON)


def hex_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))


def draw_texts(surface, texts):
    c = cairo.Context(surface)
    c.set_font_options(FO)
    for x, y, s, color, role, align, width in texts:
        c.select_font_face(UI_FONT if role == "ui" else NUM_FONT, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        c.set_font_size(UI_SIZE if role == "ui" else NUM_SIZE)
        adv = c.text_extents(s).x_advance
        if width and adv > width:               # the firmware clips (or scrolls) text to its box
            while s and c.text_extents(s + "…").x_advance > width:
                s = s[:-1]
            s += "…"
            adv = c.text_extents(s).x_advance
        tx = x + (width - adv) / 2 if align == "C" else x + width - adv if align == "R" else x
        c.set_source_rgb(*hex_rgb(color))
        c.move_to(round(tx), y + (12 if role == "ui" else 9))
        c.show_text(s)


def to_rgb565_look(surface):
    """Reduce to 5-6-5 bits per channel in place, as the panel receives it."""
    surface.flush()
    data = surface.get_data()
    stride = surface.get_stride()
    for yy in range(surface.get_height()):
        row = yy * stride
        for xx in range(surface.get_width()):
            i = row + xx * 4
            b, g, r = data[i], data[i + 1], data[i + 2]
            r5, g6, b5 = r >> 3, g >> 2, b >> 3
            data[i], data[i + 1], data[i + 2] = b5 * 255 // 31, g6 * 255 // 63, r5 * 255 // 31
    surface.mark_dirty()


def scaled(surface, k):
    out = cairo.ImageSurface(cairo.FORMAT_RGB24, surface.get_width() * k, surface.get_height() * k)
    c = cairo.Context(out)
    c.scale(k, k)
    c.set_source_surface(surface, 0, 0)
    c.get_source().set_filter(cairo.FILTER_NEAREST)
    c.paint()
    return out


def render(screen, out_dir, tag):
    src = os.path.join(out_dir, "src", "%s-%s.svg" % (tag, screen.name))
    pic = os.path.join(out_dir, "pictures", "%s-%s.png" % (tag, screen.name))
    with open(src, "w") as f:
        f.write(screen.svg_doc(with_text=True))
    tmp = os.path.join(out_dir, "pictures", "_layer.svg")
    with open(tmp, "w") as f:
        f.write(screen.svg_doc(with_text=False))
    r = subprocess.run(["vectorcraft-cli", "convert", tmp, pic], capture_output=True, text=True, timeout=120)
    if r.returncode or not os.path.exists(pic):
        sys.exit("VectorCraft could not render %s: %s" % (screen.name, (r.stdout + r.stderr)[-300:]))
    os.remove(tmp)
    layer = cairo.ImageSurface.create_from_png(pic)
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W, H)
    c = cairo.Context(surf)
    c.set_source_surface(layer, 0, 0)
    c.paint()
    draw_texts(surf, screen.texts)
    to_rgb565_look(surf)
    mock = os.path.join(out_dir, "mock", "%s-%s.png" % (tag, screen.name))
    scaled(surf, 4).write_to_png(mock)
    return mock


def main():
    out = os.path.abspath(sys.argv[1])
    for d in ("src", "pictures", "mock"):
        os.makedirs(os.path.join(out, d), exist_ok=True)
    made = {}
    for tag, t in THEMES.items():
        screens = build_screens(t) if tag == "amber" else [main_grid(t, 0), now_playing(t)]
        for s in screens:
            made[(tag, s.name)] = (render(s, out, tag), s)
            print("rendered", tag, s.name)
    return made


if __name__ == "__main__":
    main()
