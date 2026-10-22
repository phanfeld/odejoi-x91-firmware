#!/usr/bin/env python3
"""Run menu_box (patches/menu_box.S, as put into one bank) in the simulator for every draw mode and list style.

Expected: always exactly one list box call through the bank's veneer with the caller's style, data and mode and
r3 = 8, as a tail call; before it, only on a full redraw (mode 3) of style 0x6000 + n with n in BAR_STYLES (0, 2, 3,
4, 5), one call of display command 31 with (BAR_CLEAR, BAR_X, 0); no memory written, the stack as it was.

usage: check_menu_box.py BANK.dis START VENEER      (addresses in hex)
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_sim  # noqa: E402

START, VENEER = (int(a, 16) for a in sys.argv[2:4])
END = START + 0x40
BAR_CLEAR, BAR_X, BAR_STYLES = 0x8000 | 127, 17, (0, 2, 3, 4, 5)
STYLE, DATA, SP, LR = 0x7000, 0x7100, 0x100000, 0x5A5A


def main():
    code = thumb_sim.load(sys.argv[1], START, END)
    n = bad = 0
    for mode, style in itertools.product((0, 1, 2, 3, 4, 5, 0xff), [None] + list(range(0x5ffe, 0x600b)) + [0x7000, 0xe000]):
        m = thumb_sim.Machine(dict(r0=STYLE if style is not None else 0, r1=DATA, r2=mode, r3=8, r4=0xA4, sp=SP, lr=LR), {})
        if style is not None:
            m.wr(STYLE, 2, style)
            m.wr(STYLE + 2, 2, 1)
        before = dict(m.mem)
        end = m.run(code, START, (LR,), lambda target, mm: 0x55)
        box = (VENEER, STYLE if style is not None else 0, DATA, mode, 8)
        clear = mode == 3 and style is not None and style - 0x6000 in BAR_STYLES
        want = ([(VENEER, BAR_CLEAR, BAR_X, 0, 31)] if clear else []) + [box]
        n += 1
        if not (m.calls == want and end == LR and m.mem == before and m.r["sp"] == SP):
            bad += 1
            print("MISMATCH mode %d style %s: %s" % (mode, style if style is None else hex(style),
                                                     [tuple(hex(v) for v in c) for c in m.calls]))
    print("%d cases, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
