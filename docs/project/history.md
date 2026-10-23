# History

## 2026-10-12 to 2026-10-13: from no firmware to a running custom image

| Date | Step |
|---|---|
| 2026-10-12 | No X91 firmware is published anywhere; USB ID `10d6:1101` measured on the unit |
| 2026-10-13 | 66 AGPTEK packages downloaded and 52 decrypted for reference; none fits the X91 |
| 2026-10-13 | Upgrade mode entered by software (`adfu_reboot`); chip confirmed as ATJ2157 |
| 2026-10-13 | Firmware dumped twice through the boot area and verified: `x91_lfi_verified.bin` |
| 2026-10-13 | Read-only rehearsal through the vendor driver: 0 of 38,811 sectors differ |
| 2026-10-13 | First write (the unchanged image), then a custom start-up picture: the write path works |
| 2026-10-13 | Stages 1 to 12 built and flashed one after the other; `x91_tool.py` written |
| 2026-10-13 | Stage 13 built (never flashed alone), stage 14 built |

## 2026-10-14: status bar, clock, reader

| Stage | On the player | Result |
|---|---|---|
| 14 | Mint | works: scrolling text, tag title, status bar at once in Music |
| 15 | Berry | works: main menu clock, screensaver, the Berry theme |
| 16 | Berry | reader in landscape; lines broke inside words |
| 17 | Berry `f1c849f5…` | works: lines end between words, page number, bar, keys |
| 18 | Berry `4737779c…` | playlist list without names; a stutter while writing |

## 2026-10-21 to 2026-10-22: playlists and lists

| Stage | Image (Berry) | Result |
|---|---|---|
| 18 rebuilt | `d40fd160…` | works: names, adding, new playlists, "Update list?" reads the `.m3u` files |
| 19 | `13bacdaa…` | glyphs and hidden rows fine; built-in playlists still shown |
| 19 rebuilt | `3189295f…` | works |
| 20 | `c2ce9554…` | works: library at once, Remove from Playlist, Previous restarts; one message broke |
| 21 | `861c23e5…` | add, delete, volume fine; "Move song" failed (two files open) |
| 21 rebuilt | `a14cef26…` | works |
| 22 | `af61b64e…` | fine apart from the picker's sixth row and Previous with the screen off |
| 23 | `59e444c8…` | works |
| 24 | `c793fc34…` | menu names wrong or cut off, empty top lines, no counter in album folders |
| 24 rebuilt | `decde654…` | works, except the eBook list's name and the status bar's delay in sub-menus |
| 24 rebuilt again | `efa340ee…` | eBook name fine; status bar much faster, but a short blink when a menu or list opens |
| 24 rebuilt a third time | `82eed591…` | never flashed on its own; part of every stage 25 and 26 image |

## 2026-10-23: search, adding songs, naming playlists

| Stage | Image (Berry) | Result |
|---|---|---|
| 25 | `e64bdfb6…` | search works; around its texts stale pixels: the underline broken under the typed letters, specks above the keys, uneven key edges |
| 25 rebuilt | `ee7d8549…` | works: clean texts and keys, and fast |
| 26 | `00112ce2…` | "Add songs" works; after each add the screen first showed the digits typed and an empty line |
| 26 rebuilt | `2a25f3eb…` | no digits, but with fewer than four matches the screen waited about 5 s (keys dead) after each add |
| 26 rebuilt again | `ec287d08…` | the screen at once, keys at once; the new songs show in the playlist only after it is entered again |
| 26, fourth build | `89137f1b…` | works: the new songs show in the playlist at once |
| 27 | `770fd5fe…` | typing works; the name's line misplaced: the mark of the letter being typed too wide and about 20 pixels too far right, the caret behind the third letter of a longer name, stray letters to the right of the mark (the width function was asked with type 0x7d and read the UTF-16 as single bytes) |
| 27 rebuilt | `b1f169d1…` | works: the width asked with type 0x7f, the mark and the caret in place, no stray letters |

`x91_dump/themes/themes.json` lists the current image of each theme (stage 27 rebuilt: Amber `5fb39a7f…`, Mint
`2b084b26…`, Ice `7f935828…`, Berry `b1f169d1…`). The images of stages 24 to 26 are unchanged (built from the frozen sources in
`design/playlist/stage24/`, `stage25/` and `stage26/`; stage 25 rebuilt: Amber `8945629a…`, Mint `2c36fdb9…`, Ice
`e91c8f53…`, Berry `ee7d8549…`; stage 26, fourth build: Amber `76f68ef2…`, Mint `ded7d030…`, Ice `26612f9f…`, Berry
`89137f1b…`).

## Early assumptions that were wrong

Comments in older builders may still reflect these:

- The screensaver clock is drawn by code, not by its layout (stage 6 → 7).
- Pictures 345/346 are the brightness sun, not battery marks (stage 4 → 10).
- The track counter's digit count is a byte of the number-box record (stage 22; stage 14 thought it fixed).
- The engine's message numbers are the SDK's plus 2 from 0x303 on (stage 18 used the SDK's; fixed in stage 20).
- String fill mode 3 does not draw "only the dots" over what is on the screen: it leaves the driver's strip as the
  previous string left it (stage 25; rebuilt with mode 1).
- The engine does have a seek: 0x317 (stage 20).
- Bytes 0 and 1 of 0x202fbc mean "the music engine runs", playing or paused (stage 24).
- The volume curve is in the music engine, not in the audio driver (stage 21).
- The display driver's text width (function 23) takes UTF-16 with the type the string drawing takes, 0x7d: it takes
  it only as 0x7f (stage 27).
