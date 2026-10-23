"""Start-up picture, shut-down animation and the main menu.

The main menu has six tiles in two rows: Music, Playlists, Folder, Bluetooth, eBook, Settings. The list of programs
it shows is one list in the compiled settings (CONFIG.BIN, MAINMENU_AP_ID_ARRAY). The Playlists tile is the stock
alarm entry: MAINMENU.AP starts the music program with start code 0x40 for it, and the music program's root-menu
routine (patches/music_playlists_tile.S) skips its menu for that code and goes on as if "Playlists" had been chosen.
Moving up or down steps by one row of a two-row grid. The tile's label is the music program's own word for Playlists
in each language.
"""
import hashlib
import struct

from . import base
from .base import T, ap_dis, fail, svg, xd

# stock grid order of the nine entries and the picture that shows each one highlighted
GRID = [("music", 19), ("video", 25), ("radio", 21), ("picture", 20), ("bluetooth", 17), ("alarm", 16),
        ("folder", 18), ("mic", 22), ("settings", 23)]
# main-menu tiles: (icon, program id in the settings, picture that shows it highlighted)
MENU = [("music", 0, 19), ("playlist", 1, 16), ("folder", 5, 18), ("bluetooth", 11, 17), ("book", 4, 25), ("settings", 10, 23)]
STOCK_MENU = [0, 2, 8, 3, 11, 1, 5, 7, 10]
FIVE_TILES = [0, 5, 11, 4, 10]                   # the menu before the Playlists tile (in CONFIG.TXT only, see menu_list)
TILE_CODE = 0x40
LABEL_DONORS = [6, 24, 27, 26, 35, 4, 28, 15]   # Dictionary, Calculator, Stopwatch, Pedometer, wallpaper, ...: emptied
                                                 # where a language's longer label needs the room
PLAYLISTS_TEXT = 0x48                            # MUSIC.STY: "Playlists"


def boot_picture():
    return svg(128, 160, [
        xd.rect(46, 44, 36, 36, 10, T["accent"]), xd.icon("music", 53, 51, 22, T["on_accent"]),
        '<text x="64" y="107" font-family="Ubuntu" font-weight="700" font-size="17" letter-spacing="1.5" fill="%s" '
        'text-anchor="middle">X91</text>' % T["text"],
        xd.rect(54, 116, 20, 2, 1, T["line"]), xd.rect(54, 116, 9, 2, 1, T["accent"])])


def end_frame(k):
    """Shut-down, 128 x 160, nine frames: the start-up picture going dark."""
    t = k / 8.0
    mix = base.mix
    tile = mix(T["accent"], T["surface"], min(1, t * 1.6)) if t < 0.8 else mix(T["surface"], "#000000", (t - 0.8) / 0.2)
    glyph = mix(T["on_accent"], T["text2"], min(1, t * 1.6)) if t < 0.8 else mix(T["text2"], "#000000", (t - 0.8) / 0.2)
    word = mix(T["text"], "#000000", min(1, t * 1.15))
    parts = [xd.rect(46, 44, 36, 36, 10, tile), xd.icon("music", 53, 51, 22, glyph),
             base.text(64, 107, "X91", 17, 700, word, spacing=1.5)]
    if k < 8:
        parts.append(xd.rect(54, 116, 20, 2, 1, mix(T["line"], "#000000", t)))
        left = 9 * (1 - t)
        if left >= 1:
            parts.append(xd.rect(54, 116, left, 2, 1, mix(T["accent"], "#000000", t * 0.6)))
    return svg(128, 160, parts)


