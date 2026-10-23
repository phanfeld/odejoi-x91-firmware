#!/usr/bin/env python3
"""Stage 27 of the Graphite design, built on the stage 26 image: "New playlist" and "Rename" in the Playlists options,
the names typed on the keypad.

  1. MUSIC.MCG option lists 26 to 30 (the Playlists list and the playlists' songs) get two rows behind "Add songs":
     "New playlist" (MUSIC.STY text 13, COMMON.STY icon 0, the routine of the song lists' "Add to playlist",
     0x181613df, which returns 0x8605) and "Rename" (text 7, icon 52, a stock routine no menu row uses, 0x18181201,
     which returns 0x860f). Lists 21 to 30 are laid out anew in the room stage 25 used; lists 31 to 40 (unreachable
     since stage 19) share the rows of 26 to 30 again.
  2. MUSIC.STY English texts that nothing shows since stages 19 to 21 (the built-in playlists' messages): 13 "[%s]
     cleared!" becomes "New playlist", 7 "Which playlist to add to?" "Rename", 6 (the question before adding to a
     built-in playlist) the message for a name that is taken.
  3. The code (design/playlist): m3u_option hands 0x8605 to new_playlist and 0x860f to rename_playlist (browse.c). A
     name is typed on the search's keypad as on a phone before T9 (name.c); "New playlist" makes "<name>.m3u" and its
     record in M3U.LIB, then goes on to "Add songs" for it; "Rename" copies the playlist's file under the new name,
     removes the old one and gives the record the new name and place.
The playlist code is placed anew as in stage 26 (build_stage25.replace_code); the name screen, the two actions and the
copy go into the 0x1a00 group's bank tails with "Add songs", since only they run them.

usage: build_stage27.py [OUT_DIR]      (default: ../x91_dump/stage27)
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage26 as s26  # noqa: E402   (sets up build_stage20 to 25; only their helpers are used)
from build_stage18 import CFLAGS, BANK_TABLES  # noqa: E402

s20, s21, s24, s25 = s26.s20, s26.s21, s26.s24, s26.s25
LIVE = os.path.join(HERE, "playlist")

SOURCES = s26.SOURCES + ("name.c",)
DRAW = ("draw_key", "keypad_key", "space_bar", "fill", "text", "put4", "digit_of", "draw_line", "no_matches")
SEARCH_GROUPS = tuple(DRAW if g[0] == "draw_key" else g for g in s26.SEARCH_GROUPS)
if SEARCH_GROUPS == s26.SEARCH_GROUPS:
    sys.exit("stage 26's drawing group is not where it was")
# Only "New playlist" and "Rename" run these: into the 0x1a00 group's bank tails, as "Add songs" (stage 26). Each
# group fits one of that group's tails (up to 920 bytes); what runs per key or per character stays together.
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
# The 0x1000 group's tails no longer hold the rest either (1.9 KB are free in all, but in pieces): "Move song" and
# "Delete" go there too, but for the page function that list_draw calls through a pointer (move_page, with
# source_row), which stays beside the list.
MOVE_GROUPS = (("move_line",), ("find_line", "move_bytes"), ("move_song",),
               ("remove_selected", "delete_playlist", "remove_here"))
FAR_GROUPS = s26.FAR_GROUPS + NAME_GROUPS + MOVE_GROUPS

PLAYLIST_LISTS = s26.PLAYLIST_LISTS
NEW_TEXT, NEW_ICON = 13, 0                       # MUSIC.STY text; COMMON.STY picture (a grid with a plus, stock)
RENAME_TEXT, RENAME_ICON = 7, 52                 # COMMON.STY picture 52: "Tt", text
TAKEN_TEXT = 6
SUB_MENUS = range(60, 65)                        # MUSIC.MCG: the stock "Add to playlist" sub-menus (Favorites, Playlist 2
                                                 # and 3) of the song lists, unreachable since stage 21
NEW_FN = 0x181613df                              # MUSIC.AP: mov r1, r0; movw r0, #0x8605; bx lr
NEW_FN_CODE = bytes.fromhex("014648f205607047")
RENAME_FN = 0x18181201                           # MUSIC.AP: mov r1, r0; movw r0, #0x860f; bx lr (no menu row uses it)
RENAME_FN_CODE = bytes.fromhex("014648f20f607047")
TEXTS = {NEW_TEXT: ("[%s] cleared!", "New playlist"),
         RENAME_TEXT: ("Which playlist to add to?", "Rename"),
         TAKEN_TEXT: ("Add \r\n \"[%s]\" \r\n to [%s]?", "\"[%s]\"\r\nalready exists")}


def option_menus(lfi):
    """Lists 26 to 30 with "New playlist" and "Rename" behind "Add songs", lists 21 to 30 anew in stage 25's room."""
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    heads = {li: struct.unpack_from("<HHII", mcg, hsz + li * 12) for li in range(n)}
    rows = {li: s21.rows_of(mcg, hsz, li)[4] for li in s25.OPTION_LISTS}
    start = at = heads[21][2]
    for li in s25.OPTION_LISTS:
        if heads[li][2] != at:
            sys.exit("MUSIC.MCG: list %d is not right behind list %d" % (li, li - 1))
        at += heads[li][1] * 20
        if rows[li][-1][1] != s25.SEARCH_TEXT or rows[li][-1][4] != s25.SEARCH_FN:
            sys.exit("MUSIC.MCG: list %d does not end in stage 25's \"Search\"" % li)
    for li in PLAYLIST_LISTS:
        if [(r[1], r[4]) for r in rows[li][-5:-1]] != [(76, 0x1816141b), (s21.DELETE_TEXT, 0x18161413),
                                                       (s21.MOVE_TEXT, 0x1816140b), (s26.ADD_TEXT, s26.ADD_FN)]:
            sys.exit("MUSIC.MCG: list %d is not stage 26's Playlists options" % li)
    for li in range(n):                              # the two routines are no reachable row's in the Playlists options:
        for r in s21.rows_of(mcg, hsz, li)[4]:       # 0x181613df is the song lists' "Add to playlist" and a row of
            if r[0] in SUB_MENUS:                    # their stock sub-menus (lists 60 to 64), which nothing leads to
                sys.exit("MUSIC.MCG: a row of list %d leads to list %d" % (li, r[0]))
            if r[4] == RENAME_FN or (r[4] == NEW_FN and li not in range(21, 26) and li not in SUB_MENUS):
                sys.exit("MUSIC.MCG: list %d has a row with routine %#x already" % (li, r[4]))
    end = start + s26.OPTION_ROOM
    if any(mcg[at:end]):
        sys.exit("MUSIC.MCG: the room behind the option lists is not free")
    new = [0x7fff, NEW_TEXT, 0, NEW_ICON, NEW_FN, 0, s25.ROW_TAIL]
    rename = [0x7fff, RENAME_TEXT, 0, RENAME_ICON, RENAME_FN, 0, s25.ROW_TAIL]
    body_all, place = b"", {}
    for li in s25.OPTION_LISTS:
        body = rows[li][:-1] + [new, rename] + rows[li][-1:] if li in PLAYLIST_LISTS else rows[li]
        place[li] = (start + len(body_all), len(body))
        body_all += b"".join(struct.pack("<HHHHIII", *r) for r in body)
    if len(body_all) > s26.OPTION_ROOM:
        sys.exit("MUSIC.MCG: the option lists need %d bytes, the room is %d" % (len(body_all), s26.OPTION_ROOM))
    mcg[start:end] = body_all + bytes(s26.OPTION_ROOM - len(body_all))
    for li in s25.OPTION_LISTS:
        eid, _, _, link = heads[li]
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, place[li][1], place[li][0], link)
    for li in s25.BUILTIN_LISTS:
        eid, _, _, link = heads[li]
        same = 26 + (li - 31) % 5
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, place[same][1], place[same][0], link)
    lfi.put("MUSIC.MCG", bytes(mcg))
    return len(body_all)


