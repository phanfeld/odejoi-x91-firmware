#!/usr/bin/env python3
"""Run the stock and the patched "status bar on/off" routine of the shared status-bar code side by side.

Both must leave the same memory behind and make the same timer call; the patched one then draws the bar
(one more call, with r0 = 0) when the bar is switched on, and nothing more.

usage: check_headbar_patch.py OLD.dis NEW.dis [START DRAW RESTART STOP]
       (addresses in hex; by default MUSIC.AP's, where stage 14 put the patch first)
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_sim  # noqa: E402

BANK = 0x18c21a00
START, DRAW, RESTART, STOP = BANK + 0x474, BANK + 0x020, 0x18a21b80, 0x18a21acc
if len(sys.argv) == 7:
    START, DRAW, RESTART, STOP = (int(a, 16) for a in sys.argv[3:7])
END = POOL = START + 0x74
MODE, ICON, PARTS, FLAG, BACK, TIMER, SP = 0x7003, 0x7002, 0x7100, 0x700f, 0x7004, 0x7009, 0x100000


def machine(mode, icon, back, timer, fill):
    m = thumb_sim.Machine(dict(r0=mode, r1=icon, r2=back, r3=0xA3, r4=0xA4, r5=0xA5, r6=0xA6, sp=SP, lr=0), {})
    for k, addr in enumerate((MODE, ICON, PARTS, FLAG, BACK, TIMER)):
        m.wr(POOL + 4 * k, 4, addr)
    for addr in list(range(0x7000, 0x7010)) + list(range(PARTS, PARTS + 14)):
        m.wr(addr, 1, fill)
    m.wr(TIMER, 1, timer)
    return m


def main():
    old = thumb_sim.load(sys.argv[1], START, END)
    new = thumb_sim.load(sys.argv[2], START, END)
    call = lambda target, m: 0x55
    n = bad = 0
    for mode, icon, back, timer, fill in itertools.product((0, 1, 2, 255), (0, 4, 11), (0xffff, 45, 0x80f9, 0x1ffff, 0),
                                                           (0, 3, 0x7f, 0x80, 0xff), (0x00, 0xee)):
        a, b = machine(mode, icon, back, timer, fill), machine(mode, icon, back, timer, fill)
        ea, eb = a.run(old, START, (), call), b.run(new, START, (), call)
        tid = timer | 0xffffff00 if timer & 0x80 else timer
        stock = [(RESTART if mode == 1 else STOP, tid)]
        want = stock + [(DRAW, 0)] if mode == 1 else stock
        got_a, got_b = [c[:2] for c in a.calls], [c[:2] for c in b.calls]
        n += 1
        if not (got_a == stock and got_b == want and a.mem == b.mem and ea == eb == "return" and a.r["sp"] == b.r["sp"] == SP):
            bad += 1
            print("MISMATCH", (mode, icon, hex(back), timer, fill), got_a, got_b,
                  {hex(k): (a.mem.get(k), b.mem.get(k)) for k in set(a.mem) | set(b.mem) if a.mem.get(k) != b.mem.get(k)})
    print("%d input combinations, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
