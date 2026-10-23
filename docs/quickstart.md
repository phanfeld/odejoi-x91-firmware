# Quick start

All commands run from the repository root.

## Requirements

- Linux, Python 3.12 with pycairo (no Pillow, no numpy). Scripts are run with `python3 -I`.
- `arm-none-eabi-gcc`, `-as`, `-ld`, `-objdump`, `-objcopy`, `-readelf` (GCC 13.2) for patches and new code.
- The Ubuntu typeface installed as a system font (the build renders the interface font from it).
- `vectorcraft-cli` renders the SVG pictures; `ffmpeg` is used by the cover tool.
- `libusb-1.0` development files, to build `actions_dump`.

`actions_flash/` is a git submodule (upstream [actions_flash](https://github.com/ilyakurdyukov/actions_flash)).
Fetch it and build the USB tool and the `adfus` loader once:

```bash
git submodule update --init
```

```bash
make -C actions_flash
```

```bash
make -C actions_flash/payload_arm TOOLCHAIN=arm-none-eabi CC="arm-none-eabi-gcc -march=armv7-m -mthumb"
```

## Files that are not in git

The stock firmware, vendor files, device data and build output stay out of the repository. The build and the
flashing tool expect these in `x91_dump/`:

| File | What it is | Where it comes from |
|---|---|---|
| `x91_lfi_verified.bin` | the stock firmware, input of every build | dumped from the player ({doc}`firmware/flashing`); sha256 in `x91_dump/SHA256SUMS.txt` |
| `brec0.bin`, `mbrec.bin` | the unit's boot records | `actions_dump read_brec` |
| `flash_helpers/` | vendor `nandhwsc.bin`, `fwscf651.bin`, `flash_id.bin` | the AGPTEK A02XT/A02PLT package `A02T-20250709-V1.0`, decrypted with `analyze.py` and written out with `dumpdb.py`; sha256 in `x91_dump/flash_helpers/SHA256SUMS.txt` |
| `device_files/2026-10-21/M3U.LIB` | a playlist library from a player | copied from the player's disk; the host test of the C code runs on it |

{doc}`project/sources` lists every outside source with its exact version.

## Build the images

```bash
python3 -I design/build.py
```

This runs the host test of the new C code, then builds the image of every theme (Amber, Mint, Ice, Berry) from the
stock image in one go: `x91_dump/themes/x91_lfi_<theme>.bin`, and `x91_dump/themes/themes.json`, which the flashing
tool reads. It takes about a minute. The result is byte-for-byte reproducible; with `--check` the build stops unless
every image is the release image (sha256 in `RELEASE` of `design/build.py` and in `CHANGELOG.md`). One theme only:
`build.py berry`. Each theme's files, work files and a report of what was done are in `x91_dump/themes/<theme>/`
({doc}`code/build-system`).

## Flash a theme

```bash
python3 x91_tool.py
```

The tool restarts itself through sudo and offers two jobs:

- **Dump**: switch the player into upgrade mode, read the firmware into
  `x91_dump/backups/x91_firmware_DATE_TIME.bin`, check its checksums and say which known image it is.
- **Flash a theme**: choose a theme image, "Previous firmware" (what the last write replaced) or the original
  firmware; type YES; the tool saves what is on the player to `x91_dump/backups/before_NAME_DATE_TIME.bin`, writes,
  reads back and compares.

One job per stay in upgrade mode: afterwards unplug the player, hold the power key 10 to 15 seconds and switch it on
again. `x91_tool.py --demo` shows the same screens with a simulated player.

After a flash, `x91_dump/flash_work/readback.bin` is the image that was written; its sha256 tells which build is on
the player.

## Look at the firmware offline

- Unpack an image: `x91_modify.Lfi(data).unpack(folder)`; the build writes each theme's files to
  `x91_dump/themes/<theme>/unpacked/`.
- Resources: `python3 -I firmware_analysis/tools/x91_preview.py UNPACKED_DIR OUT.html` renders every picture, text
  and layout scene into one HTML page.
- Programs: `python3 -I firmware_analysis/tools/ap_dis.py FILE.AP OUT_DIR` writes a map and a Thumb disassembly with
  real addresses; `drv_dis.py` does the same for a driver.

## Build these pages

```bash
make -C docs html
```

See `docs/README.md` for the Sphinx setup. The site is `docs/_build/html/index.html`.
