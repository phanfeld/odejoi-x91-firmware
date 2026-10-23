"""What every part of the build uses: paths, the theme's colours, the image, pictures and texts of the resource files,
layout records, and program code (assembling, disassembling, checked byte changes, Thumb calls, checkers)."""
import hashlib
import os
import re
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
DESIGN = os.path.dirname(HERE)
ROOT = os.path.dirname(DESIGN)
TOOLS = os.path.join(ROOT, "firmware_analysis", "tools")
PATCHES = os.path.join(DESIGN, "patches")
PLAYLIST = os.path.join(DESIGN, "playlist")
DUMP = os.path.join(ROOT, "x91_dump")
STOCK = os.path.join(DUMP, "x91_lfi_verified.bin")
STOCK_SHA = "e85794a846ae1dff7a14c2826b46d0ce3481ea6110e14d1c1dea212e14322b60"
for path in (TOOLS, DESIGN):
    if path not in sys.path:
        sys.path.insert(0, path)
import ap_dis  # noqa: E402
import cairo  # noqa: E402
import x91_design as xd  # noqa: E402
import x91_modify as xm  # noqa: E402

# The colours of the theme being built (x91_design.THEMES) with the background forced to pure black: the stock status
# icons sit on black, and so do status bar, lists and backgrounds in every theme. use_theme() fills it in place, so
# every module sees the same dict.
T = {}
NEVER = ("CONFIG.AP", "FWUPDATE.AP")             # programs never changed: recovery depends on them


def use_theme(name):
    T.clear()
    T.update(xd.THEMES[name], bg="#000000")


def fail(text):
    raise SystemExit(text)


class Build:
    """One theme's image while it is built: the stock image's files, changed in place, and a work folder."""

    def __init__(self, theme, work):
        data = open(STOCK, "rb").read()
        if hashlib.sha256(data).hexdigest() != STOCK_SHA:
            fail("%s is not the verified stock image (sha256 %s)" % (STOCK, STOCK_SHA))
        self.stock_image = data
        self.stock = xm.Lfi(data)
        self.lfi = xm.Lfi(data)
        if self.lfi.check():
            fail("the stock image does not pass its checksums")
        self.theme = theme
        self.work = work
        self.notes = []

    def get(self, name):
        return bytearray(self.lfi.get(name))

    def put(self, name, data):
        self.lfi.put(name, bytes(data))

    def stock_file(self, name):
        return self.stock.get(name)

    def programs(self):
        """The programs that may be changed, in name order."""
        return [n for n in sorted(self.lfi.entries) if n.endswith(".AP") and n not in NEVER]

    def folder(self, *parts):
        path = os.path.join(self.work, *parts)
        os.makedirs(path, exist_ok=True)
        return path

    def note(self, text, *args):
        self.notes.append(text % args if args else text)


# ------------------------------------------------------------------ colours and SVG

def rgb(color):
    return tuple(int(color[i:i + 2], 16) for i in (1, 3, 5))


def c565(color):
    """RGB565 of "#rrggbb" or (r, g, b)."""
    r, g, b = rgb(color) if isinstance(color, str) else color
    return (r >> 3) << 11 | (g >> 2) << 5 | b >> 3


def mix(a, b, t):
    """Colour between a (t=0) and b (t=1)."""
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(rgb(a), rgb(b)))


def svg(w, h, parts):
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">%s%s</svg>'
            % (w, h, w, h, xd.rect(0, 0, w, h, 0, T["bg"]), "".join(parts)))


def stroke(color, width):
    return 'fill="none" stroke="%s" stroke-width="%g" stroke-linecap="round" stroke-linejoin="round"' % (color, width)


def text(x, y, s, size, weight, fill, anchor="middle", spacing=0):
    return ('<text x="%g" y="%g" font-family="Ubuntu" font-weight="%d" font-size="%g" letter-spacing="%g" fill="%s" '
            'text-anchor="%s">%s</text>' % (x, y, weight, size, spacing, fill, anchor, s))


