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
  (`STACK_MAX`; the stage 23 code needs 956, the stage 25 code 984, the stage 26 code 1,000, the stage 27 code 1,008).
- **Few calls between the new code's banks.** Every call into another bank of the 0x1000 group, and every return
  from it, loads a bank. Functions that run for every row or every character share one bank (the search's `HOT`
  group in `build_stage25.py`; the builder stops if they are spread). Since stage 26 the code that only "Add songs"
  runs sits in banks of the 0x1a00 group, whose window lies above the 0x1000 group's: a call between the two loads no
  bank twice. Since stage 27 so do the name screen, "New playlist", "Rename", "Move song" and "Delete".
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
| `browse.c` | the list options: "Add to playlist" in the song lists (a song, or every song of an album, artist or genre), "Delete" (a song in a playlist, or a playlist's file), "Move song", "Add songs" (stage 26: songs of the library by the search, to a playlist), "New playlist" and "Rename" (stage 27: below); "Search" goes on to `search.c` | `list_option`, `m3u_option` (the result-handler calls at 0x1816102e, 0x18161092) |
| `search.h`, `search.c` | the search with a T9 keypad (stage 25, below), over the list's level or (stage 26) over the library's songs read from `MUSIC.LIB`; the screen's layout and drawing (`fill`, `text`, `keypad_key`) shared with the name screen | `search_list` (from `list_option` and `m3u_option` for 0x8606), `search_songs` and `songs_get` (from `add_songs`) |
| `name.h`, `name.c` | the name screen (stage 27): a playlist's name typed on the keypad | `name_entry` (from `new_playlist` and `rename_playlist`) |
| `keys.c` | the Previous key: after 3 s of a song restart it (engine seek 0x317 with break point 0 between pause and resume), else the previous song; with the screen off by the engine's own time | `previous_key` (0x180a13b6), `standby_previous` (0x18b41a6e) |
| `liststyle.c` | the file lists' top line: the counter inside one album or playlist, else the level's name; on a full redraw it first clears the status bar's middle | `list_box` (0x18661380, in five programs) |
| `host/` | `mock.c`, `mock.h`, `test.c`: the test on the computer; `render.py`: pictures of the search screen from the test's draw log | |
| `stage18/`, `stage20/`, `stage21/`, `stage23/`, `stage24/`, `stage25/`, `stage26/` | frozen copies of the sources as each stage shipped them | |

`fw.h` in brief:

| Group | Names |
|---|---|
| File system (`svc 17`) | `vfs(a, b, c, cmd)`; `place_t` (folder chain and directory entry), `VFS_*` commands |
| Display (`svc 6`) | `ui(a, b, c, fn)`; `strdesc_t`, `listbox_t`, `style_t`, `dialog_t`; style ids `STYLE_PICKER` 0x6004, `STYLE_DIR` 0x6000, `STYLE_COUNTED` 0x6003, `STYLE_NAMED` 0x6005; for a screen of its own `UI_DC_GET`, `UI_CLEAR` (fill a `region_t`), `UI_PEN`, `UI_BACKGD`, `UI_STRING` and the string modes (`DRAW_COLOUR`, `ALIGN_*`, `LONG_CUT`, `LONG_DOTS`); `UI_STR_WIDTH` (stage 27, a text's width) |
| Keys and results | `get_gui_msg`, `get_app_msg`, `app_dispatch`, `key_mapping`; `EV_*` events, `RESULT_*` codes (`RESULT_SEARCH` 0x8606, `RESULT_ADD_SONGS` 0x8607, `RESULT_NEW_LIST` 0x8605, `RESULT_RENAME` 0x860f); the keys themselves, `KEY_*`, and their event bits `KT_*`; `now_ms` (the system's millisecond counter, stage 27) |
| List control | `dir_control` (its state, `dirctl_t`, 0x200714), `menu_rows` (the menu rows on top, 0x20070a), `dir_select` (its Select, 0x18681200 with 0x2704), `timer_tag` (0x20013d) |
| Messages | `message_box`, `string_format`, `dialog`, `dialog_text`; text ids `S_*` of `MUSIC.STY` and `COMMON.STY` (`S_NAME_TAKEN` 6 since stage 27) |
| Engine | `engine_status` (0x32e), `engine_pause` (0x315), `engine_resume` (0x316), `engine_seek` (0x317), `engine_stop`, `previous_song`, `elapsed_ms`, `engine_time` (0x200914), `music_playing` |
| Browser | `browser_enter_dir`, `browser_get_items`, `browser_select`, `browser_get_location`, `browser_scan_init`, `browser_scan`, `browse_path` (0x2003c0), `m3u_list` (0x200116), `list_level` (`g_dir_browser`), the stock result handlers |
| Per program | `LIST_LEVEL_AT` and `UI_ENTRY` default to `MUSIC.AP`'s addresses; `liststyle.c` is compiled with another program's |

## Host test

`design/playlist/host/` runs all of it on the computer against a simulated player:

- a simulated disk with folder positions, `cd back` onto the folder just left, long names, byte-wise reads and
  writes, a refusal of a second open file;
- a simulated library: after every change the test's `M3U.LIB` is compared with one built from scratch the builder's
  way, and the library functions also run on the player's own copy (`x91_dump/device_files/2026-10-21/M3U.LIB`);
- a simulated browser (song lists, albums, the Playlists list, and for the search levels of names in every
  encoding the browser hands out), questions, the list box (which refuses more rows than the style's lines), the
  engine (status, pause, resume, seek, time) and the list levels for `list_box`;
- for the search (stage 25): the keys as the key driver sends them (key and event bits), stretches without keys in
  which the search goes on, the volume pop-up and system messages; a model of the texts on the screen and the fills
  that cover them, and of the pixels: a text counts as painting its whole region in its background colour, and
  whenever the search waits for a key the screen below the status bar must be the design's layout, both with the
  texts and by the fills alone (so no text reaches out of its place or is needed to complete a shape); the list
  control's state and its Select, which refuses a state that does not agree with itself;
  rows read per call as the library reads them (a name cut to its buffer, two zeros); for "Add songs" a `MUSIC.LIB`
  built from the simulated disk's songs as the library builder lays it out, and the screen as it is at marked
  moments (`on_snapshot`), to check what the search shows when it comes back after an add; for the name screen
  (stage 27) keys made from the text to type (`type_keys`: the presses of each letter's key, a second's wait between
  two letters of one key), a millisecond clock that moves 10 ms per wait for a tick, the display driver's text width
  with the typeface's widths (asked only with the type the driver reads UTF-16 by), the screen's layout checked as the search's (the name's line with one caret or one marked
  character, the row of the key's characters, the space bars of 0), a create that refuses a name that is there, and a
  disk that can be made full after a number of writes. With `SEARCH_SCREENS=FILE`
  the test writes every drawing call and marked moments to FILE; `host/render.py IMAGE FILE DIR` draws them with the
  player's own typeface.

Deliberately broken versions of the code (wrong copy direction, users not renumbered, order kept, no question,
a batch stopping after one song, a missing layer check, …; for the search a letter on the wrong key, no skipping of
signs, matches inside words, marks kept after Return, rows not unmarked, the list not moved, the timer tag kept, Up
and Down not crossing between keypad and results, a text on the wrong background or reaching past its key, a gap row
not painted again, cut corners, …; for "Add songs" the keys or the chosen line not kept, the screen waiting for the
search, the chosen song not shown or not taken at once, or kept after another key, the list not recounted, songs in
the file's order
instead of All songs', names not cut as the list cuts them, no folder chain, an unchecked head, the wrong playlist,
no pause while writing, one song only, a system message's result lost, …; for the name screen the underline or the
row below the mark not painted again, the character being typed without its fill or in the keys' case, no trimming
of spaces, a name of spaces taken, a held Return deleting one character, a long name drawn from its start, Menu's
order; for "New playlist" and "Rename" a taken name made anyway, the old file kept or removed after a failed copy, a
failed copy left behind, a copy that does not move on or reads past the end, the record's old place or name kept, a
change of the letter case taken for another playlist, the same name renamed, no pause, the list not grown or not on
the new playlist, …) all fail it. Compile and run it by hand:

```bash
cd design/playlist
cc -std=c99 -Wall -Wextra -Werror -DHOST -g -fsanitize=address,undefined -I . -o host_test \
   host/test.c host/mock.c playlist.c library.c keys.c browse.c liststyle.c search.c name.c
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
in 25 banks) and leaves out the banks that call the list box, whose ends hold `menu_box`. Stage 25 takes the playlist
code out of its banks itself, leaving the three `menu_box` banks and the list control's bank as stage 24 left them
(found by their list box calls into their own ends, and checked unchanged afterwards), and places it anew with the
search: 16,516 bytes in 30 bank tails in Amber (16,504 in Berry; the theme's colours are in the code), deepest
stack chain 984 bytes. Stage 26 (`build_stage26.py`) uses stage 25's `replace_code` with two changes:

- **The 0x1a00 group.** The 0x1000 group's free tails (17,784 bytes) no longer hold all the code (about 18,200
  bytes). The groups only "Add songs" runs (`FAR_GROUPS`: reading `MUSIC.LIB` rows, the rest of the `MUSIC.LIB`
  code, the add itself) go into free tails of 0x1a00-group banks, each bank up to 0x5f0 bytes, that group's longest
  stock bank, so the code stays inside RAM the program already loads banks into. That group runs at 0x101a00 and
  keeps its data below it (0x101800 to 0x1019ff); no stock code of `MUSIC.AP` keeps data in 0x101a00 to 0x101fff
  (the only constants in that range are ids in a table of bank 0x183c1000), and no instruction of the group
  addresses its own tail. A call from the 0x1000 group into it, or back, reloads nothing.
- **The stack measured right.** The older builders' function pattern took `static inline
  __attribute__((always_inline)) int f(` for a function named `__attribute__`; `build_stage26.stack_depth` knows such
  helpers by their names (no frame of their own, their calls counted for their callers).

Stage 26: 18,394 bytes in 35 banks in Amber (18,380 in 34 in Berry), of them 1,690 in three 0x1a00-group banks;
deepest stack chain 1,000 bytes.

Stage 27 (`build_stage27.py`) takes stage 26's code out of its three 0x1a00-group banks first (`take_out_far`;
`replace_code` takes it out of the 0x1000 group's only) and places everything anew. The 0x1000 group's tails would
hold 1.9 KB more in all, but in pieces too small for `remove_line`, so "Move song" (but for `move_page`, which
`list_draw` calls through a pointer) and "Delete" went into the 0x1a00 group too, with the name screen, "New
playlist" and "Rename", in groups that each fit one tail (up to 920 bytes), placed largest first. 22,798 bytes in 45
banks in Berry, of them 7,802 in 17 banks of the 0x1a00 group; deepest stack chain 1,008 bytes (the search under "Add
songs" or "New playlist"; `m3u_option` keeps the playlist's record number in its frame now).

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
plain pointer for that reason). `take_out_code` stops at this bank (only 0x1000-group banks may be longer than
stock); stage 25 therefore takes the playlist code out with its own `replace_code`, which keeps this bank and the
`menu_box` banks.

The rule `list_box` applies:

| Level | Style | Top line |
|---|---|---|
| below the top, songs and no lists (an album, a playlist, a folder with only files), where counted | 0x6003 | the item counter |
| below the top otherwise (an artist's albums, a folder) | 0x6005 | the browser's name of the level |
| the top, with a name | 0x6005 | the list's name as a text id (Music: Playlists, All songs, Albums, Artists, Genres by the browse path) |
| the top, no name | 0x6000 | nothing |

## search.c: the search (stage 25)

"Search" is the last row of the music lists' options (`MUSIC.MCG` lists 21 to 30). Its routine is the stock one of
the hidden built-in "Playlist 2" row and returns 0x8606; `list_option` and `m3u_option` hand that to `search_list`,
which works on whatever level the list shows (`list_level()`: lists below, songs).

**The screen** is drawn by the code itself, with the display driver's fill and string functions and the theme's
colours (compiled in: `build_stage25.py` passes `-DCOL_BG` … `-DCOL_ON_ACCENT` from `build_stage1.T`). Rows of 16
pixels: the status bar (switched on, its middle cleared, "Search" where the menus have their title), the query line
(the letters the first match spells, or the digits typed while nothing is found yet; the number of matches, or
"place/number" on the results; an ellipsis while the search goes on), four result lines, and the keypad at the bottom
in four rows of three 41 x 15 keys, one pixel apart (digit in the text colour, letters in the second text colour, the
chosen key in the accent). Texts are drawn with fill mode 1: the driver paints a strip as wide as the text and 16 rows
high in the background colour, then the letters (row 15 stays empty for Latin letters). Each text lies on a fill of
its background colour, and the one-pixel rows its strip reaches are painted again after it: the row above a key (its
texts sit one row higher, to be centred in 15 rows), the row below the chosen result line, the query's underline.
Stage 25 as first flashed used mode 3, "only the dots", which leaves the strip as the previous string left it: stale
letters showed above the keys, the underline broke under the typed letters, and the keys' edges looked uneven. The
scrolling timer of the list's chosen row would draw over the screen: while it shows, the program's timer
tag (0x20013d) is 0x8e, so only timers tagged 0xff fire, and the old tag and colours come back afterwards.

**Keys** are read raw (the menu key table maps only Up and Down): Up, Down, Previous, Next move on the keypad, Play
types; Up from the keypad's top row, OK or Menu go to the results; Down below the last result goes back to the top
row; Return deletes a key, held all, and leaves with nothing typed. Other keys go through the menu key mapping and
`message_box` (the volume pop-up, then the screen again); a system message ends the search with its result.

**Matching.** A key stands for its digit and its letters (2 abc … 7 pqrs, 8 tuv, 9 wxyz). A row matches when the keys
spell the beginning of one of its words, character by character, skipping spaces and signs (so they also run on
into the next word). Names come as the list's browser gives them: UTF-16 with FF FE, UTF-8 with its mark, or one-byte
text in code page 1252 (its letters at 0x80 to 0x9f included). Latin-1 and Latin Extended-A letters count as their
base letter: both blocks run through the alphabet, so `key_of` needs only a few ranges per key.

**Searching without waiting.** A bit per row (4000 rows, the library's limit; 500 bytes of the screen's state) marks
the rows that may still match. A further key keeps the marks (a longer query can only match fewer rows) and tests
the marked rows again from the top; Return marks all rows. Between key messages `scan` tests up to 12 marked rows,
reading three per browser call (each call opens the library, so one row per call would cost three times as much);
after each such stretch `scanned` draws the matches it found on the result lines (reading those rows again, at most
four per key) and the first one's letters on the query line; a key restarts the search at once. The row of the m-th
match is found by counting marks.

**A chosen row** is row `r` of the browser, `r + menu_rows()` of the list control. `open_row` puts the control's
state on it (the page moved so the row is the third line if it was not shown), then does what Select does: a row with
lists below goes through the control's own Select (0x18681200 with 0x2704: keeps the level's place for Back, enters
the row, sets the control to read and draw the new level); a song goes through the stock "Play" option of that row
(0x8601), so it plays and the list stands on it when the playing screen is left.

**Stack.** The screen's state is one frame of about 630 bytes, the row names of a stretch of the search another 156
in `scan`. Nothing is drawn from inside `scan`; a key or system message is held in `poll`'s frame, not in the
state; the whole screen is drawn from `run`, not from inside the key handling; and `m3u_option` hands the search over
before its own frame. Since stage 26 the deepest chain is "Add songs" with the search: 1,000 bytes; 1,008 since
stage 27.

## "Add songs" (stage 26)

"Add songs" is a row of the Playlists options (`MUSIC.MCG` lists 26 to 30, in front of "Search"; `MUSIC.STY` text 30;
the stock routine of the hidden built-in "Playlist 3" row, which returns 0x8607). Inside a playlist it adds to that
playlist; in the list of playlists, to the playlist the options were opened on. As for "Delete" and "Move song", the
list's rows must agree with `M3U.LIB`, else the stock "File failed to open" shows.

`add_songs` (`browse.c`) opens the search over the library's songs (`search_songs`): All songs as the list shows them,
read from the library builder's `MUSIC.LIB` ({doc}`../firmware/music`) instead of through the browser, which is set
up for the Playlists list. A chosen song ends the screen; `add_found` takes its location from `MUSIC.LIB`
(`songs_get`), pauses a playing song and adds it as "Add to playlist" does (`add_one`: a line at the end of the
`.m3u`, a record in `M3U.LIB`), and the stock message names the song and the playlist ("already added" when it was
in it). Then the search opens again with the same keys and the same line chosen (`search_keep_t`), and finds the
songs again: the add needs 700 bytes of stack and the screen's state 630, so the screen cannot stay open while a
song is added. The screen comes back at once: the chosen song's row is kept (`want`, `want_row`), so its line shows
and Play takes it before the search has found it again (`row_of`), and the query line shows the letters it spells
(`kept_letters`); the other lines and the count come as the songs are found, and a further key drops the kept song.
Stage 26 as first flashed drew at once without it (the digits typed, an ellipsis, an empty chosen line for a
moment); its first rebuild searched until the four lines were found before drawing, which with fewer matches meant
the whole library: about 5 s without a screen or keys.

Return leaves with a "redraw" (0x8014). The list control then reads the rows of its page again but keeps its number
of rows: it counts the level's rows only when it enters one (0x187012bc, run when the control's byte +22 is 1, which
also takes the list's place from the level's history). So after songs were added `list_grown` sets the control's
number of rows from the browser's level and moves the last row shown with it, and the new songs show at once; up to
the third build they showed only after the list was left and entered again (playing a song from it does that).

## Naming playlists (stage 27)

"New playlist" and "Rename" are rows of the Playlists options (`MUSIC.MCG` lists 26 to 30, behind "Add songs";
`MUSIC.STY` texts 13 and 7). Their routines are stock ones that return a code no Playlists row returned before:
0x181613df, the song lists' "Add to playlist" (0x8605), and 0x18181201, a routine of the music menu's bank that no
menu row uses (0x860f, the SDK's `RESULT_ENTER_FAVOR_LIST`). The option menu leaves with any code that is not one of
its own (`RESULT_MENU_*`, redraw) and hands it to the result handler, where `m3u_option` takes them.

**The name screen** (`name.c`, `name_entry`) is the search's screen with the name on the query line: the name in the
text colour, the character being typed on a fill in the accent, else a caret, and the line under it in the accent;
below, the chosen key's characters in cells of 12 pixels (the one being typed in the accent) and the letter case
right-aligned; the keypad with the name screen's labels (`keypad_key` with `KEYS_NAME`: 1 with its first signs, 0
with a space bar drawn by fills, letters always small). A name longer than the line shows its end: the first
character shown is the first from which the rest fits 113 pixels, measured by the display driver's own width
function (function 23, `UI_STR_WIDTH`, with the type `TEXT_UNICODE`, 0x7f: with the drawing's 0x7d it reads one byte
per character, and stage 27 as first flashed measured every name as "ÿþ" and its first letter, about 20 pixels); the
mark of the character being typed is as wide as the driver says. The texts measured are built in a buffer that holds
zeros behind them.

**Typing.** A key's characters are a row: its letters (or the signs `- . & ' ( ) !`, or the space) and then its digit;
their number per key is packed in one constant (`CYCLES`), since a table would be data. Play types the first; Play on
the same key within `TAP_MS` (1,000 ms of the system's millisecond counter, svc 15 function 28, which the program's
app timers read) takes the next in its place; another key, a move, or a second in which no message comes (the screen's
loop checks the time whenever it would wait for a tick) keeps it. Held (`KT_LONG`), Play types the digit. The letter
case of a letter is set when its first press types it: "Abc" gives a capital at the start and after a space; Menu
switches the case and gives it to a letter being typed. OK takes the name without spaces at its ends; a name of
spaces stays on the screen. The screen's state is a frame of about 100 bytes; as the search, it holds the program's
timers by its tag and gives the display's colours back.

**New playlist** (`new_playlist`, `make_playlist`): a name that one of the root's `.m3u` files has, the letter case
aside (`find_named`, by the name the Playlists list shows), or that any file has (an open by that name succeeds),
brings "\"name\" already exists" (text 6) and the screen again with the name. Otherwise `<name>.m3u` is made empty
(the file system's create refuses an existing name, so it is never asked to), found again by its name for its place,
and gets a record (`lib_add_list`, at the end of the sorted order); without a record the file goes again and "File
failed to open" shows. Then "Add songs" runs for it (`add_songs(index, list, 1)`), and in the list of playlists the
control's number of rows grows and it stands on the new playlist, the last row (`stand_on`, the fields `open_row` and
the SDK's delete update set). `new_playlist` returns before the search's frame comes: the name and the screen are
gone by then.

**Rename** (`rename_playlist`, `rename_file`, `move_file`, `copy_to`, `lib_set_list`): the playlist as "Add songs"
finds it (`add_target`), its name from its record. An unchanged name does nothing; another playlist's name brings the
message and the screen again. The file system's rename (command 20) is used by no program of the stock firmware, so
it is not relied on. `copy_to` makes the new file and copies the old one into it 192 bytes at a time, each time
standing on the old file by walking the root folder (`find_playlist_at`, as "Delete" does) and opening the new one by
its name, one file open at a time; a failed copy removes the new file. Then the old file goes (`remove_here`), the
new one is found by name, and `lib_set_list` writes its place and name into the playlist's record, so its number and
songs stay (and a playlist the engine plays from plays on). A change of the letter case alone renames twice, by the
name with a "~" in front first: the file system finds the old file under the new name, so the copy could not be made.
A playing song is paused around the file work and the file system's place kept, as everywhere.

**Stack.** `rename_playlist` holds the two names, the playlist's place and the file system's place (336 bytes); the
second name doubles as `rename_file`'s "~" name, and `move_file` writes the new place over the old one. With a copy
buffer of 256 bytes the rename's chain, with `find_playlist_at` under `copy_to`, needed 1,016 bytes; with 192 it stays
below the search's 1,008.

