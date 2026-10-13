#!/usr/bin/env python3
"""Run the stock and the patched stretch of the music menu routine side by side on every input combination.

A small interpreter for the dozen instruction forms that occur there, working on objdump's text output.
usage: check_music_patch.py OLD.dis NEW.dis
"""
import itertools
import re
import struct
import sys

START, END = 0x181012dc, 0x1810135e
LITS = {0x1810142c: 0x00202fbc, 0x181010ec: 0x00200001}


def load(path):
    code = {}
    for line in open(path):
        m = re.match(r"\s*([0-9a-f]{8}):\t([0-9a-f ]+)\t(\S+)\t?([^@]*)", line)
        if m:
            a = int(m.group(1), 16)
            if START <= a < END:
                size = len(m.group(2).replace(" ", "")) // 2
                lit = re.search(r"@ \(?0x([0-9a-f]+)\)?\s*$", line)
                code[a] = (size, m.group(3), m.group(4).strip(), int(lit.group(1), 16) if lit else None)
    return code


def run(code, r0, engine, r6, sp64, mode):
    reg = {"r0": r0, "r1": 0xdead, "r2": 0xdead, "r3": 0xdead, "r5": 0xdead, "r6": r6, "sp": 0x1000}
    mem = {0x202fbc: engine, 0x200001: mode, 0x1000 + 64: sp64}
    calls, flags, pc, steps = [], None, START, 0
    num = lambda s: int(s.lstrip("#"), 0)
    while pc != END:
        steps += 1
        if steps > 200 or pc not in code:
            return ("LOST at %#x" % pc,)
        size, op, args, lit = code[pc]
        a = [x.strip() for x in re.split(r",\s*(?![^\[]*\])", args)] if args else []
        nxt = pc + size
        if op in ("nop",) or (op == "movs" and a == ["r0", "r0"]):
            pass
        elif op in ("ldr", "ldr.w") and "[pc" in args:
            reg[a[0]] = LITS[lit]
        elif op in ("ldrb", "ldrb.w"):
            base, off = re.match(r"\[(\w+)(?:, #(\d+))?\]", a[1]).groups()
            reg[a[0]] = mem.get(reg[base] + int(off or 0), 0x77)
        elif op in ("strb", "strb.w"):
            base, off = re.match(r"\[(\w+)(?:, #(\d+))?\]", a[1]).groups()
            mem[reg[base] + int(off or 0)] = reg[a[0]] & 0xff
        elif op in ("movs", "movw", "mov.w") and a[1].startswith("#"):
            reg[a[0]] = num(a[1])
        elif op == "mov":
            reg[a[0]] = reg[a[1]]
        elif op == "add" and a[1] == "sp":
            reg[a[0]] = reg["sp"] + num(a[2])
        elif op == "cmp":
            flags = reg[a[0]] - num(a[1])
        elif op in ("beq.n", "bne.n", "b.n"):
            if op == "b.n" or (op == "beq.n") == (flags == 0):
                nxt = int(a[0], 16)
        elif op in ("cbz", "cbnz"):
            if (reg[a[0]] == 0) == (op == "cbz"):
                nxt = int(a[1], 16)
        elif op == "bl":
            calls.append((int(a[0], 16), reg["r0"], reg["r1"], reg["r2"], reg["r3"]))
            reg.update(r0=0x8617 if int(a[0], 16) == 0x18601010 else 0, r1=0xbad, r2=0xbad, r3=0xbad)
        else:
            return ("UNKNOWN %s %s at %#x" % (op, args, pc),)
        pc = nxt
    return (tuple(calls), mem.get(0x1001), mem.get(0x1002), reg["r5"], mem[0x200001])


def main():
    old, new = load(sys.argv[1]), load(sys.argv[2])
    bad = n = 0
    for r0, engine, r6, sp64, mode in itertools.product((0, 3), (0, 1), (0, 1), (16, 2), (1, 7, 13, 0x40)):
        a = run(old, r0, engine, r6, sp64, mode)
        b = run(new, r0, engine, r6, sp64, mode)
        n += 1
        if mode != 0x40:
            ok = a == b
        else:                                   # same, minus the menu call; result "Playlists chosen"; start code reset
            ok = (b[0] == tuple(c for c in a[0] if c[0] != 0x18601010) and b[1:3] == a[1:3]
                  and b[3] == 0x8610 and b[4] == 1 and len(a[0]) == len(b[0]) + 1)
        if not ok:
            bad += 1
            print("MISMATCH", (r0, engine, r6, sp64, mode), a, b)
    print("%d input combinations, %d mismatches" % (n, bad))
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
