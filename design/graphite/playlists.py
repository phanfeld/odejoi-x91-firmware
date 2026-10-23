"""Playlists on the player: the .m3u playlists only, editing them, search, adding songs, naming playlists.

  - The Playlists view shows the .m3u playlists only: the built-in Favorites, Playlist 2 and 3 are no longer put on
    top of it (MUSIC.AP 0x181011ce bne -> b), and the menu rows that served only them are gone or serve the .m3u lists.
  - The library builder (PLAYLIST.AP) reads the .m3u files on every run, "Update list?" included; its "Searching..."
    screen is in the theme.
  - New code in C (design/playlist, see newcode.py), placed into free bank tails of MUSIC.AP:
      playing screen's options (MUSIC.MCG lists 42 and 59): "Add to playlist" (row 4) and "Remove from Playlist"
      (row 5) work on a .m3u chosen from a picker, and keep M3U.LIB, the list the Playlists view shows, up to date;
      song lists' options (21 to 25): "Add to playlist" for a song or every song of an album, artist or genre;
      Playlists options (26 to 30, the built-in playlist 1's options): "Delete", "Move song", "Add songs" (songs of the
      library by the keypad), "New playlist" and "Rename" (the name typed on the keypad);
      all of 21 to 30: "Search" with a T9 keypad over the list's level;
      the Previous key restarts the song after 3 seconds, also with the screen off.
    The two result handlers of the list options (MUSIC.AP 0x1816102e and 0x18161092) call the new code, which passes
    everything else to the stock handlers. The option lists have no room behind them, so lists 21 to 30 are laid out
    anew in the room of lists 21 to 40; lists 31 to 40 (the options of the built-in playlists 2 and 3, unreachable)
    share the rows of lists 26 to 30.
  - English texts of MUSIC.STY that nothing showed any more carry the new rows' names and messages.
"""
import os
import struct

from . import base, newcode
from .base import T, ap_dis, fail, svg, xd
from .lists import bank_entry
from .pictures import arc

# ------------------------------------------------------------------ "Searching..." and the library builder

SPINNER, SPINNER_SIZE = range(1, 9), 38           # PLAYLIST.STY pictures
BACKGROUND, TEXT_STRIPS, TRACKS, FILL = 0, (11, 12), (10, 13), 9

# ------------------------------------------------------------------ menus and texts

OPTION_LISTS, BUILTIN_LISTS = range(21, 31), range(31, 41)
SONG_OPTIONS, M3U_OPTIONS = range(21, 26), range(26, 31)
M3U_EIDS = (56, 57, 58, 59, 60)                  # the entry ids of the stock Playlists options (lists 50 to 54)
SUB_MENUS = range(60, 65)                        # the stock "Add to playlist" sub-menus of the song lists
PLAYING_OPTIONS, ADD_ROW, REMOVE_ROW = (42, 59), 4, 5
COMMON_FN = 0x181815a3                           # field 7 of the playing screen's option rows
ROW_TAIL = 0x18141221                            # field 7 of the list options' rows
OPTION_ROOM = 1420                               # bytes of lists 21 to 40
# stock routines of MUSIC.AP the new rows use (mov r1, r0; movw r0, #result; bx lr)
ADD_FN = 0x181613df                              # 0x8605: the built-in "add to list 1"; "Add to playlist", "New playlist"
SEARCH_FN = 0x181613e7                           # 0x8606: the built-in "Playlist 2" row's
ADD_SONGS_FN = 0x181613ef                        # 0x8607: the built-in "Playlist 3" row's
RENAME_FN = 0x18181201                           # 0x860f: a routine of the music menu's bank no menu row uses
ROUTINES = {ADD_FN: "014648f205607047", SEARCH_FN: "014648f206607047", ADD_SONGS_FN: "014648f207607047",
            RENAME_FN: "014648f20f607047"}
