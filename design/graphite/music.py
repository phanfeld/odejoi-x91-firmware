"""The music program: its menu, the playing screen, the title from the tag.

  - Music menu: Playlists at the top (and second, after "Now playing", while something plays): records of MUSIC.MCG
    reordered, nothing else.
  - Playing screen after the design mock: black background instead of the red glow, track counter top left (x=22,
    right of the status bar's card mark; as many digits as the numbers have), play state in the status bar, cover,
    centred title, the progress bar below it with the played part in the accent colour, times bottom left, play-mode
    icons bottom right; the equaliser's name is not shown. Layout and pictures in MUSIC.STY. The routine in MUSIC.AP
    that draws time and bar is rewritten (patches/music_playing.S): the knob moves column by column without flicker.
  - The title comes from the file's tag: the tag reader overwrote it with the file name every time; now only when the
    tag has no title (patches/music_title.S).
  - "Playlist 1" is called "Favorites" where the word is known and fits.
"""
import os
import struct

from . import base
from .base import T, ap_dis, fail, stroke, svg, xd
from .pictures import status_icon

BAR_Y, BAR_X, BAR_LEN = 132, 8, 106             # must match patches/music_playing.S
COUNTER_X = 22                                  # right of the card mark, as the main menu's clock
COUNTER_DIGITS = (0x0244, 0x0200)               # number box 0, word 12: 4 and 4 digits -> as many as needed
PLAYLISTS, ALL_SONGS = 0x48, 0x0A               # MUSIC.MCG texts of the rows
FAVORITES = {"English": "Favorites", "German": "Favoriten", "French": "Favoris", "Spanish": "Favoritos",
             "Italian": "Preferiti", "Dutch": "Favorieten", "Portuguese_European": "Favoritos",
             "Portuguese_Brazilian": "Favoritos", "Danish": "Favoritter", "Swedish": "Favoriter", "Norwegian": "Favoritter"}
PLAYLIST_1 = 73                                 # MUSIC.STY text "Playlist 1"

PLAYING = dict(bank=0x18061000, bank_len=0x644, lo=0x390, hi=0x476, stock_hash="c92da8f38e364d31")
TITLE = dict(bank=0x1c102000, bank_len=0x3e8, lo=0x1d4, hi=0x1f2, stock_hash="157e0c9342e18066")


# ------------------------------------------------------------------ music menu

def playlists_up(b):
    """Playlists (text 0x48) to the front of every music list that starts with All songs, and to second place in the
    lists that start with "Now playing" or "Last played"."""
    mcg = b.get("MUSIC.MCG")
    hsz, n = base.menu_heads(mcg)
    first = second = 0
    for i in range(n):
        eid, cnt, off, _ = struct.unpack_from("<HHII", mcg, hsz + i * 12)
        items = [bytes(mcg[off + k * 20:off + (k + 1) * 20]) for k in range(cnt)]
        texts = [struct.unpack_from("<H", it, 2)[0] for it in items]
        if cnt >= 5 and texts[0] == ALL_SONGS and PLAYLISTS in texts:
            items.insert(0, items.pop(texts.index(PLAYLISTS)))
            first += 1
        elif cnt >= 6 and texts[1] == ALL_SONGS and texts[0] != PLAYLISTS and PLAYLISTS in texts:
            items.insert(1, items.pop(texts.index(PLAYLISTS)))
            second += 1
        mcg[off:off + cnt * 20] = b"".join(items)
    b.put("MUSIC.MCG", mcg)
    return first, second


# ------------------------------------------------------------------ playing screen: pictures and layout