def render_565(svg_text, w, h, work, name):
    """SVG to RGB565 picture data, through vectorcraft-cli."""
    src, png = os.path.join(work, name + ".svg"), os.path.join(work, name + ".png")
    with open(src, "w") as f:
        f.write(svg_text)
    r = subprocess.run(["vectorcraft-cli", "convert", src, png], capture_output=True, text=True, timeout=120)
    if r.returncode or not os.path.exists(png):
        fail("render failed for %s: %s" % (name, (r.stdout + r.stderr)[-200:]))
    s = cairo.ImageSurface.create_from_png(png)
    if (s.get_width(), s.get_height()) != (w, h):
        fail("%s rendered at %dx%d, expected %dx%d" % (name, s.get_width(), s.get_height(), w, h))
    out = cairo.ImageSurface(cairo.FORMAT_RGB24, w, h)
    c = cairo.Context(out)
    c.set_source_surface(s, 0, 0)
    c.paint()
    out.flush()
    d, stride = bytes(out.get_data()), out.get_stride()
    vals = []
    for y in range(h):
        row = d[y * stride:y * stride + w * 4]
        for x in range(w):
            b, g, r8 = row[x * 4], row[x * 4 + 1], row[x * 4 + 2]
            vals.append((r8 >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return struct.pack("<%dH" % len(vals), *vals)


def fill(w, h, color):
    return struct.pack("<H", c565(color)) * (w * h)


# ------------------------------------------------------------------ pictures of a resource file (.STY)

def pictures(sty):
    po, count = struct.unpack_from("<IH", sty, 0x10)
    return [struct.unpack_from("<IIHHH", sty, po + k * 16) for k in range(count)]


def picture_bytes(sty, index):
    po = struct.unpack_from("<I", sty, 0x10)[0]
    off, ln, typ, w, h = struct.unpack_from("<IIHHH", sty, po + index * 16)
    return bytes(sty[off:off + ln]), w, h


def set_picture(sty, index, data, w, h):
    """Replace a picture with one of the same size."""
    po = struct.unpack_from("<I", sty, 0x10)[0]
    off, ln, typ, pw, ph = struct.unpack_from("<IIHHH", sty, po + index * 16)
    if (pw, ph, ln) != (w, h, w * h * 2) or len(data) != ln:
        fail("picture %d is %dx%d (%d bytes), new one is %dx%d (%d bytes)" % (index, pw, ph, ln, w, h, len(data)))
    sty[off:off + ln] = data


def resize_picture(sty, index, w, h):
    """Declare a picture smaller than it was; its data keeps its place, the rest of its old room stays unused."""
    po = struct.unpack_from("<I", sty, 0x10)[0]
    off, ln, typ, pw, ph = struct.unpack_from("<IIHHH", sty, po + index * 16)
    if w * h * 2 > ln:
        fail("picture %d: no room for %dx%d" % (index, w, h))
    struct.pack_into("<IIHHH", sty, po + index * 16, off, w * h * 2, typ, w, h)


class Pictures:
    """Puts rendered or computed pictures into one resource file's bytes."""

    def __init__(self, sty, work):
        self.sty, self.work, self.count = sty, work, 0

    def svg(self, index, svg_text, w, h, name):
        self.raw(index, render_565(svg_text, w, h, self.work, name), w, h)

    def raw(self, index, data, w, h):
        set_picture(self.sty, index, data, w, h)
        self.count += 1


def pixel_glyph(ch, w, h, color, top=0, left=0):
    """A digit in the shapes of the text font's hand-drawn digits, as picture data."""
    from .typeface import HAND
    px = [0] * (w * h)
    _, _, pattern = HAND[ch]
    v = c565(color)
    for j, line in enumerate(pattern):
        for i, c in enumerate(line):
            if c == "#":
                px[(j + top) * w + i + left] = v
    return struct.pack("<%dH" % len(px), *px)


def dots(w, h, points, color):
    px = [0] * (w * h)
    for x, y in points:
        px[y * w + x] = c565(color)
    return struct.pack("<%dH" % len(px), *px)


def transposed(data, w, h):
    px = struct.unpack("<%dH" % (w * h), data)
    return struct.pack("<%dH" % (w * h), *(px[y * w + x] for x in range(w) for y in range(h)))


def with_copy(stock):
    """Pictures of a stock resource file that are followed by their sideways copy: a picture that serves as the
    background of a scrolling text is stored a second time, turned sideways, which is what the firmware reads while
    the text moves."""
    recs = pictures(stock)
    order = sorted(range(len(recs)), key=lambda k: recs[k][0])
    found = []
    for pos, k in enumerate(order):
        off, ln, _, w, h = recs[k]
        if ln != w * h * 2 or ln < 8:
            continue
        end = off + ln
        last = pos == len(order) - 1
        room = len(stock) - end if last else recs[order[pos + 1]][0] - end
        head = stock[off:end]
        if (room == ln or last and room >= ln and any(head)) and stock[end:end + ln] == transposed(head, w, h):
            found.append(k)
    return found


def refresh_copies(b):
    """Bring every sideways copy in line with its picture (run once, after the last picture has changed)."""
    done = []
    for name in sorted(n for n in b.lfi.entries if n.endswith(".STY")):
        stock = b.stock_file(name)
        sty = b.get(name)
        if len(sty) != len(stock):
            fail("%s changed its size" % name)
        recs, stock_recs, changed = pictures(sty), pictures(stock), []
        for k in with_copy(stock):
            off, ln, _, w, h = stock_recs[k]
            if recs[k][0] != off or recs[k][1] > ln:
                fail("%s picture %d moved" % (name, k))
            if recs[k][1] != ln:                                      # declared smaller since: not a text background
                continue
            copy = transposed(bytes(sty[off:off + ln]), w, h)
            if sty[off + ln:off + 2 * ln] != copy:
                sty[off + ln:off + 2 * ln] = copy
                changed.append(k)
        if changed:
            b.put(name, sty)
            done.append("%s %s" % (name, ", ".join(map(str, changed))))
    return done


# ------------------------------------------------------------------ layout records

def tables_of(sty):
    style = struct.unpack_from("<I", sty, 8)[0]
    begin = struct.unpack_from("<I", sty, style + 8)[0]
    return [struct.unpack_from("<II", sty, begin + t * 8) for t in range(11)]


def set_fields(sty, table, size, index, **fields):
    """Change 16-bit fields of a layout record; the field number (w0, w1, ...) is the word index inside the record."""
    off = tables_of(sty)[table][0] + index * size
    for word, value in fields.items():
        struct.pack_into("<H", sty, off + int(word[1:]) * 2, value)


# ------------------------------------------------------------------ texts

ENGLISH = 2                                      # language id of the English texts


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


def set_string(sty, table, index, value, donors):
    """Replace one string of a language. The table keeps its place and size and is packed anew; if the new text is
    longer, strings of entries nothing shows any more (donors) are emptied to make room."""
    off, ln, _, cnt, _ = table
    strings = read_strings(sty, table)
    strings[index] = value.encode("utf-16-le") + b"\0\0"
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


def language_names(sty):
    """The languages' names ("English", "German", ...), in the order of the string tables (from the file's XML)."""
    style_addr = struct.unpack_from("<I", sty, 8)[0]
    xo = struct.unpack_from("<I", sty, 0x30)[0]
    xml = bytes(sty[xo:style_addr]).rstrip(b"\0").decode("utf-8", "replace") if xo else ""
    blocks = re.findall(r'<ResEntry Type="Language" Name="([^"]*)" CodePage="([^"]*)">(.*?)</ResEntry>', xml, re.S)
    return [blocks[i][0] if i < len(blocks) else "lang%d" % t[4] for i, t in enumerate(language_tables(sty))]


def english(sty):
    """Offset and count of the English string table."""
    for off, ln, _, cnt, lid in language_tables(sty):
        if lid == ENGLISH:
            return off, cnt
    fail("no English texts")


def text_of(sty, off, idx):
    o, n = struct.unpack_from("<II", sty, off + idx * 8)
    return bytes(sty[o:o + n]).decode("utf-16-le").rstrip("\0"), o, n


def set_english(sty, changes, what, wider=None):
    """English texts in place: {index: (old, new)}; the new one must not be longer than the old one's room. With
    wider = (limit, width function), a new text wider than the limit is refused."""
    off, _ = english(sty)
    for idx, (old, new) in sorted(changes.items()):
        have, o, n = text_of(sty, off, idx)
        raw = (new + "\0").encode("utf-16-le")
        if have != old or len(raw) > n:
            fail("%s: English text %d is %r, or %r is longer" % (what, idx, have, new))
        if wider and wider[1](new) > wider[0]:
            fail("%s: %r is %d pixels wide, more than %d" % (what, new, wider[1](new), wider[0]))
        sty[o:o + n] = raw + bytes(n - len(raw))
        struct.pack_into("<I", sty, off + idx * 8 + 4, len(raw))


def text_width(b, value):
    """Width of a text in the image's interface font (pixels)."""
    fon = b.lfi.get("UNICODE.FON")
    return sum(fon[ord(c) * 33 + 32] for c in value)


# ------------------------------------------------------------------ menu files (.MCG)

def menu_heads(mcg):
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    return hsz, n


def rows_of(mcg, hsz, li):
    """A menu list: entry id, row count, offset, link to its parent row, and the rows (20 bytes each)."""
    eid, cnt, off, link = struct.unpack_from("<HHII", mcg, hsz + li * 12)
    return eid, cnt, off, link, [list(struct.unpack_from("<HHHHIII", mcg, off + k * 20)) for k in range(cnt)]


# ------------------------------------------------------------------ program code

def patch_bytes(buf, offset, old, new, what):
    """Replace bytes after checking the old ones."""
    if offset is None or bytes(buf[offset:offset + len(old)]) != old:
        fail("%s: unexpected bytes at %s, not patching" % (what, offset if offset is None else "%#x" % offset))
    buf[offset:offset + len(new)] = new


def run(cmd, what, cwd=None):
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if r.returncode:
        fail("%s failed:\n%s%s" % (what, r.stdout[-1500:], r.stderr[-1500:]))
    return r.stdout


def assemble(name, work, defsym=()):
    """Assemble patches/NAME.S; the binary from address 0 of the source (the patches lay out a whole bank)."""
    src = os.path.join(PATCHES, name + ".S")
    tag = os.path.join(work, name)
    args = []
    for k, v in defsym:
        args += ["--defsym", "%s=%#x" % (k, v)]
    run(["arm-none-eabi-as"] + args + ["-o", tag + ".o", src], "assembling %s.S" % name)
    run(["arm-none-eabi-objcopy", "-O", "binary", tag + ".o", tag + ".bin"], "objcopy")
    data = open(tag + ".bin", "rb").read()
    os.remove(tag + ".bin")
    os.remove(tag + ".o")
    return data


def disassemble(data, base, path):
    """objdump listing of a stretch of Thumb code at its address (what the checkers read)."""
    tmp = path + ".bin"
    open(tmp, "wb").write(data)
    r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                        "--adjust-vma=%#x" % base, tmp], capture_output=True, text=True)
    os.remove(tmp)
    open(path, "w").write(r.stdout)
    return path