ROWS = {                                         # first, text, text2, icon, routine, -, tail
    "add": (0x7fff, 5, 7, 0, ADD_FN, 0, ROW_TAIL),
    "search": (0x7fff, 44, 0, 107, SEARCH_FN, 0, ROW_TAIL),            # COMMON.STY 107: the stock magnifier
    "add songs": (0x7fff, 30, 0, 15, ADD_SONGS_FN, 0, ROW_TAIL),       # 15: the icon of "Add to playlist"
    "new playlist": (0x7fff, 13, 0, 0, ADD_FN, 0, ROW_TAIL),           # 0: a grid with a plus
    "rename": (0x7fff, 7, 0, 52, RENAME_FN, 0, ROW_TAIL),              # 52: "Tt"
}
DELETE_TEXT, DELETE_ICON, MOVE_TEXT, MOVE_ICON = 36, 17, 29, 26
ROW_NAMES = {29: ("Clear playlist", "Move song"),             # (old, new); a row's name is at most as wide as a
             44: ("Reached maximum number of 'Playlists', overwrite an existing playlist?", "Search"),   # menu title
             30: ("Clear [%s]?", "Add songs"),
             13: ("[%s] cleared!", "New playlist"),
             7: ("Which playlist to add to?", "Rename")}
MESSAGES = {14: ("Removed \"[%s]\" from [%s]!", "[%s]\r\nremoved from\r\n[%s]!"),     # with line breaks, as text 12
            35: (" Remove \"[%s]\"  from Playlist [%s]?", "Remove\r\n[%s]\r\nfrom [%s]?"),
            6: ("Add \r\n \"[%s]\" \r\n to [%s]?", "\"[%s]\"\r\nalready exists")}      # a name that is taken
TITLE_W = 76                                     # lists.TITLE_W

# ------------------------------------------------------------------ the code's entries and callers

ENTRIES = ("add_playing_to_playlist", "remove_playing_from_playlist", "previous_key", "list_option", "m3u_option",
           "standby_previous")
PREV_CALL, PREV_VENEER = 0x180a13b6, 0x180a151a  # the Previous key's bl to the resident "previous" (0x1102b5)
RESULT_CALLS = {0x1816102e: (0x181612ee, "list_option"), 0x18161092: (0x18161290, "m3u_option")}
STANDBY_CALL, STOCK_STANDBY = 0x18b41a6e, 0x18da1cec   # the shared key filter's screen-off Previous: bl with r0 = 0
FILTER_BANK = 0x18b41a00
OPTION_ENTRIES = {0x1816116a: (0x33, 0x1b), 0x18161172: (0x34, 0x1c), 0x18161182: (0x35, 0x1d),
                  0x1816118a: (0x36, 0x1e), 0x18161192: (0x32, 0x1a)}     # movs r0, #list: Playlists options -> 26 to 30
PICKER_STYLE, LINES_AT = 4, 23                   # COMMON.STY list box record of style 0x6004; its lines on a page
MENU_BOX_BANKS = [0x18601000, 0x18621000, 0x18641000]   # MUSIC.AP banks of the 0x1000 group whose end is menu_box

# ------------------------------------------------------------------ placement

PINNED = {"previous_key": 0x180a1000}            # beside the key code that calls it
HOT = ("scan", "match", "next_cp", "key_of", "start_of", "next_row", "read_rows")     # every row and character
# Functions that call each other often share a bank. Each group goes into the bank whose free room fits it best.
GROUPS = (("remove_line", "line_done"),
          ("add_playing_to_playlist", "remove_playing_from_playlist", "pause_playing", "report"),
          ("append", "create_new", "library_add", "library_remove", "file_name", "choice_name"),
          ("list_run", "list_draw", "playlist_page", "pick", "new_playlist_text", "append_number"),
          ("lib_add_song", "find_song", "write_song", "record_tail", "rd16", "wr16"),
          ("lib_add_list", "append_to_order", "write_list", "lib_open", "lib_close", "lib_find_list", "lib_lists"),
          ("lib_remove_song", "users_change", "list_users", "lib_has_song"),
          ("lib_delete_list", "copy_record", "drop_from_order", "move_entries"),
          ("lib_move_song", "lib_order", "lib_list", "lib_count", "lib_song"),
          ("entry_name", "playlist_name", "find_playlist", "song_path_at", "find_new"),
          ("say", "text_desc", "to_wide", "row_name", "list_rows", "find_playlist_at", "list_option", "m3u_option"),
          ("add_selected", "add_one", "add_all", "added"),
          ("remove_selected", "delete_playlist", "remove_here"),
          ("move_song", "move_page", "source_row"),
          ("move_line", "find_line", "move_bytes"),
          HOT,
          ("draw_key", "keypad_key", "space_bar", "fill", "text", "put4", "digit_of", "draw_line", "no_matches"),
          ("draw_count", "draw_query", "put_number", "searching", "spelled", "found_one", "scanned"),
          ("draw_match", "match_row", "row_of", "draw_results", "draw_all", "restart", "mark_all", "type", "erase"),
          ("run", "poll", "on_key", "move", "other", "focus", "set_sel"),
          ("search_list", "open_row"))
