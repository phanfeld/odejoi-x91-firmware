# ODEJOI X91 firmware

Custom firmware for the ODEJOI X91 MP3 player (Actions ATJ2157). The stock firmware was dumped over USB and
reverse-engineered; a new interface, **Graphite**, is built on top of it by one build that patches the stock image.
A terminal tool dumps the firmware and flashes a theme.

**Release 1.0.0**: the complete design in four themes (Amber, Mint, Ice, Berry), flashed and tested on the player.
What it contains: [`CHANGELOG.md`](CHANGELOG.md).

![Main menu, Music menu, a playlist, the playing screen and the screensaver in the Berry theme](design/screens/berry.png)

![Main menu and playing screen in Amber, Mint, Ice and Berry](design/screens/themes.png)

## Quick start

Fetch the `actions_flash` submodule and build the USB tool once:

```bash
git submodule update --init
make -C actions_flash
make -C actions_flash/payload_arm TOOLCHAIN=arm-none-eabi CC="arm-none-eabi-gcc -march=armv7-m -mthumb"
```

Build every theme's image from the stock dump (`x91_dump/x91_lfi_verified.bin`, not in git); `--check` confirms that
the images are the release images, byte for byte:

```bash
python3 -I design/build.py --check
```

Dump the firmware or flash a theme:

```bash
python3 x91_tool.py
```

Requirements, the files that are not in git and where they come from: `docs/quickstart.md`. The stock firmware and
vendor files are not part of this repository, and neither are the images built from them; outside sources and their
versions are in `docs/project/sources.md`.

## Layout

| Path | What it is |
|---|---|
| `x91_tool.py` | Terminal tool: dump, flash a theme, roll back |
| `x91_dump/x91_flash.py` | The flash procedure the tool drives |
| `design/build.py` | The build: stock image in, one image per theme out |
| `design/graphite/` | The parts of the design, one module per area (typeface, main menu, pictures, screensaver, music, settings, reader, status bar, lists, playlists) |
| `design/patches/` | Program patches in Thumb assembly and their checkers |
| `design/playlist/` | New program code in C (playlists, search, naming) and its host test |
| `design/` | Also theme colours (`x91_design.py`), design sources, mock-ups, screen renders, stage previews (`history/`) |
| `firmware_analysis/tools/` | Image container, resource previewer, disassemblers, cover and playlist tools |
| `actions_flash/` | Submodule: upstream USB client for the chip's upgrade mode |
| `patches/` | Our patch to `actions_flash` for the first dump |
| `docs/` | Documentation of the firmware and of this code (Sphinx) |

## Documentation

Online at **https://phanfeld.github.io/odejoi-x91-firmware/**, rebuilt by GitHub Actions on every push to `main`
that changes `docs/` (`.github/workflows/docs.yml`). To build it locally:

```bash
make -C docs html
```

Then open `docs/_build/html/index.html`. Start with the overview and the quick start; the firmware reference covers
the image format, programs, resources, display driver, shared code, music engine and the flash procedure.

## Warning

Flashing can brick the player. No hardware key for upgrade mode is known; recovery depends on the USB-drive program
still starting. Read `docs/firmware/hardware.md` and `docs/firmware/flashing.md` first.

## Licence

Apache License 2.0, see [`LICENSE.md`](LICENSE.md). The stock firmware is not part of this repository.
