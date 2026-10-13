#!/usr/bin/env python3
"""Stage 1 of the Graphite design as real firmware pictures: start-up picture and main menu.

Pictures only: every picture keeps its size and its place, nothing else in the firmware changes.
The main menu keeps its nine entries; only their look changes.

usage: build_stage1.py [OUT_DIR]      (default: ../x91_dump/stage1)
"""
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import cairo  # noqa: E402
import x91_design as xd  # noqa: E402
import x91_modify as xm  # noqa: E402

# stock status icons sit on pure black, so stage 1 uses black as its background to avoid visible seams
THEME = os.environ.get("X91_THEME", "amber")     # amber, mint or ice
T = dict(xd.THEMES[THEME], bg="#000000")

# grid order of the stock main menu and the picture that shows each entry highlighted
GRID = [("music", 19), ("video", 25), ("radio", 21), ("picture", 20), ("bluetooth", 17), ("alarm", 16),
        ("folder", 18), ("mic", 22), ("settings", 23)]


def svg(w, h, parts):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">%s%s</svg>'
            % (w, h, w, h, xd.rect(0, 0, w, h, 0, T["bg"]), "".join(parts)))


def grid_picture(sel):
    parts = []
    for i, (ic, _) in enumerate(GRID):
        x, y = 7 + (i % 3) * 40, 4 + (i // 3) * 39
        on = i == sel
        parts += [xd.rect(x, y, 34, 34, 9.5, T["accent"] if on else T["surface"]),
                  xd.icon(ic, x + 7, y + 7, 20, T["on_accent"] if on else T["text"])]
    return svg(128, 144, parts)


def now_playing_entry():
    return svg(128, 120, [xd.rect(36, 34, 56, 56, 16, T["accent"]), xd.icon("play", 47, 45, 34, T["on_accent"])])


def boot_picture():
    return svg(128, 160, [
        xd.rect(46, 44, 36, 36, 10, T["accent"]), xd.icon("music", 53, 51, 22, T["on_accent"]),
        '<text x="64" y="107" font-family="Ubuntu" font-weight="700" font-size="17" letter-spacing="1.5" fill="%s" '
        'text-anchor="middle">X91</text>' % T["text"],
        xd.rect(54, 116, 20, 2, 1, T["line"]), xd.rect(54, 116, 9, 2, 1, T["accent"])])


def render_565(svg_text, w, h, work, name):
    src, png = os.path.join(work, name + ".svg"), os.path.join(work, name + ".png")
    with open(src, "w") as f:
        f.write(svg_text)
    r = subprocess.run(["vectorcraft-cli", "convert", src, png], capture_output=True, text=True, timeout=120)
    if r.returncode or not os.path.exists(png):
        sys.exit("render failed for %s: %s" % (name, (r.stdout + r.stderr)[-200:]))
    s = cairo.ImageSurface.create_from_png(png)
    if (s.get_width(), s.get_height()) != (w, h):
        sys.exit("%s rendered at %dx%d, expected %dx%d" % (name, s.get_width(), s.get_height(), w, h))
    rgb = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    c = cairo.Context(rgb)
    c.set_source_surface(s, 0, 0)
    c.paint()
    rgb.flush()
    d, stride = bytes(rgb.get_data()), rgb.get_stride()
    vals = []
    for y in range(h):
        row = d[y * stride:y * stride + w * 4]
        for x in range(w):
            b, g, r8 = row[x * 4], row[x * 4 + 1], row[x * 4 + 2]
            vals.append((r8 >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return struct.pack("<%dH" % len(vals), *vals)


def set_picture(sty, index, data, w, h):
    po = struct.unpack_from("<I", sty, 0x10)[0]
    off, ln, typ, pw, ph = struct.unpack_from("<IIHHH", sty, po + index * 16)
    if (pw, ph, ln) != (w, h, w * h * 2) or len(data) != ln:
        sys.exit("picture %d is %dx%d (%d bytes), new one is %dx%d (%d bytes)" % (index, pw, ph, ln, w, h, len(data)))
    sty[off:off + ln] = data


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage1")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    lfi = xm.Lfi(open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read())
    if lfi.check():
        sys.exit("the verified image does not pass its checksums")

    menu = bytearray(lfi.get("MAINMENU.STY"))
    for sel, (ic, pic) in enumerate(GRID):
        set_picture(menu, pic, render_565(grid_picture(sel), 128, 144, work, "menu-%d-%s" % (sel, ic)), 128, 144)
    black = lambda w, h: struct.pack("<%dH" % (w * h), *([0] * (w * h)))
    set_picture(menu, 5, black(128, 16), 128, 16)     # header strip
    set_picture(menu, 1, black(128, 20), 128, 20)     # label background
    set_picture(menu, 6, black(128, 20), 128, 20)     # second label background
    set_picture(menu, 8, render_565(now_playing_entry(), 128, 120, work, "menu-now-playing"), 128, 120)
    lfi.put("MAINMENU.STY", bytes(menu))

    logo = bytearray(lfi.get("LOGO.STY"))
    set_picture(logo, 0, render_565(boot_picture(), 128, 160, work, "boot"), 128, 160)
    lfi.put("LOGO.STY", bytes(logo))

    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage1.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    changed = sum(1 for i in range(0, len(stock), 512) if stock[i:i + 512] != lfi.d[i:i + 512])
    names = [n for n in lfi.entries if lfi.get(n) != stock[lfi.entries[n][1]:lfi.entries[n][1] + lfi.entries[n][2]]]
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s; sectors changed: %d of %d" % (bad or "none", len(stock) == len(lfi.d), changed, len(stock) // 512))
    print("  files changed:", ", ".join(sorted(names)))
    import hashlib
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
