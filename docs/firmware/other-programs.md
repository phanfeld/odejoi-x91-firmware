# Other programs

## Main menu (MAINMENU.AP)

- One full-screen picture per program id with that tile highlighted (`MAINMENU.STY`); the list of program ids is
  entry 1 of `CONFIG.BIN`. Stage 3 reduced the menu from nine entries to five, stage 5 to six (Music, Playlists,
  Folder, Bluetooth, eBook, Settings).
- Menu entry 1 is special-cased (0x110144): stock it started program 9 (tools) with start code 18, the alarm; since
  stage 5 it starts program 0 (music) with start code 0x40, the Playlists tile. Its label is string 0 of
  `MAINMENU.STY` (the music program's word for Playlists in each of the 28 languages).
- Up and down step through a two-row grid since stage 5 (stock: three rows; three constants).
- The status bar clock is drawn only here (see {doc}`shared-code`); its x is the byte at 0x18c21c0e (22 since stage
  15).
- The main menu's only list is its option menu (style 0x6006).

## Settings (SETTING.AP)

- `SETTING.MCG` defines 311 items in its `ACTMCGGM01` block; 100 are in use. The inactive ones include Sound
  settings, Fullsound, the equaliser and its presets, Volume limit, play mode, the screensaver modes album art, screen
  off and demo, the theme colours, key tone and PC connection. Stage 11 made Sound settings (Equalizer, Volume limit)
  the third entry of the root menu.
- The firmware has its own theme setting (one settings byte, 0 to 4: Blue, Green, Grey, Pink, Red). The code is still
  there (0x1806108c reports it, routines from 0x180612c4 store it and reload the style files, tables of file names
  `setting.sty`/`setgreen.sty`/… and `common.sty`/`cm_green.sty`/…), but no menu entry points to it and the image
  holds only the first file of each table. Graphite themes are therefore separate images.
- Screensaver menu: list 12 (None, Digital clock).

## eBook reader (EBOOK.AP)

- Scene loop 0x180e1014: switches the status bar off, then loops: one step of the background page count (0x110094),
  paint (0x180e10dc), messages. Page turns (0x180c1348 forward, 0x180c141c back) only change the page number and set
  flags.
- Paint: the strip with page number and bar (0x180e148c), the page background, then the layout routine 0x180e11f4,
  which reads the file, measures each line with driver function 24 and hands every line to 0x180e11ac, which draws it
  with function 21.
- Layout numbers are set when a book opens (0x180c11fc, block at 0x110e00: lines per page byte 566, width byte 567;
  the measuring mode at 0x180c1218). Stock 9 lines of 128 pixels; since stage 16 7 lines of 152 pixels in landscape,
  since stage 17 mode 2 (end lines between words).
- At the start of every line the decoder skips all line ends (0x180e151c), so blank lines do not show; a row is
  measured over at most 255 bytes; a line end ends the row and is counted into it.
- Flags: 0x20004a full repaint, 0x200051 page, 0x200052 page number, 0x200054 page count running, 0x200055 mark. Page
  number 0x200020, pages 0x200024, setting block 0x2001a0 (byte 2 automatic turning, 169 font option, 170 page colour:
  five colours, white text on colours 1 and 4).
- Page indexes and bookmarks carry a signature (stock 0x55aaaa55, five places); it is changed whenever the page layout
  changes (0x55aaaa57 since stage 17), so old indexes are rebuilt.
- Text: one-byte text and UTF-16 with a byte-order mark work; UTF-8 (encoding byte 124) is sized by the driver, but
  whether the reader ever sets it is not known.
- Since stage 16 the paint routine turns the screen to landscape (function 30) before drawing and back after, so
  nothing outside the page sees a turned screen.

## Folder view (BROWSER.AP)

The folder view is the Browser program; its lists are the shared list control over folders (the top level is the
disk's root, named "ROOT" by the browser). Its option menus are the "entry menus" (no play, now playing, last played).
Since stage 24 it shows the folder's name in the status bar, "Folders" at the top, and the item counter inside a
folder that holds only files.

## Bluetooth (BT.AP, BTENGINE.AP)

The Bluetooth menu (`BT.MCG`: on/off, search, device list, the device sub-menus) and the search animation
(`BT.STY`, stage 6). Bluetooth remote commands (AVRCP) go through the engine.

## Programs never changed

| Program | Why |
|---|---|
| `CONFIG.AP` | the configuration program (number 21); recovery depends on it |
| `UDISK.AP` | USB drive mode; the only program with the upgrade-mode marker |
| `FWUPDATE.AP` | the on-device updater (no menu points to it on the X91) |

The drivers and the boot record are never changed either. Shared code in these programs keeps its stock behaviour
(for example the screensaver key and the status bar delay).

## Programs not on the main menu

Video, Pictures, FM radio, Recorder, Pedometer, Study, Tools and Alarm are still in the image but not on the main menu
(Tools is a row of the Settings menu). Stage 24 shortened their long menu titles; otherwise they are stock apart from
the shared code. A new program (a game, say) would have to replace one of them, as the image has no free space.
