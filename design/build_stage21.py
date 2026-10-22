#!/usr/bin/env python3
"""Stage 21 of the Graphite design, built on the stage 20 image: playlist editing in the lists, and the volume
curve.

  1. Song lists (All songs, Artists, Albums, Genres): "Add to playlist" in a row's options again, now for the
     .m3u playlists: a song, or every song of an album, artist or genre (design/playlist/browse.c). The row is
     the stock one of the built-in playlists, without its sub-menu (MUSIC.MCG lists 21 to 25).
  2. The Playlists list: its options become lists 26 to 30 (the built-in playlists' options, unused since stage
     19; MUSIC.AP 0x1816116a to 0x18161192 name the lists), with "Delete" (a playlist: its .m3u file; a song
     inside a playlist: out of that playlist; both after a question) and "Move song" (Previous and Next move the
     song, Select puts it there).
  3. The two result handlers of the list options (MUSIC.AP 0x1816102e and 0x18161092) call the new code, which
     passes everything else to the stock handlers.
  4. Texts (MUSIC.STY, English): 14 "<title> / removed from / <playlist>!" with line breaks, as text 12 has them
     (the stock one broke inside the title); 35 the question before removing; 29 "Move song" (was "Clear
     playlist", which served the built-in playlists only).
  5. Volume: the music engine's table from the 32 volume steps to the decoder's volume (MENGINE.AP 0x1a11189e;
     0 to 191, most likely 0.375 dB each, 191 = full) gets even steps of 2 dB from -60 dB at step 1; stock it went
     from -54 dB in steps of 3 dB at the bottom and about 1 dB at the top, so the first steps were loud and the
     upper half changed little.
The new code is placed the way stage 20 did it: the stage 20 code leaves its banks and everything is placed anew.

usage: build_stage21.py [OUT_DIR]      (default: ../x91_dump/stage21)
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
import build_stage20 as s20  # noqa: E402
from build_stage18 import BANK_TABLES, put_code  # noqa: E402

s20.SRC = os.path.join(HERE, "playlist", "stage21")   # the sources as this stage shipped them (stage 23 changed the live ones)
s20.SOURCES = ("playlist.c", "library.c", "keys.c", "browse.c")
s20.ENTRIES = ("add_playing_to_playlist", "remove_playing_from_playlist", "previous_key", "list_option", "m3u_option")
s20.GROUPS = (("remove_line", "line_done"),
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
              ("move_line", "find_line", "move_bytes"))
s20.PINNED = {"previous_key": 0x180a1000}
s20.STACK_MAX = 1024

SONG_OPTIONS = (21, 22, 23, 24, 25)              # MUSIC.MCG: options of the song lists
M3U_OPTIONS = (26, 27, 28, 29, 30)               # the built-in playlist 1's options, now the Playlists list's
M3U_EIDS = (56, 57, 58, 59, 60)                  # the entry ids of the stock Playlists options (lists 50 to 54)
ROW_TAIL = 0x18141221                            # field 7 of these lists' rows
ADD_RESULT_FN = 0x181613df                       # returns 0x8605 (RESULT_ADD_FAVOR1)
DELETE_TEXT, DELETE_ICON, MOVE_TEXT, MOVE_ICON = 36, 17, 29, 26
OPTION_ENTRIES = {0x1816116a: (0x33, 0x1b), 0x18161172: (0x34, 0x1c), 0x18161182: (0x35, 0x1d),
                  0x1816118a: (0x36, 0x1e), 0x18161192: (0x32, 0x1a)}     # movs r0, #list
RESULT_CALLS = {0x1816102e: (0x181612ee, "list_option"), 0x18161092: (0x18161290, "m3u_option")}
STRINGS = {14: ("Removed \"[%s]\" from [%s]!", "[%s]\r\nremoved from\r\n[%s]!"),
           35: (" Remove \"[%s]\"  from Playlist [%s]?", "Remove\r\n[%s]\r\nfrom [%s]?"),
           29: ("Clear playlist", "Move song")}
ENGLISH = 2
VOLUME_AT = 0x1a11189e
VOLUME_STOCK = bytes([0, 47, 55, 63, 71, 79, 87, 95, 111, 119, 127, 132, 135, 138, 143, 146, 148, 151, 154, 156,
                      159, 160, 162, 164, 166, 168, 170, 172, 175, 178, 183, 191])
VOLUME = bytes([0] + [round(191 - (31 - k) * 16 / 3) for k in range(1, 32)])   # 2 dB = 5 1/3 steps of 0.375 dB
# what the frozen sources gave when stage 21 (rebuilt) went to the player
CODE_SHA = "7c91c7b5810af7ae8848753b2e2953833e4aa042bbf5bb692f4c5762e4efba63"


def take_out_code(ap, stock_ap):
    """Every bank of the 0x18NN1000 group back to its stock length, with zeros behind (the stage 20 code)."""
    stock = {}
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", stock_ap, t + i)
            if off and ln:
                stock[addr] = ln
    grown = []
    for t in BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", ap, t + i)
            if not (off and ln) or ln == stock.get(addr, ln):
                continue
            if addr >> 24 != 0x18 or addr & 0xffff != 0x1000 or ln < stock[addr] or ln > s20.BANK_MAX:
                sys.exit("MUSIC.AP: bank %#x has an unexpected length %#x" % (addr, ln))
            ap[off + stock[addr]:off + ln] = bytes(ln - stock[addr])
            struct.pack_into("<I", ap, t + i + 8, stock[addr])
            grown.append(addr)
    return grown


def bl_target(ap, segs, at):
    o = ap_dis.find(segs, at)
    hi, lo = struct.unpack_from("<HH", ap, o)
    if hi >> 11 != 0x1e or lo >> 14 != 3 or not lo >> 12 & 1:
        sys.exit("MUSIC.AP %#x: not a bl" % at)
    s = hi >> 10 & 1
    i1, i2 = ~(lo >> 13 ^ s) & 1, ~(lo >> 11 ^ s) & 1
    off = s << 24 | i1 << 23 | i2 << 22 | (hi & 0x3ff) << 12 | (lo & 0x7ff) << 1
    if s:
        off -= 1 << 25
    return at + 4 + off


def code_patches(ap, symbols, old_previous):
    segs, _ = ap_dis.segments(bytes(ap))
    if bl_target(ap, segs, s20.PREV_CALL) != old_previous:
        sys.exit("MUSIC.AP: the Previous key does not call the stage 20 code")
    o = ap_dis.find(segs, s20.PREV_CALL)
    ap[o:o + 4] = s20.thumb_bl(s20.PREV_CALL, symbols["previous_key"])
    for at, (stock, fn) in RESULT_CALLS.items():
        if bl_target(ap, segs, at) != stock:
            sys.exit("MUSIC.AP %#x: not the stock call of the result handler" % at)
        o = ap_dis.find(segs, at)
        ap[o:o + 4] = s20.thumb_bl(at, symbols[fn])
    for at, (stock, new) in OPTION_ENTRIES.items():
        o = ap_dis.find(segs, at)
        if bytes(ap[o:o + 2]) != bytes([stock, 0x20]):
            sys.exit("MUSIC.AP %#x: not movs r0, #%d" % (at, stock))
        ap[o] = new


def rows_of(mcg, hsz, li):
    eid, cnt, off, link = struct.unpack_from("<HHII", mcg, hsz + li * 12)
    return eid, cnt, off, link, [list(struct.unpack_from("<HHHHIII", mcg, off + k * 20)) for k in range(cnt)]


def menus(lfi, symbols, old_entries):
    mcg = bytearray(lfi.get("MUSIC.MCG"))
    hsz, n = struct.unpack_from("<HH", mcg, 12)
    for li in s20.OPTION_LISTS:                  # the playing screen's rows: to the new entry points
        eid, cnt, off, link, rows = rows_of(mcg, hsz, li)
        for row, text, old, fn in ((s20.ADD_ROW, 5, old_entries[0], "add_playing_to_playlist"),
                                   (s20.REMOVE_ROW, 34, old_entries[1], "remove_playing_from_playlist")):
            if rows[row][:2] != [0x7fff, text] or rows[row][4] != old | 1:
                sys.exit("MUSIC.MCG: list %d row %d is not stage 20's" % (li, row))
            struct.pack_into("<I", mcg, off + row * 20 + 8, symbols[fn] | 1)
    for li in SONG_OPTIONS:                      # "Add to playlist" again, a leaf returning "add to list 1"
        eid, cnt, off, link, rows = rows_of(mcg, hsz, li)
        if rows[-1][1] != 76 or any(mcg[off + cnt * 20:off + cnt * 20 + 20]):
            sys.exit("MUSIC.MCG: list %d is not stage 19's song options" % li)
        struct.pack_into("<HHHHIII", mcg, off + cnt * 20, 0x7fff, 5, 7, 0, ADD_RESULT_FN, 0, ROW_TAIL)
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, cnt + 1, off, link)
    for li, new_eid in zip(M3U_OPTIONS, M3U_EIDS):
        eid, cnt, off, link, rows = rows_of(mcg, hsz, li)
        texts = [r[1] for r in rows]
        if texts[-3:] != [76, 34, 29]:
            sys.exit("MUSIC.MCG: list %d is not the built-in playlist's options" % li)
        k = cnt - 2
        struct.pack_into("<HHHHIII", mcg, off + k * 20, 0x7fff, DELETE_TEXT, 0, DELETE_ICON, rows[k][4], 0, ROW_TAIL)
        struct.pack_into("<HHHHIII", mcg, off + (k + 1) * 20, 0x7fff, MOVE_TEXT, 0, MOVE_ICON, rows[k + 1][4], 0, ROW_TAIL)
        struct.pack_into("<HHII", mcg, hsz + li * 12, new_eid, cnt, off, link)
    lfi.put("MUSIC.MCG", bytes(mcg))


def strings(lfi):
    sty = bytearray(lfi.get("MUSIC.STY"))
    so, sc = struct.unpack_from("<IH", sty, 0x20)
    for k in range(sc):
        off, ln, _, cnt, lid = struct.unpack_from("<IIHHH", sty, so + k * 16)
        if lid != ENGLISH:
            continue
        for idx, (old, new) in STRINGS.items():
            o, n = struct.unpack_from("<II", sty, off + idx * 8)
            have = bytes(sty[o:o + n]).decode("utf-16-le").rstrip("\0")
            raw = (new + "\0").encode("utf-16-le")
            if have != old or len(raw) > n:
                sys.exit("MUSIC.STY: English text %d is %r, or the new one is longer" % (idx, have))
            sty[o:o + n] = raw + bytes(n - len(raw))
            struct.pack_into("<I", sty, off + idx * 8 + 4, len(raw))
        lfi.put("MUSIC.STY", bytes(sty))
        return
    sys.exit("MUSIC.STY: no English texts")


def volume(lfi):
    ap = bytearray(lfi.get("MENGINE.AP"))
    segs, _ = ap_dis.segments(bytes(ap))
    o = ap_dis.find(segs, VOLUME_AT)
    if o is None or bytes(ap[o:o + 32]) != VOLUME_STOCK:
        sys.exit("MENGINE.AP: the volume table is not the stock one")
    if len(VOLUME) != 32 or any(b >= a for a, b in zip(VOLUME[1:], VOLUME)) or VOLUME[31] != 191:
        sys.exit("the new volume table is not rising")
    ap[o:o + 32] = VOLUME
    lfi.put("MENGINE.AP", bytes(ap))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage21")
    work = os.path.join(out, "code")
    os.makedirs(work, exist_ok=True)
    print("host test:", s20.host_test(work))
    objs, secs = s20.compile_code(work)
    depths = s20.stack_depth(work)
    if max(depths.values()) > s20.STACK_MAX:
        sys.exit("the new code's deepest call chain needs %d bytes of stack" % max(depths.values()))

    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    stock_ap = xm.Lfi(stock).get("MUSIC.AP")
    base = os.environ.get("X91_STAGE20") or os.path.join(ROOT, "x91_dump", "stage20", "x91_lfi_stage20.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 20 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    ap = bytearray(lfi.get("MUSIC.AP"))
    segs, _ = ap_dis.segments(bytes(ap))
    old_previous = bl_target(ap, segs, s20.PREV_CALL)
    mcg = lfi.get("MUSIC.MCG")
    hsz = struct.unpack_from("<H", mcg, 12)[0]
    old_entries = [rows_of(mcg, hsz, s20.OPTION_LISTS[0])[4][row][4] & ~1 for row in (s20.ADD_ROW, s20.REMOVE_ROW)]
    grown = take_out_code(ap, stock_ap)
    banks = s20.plan(ap, secs)
    symbols = s20.link(work, objs, banks)
    put_code(ap, banks)
    code_sha = hashlib.sha256(b"".join(struct.pack("<I", b["addr"]) + b["code"] for b in sorted(banks, key=lambda b: b["addr"]))).hexdigest()
    if s20.SRC.endswith("stage21") and code_sha != CODE_SHA:
        sys.exit("the frozen stage 21 sources no longer give the stage 21 code (%s)" % code_sha)
    segs, _ = ap_dis.segments(bytes(ap))
    for e in s20.ENTRIES:
        if ap_dis.find(segs, symbols[e]) is None:
            sys.exit("%s is outside the program's banks" % e)
    code_patches(ap, symbols, old_previous)
    lfi.put("MUSIC.AP", bytes(ap))
    menus(lfi, symbols, old_entries)
    strings(lfi)
    volume(lfi)

    print("stage 20 code taken out of %d banks" % len(grown))
    print("new code: %d bytes in %d banks; deepest stack chain %d bytes (%s)"
          % (sum(len(b["code"]) for b in banks), len(banks), max(depths.values()),
             ", ".join("%s %d" % (e, d) for e, d in depths.items())))
    for b in sorted(banks, key=lambda b: b["addr"]):
        print("  bank %#x: length %#x -> %#x (%s)" % (b["addr"], b["len"], b["new_len"],
                                                    ", ".join(s[6:].split(".")[0] for s in b["secs"])))
    print("entries: %s" % ", ".join("%s %#x" % (e, symbols[e] | 1) for e in s20.ENTRIES))
    print("volume: %s" % list(VOLUME))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage21.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
