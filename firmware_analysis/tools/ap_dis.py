#!/usr/bin/env python3
"""Split an Actions US215A program (.AP) into its code segments and disassemble them.

Layout found in the X91 firmware: header with the resident text and data segments
(file offset, length, address at 0x08/0x14), then four tables of 12-byte records
(file offset, address, length) at 0x800, 0x1000, 0x1800 and 0x2000, one record per code bank.
Every bank has its own address (0x18NN1000 and so on); calls between banks are ordinary BL.

usage: ap_dis.py FILE.AP OUT_DIR
"""
import os
import struct
import subprocess
import sys


def segments(ap):
    segs = []
    t_off, t_len, t_addr, d_off, d_len, d_addr, b_len, b_addr, entry = struct.unpack_from("<9I", ap, 8)
    segs.append(("text", t_addr, t_off, t_len))
    segs.append(("data", d_addr, d_off, d_len))
    for base in (0x800, 0x1000, 0x1800, 0x2000):
        for i in range(0, 0x800, 12):
            off, addr, ln = struct.unpack_from("<III", ap, base + i)
            if off and ln:
                segs.append(("bank", addr, off, ln))
    return segs, dict(bss=(b_addr, b_len), entry=entry)


def find(segs, addr):
    for kind, a, off, ln in segs:
        if a <= addr < a + ln:
            return off + addr - a
    return None


def main():
    path, out = sys.argv[1], sys.argv[2]
    os.makedirs(out, exist_ok=True)
    ap = open(path, "rb").read()
    segs, info = segments(ap)
    name = os.path.basename(path).split(".")[0].lower()
    with open(os.path.join(out, name + ".map"), "w") as m:
        m.write("entry %#x  bss %#x+%#x\n" % (info["entry"], info["bss"][0], info["bss"][1]))
        for kind, addr, off, ln in segs:
            m.write("%-5s addr %#010x  file %#07x  len %#06x\n" % (kind, addr, off, ln))
    with open(os.path.join(out, name + ".dis"), "w") as f:
        for kind, addr, off, ln in segs:
            if kind == "data":
                continue
            tmp = os.path.join(out, "_seg.bin")
            open(tmp, "wb").write(ap[off:off + ln])
            r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                                "--adjust-vma=%#x" % addr, tmp], capture_output=True, text=True)
            f.write("\n;;;; %s %#010x len %#x (file %#x)\n" % (kind, addr, ln, off))
            f.write("\n".join(r.stdout.splitlines()[7:]) + "\n")
            os.remove(tmp)
    print(name, len(segs), "segments")


if __name__ == "__main__":
    main()
