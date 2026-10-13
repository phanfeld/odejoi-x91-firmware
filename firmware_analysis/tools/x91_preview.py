#!/usr/bin/env python3
"""Screen previewer for Actions US215A (ATJ2157) player firmware, written for the ODEJOI X91.

It does not run the firmware's code. It reads the unpacked firmware files and redraws what the
firmware would draw: every picture, every text in every language, and every screen layout
("scene") composed from the firmware's own layout tables and bitmap fonts.

usage: x91_preview.py UNPACKED_DIR OUT_HTML [--lang English] [--lang2 German] [--brec brec0.bin]
"""
import argparse
import base64
import html
import json
import os
import re
import struct
import zlib

W, H = 128, 160
CTRL_NAMES = ["scene", "picbox", "textbox", "numbox", "timebox", "progressbar", "listbox",
              "parambox", "dialogbox", "sliderbar", "attributebox"]

# RGB565 -> 3 bytes, precomputed once
RGB = [bytes(((v >> 11 & 31) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31)) for v in range(65536)]


def rgb565_to_rgb(px, big_endian=False):
    fmt = (">%dH" if big_endian else "<%dH") % (len(px) // 2)
    return b"".join(RGB[v] for v in struct.unpack(fmt, px[:len(px) & ~1]))


def png_bytes(w, h, rgb):
    raw = b"".join(b"\0" + rgb[y * w * 3:(y + 1) * w * 3] for y in range(h))

    def chunk(t, d):
        return struct.pack(">I", len(d)) + t + d + struct.pack(">I", zlib.crc32(t + d) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def data_uri(w, h, rgb):
    return "data:image/png;base64," + base64.b64encode(png_bytes(w, h, rgb)).decode()


class Font:
    """UNICODE.FON: 65536 glyphs, each `rows * 2` bitmap bytes plus one width byte."""

    def __init__(self, path, rows):
        self.data = open(path, "rb").read()
        self.rows = rows
        self.gsize = len(self.data) // 65536

    def glyph(self, cp):
        g = self.data[cp * self.gsize:(cp + 1) * self.gsize]
        width = g[-1]
        bpr = (width + 7) // 8 or 1
        return width, [g[r * bpr:(r + 1) * bpr] for r in range(self.rows)]

    def text_width(self, s):
        return sum(self.glyph(ord(c))[0] for c in s if ord(c) < 65536)


class Canvas:
    def __init__(self, w=W, h=H, color=(0, 0, 0)):
        self.w, self.h = w, h
        self.px = bytearray(bytes(color) * (w * h))

    def blit(self, x, y, w, h, rgb):
        for row in range(h):
            yy = y + row
            if not 0 <= yy < self.h:
                continue
            x0, x1 = max(x, 0), min(x + w, self.w)
            if x0 >= x1:
                continue
            src = (row * w + (x0 - x)) * 3
            dst = (yy * self.w + x0) * 3
            self.px[dst:dst + (x1 - x0) * 3] = rgb[src:src + (x1 - x0) * 3]

    def fill(self, x, y, w, h, color):
        self.blit(x, y, w, h, bytes(color) * (w * h))

    def text(self, font, x, y, s, color, clip=None):
        cx0, cy0, cx1, cy1 = clip or (0, 0, self.w, self.h)
        cx0, cy0, cx1, cy1 = max(cx0, 0), max(cy0, 0), min(cx1, self.w), min(cy1, self.h)
        for c in s:
            if ord(c) >= 65536:
                continue
            width, rows = font.glyph(ord(c))
            for r, row in enumerate(rows):
                yy = y + r
                if not cy0 <= yy < cy1:
                    continue
                for b in range(width):
                    if b // 8 < len(row) and row[b // 8] >> (7 - b % 8) & 1:
                        xx = x + b
                        if cx0 <= xx < cx1:
                            i = (yy * self.w + xx) * 3
                            self.px[i:i + 3] = color
            x += width

    def uri(self):
        return data_uri(self.w, self.h, bytes(self.px))


def wrap(font, text, width):
    """Greedy word wrap, as a multi-line text box would break the text."""
    lines, cur = [], ""
    for word in text.split(" "):
        trial = (cur + " " + word) if cur else word
        if font.text_width(trial) <= width or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    if cur:
        lines.append(cur)
    return lines


class Sty:
    """One .sty resource file: pictures, strings per language, and layout tables."""

    def __init__(self, path):
        self.name = os.path.basename(path)
        d = self.d = open(path, "rb").read()
        if d[:4] != b"RU3\x19":
            raise ValueError("not a resource file: " + path)
        self.style_addr = struct.unpack_from("<I", d, 8)[0]
        po, pc = struct.unpack_from("<IH", d, 0x10)
        self.pics = []
        for k in range(pc):
            off, ln, typ, w, h = struct.unpack_from("<IIHHH", d, po + k * 16)
            self.pics.append({"off": off, "len": ln, "type": typ, "w": w, "h": h})
        so, sc = struct.unpack_from("<IH", d, 0x20)
        self.langs = []
        for k in range(sc):
            off, ln, _, cnt, lid = struct.unpack_from("<IIHHH", d, so + k * 16)
            strs = []
            for j in range(cnt):
                o, n = struct.unpack_from("<II", d, off + j * 8)
                strs.append(d[o:o + n].decode("utf-16-le", "replace").split("\0")[0])
            self.langs.append({"id": lid, "name": "lang%d" % lid, "strings": strs})
        xo = struct.unpack_from("<I", d, 0x30)[0]
        self.xml = d[xo:self.style_addr].rstrip(b"\0").decode("utf-8", "replace") if xo else ""
        self.pic_names = re.findall(r'<ResEntry Name="([^"]*)" Type="Picture"', self.xml)
        lang_blocks = re.findall(r'<ResEntry Type="Language" Name="([^"]*)" CodePage="([^"]*)">(.*?)</ResEntry>',
                                 self.xml, re.S)
        self.str_names = []
        for i, (lname, cp, body) in enumerate(lang_blocks):
            if i < len(self.langs):
                self.langs[i]["name"] = lname
                self.langs[i]["codepage"] = cp
            if not self.str_names:
                self.str_names = re.findall(r'<String Name="([^"]*)"', body)
        # layout tables
        self.tables = [(0, 0)] * 11
        self.scenes, self.picboxes, self.textboxes = [], [], []
        if d[self.style_addr:self.style_addr + 3] == b"sty":
            sb = struct.unpack_from("<I", d, self.style_addr + 8)[0]
            self.tables = [struct.unpack_from("<II", d, sb + t * 8) for t in range(11)]
            o, c = self.tables[0]
            for k in range(c):
                back, x, y, w, h, _, cc, cl, attrib = struct.unpack_from("<HhhHHHHIH", d, o + k * 20)
                ctrls = []
                for j in range(cc):
                    flag, sid = struct.unpack_from("<HH", d, cl + j * 4)
                    ctrls.append((flag, sid >> 12, sid & 0xfff))
                self.scenes.append({"back": back, "ctrls": ctrls})
            o, c = self.tables[1]
            for k in range(c):
                v = struct.unpack_from("<16H", d, o + k * 32)
                n = v[3] >> 8 & 0xff
                by_addr = bool(v[3] >> 1 & 1)
                if by_addr:
                    addr = v[5] << 16 | v[4]
                    frames = list(struct.unpack_from("<%dH" % n, d, addr)) if n else []
                else:
                    frames = list(v[4:4 + min(n, 12)])
                self.picboxes.append({"id": v[0], "x": v[1], "y": v[2], "attrib": v[3], "frames": frames})
            o, c = self.tables[2]
            for k in range(c):
                v = struct.unpack_from("<10H", d, o + k * 20)
                self.textboxes.append(dict(zip(
                    ("id", "x", "y", "w", "h", "back_x", "back_y", "back_id", "color", "attrib"), v)))

    def pic_rgb(self, i):
        p = self.pics[i]
        return p["w"], p["h"], rgb565_to_rgb(self.d[p["off"]:p["off"] + p["w"] * p["h"] * 2])

    def lang(self, name):
        for lg in self.langs:
            if lg["name"].lower() == name.lower():
                return lg
        return None


class Firmware:
    def __init__(self, folder):
        self.folder = folder
        self.sty = {}
        for fn in sorted(os.listdir(folder)):
            if fn.upper().endswith(".STY"):
                try:
                    self.sty[fn.upper()] = Sty(os.path.join(folder, fn))
                except (ValueError, struct.error) as e:
                    print("skipped", fn, e)
        self.common = self.sty.get("COMMON.STY")
        self.font16 = Font(os.path.join(folder, "UNICODE.FON"), 16)
        big = os.path.join(folder, "UNICODEL.FON")
        self.font24 = Font(big, 24) if os.path.exists(big) else self.font16
        self._cache = {}

    def resolve(self, sty, rid):
        """Bit 15 of a resource id selects COMMON.STY."""
        if rid & 0x8000 and self.common:
            return self.common, rid & 0x7fff
        return sty, rid & 0x7fff

    def picture(self, sty, rid):
        s, i = self.resolve(sty, rid)
        if i >= len(s.pics):
            return None
        key = (s.name, i)
        if key not in self._cache:
            self._cache[key] = s.pic_rgb(i)
        return self._cache[key]

    def string(self, sty, rid, lang):
        s, i = self.resolve(sty, rid)
        lg = s.lang(lang) or (s.langs[0] if s.langs else None)
        if lg and i < len(lg["strings"]):
            return lg["strings"][i]
        return None

    def render_scene(self, sty, scene, lang):
        cv = Canvas()
        notes = []
        for flag, typ, idx in scene["ctrls"]:
            tname = CTRL_NAMES[typ] if typ < len(CTRL_NAMES) else "type%d" % typ
            if typ == 1 and idx < len(sty.picboxes):
                pb = sty.picboxes[idx]
                frame = pb["frames"][0] if pb["frames"] else pb["id"]
                pic = self.picture(sty, frame)
                if pic and pb["attrib"] & 1 and flag:
                    cv.blit(pb["x"], pb["y"], *pic)
                notes.append("picbox %d at (%d,%d): picture %s, %d frame(s)%s" % (
                    idx, pb["x"], pb["y"], self.pic_label(sty, frame), len(pb["frames"]),
                    "" if flag else " [hidden by default]"))
            elif typ == 2 and idx < len(sty.textboxes):
                tb = sty.textboxes[idx]
                a = tb["attrib"]
                if flag and a >> 1 & 1 and tb["back_id"] != 0xffff:
                    pic = self.picture(sty, tb["back_id"])
                    if pic:
                        cv.blit(tb["back_x"], tb["back_y"], *pic)
                text = self.string(sty, tb["id"], lang) if tb["id"] != 0xffff else None
                font = self.font24 if (a >> 2 & 3) == 2 else self.font16
                if text and a & 1 and flag:
                    align = a >> 7 & 3
                    multiline = (a >> 5 & 3) == 0 and tb["h"] >= 2 * font.rows
                    lines = wrap(font, text, tb["w"]) if multiline else [text]
                    lines = lines[:max(tb["h"] // font.rows, 1)]
                    y = tb["y"] + (0 if multiline else max((tb["h"] - font.rows) // 2, 0))
                    clip = (tb["x"], tb["y"], tb["x"] + tb["w"], tb["y"] + max(tb["h"], font.rows))
                    for line in lines:
                        tw = font.text_width(line)
                        x = tb["x"] + ((tb["w"] - tw) // 2 if align == 1 else tb["w"] - tw if align == 2 else 0)
                        cv.text(font, max(x, tb["x"]), y, line, RGB[tb["color"]], clip)
                        y += font.rows
                notes.append("textbox %d at (%d,%d) %dx%d: %s%s" % (
                    idx, tb["x"], tb["y"], tb["w"], tb["h"],
                    ("text %d “%s”" % (tb["id"] & 0x7fff, text)) if text else "text set by the program",
                    "" if flag else " [hidden by default]"))
            else:
                notes.append("%s %d (not drawn by this previewer)" % (tname, idx))
        return cv.uri(), notes

    def pic_label(self, sty, rid):
        s, i = self.resolve(sty, rid)
        nm = s.pic_names[i] if i < len(s.pic_names) else "?"
        return "%s#%d (%s)" % (s.name, i, nm)


def parse_config(path):
    rows = []
    if not os.path.exists(path):
        return rows
    text = open(path, "rb").read().rstrip(b"\0").decode("gbk", "replace")
    for line in text.splitlines():
        m = re.match(r"\s*([A-Z][A-Z0-9_]*)\s*(?:\{\d+\})?\s*=\s*([^;]*);\s*(?://\s*(.*))?", line)
        if m:
            rows.append((m.group(1), m.group(2).strip(), (m.group(3) or "").strip()))
    return rows


CSS = """
:root{--bg:#f6f5f1;--fg:#1d1c1a;--mut:#6b6860;--card:#fff;--line:#dcd9d0;--acc:#0b6e69}
@media(prefers-color-scheme:dark){:root{--bg:#171715;--fg:#ecebe6;--mut:#a3a097;--card:#22211e;--line:#3a3833;--acc:#57c4bd}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 80px}h1{font-size:26px;margin:0 0 4px}h2{font-size:19px;margin:36px 0 10px;
padding-top:14px;border-top:1px solid var(--line)}h3{font-size:15px;margin:18px 0 8px}p{margin:8px 0}.mut{color:var(--mut)}
img.px{image-rendering:pixelated;image-rendering:crisp-edges;background:#000;display:block}
.emu{display:flex;gap:24px;flex-wrap:wrap;align-items:flex-start;background:var(--card);border:1px solid var(--line);
border-radius:10px;padding:18px}.device{background:#111;border-radius:22px;padding:18px 18px 22px;width:max-content}
.device img{width:384px;height:480px;max-width:70vw;height:auto;aspect-ratio:128/160;border-radius:3px}
.keys{display:flex;gap:8px;justify-content:center;margin-top:14px}button,select{font:inherit;padding:6px 12px;border-radius:7px;
border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}button:hover{border-color:var(--acc)}
.side{flex:1;min-width:260px}.side ul{margin:6px 0;padding-left:18px}.side li{margin:3px 0;font-size:14px}
.grid{display:flex;flex-wrap:wrap;gap:10px}.tile{background:var(--card);border:1px solid var(--line);border-radius:7px;padding:6px;
font-size:12px;color:var(--mut);text-align:center}.tile img{margin:0 auto 4px;max-width:256px}
table{border-collapse:collapse;width:100%;font-size:13px;background:var(--card)}td,th{border:1px solid var(--line);padding:4px 8px;
text-align:left;vertical-align:top}th{font-weight:600}.wrap{overflow-x:auto}code{font:13px ui-monospace,monospace}
details{margin:8px 0}summary{cursor:pointer;font-weight:600}nav a{margin-right:10px;color:var(--acc);font-size:14px}
"""

JS = """
const S = JSON.parse(document.getElementById('scenes').textContent);
let file = Object.keys(S)[0], idx = 0;
const sel = document.getElementById('file'), img = document.getElementById('screen'),
      cap = document.getElementById('cap'), notes = document.getElementById('notes');
for (const f of Object.keys(S)) { const o = document.createElement('option'); o.textContent = f; sel.appendChild(o); }
function show() {
  const list = S[file]; idx = (idx + list.length) % list.length; const s = list[idx];
  img.src = s.src; cap.textContent = file + ' \\u00b7 screen ' + (idx + 1) + ' of ' + list.length;
  notes.replaceChildren(...s.notes.map(n => { const li = document.createElement('li'); li.textContent = n; return li; }));
}
sel.onchange = () => { file = sel.value; idx = 0; show(); };
document.getElementById('prev').onclick = () => { idx--; show(); };
document.getElementById('next').onclick = () => { idx++; show(); };
document.addEventListener('keydown', e => { if (e.key === 'ArrowLeft') { idx--; show(); } if (e.key === 'ArrowRight') { idx++; show(); } });
sel.value = S['MAINMENU.STY'] ? 'MAINMENU.STY' : file; file = sel.value; show();
"""


def build(args):
    fw = Firmware(args.folder)
    e = html.escape
    out = ["<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>",
           "<title>X91 firmware preview</title><style>", CSS, "</style><main>",
           "<h1>X91 firmware preview</h1>",
           "<p class=mut>Redrawn from the dumped firmware files. This shows what the firmware draws; it does not run its code.</p>"]
    scenes_json = {}
    total_pics = sum(len(s.pics) for s in fw.sty.values())
    total_strs = sum(len(s.langs[0]["strings"]) if s.langs else 0 for s in fw.sty.values())
    for name, s in fw.sty.items():
        lst = []
        for k, sc in enumerate(s.scenes):
            src, notes = fw.render_scene(s, sc, args.lang)
            lst.append({"src": src, "notes": notes})
        if lst:
            scenes_json[name] = lst
    out.append("<nav>" + "".join("<a href='#%s'>%s</a>" % (e(n), e(n[:-4].title())) for n in fw.sty) + "<a href='#settings'>Settings</a></nav>")
    out.append("<h2>Screens</h2><div class=emu><div><div class=device><img class=px id=screen alt='screen'>"
               "<div class=keys><button id=prev>◀ Previous</button><button id=next>Next ▶</button></div></div></div>"
               "<div class=side><p><select id=file></select></p><p id=cap class=mut></p>"
               "<p>Controls on this screen, from the firmware's layout table:</p><ul id=notes></ul>"
               "<p class=mut>Pictures and fixed texts are drawn. Lists, dialogs, number and time fields are filled in by the "
               "program at run time and are listed here but not drawn.</p></div></div>")
    out.append("<p class=mut>%d resource files, %d pictures, %d texts per language, %d screen layouts.</p>" % (
        len(fw.sty), total_pics, total_strs, sum(len(v) for v in scenes_json.values())))
    if args.brec and os.path.exists(args.brec):
        b = open(args.brec, "rb").read()
        off = struct.unpack_from("<H", b, 4)[0] * 512
        px = b[off:off + W * H * 2]  # big-endian RGB565, unlike the resource files
        out.append("<h2>Boot picture</h2><p class=mut>Stored in the boot record, not in a resource file. "
                   "The bottom strip did not read back reliably.</p><div class=grid><div class=tile>"
                   "<img class=px width=256 src='%s'>boot record, %dx%d</div></div>" % (
                       data_uri(W, H, rgb565_to_rgb(px, big_endian=True)), W, H))
    for name, s in fw.sty.items():
        out.append("<h2 id='%s'>%s</h2>" % (e(name), e(name)))
        counts = ", ".join("%d %s" % (c, CTRL_NAMES[t]) for t, (o, c) in enumerate(s.tables) if c)
        out.append("<p class=mut>%d pictures, %d languages, %d texts each. Layout tables: %s.</p>" % (
            len(s.pics), len(s.langs), len(s.langs[0]["strings"]) if s.langs else 0, counts or "none"))
        if s.pics:
            out.append("<details%s><summary>Pictures (%d)</summary><div class=grid>" % (" open" if len(s.pics) <= 60 else "", len(s.pics)))
            for i, p in enumerate(s.pics):
                w, h, rgb = fw.picture(s, i)
                if not w or not h:
                    continue
                scale = 2 if w <= 128 else 1
                out.append("<div class=tile><img class=px width=%d src='%s' loading=lazy>#%d %s<br>%d×%d</div>" % (
                    w * scale, data_uri(w, h, rgb), i, e(s.pic_names[i] if i < len(s.pic_names) else ""), w, h))
            out.append("</div></details>")
        if s.langs and s.langs[0]["strings"]:
            l1, l2 = s.lang(args.lang) or s.langs[0], s.lang(args.lang2)
            out.append("<details><summary>Texts (%d, in %d languages: %s)</summary><div class=wrap><table><tr><th>#</th><th>Name</th><th>%s</th>%s</tr>" % (
                len(l1["strings"]), len(s.langs), e(", ".join(lg["name"] for lg in s.langs)), e(l1["name"]),
                "<th>%s</th>" % e(l2["name"]) if l2 else ""))
            for i, t in enumerate(l1["strings"]):
                out.append("<tr><td>%d</td><td><code>%s</code></td><td>%s</td>%s</tr>" % (
                    i, e(s.str_names[i] if i < len(s.str_names) else ""), e(t),
                    "<td>%s</td>" % e(l2["strings"][i] if i < len(l2["strings"]) else "") if l2 else ""))
            out.append("</table></div></details>")
    rows = parse_config(os.path.join(args.folder, "CONFIG.TXT"))
    if rows:
        out.append("<h2 id=settings>Settings (CONFIG.TXT)</h2><p class=mut>The build-time settings as stored in the firmware, "
                   "with the vendor's original comments. The firmware reads a compiled copy (CONFIG.BIN), so editing this "
                   "text alone changes nothing.</p><div class=wrap><table><tr><th>Setting</th><th>Value</th><th>Vendor comment</th></tr>")
        for k, v, c in rows:
            out.append("<tr><td><code>%s</code></td><td><code>%s</code></td><td>%s</td></tr>" % (e(k), e(v), e(c)))
        out.append("</table></div>")
    out.append("<script type='application/json' id=scenes>%s</script><script>%s</script></main></html>" % (
        json.dumps(scenes_json).replace("</", "<\\/"), JS))
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("".join(out))
    print("wrote %s: %d files, %d pictures, %d screens" % (args.out, len(fw.sty), total_pics, sum(len(v) for v in scenes_json.values())))


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("folder")
    ap.add_argument("out")
    ap.add_argument("--lang", default="English")
    ap.add_argument("--lang2", default="German")
    ap.add_argument("--brec")
    build(ap.parse_args())
