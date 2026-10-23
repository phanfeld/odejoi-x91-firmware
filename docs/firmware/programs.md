# Programs (.AP)

## File layout

A program file has a resident part and code banks.

| Offset | Content |
|---|---|
| 0x08 | Resident text segment: file offset, length, address |
| 0x14 | Resident data segment: file offset, length, address |
| 0x800, 0x1000, 0x1800, 0x2000 | Four bank tables of 12-byte records: file offset, address, length; one record per code bank |

Every bank has its own address, such as 0x18NN1000, and calls between banks are ordinary Thumb `bl` instructions to
that address. Every bank sits in a 1 KB-aligned slot of the file and the rest of its slot is zeros (about 66 KB of
such room in `MUSIC.AP`). A bank can grow into its slot by changing its length in the table, within the RAM window of
its group; that is where new code goes ({doc}`../code/new-code`).

`firmware_analysis/tools/ap_dis.py` splits a program into its segments and disassembles them with real addresses;
its `segments(data)` and `find(segs, address)` (file offset of an address) are used by every builder.

## Bank groups and their RAM

The low half of a bank's address names its group, and the group decides where in RAM the bank runs. Banks of one
group share that window: calling a bank of the group loads it over whatever was there, and returning reloads the
caller's bank.

| Group (address) | Runs at | Keeps data at | Largest stock bank |
|---|---|---|---|
| 0x18NN1000 | 0x101000 | (on the stack) | 0xa88 (`SETTING.AP`); 0x890 in `MUSIC.AP` |
| 0x18NN1200 | 0x101200 | 0x101000 to 0x1011ff | 0x3b8 |
| 0x18NN1800 | 0x101800 | 0x101000 | 0x74c |
| 0x18NN1a00 | 0x101a00 | 0x101800 to 0x1019ff | 0x5f0 |
| 0x1cNN0e00 | | | 0x75c |
| 0x1cNN2000 | | | 0x714 |

Consequences, each found the hard way:

- A bank's scratch data always lies outside the RAM of its own window, so it survives calls within the group.
  New code (which runs in the 0x1000 group) must keep its data on the stack: anything it leaves at 0x101000 and up is
  overwritten by the next bank load (stage 18's playlist names).
- Code called from a 0x1200 bank while that bank's data (for example the list control's list data at 0x10116c) is
  in use must not load a 0x1000 bank; it has to sit in the caller's own bank (stage 24's `list_box`).
- Each call into another bank of the same group swaps banks, so functions that call each other often should share a
  bank.
- Calls into a group whose window overlaps the caller's come back to a reloaded caller as well: stock code does it
  (`MUSIC.AP` has 8 calls from 0x1000-group banks into 0x1200-group banks, among them the list scene's call of the
  list control at 0x18101208), and stage 25's search calls the list control's Select (0x18681200) that way.

No stock code of `MUSIC.AP` uses the 0x1000 window above its banks' lengths as data, so bank tails are safe for new code; the placement caps a grown bank at 0x800 bytes (`BANK_MAX`), well under the group's largest stock length.
The same holds for the 0x1a00 window (0x101a00 to 0x101fff: the only constants of `MUSIC.AP` in that range are ids in
a table of bank 0x183c1000, and no instruction of the group addresses its own tail); since stage 26 new code also
grows 0x1a00-group banks, each up to 0x5f0 bytes, the group's longest stock bank.

## Programs and how they start

The manager (`MANAGER.AP`) starts programs by number. Its name table:

| Id | Program | Id | Program |
|---|---|---|---|
| 0 | music | 11 | bt |
| 1 | pedometer | 12 | study |
| 2 | video | 13 to 17 | user2 to user6 (unused slots) |
| 3 | picture | 18 | manager |
| 4 | ebook | 19 | mainmenu |
| 5 | browser (the folder view) | 20 | playlist (the library builder) |
| 6 | voice | 21 | config |
| 7 | record | 22 | udisk |
| 8 | radio | | |
| 9 | tools | | |
| 10 | setting | | |

- A program is started with a message of type 0x201 ("create app") to the manager, carrying the program number and a
  start code that reaches the program unchanged: 1 = from the main menu, 16 and 17 = back to the playing screen,
  13 = music started by the library builder, 0x40 = the Playlists tile (stage 5).
- Byte 13 of the block at 0x202f8c holds the running program's number.
- The main menu's list of program ids is entry 1 of `CONFIG.BIN`.

The playback engine (`MENGINE.AP`), the Bluetooth engine (`BTENGINE.AP`) and the FM engine (`FMENGINE.AP`) run as
background processes; the music program talks to its engine by messages ({doc}`music`).

## System calls

Programs reach the kernel and the drivers through `svc` stubs in their resident text. The numbers are the SDK's API
numbers. In `MUSIC.AP`:

| Stub (call address) | svc | Purpose |
|---|---|---|
| 0x1102e1 | 15 | System; function in r3 (28 = millisecond counter, 49 = wait one tick) |
| 0x1102e7 | 17 | File system, the SDK's `vfs_op_entry(mount, p1, p2, p3, command)` with the command on the stack |
| 0x1102e9 | 6 | Display driver, `ui_op_entry(a, b, c, function)` with the function number in r3 ({doc}`display-driver`) |
| | 16 | C library |

The same stubs exist in every program, at other addresses: the display driver's `svc 6` is at 0x110319 in
`BROWSER.AP`, 0x110371 in `EBOOK.AP`, 0x110405 in `VIDEO.AP` and 0x1103a5 in `PICTURE.AP`.

File-system commands (SDK `vfs_interface.h`, confirmed in use): 0 cd (`:` root, `\` up, `|` back onto the folder
just left, `/` into the entry), 1 dir, 2 get name (UTF-16 with FF FE first, or an 8.3 name), 3 get/set the position
(`file_dir_offset`, 0 get, 1 set), 4 make dir, 5 open (mode 2 = modify), 6 create, 7 close, 8 remove, 9 size,
11 seek, 12 tell, 13 read, 14 write, 20 rename. The music program's mount handle is at 0x200020.

The player gives a program only a few file handles; the browser and the engine hold some of their own. New code opens
one file at a time.

## Messages and keys

- `get_gui_msg` (0x110435 in `MUSIC.AP`) returns key messages; `com_key_mapping` (0x18aa1a00) turns them into events
  with a key table (the menu table at 0x18aa1ac0: entries of 6 bytes, key, pad, key-type mask, event).
- Menu events: 0x2701 next (key 0x83), 0x2702 previous (0x82), 0x2703 release, 0x2704 select (0x05), 0x2705 back
  (0x80), 0x2706 options (0x03).
- `get_app_msg` (0x11030d) returns system messages, which a screen hands to the program's dispatcher (pointer at
  0x200140).
- Result codes travel back up the scene functions: for example 0x8014 redraw, 0x8019 "entry deleted", 0x801a "list
  deleted", 0x8306 "dialog: yes", 0x8601 start playing, 0x861b back to the playing screen.

## Shared code

The interface code of the SDK (`case/ap/common`: status bar, lists, menus, dialogs, screensaver, key filter, volume,
timers) is linked into every program separately. Across programs it often sits at the same addresses, but its
variables do not, and its calls to resident stubs differ. A patch to shared code is therefore applied per program,
found by its bytes with the calls and literals masked, and re-aimed at that program's addresses. See
{doc}`shared-code`.
