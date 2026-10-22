# The firmware image (LFI)

The firmware area holds one container, called LFI, of exactly 19,871,232 bytes (0x12f3600). The verified stock image
is `x91_dump/x91_lfi_verified.bin` (sha256 `e85794a8…2b60`). Every file in it keeps its offset and length; the image
has no free space, and the boot loader rejects any other size.

## Layout

| Offset | Size | Content |
|---|---|---|
| 0x000 | 4 | Magic `55 aa f0 0f` |
| 0x010 | 4 | Checksum of the directory: 32-bit sum of the words 0x200 to 0x2000 |
| 0x1fe | 2 | Checksum of the header: 16-bit sum of the halfwords 0x000 to 0x1fe |
| 0x200 | 32 each | Directory, one entry per file, up to 0x2000; an entry starting with 0 ends it |
| … | | The files, each at a sector-aligned offset |

Directory entry (32 bytes):

| Offset | Size | Field |
|---|---|---|
| 0x00 | 8 | Name, space padded |
| 0x08 | 3 | Extension |
| 0x10 | 4 | Offset in 512-byte sectors |
| 0x14 | 4 | Length in bytes |
| 0x1c | 4 | Checksum: 32-bit sum of the file's words |

All checksums are plain additive sums; there is no encryption or signature in the image itself (the vendor's `.fw`
packages are encrypted SQLite databases, which `atjboottool` decrypts; not needed here).

`firmware_analysis/tools/x91_modify.py` reads and writes the container:

```python
import x91_modify as xm
lfi = xm.Lfi(open("x91_lfi_verified.bin", "rb").read())
data = lfi.get("MUSIC.STY")            # bytes of one file
lfi.put("MUSIC.STY", new_bytes)        # same length; file, directory and header checksums are recomputed
assert not lfi.check()                 # list of failing checksums, empty when all pass
lfi.unpack("unpacked/")                # every file into a folder
open("out.bin", "wb").write(lfi.d)
```

## The 137 files

| Kind | Files | Notes |
|---|---|---|
| Programs `.AP` (22) | `MAINMENU`, `MUSIC`, `MENGINE` (playback engine), `PLAYLIST` (library builder), `BROWSER` (folder view), `EBOOK`, `SETTING`, `BT`, `BTENGINE`, `RADIO`, `FMENGINE`, `RECORD`, `VIDEO`, `PICTURE`, `PEDOMETE`, `STUDY`, `TOOLS`, `ALARM`, `MANAGER`, `CONFIG`, `UDISK`, `FWUPDATE` | see {doc}`programs` |
| Drivers `.DRV` (17) | `KERNEL`, `DRV_UI`, `DRV_LCD`, `KEY`, `AUD_DEV`, `NAND`, `CARD`, `CARDS`, `UHOST`, `DRV_FM`, `DRV_I2C`, FAT and exFAT drivers | never modified |
| Resources `.STY` (21) | `COMMON` (shared by all programs) and one per program, plus `LOGO` (start-up), `END` (shut-down), `UPGRADE`, `CONFIG` | see {doc}`resources` |
| Menus `.MCG` (14) | one per program with menus (`MUSIC`, `SETTING`, `BT`, `BT_BQB`, `BROWSER`, `EBOOK`, `RECORD`, `RADIO`, `TOOLS`, `PICTURE`, `VIDEO`, `PEDOMETE`, `STUDY`, `MAINMENU`) | see {doc}`resources` |
| Codecs and media libraries `.AL` (17) | decoders (`ADMP3`, `ADWMA`, `ADFLAC`, `ADAPE`, `ADAAC`, `ADOGG`, `ADWAV`), encoders (`AEMP3`, `AEWAV`, `APENC`, `APENC_AB`), audio processing (`APDAE`), the media middleware (`MMM_MP` music, `MMM_VP` video, `MMM_MR` recording, `MMM_ID` tags), `FWDEC` | `MMM_MP` hands the volume to the audio driver |
| Fonts `.FON` (2) | `UNICODE.FON` (16 rows), `UNICODEL.FON` (24 rows) | stage 2 redrew 512 glyphs of `UNICODE.FON` |
| Settings | `CONFIG.BIN` (compiled), `CONFIG.TXT`, `CONFIG.SPC`, `SETTING.INI`, `FMTOOL.CFG` | |
| Kernel | `KER_INIT.BIN`, `KER_TEXT.BIN`, `KER_DATA.BIN` | |
| Code pages `.TBL`, `.$$$` | `1250L.TBL` … `V950BIG.TBL`, `FTBL_*.$$$` | used to turn one-byte names into Unicode by language |
| Other | `SCREEN.BIN`, `M_ICON.BIN`, `EF.BIN`, `UK.BIN`, `FMTDATA.BIN`, `RECORD.EFX`, `ALARM1.MP3`, `LEGAL.TXT`, `M_TYPE.TXT`, `SN.TXT` | |

## Settings: CONFIG.BIN

`CONFIG.BIN` is the compiled form of `CONFIG.TXT`: a table of 151 entries in the order of `CONFIG.TXT`, each a
default with its range or list of values. It holds the main-menu contents and order (entry 1, a list of program ids),
the key map, and every default (for example `MUSIC_LRC_SUPPORT`, entry 76, set to 0 in stage 11). The firmware keeps
a working copy in a settings area; a firmware write resets it to the defaults, and the three built-in on-device
playlists (`USERPL1.PL` to `USERPL3.PL`) live in that area too.

Stages 3 and 5 changed the main-menu list (9 → 5 → 6 entries: `0, 1, 5, 11, 4, 10`), keeping the file's size and
tables.

## Libraries on the user disk

These are not in the image but written by `PLAYLIST.AP` on the user disk: `MUSIC.LIB` (songs by tag), `M3U.LIB`
(the `.m3u` playlists), `EBOOK.LIB` and others. They are rebuilt at power-up, after USB mode and at "Update list?".
The layout of `M3U.LIB` is in {doc}`music`.
