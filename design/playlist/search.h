/* The search of stage 25 (search.c). */
#ifndef PLAYLIST_SEARCH_H
#define PLAYLIST_SEARCH_H
#include "fw.h"

/* "Search" in the options of a music list: the keypad screen over the list's current level; returns what the list
   option handler returns (RESULT_REDRAW, "Play", or a system message's result). */
u32 search_list(u8 *path_info);

#ifdef HOST
/* for the host test: whether the keys (digits 0 to 9) spell the beginning of a word of name, and the letters they
   spell there (UTF-16 with FF FE, into spelled[26]) */
int search_matches(const u8 *name, const u8 *keys, int n, u16 *spelled);
#endif
#endif
