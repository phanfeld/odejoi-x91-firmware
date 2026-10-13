#!/usr/bin/env python3
"""Stage 12 of the Graphite design, built on the stage 11 image. Two corrections to the playing screen (MUSIC.STY).

  1. The play-state picture box shows its first picture while the track plays and its second while it is paused.
     Stage 11 had drawn "pause" and "play" the wrong way round; they are swapped.
  2. The firmware shows no program icon in the status bar on this screen, so the track counter moves to the left edge.

usage: build_stage12.py [OUT_DIR]      (default: ../x91_dump/stage12)
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage11 as s11  # noqa: E402


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage12")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE11") or os.path.join(ROOT, "x91_dump", "stage11", "x91_lfi_stage11.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 11 image does not pass its checksums")
    sty = bytearray(lfi.get("MUSIC.STY"))
    s1.set_picture(sty, 63, s1.render_565(s11.state_icon("pause"), 16, 16, work, "state-playing"), 16, 16)   # shown while playing
    s1.set_picture(sty, 62, s1.render_565(s11.state_icon("play"), 16, 16, work, "state-paused"), 16, 16)     # shown while paused
    s11.set_fields(sty, 3, 28, 0, w0=2, w8=2)                                                                # track counter
    lfi.put("MUSIC.STY", bytes(sty))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage12.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
