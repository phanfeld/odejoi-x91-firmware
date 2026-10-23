/* The top line of the file lists (to-do 18): the item counter ("12/186") only inside one album or one playlist
 * (owner, 2026-10-21), the name of the level everywhere else (owner, 2026-10-14).
 *
 * The shared list control (gui_directory, at 0x18661200 in MUSIC.AP, BROWSER.AP, EBOOK.AP, VIDEO.AP and PICTURE.AP,
 * each with its own RAM) draws every level with list style 0x6000; its call of the display driver's list box
 * (0x18661380) comes here instead. Stage 24 made three styles of the same look in COMMON.STY: 0x6000 with nothing in
 * the status bar, 0x6005 with the list's title there (where the main menu has its clock), 0x6003 with the counter
 * there in the track counter's digits.
 *
 *   - Inside one album or playlist (below the top level, songs and no lists): the counter. That is an album of an
 *     artist, of a genre or of the Albums list, a playlist, and a folder with only files. Only where it is wanted:
 *     the music lists and the folder view (LIST_COUNTED).
 *   - Below the top level otherwise: the title the control filled in, the level's name from the browser (an
 *     artist's name for its albums, a folder's name).
 *   - At the top level the browser has no name (the library) or "ROOT" (folders): the music lists name the list
 *     they are (Playlists, All songs, Artists, Albums, Genres); another program names its top level with
 *     TOP_TEXT, or leaves the line empty (0).
 *
 * On a full redraw it first clears the status bar's middle (fw.h, clear_bar): the list styles' background no longer
 * covers the bar, so that the battery and Bluetooth marks stay.
 *
 * design/graphite/lists.py compiles this once per program with that program's addresses and choices, and puts it at the
 * free end of the control's own bank: new-code banks load at 0x101000, over the list data the control keeps at
 * 0x10116c, so it cannot go where the other new code is. One function, nothing else. */
#include "fw.h"

/* The music program's choices are the defaults; the build sets all three for the other programs. */
#ifndef LIST_COUNTED
#define LIST_COUNTED 1
#endif
#ifndef TOP_TEXT
#define TOP_BY_PATH
#define TOP_TEXT 0
#endif

/* MUSIC.STY texts of the top lists, by the library's list type (0 All songs, 1 Albums, 2 Artists, 3 Genres), one byte
   each; Playlists are a file source of their own */
#define TOP_LIBRARY (10u | 8u << 8 | 17u << 16 | 42u << 24)
#define T_PLAYLISTS 72

uptr list_box(style_t *st, listbox_t *data, u32 mode)
{
    const dir_brow_t *b = list_level();
    u32 text = TOP_TEXT;

    if (LIST_COUNTED && b->layer_no > 0 && b->dir_total == 0 && b->file_total > 0) {
        st->id = STYLE_COUNTED;
    } else if (b->layer_no > 0) {
        st->id = STYLE_NAMED;
    } else {
#ifdef TOP_BY_PATH
        const u8 *path = browse_path();                    /* file source at +0, the library's list type at +6 */
        u32 type = path[6] | path[7] << 8;
        text = path[0] == FSEL_M3U ? T_PLAYLISTS : path[0] == FSEL_PLAYLIST && type < 4 ? TOP_LIBRARY >> (8 * type) & 0xff : 0;
#endif
        st->id = text ? STYLE_NAMED : STYLE_DIR;
        if (text) {
            data->title.str = text;
            data->title.lang = TEXT_ID;
        }
    }
    if (mode == LIST_DRAW_ALL)                             /* the bar's middle: from the screen before, or empty */
        clear_bar();
    return ui((uptr)st, (uptr)data, mode, UI_LISTBOX);
}
