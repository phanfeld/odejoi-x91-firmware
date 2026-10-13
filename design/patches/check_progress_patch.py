#!/usr/bin/env python3
"""Run the stock and the patched end of the time-and-progress routine of MUSIC.AP side by side.

usage: check_progress_patch.py OLD.dis NEW.dis
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_sim  # noqa: E402

START, PROGRESS, END = 0x180613f4, 0x1806144a, 0x18061476
UI, FLAGS, STATE, SP, STYLE = 0x180615d6, 0x20001c, 0x200191, 0x100000, 0x5000
TRACK, KNOB, COLUMN, Y = 67, 68, 66, 110


def machine(r8, total_hours=0, flags=0, total=0, elapsed=0, last=0):
    m = thumb_sim.Machine(dict(r0=0xA0, r1=0xA1, r2=0xA2, r3=0xA3, r4=total, r5=STYLE, r6=elapsed, r7=0, r8=r8, r9=1, sp=SP), {})
    m.wr(0x18061484, 4, FLAGS)
    m.wr(FLAGS, 4, flags)
    m.wr(SP + 12, 2, total_hours)
    m.wr(STATE, 1, last)
    return m


def main():
    old = thumb_sim.load(sys.argv[1], START, END)
    new = thumb_sim.load(sys.argv[2], START, END)
    call = lambda target, m: 0
    n = bad = 0
    # the time part: must behave exactly as stock
    for r8, hours, flags in itertools.product((0, 1, 2), (0, 1, 3), (0, 0xffffffff, 0x00000b00, 0x12345678)):
        a, b = machine(r8, hours, flags), machine(r8, hours, flags)
        ea, eb = a.run(old, START, (END,), call), b.run(new, START, (END,), call)
        same_mem = {k: v for k, v in a.mem.items() if k != STATE} == {k: v for k, v in b.mem.items() if k != STATE}
        n += 1
        if not (a.calls == b.calls and same_mem and ea == eb and b.mem[STATE] == 0):
            bad += 1
            print("TIME MISMATCH", (r8, hours, hex(flags)), a.calls, b.calls)
    # the progress part
    for r8, total, elapsed, back in itertools.product((0, 1), (0, 1, 100, 240, 3600), (0, 1, 2, 50, 99, 100, 239, 240, 5000), (0, 1, 2, 5, -1, -2, 300)):
        ref = machine(r8, total=total, elapsed=elapsed)
        ref.run(old, PROGRESS, (END,), call)
        pos = ref.calls[1][2]                                        # where stock puts the knob
        last = (pos - back) & 0xff
        a, b = machine(r8, total=total, elapsed=elapsed, last=last), machine(r8, total=total, elapsed=elapsed, last=last)
        a.run(old, PROGRESS, (END,), call)
        b.run(new, PROGRESS, (END,), call)
        stock = [(UI, TRACK, 0, Y, 31), (UI, KNOB, pos, Y, 31)]
        step = pos - last
        if r8 == 1 or step < 0 or step > 1:
            want = stock
        elif step == 0:
            want = []
        else:
            want = [(UI, COLUMN, last, Y, 31), (UI, KNOB, pos, Y, 31)]
        n += 1
        if not (a.calls == stock and b.calls == want and b.mem[STATE] == pos and b.r["sp"] == a.r["sp"] and 0 <= pos <= 122):
            bad += 1
            print("PROGRESS MISMATCH", (r8, total, elapsed, last, pos), b.calls, want)
    print("%d input combinations, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
