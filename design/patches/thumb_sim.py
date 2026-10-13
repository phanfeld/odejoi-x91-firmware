#!/usr/bin/env python3
"""A small interpreter for straight-line Thumb code, working on objdump's text output.

It knows only the instruction forms that occur in the stretches patched in this project and stops with an
error on anything else, so a result is never based on a guess. Used to run stock and patched code side by side.
"""
import re


def load(path, start, end):
    code = {}
    for line in open(path):
        m = re.match(r"\s*([0-9a-f]{8}):\t([0-9a-f ]+)\t(\S+)\t?([^@]*)", line)
        if m:
            a = int(m.group(1), 16)
            if start <= a < end:
                lit = re.search(r"@ \(?0x([0-9a-f]+)\)?\s*$", line)
                code[a] = (len(m.group(2).replace(" ", "")) // 2, m.group(3), m.group(4).strip(),
                           int(lit.group(1), 16) if lit else None)
    return code


class Machine:
    def __init__(self, regs, mem):
        self.r = dict(regs)
        self.mem = dict(mem)             # address -> byte
        self.calls = []
        self.cmp = None
        self.returns = []                # return addresses of subroutine calls inside the code under test
        self.saved = []                  # registers put aside by push, restored by the matching pop

    def rd(self, addr, n):
        return sum(self.mem.get(addr + i, 0xEE) << (8 * i) for i in range(n))

    def wr(self, addr, n, value):
        for i in range(n):
            self.mem[addr + i] = (value >> (8 * i)) & 0xff

    def val(self, tok):
        tok = tok.strip()
        return int(tok[1:], 0) if tok.startswith("#") else self.r[tok]

    def run(self, code, start, exits, on_call, limit=400):
        pc = start
        for _ in range(limit):
            if pc in exits:
                return pc
            if pc not in code:
                raise RuntimeError("left the code at %#x" % pc)
            size, op, args, lit = code[pc]
            if op.split(".")[0] in ("push", "stmdb"):                 # the values are kept aside, not in the memory picture
                names = re.findall(r"r\d+|lr|sl|fp|ip", args.split("{")[1])
                self.r["sp"] -= 4 * len(names)
                self.saved.append({k: self.r.get(k) for k in names})
                pc += size
                continue
            if op.split(".")[0] in ("pop", "ldmia"):
                names = re.findall(r"r\d+|lr|sl|fp|ip|pc", args.split("{")[1])
                self.r["sp"] += 4 * len(names)
                frame = self.saved.pop() if self.saved else {}
                for k in names:
                    if k != "pc" and frame.get(k) is not None:
                        self.r[k] = frame[k]
                if "pc" in names:
                    if not self.returns:
                        return "return"
                    pc = self.returns.pop()
                    continue
                pc += size
                continue
            a = [x.strip() for x in re.split(r",\s*(?![^\[]*\])", args)] if args else []
            nxt = pc + size
            base = op.split(".")[0]
            mem = re.match(r"\[(\w+)(?:, #(-?\d+))?\]", a[1]) if len(a) > 1 and a[1].startswith("[") else None
            if base == "nop":
                pass
            elif base in ("ldr", "ldrh", "ldrb") and mem and mem.group(1) == "pc":
                self.r[a[0]] = self.rd(lit, 4)
            elif base in ("ldr", "ldrh", "ldrb") and mem:
                self.r[a[0]] = self.rd(self.r[mem.group(1)] + int(mem.group(2) or 0), {"ldr": 4, "ldrh": 2, "ldrb": 1}[base])
            elif base == "ldrsb" and mem:
                v = self.rd(self.r[mem.group(1)] + int(mem.group(2) or 0), 1)
                self.r[a[0]] = v | 0xffffff00 if v & 0x80 else v
            elif base in ("str", "strh", "strb") and mem:
                self.wr(self.r[mem.group(1)] + int(mem.group(2) or 0), {"str": 4, "strh": 2, "strb": 1}[base], self.r[a[0]])
            elif base in ("movs", "movw", "mov") and len(a) == 2:
                self.r[a[0]] = self.val(a[1])
            elif base in ("adds", "add") and len(a) == 4 and a[3].startswith("lsr #"):
                self.r[a[0]] = (self.val(a[1]) + (self.val(a[2]) >> int(a[3][5:]))) & 0xffffffff
            elif base in ("adds", "add") and len(a) == 4 and a[3].startswith("lsl #"):
                self.r[a[0]] = (self.val(a[1]) + (self.val(a[2]) << int(a[3][5:]))) & 0xffffffff
            elif base in ("lsrs", "lsls") and len(a) == 2 and not a[1].startswith("#"):   # shift by a register
                x, k = self.r[a[0]], self.r[a[1]] & 0xff
                self.r[a[0]] = ((x << k) if base == "lsls" else (x >> k)) & 0xffffffff if k < 32 else 0
            elif base in ("lsrs", "lsls", "asrs") and len(a) == 3 and a[2].startswith("#"):
                x, k = self.val(a[1]), int(a[2][1:])
                if base == "asrs" and x & 0x80000000:
                    x -= 1 << 32
                self.r[a[0]] = (x << k if base == "lsls" else x >> k) & 0xffffffff
            elif base in ("adds", "add", "subs", "sub") and len(a) in (2, 3):
                x, y = (self.val(a[1]), self.val(a[2])) if len(a) == 3 else (self.r[a[0]], self.val(a[1]))
                self.r[a[0]] = (x + y if base.startswith("add") else x - y) & 0xffffffff
            elif base == "muls":
                self.r[a[0]] = (self.val(a[1]) * self.val(a[2] if len(a) == 3 else a[0])) & 0xffffffff
            elif base == "udiv":
                self.r[a[0]] = self.val(a[1]) // self.val(a[2])
            elif base == "bic":
                self.r[a[0]] = self.val(a[1]) & ~self.val(a[2]) & 0xffffffff
            elif base == "movt":
                self.r[a[0]] = (self.r[a[0]] & 0xffff) | self.val(a[1]) << 16
            elif base == "uxtb":
                self.r[a[0]] = self.r[a[1]] & 0xff
            elif base == "uxth":
                self.r[a[0]] = self.r[a[1]] & 0xffff
            elif base == "cmp":
                self.cmp = (self.val(a[0]), self.val(a[1]))
            elif base in ("beq", "bne", "bcc", "bcs", "blt", "bge", "bhi", "bls"):
                x, y = self.cmp
                if {"beq": x == y, "bne": x != y, "bcc": x < y, "bcs": x >= y, "blt": x < y, "bge": x >= y,
                    "bhi": x > y, "bls": x <= y}[base]:
                    nxt = int(a[0], 16)
            elif base == "b":
                nxt = int(a[0], 16)
                if nxt not in code and nxt not in exits:               # a jump out of the code under test: a tail call
                    self.calls.append((nxt, self.r["r0"], self.r["r1"], self.r["r2"], self.r["r3"]))
                    self.r.update(r0=on_call(nxt, self), r1=0xBAD1, r2=0xBAD2, r3=0xBAD3)
                    self.cmp = None
                    nxt = self.r["lr"]
                    if self.returns and self.returns[-1] == nxt:
                        self.returns.pop()
            elif base in ("cbz", "cbnz"):
                if (self.r[a[0]] == 0) == (base == "cbz"):
                    nxt = int(a[1], 16)
            elif base == "bl":
                target = int(a[0], 16)
                if target in code:                                     # a subroutine inside the code under test: follow it
                    self.r["lr"] = nxt
                    self.returns.append(nxt)
                    nxt = target
                else:
                    self.calls.append((target, self.r["r0"], self.r["r1"], self.r["r2"], self.r["r3"]))
                    self.r.update(r0=on_call(target, self), r1=0xBAD1, r2=0xBAD2, r3=0xBAD3)
                    self.cmp = None
            else:
                raise RuntimeError("unknown instruction %s %s at %#x" % (op, args, pc))
            pc = nxt
        raise RuntimeError("did not finish")
