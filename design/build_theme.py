#!/usr/bin/env python3
"""Build the current design as complete firmware images, one per accent colour.

usage: build_theme.py [THEME ...]      themes: amber, mint, ice, berry (all of them if none is named)
Writes ../x91_dump/themes/x91_lfi_THEME.bin and the list ../x91_dump/themes/themes.json, which x91_tool.py reads.
Switching theme means writing that image to the player.
"""
import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import x91_design as xd  # noqa: E402

STAGES = [1, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26]   # stage 2 (the typeface) is part of stage 3
THEMES = os.path.join(ROOT, "x91_dump", "themes")
LIST = os.path.join(THEMES, "themes.json")


def build(theme):
    out = os.path.join(THEMES, theme)
    env = dict(os.environ, X91_THEME=theme)
    for n in STAGES[:-1]:
        env["X91_STAGE%d" % n] = os.path.join(out, "stage%d" % n, "x91_lfi_stage%d.bin" % n)
    for n in STAGES:
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "build_stage%d.py" % n), os.path.join(out, "stage%d" % n)],
                           env=env, capture_output=True, text=True)
        if r.returncode or "checksum failures: none" not in r.stdout:
            sys.exit("build_stage%d.py failed for %s:\n%s%s" % (n, theme, r.stdout[-600:], r.stderr[-600:]))
    last = STAGES[-1]
    final = os.path.join(THEMES, "x91_lfi_%s.bin" % theme)
    shutil.copyfile(os.path.join(out, "stage%d" % last, "x91_lfi_stage%d.bin" % last), final)
    data = open(final, "rb").read()
    return {"id": theme, "name": theme.capitalize(), "accent": xd.THEMES[theme]["accent"], "file": os.path.basename(final),
            "stage": last, "sha256": hashlib.sha256(data).hexdigest(), "built": datetime.date.today().isoformat()}


def main():
    names = sys.argv[1:] or list(xd.THEMES)
    for name in names:
        if name not in xd.THEMES:
            sys.exit("unknown theme %s (known: %s)" % (name, ", ".join(xd.THEMES)))
    known = {t["id"]: t for t in json.load(open(LIST))} if os.path.exists(LIST) else {}
    for name in names:
        known[name] = build(name)
        print("%s: %s" % (name, os.path.join(THEMES, known[name]["file"])))
    os.makedirs(THEMES, exist_ok=True)
    with open(LIST, "w") as f:
        json.dump([known[k] for k in xd.THEMES if k in known], f, indent=1)


if __name__ == "__main__":
    main()
