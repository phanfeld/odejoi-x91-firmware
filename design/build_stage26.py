#!/usr/bin/env python3
"""Stage 26 of the Graphite design, built on the stage 25 image: "Add songs" in the Playlists options.

  1. MUSIC.MCG option lists 26 to 30 (the Playlists list and the playlists' songs) get a row "Add songs" in front of
     "Search": MUSIC.STY text 30, COMMON.STY icon 15 (the icon of "Add to playlist"), and the stock routine of the
     built-in "Playlist 3" row (0x181613ef), which returns 0x8607. Lists 21 to 30 are laid out anew in the room stage
     25 used; lists 31 to 40 (unreachable since stage 19) share the rows of 26 to 30 again.
  2. MUSIC.STY English text 30, "Clear [%s]?" (asked only before clearing a built-in playlist, which cannot be reached
     since stage 19), becomes "Add songs".
  3. The code (design/playlist): m3u_option hands 0x8607 to add_songs (browse.c), which shows the search's keypad over
     the library's songs as All songs lists them (MUSIC.LIB, search.c); every song chosen goes to the end of the
     playlist the list is in, or of the one the options were opened on in the list of playlists, with the stock
     message, and the search comes back with the same keys and the same line chosen.
The playlist code is placed anew as in stage 25 (build_stage25.replace_code); the deepest stack chain is measured with
the inline helpers counted where they are written (the older builders took "static inline __attribute__" for a
function of that name).

usage: build_stage26.py [OUT_DIR]      (default: ../x91_dump/stage26)
"""
import hashlib
import os
import re
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage25 as s25  # noqa: E402   (sets up build_stage20 to 24; only their helpers are used)
from build_stage18 import CFLAGS  # noqa: E402

s20, s21, s24 = s25.s20, s25.s21, s25.s24
s20_plan = s20.plan
LIVE = os.path.join(HERE, "playlist", "stage26")  # the sources as this stage shipped them (stage 27 changed the live ones)

SOURCES = ("playlist.c", "library.c", "keys.c", "browse.c", "search.c")
SEARCH_GROUPS = (s25.HOT,
                 ("draw_key", "fill", "text", "put4", "digit_of", "draw_line", "no_matches"),
                 ("draw_count", "draw_query", "put_number", "searching", "spelled", "found_one", "scanned"),
                 ("draw_match", "match_row", "row_of", "draw_results", "draw_all", "restart", "mark_all", "type", "erase"),
                 ("run", "poll", "on_key", "move", "other", "focus", "set_sel"),
                 ("search_list", "open_row"),
                 ("songs_rows", "songs_open"),
                 ("search_songs", "songs_head", "songs_file", "read_at", "songs_get", "kept_letters"),
                 ("add_songs", "add_target", "add_found", "add_said", "list_grown"))
# The 0x1000 group's free bank tails no longer hold all the code: these groups, which only "Add songs" runs, go into
# free tails of the 0x1a00 group (it runs at 0x101a00, above the 0x1000 window, so a call between the two loads no
# bank twice; no stock code of MUSIC.AP keeps data in 0x101a00 to 0x101fff), each bank up to that group's longest
# stock length.
FAR_GROUPS = SEARCH_GROUPS[-3:]
FAR_WINDOW, FAR_MAX = 0x1a00, 0x5f0

OPTION_ROOM = 1420                               # bytes of lists 21 to 40 before stage 25 (s25.option_menus)
PLAYLIST_LISTS = range(26, 31)
ADD_TEXT, ADD_ICON = 30, 15                      # MUSIC.STY text; COMMON.STY picture of "Add to playlist"
ADD_FN = 0x181613ef                              # MUSIC.AP: mov r1, r0; movw r0, #0x8607; bx lr
ADD_FN_CODE = bytes.fromhex("014648f207607047")
STOCK_TEXT = "Clear [%s]?"
CODE_SHA = {                                     # the placed code per theme, as the fourth build went to the player
    "amber": "ac757838b4b1a0d84ac436333c0ce72c243b0abbd3489780adfa436ce8db722d",
    "mint": "97da5ef2831a2c045f116d9b1a89223435d196bcd79bfabf1f4e4eba8b118699",
    "ice": "2ae5adf10ef4718a1bde2230b9edaca096b9770d5fbaccd191b983eaf1037aea",
    "berry": "3f138df8e132c2a226f3c59d355542bcaf01079f85341b9b573f39f683ccc129",
}


