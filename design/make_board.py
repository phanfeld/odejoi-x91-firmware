#!/usr/bin/env python3
"""Build the design board: a self-contained HTML page and a combined SVG for VectorCraft.

usage: make_board.py [UNPACKED_FIRMWARE_DIR]
"""
import base64
import html
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(HERE, "..", "firmware_analysis", "tools"))
import cairo  # noqa: E402
import x91_design as xd  # noqa: E402


def uri(path):
    return "data:image/png;base64," + base64.b64encode(open(path, "rb").read()).decode()


def stock_pictures(unpacked):
    """The current main menu and a font sample, drawn from the dumped firmware for comparison."""
    out = {}
    try:
        import x91_preview as xp
    except ImportError:
        return out
    if not unpacked or not os.path.isdir(unpacked):
        return out
    fw = xp.Firmware(unpacked)
    s = fw.sty["MAINMENU.STY"]
    src, _ = fw.render_scene(s, s.scenes[0], "English")
    raw = base64.b64decode(src.split(",")[1])
    p = os.path.join(HERE, "mock", "stock-main.png")
    open(p, "wb").write(raw)
    big = xd.scaled(cairo.ImageSurface.create_from_png(p), 4)
    big.write_to_png(p)
    out["main"] = p
    # font comparison: stock 16-row font against the proposed one, both 1-bit
    lines = ["Playlists  Artists  Albums", "01 - One More Time"]
    cv = xp.Canvas(128, 40, (11, 13, 16))
    for i, ln in enumerate(lines):
        cv.text(fw.font16, 2, 2 + i * 18, ln, bytes((242, 244, 247)))
    p1 = os.path.join(HERE, "mock", "font-stock.png")
    open(p1, "wb").write(xp.png_bytes(128, 40, bytes(cv.px)))
    xd.scaled(cairo.ImageSurface.create_from_png(p1), 4).write_to_png(p1)
    surf = cairo.ImageSurface(cairo.FORMAT_RGB24, 128, 40)
    c = cairo.Context(surf)
    c.set_source_rgb(11 / 255, 13 / 255, 16 / 255)
    c.paint()
    xd.draw_texts(surf, [(2, 3 + i * 18, ln, "#f2f4f7", "ui", "L", None) for i, ln in enumerate(lines)])
    p2 = os.path.join(HERE, "mock", "font-new.png")
    xd.scaled(surf, 4).write_to_png(p2)
    out["font_stock"], out["font_new"] = p1, p2
    return out