SONGS_GROUPS = (("songs_rows", "songs_open"),
                ("search_songs", "songs_head", "songs_file", "read_at", "songs_get", "kept_letters"),
                ("add_songs", "add_target", "add_found", "add_said", "list_grown"))
NAME_GROUPS = (("name_run", "name_poll", "name_key", "name_other"),
               ("name_entry",),
               ("draw_cycle", "cycle_len", "cycle_char", "upper_at"),
               ("name_draw", "name_keys"),
               ("draw_name", "part", "width", "name_show"),
               ("tap", "put_digit", "name_erase", "recase", "name_trim", "name_move"),
               ("new_playlist", "make_playlist", "stand_on"),
               ("rename_playlist", "rename_file"),
               ("move_file", "lib_set_list"),
               ("copy_to", "m3u_file", "find_named"))
MOVE_GROUPS = (("move_line",), ("find_line", "move_bytes"), ("move_song",),
               ("remove_selected", "delete_playlist", "remove_here"))
# The 0x1000 group's free tails do not hold all the code: what only "Add songs", "New playlist", "Rename", "Move song"
# and "Delete" run goes into free tails of the 0x1a00 group (it runs at 0x101a00, above the 0x1000 window, so a call
# between the two loads no bank twice; no stock code of MUSIC.AP keeps data in 0x101a00 to 0x101fff), each bank up to
# that group's longest stock length, the groups largest first. move_page stays beside the list (list_draw calls it
# through a pointer).
FAR_GROUPS = SONGS_GROUPS + NAME_GROUPS + MOVE_GROUPS
FAR_WINDOW, FAR_MAX = 0x1a00, 0x5f0
NEAR_GROUPS = GROUPS + SONGS_GROUPS + NAME_GROUPS


def spinner(frame):
    a = frame * 45
    c = SPINNER_SIZE / 2
    return svg(SPINNER_SIZE, SPINNER_SIZE, ['<circle cx="%g" cy="%g" r="15.5" %s/>' % (c, c, base.stroke(T["line"], 2.4)),
                                            arc(c, c, 15.5, a, a + 100, T["accent"], 2.4),
                                            xd.icon("music", 10, 10, 18, T["text"], 2.0)])


def searching(b, work):
    """The library builder's "Searching..." screen in the theme: background and the two text strips in the theme's
    background colour, the text in its text colour, a spinner like the Bluetooth search, the bar in line and accent."""
    sty = b.get("PLAYLIST.STY")
    pics = base.pictures(sty)
    sizes = {k: pics[k][3:] for k in [BACKGROUND, FILL] + list(SPINNER) + list(TEXT_STRIPS) + list(TRACKS)}
    want = {BACKGROUND: (128, 160), FILL: (1, 3)}
    want.update({k: (38, 38) for k in SPINNER})
    want.update({k: (110, 16) for k in TEXT_STRIPS})
    want.update({k: (118, 3) for k in TRACKS})
    if sizes != want:
        fail("PLAYLIST.STY: the pictures are not the expected ones: %s" % sizes)
    base.set_picture(sty, BACKGROUND, base.fill(128, 160, T["bg"]), 128, 160)
    for k in TEXT_STRIPS:
        base.set_picture(sty, k, base.fill(110, 16, T["bg"]), 110, 16)
    for k in TRACKS:
        base.set_picture(sty, k, base.fill(118, 3, T["line"]), 118, 3)
    base.set_picture(sty, FILL, base.fill(1, 3, T["accent"]), 1, 3)
    for n, k in enumerate(SPINNER):
        base.set_picture(sty, k, base.render_565(spinner(n), SPINNER_SIZE, SPINNER_SIZE, work, "searching-%d" % n),
                         SPINNER_SIZE, SPINNER_SIZE)
    if base.tables_of(sty)[2][1] != 2:
        fail("PLAYLIST.STY: not two text boxes")
    for k in range(2):
        base.set_fields(sty, 2, 20, k, w8=base.c565(T["text"]))
    b.put("PLAYLIST.STY", sty)


