#!/usr/bin/env python3
"""Check the rewritten time-and-progress routine of MUSIC.AP against the stock one.

The time part must behave exactly as stock. The bar part is checked against its description:
position = 8 + 106 * elapsed / total, and the drawing calls for each case.
usage: check_playing_patch.py STOCK.dis NEW.dis
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_sim  # noqa: E402

START, END = 0x18061390, 0x18061476
HMS, UI, GET_TOTAL = 0x18061364, 0x180615d6, 0x1806161c
TOTAL, ELAPSED, FLAGS, STATE, SP, STYLE = 0x20002c, 0x200030, 0x20001c, 0x200191, 0x100000, 0x300000
TRACK, KNOB, COLUMN, SEGMENT, Y, X0, LEN = 67, 68, 65, 70, 132, 8, 106


def machine(full, which, total_ms, elapsed_ms, flags=0, last=0):
    m = thumb_sim.Machine(dict(r0=full, r1=STYLE, r2=which, r3=0xA3, r4=0xA4, r5=0xA5, r6=0xA6, r7=0xA7, r8=0xA8, r9=0xA9, sp=SP), {})
    for lit, value in ((0x1806147c, TOTAL), (0x18061480, ELAPSED), (0x18061484, FLAGS)):
        m.wr(lit, 4, value)
    m.wr(TOTAL, 4, total_ms)
    m.wr(ELAPSED, 4, elapsed_ms)
    m.wr(FLAGS, 4, flags)
    m.wr(STATE, 1, last)
    return m


def calls_of(m):
    """Calls with the arguments each callee really reads."""
    out = []
    for target, r0, r1, r2, r3 in m.calls:
        out.append((target, r0, r1) if target == HMS else (target, r0) if target == GET_TOTAL else (target, r0, r1, r2, r3))
    return out


def main():
    stock = thumb_sim.load(sys.argv[1], START, END)
    new = thumb_sim.load(sys.argv[2], START, END)
    fresh_total = [0]

    def on_call(target, m):
        if target == HMS:
            sec, out = m.r["r0"], m.r["r1"]
            m.wr(out, 2, sec // 3600)
            m.wr(out + 2, 1, sec % 3600 // 60)
            m.wr(out + 3, 1, sec % 60)
        elif target == GET_TOTAL:
            m.wr(m.r["r0"], 4, fresh_total[0])
        return 0

    n = bad = 0
    # the time: identical to stock in calls, memory and stack
    for full, total, elapsed, flags, fresh in itertools.product((0, 1, 2), (0, 215000, 3723000), (0, 59999, 133000, 3600000),
                                                                (0, 0xffffffff, 0x12345b78), (200000, 4000000)):
        fresh_total[0] = fresh
        a, b = machine(full, 0, total, elapsed, flags), machine(full, 0, total, elapsed, flags)
        ea, eb = a.run(stock, START, (END,), on_call), b.run(new, START, (END,), on_call)
        n += 1
        if not (calls_of(a) == calls_of(b) and a.mem == b.mem and a.r["sp"] == b.r["sp"] and ea == eb):
            bad += 1
            print("TIME MISMATCH", (full, total, elapsed, hex(flags), fresh), calls_of(a), calls_of(b))
    # the bar
    for full, total, elapsed, fresh, back in itertools.product((0, 1), (0, 1000, 100000, 240000, 3600000),
                                                               (0, 999, 1000, 2000, 120000, 239000, 240000, 9000000),
                                                               (0, 240000), (0, 1, 2, 7, -1, -3, 60)):
        fresh_total[0] = fresh
        t_ms = total or fresh
        t_s, e_s = t_ms // 1000, elapsed // 1000
        pos = X0 + (min(LEN, LEN * e_s // t_s) if t_s else 0)
        last = (pos - back) & 0xff
        a, b = machine(full, 1, total, elapsed, last=last), machine(full, 1, total, elapsed, last=last)
        a.run(stock, START, (END,), on_call)
        b.run(new, START, (END,), on_call)
        draws = [c for c in calls_of(b) if c[0] == UI]
        step = pos - last
        if full == 1 or step < 0 or step > 1:
            want = [(UI, TRACK, 0, Y, 31)] + [(UI, SEGMENT, x, Y, 31) for x in range(X0, pos, 6)] + [(UI, KNOB, pos, Y, 31)]
        elif step == 0:
            want = []
        else:
            want = [(UI, COLUMN, last, Y, 31), (UI, KNOB, pos, Y, 31)]
        same_fetch = [c for c in calls_of(a) if c[0] == GET_TOTAL] == [c for c in calls_of(b) if c[0] == GET_TOTAL]
        n += 1
        if not (draws == want and same_fetch and b.mem[STATE] == pos and b.rd(TOTAL, 4) == a.rd(TOTAL, 4)
                and b.r["sp"] == a.r["sp"] and X0 <= pos <= X0 + LEN):
            bad += 1
            print("BAR MISMATCH", (full, total, elapsed, fresh, last, pos), draws[:4], want[:4])
    print("%d input combinations, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