def texts(lfi):
    sty = bytearray(lfi.get("MUSIC.STY"))
    off, _ = s24.english(sty)
    for idx, (old, text) in sorted(TEXTS.items()):
        have, o, n = s24.text_of(sty, off, idx)
        raw = (text + "\0").encode("utf-16-le")
        if have != old or len(raw) > n:
            sys.exit("MUSIC.STY: English text %d is %r, or %r is longer" % (idx, have, text))
        if idx != TAKEN_TEXT and s24.width(lfi, text) > s24.TITLE_W:     # (as wide as a menu title at most, stage 24)
            sys.exit("MUSIC.STY: %r is %d pixels wide, more than %d" % (text, s24.width(lfi, text), s24.TITLE_W))
        sty[o:o + n] = raw + bytes(n - len(raw))
        struct.pack_into("<I", sty, off + idx * 8 + 4, len(raw))
    lfi.put("MUSIC.STY", bytes(sty))


def take_out_far(lfi, stock_ap):
    """Stage 26's code out of the 0x1a00 group's banks (build_stage25.replace_code takes it out of the 0x1000 group's
    only): each grown bank back to its stock length with zeros behind."""
    ap = bytearray(lfi.get("MUSIC.AP"))
    stock = s25.stock_lengths(stock_ap)
    taken = []
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", ap, t + i)
            if not (off and ln) or addr >> 24 != 0x18 or addr & 0xffff != s26.FAR_WINDOW:
                continue
            if ln != stock[addr]:
                if ln < stock[addr] or ln > s26.FAR_MAX:
                    sys.exit("MUSIC.AP: bank %#x has an unexpected length %#x" % (addr, ln))
                ap[off + stock[addr]:off + ln] = bytes(ln - stock[addr])
                struct.pack_into("<I", ap, t + i + 8, stock[addr])
                taken.append(addr)
    if not taken:
        sys.exit("MUSIC.AP: no bank of the 0x1a00 group holds stage 26's code")
    lfi.put("MUSIC.AP", bytes(ap))
    return taken


