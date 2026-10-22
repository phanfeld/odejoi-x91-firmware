# Hardware, boot and upgrade mode

## Identification

| Item | Value | How it is known |
|---|---|---|
| USB, normal mode | `10d6:1101`, strings `ACTIONS` / `HS USB FlashDisk`, SCSI `ACTIONS / USB DISK FOB 2.0` | `lsusb`; these are SDK defaults |
| USB, upgrade mode | `10d6:10d6`, vendor-specific interface | after `adfu_reboot` |
| Chip | ATJ2157 | `adfu_info` returns `00 'CADFUD' 30 51 41` |
| NAND | `89 84 64 3c a5` (Intel), four chip selects | read by the vendor hardware scan `nandhwsc.bin` |
| Flash driver | `fwscf651.bin` (vendor rule: Intel IDs map to `f651`) | vendor flashing script; same file as the AGPTEK A02's |
| Firmware size | 0x12f3600 bytes = 38,811 sectors of 512 | boot record |
| Firmware area | 24 MiB per copy, two copies (main and mirror), 16 KiB pages | read through the driver |
| Version | `1.101.37`; Player info shows `V1.0`, `2025-07-11` | image header; `CONFIG.BIN` |

The X91's `config.txt` differs from the AGPTEK A02XT/A02PLT one in about 20 settings; the pin map is the same except
for the disabled debug UART. 80 of the 137 files are byte-identical to files in four AGPTEK A02-family packages
(kernel, storage drivers, codecs, fonts, LCD driver); the key driver, the programs, menus and graphics differ. No
vendor package fits the X91's board, and none may be flashed onto it.

## Memory

The load addresses of all programs give the memory map: a main region from 0x100000 to 0x138000 (224 KiB) and two
small regions at 0x200000 (about 19 KiB used) and 0x300000 (about 31 KiB used).

| Range | Use |
|---|---|
| 0x101000 upward | code-bank windows of the running program; banks of one group replace each other there (see {doc}`programs`) |
| 0x110000 upward | resident parts of programs and drivers: system-call stubs (for example the display driver's `svc 6` at 0x1102e9 in `MUSIC.AP`), driver function tables (`DRV_UI.DRV` at 0x1190d4) |
| 0x118000 | where the `adfus` loader runs in upgrade mode |
| 0x200000 to 0x200800 | the front program's variables (for `MUSIC.AP` up to about 0x20078c) |
| 0x200800 on | the playback engine's variables (`MENGINE.AP`: data from 0x200800, bss 0x200910) |
| 0x202f88, 0x202f8c, 0x202fbc | system-wide state blocks (settings pointer, running program, application state) |
| 0x205300, 0x205800, 0x205dc0, 0x206ac0 | stack tops: manager, …, playback engine, front program |

The front program's stack runs from 0x206ac0 down toward 0x205dc0, about 3.3 KB.

## Boot record and boot loader

The boot record (`brec0.bin`, with a second copy `brec1.bin`; loaded at 0x10e900) holds the boot code, the chip's
128-byte NAND record (bytes 0x80 to 0xbf), the pin table (0x40 to 0x7f), the sizes of the boot record (173 sectors)
and of the firmware (38,811 sectors), and the first start-up picture (big-endian RGB565, no checksum).

What its code does with the firmware (read from its disassembly):

- It checks both firmware copies at every start; a bad copy is restored from the other (`restore src_lfi...`,
  `restore mir_lfi...`).
- On six fatal conditions (both copies bad, a failed restore in two cases, a size error, `decrypt fail!`,
  `install fail!`) it calls one routine, the upgrade-mode entry. The boot picture code calls the same routine when it
  finds the marker 0xADF0ADF0 that `adfu_reboot` leaves in RAM.

So a write that leaves the firmware area unusable should bring the player up in upgrade mode by itself. The gap: a
firmware that passes its checksums and starts, but then hangs. Only the USB-disk program (`UDISK.AP`) contains the
upgrade-mode marker, so a firmware that never reaches USB-disk mode has no software way back. That is why `UDISK.AP`,
`CONFIG.AP`, `FWUPDATE.AP`, the drivers and the boot record are never changed.

The boot record is not written by this project. The ODEJOI picture it holds therefore still shows for a moment before
the firmware's own start-up picture (`LOGO.STY` picture 0).

## Upgrade mode

| Step | How |
|---|---|
| Enter | From USB-drive mode: `sudo actions_flash/actions_dump --id 10d6:1101 adfu_reboot`. Holding Play while plugging in does not work on the X91. |
| Check | `actions_dump adfu_info` |
| Leave | Unplug, hold the power key 10 to 15 seconds, release, switch on. Unplugging alone does not leave it. |
| Rule | One job per stay in upgrade mode; the driver needs a session started from a fresh power-on. |

## Recovery

- After a write, the read-back must equal the image; if it does not, the player stays plugged in and in upgrade mode
  while the write is repeated.
- A stage that starts but misbehaves: flash "Previous firmware" (the newest `x91_dump/backups/before_*.bin`) or the
  original firmware with `x91_tool.py`.
- A player that does not start: hold power 10 to 15 s, plug in USB while off; it starts as a USB drive, and from there
  the software switch into upgrade mode works.
