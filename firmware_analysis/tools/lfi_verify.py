#!/usr/bin/env python3
"""Verify an Actions LFI dump read twice (each read holds two copies) and write a checked image.

usage: lfi_verify.py READ1 READ2 FW_SECTORS PAGE_SIZE OUT_IMAGE [UNPACK_DIR]
"""
import hashlib
import itertools
import os
import struct
import sys

r1 = open(sys.argv[1], "rb").read()
r2 = open(sys.argv[2], "rb").read()
fw = int(sys.argv[3], 0) * 512
psize = int(sys.argv[4], 0)
out = sys.argv[5]
unpack = sys.argv[6] if len(sys.argv) > 6 else None
half = len(r1) // 2
assert len(r1) == len(r2) and half >= fw
cands = {"read1/copy1": r1[:fw], "read1/copy2": r1[half:half + fw],
         "read2/copy1": r2[:fw], "read2/copy2": r2[half:half + fw]}
names = list(cands)


def sum16(b):
    return sum(struct.unpack("<%dH" % (len(b) // 2), b[:len(b) & ~1])) & 0xffff


def sum32(b):
    return sum(struct.unpack("<%dI" % (len(b) // 4), b[:len(b) & ~3])) & 0xffffffff


print("firmware bytes:", fw)
for a, b in itertools.combinations(names, 2):
    pages = [p for p in range(0, fw, psize) if cands[a][p:p + psize] != cands[b][p:p + psize]]
    nbytes = sum(x != y for p in pages for x, y in zip(cands[a][p:p + psize], cands[b][p:p + psize]))
    print("%-12s vs %-12s: %2d differing pages %s, %d differing bytes"
          % (a, b, len(pages), [hex(p) for p in pages[:6]], nbytes))

head = None
for n in names:
    c = cands[n]
    ok_head = c[:4] == b"\x55\xaa\xf0\x0f" and sum16(c[:0x1fe]) == struct.unpack_from("<H", c, 0x1fe)[0]
    ok_dir = sum32(c[0x200:0x2000]) == struct.unpack_from("<I", c, 0x10)[0]
    print("%-12s header ok: %s, directory ok: %s" % (n, ok_head, ok_dir))
    if ok_head and ok_dir and head is None:
        head = n
assert head, "no candidate has a valid header and directory"
base = cands[head]
print("version string:", base[4:16].split(b"\0")[0].decode())
image = bytearray(base)
entries = []
for i in range(0x200, 0x2000, 0x20):
    e = base[i:i + 0x20]
    if not e[0]:
        break
    nm = (e[:8].decode("latin-1").rstrip() + "." + e[8:11].decode("latin-1").rstrip()).rstrip(".")
    off = struct.unpack_from("<I", e, 0x10)[0] << 9
    ln = struct.unpack_from("<I", e, 0x14)[0]
    chk = struct.unpack_from("<I", e, 0x1c)[0]
    entries.append((nm, off, ln, chk))
print("directory entries:", len(entries))
bad = 0
covered = 0x2000
for nm, off, ln, chk in entries:
    good = [n for n in names if sum32(cands[n][off:off + ln]) == chk]
    covered = max(covered, off + ln)
    if good:
        image[off:off + ln] = cands[good[0]][off:off + ln]
        if len(good) < len(names):
            print("  %-13s off=0x%07x len=%8d  valid in %d of 4: %s" % (nm, off, ln, len(good), ", ".join(good)))
        continue
    # no candidate is clean: mix pages across the four candidates until the checksum fits
    pages = sorted({(off + k) // psize * psize for k in range(0, ln, 512)})
    var = [p for p in pages if len({cands[n][max(p, off):min(p + psize, off + ln)] for n in names}) > 1]
    fixed = False
    if len(var) <= 6:
        opts = [sorted({cands[n][max(p, off):min(p + psize, off + ln)] for n in names}) for p in var]
        for combo in itertools.product(*opts):
            buf = bytearray(base[off:off + ln])
            for p, chunk in zip(var, combo):
                s = max(p, off) - off
                buf[s:s + len(chunk)] = chunk
            if sum32(bytes(buf)) == chk:
                image[off:off + ln] = buf
                fixed = True
                break
    print("  %-13s off=0x%07x len=%8d  valid in 0 of 4; %d varying pages; %s"
          % (nm, off, ln, len(var), "REPAIRED by mixing pages" if fixed else "NOT REPAIRED"))
    bad += 0 if fixed else 1
print("files failing their checksum after repair:", bad)
print("last byte covered by files: 0x%x of 0x%x" % (covered, fw))
ok = all(sum32(bytes(image[o:o + l])) == c for _, o, l, c in entries)
print("final image: every file checksum ok:", ok, " sha256:", hashlib.sha256(image).hexdigest())
with open(out, "wb") as f:
    f.write(image)
if unpack:
    os.makedirs(unpack, exist_ok=True)
    for nm, off, ln, chk in entries:
        safe = "".join(ch if ch.isalnum() or ch in "._$-" else "_" for ch in nm)
        with open(os.path.join(unpack, safe), "wb") as f:
            f.write(image[off:off + ln])
    print("unpacked", len(entries), "files to", unpack)
