# Program patches

## Method

The image has no free space, and code banks are full of unoptimised stock code. A patch therefore rewrites a stretch
of existing code more compactly, keeps its behaviour, and uses the room gained for the change.

1. **Write the new stretch** as Thumb assembly in `design/patches/NAME.S`, with `.org` at the bank offsets. A patch
   that calls into other banks is laid out from one base address so that both banks' routines can be named (as
   `music_headbar.S` does from the timer bank 0x18a21a00). Calls are `bl` to labels placed at the callees'
   offsets.
2. **Assemble** with `arm-none-eabi-as` (`build_stage14.assemble`), take the bytes of the stretch.
3. **Check the stock bytes**: the builder refuses unless the stretch in the input image is exactly the expected one
   (a hash or the bytes themselves).
4. **Run the checker**: `check_NAME.py OLD.dis NEW.dis` runs the old and the new stretch side by side in
   `thumb_sim.py` on every relevant combination of inputs and compares calls (target and arguments), memory written,
   registers and stack, apart from the intended difference. The builder refuses to produce an image if it fails.
5. **Put it in** (`build_stage14.replace_stretch` is the general form).

For shared code the stretch is found in each program by its bytes with the `bl` instructions masked
(`build_stage22.masked`, `find_all`), its calls are re-aimed at that program's routines, and the checker runs once per
program with that program's addresses.

## The patches

| Patch | Stage | Where | What | Checker |
|---|---|---|---|---|
| `music_playlists_tile.S` | 5 | `MUSIC.AP` 0x18101000 + 0x2dc to 0x35e (130 bytes) | root-menu routine: start code 0x40 skips the menu and acts as "Playlists" | `check_music_patch.py`, 64 combinations |
| `clock_sprite.S` | 7 | shared screensaver bank 0x18ce1a00 + 0x034 to 0x0c6 (146 bytes), seven programs | draw one animation frame per timer tick | `check_clock_patch.py`, 432 per program |
| `music_progress.S` | 9 | `MUSIC.AP` 0x18061000 + 0x3f4 to 0x476 | the knob without flicker (replaced by stage 11) | `check_progress_patch.py`, 666 |
| `music_playing.S` | 11 | `MUSIC.AP` 0x18061000 + 0x390 to 0x476 (230 bytes) | the whole time-and-bar routine: bar with the played part, knob moved column by column | `check_playing_patch.py`, 1336 |
| `music_title.S` | 14 | `MUSIC.AP` 0x1c102000 + 0x1d4 to 0x1f2 (30 bytes) | the tag reader fetches the file name only when the title is empty | `check_title_patch.py`, 63 |
| `music_headbar.S` | 14, 22 | shared status-bar on/off routine (0x74 bytes), `MUSIC.AP` then 14 more programs | draw the bar at once when switched on | `check_headbar_patch.py`, 600 per program |
| `ebook_reader.S` | 16 | `EBOOK.AP` 0x180e1000: 0x0dc to 0x18e, 0x48c to 0x50a, 0x3c0 to 0x406 | landscape page, bottom strip with progress bar | `check_ebook_patch.py`, 6400 |
| `headbar_soon.S` | 24 | the same on/off routine in 15 programs | also move the bar timer's next firing to now | `check_headbar_soon.py`, 840 per program |
| `menu_box.S` | 24 | new, 52 bytes at the end of every bank with a list box call other than the list control's (15 programs) | on a full redraw of style 0x6000 or 0x6002 to 0x6005 draw picture 127 at (17, 0) first, then the list box; both through the bank's own veneer, so no literal | `check_menu_box.py`, 112 per bank |

Smaller code changes are made directly by the builders with `patch_bytes` (checked old bytes):

| Stage | Where | Change |
|---|---|---|
| 5 | `MAINMENU.AP` 0x110144 | menu entry 1 starts program 0 with code 0x40; grid steps |
| 7 | screensaver timer, two places | 500 → 200 ms |
| 14 | `MUSIC.AP` 0x180810ba, 0x180810c6 | the playing screen names its own status-bar background (45) |
| 15 | `MAINMENU.AP` 0x18c21c0e | clock x = 22 |
| 15 | screensaver clock key, bank offset 0x8a or 0xa6, 15 programs | 0xb5b6 → 0 |
| 16, 17 | `EBOOK.AP` 0x180c120a, 0x180c1210, 0x180c1218; five signatures | lines, width, measuring mode; page-index signature |
| 18 | `PLAYLIST.AP` 0x180210b2 | `movs r7, #0` → `#1`: read the `.m3u` files at every run |
| 19 | `MUSIC.AP` 0x181011ce | `bne` → `b`: no built-in playlists on top of the Playlists list |
| 20 | `MUSIC.AP` 0x180a13b6 | the Previous key calls `previous_key` |
| 21 | `MUSIC.AP` 0x1816102e, 0x18161092; 0x1816116a to 0x18161192 | result handlers call the new code; Playlists options are lists 26 to 30 |
| 21 | `MENGINE.AP` 0x1a11189e | the volume table |
| 23 | `MUSIC.AP` 0x18b41a6e | the screen-off Previous calls `standby_previous` |
| 24 | 0x18661380 in five programs | the list control's list box call goes to `list_box` |
| 24 | every other list box call, 15 programs | goes to `menu_box` at the end of its bank |

## thumb_sim.py

`design/patches/thumb_sim.py` interprets straight-line Thumb code from `objdump` output. It knows only the
instruction forms that occur in the patched stretches and stops with an error on anything else, so a check never
rests on a guess.

```python
import thumb_sim
code = thumb_sim.load("new.dis", START, END)          # {address: (size, op, args, literal address)}
m = thumb_sim.Machine(dict(r0=1, r1=0, sp=0x100000, lr=0), {})
m.wr(0x7000, 4, 0x200138)                               # memory is a byte map; unwritten bytes read as 0xEE
exit = m.run(code, START, (), lambda target, m: 1)     # calls out of the code are recorded and answered
m.calls                                                 # [(target, r0, r1, r2, r3), ...]
m.mem, m.r                                              # memory and registers afterwards
```

It follows calls inside the code under test, restores registers saved by `push` on the matching `pop`, and treats a
`b` out of the code as a tail call. An earlier version mis-added a shifted operand; when a checker disagrees with
the listing, suspect the interpreter first.
