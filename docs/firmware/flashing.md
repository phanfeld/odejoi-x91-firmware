# Reading and writing the firmware

## Where the procedure comes from

The vendor's Windows flashing tool is a script interpreter; its script (`AdfuUpgrade`) is stored inside every
firmware package. The a02-os project re-implemented it on Linux with `actions_dump` for an AGPTEK A02 and proved it
there. The X91 matches the A02 in what the procedure depends on: NAND chip (`89 84 64 3c a5`), flash driver
(`fwscf651.bin`, the same file) and firmware line (`1.101.37`). Every device-specific value (pin table, boot record
size, firmware size, the chip's NAND record) is taken from this unit's own boot record.

The sequence, each step run from RAM in upgrade mode:

1. Load the `adfus` loader at 0x118000.
2. Run the vendor hardware scan (`nandhwsc.bin`); it returns the NAND ID and where the driver expects the chip's
   record.
3. Put the chip's 128-byte record there, load the flash driver with a few header fields filled in, and call it; it
   must answer `NAFWSC`.
4. Read through the driver (storage type 0x80), or write the firmware area (0xc0) and finalise (0xff).
5. Read everything back and compare, before the player is restarted.

Only the firmware area is written; the boot records are never touched.

## x91_flash.py

`x91_dump/x91_flash.py` runs the procedure and stops at the first unexpected answer.

| Command | Device | Driver | What it does |
|---|---|---|---|
| `prepare` | no | | builds the driver files and runs nine cross-checks against the boot record and the dump |
| `rehearse` | yes | read-only | reads the whole firmware through the driver and compares it with the verified dump |
| `dump --out F` | yes | read-only | reads the firmware area into F and checks its checksums |
| `write --image F --yes-write-flash [--backup B]` | yes | stock | saves the current firmware to B, writes F, finalises, reads back and compares; refuses without a passed rehearsal |

The read-only driver is the stock driver with a published two-instruction patch that makes its erase and program
routines return at once (sha256 `9008981c…`). The player must be in upgrade mode, entered with `adfu_reboot` from a
fresh power-on, with no other program run in that session.

## x91_tool.py

The terminal interface (Python curses, no extra packages) drives `x91_flash.py`. It lists the images from
`x91_dump/themes/themes.json`, the original firmware and "Previous firmware" (the newest
`x91_dump/backups/before_*.bin`), checks the chosen image, asks for a typed YES, switches the player into upgrade
mode, saves a backup, writes, reads back and compares, and explains the outcome. It restarts itself through sudo and
hands the files it wrote back to the calling user. `--demo` runs the same screens against a simulated player.

## The first dump

`x91_flash.py` needs a verified stock image to start from. On a new unit it is made through the boot area, without
the vendor driver:

1. Build `actions_dump_x91`, upstream `actions_dump` with our page-size scan patch, and the `nandread` payload:
   `patch -o actions_flash/actions_dump_x91.c actions_flash/actions_dump.c patches/actions_flash-x91_scan.patch`,
   then `make -C actions_flash APPNAME=actions_dump_x91` and
   `make -C actions_flash/payload_arm TOOLCHAIN=arm-none-eabi CC="arm-none-eabi-gcc -march=armv7-m -mthumb" NAME=nandread`.
2. `read_brec` reads the boot records (`mbrec.bin`, `brec0.bin`); they give the firmware size, 38,811 sectors.
3. `find_lfi` with the page-size override `lfi_geom 32 0x4000` (the firmware area uses 16 KiB pages, the boot area
   8 KiB) dumps both copies of the firmware. Do it twice.
4. `firmware_analysis/tools/lfi_verify.py READ1 READ2 38811 0x4000 x91_lfi_verified.bin unpacked/` checks header,
   directory and every file in all four copies and assembles a verified image.

## History of the write path

| Date | Step | Result |
|---|---|---|
| 2026-10-13 | Dump through the boot area (`find_lfi` with a 16 KiB page override), twice | six firmware blocks (main and mirror copy); two unstable pages of the main copy, inside `STUDY.AP`, taken from the mirror; all 137 file checksums pass |
| 2026-10-13 | Rehearsal with the read-only driver | 0 of 38,811 sectors differ; the driver handles the four chip selects |
| 2026-10-13 | First write: the unchanged image | written, finalised, read back identical |
| 2026-10-13 | Custom start-up picture | read-back equals the image and differs from stock in 83 sectors: the write lands |
| since then | Every stage | written and read back identical |

## Risks that remain

- A firmware that passes its checksums and starts, but then hangs, has no known way back ({doc}`hardware`).
- An interrupted write relies on the boot loader's restore logic, read from code, not tested by breaking a unit; use
  a charged battery and a direct USB port.
- The finalise step writes a marker for the settings store; the player comes back with default settings, and the
  built-in playlists are emptied. Music and files are not touched.
