#!/usr/bin/env python3
"""usage: dumpdb.py JSON [JSON...] -- OUTROOT ARCHIVE_SUBSTR [...]  : write FileTable blobs of matching archives"""
import json, os, re, sqlite3, sys
sep = sys.argv.index("--")
jsons, outroot, pats = sys.argv[1:sep], sys.argv[sep + 1], sys.argv[sep + 2:]
recs = {}
for p in jsons:
    for r in json.load(open(p)):
        if any(f["status"].startswith("sqlite") for f in r["fw"]) or r["archive"] not in recs:
            recs[r["archive"]] = r
for arc, r in sorted(recs.items()):
    if not any(p in arc for p in pats):
        continue
    for f in r["fw"]:
        if not f.get("db"):
            continue
        d = os.path.join(outroot, re.sub(r"[^A-Za-z0-9_.-]+", "_", arc[:-4]))
        os.makedirs(d, exist_ok=True)
        db = sqlite3.connect("file:" + f["db"] + "?mode=ro", uri=True)
        db.text_factory = lambda b: b.decode("utf-8", "replace")
        n = 0
        for name, blob in db.execute("select FileName, File from FileTable"):
            safe = re.sub(r"[^A-Za-z0-9_.$-]+", "_", name)
            with open(os.path.join(d, safe), "wb") as fh:
                fh.write(blob or b"")
            n += 1
        with open(os.path.join(d, "_FuncSpec.txt"), "w") as fh:
            for sig, body in db.execute("select Signature, Body from FuncSpec"):
                fh.write("=== %s\n%s\n\n" % (sig, body))
        print(d, n, "files")