def check(checker, old, new, base, work, tag, args=()):
    """Run patches/CHECKER on the old and the new bank side by side; stop if it reports a difference."""
    r = subprocess.run([sys.executable, "-I", os.path.join(PATCHES, checker),
                        disassemble(old, base, os.path.join(work, tag + "_old.dis")),
                        disassemble(new, base, os.path.join(work, tag + "_new.dis"))] + list(args),
                       capture_output=True, text=True)
    if r.returncode:
        fail("%s: the patch failed its check (%s):\n%s%s" % (tag, checker, r.stdout[-800:], r.stderr[-300:]))
    return r.stdout.strip()


def replace_stretch(ap, segs, work, what, bank, bank_len, lo, hi, built, stock_hash, checker, args=()):
    """Put new code over bank offsets lo..hi after checking the stock code and the new code's behaviour."""
    base = ap_dis.find(segs, bank)
    if base is None:
        fail("the %s routine's bank %#x is not there" % (what, bank))
    old = bytes(ap[base:base + bank_len])
    if hashlib.sha256(old[lo:hi]).hexdigest()[:16] != stock_hash:
        fail("the %s routine is not the expected one" % what)
    if len(built) != hi - lo:
        fail("the %s patch has the wrong length" % what)
    new = old[:lo] + built + old[hi:]
    result = check(checker, old, new, bank, work, what, args)
    ap[base + lo:base + hi] = built
    return result


