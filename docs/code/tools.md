# Tools

## On the device

`x91_tool.py`
: Terminal interface (curses) for two jobs: **Dump** the firmware into `x91_dump/backups/`, and **Flash a theme**
  (a theme image, "Previous firmware" or the original), with a backup first and a read-back after. Restarts itself
  through sudo; `--demo` simulates the player. Reads `x91_dump/themes/themes.json`. See {doc}`../firmware/flashing`.

`x91_dump/x91_flash.py`
: The flash procedure: `prepare`, `rehearse`, `dump --out F`, `write --image F --yes-write-flash [--backup B]`.

`actions_flash/actions_dump`
: The open USB client for Actions upgrade mode, from the `actions_flash` submodule: `adfu_reboot`, `adfu_info`,
  loading payloads, reading boot records. `x91_flash.py` drives it. `patches/actions_flash-x91_scan.patch` adds the
  page-size override needed for the first dump ({doc}`../firmware/flashing`).

## Firmware files

`firmware_analysis/tools/x91_modify.py`
: The image container `Lfi` (`get`, `put`, `check`, `unpack`; {doc}`../firmware/image-format`). As a script it built
  the first custom start-up picture: `--lfi`, `--brec`, `--out-dir`, `--png` or `--text`.

`firmware_analysis/tools/lfi_verify.py`
: Verifies a dump read twice (each read holding two copies) file by file and writes a checked image:
  `lfi_verify.py READ1 READ2 FW_SECTORS PAGE_SIZE OUT_IMAGE [UNPACK_DIR]`.

`firmware_analysis/tools/x91_preview.py`
: Reads the `.STY` files of an unpacked image and redraws every picture, every text in every language and every
  layout scene into one HTML page: `x91_preview.py UNPACKED_DIR OUT.html [--lang English] [--lang2 German] [--brec
  brec0.bin]`. As a module: `Firmware(folder)`, `Sty` (`pics`, `langs`, `scenes`, `picboxes`, `textboxes`,
  `pic_rgb(i)`). It models picture and text boxes only.

`firmware_analysis/tools/ap_dis.py`
: Splits a program into resident segments and code banks and disassembles them with real addresses:
  `ap_dis.py FILE.AP OUT_DIR` (a map and a listing). As a module: `segments(data)`, `find(segs, address)`.

`firmware_analysis/tools/drv_dis.py`
: The same for drivers, with the three bank groups of `DRV_UI.DRV`.

## Media on the player

`firmware_analysis/tools/x91_cover.py`
: Writes a copy of an MP3 with one 90 x 90 baseline JPEG as ID3v2.3 front cover, the form the playing screen shows:
  `x91_cover.py IN.mp3 COVER.jpg OUT.mp3 [SIZE]`.

`firmware_analysis/tools/x91_playlist.py`
: Writes `.m3u` playlists in the form the firmware reads (backslashes, CR LF, paths from the root, ASCII or code page
  1252): from folders, by converting existing lists, or from files already on the player.

## Vendor package analysis

`rarx.py` (list or extract archives through libarchive), `analyze.py` (unpack vendor archives and collect the metadata
of Actions FWU packages, with Rockbox's `utils/atj2137/atjboottool`), `summary.py` (a table from the results,
`firmware_analysis/package_summary.tsv`), `dumpdb.py` (write the files of a decrypted package), `compare_lfi.py`
(compare the X91's files with those in the packages). Used once, to find the X91's closest relatives (the AGPTEK
A02 family).

## Design

`design/x91_design.py`
: Theme colours (`THEMES`), the icon set (`icon`), and the mock-up generator (`x91_design.py OUT_DIR`), which draws
  screens as SVG plus the texts the way the player draws them.

`design/make_board.py`
: Builds the design board (`x91-design-board.svg` and an HTML page) from the mock-ups. Given an unpacked stock
  image it adds the stock main menu and font for comparison; those renders stay out of git.

## Documentation

`docs/` (these pages): `make -C docs html`; see `docs/README.md`.