def grid_picture(sel):
    """The nine-entry grid of the first design. The menu shows six tiles now; the highlighted pictures of the three
    stock entries it no longer has (radio, pictures, recorder) keep this look."""
    parts = []
    for i, (ic, _) in enumerate(GRID):
        x, y = 7 + (i % 3) * 40, 4 + (i // 3) * 39
        on = i == sel
        parts += [xd.rect(x, y, 34, 34, 9.5, T["accent"] if on else T["surface"]),
                  xd.icon(ic, x + 7, y + 7, 20, T["on_accent"] if on else T["text"])]
    return svg(128, 144, parts)


def menu_picture(sel):
    parts = []
    for i, (ic, _, _) in enumerate(MENU):
        x, y = 5 + (i % 3) * 41, 20 + (i // 3) * 46
        on = i == sel
        parts += [xd.rect(x, y, 36, 36, 10, T["accent"] if on else T["surface"]),
                  xd.icon(ic, x + 7, y + 7, 22, T["on_accent"] if on else T["text"])]
    return svg(128, 144, parts)


def now_playing_entry():
    return svg(128, 120, [xd.rect(36, 34, 56, 56, 16, T["accent"]), xd.icon("play", 47, 45, 34, T["on_accent"])])


def pictures(b, work):
    logo = b.get("LOGO.STY")
    base.Pictures(logo, work).svg(0, boot_picture(), 128, 160, "boot")
    b.put("LOGO.STY", logo)

    end = b.get("END.STY")
    for k in range(9):
        base.Pictures(end, work).svg(k, end_frame(k), 128, 160, "end-%d" % k)
    b.put("END.STY", end)

    menu = b.get("MAINMENU.STY")
    put = base.Pictures(menu, work)
    tiles = {pic for _, _, pic in MENU}
    for sel, (ic, pic) in enumerate(GRID):
        if pic not in tiles:
            put.svg(pic, grid_picture(sel), 128, 144, "menu-%d-%s" % (sel, ic))
    black = lambda w, h: bytes(w * h * 2)
    put.raw(5, black(128, 16), 128, 16)                   # header strip
    put.raw(1, black(128, 20), 128, 20)                   # label background
    put.raw(6, black(128, 20), 128, 20)                   # second label background
    put.svg(8, now_playing_entry(), 128, 120, "menu-now-playing")
    for sel, (ic, _, pic) in enumerate(MENU):
        put.svg(pic, menu_picture(sel), 128, 144, "menu6-%d-%s" % (sel, ic))

    # label of tile 1: string 0 ("Alarm") becomes the music program's own word for Playlists in each language
    music = b.stock_file("MUSIC.STY")
    theirs = {t[4]: base.read_strings(music, t)[PLAYLISTS_TEXT] for t in base.language_tables(music)}
    labels = 0
    for t in base.language_tables(menu):
        word = theirs.get(t[4], b"").decode("utf-16-le").split("\0")[0].strip() or "Playlists"
        labels += base.set_string(menu, t, 0, word[:1].upper() + word[1:], LABEL_DONORS)
    b.put("MAINMENU.STY", menu)
    return labels


def menu_list(b):
    cfg = b.get("CONFIG.BIN")
    off, ln = struct.unpack_from("<II", cfg, 16 + 1 * 8)          # second entry: MAINMENU_AP_ID_ARRAY
    ids = [m[1] for m in MENU]
    base.patch_bytes(cfg, off, struct.pack("<HH9H", 0, len(STOCK_MENU), *STOCK_MENU),
                     struct.pack("<HH9H", 0, len(ids), *(ids + [0] * (9 - len(ids)))), "CONFIG.BIN main-menu list")
    b.put("CONFIG.BIN", cfg)
    # The readable copy (CONFIG.TXT; the firmware does not read it) as the released images have it: its active line
    # lists the five tiles of the design before the Playlists tile, and the six tiles went into the commented-out line
    # above it (that edit took the first line of the name). Lines keep their length; changing this changes no behaviour,
    # only this file and so the images' checksums.
    txt = b.get("CONFIG.TXT")
    line = lambda menu: b"MAINMENU_AP_ID_ARRAY = 0[%s];" % ", ".join(map(str, menu)).encode()
    active, comment = line(STOCK_MENU), b"//" + line([0, 5, 7, 12, 8, 11, 9, 1, 10]) + b" "
    i, j = txt.find(active), txt.find(comment)
    if i < 0 or j < 0 or j > i:
        fail("CONFIG.TXT: the main-menu lines are not the stock ones")
    txt[i:i + len(active)] = line(FIVE_TILES).ljust(len(active))
    txt[j + 2:j + len(comment)] = line(ids).ljust(len(comment) - 2)
    b.put("CONFIG.TXT", txt)


def mainmenu_code(b):
    ap = b.get("MAINMENU.AP")
    segs, _ = ap_dis.segments(ap)
    at = lambda addr: ap_dis.find(segs, addr)
    # entry 1 was "start program 9 (tools) with code 18 (alarm)"
    base.patch_bytes(ap, at(0x110168), bytes.fromhex("0920"), bytes.fromhex("0020"), "MAINMENU.AP program number")
    base.patch_bytes(ap, at(0x11016e), bytes.fromhex("1221"), bytes((TILE_CODE, 0x21)), "MAINMENU.AP start code")
    # two rows instead of three: down = +3 or back to the top row, up = -3 or on to the bottom row
    base.patch_bytes(ap, at(0x110100), bytes.fromhex("0628"), bytes.fromhex("0328"), "MAINMENU.AP down")
    base.patch_bytes(ap, at(0x110108), bytes.fromhex("801f"), bytes.fromhex("c01e"), "MAINMENU.AP down")
    base.patch_bytes(ap, at(0x11012c), bytes.fromhex("801d"), bytes.fromhex("c01c"), "MAINMENU.AP up")
    b.put("MAINMENU.AP", ap)


def music_code(b, work):
    """MUSIC.AP root-menu routine (bank 0x18101000, offsets 0x2dc to 0x35e): start code 0x40 acts as "Playlists"."""
    built = base.assemble("music_playlists_tile", work)
    lo, hi, bank = 0x2dc, 0x35e, 0x18101000
    ap = b.get("MUSIC.AP")
    segs, _ = ap_dis.segments(ap)
    at = ap_dis.find(segs, bank)
    old = bytes(ap[at:at + 0x67c])
    if hashlib.sha256(old[lo:hi]).hexdigest()[:16] != "141b217e040863cc":
        fail("MUSIC.AP: the root-menu routine is not the expected one")
    if built[0xec:0xf0] != old[0xec:0xf0] or built[0x42c:0x430] != old[0x42c:0x430]:
        fail("MUSIC.AP: the constants the tile patch relies on are not where expected")
    result = base.check("check_music_patch.py", old, old[:lo] + built[lo:hi] + old[hi:], bank, work, "playlists_tile")
    ap[at + lo:at + hi] = built[lo:hi]
    b.put("MUSIC.AP", ap)
    return result


def build(b):
    work = b.folder("mainmenu")
    labels = pictures(b, work)
    menu_list(b)
    mainmenu_code(b)
    checked = music_code(b, work)
    b.note("main menu: %d tiles, label in %d languages; Playlists tile (%s); start-up picture, shut-down", len(MENU),
           labels, checked)
