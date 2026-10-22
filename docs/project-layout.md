# Project layout

| Path | What it is |
|---|---|
| `x91_tool.py` | Terminal tool: dump the firmware, flash a theme, the original firmware or "Previous firmware"; `--demo` simulates the player |
| `x91_dump/x91_flash.py` | The flash procedure (`prepare`, `rehearse`, `dump`, `write`); the tool drives it |
| `x91_dump/` | Inputs and outputs, mostly not in git: the stock image, boot records, flash helpers, stage and theme images, backups, the last device session (`flash_work/`) |
| `design/x91_design.py` | Theme colours (`THEMES`), the icon set and the mock-up generator |
| `design/build_stageN.py` | One stage each; `build_theme.py` chains them for every theme |
| `design/patches/` | Program patches (`.S`), their checkers and the Thumb interpreter `thumb_sim.py` |
| `design/playlist/` | New program code in C, `fw.h`, the host test (`host/`) and frozen copies per stage |
| `design/src/`, `design/mock/`, `design/*-preview.png` | SVG sources of the mock-ups, rendered mock-ups, previews of each stage |
| `firmware_analysis/tools/` | `x91_modify.py`, `x91_preview.py`, `ap_dis.py`, `drv_dis.py`, `lfi_verify.py`, `x91_cover.py`, `x91_playlist.py`, vendor package analysis scripts |
| `actions_flash/` | Submodule: upstream `actions_flash`, the USB tool `actions_dump` and its ARM payloads |
| `patches/` | Our changes to third-party code (the X91 page-size scan for `actions_dump`) |
| `docs/` | These pages (Sphinx, MyST Markdown) |

Generated or local-only paths, the stock firmware and vendor files are listed in `.gitignore`.
