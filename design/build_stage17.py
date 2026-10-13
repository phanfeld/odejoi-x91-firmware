#!/usr/bin/env python3
"""Stage 17 of the Graphite design, built on the stage 16 image: the eBook reader breaks lines between words.

Seen with stage 16: a line that is full ends wherever the next character no longer fits, in the middle of a
word too. The display driver's line-measuring routine (function 24, 0x0b0604aa) can do better: with bit 1 of
its mode set, a line that would end inside a word ends before that word instead. A word, for the driver, is a
run of the letters A to Z, a to z and the straight apostrophe. The reader passes mode 0; the mode is one number
set when a book is opened (EBOOK.AP 0x180c1218), next to the lines per page and the line width. It becomes 2.

Page breaks move with it, so the signature of the page indexes changes once more.

Limits that come with the driver's rule, not looked after here (a job for a book-preparation script):
  - a word wider than a whole line: in a two-byte (UTF-16) text about 127 characters are skipped at that spot,
    in a one-byte text the reader cannot get past it;
  - accented letters and the curly apostrophe do not count as letters, so a line may still end right before
    or after one of them inside a word;
  - in a two-byte text a line that was broken this way starts with the space that stood before the word.

usage: build_stage17.py [OUT_DIR]      (default: ../x91_dump/stage17)
"""
import hashlib
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage5 as s5  # noqa: E402
import build_stage16 as s16  # noqa: E402

WORD_BREAKS = 2                                  # mode bit 1 of the driver's line measuring
OLD_SIGNATURE, NEW_SIGNATURE = s16.NEW_SIGNATURE, 0x55aaaa57


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage17")
    os.makedirs(out, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE16") or os.path.join(ROOT, "x91_dump", "stage16", "x91_lfi_stage16.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 16 image does not pass its checksums")
    ap = bytearray(lfi.get("EBOOK.AP"))
    segs, _ = ap_dis.segments(ap)
    at = lambda addr: ap_dis.find(segs, addr)
    # movs r1, #0 ; strh.w r1, [r0, #568]   ->   movs r1, #2 ; ...
    s5.patch_bytes(ap, at(0x180c1218), bytes.fromhex("0021a0f83812"), bytes([WORD_BREAKS]) + bytes.fromhex("21a0f83812"),
                   "EBOOK.AP line-measuring mode")
    for addr in s16.SIGNATURE_AT:
        s5.patch_bytes(ap, at(addr), struct.pack("<I", OLD_SIGNATURE), struct.pack("<I", NEW_SIGNATURE), "EBOOK.AP page-index signature")
    lfi.put("EBOOK.AP", bytes(ap))
    print("reader: lines end between words (mode %d); page-index signature %#x" % (WORD_BREAKS, NEW_SIGNATURE))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage17.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