def builder_reads_playlists(b):
    """PLAYLIST.AP reads the .m3u files only when it runs after power-up (entry mode 14) or after USB mode (15), as in
    the SDK (plist_main.c); now on every run (0x180210b2: movs r7, #0 -> #1)."""
    ap = b.get("PLAYLIST.AP")
    segs, _ = ap_dis.segments(bytes(ap))
    at = ap_dis.find(segs, 0x180210a8)
    old = bytes.fromhex("04f0600008b1012700e00027")      # and.w r0, r4, #0x60; cbz; movs r7, #1; b; movs r7, #0
    base.patch_bytes(ap, at, old, old[:-2] + b"\x01\x27", "PLAYLIST.AP playlist decision")
    b.put("PLAYLIST.AP", ap)


# ------------------------------------------------------------------ menus

def option_menus(b):
    """Lists 21 to 30 anew in the room of lists 21 to 40: song lists' options with "Add to playlist" (a leaf, the
    built-in list's sub-menu gone) and "Search"; Playlists options with "Delete", "Move song", "Add songs", "New
    playlist", "Rename" and "Search". Lists 31 to 40 share the rows of 26 to 30."""
    mcg = b.get("MUSIC.MCG")
    hsz, n = base.menu_heads(mcg)
    heads = {li: struct.unpack_from("<HHII", mcg, hsz + li * 12) for li in range(n)}
    rows = {li: base.rows_of(mcg, hsz, li)[4] for li in list(OPTION_LISTS) + list(BUILTIN_LISTS)}
    start = at = heads[21][2]
    for li in list(OPTION_LISTS) + list(BUILTIN_LISTS):             # back to back, nothing between
        if heads[li][2] != at:
            fail("MUSIC.MCG: list %d is not right behind list %d" % (li, li - 1))
        at += heads[li][1] * 20
    if at - start != OPTION_ROOM:
        fail("MUSIC.MCG: lists 21 to 40 take %d bytes, not %d" % (at - start, OPTION_ROOM))
    for li in SONG_OPTIONS:
        if rows[li][-1][1] != 5 or not SUB_MENUS[0] <= rows[li][-1][0] <= SUB_MENUS[-1] or rows[li][-2][1] != 76:
            fail("MUSIC.MCG: the last row of list %d is not the built-in \"Add to playlist\"" % li)
    for li in list(M3U_OPTIONS) + list(BUILTIN_LISTS):
        if [r[1] for r in rows[li][-3:]] != [76, 34, 29]:
            fail("MUSIC.MCG: list %d is not a built-in playlist's options" % li)
    for li in BUILTIN_LISTS:
        if heads[li][0] not in (74, 75):
            fail("MUSIC.MCG: list %d is not a built-in playlist's options" % li)
    for li, (eid, cnt, off, link) in heads.items():               # nothing leads to lists 31 to 40 or into their rows
        if link != 0xffffffff and (link & 0xffff) in BUILTIN_LISTS:
            fail("MUSIC.MCG: list %d hangs below list %d" % (li, link & 0xffff))
        for r in base.rows_of(mcg, hsz, li)[4]:
            if r[0] in BUILTIN_LISTS:
                fail("MUSIC.MCG: a row of list %d leads to list %d" % (li, r[0]))
            if r[4] == RENAME_FN or (r[4] == ADD_FN and li not in SONG_OPTIONS and li not in SUB_MENUS):
                fail("MUSIC.MCG: list %d has a row with routine %#x already" % (li, r[4]))

    body_all, place = b"", {}
    for li in OPTION_LISTS:
        if li in SONG_OPTIONS:
            body = rows[li][:-1] + [ROWS["add"], ROWS["search"]]
        else:
            k = len(rows[li]) - 2
            delete = (0x7fff, DELETE_TEXT, 0, DELETE_ICON, rows[li][k][4], 0, ROW_TAIL)
            move = (0x7fff, MOVE_TEXT, 0, MOVE_ICON, rows[li][k + 1][4], 0, ROW_TAIL)
            body = rows[li][:k] + [delete, move] + [ROWS[r] for r in ("add songs", "new playlist", "rename", "search")]
        place[li] = (start + len(body_all), len(body))
        body_all += b"".join(struct.pack("<HHHHIII", *r) for r in body)
    if len(body_all) > OPTION_ROOM:
        fail("MUSIC.MCG: the option lists need %d bytes, the room is %d" % (len(body_all), OPTION_ROOM))
    mcg[start:start + OPTION_ROOM] = body_all + bytes(OPTION_ROOM - len(body_all))
    for li in OPTION_LISTS:
        eid, _, _, link = heads[li]
        if li in M3U_OPTIONS:
            eid = M3U_EIDS[li - M3U_OPTIONS[0]]
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, place[li][1], place[li][0], link)
    for li in BUILTIN_LISTS:
        eid, _, _, link = heads[li]
        same = 26 + (li - 31) % 5                                 # the same five states: plain, music, paused, radio ...
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, place[same][1], place[same][0], link)

    for li in range(n):                                           # the stock sub-menus of the song lists' "Add to
        for r in base.rows_of(mcg, hsz, li)[4]:                   # playlist" are out of reach: their routines (one of
            if r[0] in SUB_MENUS:                                 # them ADD_FN) now only run from the new rows
                fail("MUSIC.MCG: a row of list %d leads to list %d" % (li, r[0]))
    b.put("MUSIC.MCG", mcg)
    return len(body_all)


