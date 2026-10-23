# Sources

Nothing from the stock firmware is in this repository, and no third-party code is copied into it.

## Used for flashing and building

| What | Source | How it is used |
|---|---|---|
| `actions_dump`, `adfus` loader, `nandread` payload | [ilyakurdyukov/actions_flash](https://github.com/ilyakurdyukov/actions_flash), commit `0a7d9cf` | git submodule `actions_flash/`; the X91 page-size scan is our patch `patches/actions_flash-x91_scan.patch` |
| Flashing sequence, read-only driver patch | [TheWirelessPhoenix/a02-os](https://github.com/TheWirelessPhoenix/a02-os) | re-implemented in `x91_dump/x91_flash.py`; no code copied |
| Vendor flash helpers `fwscf651.bin`, `nandhwsc.bin`, `flash_id.bin` | AGPTEK A02XT/A02PLT firmware package `A02T-20250709-V1.0` ([download page](https://www.agptek.com/blog/a02xt-a02plt-firmware-upgrade/)) | not in git; extracted locally, checked against `x91_dump/flash_helpers/SHA256SUMS.txt` and the hash pinned in `x91_flash.py` |
| Ubuntu typeface | [Ubuntu Font Family](https://design.ubuntu.com/font) (Ubuntu Font Licence 1.0) | rendered from the installed system font by `design/graphite/typeface.py` |

## Used for analysis only

| What | Source | How it is used |
|---|---|---|
| `atjboottool` | [Rockbox](https://github.com/Rockbox/rockbox) `utils/atj2137/atjboottool`, commit `ef1b9d1` (GPL-2.0-or-later) | decrypts vendor `.fw` packages for `firmware_analysis/tools/analyze.py` |
| US212A SDK of the ATJ2127 | [Suber/PD196_ATJ2127](https://github.com/Suber/PD196_ATJ2127), commit `b964feb` | names, structures and logic for reading the X91's code; nothing copied |
| AGPTEK packages of the A02 family | [agptek.com firmware downloads](https://www.agptek.com/index.php/blog-category/firmware-download/) | compared with the X91's files (`firmware_analysis/package_summary.tsv`); never flashed |
