#!/usr/bin/env python3
"""Stage 25 of the Graphite design, built on the stage 24 image: Search with a T9 keypad in the music lists.

  1. "Search" in the options (Menu key) of the music lists: Playlists, All songs, Artists, Albums and Genres, at
     every level (an artist's albums, an album, a playlist). MUSIC.MCG option lists 21 to 25 (song lists) and 26 to
     30 (Playlists) end in a row "Search": MUSIC.STY text 44, COMMON.STY icon 107 (the stock magnifier), and the stock
     routine of the built-in "Playlist 2" row (0x181613e7), which returns 0x8606. The option lists have no room
     behind them, so lists 21 to 30 are laid out anew in the room of lists 21 to 40; lists 31 to 40 (the options of
     the built-in playlists 2 and 3, unreachable since stage 19) share the rows of lists 26 to 30.
  2. MUSIC.STY English text 44, "Reached maximum number of 'Playlists' ..." (shown only when a built-in playlist was
     full), becomes "Search".
  3. The search itself (design/playlist/search.c): the two list option handlers (browse.c) hand 0x8606 to it. A
     phone keypad (1, 2 abc ... 9 wxyz, Del, 0, OK) finds the rows of the list's current level whose words begin
     with the letters typed, one key per letter; four result lines below it; a chosen row is opened as Select opens
     it (a list) or played (a song), and the list stands on it afterwards. The theme's colours go in at compile time.
The playlist code is placed anew as in stages 23 and 24; stage 24's menu_box and list_box stay where they are. The
functions the search runs for every row and every character are kept in one bank, since every call into another
bank of the group loads that bank.

usage: build_stage25.py [OUT_DIR]      (default: ../x91_dump/stage25)
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
import build_stage11 as s11  # noqa: E402
import build_stage24 as s24  # noqa: E402   (sets up build_stage20 to 23; only their helpers are used)
from build_stage18 import CFLAGS, BANK_TABLES, put_code  # noqa: E402

s20, s21, s23 = s24.s20, s24.s21, s24.s23
LIVE = os.path.join(HERE, "playlist", "stage25")  # the sources as this stage shipped them (stage 26 changed the live ones)

SOURCES = ("playlist.c", "library.c", "keys.c", "browse.c", "search.c")
HOT = ("scan", "match", "next_cp", "key_of", "start_of", "next_row", "read_rows")     # every row and character
SEARCH_GROUPS = (HOT,
                 ("draw_key", "fill", "panel", "text", "put4", "digit_of", "draw_line"),
                 ("draw_count", "draw_query", "put_number", "searching", "spelled", "found_one", "scanned"),
                 ("draw_match", "match_row", "draw_results", "draw_all", "restart", "mark_all", "type", "erase"),
                 ("run", "on_key", "move", "other", "focus", "set_sel"),
                 ("search_list", "open_row"))
COLOURS = ("bg", "surface", "line", "text", "text2", "accent", "on_accent")

OPTION_LISTS = range(21, 31)                     # MUSIC.MCG: song lists' options 21 to 25, Playlists' 26 to 30
BUILTIN_LISTS = range(31, 41)                    # the options of the built-in playlists 2 and 3 (5 states each)
SEARCH_TEXT, SEARCH_ICON = 44, 107               # MUSIC.STY text; COMMON.STY picture (a magnifier, stock)
SEARCH_FN = 0x181613e7                           # MUSIC.AP: mov r1, r0; movw r0, #0x8606; bx lr
SEARCH_FN_CODE = bytes.fromhex("014648f206607047")
ROW_TAIL = s21.ROW_TAIL                          # field 7 of the option rows
ADD_ROW = (0x7fff, 5, 7, 0, s21.ADD_RESULT_FN | 0, 0, ROW_TAIL)
STOCK_TEXT = "Reached maximum number of 'Playlists', overwrite an existing playlist?"
LIST_BANK_GROUP = 0x1200                         # list_box (stage 24) sits at the end of the list control's bank
MENU_BOX_LEN = 52
CODE_SHA = {                                     # the placed code per theme (its colours are in the code)
    "amber": "515de04d9f603af2126adcae755b707dd3d10476727a9d1509fa794ff3bb98d6",
    "mint": "7eec769fc4debf33fa9e3a759a5b621450d258bb36448f6ea6003adb42d274af",
    "ice": "eb8d05c3212db24deeff218f6725e0643014fb42cc9eee8e54bb4f8c1955c95d",
    "berry": "17f9a3a50b69a3e477b98db9b7a7909b117cddb9e12e8edd4545742ed9e22e08",
}


def theme_flags():
    return ["-DCOL_%s=%#x" % (k.upper(), s11.s10_colour(s1.T[k])) for k in COLOURS]


def option_menus(lfi):
    """Lists 21 to 30 with a last row "Search", in the room of lists 21 to 40; lists 31 to 40 share 26 to 30's rows."""
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    heads = {li: struct.unpack_from("<HHII", mcg, hsz + li * 12) for li in range(n)}
    rows = {li: s21.rows_of(mcg, hsz, li)[4] for li in list(OPTION_LISTS) + list(BUILTIN_LISTS)}
    start = heads[21][2]
    at = start
    for li in list(OPTION_LISTS) + list(BUILTIN_LISTS):            # back to back, nothing between
        if heads[li][2] != at:
            sys.exit("MUSIC.MCG: list %d is not right behind list %d" % (li, li - 1))
        at += heads[li][1] * 20
    end = at
    for li in range(21, 26):
        if tuple(rows[li][-1]) != ADD_ROW or rows[li][-2][1] != 76:
            sys.exit("MUSIC.MCG: list %d is not stage 21's song options" % li)
    for li in range(26, 31):
        if [r[1] for r in rows[li][-3:]] != [76, s21.DELETE_TEXT, s21.MOVE_TEXT]:
            sys.exit("MUSIC.MCG: list %d is not stage 21's Playlists options" % li)
    for li in BUILTIN_LISTS:
        if [r[1] for r in rows[li][-3:]] != [76, 34, 29] or heads[li][0] not in (74, 75):
            sys.exit("MUSIC.MCG: list %d is not a built-in playlist's options" % li)
    for li, (eid, cnt, off, link) in heads.items():               # nothing leads to lists 31 to 40 or into their rows
        if link != 0xffffffff and (link & 0xffff) in BUILTIN_LISTS:
            sys.exit("MUSIC.MCG: list %d hangs below list %d" % (li, link & 0xffff))
        for r in s21.rows_of(mcg, hsz, li)[4]:
            if r[0] in BUILTIN_LISTS:
                sys.exit("MUSIC.MCG: a row of list %d leads to list %d" % (li, r[0]))
    search = (0x7fff, SEARCH_TEXT, 0, SEARCH_ICON, SEARCH_FN, 0, ROW_TAIL)
    new, place = b"", {}
    for li in OPTION_LISTS:
        body = rows[li] + [list(search)]
        place[li] = (start + len(new), len(body))
        new += b"".join(struct.pack("<HHHHIII", *r) for r in body)
    if start + len(new) > end:
        sys.exit("MUSIC.MCG: the option lists need %d bytes, the room is %d" % (len(new), end - start))
    mcg[start:end] = new + bytes(end - start - len(new))
    for li in OPTION_LISTS:
        eid, _, _, link = heads[li]
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, place[li][1], place[li][0], link)
    for li in BUILTIN_LISTS:
        eid, _, _, link = heads[li]
        same = 26 + (li - 31) % 5                                 # the same five states: plain, music, paused, radio ...
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, place[same][1], place[same][0], link)
    lfi.put("MUSIC.MCG", bytes(mcg))
    return len(new), end - start


