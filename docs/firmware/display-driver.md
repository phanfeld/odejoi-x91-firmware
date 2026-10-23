# Display driver (DRV_UI.DRV)

## Layout

A driver file has a resident part and code banks like a program, but in three groups. The header names the groups
at 0x30; a bank's address is 0x13NN0000 (first group, 0x400 apart in the file), 0x0bNN0400 (second, 0x800 apart) or
0x03NN0c00 (third, 0x400 apart), with NN = twice its place in the group. The function table (its address at 0x3c of
the header, 0x1190d4 in memory) holds such addresses directly, next to addresses in the resident part.

`firmware_analysis/tools/drv_dis.py` disassembles a driver, this one and `DRV_LCD.DRV` included.

Programs call it through `svc 6` with the function number in r3: `ui(a, b, c, function)`.

## Functions

The table has 40 entries. Numbers 0 to 34 are the SDK's (`ui_op_e` in `display.h` of the US212A SDK, names below);
35 to 39 exist only in this firmware. Addresses are the table's (Thumb bit included).

| No. | Address | SDK name | What it does here |
|---|---|---|---|
| 0 | 0x13080063 | `UI_RES_OPEN` | open a resource file |
| 1 | 0x13080125 | `UI_RES_CLOSE` | close it |
| 2 | 0x117701 | `UI_SHOW_PICBOX` | picture box |
| 3 | 0x0b1a04bb | `UI_SHOW_TEXTBOX` | text box: background (plain picture draw), then the text; a text that does not fit prepares scrolling from the background's sideways copy (0x13220000) |
| 4 | 0x0b180401 | `UI_SHOW_TIMEBOX` | time box |
| 5 | 0x0b100777 | `UI_SHOW_NUMBOX` | number box: picture form (0x0b10064a, digits through 0x0b100400) or text form (0x13120001) |
| 6 | 0x0b160401 | `UI_SHOW_PROGRESSBAR` | progress bar |
| 7 | 0x13060001 | `UI_LOAD_ATTRIBUTEBOX` | |
| 8 | 0x131a0123 | `UI_SHOW_LISTBOX` | list box `(style, data, mode)`; see below |
| 9 | 0x0b2007c5 | `UI_SHOW_DIALOG` | dialog |
| 10 | 0x13180001 | `UI_SHOW_PARAMBOX` | |
| 11 | 0x131e0001 | `UI_SHOW_SLIDERBAR` | slider (volume, brightness, equaliser) |
| 12 | 0x13040001 | `UI_GET_TEXTBOX_ATTRB` | a text box's area (the cover area is text box 1 of `MUSIC.STY`) |
| 13 | 0x130e0001 | `UI_GET_PICBOX_ATTRB` | |
| 14 | 0x130c0001 | `UI_GET_LISTBOX_ATTRB` | list style attributes (lines per page) |
| 15 | 0x0b0c06b5 | `UI_SCROLLSTRING_EXT` | the rotating title line |
| 16 | 0x03020c01 | `UI_SET_LANGUAGE` | |
| 17 | 0x118011 | `UI_GET_DC_STATUS` | read the current colours (to restore them) |
| 18 | 0x03080c01 | `UI_CLEARSCREEN` | |
| 19 | 0x11801f | `UI_SET_PEN_COLOR` | text colour |
| 20 | 0x118027 | `UI_SET_BACKGD_COLOR` | background colour |
| 21 | 0x0b080679 | `UI_SHOW_STRING` | draw a string in a region `(string, region, mode)` |
| 22 | 0x03060c01 | `UI_ELLIPSIS_TO_LONGSTR` | |
| 23 | 0x1186fb | `UI_GET_STRING_LENGTH` | `(string, max, result or 0)`: the sum of the characters' widths (the font's width function, as the string drawing has them), stopping after the first character past max; result: the width and bytes that fit (used since stage 27). UTF-16 only with the type 0x7f (the SDK's `UNICODELANGUAGE`), which skips FF FE and ends at a zero character; with 0x7d, the type the string drawing takes, it reads one byte per character as code-page text and stops at the first zero byte |
| 24 | 0x0b0604ab | `UI_GET_TEXT_LINE` | measure how much text fits a line; mode bit 1: do not end a line inside a word (a word is a run of A to Z, a to z and the straight apostrophe) |
| 25 | 0x03080c4b | `UI_SET_DISPLAYBUF` | |
| 26 | 0x03040d8b | `UI_UNICODE_TO_CHAR` | |
| 27 | 0x03040c99 | `UI_CHAR_TO_UNICODE` | |
| 28 | 0x118047 | `UI_GET_MULTI_STRING_UNICODE` | |
| 29 | 0x03040c01 | `UI_UTF8_TO_UNICODE` | |
| 30 | 0x03080c21 | `UI_SET_SCREEN_DIRECTION` | turn the screen: 1 = landscape (160 x 128); every later drawing call works in those coordinates |
| 31 | 0x1187d1 | `UI_SHOW_PIC` | draw a picture at x, y |
| 32 | 0x03080c9d | `UI_READ_PIC_TO_BUFFER` | |
| 33 | 0x03080c0f | `UI_FLUSH_FONT_BUFFER` | |
| 34 | 0x03080c97 | `UI_SET_LANG_OPTION` | |
| 35 | 0x130c0057 | | prepare a list style (the list code calls it before drawing) |
| 36 | 0x0b06069d | | |
| 37 | 0x117c7f | | draw a picture over a background picture; black pixels of the picture are replaced by the background's |
| 38 | 0x118a7b | | keyed draw: restore the background piece, then draw only pixels whose 16-bit value is above a key |
| 39 | 0x118fc1 | | a row of pictures through the keyed draw (the status bar clock) |

A style is passed as `{id, type}` (4 bytes; type 1 = `COMMON.STY`). Strings are passed as the SDK's `string_desc_t`
(12 bytes): data pointer (or a text id in the low half), type byte (0x7e text id, 0x7d UTF-16 data with FF FE first,
0x7c UTF-8, otherwise a language id for one-byte text), a reserved byte, buffer size, an argument and a result
halfword.

String drawing modes (16 bits): bits 0-1 fill mode (0 read the background back from the panel and draw over it,
1 opaque with the background colour, 2 from a column-wise background picture, 3 nothing: see below), bits 2-3
alignment (left, centre, right), bits 4-7 long-text handling (clip, drop incomplete characters, several rows,
ellipsis, scroll), bits 10-11 font size (0 normal, 1 large, 2 small), bit 12 divide words.

A string is drawn into a buffer strip as wide as the text (at the place its alignment gives it in the region) and as
high as the font (16 rows), in pieces of at most 160 columns, and each piece is written to the panel whole. Before the
letters go in, the strip is prepared by the fill mode (0x11825e, then 0x117e32): mode 1 fills it with the background
colour (DC +4, the colour function 18 fills with), mode 0 reads the panel back into it, mode 2 copies the background
picture, and mode 3 does nothing, so the strip holds what the previous string left there. Mode 3 is not
"transparent": around the letters the panel gets stale pixels (stage 25 as first flashed).

## Keyed draws

Function 38 compares each pixel as an unsigned 16-bit value with the key in its argument block and draws it only if
it is greater. The screensaver clock passes 0xb5b6 (red at least about 184 of 255), so in the stock firmware soft
edges, dim and non-red colours vanished there; stage 15 sets that key to 0. The status bar clock (function 39) uses
0x7bcf: a theme's `text2` colour must stay above it.

## List boxes

The list box function reads the style's 28-byte record ({doc}`resources`) and draws, by the record's byte 24:

1. on a full redraw (mode 3) the background picture of the record (stock 185 at (0, 0), the whole screen);
2. bit 1: the title (0x131a0088), only on a full redraw, over what is on the screen;
3. bit 2: the scroll bar (0x131a0000);
4. bit 3: the counter (0x0b0e0400), on every draw;
5. the rows (0x131c0000 per row): each row's background is the slice of picture 263 behind it, the icon is the row's
   icon number plus the style's icon base, the text is clipped or scrolled; rows beyond the list's end are drawn
   empty.

Draw modes: 1 the active row, 2 the rows, 3 everything, 5 continue scrolling the active row. The list data is the
SDK's `listbox_private_t` (100 bytes): title descriptor at +0, six item descriptors at +12 (12 bytes each; the item's
`argv` holds its icon and mark), icon ids at +84 and +86, rows filled +88, active row +90, previous row +92, total
+94, position +96 (rows counted from 0).

