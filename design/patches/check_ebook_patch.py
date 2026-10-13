#!/usr/bin/env python3
"""Run the stock and the patched page-painting code of EBOOK.AP (bank 0x180e1000) side by side.

Stock:    [strip: top strip picture (on a full repaint) and page number]  [page: background, text colour,
          page layout]  [mark for automatic page turning]
Patched:  landscape on, [strip: picture, page number, progress bar], [page: as stock], landscape off.
The page part must be identical, the flags must end up the same, and the strip part must follow the rules
written down in ebook_reader.S.

usage: check_ebook_patch.py OLD.dis NEW.dis
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_sim  # noqa: E402

BANK = 0x180e1000
PAINT, STRIP, MARK = BANK + 0x0dc, BANK + 0x48c, BANK + 0x3c0
UI, DECODE = BANK + 0x648, BANK + 0x1f4
FULL, PAGE, NUMBER, COUNTING, MARKFLAG = 0x20004a, 0x200051, 0x200052, 0x200054, 0x200055
SYS, CFG, OFFSET, FILE, DEC, CUR, TOTAL = 0x202fbc, 0x2001a0, 0x200030, 0x2004f8, 0x110e00, 0x200020, 0x200024
POOLS = {0x190: NUMBER, 0x194: PAGE, 0x198: SYS, 0x19c: CFG, 0x1a0: OFFSET, 0x1a4: FILE, 0x1a8: DEC,
         0x408: MARKFLAG, 0x40c: CFG, 0x50c: CFG, 0x510: CUR, 0x514: TOTAL, 0x518: FULL}
BAR_X, BAR_LEN, BAR_Y, PIECE, COLUMN = 6, 104, 119, 43, 44
SP, START, BYTES = 0x100000, 0x4321, 777


def machine(page, number, sys9, full, counting, mark, colour, auto, cur, total):
    m = thumb_sim.Machine(dict(r0=0xA0, r1=0xA1, r2=0xA2, r3=0xA3, r4=0xA4, r5=0xA5, r6=0xA6, r7=0xA7, sp=SP, lr=0), {})
    for off, value in POOLS.items():
        m.wr(BANK + off, 4, value)
    for addr, value in ((FULL, full), (PAGE, page), (NUMBER, number), (COUNTING, counting), (MARKFLAG, mark),
                        (SYS + 9, sys9), (CFG + 170, colour), (CFG + 2, auto)):
        m.wr(addr, 1, value)
    for addr, value in ((OFFSET, START), (FILE + 12, 0), (CUR, cur), (TOTAL, total)):
        m.wr(addr, 4, value)
    return m


def on_call(target, m):
    r = m.r
    if target == DECODE:
        m.seen.append(("layout", r["r0"], r["r1"], m.rd(FILE + 12, 4)))
        m.wr(r["r2"], 4, BYTES)
        return 1
    fn = r["r3"]
    if fn == 2:
        m.seen.append((2, m.rd(r["r0"], 2), m.rd(r["r0"] + 2, 1), m.rd(r["r1"], 2), m.rd(r["r1"] + 2, 1)))
    elif fn == 5:
        m.seen.append((5, m.rd(r["r0"], 2), m.rd(r["r0"] + 2, 1), m.rd(r["r1"], 4), m.rd(r["r1"] + 4, 4), r["r2"]))
    elif fn == 19:
        m.seen.append((19, r["r0"], r["r1"], r["r2"]))
    elif fn == 30:
        m.seen.append((30, r["r0"]))
    elif fn == 31:
        m.seen.append((31, r["r0"], r["r1"], r["r2"]))
    else:
        m.seen.append(("?", fn))
    return 0


def page_part(colour):
    return [(2, 0x1000, 0, 0xffff, colour), (19, 0xffff if colour in (1, 4) else 0, 0, 0), ("layout", DEC, FILE, START)]


def main():
    load = lambda path, ranges: {a: v for lo, hi in ranges for a, v in thumb_sim.load(path, BANK + lo, BANK + hi).items()}
    old = load(sys.argv[1], ((0x0dc, 0x190), (0x3c0, 0x408), (0x48c, 0x50c)))
    new = load(sys.argv[2], ((0x0dc, 0x190), (0x3c0, 0x410), (0x48c, 0x50c)))
    n = bad = 0
    pages = ((0, 0), (0, 1), (4, 10), (9, 10), (99, 100), (0, 300), (149, 300), (299, 300), (500, 300), (7, 3999))
    for page, number, sys9, full, counting, mark, colour, auto, (cur, total) in itertools.product(
            (0, 1), (0, 1), (0, 1), (0, 1), (0, 1), (0, 1), range(5), (0, 1), pages):
        args = (page, number, sys9, full, counting, mark, colour, auto, cur, total)
        a, b = machine(*args), machine(*args)
        a.seen, b.seen = [], []
        ea, eb = a.run(old, PAINT, (), on_call, limit=4000), b.run(new, PAINT, (), on_call, limit=4000)
        strip = (number == 1 or page == 1) and sys9 == 0
        want_old, want_new = [], [(30, 1)]
        if strip:
            box = (5, 0x3000 + colour, 0, cur + 1, total)
            want_old += [(2, 0x1002, 0, 0xffff, colour), box + (2,)] if full else [box + (1,)]
            if full or page == 1 or not counting:
                want_new += [(2, 0x1002, 0, 0xffff, colour), box + (2,)]
                if not counting and total:
                    end = BAR_X + min(BAR_LEN * (cur + 1) // total, BAR_LEN)
                    x = BAR_X
                    while x + 8 <= end:
                        want_new.append((31, PIECE, x, BAR_Y))
                        x += 8
                    while x < end:
                        want_new.append((31, COLUMN, x, BAR_Y))
                        x += 1
        if page == 1:
            want_old += page_part(colour)
            want_new += page_part(colour)
        if mark == 1:
            want_old.append((2, 0x1001, 0, 0xffff, auto + 2 * colour))
        want_new.append((30, 0))
        flags = lambda m: [m.rd(x, 1) for x in (FULL, PAGE, NUMBER, COUNTING)] + [m.rd(OFFSET, 4), m.rd(FILE + 12, 4)]
        ok = (a.seen == want_old and b.seen == want_new and ea == eb == "return" and a.r["sp"] == b.r["sp"] == SP
              and flags(a) == flags(b) and b.rd(MARKFLAG, 1) == mark
              and flags(b)[:3] == [0 if strip else full, 0, 0 if strip else number]
              and flags(b)[4] == (START + BYTES if page == 1 else START))
        n += 1
        if not ok:
            bad += 1
            if bad <= 5:
                print("MISMATCH", args, "\n  stock  ", a.seen, "\n  wanted ", want_old, "\n  patched", b.seen, "\n  wanted ", want_new,
                      "\n  flags", flags(a), flags(b))
    print("%d input combinations, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
