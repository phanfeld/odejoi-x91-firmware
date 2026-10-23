"""The Graphite interface for the ODEJOI X91, built from the stock firmware image in one go (design/build.py).

Each module changes one part of the firmware; build.py runs them in this order on the stock image:

  typeface     UNICODE.FON: the interface typeface
  mainmenu     start-up picture, shut-down animation, the six-tile main menu and its Playlists tile
  pictures     shared pictures: status icons, lists, notices, volume pop-up, Bluetooth search
  screensaver  the screensaver clock: meadow, animation, digits, the clock routine
  music        the music menu, the playing screen, the title from the tag
  settings     Sound settings, lyrics off, the volume curve
  reader       the eBook reader in landscape
  statusbar    the status bar at once, its marks, the main menu clock
  lists        the top line of menus and lists, short menu names, list_box and menu_box
  playlists    the .m3u playlists: the new code in C and the menus and texts that lead to it
"""

VERSION = "1.0.0"
