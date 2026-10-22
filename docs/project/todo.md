# Open work

| Item | What is known |
|---|---|
| Equaliser look | slider record 7 of `COMMON.STY`; preset names are `MUSIC.STY` pictures 18 to 26 |
| Search, text entry, on-screen keyboard | no text input in the firmware; lists are the shared list control; landscape possible (function 30) |
| More themes and screensaver options | hidden screensaver modes have routines in `SETTING.AP`; pictures 234 to 239 and most of 240 are free |
| Simple games | a new program would replace an unused one; system-call interface mostly unknown |
| Playing screen exactly as the mock | two play-mode symbols need a rewrite of the painter at 0x180811fc |
| Lyrics on demand | off since stage 11; a toggle needs the painters at 0x18081068 and 0x18061000 |
| Now playing as screensaver | new drawing code in the shared screensaver bank |
| Volume differs with the screen off | the screen-off path stores the volume through its own variable (see {doc}`../firmware/shared-code`); not yet reproduced |
| Volume bar shown briefly with the screen off | not started |
| Remote buttons (cable, Bluetooth) | depends on the hardware; AVRCP goes through `BTENGINE.AP` |
| Folder play repeats the title | in folder play the third line of the playing screen repeats the title |

The flashing tool's separate Dump job has not been run on a device yet.
