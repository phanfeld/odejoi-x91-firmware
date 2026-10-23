"""The interface typeface (UNICODE.FON).

The firmware's 16-row bitmap font holds 65536 glyphs of 33 bytes: 16 rows of one byte (width up to 8) or two bytes
(width 9 to 16), most significant bit left, and the advance width in the last byte. The Latin, Greek and Cyrillic
glyphs are replaced with Ubuntu at 12 px rendered to one bit; glyphs that read badly at that size are drawn by hand.
Wide letters (M, W) use the two-byte row form, which the firmware reads correctly. Glyphs the typeface lacks (the
"missing" box) become copies of the drawn glyph that looks like them.
"""
from .base import cairo, fail

FAMILY, SIZE, BASELINE = "Ubuntu", 12, 13       # caps then sit on rows 4 to 12, as in the stock font
RANGES = [(0x21, 0x7E), (0xA1, 0xFF), (0x100, 0x17F), (0x384, 0x3CE), (0x400, 0x45F),
          (0x2010, 0x2026), (0x20AC, 0x20AC), (0x2122, 0x2122)]
G = 33                                           # bytes per glyph

# Glyphs drawn by hand where the automatic one-bit rendering reads badly at this size: the lowercase f looked like a
# capital F, S like 5, the digits were uneven, and M, N, O and Q had a doubled right-hand stroke. Capitals and digits
# occupy rows 5 to 12, ascenders start at row 4. Each entry: advance width, first row, rows as text ("#" = lit),
# starting at column 1. The digits are also the shapes of every pixel-drawn number (track counter, clocks).
HAND = {
    "f": (5, 4, ["..##", ".#..", ".#..", "###.", ".#..", ".#..", ".#..", ".#..", ".#.."]),
    "t": (5, 5, [".#..", ".#..", "###.", ".#..", ".#..", ".#..", ".#..", "..##"]),
    "S": (7, 5, [".###.", "#...#", "#....", ".###.", "....#", "....#", "#...#", ".###."]),
    "M": (9, 5, ["#.....#", "##...##", "#.#.#.#", "#..#..#", "#.....#", "#.....#", "#.....#", "#.....#"]),
    "N": (8, 5, ["#....#", "##...#", "#.#..#", "#.#..#", "#..#.#", "#..#.#", "#...##", "#....#"]),
    "O": (9, 5, [".#####.", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", ".#####."]),
    "Q": (9, 5, [".#####.", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", "#.....#", ".#####.", "....#..", ".....##"]),
    "0": (7, 5, [".###.", "#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."]),
    "1": (7, 5, ["..#..", ".##..", "..#..", "..#..", "..#..", "..#..", "..#..", ".###."]),
    "2": (7, 5, [".###.", "#...#", "....#", "...#.", "..#..", ".#...", "#....", "#####"]),
    "3": (7, 5, [".###.", "#...#", "....#", "..##.", "....#", "....#", "#...#", ".###."]),
    "4": (7, 5, ["...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#.", "...#."]),
    "5": (7, 5, ["#####", "#....", "#....", "####.", "....#", "....#", "#...#", ".###."]),
    "6": (7, 5, [".###.", "#...#", "#....", "####.", "#...#", "#...#", "#...#", ".###."]),
    "7": (7, 5, ["#####", "....#", "...#.", "...#.", "..#..", "..#..", ".#...", ".#..."]),
    "8": (7, 5, [".###.", "#...#", "#...#", ".###.", "#...#", "#...#", "#...#", ".###."]),
    "9": (7, 5, [".###.", "#...#", "#...#", "#...#", ".####", "....#", "#...#", ".###."]),
}

# Glyphs the typeface lacks, as copies of drawn ones (tags use some: "alt‐J" is written with U+2010 HYPHEN). Three
# unassigned Greek code points keep the box.
GLYPH_COPIES = {0x2010: 0x2D, 0x2011: 0x2D, 0x2012: 0x2013, 0x2016: 0x7C, 0x2017: 0x5F, 0x201B: 0x2018,
                0x201F: 0x201C, 0x2023: 0x2022, 0x2024: 0x2E, 0x2025: 0x2026, 0x0387: 0xB7}
BOX_KEPT = (0x038B, 0x038D, 0x03A2)


def hand_glyph(ch):
    width, top, pattern = HAND[ch]
    rows = [0] * 16
    for i, line in enumerate(pattern):
        for x, c in enumerate(line):
            if c == "#":
                rows[top + i] |= 0x8000 >> (x + 1)
    return width, rows


def tidy(rows):
    """Remove the single stray pixel that one-bit hinting leaves above or below a round stroke."""
    used = [y for y in range(16) if rows[y]]
    if len(used) < 4:
        return rows
    for edge, inner in ((used[0], used[0] + 1), (used[-1], used[-1] - 1)):
        bits = rows[edge]
        if bin(bits).count("1") == 1 and (rows[inner] & (bits << 1)) and (rows[inner] & (bits >> 1)) and (rows[inner] & bits):
            rows[edge] = 0
    return rows


def rasterise(ch):
    """One glyph as (width, rows) with rows as 16 integers, bit 15 = leftmost column; None if it does not fit."""
    if ch in HAND:
        return hand_glyph(ch)
    s = cairo.ImageSurface(cairo.FORMAT_RGB24, 24, 16)
    c = cairo.Context(s)
    fo = cairo.FontOptions()
    fo.set_antialias(cairo.ANTIALIAS_NONE)
    fo.set_hint_style(cairo.HINT_STYLE_FULL)
    fo.set_hint_metrics(cairo.HINT_METRICS_ON)
    c.set_font_options(fo)
    c.select_font_face(FAMILY, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
    c.set_font_size(SIZE)
    ext = c.text_extents(ch)
    pen = max(0, -int(round(ext.x_bearing)))
    c.set_source_rgb(1, 1, 1)
    c.move_to(pen, BASELINE)
    c.show_text(ch)
    s.flush()
    d, stride = bytes(s.get_data()), s.get_stride()
    rows, right = [], -1
    for y in range(16):
        bits = 0
        for x in range(16):
            if d[y * stride + x * 4 + 1] > 127:
                bits |= 0x8000 >> x
                right = max(right, x)
        if any(d[y * stride + x * 4 + 1] > 127 for x in range(16, 24)):
            return None                          # wider than the format allows
        rows.append(bits)
    if right < 0:
        return None
    rows = tidy(rows)
    width = max(int(round(ext.x_advance)) + pen, right + 2)   # keep at least one empty column after the ink
    if width > 16:
        return None
    return width, rows


def encode(width, rows):
    g = bytearray(G)
    for y, bits in enumerate(rows):
        if width <= 8:
            g[y] = bits >> 8
        else:
            g[2 * y], g[2 * y + 1] = bits >> 8, bits & 0xFF
    g[32] = width
    return bytes(g)


def build(b):
    font = b.get("UNICODE.FON")
    if len(font) < 65536 * G:
        fail("unexpected font file size")
    done, kept = 0, 0
    for lo, hi in RANGES:
        for cp in range(lo, hi + 1):
            if not any(font[cp * G:cp * G + 32]):
                continue                         # the stock font has no glyph here; leave it empty
            r = rasterise(chr(cp))
            if r is None:
                kept += 1
                continue
            font[cp * G:(cp + 1) * G] = encode(*r)
            done += 1
    box = bytes(font[0x2010 * G:(0x2010 + 1) * G])
    boxed = sorted(cp for cp in range(0x20, 0x10000) if font[cp * G:(cp + 1) * G] == box)
    if boxed != sorted(list(GLYPH_COPIES) + list(BOX_KEPT)):
        fail("UNICODE.FON: the glyphs drawn as boxes are not the expected ones: %s" % [hex(c) for c in boxed])
    for cp, src in GLYPH_COPIES.items():
        if font[src * G:(src + 1) * G] == box:
            fail("UNICODE.FON: U+%04X would be copied from a box" % cp)
        font[cp * G:(cp + 1) * G] = font[src * G:(src + 1) * G]
    b.put("UNICODE.FON", font)
    b.note("typeface: %d glyphs drawn, %d kept as stock, %d boxes replaced by look-alikes", done, kept, len(GLYPH_COPIES))
