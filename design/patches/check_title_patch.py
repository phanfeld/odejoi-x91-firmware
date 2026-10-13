#!/usr/bin/env python3
"""Run the stock and the patched title step of the tag reader in MUSIC.AP side by side.

Stock: always fetches the file name into the title buffer. Patched: only when the title is empty; then it must
make exactly the stock calls. With a title present it must make no call and write nothing.

usage: check_title_patch.py OLD.dis NEW.dis
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_sim  # noqa: E402

START, END = 0x1c1021d4, 0x1c1021f2
FILE_CALL, SHORT_NAME, LIT = 0x1c10230a, 0x1c1020ee, 0x1c1022dc
REC, BUF, VAR, MOUNT, SP = 0x5000, 0x6000, 0x7000, 0x77, 0x100000


def machine(first, size):
    m = thumb_sim.Machine(dict(r0=0xA0, r1=0xA1, r2=0xA2, r3=0xA3, r4=REC, r5=2, r6=0xA6, r7=0xA7, sp=SP, lr=0), {})
    m.wr(REC, 4, BUF)
    m.wr(REC + 24, 1, size)
    m.wr(BUF, 1, first)
    m.wr(LIT, 4, VAR)
    m.wr(VAR, 4, MOUNT)
    return m


def main():
    old = thumb_sim.load(sys.argv[1], START, END)
    new = thumb_sim.load(sys.argv[2], START, END)
    n = bad = 0
    for first, size in itertools.product((0, 0x20, 0x41, 0xef, 0xff, 0x01, 0x80), (0, 1, 2, 51, 52, 92, 93, 254, 255)):
        a, b = machine(first, size), machine(first, size)
        stack = []
        call = lambda target, m: stack.append(m.rd(m.r["sp"], 4)) or 0
        ea, eb = a.run(old, START, (END,), call), b.run(new, START, (END,), call)
        want = [(FILE_CALL, MOUNT, BUF, size // 2, 0), (SHORT_NAME, BUF)]
        got_a = [a.calls[0], a.calls[1][:2]] if len(a.calls) == 2 else a.calls
        got_b = [b.calls[0], b.calls[1][:2]] if len(b.calls) == 2 else b.calls
        ok = got_a == want and ea == eb == END and a.r["sp"] == b.r["sp"] == SP and all(b.r[k] == a.r[k] for k in ("r4", "r5", "r7"))
        if first == 0:
            ok = ok and got_b == want and stack == [2, 2, 2, 2] and a.mem == b.mem
        else:
            ok = ok and got_b == [] and b.mem == machine(first, size).mem
        n += 1
        if not ok:
            bad += 1
            print("MISMATCH", (first, size), got_a, got_b, stack)
    print("%d input combinations, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
