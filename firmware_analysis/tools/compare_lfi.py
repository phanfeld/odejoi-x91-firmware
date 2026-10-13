#!/usr/bin/env python3
"""Compare unpacked LFI files with the files inside decrypted vendor packages.

usage: compare_lfi.py UNPACK_DIR REF_JSON
"""
import collections, json, os, sqlite3, sys

unp, ref = sys.argv[1], sys.argv[2]
mine = {n.lower(): open(os.path.join(unp, n), "rb").read() for n in sorted(os.listdir(unp))}
pk = {}
for r in json.load(open(ref)):
    for f in r["fw"]:
        if not f.get("db"):
            continue
        db = sqlite3.connect("file:" + f["db"] + "?mode=ro", uri=True)
        db.text_factory = lambda b: b.decode("utf-8", "replace")
        d = {}
        for kw, name, blob in db.execute("select Keyword, FileName, File from FileTable"):
            if kw == "FWIM":
                d[name.lower()] = blob or b""
        pk[r["archive"].replace("AGPTEK_", "").replace(".rar", "")] = d

def same(a, b):
    b2 = b + b"\0" * (-len(b) % 512)
    return a == b2

names = list(mine)
print("X91 files: %d" % len(names))
tot = collections.Counter()
match = {n: [p for p, d in pk.items() if n in d and same(mine[n], d[n])] for n in names}
for p, d in pk.items():
    eq = sum(1 for n in names if p in match[n])
    missing = [n for n in names if n not in d]
    extra = [n for n in d if n not in mine]
    print("%-28s identical files: %3d of %d; X91 files absent there: %d; files only there: %d"
          % (p, eq, len(names), len(missing), len(extra)))
best = "A02XT_A02PLT(20250709)"
print("\n--- per file vs", best)
d = pk[best]
groups = collections.defaultdict(list)
for n in names:
    if n not in d:
        groups["not in " + best].append(n)
    elif best in match[n]:
        groups["identical"].append(n)
    else:
        other = [p for p in match[n]]
        groups["different" + (" (but identical in: " + ", ".join(other) + ")" if other else "")].append(
            "%s[%d vs %d]" % (n, len(mine[n]), len(d[n])))
for k, v in groups.items():
    print("%s: %d\n   %s" % (k, len(v), " ".join(v)))
print("only in %s: %s" % (best, " ".join(n for n in d if n not in mine)))
