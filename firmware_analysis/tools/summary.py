#!/usr/bin/env python3
"""Print a comparison table from analyze.py JSON outputs.

usage: summary.py OUT_TSV JSON [JSON ...]   (later files override earlier ones per archive)
"""
import json
import re
import sys

out_tsv = sys.argv[1]
recs = {}
for p in sys.argv[2:]:
    for r in json.load(open(p)):
        if r["archive"] in recs and not any(f["status"].startswith("sqlite") for f in r["fw"]):
            continue
        recs[r["archive"]] = r


def cfg(text, key):
    m = re.search(r"^\s*" + re.escape(key) + r"\s*(?:\{\d+\})?\s*=\s*([^;]*);", text, re.M)
    return m.group(1).strip() if m else ""


def one(t, k):
    v = t.get(k)
    return v[0] if v else None


rows = []
for arc in sorted(recs):
    r = recs[arc]
    for f in r["fw"]:
        if not f["status"].startswith("sqlite"):
            continue
        i = f["info"]
        t = i["tables"]
        names = {x["name"].lower() for x in i["files"]}
        c = i["texts"].get("config.txt", "")
        adf = one(t, "ADFUS")
        addr = int(adf[1]) & 0xFFFFFFFF if adf else 0
        case = ""
        for root, n in i["path_roots"]:
            if "fwpkg" in root.lower() and not root.lower().endswith(("\\sty", "\\ap", "\\font", "\\mcg", "\\drv")):
                case = root
                break
        brec = [x[0] for x in t.get("BREC", [])]
        rows.append({
            "archive": arc,
            "fwfile": f["name"].rsplit("/", 1)[-1],
            "fw_type": (one(t, "FW_TYPE") or [""])[0],
            "adfus": "0x%08X" % addr,
            "ver": (one(t, "VER") or [""])[0],
            "built": i["max_filetime"],
            "case": case,
            "label": cfg(c, "INF_UDISK_LABEL"),
            "keys": cfg(c, "CFG_KEY_ARRAY"),
            "menu": cfg(c, "MAINMENU_AP_ID_ARRAY"),
            "card": cfg(c, "SETTING_AP_ID_SUPPORT_CARD"),
            "bt": "bt" if "bt.ap" in names or "btengine.ap" in names else "-",
            "fwupd": "fwupdate" if "fwupdate.ap" in names else "-",
            "nbrec": len(brec),
            "cardbrec": "cardbrec" if any("card" in b.lower() for b in brec) else "-",
            "norbrec": ",".join(b for b in brec if "nor" in b.lower() or "spi" in b.lower()),
            "mbrec": ",".join(x[0] for x in t.get("MBREC", [])),
            "lcd": "%sx%s" % ((one(t, "INF_LCDWIDTH") or ["?"])[0], (one(t, "INF_LCDHEIGHT") or ["?"])[0]),
            "userid": (one(t, "INF_USERDEFINED_ID_48") or [""])[0],
            "sector": (one(t, "INF_SECTOR_SIZE") or [""])[0],
            "nfiles": len(i["files"]),
        })

cols = ["archive", "fwfile", "fw_type", "adfus", "ver", "built", "label", "bt", "fwupd", "nbrec", "cardbrec",
        "norbrec", "mbrec", "lcd", "sector", "userid", "nfiles", "keys", "menu", "card", "case"]
with open(out_tsv, "w") as fh:
    fh.write("\t".join(cols) + "\n")
    for row in rows:
        fh.write("\t".join(str(row[c]) for c in cols) + "\n")

for row in rows:
    print("%-40s %-7s %s v%-5s %s  %-10s %-2s %-8s brec=%-2d %-8s %s" % (
        row["archive"][:40], row["fw_type"], row["adfus"], row["ver"], row["built"][:10], row["label"][:10].strip('"'),
        row["bt"], row["fwupd"], row["nbrec"], row["cardbrec"], row["mbrec"]))
print(len(rows), "Actions FWU packages")
