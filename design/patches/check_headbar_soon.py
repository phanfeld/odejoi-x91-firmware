#!/usr/bin/env python3
"""Run the stage 14 and the stage 24 "status bar on/off" routine of the shared status-bar code side by side.

Both must make the same calls (timer restart or stop, then for "on" the bar drawn at once) and leave the same memory
behind, except for one thing: after "on", when the timer restart reports success, the stage 24 routine moves that
timer's next firing time (+8 of its 16-byte entry) back by its period (+2), and touches nothing else.

usage: check_headbar_soon.py OLD.dis NEW.dis START DRAW RESTART STOP      (addresses in hex)
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_sim  # noqa: E402

START, DRAW, RESTART, STOP = (int(a, 16) for a in sys.argv[3:7])
END = POOL = START + 0x74
TABLE_LIT = START + 0x70                          # the new routine's own literal: where the table pointer is kept
MODE, ICON, PARTS, FLAG, BACK, TIMER, SP = 0x7003, 0x7002, 0x7100, 0x700f, 0x7004, 0x7009, 0x100000
TABLE_PTR, TABLE, ENTRIES = 0x7200, 0x7300, 4


def machine(mode, icon, back, timer, fill, new):
    m = thumb_sim.Machine(dict(r0=mode, r1=icon, r2=back, r3=0xA3, r4=0xA4, r5=0xA5, r6=0xA6, sp=SP, lr=0), {})
    for k, addr in enumerate((MODE, ICON, PARTS, FLAG, BACK, TIMER)):
        m.wr(POOL + 4 * k, 4, addr)
    if new:
        m.wr(TABLE_LIT, 4, TABLE_PTR)
    m.wr(TABLE_PTR, 4, TABLE)
    for k in range(ENTRIES):                      # period 500 + k, next firing 0x12345000 + k
        m.wr(TABLE + 16 * k, 16, 0)
        m.wr(TABLE + 16 * k + 2, 2, 500 + k)
        m.wr(TABLE + 16 * k + 8, 4, 0x12345000 + k)
    for addr in list(range(0x7000, 0x7010)) + list(range(PARTS, PARTS + 14)):
        m.wr(addr, 1, fill)
    m.wr(TIMER, 1, timer)
    return m


def main():
    old = thumb_sim.load(sys.argv[1], START, END)
    new = thumb_sim.load(sys.argv[2], START, END)
    tid = 0

    def call(target, m):                          # the timer library: success only for a timer that exists
        return int(0 <= tid < ENTRIES) if target in (RESTART, STOP) else 0x55
    n = bad = 0
    for mode, icon, back, timer, fill in itertools.product((0, 1, 2, 255), (0, 4, 11), (0xffff, 45, 0x80f9, 0x1ffff, 0),
                                                           (0, 1, 3, 4, 0x7f, 0x80, 0xff), (0x00, 0xee)):
        tid = timer - 256 if timer & 0x80 else timer
        a, b = machine(mode, icon, back, timer, fill, False), machine(mode, icon, back, timer, fill, True)
        ea, eb = a.run(old, START, (), call), b.run(new, START, (), call)
        got_a, got_b = [c[:2] for c in a.calls], [c[:2] for c in b.calls]
        want = dict(a.mem)
        want.update({k: v for k, v in b.mem.items() if TABLE_LIT <= k < TABLE_LIT + 4})   # the literal itself
        if mode == 1 and 0 <= tid < ENTRIES:
            e = TABLE + 16 * tid
            nxt = (a.rd(e + 8, 4) - a.rd(e + 2, 2)) & 0xffffffff
            for i in range(4):
                want[e + 8 + i] = (nxt >> (8 * i)) & 0xff
        n += 1
        if not (got_a == got_b and want == b.mem and ea == eb == "return" and a.r["sp"] == b.r["sp"] == SP):
            bad += 1
            print("MISMATCH", (mode, icon, hex(back), timer, fill), got_a, got_b,
                  {hex(k): (want.get(k), b.mem.get(k)) for k in set(want) | set(b.mem) if want.get(k) != b.mem.get(k)})
    print("%d input combinations, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