The **counter** formats "position + 1" and "total". With attribute bit 0 clear (stock) it builds "pos/total" and
draws it as text in the interface font in the counter's text box, with the background picture (bit 5) first. With
bit 0 set it hands the digits to the number-box picture routine 0x0b100400: the background picture is drawn at the
counter's x and y when the number of digits changes, then each changed digit is drawn as picture "first + digit" over
it with black transparent, the separator after the position's digits. That routine keeps the last digits in a buffer
shared with the number boxes and starts afresh on a full list redraw.

## The LCD driver and rotation

Function 30 sets a flag and the drawing window (160 x 128 or 128 x 160). Every drawing routine sets its window
through one hook (0x117ebe), which tells the LCD driver the orientation. `DRV_LCD.DRV` function 2 (0x119d9c) writes
the panel's orientation register: mode 0 = 0xc8 (upright), 1 = 0xa8 (landscape), 2 = 0x48, 3 and 4 = 0xe8,
5 = 0x88, 6 = 0xa8. Modes 4 and 5 are the column-by-column modes behind the sideways picture copies. In landscape a
point (x, y) is the upright point (127 − y, x): the upright top edge is the landscape left edge. The shared code has a
wrapper around function 30 that remembers the direction (`MUSIC.AP` 0x18da1d34, read back by 0x18da1d28), which the
screensaver uses.
