# About this reference

What is known about the X91's stock firmware: formats, addresses and behaviour, as read from the dump and checked
on the player. Addresses are those of the stock firmware (line `1.101.37`) unless a page says otherwise; where a
stage moved or replaced something, the page says so.

The predecessor's SDK (US212A for the ATJ2127, partly published as
[PD196_ATJ2127](https://github.com/Suber/PD196_ATJ2127)) explains many names; the X91's code matches it closely, with exceptions noted where they were found (the engine's message
numbers, for one).

| Page | Covers |
|---|---|
| {doc}`hardware` | identification, memory, boot record, upgrade mode, recovery |
| {doc}`image-format` | the LFI container, its 137 files, `CONFIG.BIN` |
| {doc}`programs` | `.AP` layout, bank groups and their RAM, program ids, system calls, messages and keys |
| {doc}`resources` | `.STY` pictures, texts and layouts, list styles, `.MCG` menus, fonts, picture bookkeeping |
| {doc}`display-driver` | `DRV_UI.DRV` functions, keyed draws, list boxes and the counter, rotation |
| {doc}`shared-code` | status bar, app timers, list control, menus, key filter, screensaver |
| {doc}`music` | the music program, the engine and its messages, volume, the library builder, `M3U.LIB` |
| {doc}`other-programs` | main menu, settings, eBook reader, folder view, Bluetooth, programs never changed |
| {doc}`flashing` | the vendor flash procedure on Linux, `x91_flash.py`, `x91_tool.py` |
