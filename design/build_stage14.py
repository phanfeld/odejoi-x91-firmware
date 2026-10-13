#!/usr/bin/env python3
"""Stage 14 of the Graphite design, built on the stage 13 image.

  1. Scrolling text keeps the new background. A picture that serves as the background of a scrolling text is
     stored twice: as usual, and directly behind that a second time turned sideways (column by column), which
     is what the firmware reads while the text moves. Earlier stages replaced only the first copy, so the
     stock picture came back during scrolling (red behind the title, grey behind a long selected list row).
     Every such second copy is brought in line with its picture.
  2. The playing screen shows the title from the file's tag. The tag reader in MUSIC.AP overwrote the title
     with the file name every time; now it does so only when the tag has no title (patches/music_title.S).
  3. Status bar on the playing screen:
     - the bar is drawn at once when a screen switches it on, no longer half a second later
       (patches/music_headbar.S, the shared status-bar code of MUSIC.AP);
     - the "box" that covered the top left corner is the storage-card mark, drawn through black = transparent
       over the status bar's background picture. The playing screen now names its own background as that
       picture (two constants in MUSIC.AP), and that background carries a music note in the corner; so the
       mark's empty state redraws the note, and an inserted card shows the card mark in its place.

usage: build_stage14.py [OUT_DIR]      (default: ../x91_dump/stage14)
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
import x91_design as xd  # noqa: E402
import x91_modify as xm  # noqa: E402
import build_stage1 as s1  # noqa: E402
import build_stage4 as s4  # noqa: E402
import build_stage5 as s5  # noqa: E402
import build_stage11 as s11  # noqa: E402

T = s1.T
NOTE_AT, NOTE_SIZE = (2, 3), (15, 11)            # where the status bar draws the card mark (picture box 2 of COMMON.STY)
BACKGROUND = 45                                  # the playing screen's background, picture of MUSIC.STY
CARD_MARKS = (203, 205)                          # card present, card in use (COMMON.STY)
ALMOST_BLACK = 0x0020                            # drawn as black, but not treated as transparent


# ------------------------------------------------------------------ the sideways copies

def pictures(sty):
    po, count = struct.unpack_from("<IH", sty, 0x10)
    return [struct.unpack_from("<IIHHH", sty, po + k * 16) for k in range(count)]


def transposed(data, w, h):
    px = struct.unpack("<%dH" % (w * h), data)
    return struct.pack("<%dH" % (w * h), *(px[y * w + x] for x in range(w) for y in range(h)))


def with_copy(stock):
    """Pictures of a stock resource file that are followed by their sideways copy."""
    recs = pictures(stock)
    order = sorted(range(len(recs)), key=lambda k: recs[k][0])
    found = []
    for pos, k in enumerate(order):
        off, ln, _, w, h = recs[k]
        if ln != w * h * 2 or ln < 8:
            continue
        end = off + ln
        last = pos == len(order) - 1
        room = len(stock) - end if last else recs[order[pos + 1]][0] - end
        head = stock[off:end]
        if (room == ln or last and room >= ln and any(head)) and stock[end:end + ln] == transposed(head, w, h):
            found.append(k)
    return found


def refresh_copies(lfi, done):
    for name in sorted(lfi.entries):
        if not name.endswith(".STY"):
            continue
        stock = open(os.path.join(ROOT, "x91_dump", "unpacked", name), "rb").read()
        sty = bytearray(lfi.get(name))
        if len(sty) != len(stock):
            sys.exit("%s changed its size" % name)
        recs, changed = pictures(sty), []
        stock_recs = pictures(stock)
        for k in with_copy(stock):
            off, ln, _, w, h = stock_recs[k]
            if recs[k][0] != off or recs[k][1] > ln:
                sys.exit("%s picture %d moved" % (name, k))
            if recs[k][1] != ln:                                      # declared smaller since: not a text background
                continue
            copy = transposed(bytes(sty[off:off + ln]), w, h)
            if sty[off + ln:off + 2 * ln] != copy:
                sty[off + ln:off + 2 * ln] = copy
                changed.append(k)
        if changed:
            lfi.put(name, bytes(sty))
            done.append("%s %s" % (name, ", ".join(map(str, changed))))


# ------------------------------------------------------------------ pictures

def note_picture(work):
    w, h = NOTE_SIZE
    return s1.render_565(s1.svg(w, h, [xd.icon("music", -1.2, -2.85, 16.5, T["text"], 2.3)]), w, h, work, "status-note")


def edit_pictures(lfi, work):
    sty = bytearray(lfi.get("MUSIC.STY"))
    data, w, h = s4.picture_bytes(sty, BACKGROUND)
    if (w, h) != (128, 160):
        sys.exit("MUSIC.STY: the playing background is not the expected picture")
    back = bytearray(data)
    note, (nw, nh), (nx, ny) = note_picture(work), NOTE_SIZE, NOTE_AT
    for row in range(nh):
        o = ((ny + row) * w + nx) * 2
        back[o:o + nw * 2] = note[row * nw * 2:(row + 1) * nw * 2]
    s1.set_picture(sty, BACKGROUND, bytes(back), w, h)
    lfi.put("MUSIC.STY", bytes(sty))

    com = bytearray(lfi.get("COMMON.STY"))
    box = struct.unpack_from("<16H", com, s11.tables_of(com)[1][0] + 2 * 32)
    if box[1:3] != NOTE_AT or box[4:7] != (0x8000 | 204, 0x8000 | 203, 0x8000 | 205):
        sys.exit("COMMON.STY: the card mark is not where expected")
    for index in CARD_MARKS:
        data, w, h = s4.picture_bytes(com, index)
        if (w, h) != NOTE_SIZE:
            sys.exit("COMMON.STY: card mark %d has an unexpected size" % index)
        px = [v or ALMOST_BLACK for v in struct.unpack("<%dH" % (w * h), data)]
        s1.set_picture(com, index, struct.pack("<%dH" % len(px), *px), w, h)
    lfi.put("COMMON.STY", bytes(com))


# ------------------------------------------------------------------ program patches (MUSIC.AP)

def assemble(name, work):
    src = os.path.join(HERE, "patches", name + ".S")
    obj, raw = os.path.join(work, name + ".o"), os.path.join(work, name + ".bin")
    for cmd in (["arm-none-eabi-as", "-o", obj, src], ["arm-none-eabi-objcopy", "-O", "binary", obj, raw]):
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode:
            sys.exit("could not assemble %s: %s" % (name, r.stderr[-300:]))
    data = open(raw, "rb").read()
    os.remove(raw)
    os.remove(obj)
    return data


def disassemble(data, base, path):
    tmp = path + ".bin"
    open(tmp, "wb").write(data)
    r = subprocess.run(["arm-none-eabi-objdump", "-D", "-b", "binary", "-marm", "-Mforce-thumb",
                        "--adjust-vma=%#x" % base, tmp], capture_output=True, text=True)
    os.remove(tmp)
    open(path, "w").write(r.stdout)
    return path


def replace_stretch(ap, segs, work, what, bank, bank_len, lo, hi, built, stock_hash, checker):
    """Put new code over bank offsets lo..hi after checking the stock code and the new code's behaviour."""
    base = ap_dis.find(segs, bank)
    old = bytes(ap[base:base + bank_len])
    if base is None or hashlib.sha256(old[lo:hi]).hexdigest()[:16] != stock_hash:
        sys.exit("MUSIC.AP: the %s routine is not the expected one" % what)
    if len(built) != hi - lo:
        sys.exit("the %s patch has the wrong length" % what)
    new = old[:lo] + built + old[hi:]
    r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "patches", checker),
                        disassemble(old, bank, os.path.join(work, what + "_stock.dis")),
                        disassemble(new, bank, os.path.join(work, what + "_new.dis"))], capture_output=True, text=True)
    if r.returncode:
        sys.exit("the %s patch failed its check:\n%s%s" % (what, r.stdout[-600:], r.stderr[-300:]))
    ap[base + lo:base + hi] = built
    return r.stdout.strip()


