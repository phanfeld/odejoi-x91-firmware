#!/usr/bin/env python3
"""Build the Graphite firmware images from the stock image, one per theme.

usage: build.py [--out DIR] [--check] [THEME ...]      themes: amber, mint, ice, berry (all of them if none is named)

Reads the stock firmware x91_dump/x91_lfi_verified.bin (dumped from the player, not in git; its sha256 is in
x91_dump/SHA256SUMS.txt), runs every part of the design on it (design/graphite/) and writes into DIR (default
x91_dump/themes):

  x91_lfi_THEME.bin   the flashable image
  themes.json         the list of images x91_tool.py offers
  THEME/unpacked/     the image's files
  THEME/work/         rendered pictures, compiled code, linker scripts, listings the checkers ran on
  THEME/build.txt     what each part did

The images are byte-for-byte reproducible. --check stops with an error unless every image built is the release image
(RELEASE below).
"""
import argparse
import datetime
import hashlib
import json
import os
import shutil
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
from graphite import VERSION, base  # noqa: E402
from graphite import lists, mainmenu, music, newcode, pictures, playlists, reader, screensaver, settings  # noqa: E402
from graphite import statusbar, typeface  # noqa: E402

STEPS = [typeface, mainmenu, pictures, screensaver, music, settings, reader, statusbar, lists, playlists]
OUT = os.path.join(ROOT, "x91_dump", "themes")
RELEASE = {                                      # sha256 of the 1.0.0 images (as flashed and tested: Berry b1f169d1...)
    "amber": "5fb39a7f8d86e210e9850c495d1621f1744039a78aa81dc9350a147948e50bab",
    "mint": "2b084b2692dc7680f33a674c02e80e61226ecbad9f52f5d9b792fa38b91e1f4b",
    "ice": "7f9358288c6dd28d0614618febbbd018d9878d2b5628fabfc496fe9bba20b7b5",
    "berry": "b1f169d16f5e6bf600725c355206fee4fb2d42d0ad9780cb2d23200a8c88bb80",
}


def build(theme, out):
    """One theme's image, from the stock image; returns its entry for themes.json."""
    folder = os.path.join(out, theme)
    work = os.path.join(folder, "work")
    shutil.rmtree(work, ignore_errors=True)
    os.makedirs(work)
    base.use_theme(theme)
    b = base.Build(theme, work)
    for step in STEPS:
        step.build(b)
    copies = base.refresh_copies(b)
    b.note("text-background copies refreshed: %s", "; ".join(copies) or "none")
    bad = b.lfi.check()
    if bad or len(b.lfi.d) != len(b.stock_image):
        base.fail("%s: checksum failures: %s; size %d" % (theme, ", ".join(bad) or "none", len(b.lfi.d)))
    image = os.path.join(out, "x91_lfi_%s.bin" % theme)
    with open(image, "wb") as f:
        f.write(b.lfi.d)
    shutil.rmtree(os.path.join(folder, "unpacked"), ignore_errors=True)
    b.lfi.unpack(os.path.join(folder, "unpacked"))
    digest = hashlib.sha256(b.lfi.d).hexdigest()
    changed = sorted(n for n in b.lfi.entries if b.lfi.get(n) != b.stock.get(n))
    b.note("files changed: %s", ", ".join(changed))
    b.note("checksum failures: none; sha256 %s%s", digest,
           " (the %s release image)" % VERSION if RELEASE.get(theme) == digest else "")
    with open(os.path.join(folder, "build.txt"), "w") as f:
        f.write("Graphite %s, %s\n\n%s\n" % (VERSION, theme, "\n".join(b.notes)))
    return {"id": theme, "name": theme.capitalize(), "accent": base.xd.THEMES[theme]["accent"], "file": os.path.basename(image),
            "version": VERSION, "sha256": digest, "built": datetime.date.today().isoformat()}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("themes", nargs="*", help="themes to build (default: all)")
    ap.add_argument("--out", default=OUT, help="output folder (default: x91_dump/themes)")
    ap.add_argument("--check", action="store_true", help="fail unless every image is the release image")
    a = ap.parse_args()
    xd = base.xd
    names = a.themes or list(xd.THEMES)
    for name in names:
        if name not in xd.THEMES:
            sys.exit("unknown theme %s (known: %s)" % (name, ", ".join(xd.THEMES)))
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    print("Graphite %s from %s" % (VERSION, os.path.relpath(base.STOCK, ROOT)))
    test = os.path.join(out, "host_test")
    os.makedirs(test, exist_ok=True)
    print("host test of the new code:", newcode.host_test(test))
    listing = os.path.join(out, "themes.json")
    known = {t["id"]: t for t in json.load(open(listing))} if os.path.exists(listing) else {}
    differ = []
    for name in names:
        start = time.time()
        known[name] = build(name, out)
        same = RELEASE.get(name) == known[name]["sha256"]
        differ += [] if same else [name]
        print("%-6s %s  sha256 %s  %s  (%.0f s)" % (name, os.path.relpath(os.path.join(out, known[name]["file"])),
                                                    known[name]["sha256"][:16],
                                                    "release image" if same else "differs from the release image",
                                                    time.time() - start))
    with open(listing, "w") as f:
        json.dump([known[k] for k in xd.THEMES if k in known], f, indent=1)
    if a.check and differ:
        sys.exit("not the %s release image: %s" % (VERSION, ", ".join(differ)))


if __name__ == "__main__":
    main()
