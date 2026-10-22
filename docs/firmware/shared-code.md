# Shared interface code

The SDK's interface code is linked into every program with a screen. The addresses below are `MUSIC.AP`'s; in other
programs the same routine is often at the same address, but always with that program's variables and resident stubs.
To change one routine everywhere, a builder finds it in each program by its bytes (calls and literals masked) and
re-aims the calls ({doc}`../code/patches`).

## Status bar

| Routine | `MUSIC.AP` | Role |
|---|---|---|
| on/off | 0x18c21e74 | `(mode, program icon, background picture)`; fills the parts table and (re)starts the bar's timer |
| draw | 0x18c21a20 | draws the parts (r0 = 0: every part) |
| timer routine | 0x18dc1e1c | draws the whole bar on its first tick after "on", changed parts afterwards; every 500 ms |
| Bluetooth state | 0x18c21d24 to 0x18c21de4 | picks the Bluetooth frame from a state byte (bit 0 on, bits 0 and 1 connected, bit 2 blinking) |

The on/off routine sits at 0x18c21e74 (Alarm, Browser, eBook, Music, Picture, Tools, Video), 0x18c21e54 (Main menu,
Pedometer, Radio, Record, Setting, Study), 0x18c21a20 (Playlist, and Config and Firmware update, never modified) or
0x18c21a00 (Bluetooth). Its draw routine is at 0x18c21a00 in most programs (0x18c21aac in Bluetooth and Playlist).

**Parts.** The on routine fills a table of seven layout-record numbers (at 0x200668 in `MUSIC.AP`), 0xffff = part
not shown: bar background (off), program icon (off in this build; the SDK feature is picture box 0, pictures 174 to
184), clock (1), battery (0x1001 = picture box 1 of `COMMON.STY`), one unused part, card mark (0x1002), Bluetooth
mark (0x1003). Each part goes through driver function 37: its black pixels are replaced by the pixels of the bar's
background picture at that place (the picture named when the bar was switched on; default 249, black, 160 x 20).
The draw routine never paints the whole background, only the parts' rectangles.

**Clock.** The time is drawn only while the main menu is the running program (program 19): `hh:mm` digit by digit
through function 39 (key 0x7bcf) with pictures 135 to 145 of `COMMON.STY`, at a position fixed in the code (stock
x=45, y=1; `MAINMENU.AP` 0x18c21c0e, x=22 since stage 15), plus picture box 4 for AM/PM.

**Timing.**

- Stock: "on" only restarts the 500 ms timer, so battery and marks appear half a second after every full repaint.
- Stage 14 (music program), stage 22 (14 more programs): "on" also draws the bar at once
  (`design/patches/music_headbar.S`).
- Menus and lists switch the bar on and then paint their full-screen background over it, so there the bar still came
  back with the timer. Stage 24 (`design/patches/headbar_soon.S`, the same 15 programs): "on" also moves the timer's
  next firing to "now", so the bar is drawn as soon as the program waits for keys.

## App timers

Every program keeps its own SDK app timers (`MUSIC.AP` bank 0x18a21a00). The timer table pointer is at 0x200138 and
the count at 0x20013c; entries are 16 bytes:

| Offset | Field |
|---|---|
| +0 | state: 0 running, 1 stopped, 2 free |
| +1 | type |
| +2 | period in ms |
| +4, +5 | |
| +8 | next firing time (ms) |
| +12 | routine |

Routines: create 0x18a21a48 (wrapper 0x18a21bc0), stop 0x18a21acc, modify (new period, next = now + period)
0x18a21af8, kill 0x18a21b3c, restart (state 0, next = now + period; returns 1, or 0 for no such timer) 0x18a21b80.
The time comes from system call 28 (`svc 15`). Timers fire when the program looks at them, which is when it waits for
keys; a routine never interrupts drawing.

## List control (gui_directory)

The file lists (music lists, the folder view, eBook, Video and Picture) are drawn by the SDK's directory control,
`gui_directory(style, path_info, dir_com)` at 0x18661200 in `MUSIC.AP`, `BROWSER.AP`, `EBOOK.AP`, `VIDEO.AP` and
`PICTURE.AP`. Each program calls it once, with style 0x6000.

