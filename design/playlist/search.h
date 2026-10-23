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

/* The screen, shared with the name screen (name.c, stage 27): rows of 16 pixels, the status bar with the title, a
   line at the top for what is typed, four lines below it, the keypad at the bottom in four rows of three 41 x 15 keys,
   one pixel apart: 1 to 9, then Del, 0, OK. */
#define KEYS      12                     /* keys 0 to 8 are 1 to 9; then Del, 0, OK */
#define K_DEL     9
#define K_ZERO    10
#define K_OK      11
#define Y_QUERY   16                     /* the screen: status bar, query line, 4 result lines, 4 rows of keys */
#define Y_LIST    32
#define Y_KEYS    96
#define LINE      16
#define KEY_W     41                     /* a key, 41 x 15, one pixel apart (its texts start a row higher: keypad_key) */
#define KEY_H     15
#define DIGIT_W   12                     /* a key's digit centred in its first 12 pixels, */
#define LETTERS_W 30                     /* its letters in the last 30 ("wxyz" is 30 wide) */
#define TITLE_X   22                     /* the status bar's title, where the menus have theirs (stage 24) */
#define TITLE_W   76
#define TAG_SEARCH 0x8e                  /* the app timer tag while the screen shows (the SDK's tags end at 0x8d) */
#define SPACE_BAR_X 9                    /* the name screen's 0: a space bar (space_bar), 12 x 4, in the letters' place */
#define SPACE_BAR_Y 10
#define SPACE_BAR_W 12
#define KEY1_SIGNS ('-' | '.' << 8 | '&' << 16 | (u32)'\'' << 24)   /* the name screen's 1: its first four signs */
enum { KEYS_SEARCH, KEYS_NAME };        /* the keys' labels: the search's; the name screen's (1 with signs, 0 with a space bar) */

/* colours: ON(pen, background) */
#define ON(pen, back) ((u32)(pen) | (u32)(back) << 16)
/* a rectangle in a colour */
void fill(int x, int y, int w, int h, u32 colour);
/* A text of one line in a region 16 pixels high (UTF-16 with FF FE, UTF-8 with its mark, or one-byte text in the
   player's language); the driver paints a strip as wide as the text and 16 rows high in the background colour first. */
void text(const void *s, int room, int x, int y, int w, u32 colours, u32 mode);
/* up to four ASCII characters packed in a word (the first in the low byte) put at w[n]; the new n */
int put4(u16 *w, int n, u32 chars);
int digit_of(int k);                     /* the digit of key k, -1 for Del and OK */
/* the sign for the space: a line w wide at row y with ends 3 rows high above it */
void space_bar(int x, int y, int w, u32 colour);
/* key k of the keypad, in the accent if on, with the labels of KEYS_SEARCH or KEYS_NAME (always small letters: in
   capitals "pqrs" and "wxyz" are wider than their place) */
void keypad_key(int k, int on, int labels);

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