def playing_options(b, symbols):
    """Rows 4 and 5 of the playing screen's options: leaves that run the new code."""
    mcg = b.get("MUSIC.MCG")
    hsz, _ = base.menu_heads(mcg)
    for li in PLAYING_OPTIONS:
        eid, cnt, off, link, rows = base.rows_of(mcg, hsz, li)
        add, remove = rows[ADD_ROW], rows[REMOVE_ROW]
        if cnt != 8 or add[1:5] != [5, 88, 15, 0x18201121] or add[0] == 0x7fff or remove[1:4] != [34, 88, 16]:
            fail("MUSIC.MCG: list %d is not the stock options of the playing screen" % li)
        struct.pack_into("<HHHHIII", mcg, off + ADD_ROW * 20, 0x7fff, add[1], add[2], add[3],
                         symbols["add_playing_to_playlist"] | 1, add[5], add[6])
        struct.pack_into("<HHHHIII", mcg, off + REMOVE_ROW * 20, 0x7fff, 34, 88, 16,
                         symbols["remove_playing_from_playlist"] | 1, 0, COMMON_FN)
    b.put("MUSIC.MCG", mcg)


def texts(b):
    sty = b.get("MUSIC.STY")
    base.set_english(sty, ROW_NAMES, "MUSIC.STY", wider=(TITLE_W, lambda t: base.text_width(b, t)))
    base.set_english(sty, MESSAGES, "MUSIC.STY")
    b.put("MUSIC.STY", sty)


# ------------------------------------------------------------------ code

def playlists_only(ap, segs):
    at = ap_dis.find(segs, 0x181011ca)
    # ldrb r0, [r4] ; cmp r0, #8 ; bne.n 0x181011f2 ; movs r0, #0 ; strb.w r0, [sp] ; movs r0, #49  ->  b.n 0x181011f2
    old = bytes.fromhex("2078082810d100208df800003120")
    base.patch_bytes(ap, at, old, old[:4] + bytes.fromhex("10e0") + old[6:], "MUSIC.AP menu rows of the Playlists view")


def option_entries(ap, segs):
    for at, (stock, new) in OPTION_ENTRIES.items():
        base.patch_bytes(ap, ap_dis.find(segs, at), bytes([stock, 0x20]), bytes([new, 0x20]),
                         "MUSIC.AP %#x: movs r0, #%d" % (at, stock))


