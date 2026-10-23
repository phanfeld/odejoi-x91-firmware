# Changelog

## 1.0.0 (2026-10-23)

The first release: the Graphite interface for the ODEJOI X91, in four themes, built from the stock firmware
(`1.101.37`, 2025-07-11) in one go. Every part of it went onto the player and was tested there (stages 1 to 27,
`docs/project/history.md`).

### On the player

- **Look.** Black background, one accent colour, rounded tiles, thin line icons; Ubuntu 12 px as the interface
  typeface, with missing glyphs drawn from look-alikes. Four themes: Amber, Mint, Ice and Berry.
- **Start, main menu, shut-down.** A new start-up picture and shut-down animation; six tiles (Music, Playlists,
  Folder, Bluetooth, eBook, Settings), the Playlists tile going straight to the playlists; the clock at the top left.
- **Status bar.** Drawn at once and right after every screen, without a blink of its marks; menus show their name
  there, lists the level's name, and inside an album, playlist or album folder the item counter. Short English menu
  names.
- **Music.** Playlists first in the music menu; the playing screen after the design mock, with the title from the tag,
  the play state in the status bar and a progress bar without flicker; the Previous key restarts the song after 3
  seconds, also with the screen off; even 2 dB volume steps; lyrics off.
- **Playlists.** Only the `.m3u` playlists; add the playing song, a song, or an album, artist or genre to a playlist
  or a new one; remove a song; delete a playlist; move songs; "Add songs" from the library by the keypad; "New
  playlist" and "Rename" with the name typed on the keypad. `M3U.LIB` is kept up to date, so changes show at once;
  "Update list?" reads the `.m3u` files.
- **Search.** A T9 keypad in the options of Playlists, All songs, Artists, Albums and Genres, at every level.
- **eBook reader.** Landscape, 7 lines of 152 pixels that end between words, a progress bar and the page number.
- **Screensaver.** A night meadow with a hopping blob; the clock's digits and colon in every theme's colours.
- **Settings.** Sound settings with Equalizer and Volume limit; the volume pop-up, notices, Bluetooth search and the
  library's "Searching..." screen in the theme.

### In this repository

- One build, `design/build.py`, with the parts of the design in `design/graphite/`: stock image in, one image per
  theme out, in about a minute. It replaces the 27 stage builders, which each read the previous stage's image; their
  frozen copies of the C sources and stage 9's superseded patch are gone (all of it is in the git history). The
  stage previews moved to `design/history/`.
- The images are byte for byte the stage 27 images that were tested on the player. `design/build.py --check` stops
  unless they are:

  | Theme | sha256 of `x91_lfi_<theme>.bin` |
  |---|---|
  | Amber | `5fb39a7f8d86e210e9850c495d1621f1744039a78aa81dc9350a147948e50bab` |
  | Mint | `2b084b2692dc7680f33a674c02e80e61226ecbad9f52f5d9b792fa38b91e1f4b` |
  | Ice | `7f9358288c6dd28d0614618febbbd018d9878d2b5628fabfc496fe9bba20b7b5` |
  | Berry | `b1f169d16f5e6bf600725c355206fee4fb2d42d0ad9780cb2d23200a8c88bb80` |

- `themes.json` names the release (`version`) instead of a stage; `x91_tool.py` shows it and still reads older lists.
- The build no longer needs the stock image unpacked in `x91_dump/unpacked/`.
- Documentation rewritten for the single build (`docs/code/build-system.md`); the stages are kept as the design's
  history (`docs/design/stages.md`).

### Known

- `CONFIG.TXT`, the readable copy of the settings that the firmware does not read, lists the six tiles in a
  commented-out line and the five tiles of stage 3 in the active one.
- Open work and limits: `docs/project/todo.md`.
