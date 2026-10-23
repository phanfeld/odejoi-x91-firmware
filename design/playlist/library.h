/* M3U.LIB, kept up to date in place (library.c). Every function returns 0 / -1 on any error and then leaves the
 * file as it was, or readable. */
#ifndef PLAYLIST_LIBRARY_H
#define PLAYLIST_LIBRARY_H
#include "fw.h"

#define LISTS_MAX 50                     /* playlists the library holds */

uptr lib_open(void);                     /* the library, checked; 0 if there is none or it is not as expected */
void lib_close(uptr h);
/* the playlist record of the .m3u at p, or -1 */
int lib_find_list(uptr h, const place_t *p);
/* a new playlist record for the .m3u at p, named name[0 .. n) (one-byte text); its number, or -1 */
int lib_add_list(uptr h, const place_t *p, const u8 *name, int n);
/* the song at loc (the playing song's location) at the end of playlist list; name is its file name */
int lib_add_song(uptr h, int list, const u8 *loc, const u8 *name, int n);
/* the song at loc out of playlist list; 1 if it was in it */
int lib_remove_song(uptr h, int list, const u8 *loc);
int lib_lists(uptr h);                   /* the number of playlists */
/* the record at place k (from 0) of the order the Playlists list shows, or -1 */
int lib_order(uptr h, int k);
/* a playlist's .m3u place and name (UTF-16 with FF FE, 28 units; either may be 0) */
int lib_list(uptr h, int list, place_t *p, u16 *name);
/* stage 27: a playlist's record gets another .m3u place and name (UTF-16 with FF FE, cut to its 26 characters) */
int lib_set_list(uptr h, int list, const place_t *p, const u16 *name);
int lib_count(uptr h, int list);         /* its number of songs, or -1 */
/* the song at place pos (from 0) of a playlist: its number and place, or -1 */
int lib_song(uptr h, int list, int pos, place_t *p);
int lib_has_song(uptr h, int list, const u8 *loc);
/* the song at place from of a playlist moves to place to; the ones between move up or down */
int lib_move_song(uptr h, int list, int from, int to);
/* a playlist's record goes: the last record takes its number (its songs' lists of users follow) */
int lib_delete_list(uptr h, int list);

#endif
