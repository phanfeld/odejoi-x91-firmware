# Build system

## One build from the stock image

`design/build.py` makes the firmware images. It reads the stock image `x91_dump/x91_lfi_verified.bin` (and checks
its sha256), and for each theme applies every part of the design (`design/graphite/`) to a copy of it in memory, one
after the other, and writes the image once:

```
x91_lfi_verified.bin ─ typeface ─ mainmenu ─ pictures ─ screensaver ─ music ─ settings ─ reader ─ statusbar
                     ─ lists ─ playlists ─ sideways copies ─ x91_lfi_<theme>.bin
```

Before the themes it compiles and runs the host test of the new C code ({doc}`new-code`) once; it does not depend on
the theme. A build of all four themes takes about a minute.

```bash
python3 -I design/build.py
```

| Option | Does |
|---|---|
| `THEME …` | build only these themes (`amber`, `mint`, `ice`, `berry`); `themes.json` keeps the others' entries |
| `--out DIR` | write somewhere else than `x91_dump/themes` |
| `--check` | stop with an error unless every image built is the release image (`RELEASE` in `build.py`) |

The images are byte-for-byte reproducible: the same stock image, sources and tools give the same bytes. `RELEASE`
holds the sha256 of the 1.0.0 images; they are the stage 27 images that were flashed and tested on the player
({doc}`../project/history`).

## The parts

Each module of `design/graphite/` changes one area of the firmware and has a `build(b)` function; `build.py` runs them
in the order of `STEPS`.

| Module | Files it changes | What |
|---|---|---|
| `base.py` | | paths, the theme's colours `T`, `Build` (the image being built), and the helpers below |
| `typeface.py` | `UNICODE.FON` | Ubuntu 12 px in one bit, hand-drawn glyphs (`HAND`, also the shapes of every pixel-drawn digit), look-alikes for missing glyphs |
| `mainmenu.py` | `LOGO.STY`, `END.STY`, `MAINMENU.STY`, `MAINMENU.AP`, `CONFIG.BIN`, `CONFIG.TXT`, `MUSIC.AP` | start-up picture, shut-down animation, the six tiles, the Playlists tile (`music_playlists_tile.S`) |
| `pictures.py` | `COMMON.STY`, `BT.STY` | status icons, battery, charging, list rows and marks, scroll bar, neutral icons, key lock, notices, volume pop-up, brightness, Bluetooth search |
| `screensaver.py` | `COMMON.STY`, every program with the clock | meadow and animation, clock digits, `clock_sprite.S` and the 200 ms timer in seven programs, the colour key 0 |
| `music.py` | `MUSIC.MCG`, `MUSIC.STY`, `MUSIC.AP` | Playlists first in the music menu, the playing screen's pictures and layout, "Favorites", `music_playing.S`, `music_title.S` |
| `settings.py` | `SETTING.MCG`, `CONFIG.BIN`, `CONFIG.TXT`, `MENGINE.AP` | Sound settings, lyrics off, the volume curve |
| `reader.py` | `EBOOK.STY`, `EBOOK.AP` | the reader in landscape (`ebook_reader.S`), line breaks between words, page-index signature |
| `statusbar.py` | `MUSIC.STY`, `MUSIC.AP`, `COMMON.STY`, `MAINMENU.AP`, 15 programs | the playing screen's bar background and card marks, the main menu clock, `headbar_soon.S`, the marks' black border |
| `lists.py` | `COMMON.STY`, ten `.STY`, `MUSIC.MCG`, `SETTING.MCG`, 15 programs | list styles, short menu names and titles, `list_box` (`liststyle.c`) in five programs, `menu_box.S` |
| `newcode.py` | | the new code: host test, compile, plan helpers, link, put into bank tails |
| `playlists.py` | `PLAYLIST.STY`, `PLAYLIST.AP`, `MUSIC.MCG`, `MUSIC.STY`, `MUSIC.AP` | "Searching...", the library builder, the option lists, the new code's placement and callers |

After the parts, `base.refresh_copies` brings every sideways copy in line with its picture
({doc}`../firmware/resources`).

Each part works the same way:

1. it checks that what it is about to change is what it expects (stock bytes, record values, texts, picture sizes) and
   stops otherwise;
2. it takes colours from `base.T`, the theme being built with the background forced to black;
3. it changes files with `b.get(name)` and `b.put(name, data)` (same length, checksums recomputed); program code
   only with checked byte changes and patches that pass their checker ({doc}`patches`), or through the new code's
   placement ({doc}`new-code`);
4. it notes what it did (`b.note`), which ends up in `THEME/build.txt`.

The order matters where two parts touch the same bytes or one reads what another wrote:

- `music` packs the string tables of `MUSIC.STY` anew where it writes "Favorites"; `lists` and `playlists` change
  English texts in place afterwards.