def without_red(data, tint=None):
    """Remove the stock red glow: a pixel keeps only its neutral part. With tint, that part is drawn in the tint colour."""
    out = bytearray(len(data))
    tr, tg, tb = base.rgb(tint) if tint else (255, 255, 255)
    for i in range(0, len(data), 2):
        v = data[i] | data[i + 1] << 8
        r, g, b = (v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31
        m = max(g, b)
        if r > m:
            r = g = b = m
        if tint:
            m = max(r, g, b)
            m = 0 if m < 48 else m
            r, g, b = tr * m // 255, tg * m // 255, tb * m // 255
        struct.pack_into("<H", out, i, (r >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return bytes(out)


def tinted(data, color):
    """Keep the shape of a white-on-black picture, in another colour."""
    r0, g0, b0 = base.rgb(color)
    out = bytearray(len(data))
    for i in range(0, len(data), 2):
        v = data[i] | data[i + 1] << 8
        m = max((v >> 11) * 255 // 31, (v >> 5 & 63) * 255 // 63, (v & 31) * 255 // 31)
        r, g, b = r0 * m // 255, g0 * m // 255, b0 * m // 255
        struct.pack_into("<H", out, i, (r >> 3) << 11 | (g >> 2) << 5 | b >> 3)
    return bytes(out)


def bar(w, color, x0=0, x1=None):
    """A piece of the progress bar: 6 rows, the line on rows 2 and 3 from x0 to x1."""
    x1 = w if x1 is None else x1
    row = [base.c565(color) if x0 <= x < x1 else 0 for x in range(w)]
    return struct.pack("<%dH" % (w * 6), *([0] * (2 * w) + row * 2 + [0] * (2 * w)))


def state_icon(kind):
    """Play state in the status bar, 16 x 16."""
    c = T["text"]
    shapes = {"play": '<path d="M5 3.500l8 4.500-8 4.500z" fill="%s" stroke="%s" stroke-width="1" stroke-linejoin="round"/>' % (c, c),
              "pause": xd.rect(4, 3.5, 3, 9, 0.8, c) + xd.rect(9, 3.5, 3, 9, 0.8, c),
              "ff": '<path d="M2.500 4l5 4-5 4zM8.500 4l5 4-5 4z" fill="%s" stroke="%s" stroke-width=".800" stroke-linejoin="round"/>' % (c, c),
              "rw": '<path d="M13.500 4l-5 4 5 4zM7.500 4l-5 4 5 4z" fill="%s" stroke="%s" stroke-width=".800" stroke-linejoin="round"/>' % (c, c)}
    return svg(16, 16, [shapes[kind]])


def mode_icon(kind, on):
    """Repeat or shuffle, 13 x 11."""
    c = T["accent"] if on else T["text2"]
    parts = [xd.icon("shuffle" if kind == "shuffle" else "repeat", 0.5, -1, 12, c, 2.4)]
    if kind == "one":
        parts.append(base.text(6.5, 8.2, "1", 6.5, 700, c))
    return svg(13, 11, parts)


def field_icon(kind):
    """Which tag field the title line is showing, 15 x 16."""
    c = T["text2"]
    if kind == "artist":
        body = '<circle cx="7.500" cy="5.500" r="2.400" %s/><path d="M3 13.500c0-2.800 2-4.300 4.500-4.300s4.500 1.500 4.500 4.300" %s/>' % (stroke(c, 1.3), stroke(c, 1.3))
    else:
        body = '<circle cx="7.500" cy="8" r="5" %s/><circle cx="7.500" cy="8" r="1.300" fill="%s"/>' % (stroke(c, 1.3), c)
    return svg(15, 16, [body])


def playing_screen(b, work):
    sty = b.get("MUSIC.STY")
    t = base.tables_of(sty)
    if (t[1][1], t[2][1], t[3][1], t[4][1]) != (15, 4, 1, 2) or t[2][0] - t[1][0] != 15 * 32 or t[4][0] - t[3][0] != 28:
        fail("MUSIC.STY: the layout tables are not the expected ones")
    if struct.unpack_from("<H", sty, t[3][0] + 24)[0] != COUNTER_DIGITS[0]:
        fail("MUSIC.STY: the track counter's digit counts are not the stock ones")
    put = base.Pictures(sty, work)

    # the red glow out of every picture; the first eleven (the spectrum) in the accent colour
    for index in range(len(base.pictures(sty))):
        data, w, h = base.picture_bytes(sty, index)
        put.raw(index, without_red(data, T["accent"] if index <= 10 else None), w, h)

    # layout. Picture box: id, x, y, ...; text box: id, x, y, w, h, back x, back y, back id, colour, attributes
    base.set_fields(sty, 3, 28, 0, w0=COUNTER_X, w8=COUNTER_X, w12=COUNTER_DIGITS[1])   # track counter
    base.set_fields(sty, 4, 36, 1, w0=8, w1=146, w13=8, w14=146)                         # elapsed/total
    base.set_fields(sty, 2, 20, 0, w1=16, w2=113, w3=96, w5=16, w6=113, w9=0xa7)         # title: centred, 96 wide
    for box, x, y in ((1, 100, 145), (2, 114, 145), (5, 0, 113), (6, 80, 0), (9, 80, 0), (7, 84, 146), (8, 127, 159)):
        base.set_fields(sty, 1, 32, box, w1=x, w2=y)

    # progress bar pieces and knob
    put.raw(67, bar(128, T["line"], BAR_X, BAR_X + BAR_LEN + 6), 128, 6)
    put.raw(49, bar(128, T["line"], BAR_X, BAR_X + BAR_LEN + 6), 128, 6)
    put.raw(65, bar(1, T["accent"]), 1, 6)
    put.raw(66, bar(1, T["line"]), 1, 6)
    put.raw(70, bar(6, T["accent"]), 6, 6)
    put.raw(69, bar(6, T["line"]), 6, 6)
    put.svg(68, svg(6, 6, ['<circle cx="3" cy="3" r="2.800" fill="%s"/>' % T["text"]]), 6, 6, "progress-knob")

    # digits: time 51..60 with colon 17 and slash 74/88, track counter 77..86
    for k in range(10):
        put.raw(51 + k, base.pixel_glyph(str(k), 6, 8, T["text2"]), 6, 8)
        put.raw(77 + k, base.pixel_glyph(str(k), 6, 8, T["text2"]), 6, 8)
    put.raw(17, base.dots(4, 8, [(1, 2), (1, 5)], T["text2"]), 4, 8)
    for index in (74, 88):
        put.raw(index, base.dots(4, 8, [(2, 1), (2, 2), (1, 3), (1, 4), (0, 5), (0, 6)], T["text2"]), 4, 8)

    # icons. The play-state box shows its first picture while the track plays, its second while it is paused.
    put.svg(12, svg(40, 40, [xd.rect(0, 0, 40, 40, 9, T["surface"]), xd.icon("music", 8, 8, 24, T["accent"])]), 40, 40,
            "cover-default")
    put.svg(48, status_icon("music", T["text"]), 20, 16, "status-music")
    for index, kind in ((63, "pause"), (62, "play"), (27, "ff"), (28, "rw")):
        put.svg(index, state_icon(kind), 16, 16, "state-" + kind)
    for index, label in ((37, "A-B"), (39, "-B"), (40, "A-")):
        put.svg(index, svg(16, 16, [base.text(8, 11.5, label, 8.5, 700, T["accent"])]), 16, 16, "state-ab-%d" % index)
    put.svg(36, mode_icon("repeat", False), 13, 11, "mode-normal")
    put.svg(33, mode_icon("repeat", True), 13, 11, "mode-repeat")
    put.svg(35, mode_icon("one", True), 13, 11, "mode-repeat-one")
    put.svg(73, mode_icon("shuffle", True), 13, 11, "mode-shuffle")
    put.svg(14, field_icon("artist"), 15, 16, "field-artist")
    put.svg(13, field_icon("album"), 15, 16, "field-album")
    for index, color in ((34, T["text2"]), (89, T["accent"]), (90, T["accent"]), (24, T["text2"]), (30, T["text2"]), (16, T["text2"])):
        data, w, h = base.picture_bytes(sty, index)
        put.raw(index, tinted(data, color), w, h)
    for index in range(18, 27):                                     # equaliser name on the playing screen: not shown
        base.resize_picture(sty, index, 1, 1)
        put.raw(index, bytes(2), 1, 1)

    # "Playlist 1" becomes "Favorites"
    renamed = 0
    for name, table in zip(base.language_names(b.stock_file("MUSIC.STY")), base.language_tables(sty)):
        if name in FAVORITES and base.set_string(sty, table, PLAYLIST_1, FAVORITES[name], []):
            renamed += 1
    b.put("MUSIC.STY", sty)
    return put.count, renamed


# ------------------------------------------------------------------ routines

def routines(b, work):
    ap = b.get("MUSIC.AP")
    segs, _ = ap_dis.segments(ap)
    word = lambda addr: base.word_at(ap, segs, addr)

    text = open(os.path.join(base.PATCHES, "music_playing.S")).read()
    for name, value in (("BAR_Y", BAR_Y), ("BAR_X", BAR_X), ("BAR_LEN", BAR_LEN)):
        if ".equ    %s, %d" % (name, value) not in text:
            fail("%s differs between patches/music_playing.S and this script" % name)
    if (word(0x1806147c), word(0x18cc1b94), word(0x18cc1b98)) != (0x20002c, 0x200190, 0x200191):
        fail("MUSIC.AP: the variables the playing-screen patch relies on are not where expected")
    built = base.assemble("music_playing", work)[PLAYING["lo"]:PLAYING["hi"]]
    playing = base.replace_stretch(ap, segs, work, "playing", built=built, checker="check_playing_patch.py", **PLAYING)

    built = base.assemble("music_title", work)[TITLE["lo"]:TITLE["hi"]]
    title = base.replace_stretch(ap, segs, work, "title", built=built, checker="check_title_patch.py", **TITLE)
    b.put("MUSIC.AP", ap)
    return playing, title


def build(b):
    work = b.folder("music")
    first, second = playlists_up(b)
    pictures, renamed = playing_screen(b, work)
    playing, title = routines(b, work)
    b.note("music menu: Playlists first in %d list(s), second in %d; playing screen: %d pictures, 'Favorites' in %d "
           "languages; time and bar routine (%s); title from the tag (%s)", first, second, pictures, renamed, playing, title)
