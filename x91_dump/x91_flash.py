#!/usr/bin/env python3
"""Vendor flash procedure for the ODEJOI X91 (ATJ2157, NAND 89 84 64 3c a5), replayed with actions_dump.

The sequence is the one the vendor's Windows tool runs (script `AdfuUpgrade` inside every firmware
package), as worked out and proven on an AGPTEK A02 by the a02-os project
(https://github.com/TheWirelessPhoenix/a02-os), which also published the read-only driver patch used
below. The USB transport is actions_dump from https://github.com/ilyakurdyukov/actions_flash.
Every device-specific value is taken from this unit's own boot record instead of from a firmware package.

  x91_flash.py prepare                  offline: build and cross-check the work files
  sudo x91_flash.py rehearse            device, READ-ONLY driver: read the firmware through the
                                        vendor driver and compare it with the verified dump
  sudo x91_flash.py dump --out F        device, READ-ONLY driver: read the firmware area into F
                                        and check its checksums
  sudo x91_flash.py write --image F --yes-write-flash [--backup B]
                                        device, stock driver: write F to the firmware area,
                                        read it back and compare. Refuses without a passed rehearsal.
                                        With --backup the current firmware is saved to B first.

The player must be in upgrade mode (10d6:10d6), entered with `adfu_reboot` from a fresh power-on,
with no other program run in that session.
"""
import argparse
import hashlib
import os
import re
import struct
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DUMP = HERE
AD = HERE.parent / "actions_flash"
HELP = HERE / "flash_helpers"
WORK = HERE / "flash_work"

NAND_ID = bytes.fromhex("8984643ca5")
PARAM_ADDR = 0x125400
STOCK_FWSC_SHA = "93c4686260826e635babb16226e1a348a971892ef09fcdaaa4f70bfde4d7bcf9"
RO_FWSC_SHA = "9008981c49e27ed684764b6ed7ceaac83f0afe375bc3e1b604dc1d6952f617ff"
# read-only driver: erase and program return at once (patch from a02-os)
RO_PATCHES = [(0x3FA0, "f0b587b0", "01207047"),   # erase:   movs r0,#1 ; bx lr
              (0x4B44, "70b53f4d", "00207047")]   # program: movs r0,#0 ; bx lr
PRESERVE = [(0x28, 0x38), (0x4F, 0x80)]           # per-device fields in the firmware header
# flags the sibling builds of July 2025 set in the driver header (same project family)
FLAG_AUTOREBOOT, FLAG_PROG_SPEEDUP = 1, 1


def sha(b):
    return hashlib.sha256(b).hexdigest()


