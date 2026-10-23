"""The shared pictures (COMMON.STY) and the Bluetooth search animation (BT.STY).

Every picture keeps its size and its place. Status icons, battery and charging pictures, list marks, the selected
row, the scroll bar, file-type icons, numbered marks, the key lock, the battery notices, the hearing notice and the
volume pop-up are drawn anew in the theme; the 113 generic coloured icons and the leftover green and blue details are
turned neutral, keeping their shapes.
"""
import collections
import math
import struct

from . import base
from .base import T, fail, rgb, stroke, svg, xd

RED = "#ff4d4d"
FILE_ICON = ('<path d="M7 3.500h7l4 4V19a1.500 1.500 0 0 1-1.500 1.500h-9.500A1.500 1.500 0 0 1 5.500 19V5A1.500 1.500 0 0 1 7 3.500z'
             'M13.500 3.800V8h4" %s/>')
FILE_TYPES = ["file", "folder", "music", "video", "book", "picture"]      # order in which the firmware numbers them
VOLUME_SLIDER, VOLUME_PANEL = 5, 233             # slider record of the volume pop-up; its background (a free picture)


def arc(cx, cy, r, a0, a1, color, width):
    """Arc from angle a0 to a1 in degrees, clockwise, 0 = up."""
    p = lambda a: (cx + r * math.sin(math.radians(a)), cy - r * math.cos(math.radians(a)))
    (x0, y0), (x1, y1) = p(a0), p(a1)
    return '<path d="M%.2f %.2fA%g %g 0 %d 1 %.2f %.2f" %s/>' % (x0, y0, r, r, 1 if (a1 - a0) % 360 > 180 else 0, x1, y1,
                                                             stroke(color, width))


# ------------------------------------------------------------------ status bar, lists

def status_icon(name, color):
    """File-type mark, 20 x 16."""
    if name == "lock":
        return svg(20, 16, ['<rect x="5.5" y="7" width="9" height="7" rx="1.8" fill="%s"/>' % color,
                            '<path d="M7.3 7V5.4a2.700 2.700 0 0 1 5.400 0V7" %s/>' % stroke(color, 1.3)])
    return svg(20, 16, [xd.icon(name, 3, 1, 14, color, 1.6 if name == "settings" else 2.2)])


def battery(level, low=False):
    """Status-bar battery, 20 x 13; level 0 to 4."""
    c = RED if low else T["text"]
    parts = ['<rect x="1.600" y="2.600" width="14.800" height="7.800" rx="2.200" %s/>' % stroke(RED if low else T["text2"], 1.2),
             xd.rect(17.4, 5, 1.6, 3, 0.8, RED if low else T["text2"])]
    if low:
        parts.append(xd.rect(3.5, 4.5, 2, 4, 0.6, c))
    for i in range(0 if low else level):
        parts.append(xd.rect(3.5 + i * 2.9, 4.5, 2.2, 4, 0.6, c))
    return svg(20, 13, parts)


def charge_picture(level, bolt=False):
    """Charging animation, 50 x 34; level 0 to 4."""
    parts = ['<rect x="7" y="8" width="33" height="18" rx="5" %s/>' % stroke(T["text2"], 1.6),
             xd.rect(42, 13.5, 2.6, 7, 1.3, T["text2"])]
    for i in range(level):
        parts.append(xd.rect(10.5 + i * 6.7, 11.5, 5.2, 11, 1.6, T["accent"]))
    if bolt:
        parts.append('<path d="M25.500 9.500l-6 8.500h4.500l-1.500 6.500 6-8.500h-4.500z" fill="%s" stroke="%s" stroke-width="1.400" '
                     'stroke-linejoin="round"/>' % (T["text"], T["bg"]))
    return svg(50, 34, parts)