def search_text(lfi):
    sty = bytearray(lfi.get("MUSIC.STY"))
    off, _ = s24.english(sty)
    have, o, n = s24.text_of(sty, off, SEARCH_TEXT)
    raw = "Search\0".encode("utf-16-le")
    if have != STOCK_TEXT or len(raw) > n:
        sys.exit("MUSIC.STY: English text %d is %r" % (SEARCH_TEXT, have))
    sty[o:o + n] = raw + bytes(n - len(raw))
    struct.pack_into("<I", sty, off + SEARCH_TEXT * 8 + 4, len(raw))
    lfi.put("MUSIC.STY", bytes(sty))


def stock_lengths(stock_ap):
    out = {}
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", stock_ap, t + i)
            if off and ln:
                out[addr] = ln
    return out


def menu_box_banks(ap, stock):
    """Banks whose grown end is stage 24's menu_box: a list box call of the bank (movs r3, #8; ldr r1, [pc ...];
    add r0, sp or mov r0, sp; bl) leads into it."""
    segs, _ = ap_dis.segments(bytes(ap))
    out = set()
    for kind, addr, off, n in segs:
        if kind != "bank" or n <= stock.get(addr, n) or addr == s24.LIST_BANK:    # (that one leads to list_box)
            continue
        tail = (stock[addr] + 3) & ~3
        for i in range(0, stock[addr] - 10, 2):
            o = off + i
            if ap[o:o + 2] != b"\x08\x23" or ap[o + 3] != 0x49 or not (ap[o + 5] == 0xa8 or ap[o + 4:o + 6] == b"\x68\x46"):
                continue
            if ap[o + 7] >> 3 == 0x1e and ap[o + 9] >> 6 == 3 and tail <= s21.bl_target(ap, segs, addr + i + 6) - addr < n:
                if n - tail != MENU_BOX_LEN:
                    sys.exit("MUSIC.AP: bank %#x ends in %d bytes, not a menu_box" % (addr, n - tail))
                out.add(addr)
    return out