def sum16(b):
    return sum(struct.unpack("<%dH" % (len(b) // 2), b[:len(b) & ~1])) & 0xffff


def sum32(b):
    return sum(struct.unpack("<%dI" % (len(b) // 4), b[:len(b) & ~3])) & 0xffffffff


def lfi_problems(img):
    """Header, directory and every file checksum, as the boot loader and updater check them."""
    bad = []
    if img[:4] != b"\x55\xaa\xf0\x0f":
        return ["no firmware magic"]
    if sum16(img[:0x1fe]) != struct.unpack_from("<H", img, 0x1fe)[0]:
        bad.append("header checksum")
    if sum32(img[0x200:0x2000]) != struct.unpack_from("<I", img, 0x10)[0]:
        bad.append("directory checksum")
    for i in range(0x200, 0x2000, 0x20):
        e = img[i:i + 0x20]
        if not e[0]:
            break
        off, ln, chk = struct.unpack_from("<I", e, 0x10)[0] << 9, struct.unpack_from("<I", e, 0x14)[0], struct.unpack_from("<I", e, 0x1c)[0]
        if off + ln > len(img) or sum32(img[off:off + ln]) != chk:
            bad.append("file " + e[:11].decode("latin-1").strip())
    return bad


def need(path, what):
    if not Path(path).exists():
        sys.exit("missing %s: %s" % (what, path))
    return Path(path)


def search_id(table, id8):
    """Vendor rule SERACH_ID: first 128-byte record matching the NAND ID, and the driver type."""
    for off in range(512, len(table) - 127, 128):
        rec = table[off:off + 128]
        if all(rec[i] == 0xFF or rec[i] == id8[i] for i in range(8)):
            break
    else:
        sys.exit("NAND ID not in the vendor table")
    if not rec[22] & 8:
        return rec, 0xF644
    m, d5 = rec[0], rec[5]
    for cond, t in [(m == 0xAD and d5 & 7 == 3, 0xF645), (m == 0x98, 0xF646), (m == 0xAD and d5 & 7 == 4, 0xF647),
                    (m == 0xAD and d5 & 15 == 10, 0xF655), (m == 0xEC and d5 & 7 == 4, 0xF648), (m == 0x2C, 0xF649),
                    (m == 0x89, 0xF651), (m == 0x45 and d5 == 0x57, 0xF650), (m == 0x45 and d5 == 0x50, 0xF652),
                    (m == 0x45 and d5 == 0x56, 0xF653), (m == 0x45 and d5 & 15 == 1, 0xF654)]:
        if cond:
            return rec, t
    return rec, 0xF644


def prepare(quiet=False):
    say = (lambda *a: None) if quiet else print
    WORK.mkdir(exist_ok=True)
    brec = need(DUMP / "brec0.bin", "boot record dump").read_bytes()
    stock = need(DUMP / "x91_lfi_verified.bin", "verified firmware image").read_bytes()
    table = need(HELP / "flash_id.bin", "vendor NAND table").read_bytes()
    drv = need(HELP / "fwscf651.bin", "vendor flash driver").read_bytes()
    need(HELP / "nandhwsc.bin", "vendor hardware scan")
    need(AD / "actions_dump", "actions_dump")
    need(AD / "payload_arm" / "adfus.bin", "adfus loader")

    code_sec, total_sec, lfi_sec = struct.unpack_from("<HHI", brec, 4)
    checks = []
    checks.append(("boot record code checksum", struct.unpack_from("<H", brec, 0)[0] == (sum16(brec[2:code_sec * 512]) + 0x1234) & 0xffff))
    checks.append(("verified image passes all its checksums", not lfi_problems(stock)))
    checks.append(("image size equals the size in the boot record (%d sectors)" % lfi_sec, len(stock) == lfi_sec * 512))
    rec, ftype = search_id(table, NAND_ID + b"\x0c\x00\x00")
    checks.append(("NAND ID maps to driver f651", ftype == 0xF651))
    checks.append(("chip record equals the one stored in this unit's boot record", brec[0x80:0xC0] == rec[:64]))
    checks.append(("flash driver is the stock fwscf651.bin proven by a02-os", sha(drv) == STOCK_FWSC_SHA))
    mfp = brec[0x40:0x80]
    checks.append(("pin table in the boot record looks filled in", mfp[:3] != b"\xff\xff\xff" and mfp[0] != 0))

    def header(d):
        f = bytearray(d)
        f[2] = 0                                   # FLASH_ERASE flag: never erase the whole flash
        struct.pack_into("<H", f, 6, total_sec)    # boot record size incl. boot picture
        struct.pack_into("<I", f, 8, lfi_sec)      # firmware size
        f[128:192] = mfp                           # this unit's pin table
        f[255], f[253] = FLAG_AUTOREBOOT, FLAG_PROG_SPEEDUP
        return f

    ro = bytearray(drv)
    for off, exp, rep in RO_PATCHES:
        if ro[off:off + 4].hex() != exp:
            sys.exit("read-only patch: original bytes differ at 0x%x" % off)
        ro[off:off + 4] = bytes.fromhex(rep)
    checks.append(("read-only driver equals a02-os's published hash", sha(ro) == RO_FWSC_SHA))
    fw_ro, fw_rw = header(ro), header(drv)
    checks.append(("driver code is untouched by the header values", fw_rw[0x200:] == drv[0x200:] and fw_ro[0x200:] == ro[0x200:]))

    ok = True
    for name, good in checks:
        say("  %-62s %s" % (name, "ok" if good else "MISMATCH"))
        ok &= good
    if not ok:
        sys.exit("REFUSED: a cross-check failed; nothing was written to disk")
    (WORK / "fwsc-ro.bin").write_bytes(fw_ro)
    (WORK / "fwsc.bin").write_bytes(fw_rw)
    (WORK / "nandinfo.bin").write_bytes(rec)
    vram = bytearray(512)
    vram[510:512] = b"\xaa\xbb"
    (WORK / "vram_last.bin").write_bytes(vram)
    say("work files in %s: fwsc-ro.bin, fwsc.bin, nandinfo.bin, vram_last.bin" % WORK)
    say("firmware: %d sectors, sha256 %s" % (lfi_sec, sha(stock)))
    return stock


def run(args, what):
    cmd = [str(AD / "actions_dump"), "--wait", "20", "chip", "2157", "timeout", "60000"] + [str(a) for a in args]
    print("\n== %s" % what)
    r = subprocess.run(cmd, cwd=AD, capture_output=True, text=True, timeout=1800)
    out = r.stdout + r.stderr
    print("   " + "\n   ".join(out.strip().splitlines()[-10:]))
    if r.returncode or "failed" in out or "unexpected" in out:
        sys.exit("STOP: '%s' did not complete. Unplug, then hold the power key 10 to 15 s to restart the player." % what)
    return out


def hexdump_bytes(out):
    data = bytearray()
    for line in out.splitlines():
        m = re.match(r"^((?:[0-9a-f]{2} ){1,16})\s*\|", line)
        if m:
            data += bytes.fromhex(m.group(1).replace(" ", ""))
    return bytes(data)


def bring_up(driver):
    """Steps 1 to 3 of the vendor sequence: loader, hardware scan, flash driver with chip record."""
    run(["simple_switch", "0x118000", AD / "payload_arm" / "adfus.bin"], "loader (adfus)")
    hw = hexdump_bytes(run(["write_mem", "0x11e000", "0", "0", HELP / "nandhwsc.bin", "exec_ret", "0x11e000", "-1"],
                           "hardware scan (vendor nandhwsc)"))
    if len(hw) < 0x20 or hw[0:2] != b"HW" or hw[16:21] != NAND_ID or int.from_bytes(hw[0x18:0x1C], "little") != PARAM_ADDR:
        sys.exit("STOP: unexpected hardware scan %s" % hw[:32].hex())
    print("   hardware scan ok: NAND %s, chip-record slot 0x%x" % (hw[16:22].hex(), PARAM_ADDR))
    st = hexdump_bytes(run(["write_mem", "0x11e000", "0", "0", driver,
                            "write_mem", hex(PARAM_ADDR), "0", "0", WORK / "nandinfo.bin",
                            "exec_ret", "0x11e200", "-1"], "flash driver + chip record"))
    (WORK / "fwsc_status.bin").write_bytes(st)
    print("   driver status (%d bytes): %s" % (len(st), st[:32].hex()))
    if st[6:12] != b"NAFWSC":
        sys.exit("STOP: the driver did not report NAFWSC")


def compare(a, b):
    return [i // 512 for i in range(0, max(len(a), len(b)), 512) if a[i:i + 512] != b[i:i + 512]]


def give_back(path):
    """A file written under sudo goes back to the user who called sudo."""
    uid, gid = os.environ.get("SUDO_UID"), os.environ.get("SUDO_GID")
    if uid and gid and os.geteuid() == 0:
        os.chown(path, int(uid), int(gid))


def save_read(size, out, what):
    """Read the firmware area into `out` (through a temporary name) and report on it; returns the checksum problems."""
    out = Path(out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    give_back(out.parent)
    tmp = out.with_name(out.name + ".part")
    run(["blk_size", "0x4000", "read_lfi", "0", hex(size), tmp], what)
    img = tmp.read_bytes()
    probs = lfi_problems(img) if len(img) == size else ["size %d instead of %d" % (len(img), size)]
    os.replace(tmp, out)
    give_back(out)
    print("   saved: %s" % out)
    print("   %d bytes, sha256 %s" % (len(img), sha(img)))
    print("   checksums: %s" % ("all ok" if not probs else "PROBLEMS: %s" % ", ".join(probs[:5])))
    return probs


def dump(out):
    stock = prepare(quiet=True)
    print("cross-checks passed; using the READ-ONLY driver (erase and program are disabled)")
    bring_up(WORK / "fwsc-ro.bin")
    probs = save_read(len(stock), out, "read the whole firmware through the driver")
    print("\nDUMP %s" % ("COMPLETE: the image passes all its checksums." if not probs else "SAVED, BUT IT FAILS ITS CHECKSUMS."))
    print("Now unplug and hold the power key 10 to 15 s, then switch on normally.")
    if probs:
        sys.exit(3)


def rehearse():
    stock = prepare(quiet=True)
    print("cross-checks passed; using the READ-ONLY driver (erase and program are disabled)")
    bring_up(WORK / "fwsc-ro.bin")
    run(["read_lfi", "0", "0x2000", WORK / "lfi_head.bin"], "read header and directory through the driver")
    head = (WORK / "lfi_head.bin").read_bytes()
    if head != stock[:0x2000]:
        sys.exit("STOP: header/directory differ from the verified dump (saved lfi_head.bin)")
    print("   header and directory: identical to the verified dump")
    run(["blk_size", "0x4000", "read_lfi", "0", hex(len(stock)), WORK / "lfi_via_driver.bin"],
        "read the whole firmware through the driver")
    full = (WORK / "lfi_via_driver.bin").read_bytes()
    bad = compare(full, stock)
    print("\nRESULT: %d of %d sectors differ from the verified dump" % (len(bad), len(stock) // 512))
    if bad:
        sys.exit("NOT identical (first sectors %s). Do not write. Restart the player with the power key." % bad[:8])
    (WORK / "rehearsal_ok").write_text(sha(stock) + "\n")
    print("REHEARSAL PASSED: the vendor driver reads this unit's firmware exactly as dumped.")
    print("Now unplug and hold the power key 10 to 15 s, then switch on normally.")


def write(image_path, backup=None):
    stock = prepare(quiet=True)
    ok = WORK / "rehearsal_ok"
    if not ok.exists() or ok.read_text().strip() != sha(stock):
        sys.exit("REFUSED: no passed rehearsal for this firmware (run 'rehearse' first)")
    image = bytearray(Path(image_path).read_bytes())
    if len(image) != len(stock):
        sys.exit("REFUSED: the image must be exactly %d bytes (the boot loader rejects any other size)" % len(stock))
    probs = lfi_problems(bytes(image))
    if probs:
        sys.exit("REFUSED: image fails its own checksums: %s" % probs[:5])
    bring_up(WORK / "fwsc.bin")
    run(["read_lfi", "0", "0x200", WORK / "device_head.bin"], "read the current header")
    dev = (WORK / "device_head.bin").read_bytes()
    if dev[:4] != b"\x55\xaa\xf0\x0f":
        sys.exit("STOP: the device header has no firmware magic")
    if backup:
        if save_read(len(stock), backup, "back up the current firmware"):
            print("   note: the firmware now on the player fails its checksums; the backup was kept as read")
    for s, e in PRESERVE:
        image[s:e] = dev[s:e]
    struct.pack_into("<H", image, 0x1FE, sum16(bytes(image[:0x1FE])))
    if lfi_problems(bytes(image)):
        sys.exit("STOP: image invalid after keeping the per-device fields")
    (WORK / "image.bin").write_bytes(image)
    print("   image: %d sectors, sha256 %s" % (len(image) // 512, sha(bytes(image))))
    run(["blk_size", "0x4000", "write_flash", "0xc0000000", "0", "0", WORK / "image.bin"], "WRITE the firmware area")
    run(["write_flash", "0xff000000", "0", "0", WORK / "vram_last.bin"], "finalize")
    run(["blk_size", "0x4000", "read_lfi", "0", hex(len(image)), WORK / "readback.bin"], "read back")
    bad = compare((WORK / "readback.bin").read_bytes(), bytes(image))
    if bad:
        print("\nVERIFY FAILED: %d sectors differ (first %s)." % (len(bad), bad[:8]))
        sys.exit("Leave the player plugged in and in upgrade mode. Do NOT restart it. Run the write again.")
    print("\nVERIFIED: all %d sectors read back identical." % (len(image) // 512))
    print("Now unplug and hold the power key 10 to 15 s, then switch on normally.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["prepare", "rehearse", "dump", "write"])
    ap.add_argument("--image")
    ap.add_argument("--out")
    ap.add_argument("--backup")
    ap.add_argument("--yes-write-flash", action="store_true")
    a = ap.parse_args()
    if a.mode == "prepare":
        prepare()
    elif a.mode == "rehearse":
        rehearse()
    elif a.mode == "dump":
        if not a.out:
            sys.exit("dump needs --out FILE")
        dump(a.out)
    else:
        if not a.image or not a.yes_write_flash:
            sys.exit("write needs --image FILE and --yes-write-flash")
        write(a.image, a.backup)