def callers_are_stock(b, ap, segs):
    """The calls the new code takes over are the stock ones."""
    stock = b.stock_file("MUSIC.AP")
    ssegs, _ = ap_dis.segments(stock)
    if base.bl_target(ap, segs, PREV_CALL) != PREV_VENEER:
        fail("MUSIC.AP: the Previous key's call is not the expected code")
    v = ap_dis.find(segs, PREV_VENEER)
    if bytes(ap[v:v + 10]) != bytes.fromhex("40f2b52cc0f2110c6047"):
        fail("MUSIC.AP: %#x is not the veneer to the resident \"previous\"" % PREV_VENEER)
    for at, (target, _) in RESULT_CALLS.items():
        if base.bl_target(ap, segs, at) != target:
            fail("MUSIC.AP %#x: not the stock call of the result handler" % at)
    o, so = ap_dis.find(segs, FILTER_BANK), ap_dis.find(ssegs, FILTER_BANK)
    if bytes(ap[o:o + 0x434]) != stock[so:so + 0x434]:
        fail("MUSIC.AP: the shared key filter is not the stock one")
    at = ap_dis.find(segs, STANDBY_CALL)
    if bytes(ap[at - 2:at]) != b"\x00\x20" or base.bl_target(ap, segs, STANDBY_CALL) != STOCK_STANDBY:
        fail("MUSIC.AP: the screen-off Previous is not movs r0, #0; bl %#x" % STOCK_STANDBY)
    o = ap_dis.find(segs, STOCK_STANDBY)
    if bytes(ap[o + 0x22:o + 0x26]) != bytes.fromhex("40f21b30"):
        fail("MUSIC.AP: %#x does not send 0x31b" % STOCK_STANDBY)
    for fn, code in ROUTINES.items():
        o = ap_dis.find(segs, fn & ~1)
        if bytes(ap[o:o + 8]) != bytes.fromhex(code):
            fail("MUSIC.AP: %#x is not the expected routine (mov r1, r0; movw r0, #result; bx lr)" % fn)


def picker_lines(b):
    com = b.lfi.get("COMMON.STY")
    off, _ = base.tables_of(com)[6]
    lines = com[off + PICKER_STYLE * 28 + LINES_AT]
    rows = int(next(line.split()[2] for line in open(os.path.join(base.PLAYLIST, "playlist.h"))
                    if line.startswith("#define ROWS")))
    if lines != rows:
        fail("the picker's list style has %d lines, the code puts %d rows on a page" % (lines, rows))
    return lines


def plan(ap, secs):
    """FAR_GROUPS (largest first) into free tails of the 0x1a00 group, each group in one bank if it fits, else one by
    one; then the rest into the 0x1000 group: PINNED to their banks, NEAR_GROUPS (largest first) each into the bank
    whose free room fits it best, the rest one by one, largest first, into the fullest bank they fit."""
    size = {newcode.section_base(n): (sz + 3) & ~3 for n, sz, _ in secs}
    far = newcode.free_tails(ap, FAR_WINDOW, FAR_MAX)
    by = {newcode.section_base(n): (n, sz, a) for n, sz, a in secs}
    for group in sorted(FAR_GROUPS, key=lambda g: -sum(size.get(f, 0) for f in g)):
        members = [by.pop(f) for f in group if f in by]
        need = sum((m[1] + 3) & ~3 for m in members)
        fits = [bk for bk in far if not bk["secs"] and bk["top"] - bk["at"] >= need]
        for m in members:
            if not any(newcode.place(bk, *m) for bk in ([min(fits, key=lambda bk: bk["top"] - bk["at"])] if fits else [])
                       + sorted(far, key=lambda bk: bk["top"] - bk["at"])):
                fail("no room left in the 0x1a00 group for %s" % m[0])
    return near_plan(ap, list(by.values())) + [bk for bk in far if bk["secs"]]


def near_plan(ap, secs):
    banks = newcode.free_tails(ap, 0x1000, newcode.BANK_MAX)
    by = {newcode.section_base(n): (n, s, a) for n, s, a in secs}
    left = dict(by)
    for fn, addr in PINNED.items():
        bk = next(bk for bk in banks if bk["addr"] == addr)
        if not newcode.place(bk, *by[fn]):
            fail("%s does not fit bank %#x" % (fn, addr))
        del left[fn]
    for group in sorted(NEAR_GROUPS, key=lambda g: -sum(by[f][1] + 3 for f in g if f in by)):
        members = [by[f] for f in group if f in left]
        need = sum((s + 3) & ~3 for _, s, _ in members)
        fits = [bk for bk in banks if not bk["secs"] and bk["top"] - bk["at"] >= need]
        if not fits:
            continue                             # placed one by one below
        bk = min(fits, key=lambda bk: bk["top"] - bk["at"])
        for m in members:
            newcode.place(bk, *m)
            del left[newcode.section_base(m[0])]
    for name, size, align in sorted(left.values(), key=lambda s: -s[1]):
        if not any(newcode.place(bk, name, size, align) for bk in sorted(banks, key=lambda bk: bk["top"] - bk["at"])):
            fail("no room left for %s (%d bytes)" % (name, size))
    return [bk for bk in banks if bk["secs"]]