def row_picture(w):
    """Selected list row: a soft panel with the accent bar at the left."""
    return svg(w, 24, [xd.rect(1, 1.5, w - 3, 21, 6.5, T["surface"]), xd.rect(4, 6.5, 3, 11, 1.5, T["accent"])])


def tail(active):
    """Mark at the end of a list row, 16 x 24. On the selected row it also has to continue the row panel."""
    if not active:
        return svg(16, 24, ['<circle cx="7" cy="12" r="4" %s/>' % stroke(T["line"], 1.4)])
    return svg(16, 24, [xd.rect(-20, 1.5, 34, 21, 6.5, T["surface"]),
                        '<circle cx="7" cy="12" r="4" %s/>' % stroke(T["accent"], 1.4),
                        '<circle cx="7" cy="12" r="1.900" fill="%s"/>' % T["accent"]])


def scroll_bar(h, color):
    return svg(3, h, [xd.rect(1, 0, 1, h, 0, color)])


def glyph14(name, color):
    if name == "file":
        return '<g transform="scale(%.4f)">%s</g>' % (14 / 24.0, FILE_ICON % stroke(color, 2.3))
    return xd.icon(name, 0, 0, 14, color, 2.3)


def panel_under(hx, hy):
    """The piece of the selected-row panel that lies under an icon drawn at (hx, hy) within the row."""
    return '<g transform="translate(%d %d)">%s</g>' % (-hx, -hy, xd.rect(1, 1.5, 122, 21, 6.5, T["surface"]))


def list_icon(name, active):
    """Folder view, 14 x 14, one pixel down so it lines up with the text."""
    down = '<g transform="translate(0 1)">%s</g>' % glyph14(name, T["accent"] if active else T["text2"])
    return svg(14, 14, [panel_under(1, 5), down] if active else [down])


def number_mark(n, active):
    """Numbered mark, 14 x 13."""
    if active:
        return svg(14, 13, [panel_under(0, 4), '<circle cx="7" cy="6.500" r="6" fill="%s"/>' % T["accent"],
                            base.text(7, 10, str(n), 9.5, 700, T["on_accent"])])
    return svg(14, 13, ['<circle cx="7" cy="6.500" r="5.500" %s/>' % stroke(T["text2"], 1.1),
                        base.text(7, 10, str(n), 9.5, 500, T["text"])])


