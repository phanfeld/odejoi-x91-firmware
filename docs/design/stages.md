# The stages

Each stage is one builder, `design/build_stageN.py`, which takes the previous stage's image and writes the next one
(stage 3 is built on stage 1; stage 2's typeface is part of it). The column "Code" marks stages that change program
code. The {doc}`../project/history` page lists what went onto the player and when.

| Stage | Changes | Files | Code |
|---|---|---|---|
| 1 | start-up picture and main menu (nine entries) | `LOGO.STY`, `MAINMENU.STY` | |
| 2 | new typeface (Ubuntu, 12 px, 1 bit) | `UNICODE.FON` | |
| 3 | typeface fixes; main menu down to five entries; Playlists first in the music menu; selected list row | `UNICODE.FON`, `CONFIG.BIN`, `MAINMENU.STY`, `MUSIC.MCG`, `COMMON.STY` | |
| 4 | small shared pictures: status icons, battery, scroll bar, list marks | `COMMON.STY` | |
| 5 | Playlists tile in the main menu; Playlists second while playing; playing screen pictures | `CONFIG`, `MAINMENU`, `MUSIC` | yes |
| 6 | Bluetooth search and shut-down animations, list icons, key lock, notices | `BT.STY`, `END.STY`, `COMMON.STY` | |
| 7 | screensaver: night meadow and a hopping blob animation | `COMMON.STY`, `BT.STY`, seven programs | yes |
| 8 | screensaver digits redrawn for the colour key; battery notice | `COMMON.STY` | |
| 9 | progress knob without flicker | `MUSIC.AP` | yes |
| 10 | volume pop-up; brightness sun restored | `COMMON.STY` | |
| 11 | playing screen as in the mock; Sound settings in Settings; lyrics off; "Favorites" | `MUSIC.AP`, `MUSIC.STY`, `SETTING.MCG`, `CONFIG.BIN`, `CONFIG.TXT` | yes |
| 12 | play/pause pictures swapped; track counter left | `MUSIC.STY` | |
| 13 | track counter at x=22 (never flashed on its own) | `MUSIC.STY` | |
| 14 | sideways copies of text backgrounds; tag title; status bar at once in Music | `MUSIC.*`, `COMMON.STY` | yes |
| 15 | main menu clock at the top left; screensaver key 0; the Berry theme | `MAINMENU.AP`, 15 programs, `COMMON.STY` | yes |
| 16 | eBook reader in landscape | `EBOOK.*` | yes |
| 17 | reader breaks lines between words | `EBOOK.AP` | yes |
| 18 | "Add to playlist" writes the `.m3u` files (first new code in C) | `MUSIC.AP`, `MUSIC.MCG`, `PLAYLIST.AP` | yes |
| 19 | missing glyphs; only `.m3u` playlists; rows of the built-in lists hidden | `UNICODE.FON`, `MUSIC.*` | yes |
| 20 | library follows the player's changes; Remove from Playlist; Previous restarts the song | `MUSIC.AP`, `MUSIC.MCG` | yes |
| 21 | playlist editing in the lists (add, delete, move); volume curve | `MUSIC.*`, `MENGINE.AP` | yes |
| 22 | "Searching..." screen; status bar at once everywhere; track counter digits; card marks; screensaver date | `PLAYLIST.STY`, 14 programs, `COMMON.STY`, `MUSIC.STY` | yes |
| 23 | the picker's page of five; Previous with the screen off | `MUSIC.AP` | yes |
| 24 | the lists' top line: menu names, list names, counter only in an album or playlist; short menu texts; status bar right after a list, its marks without a blink | `COMMON.STY`, five programs, ten style files, `MUSIC.MCG`, `SETTING.MCG`, 15 programs | yes |

## Stage notes

**1 to 4: pictures and type.** Every picture keeps its size and place. Stage 2's font: 512 glyphs replaced, wide
letters (`M`, `W`) use the two-byte row form, which the firmware reads correctly for ASCII. Stage 3's main menu is a
change of one list in `CONFIG.BIN` (9 bytes); the music menu's Playlists record was moved, not edited.

**5: the Playlists tile.** The first code change: `MAINMENU.AP` (the alarm entry starts music with code 0x40; grid
steps), `MUSIC.AP` (the root-menu routine skips the menu for 0x40, `music_playlists_tile.S`, checked on all 64 input
combinations).

**6 to 8: animations and the screensaver.** The screensaver clock turned out to be drawn by code, not by its layout;
stage 7 rewrote the start of the shared clock routine to draw one animation frame per 200 ms tick
(`clock_sprite.S`, in seven programs, 432 input combinations each). The colour key of the keyed draw (0xb5b6) then
explained damaged digits; stage 8 redrew them solid.

**9 to 13: the playing screen.** Stage 9 (`music_progress.S`) stopped the knob's flicker; stage 11 rewrote the whole
time-and-bar routine (`music_playing.S`, 1336 combinations) and laid out the screen after the mock; stages 12 and 13
corrected the play/pause pictures and moved the counter out of the status bar's corner.

**14: three causes found in code.** Scrolling text showed the stock background (the sideways copies); the title line
showed the file name (the tag reader overwrote the title, `music_title.S`); the status bar appeared half a second late
and its "black box" was the card mark (`music_headbar.S`; the playing screen got its own bar background with a note).

**15: clock and Berry.** The main menu clock moved to x=22 in the track counter's lettering; the screensaver key
became 0 in 15 programs, so the accent colon shows in every theme.

**16 and 17: the reader.** Landscape for the page only (`ebook_reader.S`, three stretches, 6400 combinations); stage
17 changed one mode number so lines end between words.

**18 to 23: playlists on the player.** New code in C (`design/playlist/`), placed in free bank room of `MUSIC.AP`.
18: add the playing song to an `.m3u` or a new playlist; the library builder reads the `.m3u` files at every run. 19:
glyphs, hide the built-in playlists. 20: write `M3U.LIB` in place, Remove from Playlist, correct engine messages, the
Previous key. 21: add from the song lists, delete songs and playlists, move songs, the volume table. 22: the small
items, among them the status bar at once in 14 more programs. 23: five rows per page, Previous with the screen off.

**24: the lists' top line.** Menus lost the counter and show their name; menu texts that were wrong or too long got
short English forms (title and row alike); file lists show the level's name, and the counter (in the
track counter's digits) only inside one album, playlist or album folder (`liststyle.c`, compiled per program into
five programs); the status bar is drawn right after a menu or list (`headbar_soon.S`, 15 programs). Lists and menus
drawn with the bar on (0x6000, 0x6002 to 0x6005) paint their background from row 16 and clear only the bar's middle
first (`list_box`, `menu_box.S` at the end of every bank with a list box call, the playlist picker); the battery,
card and Bluetooth marks got a black border out to the bar's edges, so the bar repaints rows 0 to 15 and the marks
no longer go out while a list is drawn.
