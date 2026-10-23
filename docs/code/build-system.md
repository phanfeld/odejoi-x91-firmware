# Build system

## The chain

Every stage is a script `design/build_stageN.py` with one job: read the previous stage's image, change files, write
the next image. Nothing is edited by hand, so every image can be rebuilt from the stock dump.

```
x91_lfi_verified.bin ─ stage 1 ─ stage 3 (with stage 2's font) ─ stage 4 ─ … ─ stage 26 ─ x91_lfi_<theme>.bin
```

A builder:

1. reads its input image: the environment variable `X91_STAGE<N-1>` if set, else
   `x91_dump/stage<N-1>/x91_lfi_stage<N-1>.bin`, and checks its checksums;
2. takes colours from `build_stage1.T` (the theme named by `X91_THEME`, default Amber);
3. checks that what it is about to change is what it expects (stock bytes, record values, text, picture sizes) and
   stops otherwise;
4. changes files with `lfi.put(name, bytes)` (same length, checksums recomputed);
5. writes `OUT_DIR/x91_lfi_stageN.bin` (default `x91_dump/stageN/`), the unpacked files and work files, and prints
   which files changed and the image's sha256.

`design/build_theme.py [THEME …]` runs the stages listed in its `STAGES` for each theme, with `X91_THEME` and the
`X91_STAGE<N>` variables pointing into `x91_dump/themes/<theme>/`, checks that each stage reports "checksum failures:
none", copies the last image to `x91_dump/themes/x91_lfi_<theme>.bin` and records it in `themes.json` (id, name,
accent, file, stage, sha256, date), which `x91_tool.py` reads.

## Adding a stage

1. Copy the shape of an existing builder (a small one: `build_stage12.py`, `build_stage17.py`).
2. Honour `X91_STAGE<N-1>` and take colours from `build_stage1.T`.
3. Check before changing; print what was done.
4. Add N to `STAGES` in `design/build_theme.py` and build every theme.

Flash and test one stage at a time. A stage that misbehaves on the player is fixed in place ("stage 21 rebuilt")
rather than followed by a new number.

## Reproducibility

The images are deterministic. Two things keep them so when code changes:

- **Frozen sources.** A stage that changes the C sources in `design/playlist/` first copies the previous stage's
  sources into `design/playlist/stageN/` (stage 18, 20, 21, 23, 24, 25) and points that stage's builder at the copy.
- **Code hashes.** Builders 20, 21, 23, 24 and 25 hash the code they place (bank address plus bytes, in bank order;
  stage 24 also each program's `list_box`, `LIST_BOX_SHA`) and stop if the frozen sources no longer give the hash
  recorded in `CODE_SHA`. Their host test is skipped for frozen sources ("not run here"). Stage 25's code holds the
  theme's colours, so its `CODE_SHA` has one hash per theme. Stage 26's sources are the live ones.

`music_headbar.S` stays as stage 14 wrote it; stage 24's changed status-bar routine is a new file
(`headbar_soon.S`) for the same reason.

## Helpers worth knowing

| Helper | Does |
|---|---|
| `x91_modify.Lfi(data)` | the image container: `get`, `put`, `check`, `unpack`, `d` (the bytes) |
| `ap_dis.segments(data)`, `ap_dis.find(segs, address)` | a program's segments; the file offset of an address |
| `build_stage1.render_565(svg, w, h, work, name)` | SVG → RGB565 bytes through `vectorcraft-cli` |
| `build_stage1.set_picture(sty, i, data, w, h)` | replace a picture of the same size |
| `build_stage7.resize_picture(sty, i, w, h)` | declare a picture smaller |
| `build_stage14.with_copy(stock_sty)`, `build_stage14.refresh_copies(lfi, done)` | find and refresh the sideways copies |
| `build_stage11.tables_of(sty)`, `build_stage11.set_fields(sty, table, size, index, wN=…)` | layout tables and their records |
| `build_stage11.pixel_glyph`, `build_stage11.dots`, `build_stage11.s10_colour` | pixel digits, dot pictures, RGB565 of a colour |
| `build_stage5.patch_bytes(buf, offset, old, new, what)` | replace bytes after checking the old ones |
| `build_stage14.assemble(name, work)`, `build_stage14.disassemble(data, base, path)` | assemble a patch; disassemble a bank for a checker |
| `build_stage14.replace_stretch(...)` | check stock bytes, run the checker, put new code in |
| `build_stage22.masked`, `find_all`, `bls` | find a stretch of shared code in any program with its calls masked; list its calls |
| `build_stage20.thumb_bl(at, target)`, `build_stage21.bl_target(ap, segs, at)` | encode and decode a Thumb `bl` |
| `build_stage20.compile_code`, `plan`, `link`, `stack_depth`, `host_test` | the new code's compile and placement ({doc}`new-code`) |
| `build_stage18.put_code`, `bank_entry` | write placed code into bank tails |
| `build_stage21.take_out_code(ap, stock_ap)`, `rows_of(mcg, hsz, li)` | remove earlier new code from its banks; a menu list's items |
| `build_stage23.old_code`, `old_targets` | the ranges of earlier new code, and checks that the calls into it are where expected |
| `build_stage24.place_list_box(ap, name, work, counted, top)` | compile `liststyle.c` for one program and put it at the end of its list control bank |
| `build_stage24.headbar_soon(lfi, work)` | put `headbar_soon.S` into every program with the stage 14 routine |
| `build_stage24.place_menu_boxes(ap, name, work)` | put `menu_box.S` at the end of every bank with a list box call, re-aim the calls, run `check_menu_box.py` per bank |
| `build_stage24.bank_entry(ap, addr)`, `put_tail(...)` | a bank's table entry and the room its slot and group allow; link one function at the end of a bank |
| `build_stage24.status_marks(com)` | the status bar's marks with their black border, stored in picture 240 |
| `build_stage25.option_menus(lfi)` | the music lists' option lists with a "Search" row, laid out anew in the room of lists 21 to 40 |
| `build_stage25.menu_box_banks(ap, stock)`, `replace_code(lfi, work, stock_ap)` | the banks whose ends hold stage 24's `menu_box`; the playlist code out of its banks and placed anew, those banks and `list_box` kept and checked unchanged |
| `build_stage26.option_menus(lfi)`, `plan(ap, secs)`, `stack_depth(work)` | "Add songs" in the Playlists options; the placement with `FAR_GROUPS` in the 0x1a00 group; the stack measured with inline helpers known by name |
| `design/playlist/host/render.py` | pictures of the search screen from the host test's draw log (`SEARCH_SCREENS`) |

## Outputs

| Path | Content |
|---|---|
| `x91_dump/stageN/x91_lfi_stageN.bin` | the image (Amber) |
| `x91_dump/stageN/unpacked/` | its files |
| `x91_dump/stageN/pictures/` | rendered SVG and PNG of the stage's pictures |
| `x91_dump/stageN/code/` | compiled code, link scripts, disassemblies, checker listings |
| `x91_dump/themes/<theme>/stageN/` | the same per theme |
| `x91_dump/themes/x91_lfi_<theme>.bin`, `themes.json` | the flashable images |
