#!/usr/bin/env python3
"""Pictures of what the search screen (search.c) draws, from the host test's draw log.

The host test writes every fill, string and picture the search asks the display driver for into the file named by
SEARCH_SCREENS, with "snapshot N" where a test marks a moment. This replays the log on a 128 x 160 screen with the
player's own typeface (UNICODE.FON of a firmware image) and writes snapshot-N.png for each mark. The driver's text
rules are followed as far as they are known: a region 16 rows high, alignment within its width, characters that do
not fit left out (or an ellipsis), a strip as wide as the text and 16 rows high painted in the background colour
first (fill mode 1). The status bar's marks (battery, card, Bluetooth) are the firmware's own drawing and are not in
the log.

usage: render.py IMAGE DRAW_LOG OUT_DIR [SCALE]
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "firmware_analysis", "tools"))
import x91_modify as xm  # noqa: E402

W, H = 128, 160
CENTRE, RIGHT, ELLIPSIS = 1 << 2, 2 << 2, 3 << 4


def rgb(v):
    return ((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31)


class Screen:
    def __init__(self, font):
        self.font = font
        self.px = [[(0, 0, 0)] * W for _ in range(H)]

    def fill(self, x, y, w, h, colour):
        for yy in range(y, min(y + h, H)):
            for xx in range(x, min(x + w, W)):
                self.px[yy][xx] = rgb(colour)

    def advance(self, ch):
        return self.font[ord(ch) * 33 + 32]

    def glyph(self, ch, x, y, colour):
        g = self.font[ord(ch) * 33:ord(ch) * 33 + 33]
        wide = g[32] > 8
        for row in range(16):
            bits = (g[2 * row] << 8 | g[2 * row + 1]) if wide else g[row] << 8
            for col in range(16):
                if bits & 0x8000 >> col and 0 <= x + col < W and 0 <= y + row < H:
                    self.px[y + row][x + col] = rgb(colour)

    def text(self, x, y, w, colour, back, mode, s):
        width = sum(self.advance(c) for c in s)
        if width > w and mode & 0xf0:
            tail = "…" if mode & 0xf0 == ELLIPSIS else ""
            room = w - sum(self.advance(c) for c in tail)
            while s and sum(self.advance(c) for c in s) > room:
                s = s[:-1]
            s += tail
            width = sum(self.advance(c) for c in s)
        x += (w - width) // 2 if mode & 0xc == CENTRE else w - width if mode & 0xc == RIGHT else 0
        self.fill(x, y, width, 16, back)
        for c in s:
            self.glyph(c, x, y, colour)
            x += self.advance(c)

    def save(self, path, scale):
        import cairo
        surf = cairo.ImageSurface(cairo.FORMAT_RGB24, W * scale, H * scale)
        ctx = cairo.Context(surf)
        for y in range(H):
            for x in range(W):
                r, g, b = self.px[y][x]
                ctx.set_source_rgb(r / 255, g / 255, b / 255)
                ctx.rectangle(x * scale, y * scale, scale, scale)
                ctx.fill()
        surf.write_to_png(path)


def decode(lang, hexs):
    raw = bytes.fromhex(hexs)
    if lang == 0x7d:
        units = struct.unpack("<%dH" % (len(raw) // 2), raw)
        return "".join(chr(u) for u in units if u != 0xfeff)
    if raw[:3] == b"\xef\xbb\xbf":
        return raw[3:].decode("utf-8", "replace")
    return raw.decode("cp1252", "replace")


def main():
    image, log, out = sys.argv[1:4]
    scale = int(sys.argv[4]) if len(sys.argv) > 4 else 3
    font = xm.Lfi(open(image, "rb").read()).get("UNICODE.FON")
    os.makedirs(out, exist_ok=True)
    screen = Screen(font)
    made = []
    for line in open(log):
        f = line.split()
        if f[0] == "fill":
            screen.fill(*(int(v, 0) for v in f[1:6]))
        elif f[0] == "text":
            x, y, w, h, colour, back, mode, lang = (int(v, 0) for v in f[1:9])
            screen.text(x, y, w, colour, back, mode, decode(lang & 0xff, f[9] if len(f) > 9 else ""))
        elif f[0] == "picture":
            if int(f[1], 0) == 0x8000 | 127:                   # COMMON.STY 127: the status bar's middle, black
                screen.fill(int(f[2]), int(f[3]), 81, 16, 0)
        elif f[0] == "snapshot":
            path = os.path.join(out, "snapshot-%s.png" % f[1])
            screen.save(path, scale)
            made.append(path)
    print("\n".join(made))


if __name__ == "__main__":
    main()
