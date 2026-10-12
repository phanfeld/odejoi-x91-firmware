#!/usr/bin/env python3
"""Unpack vendor firmware archives and collect metadata from Actions FWU packages.

usage: analyze.py RARX ATJBOOTTOOL ARCHIVE_DIR WORK_DIR OUT_JSON

ATJBOOTTOOL is Rockbox's utils/atj2137/atjboottool (https://github.com/Rockbox/rockbox).
"""
import collections
import hashlib
import json
import ntpath
import os
import re
import sqlite3
import subprocess
import sys

RARX, ATJ, ARCH_DIR, WORK, OUT = sys.argv[1:6]
FW_RE = r"\.(fw|hex|upg|fwu|ufw|bfu|upt|bin|img)$"
DOC_RE = r"\.(pdf|txt|docx?|xlsx?|rtf|ini|cfg)$"
SKIP_TABLES = {"FileTable", "FileAttribute", "FuncSpec", "ExSymbol", "L130Spec"}
TEXT_FILES = ("config.txt", "fmtool.cfg", "m_type.txt", "setting.ini", "legal.txt")


def listing(arc):
    out = subprocess.run([sys.executable, "-I", RARX, "list", arc], capture_output=True, text=True)
    rows = []
    for line in out.stdout.splitlines():
        m = re.match(r"^(.) +(\d+) (\S+) (.*)$", line)
        if m:
            rows.append({"dir": m.group(1) == "d", "size": int(m.group(2)), "date": m.group(3), "name": m.group(4)})
    return rows, out.stderr.strip()


def decode(b):
    for enc in ("utf-8", "gbk", "latin-1"):
        try:
            return b.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def read_db(path):
    info = {}
    db = sqlite3.connect("file:" + path + "?mode=ro", uri=True)
    db.text_factory = lambda b: b.decode("utf-8", "replace")
    tabs = [r[0] for r in db.execute("select name from sqlite_master where type='table'")]
    vals = {}
    for t in tabs:
        if t in SKIP_TABLES:
            continue
        rows = db.execute('select * from "%s"' % t).fetchall()
        if rows:
            vals[t] = [list(r) for r in rows]
    info["tables"] = vals
    files = []
    texts = {}
    for kw, name, length, blob in db.execute("select Keyword, FileName, FileLength, File from FileTable"):
        blob = blob or b""
        files.append({"kw": kw, "name": name, "len": len(blob), "sha1": hashlib.sha1(blob).hexdigest()})
        if name.lower() in TEXT_FILES:
            texts[name.lower()] = decode(blob)
    info["files"] = files
    info["texts"] = texts
    roots = collections.Counter()
    attrs = {}
    maxt = ""
    try:
        for kw, name, fpath, ftime in db.execute("select Keyword, FileName, FilePath, FileTime from FileAttribute"):
            roots[ntpath.dirname(fpath or "")] += 1
            attrs[name] = [fpath, ftime]
            if ftime and ftime > maxt:
                maxt = ftime
    except sqlite3.Error as e:
        info["attr_error"] = str(e)
    info["path_roots"] = roots.most_common()
    info["attrs"] = attrs
    info["max_filetime"] = maxt
    try:
        info["funcspec"] = [r[0] for r in db.execute("select Signature from FuncSpec")]
    except sqlite3.Error:
        info["funcspec"] = []
    db.close()
    return info


def main():
    results = []
    archives = sorted(f for f in os.listdir(ARCH_DIR) if f.lower().endswith((".rar", ".zip")))
    for i, arc in enumerate(archives):
        apath = os.path.join(ARCH_DIR, arc)
        rec = {"archive": arc, "size": os.path.getsize(apath)}
        rows, err = listing(apath)
        rec["list_err"] = err
        rec["entries"] = rows
        wdir = os.path.join(WORK, "%03d" % i)
        os.makedirs(wdir, exist_ok=True)
        rec["workdir"] = wdir
        cands = [r for r in rows if not r["dir"] and (re.search(r"\.(fw|hex|upg|fwu)$", r["name"], re.I)
                 or (r["size"] > 1 << 20 and "." not in r["name"].replace("\\", "/").rsplit("/", 1)[-1]))]
        rec["fw_candidates"] = [c["name"] for c in cands]
        if cands or any(re.search(r"\.pdf$", r["name"], re.I) for r in rows):
            subprocess.run([sys.executable, "-I", RARX, "extract", apath, wdir, r"\.(fw|hex|upg|fwu|pdf|docx?)$|(^|/)[^./]*$"],
                           capture_output=True, text=True)
        rec["fw"] = []
        for j, c in enumerate(cands):
            src = os.path.join(wdir, c["name"].replace("\\", "/"))
            fwrec = {"name": c["name"], "size": c["size"]}
            if not os.path.isfile(src):
                fwrec["status"] = "not extracted"
                rec["fw"].append(fwrec)
                continue
            with open(src, "rb") as f:
                fwrec["head"] = f.read(32).hex()
            out = os.path.join(wdir, "fw%d.db" % j)
            status = "decrypt failed"
            for extra in ([], ["--atj2127"]):
                if os.path.exists(out):
                    os.remove(out)
                p = subprocess.run([ATJ, "-c", "--fwu"] + extra + ["-o", out, src], capture_output=True, text=True)
                fwrec["atj_tail"] = (p.stdout + p.stderr)[-400:]
                if os.path.isfile(out):
                    with open(out, "rb") as f:
                        magic = f.read(16)
                    if magic.startswith(b"SQLite format 3"):
                        status = "sqlite" + ("(atj2127 flag)" if extra else "")
                        break
                    status = "decrypted, not sqlite: " + magic.hex()
            fwrec["status"] = status
            fwrec["db"] = out if status.startswith("sqlite") else None
            if fwrec["db"]:
                try:
                    fwrec["info"] = read_db(out)
                except Exception as e:  # keep going; record the failure
                    fwrec["status"] = "sqlite read error: %s" % e
            rec["fw"].append(fwrec)
        results.append(rec)
        print("%3d %-58s fw=%d %s" % (i, arc[:58], len(cands), "; ".join(f["status"] for f in rec["fw"])), flush=True)
    with open(OUT, "w") as f:
        json.dump(results, f)


if __name__ == "__main__":
    main()
