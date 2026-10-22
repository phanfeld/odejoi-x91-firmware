# Glossary

ADFU
: Actions' USB service mode ("upgrade mode"), USB ID `10d6:10d6`. Entered with `adfu_reboot`.

bank
: A piece of program code with its own address that is loaded into a RAM window when called. Banks of one group
  share the window. See {doc}`firmware/programs`.

bank tail
: The zeros between a bank's end and the end of its 1 KB file slot; where new code is placed.

checker
: A script that runs old and new code side by side in `thumb_sim.py` and compares the results; every program patch
  has one.

`COMMON.STY`
: The resource file all programs share. Ids with bit 15 set refer to it.

engine
: `MENGINE.AP`, the background process that plays music, controlled by messages.

Graphite
: The new interface design built in this project.

host test
: The test of the new C code on the computer, against a simulated disk, library, browser and engine
  (`design/playlist/host/`).

keyed draw
: A display driver call that draws only pixels whose 16-bit value is above a key (function 38).

LFI
: The firmware container: header, directory, 137 files, additive checksums.

list style
: A list-box record of `COMMON.STY` (0x6000 to 0x6008) that decides how a list looks and which parts it shows.

readback
: The image read from the player after a write (`x91_dump/flash_work/readback.bin`); it identifies what is on the
  player.

shared code
: The SDK's interface code (status bar, lists, menus, screensaver, key filter, timers) linked into every program
  separately.

sideways copy
: The second, column-wise copy of a picture that serves as a scrolling text's background.

stage
: One step of the design, one builder (`design/build_stageN.py`), one flash.

status bar
: The top 20 rows: card mark, Bluetooth mark, battery, and (main menu) the clock; since stage 24 also menu and list
  names or the item counter.

`STY`, `MCG`, `AP`, `DRV`, `FON`
: Resource file, menu file, program, driver, font.

theme
: The same design in another accent colour, built as its own image.
