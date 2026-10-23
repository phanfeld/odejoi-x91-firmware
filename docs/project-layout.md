# Project layout

| Path | What it is |
|---|---|
| `x91_tool.py` | Terminal tool: dump the firmware, flash a theme, the original firmware or "Previous firmware"; `--demo` simulates the player |
| `x91_dump/x91_flash.py` | The flash procedure (`prepare`, `rehearse`, `dump`, `write`); the tool drives it |
| `x91_dump/` | Inputs and outputs, mostly not in git: the stock image, boot records, flash helpers, the theme images, backups, the last device session (`flash_work/`) |
| `design/build.py` | The build: every theme's image from the stock image, in one go |
| `design/graphite/` | The parts of the design the build applies, one module per area (`base.py` holds the shared helpers) |
| `design/x91_design.py` | Theme colours (`THEMES`), the icon set and the mock-up generator |
| `design/patches/` | Program patches (`.S`), their checkers and the Thumb interpreter `thumb_sim.py` |
| `design/playlist/` | New program code in C, `fw.h` and the host test (`host/`) |
| `design/make_screens.py`, `design/screens/` | Renders of the current screens for the documentation |
| `design/src/`, `design/mock/`, `design/pictures/` | SVG sources of the mock-ups and their renders |
| `design/history/` | Previews made while each stage was built |
| `firmware_analysis/tools/` | `x91_modify.py`, `x91_preview.py`, `ap_dis.py`, `drv_dis.py`, `lfi_verify.py`, `x91_cover.py`, `x91_playlist.py`, vendor package analysis scripts |
| `actions_flash/` | Submodule: upstream `actions_flash`, the USB tool `actions_dump` and its ARM payloads |
| `patches/` | Our changes to third-party code (the X91 page-size scan for `actions_dump`) |
| `docs/` | These pages (Sphinx, MyST Markdown) |
| `CHANGELOG.md` | What each release contains |

Generated or local-only paths, the stock firmware and vendor files are listed in `.gitignore`.