def word_at(ap, segs, addr):
    return struct.unpack_from("<I", ap, ap_dis.find(segs, addr))[0]


def thumb_bl(at, target):
    """The Thumb bl at `at` that calls `target`."""
    off = target - (at + 4)
    if not -(1 << 24) <= off < (1 << 24) or off & 1:
        fail("bl from %#x cannot reach %#x" % (at, target))
    s = (off >> 24) & 1
    i1, i2 = (off >> 23) & 1, (off >> 22) & 1
    j1, j2 = (~i1 ^ s) & 1, (~i2 ^ s) & 1
    hi = 0xf000 | (s << 10) | ((off >> 12) & 0x3ff)
    lo = 0xd000 | (j1 << 13) | (j2 << 11) | ((off >> 1) & 0x7ff)
    return struct.pack("<HH", hi, lo)


def bl_at(code, k, at):
    """Target of the bl at offset k of code, which runs at address `at`."""
    hi, lo = struct.unpack_from("<HH", code, k)
    s = hi >> 10 & 1
    off = s << 24 | (~(lo >> 13 ^ s) & 1) << 23 | (~(lo >> 11 ^ s) & 1) << 22 | (hi & 0x3ff) << 12 | (lo & 0x7ff) << 1
    return at + 4 + (off - (1 << 25) if s else off)


