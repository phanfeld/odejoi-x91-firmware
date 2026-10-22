# New program code (design/playlist)

Since stage 18 the project adds program code written in C. It runs inside `MUSIC.AP` (and, for the list style,
four more programs), called from a few re-aimed `bl` instructions and menu rows.

## Rules the code follows

- **No data of its own.** No global or static variables, no string constants (constant text is built in code), no
  C library. Everything the firmware offers is reached through fixed addresses in `fw.h`. The builders refuse
  sections other than `.text.*`.
- **Buffers on the stack.** The RAM from 0x101000 upward is where code banks are loaded; data there does not survive
  a call into another bank. The front program's stack has about 3.3 KB; the builders compute the deepest chain of the
  new code's own frames from the compiler's `.su` files and the call graph and refuse more than 1024 bytes
  (`STACK_MAX`; the stage 23 code needs 956).
- **One file open at a time** (the player's file handles are few).
- **Pause around file work.** While files are read and written a playing song is paused (0x315) and resumed (0x316),
  as the Play key does; the engine reads the same storage.
- **Pages as long as the list style.** The picker shows `ROWS` = 5 rows, the line count of list style 0x6004.
- **The status bar's middle.** A list drawn with style 0x6004 or one of the file-list styles is drawn with the bar on
  and its middle cleared first (`clear_bar` in `fw.h`) on a full redraw: since stage 24 these styles' background
  starts below the bar.

Compiler flags (`build_stage18.CFLAGS`): `-mcpu=cortex-m4 -mthumb -Os -fno-inline -ffreestanding -fno-builtin
-nostdlib -fno-strict-aliasing -fno-tree-loop-distribute-patterns -ffunction-sections -fdata-sections -fno-common
-fstack-usage -Wall -Wextra -Werror`.

## Files

| File | What it does | Entry points |
|---|---|---|
| `fw.h` | Every firmware entry point and structure the code uses, with the address and how it was found; with `-DHOST` the same names are plain function declarations that `host/mock.c` implements | |
| `util.h` | small helpers (byte fill, upper case, little-endian reads and writes) | |
| `playlist.h`, `playlist.c` | the playlist picker, appending a song to an `.m3u` or making "New playlist N", removing lines (the file keeps its size; the rest becomes one comment line of `#` and spaces), messages | `add_playing_to_playlist`, `remove_playing_from_playlist` (rows 4 and 5 of `MUSIC.MCG` lists 42 and 59) |
| `library.h`, `library.c` | `M3U.LIB` kept up to date in place: open and check, find a playlist, add a playlist record, add and remove songs, delete a record, move a song; every write leaves a readable file | used by the others |
| `browse.c` | the list options: "Add to playlist" in the song lists (a song, or every song of an album, artist or genre), "Delete" (a song in a playlist, or a playlist's file), "Move song" | `list_option`, `m3u_option` (the result-handler calls at 0x1816102e, 0x18161092) |
| `keys.c` | the Previous key: after 3 s of a song restart it (engine seek 0x317 with break point 0 between pause and resume), else the previous song; with the screen off by the engine's own time | `previous_key` (0x180a13b6), `standby_previous` (0x18b41a6e) |
| `liststyle.c` | the file lists' top line: the counter inside one album or playlist, else the level's name; on a full redraw it first clears the status bar's middle | `list_box` (0x18661380, in five programs) |
| `host/` | `mock.c`, `mock.h`, `test.c`: the test on the computer | |
| `stage18/`, `stage20/`, `stage21/`, `stage23/` | frozen copies of the sources as each stage shipped them | |

`fw.h` in brief:

| Group | Names |
|---|---|
| File system (`svc 17`) | `vfs(a, b, c, cmd)`; `place_t` (folder chain and directory entry), `VFS_*` commands |
| Display (`svc 6`) | `ui(a, b, c, fn)`; `strdesc_t`, `listbox_t`, `style_t`, `dialog_t`; style ids `STYLE_PICKER` 0x6004, `STYLE_DIR` 0x6000, `STYLE_COUNTED` 0x6003, `STYLE_NAMED` 0x6005 |
| Keys and results | `get_gui_msg`, `get_app_msg`, `app_dispatch`, `key_mapping`; `EV_*` events, `RESULT_*` codes |
| Messages | `message_box`, `string_format`, `dialog`, `dialog_text`; text ids `S_*` of `MUSIC.STY` and `COMMON.STY` |
| Engine | `engine_status` (0x32e), `engine_pause` (0x315), `engine_resume` (0x316), `engine_seek` (0x317), `engine_stop`, `previous_song`, `elapsed_ms`, `engine_time` (0x200914), `music_playing` |
| Browser | `browser_enter_dir`, `browser_get_items`, `browser_select`, `browser_get_location`, `browser_scan_init`, `browser_scan`, `browse_path` (0x2003c0), `m3u_list` (0x200116), `list_level` (`g_dir_browser`), the stock result handlers |
| Per program | `LIST_LEVEL_AT` and `UI_ENTRY` default to `MUSIC.AP`'s addresses; `liststyle.c` is compiled with another program's |

## Host test

`design/playlist/host/` runs all of it on the computer against a simulated player:

- a simulated disk with folder positions, `cd back` onto the folder just left, long names, byte-wise reads and
  writes, a refusal of a second open file;
- a simulated library: after every change the test's `M3U.LIB` is compared with one built from scratch the builder's
  way, and the library functions also run on the player's own copy (`x91_dump/device_files/2026-10-21/M3U.LIB`);
- a simulated browser (song lists, albums, the Playlists list), questions, the list box (which refuses more rows
  than the style's lines), the engine (status, pause, resume, seek, time) and the list levels for `list_box`.

Deliberately broken versions of the code (wrong copy direction, users not renumbered, order kept, no question,
a batch stopping after one song, a missing layer check, …) all fail it. Compile and run it by hand:

```bash
cd design/playlist
cc -std=c99 -Wall -Wextra -Werror -DHOST -g -fsanitize=address,undefined -I . -o host_test \
   host/test.c host/mock.c playlist.c library.c keys.c browse.c liststyle.c
./host_test ../../x91_dump/device_files/2026-10-21/M3U.LIB
```

The stage builders run it first (`build_stage20.host_test`) and stop if it fails.

## Placement into bank tails

Every bank of `MUSIC.AP` sits in a 1 KB-aligned slot of the file with zeros behind it. New code goes into those
tails, in banks of the 0x1000 group (they run at 0x101000):

1. **Compile** each source with one section per function (`compile_code`); record each section's size.
2. **Take out** earlier new code: every 0x1000-group bank back to its stock length with zeros behind
   (`build_stage21.take_out_code`).
3. **Plan** (`build_stage20.plan`): the candidate banks are the 0x1000-group banks with free room up to their slot or
   `BANK_MAX` (0x800). Functions in a `PINNED` entry go to a fixed bank (`previous_key` beside the key code at
   0x180a1000); functions that call each other often (`GROUPS`) share a bank, because each call into another bank of
   the group swaps banks; the rest go first-fit, largest first.
4. **Link** (`build_stage20.link`) with a generated linker script that places each bank's sections at the bank's
   address plus its old length (rounded to 4), and extract each bank's bytes.
5. **Put** them in (`build_stage18.put_code`): check the tail is zeros, write, grow the bank's length in the table.
6. **Point the callers** at the new entry points: re-aimed `bl`s (`build_stage20.thumb_bl`) and menu rows'
   routine addresses (`MUSIC.MCG`). Before that, `build_stage23.old_targets` checks that each of them leads into the
   old code.

Stage 23's code: 12,406 bytes in 25 bank tails, deepest stack chain 956 bytes. Stage 24 places it anew (12,418 bytes
in 25 banks) and leaves out the banks that call the list box, whose ends hold `menu_box`.

## liststyle.c: code in a 0x1200 bank

`list_box` runs while the list control's data at 0x10116c is in use, so it cannot sit in a 0x1000 bank.
`build_stage24.place_list_box` compiles it on its own for each of `MUSIC.AP`, `BROWSER.AP`, `EBOOK.AP`, `VIDEO.AP`
and `PICTURE.AP`, with that program's addresses read from its copy of the list control:

| Define | Taken from | Meaning |
|---|---|---|
| `LIST_LEVEL_AT` | the literal at 0x18661400 | `g_dir_browser` |
| `UI_ENTRY` | the veneer at 0x186614e2 (decoded `movw`/`movt`, checked to be an `svc 6`) | the display driver's entry |
| `LIST_COUNTED` | the program's choice | counter inside an album or playlist (Music, Browser) |
| `TOP_TEXT` | the program's choice | the top level's name (Browser "Folders", eBook "eBook", none for Video and Picture); not set for Music, which names its top lists by the browse path |

It must compile to one section (`-fno-tree-switch-conversion` keeps the list-type choice from becoming a table in a
data section), is linked at the end of the control's own bank (0x18661514), checked to fit both the bank's file
slot and 0x3b8 (the group's largest stock bank), and the control's call at 0x18661380 is re-aimed at it. The music
version is 160 of the 164 bytes free; it reads each field of the browser state once (`list_level()` returns a
plain pointer for that reason). A stage that takes the new code out of `MUSIC.AP` with `take_out_code` stops at this bank
(only 0x1000-group banks may be longer than stock): it sets the bank back to 0x314 first and calls `place_list_box`
again afterwards.

The rule `list_box` applies:

| Level | Style | Top line |
|---|---|---|
| below the top, songs and no lists (an album, a playlist, a folder with only files), where counted | 0x6003 | the item counter |
| below the top otherwise (an artist's albums, a folder) | 0x6005 | the browser's name of the level |
| the top, with a name | 0x6005 | the list's name as a text id (Music: Playlists, All songs, Albums, Artists, Genres by the browse path) |
| the top, no name | 0x6000 | nothing |