def board_svg(screens, path):
    """All screens of one theme side by side, with live text, for editing in VectorCraft."""
    cols, gap, top = 5, 28, 34
    rows = (len(screens) + cols - 1) // cols
    bw, bh = cols * (xd.W + gap) + gap, rows * (xd.H + top + 10) + 20
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d">' % (bw, bh, bw, bh),
             '<rect width="%d" height="%d" fill="#15171b"/>' % (bw, bh)]
    for i, s in enumerate(screens):
        x, y = gap + (i % cols) * (xd.W + gap), 10 + top + (i // cols) * (xd.H + top + 10)
        inner = s.svg_doc(with_text=True)
        inner = inner[inner.index(">") + 1:inner.rindex("</svg>")]
        inner = re.sub(r'id="([^"]+)"', lambda m: 'id="%s-%s"' % (s.name, m.group(1)), inner)
        inner = re.sub(r'url\(#([^)]+)\)', lambda m: 'url(#%s-%s)' % (s.name, m.group(1)), inner)
        parts.append('<text x="%d" y="%d" font-family="Ubuntu" font-size="10" fill="#9aa3ae">%s</text>'
                     % (x, y - 8, html.escape(s.title)))
        parts.append('<clipPath id="clip-%s"><rect x="0" y="0" width="%d" height="%d"/></clipPath>' % (s.name, xd.W, xd.H))
        parts.append('<g transform="translate(%d %d)"><g clip-path="url(#clip-%s)">%s</g></g>' % (x, y, s.name, inner))
    parts.append("</svg>")
    with open(path, "w") as f:
        f.write("".join(parts))


CSS = """
:root{--bg:#f4f3ef;--fg:#1b1a18;--mut:#66635c;--card:#fff;--line:#dedbd2;--acc:#a86a00}
@media(prefers-color-scheme:dark){:root{--bg:#141413;--fg:#eceae4;--mut:#a09d94;--card:#1f1e1c;--line:#35332e;--acc:#ffb000}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:15px/1.55 system-ui,sans-serif}
main{max-width:1060px;margin:0 auto;padding:28px 16px 80px}h1{font-size:28px;line-height:1.2;margin:0 0 6px;letter-spacing:-.01em}
h2{font-size:19px;margin:44px 0 6px;padding-top:18px;border-top:1px solid var(--line)}p{margin:8px 0;max-width:68ch}.mut{color:var(--mut)}
.row{display:flex;flex-wrap:wrap;gap:22px;margin:16px 0}.dev{width:max-content;max-width:100%}
.dev .bezel{background:#08090a;border-radius:20px;padding:12px;border:1px solid #2a2a2a}
.dev img{display:block;width:256px;max-width:100%;height:auto;aspect-ratio:128/160;image-rendering:pixelated;border-radius:2px}
.dev .cap{font-size:13px;margin-top:8px;max-width:280px}.dev .cap b{display:block;font-size:14px}.dev .cap span{color:var(--mut)}
.tag{display:inline-block;font-size:11px;font-weight:600;letter-spacing:.04em;text-transform:uppercase;color:var(--acc);margin-bottom:2px}
.sw{display:flex;flex-wrap:wrap;gap:10px;margin:14px 0}.sw div{width:104px;font-size:12px;color:var(--mut)}
.sw i{display:block;height:44px;border-radius:8px;border:1px solid var(--line);margin-bottom:4px}
.font img{display:block;width:512px;max-width:100%;image-rendering:pixelated;border-radius:6px;margin:6px 0 2px}
table{border-collapse:collapse;width:100%;font-size:14px;background:var(--card);margin:12px 0}td,th{border:1px solid var(--line);padding:6px 10px;
text-align:left;vertical-align:top}th{font-weight:600}.wrap{overflow-x:auto}code{font:13px ui-monospace,monospace}
"""


def dev(src, title, note="", tag=""):
    return ("<div class=dev><div class=bezel><img src='%s' alt='%s'></div><div class=cap>%s<b>%s</b><span>%s</span></div></div>"
            % (uri(src), html.escape(title), "<span class=tag>%s</span>" % tag if tag else "", html.escape(title), html.escape(note)))


def main():
    unpacked = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "..", "x91_dump", "unpacked")
    made = {}
    for tag, t in xd.THEMES.items():
        screens = xd.build_screens(t) if tag == "amber" else [xd.main_grid(t, 0), xd.now_playing(t)]
        for s in screens:
            made[(tag, s.name)] = (xd.render(s, HERE, tag), s)
    amber = [made[("amber", n)][1] for n in ("boot", "main-grid", "main-grid-2", "main-focus", "music-menu", "playlist",
                                             "now-playing", "volume", "bluetooth", "settings")]
    board = os.path.join(HERE, "x91-design-board.svg")
    board_svg(amber, board)
    for ext in (".vectorcraft", ".png"):
        subprocess.run(["vectorcraft-cli", "convert", board, board[:-4] + ext] + (["--scale", "2"] if ext == ".png" else []),
                       capture_output=True, text=True, timeout=180)
    stock = stock_pictures(unpacked)
    m = lambda tag, name: made[(tag, name)][0]
    t = xd.THEMES["amber"]
    o = ["<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>",
         "<title>X91 interface design</title><style>", CSS, "</style><main>",
         "<h1>X91 interface design</h1>",
         "<p class=mut>A first proposal for a new look, drawn for the player's real screen: 128 by 160 pixels, 16-bit colour. "
         "Every picture below is shown at twice its pixel size, about four times its size on the device.</p>",
         "<p>The direction is called Graphite: a near-black background, one accent colour, rounded tiles and simple line icons. "
         "Flat colours suit this display, because gradients show bands in 16-bit colour, and one accent keeps the selected "
         "item obvious at arm's length.</p>",
         "<h2>Main menu</h2><p>Six entries: Music, Playlists, Folder, Bluetooth, eBook, Settings. Two layouts are possible. "
         "The grid shows everything at once. The focus layout shows one entry at a time and uses a menu style the firmware "
         "already has.</p><div class=row>"]
    if "main" in stock:
        o.append(dev(stock["main"], "Today", "The current main menu, drawn from your firmware dump.", "Before"))
    o += [dev(m("amber", "main-grid"), "Grid", "Three by two, selected tile filled with the accent.", "Option A"),
          dev(m("amber", "main-grid-2"), "Grid, next entry", "Each highlighted entry is its own full-screen picture."),
          dev(m("amber", "main-focus"), "Focus", "One entry large, neighbours peeking in, position dots.", "Option B"),
          "</div><h2>Lists and playback</h2><div class=row>",
          dev(m("amber", "music-menu"), "Music menu", "Playlists first. Selected row: soft panel and accent bar."),
          dev(m("amber", "playlist"), "Inside a playlist", "The playing track carries the level icon."),
          dev(m("amber", "now-playing"), "Now playing", "Cover from the file's tag, one accent for progress and active modes."),
          dev(m("amber", "volume"), "Volume", "A panel over the dimmed screen."),
          "</div><h2>Other screens</h2><div class=row>",
          dev(m("amber", "settings"), "Settings", "Current values on the right in the secondary colour."),
          dev(m("amber", "bluetooth"), "Bluetooth", "Search state on top, found devices as list rows."),
          dev(m("amber", "boot"), "Start-up", "A picture, so its lettering can be smooth."),
          "</div><h2>Accent colour</h2><p>The same design with three accents. Amber is the warmest and the most legible on "
          "a cheap panel; mint and ice are cooler.</p><div class=row>"]
    for tag, name in (("amber", "Amber"), ("mint", "Mint"), ("ice", "Ice")):
        o.append(dev(m(tag, "main-grid"), name, xd.THEMES[tag]["accent"]))
        o.append(dev(m(tag, "now-playing"), name + ", playing", ""))
    o.append("</div><h2>Colours</h2><div class=sw>")
    for k, label in (("bg", "Background"), ("surface", "Panel"), ("raised", "Overlay"), ("line", "Track, divider"),
                     ("text", "Text"), ("text2", "Secondary text"), ("accent", "Accent")):
        o.append("<div><i style='background:%s'></i>%s<br><code>%s</code></div>" % (t[k], label, t[k]))
    o.append("</div>")
    if "font_stock" in stock:
        o += ["<h2>Typeface</h2><p>The firmware draws all text from a bitmap font: one colour, no smoothing, 16 pixel rows. "
              "Replacing the Latin letters in that font file changes every screen at once. Both samples below are drawn "
              "the way the player draws text.</p><div class=font><span class=mut>Today</span><img src='%s' alt='stock font sample'>"
              "<span class=mut>Proposed: Ubuntu at 12 pixels, rendered to one bit</span><img src='%s' alt='proposed font sample'></div>"
              % (uri(stock["font_stock"]), uri(stock["font_new"]))]
    o += ["<h2>What each part takes</h2><div class=wrap><table><tr><th>Part</th><th>What changes in the firmware</th><th>Kind of change</th></tr>",
          "<tr><td>Icons, tiles, backgrounds, bars, start-up picture</td><td>Pictures in the resource files, same sizes as today</td><td>Pictures only, like the boot picture</td></tr>",
          "<tr><td>Typeface</td><td>Glyph bitmaps in the font file</td><td>Data only, but it touches every screen</td></tr>",
          "<tr><td>Text colours and positions</td><td>Entries in the layout tables</td><td>Data only; each screen needs checking on the device</td></tr>",
          "<tr><td>Six-entry main menu, Playlists on top of the music menu</td><td>The compiled settings and the menu file</td><td>Behaviour; needs the recovery key first</td></tr>",
          "<tr><td>Playlists as its own main-menu entry</td><td>Program code or a launch table in the menu program</td><td>Not yet known to be possible</td></tr>",
          "<tr><td>Cover size and place on the playing screen</td><td>Read from the layout first; the mock-up shows the intent</td><td>To be confirmed</td></tr>",
          "</table></div>",
          "<h2>Files</h2><p>The pictures are written as SVG and rendered with VectorCraft. Open <code>design/x91-design-board.vectorcraft</code> "
          "(or the <code>.svg</code>) in VectorCraft to adjust shapes and colours; single screens are in <code>design/src/</code>. "
          "<code>design/x91_design.py</code> regenerates everything, including a different accent.</p>",
          "</main></html>"]
    out = os.path.join(HERE, "X91 design concept.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(o))
    print("wrote", out, os.path.getsize(out), "bytes;", len(made), "screens")


if __name__ == "__main__":
    main()