def neutral(data):
    """Stock green turned white and stock blue black, keeping each pixel's brightness."""
    out = bytearray(len(data))
    for i in range(0, len(data), 2):
        v = data[i] | data[i + 1] << 8
        r, g, b = (v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31
        hi, lo = max(r, g, b), min(r, g, b)
        if hi - lo > 40:
            if g == hi:                                   # green: a grey of the same strength
                y = min(255, hi + 30)
                r, g, b = y, y, y
            else:                                         # blue backgrounds
                r, g, b = 0, 0, 0
        struct.pack_into("<H", out, i, (r >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return bytes(out)


def neutral_tile(data):
    """A coloured icon tile with a white glyph becomes a dark tile with a light glyph."""
    px = [data[i] | data[i + 1] << 8 for i in range(0, len(data), 2)]
    to_rgb = lambda v: ((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31)
    cols = [to_rgb(v) for v in px]
    counts = collections.Counter(c for c in cols if max(c) > 60 and max(c) - min(c) > 40)
    if not counts:
        return data
    tile = counts.most_common(1)[0][0]
    lo = min(range(3), key=lambda i: tile[i])
    hi = max(range(3), key=lambda i: tile[i])
    tn, wn = rgb(T["raised"]), rgb(T["text"])
    out = bytearray(len(data))
    for k, c in enumerate(cols):
        if c[lo] > tile[lo] + 12:                                   # some white mixed in: part of the glyph
            a = min(1.0, (c[lo] - tile[lo]) / max(1, 255 - tile[lo]))
            b = 1.0
        else:                                                       # tile or its rounded edge
            a = 0.0
            b = min(1.0, c[hi] / max(1, tile[hi]))
        r, g, bl = (int(b * (tn[i] + a * (wn[i] - tn[i]))) for i in range(3))
        struct.pack_into("<H", out, k * 2, (r >> 3) << 11 | (g >> 2) << 5 | bl >> 3)
    return bytes(out)


# ------------------------------------------------------------------ lock, notices

def padlock(frame):
    """Key lock, 36 x 44, five frames from open to closed."""
    d = [7, 5, 3, 1, 0][frame]
    color = T["accent"] if frame == 4 else T["text"]
    top = 9 - d
    right_end = 21 - d * 1.3 if d else 21
    shackle = ('<path d="M11.500 21V%g a6.500 6.500 0 0 1 13 0V%g" %s/>' % (top + 6.5, right_end, stroke(color, 2.4)))
    return svg(36, 44, [shackle, xd.rect(6, 21, 24, 18, 4.5, color),
                        '<circle cx="18" cy="29" r="2.300" fill="%s"/>' % T["bg"],
                        xd.rect(17.1, 29, 1.8, 5, 0.9, T["bg"])])


def notice_panel():
    """Behind "Charged." and "Low battery...", 108 x 100: the firmware writes the text into the lower half and draws
    its own battery mark (pictures 248 and 322) on it."""
    return svg(108, 100, ['<rect x="1" y="1" width="106" height="98" rx="10" %s/>' % stroke(T["line"], 1.4)])


def battery_mark(low):
    """The battery the firmware puts on the notice panel, 31 x 19."""
    c = RED if low else T["accent"]
    return svg(31, 19, ['<rect x="1.200" y="1.200" width="25.600" height="16.600" rx="4.500" %s/>' % stroke(T["text2"], 1.6),
                        xd.rect(28, 6, 2.2, 7, 1.1, T["text2"]),
                        xd.rect(4.2, 4.2, 4.5 if low else 19.6, 10.6, 2, c)])


def hearing_notice():
    """Shown as a full-screen notice about loud listening; the stock picture has Chinese text."""
    return svg(128, 160, ['<rect x="10" y="26" width="108" height="108" rx="14" %s/>' % stroke(T["line"], 1.4),
                          xd.icon("speaker", 40, 44, 48, T["accent"], 1.8),
                          base.text(64, 112, "High volume", 12, 500, T["text"]),
                          base.text(64, 126, "can harm hearing", 10.5, 400, T["text2"])])


# ------------------------------------------------------------------ volume pop-up, brightness

def rows_picture(w, h, rows):
    """A picture given as one colour (or None for black) per row."""
    out = []
    for c in rows:
        out += [base.c565(c) if c else 0] * w
    return struct.pack("<%dH" % len(out), *out)


def speaker(muted):
    """18 x 16."""
    c = T["text2"] if muted else T["text"]
    parts = ['<path d="M2.500 6.200h2.600L8.600 3.300v9.400L5.100 9.800H2.500z" fill="%s" stroke="%s" stroke-width="1.200" '
             'stroke-linejoin="round"/>' % (c, c)]
    if muted:
        parts.append('<path d="M11.500 5.800l4 4.400M15.500 5.800l-4 4.400" %s/>' % stroke(T["text"], 1.5))
    else:
        parts.append('<path d="M11.300 5.600a3.400 3.400 0 0 1 0 4.800M13.600 3.600a6.200 6.200 0 0 1 0 8.800" %s/>' % stroke(c, 1.4))
    return svg(18, 16, parts)


def sun():
    """Brightness icon, 20 x 20."""
    rays = []
    for k in range(8):
        a = math.radians(k * 45)
        rays.append("M%.2f %.2fL%.2f %.2f" % (10 + 6.2 * math.cos(a), 10 + 6.2 * math.sin(a), 10 + 8.4 * math.cos(a), 10 + 8.4 * math.sin(a)))
    return svg(20, 20, ['<circle cx="10" cy="10" r="3.600" %s/>' % stroke(T["text"], 1.6),
                        '<path d="%s" %s/>' % ("".join(rays), stroke(T["text"], 1.6))])


def volume_panel():
    return svg(128, 160, ['<rect x="4.700" y="16.700" width="118.600" height="86.600" rx="12" %s/>' % stroke(T["line"], 1.4)])


def knob():
    return svg(8, 8, ['<circle cx="4" cy="4" r="3.600" fill="%s"/>' % T["text"]])


# ------------------------------------------------------------------ Bluetooth

def bt_spinner(frame):
    """Search animation, 48 x 48, six frames: three accent arcs turning 20 degrees per frame round the mark."""
    parts = ['<circle cx="24" cy="24" r="20" %s/>' % stroke(T["line"], 2.4)]
    for k in range(3):
        a = frame * 20 + k * 120
        parts.append(arc(24, 24, 20, a, a + 55, T["accent"], 2.4))
    parts.append(xd.icon("bluetooth", 13, 13, 22, T["text"], 2.0))
    return svg(48, 48, parts)


# ------------------------------------------------------------------ build

def selected_text_white(com):
    """Lists: selected text in white instead of the stock yellow (every list style's rows)."""
    style = struct.unpack_from("<I", com, 8)[0]
    begin = struct.unpack_from("<I", com, style + 8)[0]
    off, cnt = struct.unpack_from("<II", com, begin + 6 * 8)          # list controls
    changed = 0
    for k in range(cnt):
        item = struct.unpack_from("<I", com, off + k * 28 + 8)[0]
        if item and struct.unpack_from("<H", com, item + 18 * 2)[0] == 0xFFE0:
            struct.pack_into("<H", com, item + 18 * 2, 0xFFFF)
            changed += 1
    return changed


def volume_slider(com):
    """Slider record: four addresses, then background picture, x, y, icon picture, x, y, ...; its background was the
    shared black picture 185."""
    style = struct.unpack_from("<I", com, 8)[0]
    begin = struct.unpack_from("<I", com, style + 8)[0]
    table, count = struct.unpack_from("<II", com, begin + 9 * 8)
    rec = table + VOLUME_SLIDER * 48
    if count <= VOLUME_SLIDER or struct.unpack_from("<6H", com, rec + 16) != (0x8000 | 185, 0, 0, 0x8000 | 406, 45, 40):
        fail("COMMON.STY: the volume slider record is not the expected one")
    struct.pack_into("<H", com, rec + 16, 0x8000 | VOLUME_PANEL)


def build(b):
    work = b.folder("pictures")
    stock = b.stock_file("COMMON.STY")
    com = b.get("COMMON.STY")
    put = base.Pictures(com, work)

    # lists
    put.svg(292, row_picture(125), 125, 24, "row-125")
    put.svg(293, row_picture(140), 140, 24, "row-140")
    for index in range(295, 300):                          # the other "selected row" pictures, blue in the stock file
        put.svg(index, row_picture(125), 125, 24, "row-125")
    put.svg(290, tail(False), 16, 24, "tail")
    put.svg(291, tail(True), 16, 24, "tail-active")
    for index, h in ((310, 144), (311, 120), (312, 96), (313, 96)):
        put.svg(index, scroll_bar(h, T["line"]), 3, h, "scroll-track-%d" % h)
    put.svg(314, scroll_bar(79, T["text2"]), 3, 79, "scroll-thumb")
    put.svg(315, scroll_bar(79, T["line"]), 3, 79, "scroll-thumb-off")
    for k, name in enumerate(FILE_TYPES):                  # folder view: normal and selected
        put.svg(113 + k, list_icon(name, False), 14, 14, "list-%s" % name)
        put.svg(119 + k, list_icon(name, True), 14, 14, "list-%s-on" % name)
    for k in range(6):
        put.svg(251 + k, number_mark(k + 1, True), 14, 13, "mark-%d-on" % (k + 1))
        put.svg(257 + k, number_mark(k + 1, False), 14, 13, "mark-%d" % (k + 1))
    white = selected_text_white(com)

    # status bar and charging
    for index, name, color in ((174, "folder", T["text"]), (175, "folder", T["accent"]), (176, "lock", T["text"]),
                               (178, "music", T["text"]), (179, "picture", T["text"]), (180, "radio", T["text"]),
                               (181, "mic", T["text"]), (182, "settings", T["text"]), (183, "video", T["text"]),
                               (184, "video", T["accent"])):
        put.svg(index, status_icon(name, color), 20, 16, "status-%d-%s" % (index, name))
    for first in (188, 194):                               # two identical sets of six in the stock file
        for level in range(5):
            put.svg(first + level, battery(level), 20, 13, "battery-%d" % level)
        put.svg(first + 5, battery(0, low=True), 20, 13, "battery-low")
    for index, color in ((200, T["text"]), (202, T["accent"])):
        put.svg(index, svg(9, 13, [xd.icon("bluetooth", -2, 0, 13, color, 2.3)]), 9, 13, "bt-%d" % index)
    for level in range(5):
        put.svg(206 + level, charge_picture(level), 50, 34, "charge-%d" % level)
    put.svg(211, charge_picture(4, bolt=True), 50, 34, "charge-bolt")

    # neutral: generic coloured icons, leftover green and blue details (check marks, small folders)
    for index in range(113):
        data, w, h = base.picture_bytes(stock, index)
        put.raw(index, neutral_tile(data), w, h)
    for index in list(range(268, 279)) + list(range(283, 290)):
        data, w, h = base.picture_bytes(stock, index)
        put.raw(index, neutral(data), w, h)

    # key lock, notices
    for frame in range(5):
        put.svg(316 + frame, padlock(frame), 36, 44, "lock-%d" % frame)
    put.svg(247, notice_panel(), 108, 100, "notice-panel")
    put.svg(321, notice_panel(), 108, 100, "notice-panel")
    put.svg(248, battery_mark(False), 31, 19, "notice-battery")
    put.svg(322, battery_mark(True), 31, 19, "notice-battery-low")
    put.svg(416, hearing_notice(), 128, 160, "notice-hearing")

    # volume pop-up: a full-screen page with background, speaker icon and number at y=40, a 106-pixel bar with a knob
    # at y=80; brightness slider's sun
    put.svg(406, speaker(False), 18, 16, "volume-speaker")
    put.svg(384, speaker(True), 18, 16, "volume-mute")
    put.svg(359, knob(), 8, 8, "volume-knob")
    put.raw(360, rows_picture(8, 8, [None, None, None, T["line"], T["line"], None, None, None]), 8, 8)   # track behind the knob
    put.raw(333, rows_picture(106, 2, [T["line"]] * 2), 106, 2)           # track
    put.raw(353, rows_picture(1, 2, [T["accent"]] * 2), 1, 2)             # filled part
    put.raw(354, rows_picture(1, 2, [T["line"]] * 2), 1, 2)               # open part
    put.raw(358, rows_picture(1, 2, [T["line"]] * 2), 1, 2)
    put.svg(VOLUME_PANEL, volume_panel(), 128, 160, "volume-panel")
    put.svg(345, sun(), 20, 20, "brightness")
    put.svg(346, sun(), 20, 20, "brightness")
    volume_slider(com)
    b.put("COMMON.STY", com)

    bt = b.get("BT.STY")
    for frame in range(6):
        base.Pictures(bt, work).svg(1 + frame, bt_spinner(frame), 48, 48, "bt-search-%d" % frame)
    b.put("BT.STY", bt)
    b.note("shared pictures: %d redrawn or made neutral; selected list text white in %d styles; Bluetooth search", put.count, white)
