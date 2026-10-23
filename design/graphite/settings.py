"""Settings and sound.

  - Settings gets "Sound settings" with Equalizer and Volume limit. The settings program has these routines and its
    menu file lists every item it defines; the X91 did not use them. The new lists go to the end of SETTING.MCG, over
    the tail of the editor block (the firmware reads only the list table and the lists).
  - Lyrics are switched off (MUSIC_LRC_SUPPORT in CONFIG.BIN).
  - Volume: the music engine's table from the 32 volume steps to the decoder's volume (MENGINE.AP 0x1a11189e; 0 to
    191, most likely 0.375 dB each, 191 = full) gets even steps of 2 dB from -60 dB at step 1. Stock it went from
    -54 dB in steps of 3 dB at the bottom and about 1 dB at the top, so the first steps were loud and the upper half
    changed little.
"""
import struct

from . import base
from .base import ap_dis, fail

VOLUME_AT = 0x1a11189e
VOLUME_STOCK = bytes([0, 47, 55, 63, 71, 79, 87, 95, 111, 119, 127, 132, 135, 138, 143, 146, 148, 151, 154, 156,
                      159, 160, 162, 164, 166, 168, 170, 172, 175, 178, 183, 191])
VOLUME = bytes([0] + [round(191 - (31 - k) * 16 / 3) for k in range(1, 32)])   # 2 dB = 5 1/3 steps of 0.375 dB


def lyrics_off(b):
    cfg = b.get("CONFIG.BIN")
    off, ln = struct.unpack_from("<II", cfg, 16 + 76 * 8)          # entry 76: MUSIC_LRC_SUPPORT, a choice of 0 or 1
    base.patch_bytes(cfg, off, struct.pack("<4H", 1, 2, 0, 1), struct.pack("<4H", 0, 2, 0, 1), "CONFIG.BIN lyrics setting")
    b.put("CONFIG.BIN", cfg)
    txt = b.get("CONFIG.TXT")
    a, c = b"MUSIC_LRC_SUPPORT = 1[0,1];", b"MUSIC_LRC_SUPPORT = 0[0,1];"
    if a in txt:
        b.put("CONFIG.TXT", bytes(txt).replace(a, c))


def pool_items(mcg):
    """Every menu item the settings program defines, from the editor block of its menu file: number -> fields."""
    start = mcg.find(b"ACTMCGGM01")
    items = {}
    for k in range((len(mcg) - start - 14) // 42):
        idx, _, s_1, s_2, f1, _, f2, w1, icon = struct.unpack_from("<IIHHIIIHH", mcg, start + 14 + k * 42)
        if 0x18000000 <= f2 < 0x19000000:
            items.setdefault(idx, dict(text=s_1, text2=s_2, run=f1, common=f2, radio=w1 & 0xff == 1))
    return items


def menu_item(p, child=None, icon=0):
    first = child if child is not None else 0xffff if p["radio"] else 0x7fff
    return struct.pack("<HHHHIII", first, p["text"], p["text2"], icon, p["run"], 0, p["common"])


def sound_settings(b):
    mcg = b.get("SETTING.MCG")
    pool = pool_items(bytes(mcg))
    names = {17: 153, 21: 32, 22: 0x8026, 23: 30, 24: 26, 25: 27, 26: 28, 27: 24, 28: 31, 29: 25, 34: 180}   # item -> text id
    if any(pool.get(i, {}).get("text") != t for i, t in names.items()):
        fail("SETTING.MCG: the sound items are not the expected ones")
    hsz, n = base.menu_heads(mcg)
    table = [list(struct.unpack_from("<HHII", mcg, hsz + i * 12)) for i in range(n)]
    if n != 18 or table[0][:3] != [0x89, 10, hsz + n * 12]:
        fail("SETTING.MCG: unexpected list table")
    root = [bytes(mcg[table[0][2] + k * 20:table[0][2] + (k + 1) * 20]) for k in range(10)]
    SOUND, EQ, AT = 18, 19, 2                                         # new list numbers; place in the root menu
    root.insert(AT, menu_item(pool[17], child=SOUND, icon=12))
    sound = [menu_item(pool[21], child=EQ, icon=27), menu_item(pool[34], icon=14)]
    eq = [menu_item(pool[i], icon=28 + k) for k, i in enumerate(range(22, 30))]
    for row in table:                                                 # lists that hang off a root item behind the new one
        if row[3] != 0xffffffff and row[3] & 0xffff == 0 and row[3] >> 16 >= AT:
            row[3] += 0x10000
    # the root list's old room takes the two new table entries
    pos = len(mcg) - 512
    for row_id, items, link in ((None, root, None), (153, sound, AT << 16), (32, eq, SOUND)):
        data = b"".join(items)
        mcg[pos:pos + len(data)] = data
        if row_id is None:
            table[0][1:3] = [len(items), pos]
        else:
            table.append([row_id, len(items), pos, link])
        pos += len(data)
    old_root = hsz + n * 12
    mcg[old_root:old_root + 200] = bytes(200)
    for i, row in enumerate(table):
        struct.pack_into("<HHII", mcg, hsz + i * 12, *row)
    struct.pack_into("<H", mcg, 14, len(table))
    b.put("SETTING.MCG", mcg)
    return len(table)


def volume(b):
    ap = b.get("MENGINE.AP")
    segs, _ = ap_dis.segments(ap)
    o = ap_dis.find(segs, VOLUME_AT)
    if o is None or bytes(ap[o:o + 32]) != VOLUME_STOCK:
        fail("MENGINE.AP: the volume table is not the stock one")
    if len(VOLUME) != 32 or any(y <= x for x, y in zip(VOLUME, VOLUME[1:])) or VOLUME[31] != 191:
        fail("the new volume table is not rising")
    ap[o:o + 32] = VOLUME
    b.put("MENGINE.AP", ap)


def build(b):
    lyrics_off(b)
    lists = sound_settings(b)
    volume(b)
    b.note("settings: Sound settings with Equalizer and Volume limit (%d lists); lyrics off; volume in steps of 2 dB", lists)