def stack_depth(work):
    """Deepest chain of the new code's own frames (as build_stage18.stack_depth, with always_inline helpers known by
    their own names: they have no frame, the calls in them count for their callers)."""
    frames, bodies = {}, {}
    for src in s20.SOURCES:
        for line in open(os.path.join(work, src.replace(".c", ".su"))):
            name, size = line.split()[0].split(":")[-1], int(line.split()[1])
            frames[name.split(".")[0]] = size
        text = open(os.path.join(s20.SRC, src)).read()
        bodies.update(re.findall(r"\n(?:static )?(?:inline __attribute__\(\(always_inline\)\) )?[\w ]+?\**(\w+)\([^;{]*\)"
                                 r"\n\{(.*?)\n\}", text, re.S))
    calls = {f: [g for g in bodies if g != f and re.search(r"\b%s\(" % g, b)] for f, b in bodies.items()}

    def depth(f, seen=()):
        return frames.get(f, 0) + max([depth(g, seen + (f,)) for g in calls.get(f, []) if g not in seen] or [0])
    return {e: depth(e) for e in s20.ENTRIES}


def plan(ap, secs):
    """FAR_GROUPS in the 0x1a00 group's free tails (each group in one bank if it fits, else one by one), the rest as
    build_stage20.plan places it."""
    starts = sorted(struct.unpack_from("<I", ap, t + i)[0] for t in s20.BANK_TABLES for i in range(0, 0x800, 12)
                    if struct.unpack_from("<III", ap, t + i)[0] and struct.unpack_from("<III", ap, t + i)[2])
    far = []
    for t in s20.BANK_TABLES:
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", ap, t + i)
            if not (off and ln) or addr >> 24 != 0x18 or addr & 0xffff != FAR_WINDOW:
                continue
            top = min(min([x for x in starts if x > off] + [len(ap)]) - off, FAR_MAX)
            if top > ln and not any(ap[off + ln:off + top]):
                far.append(dict(addr=addr, hdr=t + i, off=off, len=ln, at=(ln + 3) & ~3, top=top, secs=[]))
    base = lambda name: name[len(".text."):].split(".")[0]
    by = {base(n): (n, size, a) for n, size, a in secs}

    def place(b, name, size, align):
        at = (b["at"] + align - 1) & ~(align - 1)
        if at + size > b["top"]:
            return False
        b["secs"].append(name)
        b["at"] = at + size
        return True
    for group in FAR_GROUPS:
        members = [by.pop(f) for f in group if f in by]
        need = sum((m[1] + 3) & ~3 for m in members)
        fits = [b for b in far if not b["secs"] and b["top"] - b["at"] >= need]
        for m in members:
            if not any(place(b, *m) for b in ([min(fits, key=lambda b: b["top"] - b["at"])] if fits else [])
                       + sorted(far, key=lambda b: b["top"] - b["at"])):
                sys.exit("no room left in the 0x1a00 group for %s" % m[0])
    return s20_plan(ap, list(by.values())) + [b for b in far if b["secs"]]