def replace_code(lfi, work, stock_ap):
    """The playlist code out of its banks and placed anew, with the search; menu_box and list_box stay."""
    objs, secs = s20.compile_code(work)
    depths = s20.stack_depth(work)
    if max(depths.values()) > s20.STACK_MAX:
        sys.exit("the new code's deepest call chain needs %d bytes of stack" % max(depths.values()))
    ap = bytearray(lfi.get("MUSIC.AP"))
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    stock = stock_lengths(stock_ap)
    ranges = s23.old_code(ap, stock_ap)
    calls, rows = s23.old_targets(ap, mcg, ranges)
    segs, _ = ap_dis.segments(bytes(ap))
    if not s23.inside(ranges, s21.bl_target(ap, segs, s23.STANDBY_CALL)):
        sys.exit("MUSIC.AP %#x: does not call the stage 24 code" % s23.STANDBY_CALL)
    calls[s23.STANDBY_CALL] = "standby_previous"
    boxes = menu_box_banks(ap, stock)
    kept = {}                                         # bank: its table entry and bytes, which must not change
    taken = []
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", ap, t + i)
            if not (off and ln) or ln == stock.get(addr, ln):
                continue
            if addr in boxes or addr & 0xffff == LIST_BANK_GROUP:
                kept[addr] = (bytes(ap[t + i:t + i + 12]), bytes(ap[off:off + ln]))
                continue
            if addr >> 24 != 0x18 or addr & 0xffff != 0x1000 or ln > s20.BANK_MAX:
                sys.exit("MUSIC.AP: bank %#x has an unexpected length %#x" % (addr, ln))
            ap[off + stock[addr]:off + ln] = bytes(ln - stock[addr])
            struct.pack_into("<I", ap, t + i + 8, stock[addr])
            taken.append(addr)
    if sorted(boxes) != [0x18601000, 0x18621000, 0x18641000] or [a for a in kept if a not in boxes] != [s24.LIST_BANK]:
        sys.exit("MUSIC.AP: stage 24's menu_box and list_box are not where expected (%s)" % ", ".join("%#x" % a for a in kept))
    planning = bytearray(ap)                          # the planner takes banks whose end is free: these look full
    for bank in boxes:
        _, off, ln, top = s24.bank_entry(planning, bank)
        planning[off + ln:off + top] = b"\xff" * (top - ln)
    banks = s20.plan(planning, secs)
    symbols = s20.link(work, objs, banks)
    put_code(ap, banks)
    hot = {b["addr"] for b in banks for f in HOT if any(s[6:].split(".")[0] == f for s in b["secs"])}
    if len(hot) != 1:
        sys.exit("the search's per-row functions are spread over %d banks" % len(hot))
    segs, _ = ap_dis.segments(bytes(ap))
    for e in s20.ENTRIES:
        if ap_dis.find(segs, symbols[e]) is None:
            sys.exit("%s is outside the program's banks" % e)
    for at, fn in calls.items():
        o = ap_dis.find(segs, at)
        ap[o:o + 4] = s20.thumb_bl(at, symbols[fn])
    for off, fn in rows:
        struct.pack_into("<I", mcg, off, symbols[fn] | 1)
    for addr, (entry, body) in kept.items():
        hdr, off, ln, _ = s24.bank_entry(ap, addr)
        if bytes(ap[hdr:hdr + 12]) != entry or bytes(ap[off:off + ln]) != body:
            sys.exit("MUSIC.AP: bank %#x changed" % addr)
    o = ap_dis.find(segs, SEARCH_FN & ~1)
    if bytes(ap[o:o + len(SEARCH_FN_CODE)]) != SEARCH_FN_CODE:
        sys.exit("MUSIC.AP: %#x is not the routine that returns 0x8606" % SEARCH_FN)
    lfi.put("MUSIC.AP", bytes(ap))
    lfi.put("MUSIC.MCG", bytes(mcg))
    return banks, depths, taken, hot.pop()


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage25")
    work = os.path.join(out, "code")
    os.makedirs(work, exist_ok=True)
    s20.SRC = LIVE
    s20.SOURCES = SOURCES + ("liststyle.c",)          # the host test runs everything; liststyle.c stays as stage 24 put it
    print("host test:", s20.host_test(work))
    s20.SOURCES = SOURCES
    s20.GROUPS = s20.GROUPS + SEARCH_GROUPS
    s20.CFLAGS = CFLAGS + theme_flags()

    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    stock_ap = xm.Lfi(stock).get("MUSIC.AP")
    base = os.environ.get("X91_STAGE24") or os.path.join(ROOT, "x91_dump", "stage24", "x91_lfi_stage24.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 24 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    used, room = option_menus(lfi)
    search_text(lfi)
    banks, depths, taken, hot = replace_code(lfi, work, stock_ap)

    print("option lists 21 to 30 end in \"Search\" (text %d, icon %d, routine %#x): %d of %d bytes; lists 31 to 40 share 26 to 30"
          % (SEARCH_TEXT, SEARCH_ICON, SEARCH_FN, used, room))
    print("colours: %s" % ", ".join("%s %s" % (k, s1.T[k]) for k in COLOURS))
    print("stage 24 code taken out of %d banks; menu_box and list_box kept" % len(taken))
    print("new code: %d bytes in %d banks; deepest stack chain %d bytes (%s)"
          % (sum(len(b["code"]) for b in banks), len(banks), max(depths.values()),
             ", ".join("%s %d" % (e, d) for e, d in depths.items())))
    for b in sorted(banks, key=lambda b: b["addr"]):
        print("  bank %#x: length %#x -> %#x (%s)" % (b["addr"], b["len"], b["new_len"],
                                                    ", ".join(s[6:].split(".")[0] for s in b["secs"])))
    print("the search's per-row functions in bank %#x" % hot)
    code_sha = hashlib.sha256(b"".join(struct.pack("<I", b["addr"]) + b["code"]
                                       for b in sorted(banks, key=lambda b: b["addr"]))).hexdigest()
    print("code sha256 (%s): %s" % (s1.THEME, code_sha))
    if CODE_SHA.get(s1.THEME) != code_sha:
        sys.exit("the frozen stage 25 sources no longer give the stage 25 code for %s" % s1.THEME)
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage25.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
