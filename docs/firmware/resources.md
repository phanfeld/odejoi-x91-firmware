# Resources, menus and fonts

## Resource files (.STY)

Every program has a resource file with its pictures, its texts in 28 languages and its screen layouts;
`COMMON.STY` holds what all programs share (status bar, lists, dialogs, sliders, screensaver). **An id with bit 15
set refers to `COMMON.STY`**, without it to the program's own file: picture 0x80fa is `COMMON.STY` picture 250.

`firmware_analysis/tools/x91_preview.py` parses these files (class `Sty`) and renders them.

### Header

| Offset | Content |
|---|---|
| 0x00 | Magic `RU3\x19` |
| 0x08 | Address of the layout area (starts with `sty`); its word at +8 points to the table directory |
| 0x10 | Picture table: offset (u32), count (u16) |
| 0x20 | Language table: offset (u32), count (u16) |
| 0x30 | Offset of an embedded XML description (resource and string names, code pages) |

### Pictures

Picture table entries are 16 bytes: offset (u32), length (u32), type (u16), width (u16), height (u16). The data is
RGB565, little-endian, row by row. A picture can be declared smaller than its data (`build_stage7.resize_picture`);
the rest of its room stays unused. `build_stage1.set_picture(sty, index, data, w, h)` replaces a picture of the same
size.

**Sideways copies.** A picture that is the background of a scrolling text (title line, selected list row, time
boxes) is stored twice: as usual, and directly behind it the same picture turned sideways (column by column,
`copy[x * h + y] = picture[y * w + x]`), which the display driver reads while the text scrolls. The picture table
knows only the first. Concerned: `MUSIC.STY` 11, 15, 32, 47, 49, 76 and `COMMON.STY` 212, 250, 292, 293, 414, 415
(`build_stage14.with_copy(stock_file)` finds them). After changing such a picture call
`build_stage14.refresh_copies(lfi, [])`.

Transparency is a matter of the drawing call, not the picture: some calls treat black as transparent, others draw
only pixels above a key value ({doc}`display-driver`). Pictures that must cover something use 0x0020, which looks
black but is not transparent (the card marks since stage 14).

### Texts

Language table entries are 16 bytes: offset (u32), length (u32), a halfword, count (u16), language id (u16). Each
language block is a list of 8-byte entries (offset, length) pointing at UTF-16LE strings with a final zero. English is
language id 2. The language setting selects a string table and a code page and nothing else.

Texts are changed in English only and in place: the new text must fit the old one's room, and the entry's length is
set to the new length (stages 21 and 24, `build_stage24.menu_texts`). Dialog texts break lines where they contain
CR LF; without them the dialog wraps where it can, also inside a name.

### Layout tables

The table directory has 11 entries of (offset, count), in this order:

| Table | Control | Record | What is known |
|---|---|---|---|
| 0 | scene | 20 bytes | background, x, y, w, h, …, control count, control list (pairs: flag, type << 12 \| id), attributes |
| 1 | picture box | 32 bytes | id, x, y, attributes (frame count in the high byte; bit 1: frame list by address), frames |
| 2 | text box | 20 bytes | id, x, y, w, h, background x, y, background picture (a fill colour when attribute bit 1 is clear), text colour, attributes |
| 3 | number box | 28 bytes | see below |
| 4 | time box | | |
| 5 | progress bar | | the playing screen's bar is not this control; `MUSIC.AP` draws it |
| 6 | list box | 28 bytes | see below |
| 7 | parameter box | | |
| 8 | dialog box | | |
| 9 | slider | 48 bytes | four sub-record addresses, background picture with x and y, icon picture with x and y, … |
| 10 | attribute box | | |

`build_stage11.tables_of(sty)` returns the directory and `build_stage11.set_fields(sty, table, size, index, w3=…)`
changes 16-bit fields of a record.