def option_menus(lfi):
    """Lists 26 to 30 with a row "Add songs" in front of "Search", lists 21 to 30 anew in stage 25's room."""
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
        if [r[1] for r in rows[li][-4:-1]] != [76, s21.DELETE_TEXT, s21.MOVE_TEXT]:
            sys.exit("MUSIC.MCG: list %d is not stage 25's Playlists options" % li)
    end = start + OPTION_ROOM
    if any(mcg[at:end]):
        sys.exit("MUSIC.MCG: the room behind the option lists is not free")
    add = [0x7fff, ADD_TEXT, 0, ADD_ICON, ADD_FN, 0, s25.ROW_TAIL]
    new, place = b"", {}
    for li in s25.OPTION_LISTS:
        body = rows[li][:-1] + [add] + rows[li][-1:] if li in PLAYLIST_LISTS else rows[li]
        place[li] = (start + len(new), len(body))
        new += b"".join(struct.pack("<HHHHIII", *r) for r in body)
    if len(new) > OPTION_ROOM:
        sys.exit("MUSIC.MCG: the option lists need %d bytes, the room is %d" % (len(new), OPTION_ROOM))
    mcg[start:end] = new + bytes(OPTION_ROOM - len(new))
    for li in s25.OPTION_LISTS:
        eid, _, _, link = heads[li]
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, place[li][1], place[li][0], link)
    for li in s25.BUILTIN_LISTS:
        eid, _, _, link = heads[li]
        same = 26 + (li - 31) % 5
        struct.pack_into("<HHII", mcg, hsz + li * 12, eid, place[same][1], place[same][0], link)
    lfi.put("MUSIC.MCG", bytes(mcg))
    return len(new)


def add_text(lfi):
    sty = bytearray(lfi.get("MUSIC.STY"))
    off, _ = s24.english(sty)
    have, o, n = s24.text_of(sty, off, ADD_TEXT)
    raw = "Add songs\0".encode("utf-16-le")
    if have != STOCK_TEXT or len(raw) > n:
        sys.exit("MUSIC.STY: English text %d is %r" % (ADD_TEXT, have))
    sty[o:o + n] = raw + bytes(n - len(raw))
    struct.pack_into("<I", sty, off + ADD_TEXT * 8 + 4, len(raw))
    lfi.put("MUSIC.STY", bytes(sty))


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage26")
    work = os.path.join(out, "code")
    os.makedirs(work, exist_ok=True)
    s20.SRC = LIVE
    s20.SOURCES = SOURCES + ("liststyle.c",)          # the host test runs everything; liststyle.c stays as stage 24 put it
    print("host test:", s20.host_test(work))
    s20.SOURCES = SOURCES
    s20.GROUPS = s20.GROUPS + SEARCH_GROUPS
    s20.CFLAGS = CFLAGS + s25.theme_flags()
    s20.stack_depth = stack_depth
    s20.plan = plan

    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    stock_ap = xm.Lfi(stock).get("MUSIC.AP")
    base = os.environ.get("X91_STAGE25") or os.path.join(ROOT, "x91_dump", "stage25", "x91_lfi_stage25.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 25 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    used = option_menus(lfi)
    add_text(lfi)
    banks, depths, taken, hot = s25.replace_code(lfi, work, stock_ap)
    ap = lfi.get("MUSIC.AP")
    o = ap_dis.find(ap_dis.segments(ap)[0], ADD_FN & ~1)
    if ap[o:o + len(ADD_FN_CODE)] != ADD_FN_CODE:
        sys.exit("MUSIC.AP: %#x is not the routine that returns 0x8607" % ADD_FN)

    print("option lists 26 to 30 get \"Add songs\" (text %d, icon %d, routine %#x): lists 21 to 30 in %d of %d bytes"
          % (ADD_TEXT, ADD_ICON, ADD_FN, used, OPTION_ROOM))
    print("colours: %s" % ", ".join("%s %s" % (k, s1.T[k]) for k in s25.COLOURS))
    print("stage 25 code taken out of %d banks; menu_box and list_box kept" % len(taken))
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
        sys.exit("the frozen stage 26 sources no longer give the stage 26 code for %s" % s1.THEME)
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage26.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
