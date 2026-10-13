#!/usr/bin/env python3
"""Write M3U playlists in the form the X91's firmware reads.

Form tested on the player by the odejoi-player-sync project (2026-10-13):
  - backslashes as path separators and CR LF line ends,
  - paths from the root of the player without a leading backslash ("Music\\Artist\\Album\\01 - Title.mp3"),
  - no header line; only mp3 files played from a playlist,
  - plain ASCII names. UTF-8, UTF-16 and GBK names failed. The firmware converts names with the
    code page of its language (1252 for English and German), which is what this tool writes for
    non-ASCII names; that case is untested on the player.

usage:
  x91_playlist.py PLAYER --from-folders [FOLDER ...]   one playlist per folder that holds music
  x91_playlist.py PLAYER --convert LIST.m3u8 [...]     rewrite existing playlists for the player
  x91_playlist.py PLAYER --name "Running" FILE [...]   a playlist from files already on the player

PLAYER is where the player is mounted, e.g. /media/you/XXXX. Playlists are written to its root.
"""
import argparse
import os
import sys

AUDIO = {".mp3", ".wma", ".wav", ".ape", ".flac", ".ogg", ".aac", ".m4a", ".aax", ".aa", ".mp2", ".mp1"}


def index_player(root):
    """All music files on the player, as paths relative to its root."""
    files = []
    for d, _, names in os.walk(root):
        for n in names:
            if os.path.splitext(n)[1].lower() in AUDIO:
                files.append(os.path.relpath(os.path.join(d, n), root))
    return sorted(files, key=str.lower)


def write_m3u(root, name, rel_paths, codepage):
    safe = "".join(c for c in name if c.isalnum() or c in " _-").strip() or "playlist"
    lines, skipped, non_ascii = [], [], 0
    for rel in rel_paths:
        line = rel.replace("/", "\\")
        non_ascii += not line.isascii()
        try:
            line.encode(codepage)
        except UnicodeEncodeError:
            skipped.append(rel)
            continue
        lines.append(line)
    if not lines:
        print("  %s: nothing to write" % safe)
        return
    out = os.path.join(root, safe + ".m3u")
    with open(out, "wb") as f:
        f.write(("\r\n".join(lines) + "\r\n").encode(codepage))
    if non_ascii:
        print("      note: %d names contain non-ASCII characters, written in %s (untested on the player)" % (non_ascii, codepage))
    print("  %s.m3u: %d tracks%s" % (safe, len(lines),
                                     ", %d skipped (name not writable in %s)" % (len(skipped), codepage) if skipped else ""))
    for s in skipped[:5]:
        print("      skipped:", s)


def resolve(entry, src_dir, root, files, by_tail):
    """Find the file on the player that a playlist line means."""
    entry = entry.strip().replace("\\", "/")
    if len(entry) > 1 and entry[1] == ":":
        entry = entry[2:]
    cand = os.path.normpath(os.path.join(src_dir, entry.lstrip("/")))
    if os.path.isfile(cand) and os.path.realpath(cand).startswith(os.path.realpath(root) + os.sep):
        return os.path.relpath(cand, root)
    parts = [p for p in entry.split("/") if p and p != ".."]
    for n in (3, 2, 1):  # match by the last folders and the file name, ignoring case
        hits = by_tail.get("/".join(parts[-n:]).lower(), [])
        if len(hits) == 1:
            return hits[0]
    return None


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("player")
    ap.add_argument("--from-folders", nargs="*", metavar="FOLDER")
    ap.add_argument("--convert", nargs="+", metavar="LIST")
    ap.add_argument("--name")
    ap.add_argument("files", nargs="*")
    ap.add_argument("--codepage", default="cp1252", help="code page of the player's language (default: Western European)")
    a = ap.parse_args()
    root = os.path.abspath(a.player)
    if not os.path.isdir(root):
        sys.exit("not a folder: " + root)
    files = index_player(root)
    print("%d music files on the player" % len(files))
    by_tail = {}
    for f in files:
        parts = f.replace("\\", "/").split("/")
        for n in (1, 2, 3):
            by_tail.setdefault("/".join(parts[-n:]).lower(), []).append(f)

    if a.from_folders is not None:
        wanted = [os.path.normpath(x) for x in a.from_folders]
        groups = {}
        for f in files:
            d = os.path.dirname(f)
            if d and (not wanted or any(d == w or d.startswith(w + os.sep) for w in wanted)):
                groups.setdefault(d, []).append(f)
        for d, lst in sorted(groups.items()):
            write_m3u(root, d.replace(os.sep, " - "), lst, a.codepage)
    if a.convert:
        for src in a.convert:
            try:
                text = open(src, "rb").read().decode("utf-8-sig")
            except UnicodeDecodeError:
                text = open(src, "rb").read().decode("cp1252")
            found, missing = [], 0
            for line in text.splitlines():
                if not line.strip() or line.startswith("#"):
                    continue
                r = resolve(line, os.path.dirname(os.path.abspath(src)), root, files, by_tail)
                if r:
                    found.append(r)
                else:
                    missing += 1
            write_m3u(root, os.path.splitext(os.path.basename(src))[0], found, a.codepage)
            if missing:
                print("      %d entries not found on the player" % missing)
    if a.name:
        rels = []
        for f in a.files:
            p = os.path.abspath(f)
            if not p.startswith(root + os.sep):
                sys.exit("not on the player: " + f)
            rels.append(os.path.relpath(p, root))
        write_m3u(root, a.name, rels, a.codepage)


if __name__ == "__main__":
    main()
