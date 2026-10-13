#!/usr/bin/env python3
"""Disassemble an Actions US215A driver (.DRV), resident part and code banks.

Layout found in DRV_UI.DRV of the X91: header with the resident text (file offset, length, address at 0x08)
and data, then at 0x30 the file offsets of three bank groups. A bank's address is
0x13NN0000 (first group, 0x400 apart in the file), 0x0bNN0400 (second, 0x800 apart) or 0x03NN0c00 (third,
0x400 apart) with NN = 2 * its place in the group. The function table (address at 0x3c) holds such
addresses directly, next to addresses in the resident part.

usage: drv_dis.py FILE.DRV OUT_DIR
"""
import os
import struct
import subprocess
import sys

GROUPS = ((0x13000000, 0x400), (0x0b000400, 0x800), (0x03000c00, 0x400))


def segments(drv):
    t_off, t_len, t_addr, d_off, d_len, d_addr = struct.unpack_from("<6I", drv, 8)
    segs = [("text", t_addr, t_off, t_len), ("data", d_addr, d_off, d_len)]
    starts = list(struct.unpack_from("<3I", drv, 0x30)) + [len(drv)]
    for g, (base, step) in enumerate(GROUPS):
        for k in range((starts[g + 1] - starts[g]) // step):
            off = starts[g] + k * step
            body = drv[off:off + step].rstrip(b"\0")
            if body:
                segs.append(("bank", base + (2 * k << 16), off, (len(body) + 3) & ~3))
    return segs


def find(segs, addr):
    for kind, a, off, ln in segs:
        if a <= addr < a + ln:
            return off + addr - a
    return None


def main():
    path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    drv = open(path, "rb").read()
    segs = segments(drv)
    name = os.path.basename(path).split(".")[0].lower()
    with open(os.path.join(out, name + ".map"), "w") as m:
        for kind, addr, off, ln in segs:
            m.write("%-5s addr %#010x  file %#07x  len %#06x\n" % (kind, addr, off, ln))
    with open(os.path.join(out, name + ".dis"), "w") as f:
        for kind, addr, off, ln in segs:
            if kind == "data":
                continue
            tmp = os.path.join(out, "_seg.bin")
            open(tmp, "wb").write(drv[off:off + ln])
            r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                                "--adjust-vma=%#x" % addr, tmp], capture_output=True, text=True)
            f.write("\n;;;; %s %#010x len %#x (file %#x)\n" % (kind, addr, ln, off))
            f.write("\n".join(r.stdout.splitlines()[7:]) + "\n")
            os.remove(tmp)
    print(name, len(segs), "segments")


if __name__ == "__main__":
    main()
