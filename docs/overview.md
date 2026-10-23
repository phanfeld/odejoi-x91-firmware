# Overview

## The player

| | |
|---|---|
| Device | ODEJOI X91, 64 GB (Amazon B0FJC6PH93; part numbers X91 and ODX66). Built by RUIZU. |
| Chip | Actions ATJ2157 (ARM Cortex-M4 class), confirmed by the upgrade-mode signature `30 51` |
| Memory | Under 300 KiB in all: a main region 0x100000 to 0x138000 (224 KiB) and two small ones at 0x200000 and 0x300000 |
| Screen | 128 x 160, RGB565 |
| Storage | Intel NAND, ID `89 84 64 3c a5`, four chip selects; 62.4 GiB user disk (FAT, 1024-byte logical sectors) and a card slot |
| Bluetooth | Actions ATS2851 module (inferred from the shared build tree) |
| Keys | power, return, up, menu, next, play, down, prev, volume up and down |
| Software | Actions "US215A" SDK on uC/OS-II, firmware line `1.101.37`, build date 2025-07-11 |
| USB | `10d6:1101` as a USB drive, `10d6:10d6` in upgrade mode |

Programs are bank-switched: each keeps only 0.6 to 2 KiB of code in memory and loads the rest from flash on demand.
That rules out Rockbox and any system that needs its whole core in RAM.

## What was done

1. **Dump.** No firmware for this player is published. It was read over USB with `actions_flash`, twice, and
   verified file by file.
2. **Write path.** The vendor's flashing sequence, replayed on Linux, was rehearsed read-only, then used to write the
   unchanged image, then a modified one. Every write is read back and compared. See {doc}`firmware/flashing`.
3. **Graphite.** A new interface built on top of the stock firmware in 26 stages: pictures, typeface, layouts,
   menus, settings, program patches and new program code in C (playlist editing, a search with a T9 keypad). See
   {doc}`design/index`.
4. **Tooling.** `x91_tool.py` dumps the firmware and flashes a theme; `design/build_theme.py` rebuilds every stage
   for every theme from the stock dump, deterministically.

Every stage up to 26 (search and "Add songs") has been flashed and tested on the device; the last stage 24 rebuild
only as part of the stage 25 and 26 images. Stage 27 ("New playlist" and "Rename" with names typed on the keypad) is
built but not yet flashed. See {doc}`project/history`.

## The firmware in one page

- **Image.** One "LFI" container of 137 files: programs (`.AP`), drivers (`.DRV`), resources (`.STY`), menus
  (`.MCG`), settings (`CONFIG.BIN`), fonts (`.FON`), codecs (`.AL`), code-page tables (`.TBL`). Three levels of
  additive checksums. Size and file positions never change. {doc}`firmware/image-format`
- **Programs.** A resident part plus code banks, each bank with its own address; banks of one group share a RAM
  window and replace each other there. The shared interface code (status bar, lists, menus, screensaver, key
  filter) is linked into every program separately. {doc}`firmware/programs`, {doc}`firmware/shared-code`
- **Resources.** Pictures (RGB565), strings in 28 languages, and layout tables (scenes, picture boxes, text boxes,
  number boxes, list boxes, sliders). An id with bit 15 set refers to `COMMON.STY`. {doc}`firmware/resources`
- **Display driver.** `DRV_UI.DRV`, reached with `svc 6`: list boxes, text, numbers, pictures with transparency,
  screen rotation. {doc}`firmware/display-driver`
- **Music.** `MUSIC.AP` drives the screens; `MENGINE.AP` plays, controlled by messages; `PLAYLIST.AP` builds the
  libraries (`MUSIC.LIB`, `M3U.LIB`). {doc}`firmware/music`

## Constraints

- The image is exactly 19,871,232 bytes and every file keeps its length and position; the boot loader rejects
  anything else.
- No hardware key for upgrade mode is known. Recovery from a bad firmware goes through USB-drive mode, so
  `CONFIG.AP`, `UDISK.AP`, `FWUPDATE.AP`, the drivers and the boot record are never modified
  ({doc}`firmware/hardware`).
- There is no free space in the code. Patches rewrite existing code more compactly ({doc}`code/patches`); new code
  goes into the zero-filled tails of code banks ({doc}`code/new-code`).
