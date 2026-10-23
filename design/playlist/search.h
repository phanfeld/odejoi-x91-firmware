/* The search of stage 25 (search.c). */
#ifndef PLAYLIST_SEARCH_H
#define PLAYLIST_SEARCH_H
#include "fw.h"

/* The theme's colours as RGB565; build_stage25.py passes the theme's own, these are Amber's. */
#ifndef COL_BG
#define COL_BG        0x0000
#define COL_SURFACE   0x18e4
#define COL_LINE      0x2987
#define COL_TEXT      0xf7be
#define COL_TEXT2     0x8cb4
#define COL_ACCENT    0xfd80
#define COL_ON_ACCENT 0x0862
#endif

/* "Search" in the options of a music list: the keypad screen over the list's current level; returns what the list
   option handler returns (RESULT_REDRAW, "Play", or a system message's result). */
u32 search_list(u8 *path_info);

/* "Add songs" (stage 26): the library's songs, as All songs lists them (MUSIC.LIB), by the same keypad. A chosen song
   ends the screen with SONGS_CHOSEN and its row of All songs (from 0) in keep->row; called again with keep as it came
   back, the screen opens with the same keys and the same line chosen. SONGS_LEFT: Return; SONGS_PASS: a system
   message's result in keep->result; SONGS_FAILED: MUSIC.LIB cannot be read. keep starts zeroed. */
#define SEARCH_KEYS 16
typedef struct {
    u8 q[SEARCH_KEYS];                   /* the keys typed (digits) */
    u8 qlen, key;                        /* their number; the keypad's key */
    u16 sel, top;                        /* the chosen result and the first one shown */
    u16 row;                             /* the chosen song */
    u32 result;
} search_keep_t;
enum { SONGS_FAILED = -2, SONGS_PASS = -1, SONGS_LEFT = 0, SONGS_CHOSEN = 1 };
int search_songs(search_keep_t *keep);
/* Row `row` of All songs: with place, its location as browser_get_location gives a song's (fw.h: the extension,
   the directory entry and the folder chain); else its name (UTF-16 with FF FE as the list shows it, ROW_NAME bytes,
   the last two zero). 0 if MUSIC.LIB cannot be read. */
int songs_get(int row, u8 *out, int place);

#ifdef HOST
/* for the host test: whether the keys (digits 0 to 9) spell the beginning of a word of name, and the letters they
   spell there (UTF-16 with FF FE, into spelled[26]) */
int search_matches(const u8 *name, const u8 *keys, int n, u16 *spelled);
#endif
#endif
