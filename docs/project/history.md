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
| 24 rebuilt a third time | `82eed591…` | built, not yet flashed |

## 2026-10-23: search

| Stage | Image (Berry) | Result |
|---|---|---|
| 25 | `e64bdfb6…` | Search with a T9 keypad in the music lists' options; built, not yet flashed |

`x91_dump/themes/themes.json` lists the current image of each theme (stage 25: Amber `61618794…`, Mint
`13f16611…`, Ice `ff56ddfe…`, Berry `e64bdfb6…`). Stage 24's images are unchanged (built from the frozen sources in
`design/playlist/stage24/`).

## Early assumptions that were wrong

Comments in older builders may still reflect these:

- The screensaver clock is drawn by code, not by its layout (stage 6 → 7).
- Pictures 345/346 are the brightness sun, not battery marks (stage 4 → 10).
- The track counter's digit count is a byte of the number-box record (stage 22; stage 14 thought it fixed).
- The engine's message numbers are the SDK's plus 2 from 0x303 on (stage 18 used the SDK's; fixed in stage 20).
- The engine does have a seek: 0x317 (stage 20).
- Bytes 0 and 1 of 0x202fbc mean "the music engine runs", playing or paused (stage 24).
- The volume curve is in the music engine, not in the audio driver (stage 21).
