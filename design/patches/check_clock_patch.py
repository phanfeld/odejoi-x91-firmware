#!/usr/bin/env python3
"""Run the stock and the patched start of the clock routine side by side on every input combination.

usage: check_clock_patch.py OLD.dis NEW.dis
"""
import itertools
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import thumb_sim  # noqa: E402

START, END, LEAVE = 0x18ce1a34, 0x18ce1ac6, 0x18ce1b4a
SHOW, SYS = 0x18ce1e1c, 0x18ce1e12
TABLE, SETTINGS_PTR, SETTINGS, LAST, SP = 0x18ce1e48, 0x202f88, 0x203000, 0x200104, 0x100000
FRAMES, FIRST, SX, SY = 12, 0x8000 + 221, 36, 72


def state(first_call, minute, last, bg, twelve_hour, counter):
    m = thumb_sim.Machine(dict(r0=0xA0, r1=0xA1, r2=0xA2, r3=0xA3, r4=0xA4, r5=32, r6=13, r7=0xA7, sl=first_call, fp=0, sp=SP), {})
    m.wr(0x18ce1de4, 4, TABLE)
    m.wr(0x18ce1de8, 4, SETTINGS_PTR)
    m.wr(0x18ce1dec, 4, LAST)
    m.wr(TABLE, 2, 0x80ab)
    m.wr(SETTINGS_PTR, 4, SETTINGS)
    m.wr(SETTINGS + 30, 1, bg)
    m.wr(SETTINGS + 10, 1, twelve_hour)
    m.wr(LAST, 1, last)
    m.wr(LAST - 4, 1, counter)
    m.wr(SP + 37, 1, minute)
    return m


def outcome(m, exit_pc):
    keep = {k: v for k, v in m.mem.items() if k != LAST - 4 and (SP <= k < SP + 26 or k == LAST)}
    return exit_pc, m.r["fp"], m.r["r5"], m.r["r6"], m.r["sp"], tuple(sorted(keep.items()))


def main():
    old = thumb_sim.load(sys.argv[1], START, END)
    new = thumb_sim.load(sys.argv[2], START, END)
    on_call = lambda target, m: 0x1234 if target == SYS else 0
    n = bad = 0
    for first_call, minute, last, bg, twelve, counter in itertools.product(
            (0, 1), (0, 7, 59), (0, 7, 59), (0, 2), (0, 1), (0, 5, FRAMES - 2, FRAMES - 1, 19, 255)):
        a, b = state(first_call, minute, last, bg, twelve, counter), state(first_call, minute, last, bg, twelve, counter)
        ea = a.run(old, START, (END, LEAVE), on_call)
        eb = b.run(new, START, (END, LEAVE), on_call)
        frame = counter + 1 if counter + 1 < FRAMES else 0
        sprite = (SHOW, FIRST + frame, SX, SY, 31)
        rest = [c for c in b.calls if c != sprite]
        ok = (outcome(a, ea) == outcome(b, eb) and rest == a.calls and b.calls.count(sprite) == 1
              and b.mem[LAST - 4] == frame and a.mem[LAST - 4] == counter
              and (not first_call or b.calls.index(sprite) == 1))        # the sprite is drawn after the background
        n += 1
        if not ok:
            bad += 1
            print("MISMATCH", (first_call, minute, last, bg, twelve, counter), a.calls, b.calls)
    print("%d input combinations, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