- It reads the style's lines per page (function 14), then loops: on a full redraw it switches the status bar on
  (0x1866132a), prepares the style (function 35), fills the list data at 0x10116c (0x18ba19f4), and draws the list
  box (0x18661380: `bl` to the display veneer 0x186614e2 with the style at sp+12, the data, the draw mode from
  0x200729 and 8). Since stage 24 that call goes to `list_box` ({doc}`../code/new-code`).
- Its browser state (`g_dir_browser`, the SDK's `dir_brow_t`): lists below this level (u16), songs or files at this
  level (u16), name length, layer (0 = top), name buffer. At 0x2006fc in `MUSIC.AP`, 0x200440 in `BROWSER.AP`,
  0x2006a8 in `EBOOK.AP`, 0x200480 in `VIDEO.AP`, 0x2003c4 in `PICTURE.AP`.
- The level's name, which the control puts into the list title: the library writes an empty name at the top level
  and the chosen item's name below it (the artist, the genre); folder browsing writes "ROOT" at the disk's top and
  otherwise the folder's own name.
- The option key calls a list option callback (`MUSIC.AP` 0x18161000); when the result handler returns 0x8019 or
  0x801a, the control takes the row out and reads itself again.
- The control's data area 0x101000 to 0x1011ff (0x1200 bank group) is overwritten if code called from it loads a
  0x1000 bank.

## Menus (gui_menulist)

Menus are the SDK's menu list code (bank 0x18641000 in each program). It reads the menu tree from the program's
`.MCG`, puts the list's title text into the list title (`g_menu_title.str_id`) and the rows' texts and icons into the
list data, and draws with the style it was given (0x6002 menus, 0x6004 sub-menus with a title line, 0x6006 option
menus). For styles 0x6002 and 0x6004 it switches the status bar on before a full redraw (0x18641130).

## Key filter with the screen off

Every program's shared key filter (`MUSIC.AP` 0x18b41a00, run inside the message call) acts while byte 8 of
0x202fbc is 2 (screen off). It handles the keys itself and returns 0:

| Key | Routine | What it does |
|---|---|---|
| Previous | 0x18da1cec(0) | sends 0x31b to the engine (process 23) when bytes 0 and 1 of 0x202fbc are both 1: the background engine is the music engine and it runs (a song playing or paused) |
| Next | 0x18da1cec(1) | sends 0x31a likewise |
| Play | 0x18b41bf4 | |
| Volume | 0x18da1c8c | one step up or down in byte 6 of 0x202fbc or byte 17 of the settings block at *0x202f88; 0x18b61a00 stores it at 0x202fbc+6/+7 and sends 0x332 to the engine (0x40d to the radio engine), and 0x331c to process 29 while bit 1 of 0x202fbc+21 is set (Bluetooth) |

The screen-on volume screen is 0x18d21a00. Since stage 23 the music program's filter sends Previous to
`standby_previous` (0x18b41a6e).

## Screensaver

Shared code in banks 0x18cc1a00 and 0x18ce1a00 of every program with a screen. Entering it (0x18cc1a00) dispatches on
the mode: 0 none, 1 digital clock, 2 album art, 3 screen off, 4 demo (the menu offers only None and Digital clock;
`SETTING.AP` has routines for the others at 0x180612b0, 0x18061260, 0x18061288).

The clock routine (0x18ce1a0c) draws the background `171 + n` of `COMMON.STY` once, then on every call returns at
once unless the minute has changed; the time with digits 158 to 167 and colon 170 at y=18 (x from 32, 13 apart; 7
further left in 12-hour mode, with AM/PM 168/169), the date with digits 147 to 156 and dash 157 at y=43. Digits go
through function 38 with the key set at bank offset 0x8a (0xa6 in the stage 7 routine). Stage 7 rewrote the start of
the routine to draw an animation frame on every 200 ms tick (`clock_sprite.S`); stage 15 set the key to 0.

In every program the byte 4 below the "last minute drawn" variable is the animation frame counter (it was the demo
mode's picture number).

## Other shared routines used by new code

| Routine | `MUSIC.AP` | Use |
|---|---|---|
| dialog | 0x18d61d89, text-only form 0x18d61d4d | questions and messages |
| message box | 0x18de1a01 | |
| string format | 0x18b01a01 | fills `[%s]` placeholders |
| key mapping | 0x18aa1a01 (table 0x18aa1ac0) | key messages to events |
| delete control | 0x18c41b30 | the stock "Delete" of the playing screen |