**Number box** (28 bytes): x, y, w, h, first digit picture, separator picture, digit width and separator width
(bytes 12 and 13), …, background x, y, background picture (20), …, digit counts (byte 24: low and high nibble for the
two numbers, 0 = as many as needed), attributes (byte 26: bit 0 shown, bits 2-3 alignment, bit 4 two numbers,
bit 5 picture form). In picture form the digits are pictures "first + digit" drawn over the background picture with
black transparent; otherwise the number is text in the interface font, in the record's colours. The playing
screen's track counter is `MUSIC.STY` number box 0 (digits 77 to 86, separator 88, background 76).

**Slider** records of `COMMON.STY`: 0 to 3 brightness-type sliders (icon 345/346, the sun), 5 the volume page
(background 233 since stage 10, speaker 406 at (45, 40), number on 403 at (66, 40), bar at (11, 80): track 333, fill
353, open part 354 and 358, knob 359 and its repair piece 360), 6 a landscape slider, 7 the five-band equaliser (bars
334 to 343, marks 355 to 357, line 344).

### List boxes

`COMMON.STY` table 6 holds nine list styles; the style id is 0x6000 + record number.

| Id | SDK name | Used by |
|---|---|---|
| 0x6000 | DIRLIST | the shared list control: music lists, folder view, eBook, Video and Picture file lists |
| 0x6001 | FILELIST | a list in `MUSIC.AP` (0x18221350), eBook, Study, Tools |
| 0x6002 | MENULIST | the menus of every program |
| 0x6003 | MENULIST_HEAD | no program; since stage 24 the file lists with the item counter |
| 0x6004 | MENULIST_TITLE | sub-menus with a title line; the playlist picker (5 lines) |
| 0x6005 | MENULIST_TITLE2 | no program; since stage 24 the file lists with their name |
| 0x6006 | MENULIST_OPTION | option menus (also the main menu's only list) |
| 0x6007 | MENULIST_OPTION_TITLE | no program found |
| 0x6008 | MENULIST_OPTION_V | landscape option menu |

Record (28 bytes):

| Bytes | Field |
|---|---|
| 0 to 15 | File offsets of four sub-records: title (12 bytes), scroll bar (16), rows (264 in records 0 to 3), counter (28); they may be shared between records |
| 16 to 21 | Background picture, x, y; drawn on a full redraw (stock: 185, the black 128 x 160 picture, at 0, 0) |
| 22 | Row height (0x18 = 24) |
| 23 | Lines per page (6; record 4 has 5) |
| 24 | Parts shown: bit 0 the list, bit 1 the title, bit 2 the scroll bar, bit 3 the counter |

Since stage 24 the styles drawn with the status bar on (0x6000, 0x6002 to 0x6005) have picture 126 at (0, 16) as
background, the black picture 185 from row 16 down, so a full redraw leaves the bar alone.

Title sub-record: x, y, w, h, text colour, attributes (bits 0-1 alignment: 0 left, 1 centre, 2 right; bits 2-3 font:
0 small, 1 normal, 2 large). Drawn only on a full redraw, over what is on the screen.

Counter sub-record (14 halfwords): first digit picture, separator picture, digit width | separator width << 8, digit
counts for position and total, text box (x, y, w, h), background x, y, background picture, text colour, attributes
(bit 0 picture form; bits 1-2 alignment; bits 3, 4 keep the digit counts; bit 5 background picture in text form;
bits 6-7 font size). The driver formats "position + 1" and "total" (see {doc}`display-driver`).

Rows sub-record: begins with the row background (picture 263, a full-screen picture from which each row's slice is
drawn), the icon base (picture 113 for 0x6000; 0x8000 for the menus, so a menu row's icon number is the
`COMMON.STY` picture itself), and the pictures and colours of the selected row (292, 293, 294).

## Menus (.MCG)

A menu file is a table of lists and the lists' items.

| Where | Content |
|---|---|
| +12 | Header size (u16), number of lists (u16) |
| header | List table, 12 bytes per list: title text id (u16), item count (u16), file offset of the items (u32), link (u32: item index << 16 \| parent list, or 0xffffffff for an entry list) |
| items | 20 bytes each: sub-list number (u16; 0x7fff plain action, 0xffff radio choice), text id (u16), second text id (u16), icon number (u16, a `COMMON.STY` picture 0 to 124), routine address (u32), 0, common routine address (u32) |
| after the lists | A block starting `ACTMCGGM01`: 42-byte records, one per item the program defines, used or not (text id, second text id, routine address, item number with a radio flag, icon, sub-menu number in the editor's counting) |

The firmware reads only the list table and the lists; the `ACTMCGGM01` block is how hidden items were found (stage 11
switched on Sound settings in Settings from it). A row finds its sub-menu through its own child field, not through
the links. The title text id is what the menu code shows as the menu's name (since stage 24 in the status bar).

`build_stage21.rows_of(mcg, header_size, list)` returns a list's header and its items.

## Fonts

`UNICODE.FON` (the interface and reading font) holds 65,536 glyphs of 33 bytes, indexed by code point: 16 rows, one
byte per row for widths up to 8 or two bytes per row for widths 9 to 16 (most significant bit left), and the advance
width in the last byte. One bit per pixel; the colour comes from the drawing call. Capitals and digits sit on rows 5
to 12.

- Stage 2 replaced 512 Latin, Greek and Cyrillic glyphs with Ubuntu at 12 pixels, rendered to one bit, with `f`, `t`,
  `S`, the digits and (stage 3) `M`, `N`, `O`, `Q` drawn by hand. The widths are proportional (`i` 3, `m` 10, space
  3); the stock font has 7 for every ASCII letter. Anything that lays out text for the player must take the font from
  a stage image, not from `x91_dump/unpacked/`.
- Stage 19 copied drawn glyphs into 11 code points the typeface lacks (U+2010 and U+2011 hyphens and others).
- `UNICODEL.FON` (24 rows) is stock.

## Picture bookkeeping in COMMON.STY

| Pictures | Use |
|---|---|
| 0 to 124 | 14 x 14 icons for menu rows (the row's icon number is the picture) |
| 113 to 124 | file-type icons of the folder view in two states (stage 6) |
| 125 | the list counter's slash, 4 x 12 (stage 24; was an unused stock icon) |
| 126 | list background below the status bar, 128 x 144, a view into picture 185 (stage 24; was an unused stock icon) |
| 127 | black field for the status bar's middle, 81 x 16, a view into picture 185 (stage 24; was an unused stock icon) |
| 135 to 145 | the main menu clock's digits and colon, 6 x 12, also the list counter's digits |
| 147 to 157, 158 to 167, 168/169, 170, 171 + n | screensaver clock: date digits and dash, time digits, AM/PM, colon, background |
| 185 | the shared black full-screen picture (list and volume backgrounds) |
| 188 to 193 | battery mark (picture box 1); 20 x 16 with a black border since stage 24 |
| 200 to 202 | Bluetooth mark: on, empty, connected; 10 x 16 with a black border since stage 24 |
| 203 to 205 | card mark: card in, no card, card in use; 17 x 16 with a black border since stage 24 |
| 221 to 232 | screensaver animation frames, 56 x 80 (stage 7; were "demo" pictures) |
| 233 | volume panel (stage 10) |
| 234 to 239 | free, 128 x 160 each |
| 240 | free, declared 128 x 134; its last 26 rows hold pictures 188 to 193 and 200 to 205 (stage 24) |
| 247/321, 248/322 | battery notice panels and the marks drawn on them |
| 249 | default status-bar background, 160 x 20 |
| 250 | the list counter's background, 68 x 16 |
| 263 | list row background, 128 x 160 |
| 292 to 294 | selected list row |
| 310 to 315 | scroll bar |
| 345/346 | the brightness slider's sun |
| 411/413 | AM/PM in the status bar (picture box 4) |

Picture boxes 0 to 4 of `COMMON.STY` are the status bar's parts: program icon (switched off in this build), battery
at (108, 0), card mark at (0, 0), Bluetooth mark at (98, 0), AM/PM. The marks were at (108, 2), (2, 3) and (98, 2);
stage 24 bordered them out to the bar's edges ({doc}`shared-code`).