def bl_target(ap, segs, at):
    """Target of the bl at address `at` of a program; stops if there is none."""
    o = ap_dis.find(segs, at)
    hi, lo = struct.unpack_from("<HH", ap, o)
    if hi >> 11 != 0x1e or lo >> 14 != 3 or not lo >> 12 & 1:
        fail("%#x: not a bl" % at)
    return bl_at(ap, o, at)


def aim(ap, segs, at, target, stock_target, what):
    """Re-aim the bl at `at` from its stock target to a new one."""
    if bl_target(ap, segs, at) != stock_target:
        fail("%s: %#x does not call %#x" % (what, at, stock_target))
    o = ap_dis.find(segs, at)
    ap[o:o + 4] = thumb_bl(at, target)


def bl_offsets(code):
    """Offsets of the bl instructions in a stretch of code."""
    out, i = [], 0
    while i < len(code) - 2:
        hi, lo = struct.unpack_from("<HH", code, i)
        if hi >> 11 == 0x1e and lo >> 14 == 3:
            out.append(i)
            i += 4
        else:
            i += 2
    return out


def masked(code):
    """Bytes of a stretch of code with its bl instructions masked out (to find shared code in any program)."""
    mask = bytearray(b"\xff" * len(code))
    for i in bl_offsets(code):
        mask[i:i + 4] = bytes(4)
    return code, mask


def find_all(data, segs, pattern):
    code, mask = pattern
    hits = []
    for kind, addr, off, n in segs:
        if kind != "bank":
            continue
        for at in range(off, off + n - len(code), 2):
            if all(not mask[k] or data[at + k] == code[k] for k in range(len(code))):
                hits.append(addr + at - off)
    return hits


def bls(data, segs, start, length):
    """The bl instructions of a stretch: (address, target)."""
    o = ap_dis.find(segs, start)
    return [(start + i, bl_at(data, o + i, start + i)) for i in bl_offsets(bytes(data[o:o + length]))]


BANK_TABLES = (0x800, 0x1000, 0x1800, 0x2000)   # a program's bank tables: entries of (file offset, address, length)


def bank_list(ap):
    """Every bank of a program: (table entry offset, file offset, address, length), in table order."""
    out = []
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", ap, t + i)
            if off and ln:
                out.append((t + i, off, addr, ln))
    return out


def bank_lengths(ap):
    return {addr: ln for _, _, addr, ln in bank_list(ap)}


def slot_of(ap, off):
    """The room of the file slot that starts at a bank's file offset (up to the next bank)."""
    starts = sorted(o for _, o, _, _ in bank_list(ap))
    return min([s for s in starts if s > off] + [len(ap)]) - off