TITLE = dict(bank=0x1c102000, bank_len=0x3e8, lo=0x1d4, hi=0x1f2, stock_hash="157e0c9342e18066")
HEADBAR = dict(bank=0x18c21a00, bank_len=0x520, lo=0x474, hi=0x4e8, stock_hash="3d68276703da3c68")
HEADBAR_SOURCE_BASE = 0x18a21a00                 # the address patches/music_headbar.S is laid out from
PAINTER_SITES = (0x180810ba, 0x180810c6)         # "background picture = the default one" in the playing screen's painter


def patch_music(lfi, work):
    ap = bytearray(lfi.get("MUSIC.AP"))
    segs, _ = ap_dis.segments(ap)
    word = lambda addr: struct.unpack_from("<I", ap, ap_dis.find(segs, addr))[0]
    notes = []

    built = assemble("music_title", work)[TITLE["lo"]:TITLE["hi"]]
    notes.append("title: " + replace_stretch(ap, segs, work, "title", built=built, checker="check_title_patch.py", **TITLE))

    pool = [word(HEADBAR["bank"] + HEADBAR["hi"] + 4 * k) for k in range(6)]
    if pool != [0x200163, 0x200162, 0x200668, 0x20015f, 0x200164, 0x200159]:
        sys.exit("MUSIC.AP: the status bar's variables are not where expected")
    shift = HEADBAR["bank"] - HEADBAR_SOURCE_BASE
    built = assemble("music_headbar", work)[shift + HEADBAR["lo"]:shift + HEADBAR["hi"]]
    notes.append("status bar: " + replace_stretch(ap, segs, work, "headbar", built=built, checker="check_headbar_patch.py", **HEADBAR))

    for site in PAINTER_SITES:                                        # movw r2, #0xffff  ->  movw r2, #BACKGROUND
        s5.patch_bytes(ap, ap_dis.find(segs, site), bytes.fromhex("4ff6ff72"),
                       struct.pack("<HH", 0xf240, 0x0200 | BACKGROUND), "MUSIC.AP playing-screen painter")
    lfi.put("MUSIC.AP", bytes(ap))
    return notes