def plan(ap, secs):
    """build_stage26.plan with the 0x1a00 group's groups placed largest first (each into the smallest tail it fits)."""
    size = {n[len(".text."):].split(".")[0]: (sz + 3) & ~3 for n, sz, _ in secs}
    s26.FAR_GROUPS = tuple(sorted(FAR_GROUPS, key=lambda g: -sum(size.get(f, 0) for f in g)))
    return s26.plan(ap, secs)


def check_routine(ap, addr, code):
    o = ap_dis.find(ap_dis.segments(ap)[0], addr & ~1)
    if ap[o:o + len(code)] != code:
        sys.exit("MUSIC.AP: %#x is not the routine that returns %#x" % (addr, struct.unpack_from("<H", code, 2)[0]))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage27")
    work = os.path.join(out, "code")
    os.makedirs(work, exist_ok=True)
    s20.SRC = LIVE
    s20.SOURCES = SOURCES + ("liststyle.c",)          # the host test runs everything; liststyle.c stays as stage 24 put it
    print("host test:", s20.host_test(work))
    s20.SOURCES = SOURCES
    s20.GROUPS = s20.GROUPS + SEARCH_GROUPS + NAME_GROUPS
    s20.CFLAGS = CFLAGS + s25.theme_flags()
    s20.stack_depth = s26.stack_depth
    s20.plan = plan

    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    stock_ap = xm.Lfi(stock).get("MUSIC.AP")
    base = os.environ.get("X91_STAGE26") or os.path.join(ROOT, "x91_dump", "stage26", "x91_lfi_stage26.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 26 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    used = option_menus(lfi)
    texts(lfi)
    far_taken = take_out_far(lfi, stock_ap)
    banks, depths, taken, hot = s25.replace_code(lfi, work, stock_ap)
    ap = lfi.get("MUSIC.AP")
    check_routine(ap, NEW_FN, NEW_FN_CODE)
    check_routine(ap, RENAME_FN, RENAME_FN_CODE)
    check_routine(ap, s26.ADD_FN, s26.ADD_FN_CODE)

    print("option lists 26 to 30 get \"New playlist\" (text %d, icon %d, routine %#x) and \"Rename\" (text %d, icon %d, "
          "routine %#x): lists 21 to 30 in %d of %d bytes" % (NEW_TEXT, NEW_ICON, NEW_FN, RENAME_TEXT, RENAME_ICON,
                                                              RENAME_FN, used, s26.OPTION_ROOM))
    print("texts: %s" % "; ".join("%d %r" % (k, v[1]) for k, v in sorted(TEXTS.items())))
    print("colours: %s" % ", ".join("%s %s" % (k, s1.T[k]) for k in s25.COLOURS))
    print("stage 26 code taken out of %d banks of the 0x1000 group and %d of the 0x1a00 group (%s); menu_box and "
          "list_box kept" % (len(taken), len(far_taken), ", ".join("%#x" % a for a in far_taken)))
    far = [b for b in banks if b["addr"] & 0xffff == s26.FAR_WINDOW]
    print("new code: %d bytes in %d banks, of them %d in %d banks of the 0x1a00 group; deepest stack chain %d bytes (%s)"
          % (sum(len(b["code"]) for b in banks), len(banks), sum(len(b["code"]) for b in far), len(far),
             max(depths.values()), ", ".join("%s %d" % (e, d) for e, d in depths.items())))
    for b in sorted(banks, key=lambda b: b["addr"]):
        print("  bank %#x: length %#x -> %#x (%s)" % (b["addr"], b["len"], b["new_len"],
                                                    ", ".join(s[6:].split(".")[0] for s in b["secs"])))
    print("the search's per-row functions in bank %#x" % hot)
    code_sha = hashlib.sha256(b"".join(struct.pack("<I", b["addr"]) + b["code"]
                                       for b in sorted(banks, key=lambda b: b["addr"]))).hexdigest()
    print("code sha256 (%s): %s" % (s1.THEME, code_sha))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage27.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
