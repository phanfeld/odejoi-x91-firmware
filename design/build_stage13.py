#!/usr/bin/env python3
"""Stage 13 of the Graphite design, built on the stage 12 image. One correction to the playing screen (MUSIC.STY).

The shared status-bar code paints its 20-pixel icon box at the top left about half a second after the screen is
drawn, also when it has no icon to show there. A track counter at x=2 is covered by it, so the counter goes
to x=22, just right of that box.

usage: build_stage13.py [OUT_DIR]      (default: ../x91_dump/stage13)
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import x91_modify as xm  # noqa: E402
import build_stage11 as s11  # noqa: E402


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage13")
    os.makedirs(out, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE12") or os.path.join(ROOT, "x91_dump", "stage12", "x91_lfi_stage12.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 12 image does not pass its checksums")
    sty = bytearray(lfi.get("MUSIC.STY"))
    s11.set_fields(sty, 3, 28, 0, w0=22, w8=22)
    lfi.put("MUSIC.STY", bytes(sty))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage13.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
