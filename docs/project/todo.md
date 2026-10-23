# Open work

| Item | What is known |
|---|---|
| Equaliser look | slider record 7 of `COMMON.STY`; preset names are `MUSIC.STY` pictures 18 to 26 |
| More themes and screensaver options | hidden screensaver modes have routines in `SETTING.AP`; pictures 234 to 239 and most of 240 are free |
| Simple games | a new program would replace an unused one; system-call interface mostly unknown |
| Playing screen exactly as the mock | two play-mode symbols need a rewrite of the painter at 0x180811fc |
| Lyrics on demand | off since stage 11; a toggle needs the painters at 0x18081068 and 0x18061000 |
| Now playing as screensaver | new drawing code in the shared screensaver bank |
| Volume differs with the screen off | the screen-off path stores the volume through its own variable (see {doc}`../firmware/shared-code`); not yet reproduced |
| Volume bar shown briefly with the screen off | not started |
| Remote buttons (cable, Bluetooth) | depends on the hardware; AVRCP goes through `BTENGINE.AP` |
| Folder play repeats the title | in folder play the third line of the playing screen repeats the title |
| A name for "New playlist" in "Add to playlist" | the picker's "New playlist" (playing screen, song lists) still makes "New playlist N"; it could open the name screen of stage 27 first |
| "New playlist" with no playlists | the Playlists list with no `.m3u` cannot be opened, so neither can its options; "Add to playlist" makes the first one |
| Letters beyond ASCII in names | the name screen types ASCII only; how the file system makes short names for other letters is not known |
| `CONFIG.TXT` | the readable copy of the settings shows the six tiles in a commented-out line and the five tiles of stage 3 in the active one ({doc}`history`); the firmware does not read it, so a fix changes only the images' checksums |

The flashing tool's separate Dump job has not been run on a device yet.