def place_code(b, work):
    objs, secs = newcode.compile_code(work)
    depths = newcode.stack_depth(work, ENTRIES)
    if max(depths.values()) > newcode.STACK_MAX:
        fail("the new code's deepest call chain needs %d bytes of stack" % max(depths.values()))
    ap = b.get("MUSIC.AP")
    segs, _ = ap_dis.segments(bytes(ap))
    callers_are_stock(b, ap, segs)
    boxes = [bk for bk in b.menu_boxes["MUSIC.AP"] if bk & 0xffff == 0x1000]
    if boxes != MENU_BOX_BANKS:
        fail("MUSIC.AP: menu_box is not at the end of banks %s" % ", ".join("%#x" % a for a in MENU_BOX_BANKS))
    kept = {}
    planning = bytearray(ap)                     # the planner takes banks whose end is free: these look full
    for bank in b.menu_boxes["MUSIC.AP"] + [0x18661200]:
        hdr, off, ln, top, _ = bank_entry(ap, bank)
        kept[bank] = (bytes(ap[hdr:hdr + 12]), bytes(ap[off:off + ln]))
        if bank in b.menu_boxes["MUSIC.AP"]:
            planning[off + ln:off + top] = b"\xff" * (top - ln)
    banks = plan(planning, secs)
    symbols = newcode.link(work, objs, banks, ENTRIES[0])
    newcode.put_code(ap, banks)
    hot = {bk["addr"] for bk in banks for f in HOT if any(newcode.section_base(s) == f for s in bk["secs"])}
    if len(hot) != 1:
        fail("the search's per-row functions are spread over %d banks" % len(hot))
    segs, _ = ap_dis.segments(bytes(ap))
    for e in ENTRIES:
        if ap_dis.find(segs, symbols[e]) is None:
            fail("%s is outside the program's banks" % e)
    calls = {PREV_CALL: "previous_key", STANDBY_CALL: "standby_previous"}
    calls.update({at: fn for at, (_, fn) in RESULT_CALLS.items()})
    for at, fn in calls.items():
        o = ap_dis.find(segs, at)
        ap[o:o + 4] = base.thumb_bl(at, symbols[fn])
    playlists_only(ap, segs)
    option_entries(ap, segs)
    for bank, (entry, body) in kept.items():
        hdr, off, ln, _, _ = bank_entry(ap, bank)
        if bytes(ap[hdr:hdr + 12]) != entry or bytes(ap[off:off + ln]) != body:
            fail("MUSIC.AP: bank %#x changed" % bank)
    b.put("MUSIC.AP", ap)
    return banks, symbols, depths, hot.pop()


def build(b):
    work = b.folder("playlists")
    searching(b, work)
    builder_reads_playlists(b)
    used = option_menus(b)
    texts(b)
    lines = picker_lines(b)
    banks, symbols, depths, hot = place_code(b, work)
    playing_options(b, symbols)
    far = [bk for bk in banks if bk["addr"] & 0xffff == FAR_WINDOW]
    b.note("playlists: option lists 21 to 30 in %d of %d bytes; picker %d rows a page; Searching screen", used,
           OPTION_ROOM, lines)
    b.note("new code: %d bytes in %d banks, of them %d in %d banks of the 0x1a00 group; deepest stack chain %d bytes (%s); "
           "the search's per-row functions in bank %#x", sum(len(bk["code"]) for bk in banks), len(banks),
           sum(len(bk["code"]) for bk in far), len(far), max(depths.values()),
           ", ".join("%s %d" % (e, d) for e, d in depths.items()), hot)
    for bk in sorted(banks, key=lambda bk: bk["addr"]):
        b.note("  bank %#x: length %#x -> %#x (%s)", bk["addr"], bk["len"], bk["new_len"],
               ", ".join(newcode.section_base(s) for s in bk["secs"]))
    b.note("entries: %s", ", ".join("%s %#x" % (e, symbols[e] | 1) for e in ENTRIES))
