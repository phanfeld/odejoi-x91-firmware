#!/usr/bin/env python3
"""Build a modified X91 firmware image with a custom start-up picture. Works on files only.

The start-up picture exists twice: in the firmware area (LOGO.STY, picture 0) and in the boot
record (the "welcome" picture the boot loader shows first). This tool replaces both in copies of
the dump and fixes the firmware checksums. Nothing is sent to a player.

usage: x91_modify.py --lfi x91_lfi_verified.bin --brec brec0.bin --out-dir custom
                     [--png picture.png | --text "X91" --subtext "custom boot"]
"""
import argparse
import hashlib
import os
import struct
import sys
import zlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import x91_preview as xp  # noqa: E402

W, H = 128, 160


def sum16(b):
    return sum(struct.unpack("<%dH" % (len(b) // 2), b[:len(b) & ~1])) & 0xffff


def sum32(b):
    return sum(struct.unpack("<%dI" % (len(b) // 4), b[:len(b) & ~3])) & 0xffffffff


# ---------------------------------------------------------------- pictures

def read_png(path):
    """Minimal PNG reader: 8-bit grey, RGB, palette or RGBA, not interlaced. Returns (w, h, rgb)."""
    d = open(path, "rb").read()
    if d[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, idat, pal = 8, b"", None
    while pos < len(d):
        n, typ = struct.unpack_from(">I4s", d, pos)
        body = d[pos + 8:pos + 8 + n]
        if typ == b"IHDR":
            w, h, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif typ == b"PLTE":
            pal = body
        elif typ == b"IDAT":
            idat += body
        pos += 12 + n
    if depth != 8 or interlace:
        raise ValueError("only 8-bit, non-interlaced PNG files are supported")
    ch = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    raw = zlib.decompress(idat)
    stride = w * ch
    rows, prev = [], bytearray(stride)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        cur = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = cur[i - ch] if i >= ch else 0
            b = prev[i]
            c = prev[i - ch] if i >= ch else 0
            if ft == 1:
                cur[i] = (cur[i] + a) & 255
            elif ft == 2:
                cur[i] = (cur[i] + b) & 255
            elif ft == 3:
                cur[i] = (cur[i] + (a + b) // 2) & 255
            elif ft == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                cur[i] = (cur[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        rows.append(cur)
        prev = cur
    rgb = bytearray()
    for cur in rows:
        for x in range(w):
            px = cur[x * ch:(x + 1) * ch]
            if ctype == 0:
                rgb += bytes((px[0],) * 3)
            elif ctype == 2:
                rgb += px
            elif ctype == 3:
                rgb += pal[px[0] * 3:px[0] * 3 + 3]
            elif ctype == 4:  # grey + alpha, blended on black
                v = px[0] * px[1] // 255
                rgb += bytes((v, v, v))
            else:  # RGBA, blended on black
                rgb += bytes(c * px[3] // 255 for c in px[:3])
    return w, h, bytes(rgb)


def fit(w, h, rgb):
    """Scale to cover 128x160 (nearest neighbour) and crop the centre."""
    scale = max(W / w, H / h)
    sw, sh = max(int(round(w * scale)), W), max(int(round(h * scale)), H)
    x0, y0 = (sw - W) // 2, (sh - H) // 2
    out = bytearray()
    for y in range(H):
        sy = min(int((y + y0) / scale), h - 1)
        for x in range(W):
            sx = min(int((x + x0) / scale), w - 1)
            out += rgb[(sy * w + sx) * 3:(sy * w + sx) * 3 + 3]
    return bytes(out)


def text_mask(font, s, scale):
    """Set of lit pixels for a text line, scaled by an integer factor."""
    pts, x = set(), 0
    for c in s:
        width, rows = font.glyph(ord(c))
        for r, row in enumerate(rows):
            for b in range(width):
                if b // 8 < len(row) and row[b // 8] >> (7 - b % 8) & 1:
                    for dy in range(scale):
                        for dx in range(scale):
                            pts.add(((x + b) * scale + dx, r * scale + dy))
        x += width
    return pts, x * scale, font.rows * scale


def text_card(folder, line1, line2):
    """A simple start-up card in the style of the original: white lettering with a faded reflection."""
    big = xp.Font(os.path.join(folder, "UNICODEL.FON"), 24)
    small = xp.Font(os.path.join(folder, "UNICODE.FON"), 16)
    cv = xp.Canvas(W, H)
    scale = 2
    pts, tw, th = text_mask(big, line1, scale)
    while tw > W - 8 and scale > 1:
        scale -= 1
        pts, tw, th = text_mask(big, line1, scale)
    ys = [y for _, y in pts] or [0]
    top, bottom = min(ys), max(ys)
    x0, y0 = (W - tw) // 2, 58 - (bottom - top)
    for x, y in pts:
        px, py = x0 + x, y0 + y - top
        if 0 <= px < W and 0 <= py < H:
            cv.px[(py * W + px) * 3:(py * W + px) * 3 + 3] = b"\xff\xff\xff"
        # mirrored, fading reflection below the baseline
        d = bottom - y
        ry = y0 + (bottom - top) + 3 + d
        fade = max(120 - d * 5, 0)
        if fade and 0 <= px < W and 0 <= ry < H:
            cv.px[(ry * W + px) * 3:(ry * W + px) * 3 + 3] = bytes((fade // 4, fade, fade))
    cv.fill(24, 104, 80, 1, (0, 150, 150))
    if line2:
        cv.text(small, (W - small.text_width(line2)) // 2, 112, line2, bytes((190, 190, 190)))
    return bytes(cv.px)


def rgb_to_565(rgb, big_endian=False):
    vals = [(rgb[i] >> 3) << 11 | (rgb[i + 1] >> 2) << 5 | rgb[i + 2] >> 3 for i in range(0, len(rgb), 3)]
    return struct.pack((">%dH" if big_endian else "<%dH") % len(vals), *vals)


# ---------------------------------------------------------------- firmware image

class Lfi:
    def __init__(self, data):
        self.d = bytearray(data)
        if self.d[:4] != b"\x55\xaa\xf0\x0f":
            raise ValueError("not a firmware image")
        self.entries = {}
        for i in range(0x200, 0x2000, 0x20):
            e = self.d[i:i + 0x20]
            if not e[0]:
                break
            nm = (e[:8].decode("latin-1").rstrip() + "." + e[8:11].decode("latin-1").rstrip()).rstrip(".")
            off = struct.unpack_from("<I", e, 0x10)[0] << 9
            ln = struct.unpack_from("<I", e, 0x14)[0]
            self.entries[nm.upper()] = (i, off, ln)

    def get(self, name):
        _, off, ln = self.entries[name.upper()]
        return bytes(self.d[off:off + ln])

    def put(self, name, content):
        i, off, ln = self.entries[name.upper()]
        if len(content) != ln:
            raise ValueError("%s must stay %d bytes, got %d" % (name, ln, len(content)))
        self.d[off:off + ln] = content
        struct.pack_into("<I", self.d, i + 0x1c, sum32(content))
        struct.pack_into("<I", self.d, 0x10, sum32(bytes(self.d[0x200:0x2000])))
        struct.pack_into("<H", self.d, 0x1fe, sum16(bytes(self.d[:0x1fe])))

    def check(self):
        bad = []
        if sum16(bytes(self.d[:0x1fe])) != struct.unpack_from("<H", self.d, 0x1fe)[0]:
            bad.append("header")
        if sum32(bytes(self.d[0x200:0x2000])) != struct.unpack_from("<I", self.d, 0x10)[0]:
            bad.append("directory")
        for nm, (i, off, ln) in self.entries.items():
            if sum32(bytes(self.d[off:off + ln])) != struct.unpack_from("<I", self.d, i + 0x1c)[0]:
                bad.append(nm)
        return bad

    def unpack(self, folder):
        os.makedirs(folder, exist_ok=True)
        for nm, (i, off, ln) in self.entries.items():
            with open(os.path.join(folder, nm), "wb") as f:
                f.write(self.d[off:off + ln])


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--lfi", required=True, help="verified firmware image from the dump")
    ap.add_argument("--brec", help="boot record from the dump")
    ap.add_argument("--unpacked", help="unpacked firmware folder (for the fonts); default: next to --lfi")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--png", help="your own picture; it is scaled and cropped to 128x160")
    ap.add_argument("--text", default="X91")
    ap.add_argument("--subtext", default="custom boot")
    a = ap.parse_args()
    os.makedirs(a.out_dir, exist_ok=True)
    src = a.unpacked or os.path.join(os.path.dirname(os.path.abspath(a.lfi)), "unpacked")

    if a.png:
        rgb = fit(*read_png(a.png))
    else:
        rgb = text_card(src, a.text, a.subtext)
    with open(os.path.join(a.out_dir, "custom_boot_picture.png"), "wb") as f:
        f.write(xp.png_bytes(W, H, rgb))

    # 1. firmware area: LOGO.STY, picture 0 (little-endian RGB565)
    lfi = Lfi(open(a.lfi, "rb").read())
    before = lfi.check()
    logo = bytearray(lfi.get("LOGO.STY"))
    po = struct.unpack_from("<I", logo, 0x10)[0]
    off, ln, typ, w, h = struct.unpack_from("<IIHHH", logo, po)
    if (w, h, ln) != (W, H, W * H * 2):
        raise SystemExit("LOGO.STY picture 0 is not 128x160")
    logo[off:off + ln] = rgb_to_565(rgb)
    lfi.put("LOGO.STY", bytes(logo))
    after = lfi.check()
    out_lfi = os.path.join(a.out_dir, "x91_lfi_custom.bin")
    with open(out_lfi, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(a.out_dir, "unpacked"))
    orig = open(a.lfi, "rb").read()
    changed = sum(1 for i in range(0, len(orig), 512) if orig[i:i + 512] != lfi.d[i:i + 512])
    print("firmware image: %s" % out_lfi)
    print("  checksum failures before: %s, after: %s" % (before or "none", after or "none"))
    print("  512-byte sectors changed: %d of %d; size unchanged: %s" % (changed, len(orig) // 512, len(orig) == len(lfi.d)))
    print("  sha256: %s" % hashlib.sha256(lfi.d).hexdigest())

    # 2. boot record: welcome picture (big-endian RGB565), stored after the boot code
    if a.brec:
        b = bytearray(open(a.brec, "rb").read())
        code_sectors, total_sectors = struct.unpack_from("<HH", b, 4)
        res = code_sectors * 512
        # same rule the dump tool checks: all 16-bit words after the first, plus 0x1234
        code_ok = lambda x: struct.unpack_from("<H", x, 0)[0] == (sum16(bytes(x[2:res])) + 0x1234) & 0xffff
        ok_before = code_ok(b)
        b[res:res + W * H * 2] = rgb_to_565(rgb, big_endian=True)
        out_brec = os.path.join(a.out_dir, "brec_custom.bin")
        with open(out_brec, "wb") as f:
            f.write(b)
        print("boot record: %s" % out_brec)
        print("  boot code checksum valid before: %s, after: %s; size %d bytes (%d sectors declared)" % (
            ok_before, code_ok(b), len(b), total_sectors))


if __name__ == "__main__":
    main()