- `music` takes the red glow out of every playing-screen picture; `statusbar` draws the note on that background.
- `statusbar` borders the status bar's marks as `pictures` and `statusbar` drew them.
- `screensaver` sets the colour key after `clock_sprite.S` is in (the key sits inside that routine in seven programs).
- `lists` puts `list_box` and `menu_box` at the ends of their banks before `playlists` places the new code, which
  leaves those banks out.
- The sideways copies come last.

## Changing the design

1. Change the module of the area (a new area is a new module, added to `STEPS` in `build.py`).
2. Check before changing; take colours from `base.T`; note what was done.
3. Build every theme. The images change, so `--check` fails until `RELEASE` holds the next release's hashes.
4. Flash and test one change at a time; `x91_tool.py` keeps the image the last write replaced as "Previous firmware".

## Helpers worth knowing

| Helper | Does |
|---|---|
| `base.Build(theme, work)` | the stock image as `b.lfi` (`x91_modify.Lfi`), `get`, `put`, `stock_file`, `programs`, `folder`, `note` |
| `base.render_565(svg, w, h, work, name)` | SVG → RGB565 bytes through `vectorcraft-cli` |
| `base.svg`, `base.text`, `base.stroke`, `base.c565`, `base.mix` | SVG pieces in the theme; RGB565 of a colour |
| `base.Pictures(sty, work)` | `.svg(index, svg, w, h, name)` and `.raw(index, data, w, h)` into one resource file |
| `base.set_picture`, `base.resize_picture`, `base.picture_bytes`, `base.pictures` | replace a picture of the same size; declare one smaller; read them |
| `base.pixel_glyph`, `base.dots`, `base.fill` | pixel digits in the font's hand-drawn shapes, dot pictures, plain pictures |
| `base.with_copy(stock_sty)`, `base.refresh_copies(b)` | find and refresh the sideways copies |
| `base.tables_of(sty)`, `base.set_fields(sty, table, size, index, wN=…)` | layout tables and their records |
| `base.set_string`, `base.set_english`, `base.english`, `base.text_of`, `base.text_width` | texts: a language's table packed anew; English texts in place; a text's width in the interface font |
| `base.menu_heads`, `base.rows_of(mcg, hsz, li)` | a menu file's list table; a list's header and rows |
| `base.patch_bytes(buf, offset, old, new, what)` | replace bytes after checking the old ones |
| `base.assemble(name, work, defsym)`, `base.disassemble(data, address, path)` | assemble a patch; disassemble a bank for a checker |
| `base.check(checker, old, new, address, work, tag, args)` | run a checker on the old and new bank, stop if it fails |
| `base.replace_stretch(...)` | check the stock bytes, run the checker, put the new code in |
| `base.masked`, `base.find_all`, `base.bls` | find a stretch of shared code in any program with its calls masked; list its calls |
| `base.thumb_bl(at, target)`, `base.bl_target(ap, segs, at)`, `base.bl_at(code, k, at)` | encode and decode a Thumb `bl` |
| `base.bank_list`, `base.slot_of` | a program's banks; the room of a bank's file slot |
| `newcode.host_test`, `compile_code`, `stack_depth`, `free_tails`, `place`, `link`, `put_code` | the new code ({doc}`new-code`) |
| `newcode.compile_tail`, `newcode.put_tail` | one function on its own, at the end of one bank (`list_box`) |
| `lists.bank_entry`, `lists.list_calls`, `lists.place_list_box`, `lists.place_menu_boxes` | a bank's room in its group; the list box calls of a program; `list_box` and `menu_box` |
| `statusbar.bordered_marks(b)` | the status bar's marks with their black border, stored in picture 240 |
| `playlists.option_menus(b)`, `playlists.plan(ap, secs)` | the music lists' option lists; the placement of the new code |
| `design/playlist/host/render.py` | pictures of the search and name screens from the host test's draw log (`SEARCH_SCREENS`) |

## Outputs

| Path | Content |
|---|---|
| `x91_dump/themes/x91_lfi_<theme>.bin` | the flashable image |
| `x91_dump/themes/themes.json` | the list `x91_tool.py` reads: id, name, accent, file, version, sha256, date |
| `x91_dump/themes/<theme>/unpacked/` | the image's files (`design/make_screens.py` reads them) |
| `x91_dump/themes/<theme>/work/` | per part: rendered SVG and PNG, compiled code, linker scripts, disassemblies, checker listings |
| `x91_dump/themes/<theme>/build.txt` | what each part did, the code's placement, the image's sha256 |
| `x91_dump/themes/host_test/` | the host test's program |

## Before 1.0: the stages

Up to stage 27 the design was built as a chain of 27 builders, `design/build_stageN.py`, each reading the image of
the stage before and writing its own, with frozen copies of the C sources per stage so that every intermediate image
stayed reproducible ({doc}`../design/stages`, {doc}`../project/history`). Release 1.0 merged them into this build:
each change is applied in its final form only, code a later stage took out again is never placed, and the frozen
sources and the intermediate images are gone. The result is the stage 27 image, byte for byte, in every theme. The
stage builders are in the git history (the last one at commit `1e2be06`, "Stage 27 rebuilt").
