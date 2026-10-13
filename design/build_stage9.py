#!/usr/bin/env python3
"""Stage 9 of the Graphite design, built on the stage 8 image. One change, in MUSIC.AP (program code).

The progress knob on the playing screen flickered: on every refresh the firmware redrew the whole track
picture, which wipes the knob, and then the knob. The end of that routine is rewritten
(patches/music_progress.S): nothing is drawn while the knob stays where it is; when it moves one pixel,
the column it leaves is restored and the knob is drawn at its new place; a full repaint of the screen,
a seek or a new track are drawn as before.

usage: build_stage9.py [OUT_DIR]      (default: ../x91_dump/stage9)
"""
import hashlib
import os
import struct
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(ROOT, "firmware_analysis", "tools"))
import ap_dis  # noqa: E402
import x91_modify as xm  # noqa: E402

BANK, BANK_LEN, LO, HI = 0x18061000, 0x644, 0x3f4, 0x476
STOCK_REGION = "86863e98e791b216"
STATE = 0x00200191                       # must match STATE in the patch source


def disassemble(data, path):
    tmp = path + ".bin"
    open(tmp, "wb").write(data)
    r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                        "--adjust-vma=%#x" % BANK, tmp], capture_output=True, text=True)
    os.remove(tmp)
    open(path, "w").write(r.stdout)
    return path


def patch_music(lfi, work):
    src = os.path.join(HERE, "patches", "music_progress.S")
    if ".equ    STATE, 0x%08x" % STATE not in open(src).read():
        sys.exit("the state address in the patch source and in this script differ")
    obj, raw = os.path.join(work, "progress_patch.o"), os.path.join(work, "progress_patch.bin")
    for cmd in (["arm-none-eabi-as", "-o", obj, src], ["arm-none-eabi-objcopy", "-O", "binary", obj, raw]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit("could not assemble the progress patch: " + r.stderr[-300:])
    built = open(raw, "rb").read()[LO:HI]
    os.remove(raw)
    ap = bytearray(lfi.get("MUSIC.AP"))
    segs, _ = ap_dis.segments(ap)
    base = ap_dis.find(segs, BANK)
    bank = bytes(ap[base:base + BANK_LEN])
    if hashlib.sha256(bank[LO:HI]).hexdigest()[:16] != STOCK_REGION:
        sys.exit("MUSIC.AP: the routine to patch is not the expected one")
    # the state byte must be the one only the unused demo screensaver refers to
    demo = [struct.unpack_from("<I", ap, ap_dis.find(segs, a))[0] for a in (0x18cc1b94, 0x18cc1b98)]
    if demo != [STATE - 1, STATE]:
        sys.exit("MUSIC.AP: the spare byte is not where expected")
    others = 0
    for kind, addr, off, ln in segs:
        if kind != "data":
            for o in range(0, ln - 3, 2):
                if struct.unpack_from("<I", ap, off + o)[0] == STATE and addr + o != 0x18cc1b98:
                    others += 1
    if others:
        sys.exit("MUSIC.AP: something else refers to the spare byte")
    new_bank = bank[:LO] + built + bank[HI:]
    old_dis = disassemble(bank, os.path.join(work, "progress_old.dis"))
    new_dis = disassemble(new_bank, os.path.join(work, "progress_new.dis"))
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", "check_progress_patch.py"), old_dis, new_dis],
                       capture_output=True, text=True)
    if r.returncode:
        sys.exit("the progress patch failed its side-by-side check:\n%s%s" % (r.stdout[-600:], r.stderr[-300:]))
    ap[base + LO:base + HI] = built
    lfi.put("MUSIC.AP", bytes(ap))
    return r.stdout.strip()


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage9")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE8") or os.path.join(ROOT, "x91_dump", "stage8", "x91_lfi_stage8.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 8 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    # the quick path restores one column of the track with picture 66; it must equal a column of the track picture 67
    sty = lfi.get("MUSIC.STY")
    po = struct.unpack_from("<I", sty, 0x10)[0]
    pic = lambda i: struct.unpack_from("<IIHHH", sty, po + i * 16)
    (o66, l66, _, w66, h66), (o67, l67, _, w67, h67) = pic(66), pic(67)
    column = sty[o66:o66 + l66]
    if (w66, h66, h67) != (1, 6, 6) or any(bytes(sty[o67 + (y * w67 + x) * 2:o67 + (y * w67 + x) * 2 + 2]) != column[y * 2:y * 2 + 2]
                                           for y in range(6) for x in range(w67)):
        sys.exit("MUSIC.STY: picture 66 is not a column of the track picture 67")
    print("music program patch:", patch_music(lfi, work))
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage9.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
