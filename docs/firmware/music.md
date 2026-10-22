# Music: program, engine and libraries

Three programs work together: `MUSIC.AP` (the screens), `MENGINE.AP` (the playback engine, a background process) and
`PLAYLIST.AP` (the library builder, run between them).

## Music root menu

- Each entry only returns a result code: All songs 0x860b, Albums 0x860c, Artists 0x860d, Genres 0x860e, Playlists
  0x8610, "Update list?" 0x861d. The routine at 0x18101288 shows the menu and turns the result into a list type
  (Playlists: type 8, sub-type 0x50).
- `MUSIC.MCG` has six versions of the root list: plain (list 0), with a card (1), while playing (55, 56 with "Now
  playing" on top) and with a bookmark (57, 58 with "Resume"). Since stage 24 all are titled "Music".
- Start code 0x40 (the main menu's Playlists tile, stage 5) skips the menu and continues as if Playlists was chosen
  (`patches/music_playlists_tile.S`).

## The lists

The list scene (0x18101150) calls the shared list control ({doc}`shared-code`) with the browse path
`g_browser_filepath` at 0x2003c0 (the SDK's `file_path_info_t`):

| Offset | Field |
|---|---|
| +0 | file source: 3 the library (song lists), 8 the `.m3u` playlists, others for folder browsing |
| +4 | location: disk, list layer, list type (+6: 0 All songs, 1 Albums, 2 Artists, 3 Genres, 0x50 M3U), … |

Rows the control adds on top (SDK `music_scene_listmenu.c`): "All songs" of an artist or genre, "Repeat All Songs"
in All songs. The Playlists list used to show the built-in lists (menu list 49) on top; stage 19 skips that set-up
(0x181011ce).

The browser functions (the SDK's `fsel_browser_*`): enter a level 0x1c0a2001 (current 0, son 1, parent 2), get rows
0x1c0a2023, select 0x1c0a2077, get location 0x1c0a20cb, scan init 0x1c8b1293 and scan 0x1c8b117f (every song below a
row). In the Playlists list the playlist one is in is at 0x200116 (0xffff at the top).

**List options.** The option key calls the list option callback (0x18161000, the SDK's
`list_scene_list_option_callback`). By the list's file source it opens an option menu (song lists: `MUSIC.MCG` lists
21 to 25; Playlists: lists 26 to 30 since stage 21; built-in playlists: 26 to 40) and hands the chosen row's result,
the path info and the list row to a result handler (song lists 0x181612ee, Playlists 0x18161290, built-in
0x18161238). Row results: 0x8601 play, 0x8605 to 0x8607 add to built-in list 1 to 3, 0x8608 remove, 0x8609 clear.
Since stage 21 the two handler calls (0x1816102e, 0x18161092) go to new code first.

## The playing screen

| What | Where | Notes |
|---|---|---|
| Full painter | 0x18081068 | runs when the repaint flag is set (entering the screen, after pop-ups); passes its own status-bar background (picture 45) since stage 14 |
| Refresh | in 0x18061000 | the screen's loop; updates the elapsed time only while byte 9 of 0x202fbc is 0 |
| Time and bar | 0x18061390 to 0x18061476 | rewritten in stage 11 (`music_playing.S`): bar at y=132, x from 8, 106 long, played part in the accent, the knob moves column by column |
| Cover | text box 1 of `MUSIC.STY` | area 110 x 90 at (9, 19), picture centred: a square cover shows at 90 x 90. Covers are read from MP1, MP2, MP3, WMA, APE and FLAC (table at 0x180814c4); the area is cleared with picture 71; no cover: the spectrum |
| Title, artist, album | tag reader 0x1c0e2000 (from 0x180c1000) | buffers of 92, 52, 52 bytes at 0x2001f4, 0x200250, 0x200284; stock overwrote the title with the file name; since stage 14 only when the tag has none (`music_title.S`) |
| Play mode | painter 0x180811fc | the shuffle picture replaces the repeat picture when shuffle is on; the second picture box only in folder play |
| Track counter | `MUSIC.STY` number box 0 | at x=22 in the status bar since stage 13; digit counts 0 since stage 22 |
| Lyrics | painters 0x18081068, 0x18061000 | text box 2; off since stage 11 (`MUSIC_LRC_SUPPORT` = 0) |
| Previous key | 0x180a1374 | calls the stock "previous" (0x1102b5) at 0x180a13b6 for a plain press; since stage 20 `previous_key` |
| Play key | 0x180a1328 | status 0 or 1 sends 0x316, 2 or 3 sends 0x315 |

Options of the playing screen: `MUSIC.MCG` lists 42 and 59 (Back to the main interface, Play mode, A-B repeat, Sound
settings, Add to playlist, Remove from Playlist, Delete, Bookmarks).

## Variables (MUSIC.AP)

| Address | Content |
|---|---|
| 0x200020 | file-system mount handle |
| 0x200024 | copy of the engine status |
| 0x20002c | total time of the song (ms) |
| 0x200030 | elapsed time (ms), the playing screen's copy |
| 0x200116 | the playlist the Playlists list is in |
| 0x200138, 0x20013c | app timer table pointer, count |
| 0x200140 | pointer to the program's message dispatcher |
| 0x200162 | the status bar's background argument |
| 0x200191 | last knob position (stage 9; a spare demo-mode byte) |
| 0x2001f4, 0x200250, 0x200284 | title, artist, album |
| 0x200324 | the playing song's path info: source byte, location (cluster +8, directory entry +12, folder chain +16) |
| 0x2003c0 | `g_browser_filepath`, the lists' browse path |
| 0x200668 | the status bar's parts table |
| 0x2006fc | `g_dir_browser`, the list control's browser state |
| 0x200714 | the list control's own state (+21: draw mode) |
| 0x10116c | the list control's list data (`listbox_private_t`) |

## Engine messages

The music program sends messages to its engine with 0x11034d `(data, reply, message)`. The X91 numbers them as the
SDK does up to 0x302 (file path) and then as the SDK plus 2 (dispatcher `MENGINE.AP` 0x1a051600, resident
pre-dispatch 0x110926):

| Message | Meaning |
|---|---|
| 0x302 | file path |
| 0x313 | play (`_play(PLAY_NORMAL)`) |
| 0x314 | stop |
| 0x315 | pause (`_stop(STOP_PAUSE)`); keeps the break point |
| 0x316 | resume (`_play(PLAY_RESUME)`) |
| 0x317 | seek: the file again from a break point given with the message (12 bytes: time in ms, file offset, extra) |
| 0x31a, 0x31b | next, previous (resident 0x110409, 0x1102b5) |
| 0x32b | play mode (repeat mode or shuffle flag) |
| 0x32d | file info (24 bytes; first word: total time) |
| 0x32e | status (four bytes from 0x200910: play status 0 stopped, 1 paused, 2 playing, 3 A-B, 4 winding; A-B status; winding; error); resident 0x110281 |
| 0x32f | play info (16 bytes from 0x200914: time in ms, then flags); its handler clears the "song changed" flags, so only the playing screen may ask |
| 0x332 | volume |

The engine's RAM starts at 0x200800 (bss 0x200910); its loop copies the decoder's playing time to 0x200914, which new
code reads directly while the screen is off (the playing screen's copy stands still then).

## Volume

`MENGINE.AP` 0x1a111780 (the SDK's `mengine_set_real_volume`) looks the step (0 to 31) up in 32 bytes at 0x1a11189e
and sends the value with decoder command 30; `MMM_MP.AL` keeps it and calls audio driver function 11 with it. Read as
0.375 dB per unit (191 = full), the stock table went from −54 dB in 3 dB steps at the bottom to about 1 dB steps at the
top (0, 47, 55, 63, 71, 79, 87, 95, 111, 119, 127, 132, 135 … 183, 191). Since stage 21: 2 dB per step from −60 dB at
step 1 (0, 31, 36, 42 … 186, 191). The only other copies of the table are in `VIDEO.AP`.

## The library builder (PLAYLIST.AP)

- Started by "create app" for program 20 with one parameter byte: disk bits (0xc0, or 0x40 for the card) and the entry
  mode: 2 from music ("Update list?"), 14 power-up, 15 after USB mode. The music program's exit routine (0x18341000)
  sends it.
- It always builds the five ordinary libraries and adds the playlists (`M3U.LIB`) for modes 14 and 15 only, as in the
  SDK's `plist_main.c`; since stage 18 for every run (0x180210b2: `movs r7, #0` → `#1`).
- When done it starts the next program by mode (0x18841814): mode 2 → music with parameter 13, 4/5/6 → video, picture,
  eBook; anything else → the main menu.
- It shows the "Searching..." screen (`PLAYLIST.STY`: background 0, spinner pictures 1 to 8 at (44, 37), text boxes at
  (9, 80) and (9, 98), bar track 10/13 and fill 9; restyled in stage 22).
- The library holds at most 4,000 songs; at most 50 playlists.

## Playlists (.m3u) as the firmware reads them

- A line ends at CR, so every line, the last one too, needs CR LF; a line without a final line end is skipped.
- `#` anywhere ends the line; `#` lines are comments.
- `a:\x\y.mp3` and `\x\y.mp3` are from the root; `x\y.mp3` is looked up from the root first, then from the playlist's
  folder; `..\` goes up. At most 63 characters per path part are kept.
- Names are one-byte text in the code page of the player's language (1252 for English); the sync writes ASCII only.
- Only MP3 files play from a playlist.

The firmware itself never writes `.m3u` files; since stage 18 new code does ({doc}`../code/new-code`).

## M3U.LIB

The `.m3u` library has the SDK's layout (`enhanced.h`), size 1,485,312 bytes (0x16aa00). The music program reads the
head on every open (0x1c0c2164), song records from sector 0x345 (0x1c0c23a6) and a playlist's index from sector
37 + 16 L (0x1c0c22d2); it keeps no copy, so a change written in place shows the next time the Playlists list opens.

| Where | Content |
|---|---|
| sector 0 | head: "M3U", number of playlists (+8), first record's sector (+10), item "ALLFILE" with the sectors of the sorted order and its inverse (+0x24, +0x26); from +0xa0 the number of songs, the songs per playlist (u16[50]), the Audible files per playlist |
| sector 1 on | playlist records of 256 bytes in folder order: name (UTF-16, without ".m3u"), "M3U", flag, directory entry of the `.m3u` (cluster +0x9c, offset +0xa0), previous and next record (+0xa4, +0xa6), folder chain (+0xa8) |
| right behind | the sorted order (u16 record numbers) and its inverse, one sector each |
| 0x4a00 | per playlist 0x2000 bytes: its songs as u16 song numbers, in the order of the `.m3u` |
| 0x68a00 | song records of 256 bytes: file name (one-byte text, at most 54 bytes), the playlists using the song (+0x38, 50 bytes, 0xff free), "MP3" (+0x94), ID3 flag, flag (+0x99), track (+0x9a), cluster and offset (+0x9c, +0xa0), folder chain (73 bytes: nine pairs of cluster and offset, depth at byte 72) |
| 0x162a00 | per song 8 bytes: cluster and offset of its directory entry |

Records and index entries behind the counts are left over from older builds.

The three built-in playlists (`USERPL1.PL` to `USERPL3.PL`, "Favorites", "Playlist 2", "Playlist 3") live in the
settings area, which a firmware write resets; they are hidden since stage 19.