def main():
    out = os.path.abspath(sys.argv[1]) if len(sys.argv) > 1 else os.path.join(ROOT, "x91_dump", "stage14")
    work = os.path.join(out, "pictures")
    os.makedirs(work, exist_ok=True)
    stock = open(os.path.join(ROOT, "x91_dump", "x91_lfi_verified.bin"), "rb").read()
    base = os.environ.get("X91_STAGE13") or os.path.join(ROOT, "x91_dump", "stage13", "x91_lfi_stage13.bin")
    lfi = xm.Lfi(open(base, "rb").read())
    if lfi.check():
        sys.exit("the stage 13 image does not pass its checksums")
    before = {n: lfi.get(n) for n in lfi.entries}
    edit_pictures(lfi, work)
    print("pictures: music note in the playing background, card marks made opaque")
    copies = []
    refresh_copies(lfi, copies)
    print("sideways copies brought in line:", "; ".join(copies) or "none needed")
    for line in patch_music(lfi, work):
        print("music program,", line)
    bad = lfi.check()
    img = os.path.join(out, "x91_lfi_stage14.bin")
    with open(img, "wb") as f:
        f.write(lfi.d)
    lfi.unpack(os.path.join(out, "unpacked"))
    print("image:", img)
    print("  checksum failures: %s; size unchanged: %s" % (bad or "none", len(stock) == len(lfi.d)))
    print("  files changed in this stage:", ", ".join(sorted(n for n in lfi.entries if lfi.get(n) != before[n])))
    print("  sha256:", hashlib.sha256(lfi.d).hexdigest())


if __name__ == "__main__":
    main()
