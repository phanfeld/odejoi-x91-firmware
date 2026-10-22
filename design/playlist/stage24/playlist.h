/* What playlist.c shares with browse.c: the list of playlists, writing and taking out lines, the messages. */
#ifndef PLAYLIST_PLAYLIST_H
#define PLAYLIST_PLAYLIST_H
#include "fw.h"

#define ROWS        5                    /* rows on a page: the picker's list style (COMMON.STY list box 4) has 5 */
#define ROW_CHARS   21                   /* a shown playlist name and its zero */
#define LINE_MAX    192                  /* a song's path; room for the sync's longest names, see song_path_at */
#define MAX_ENTRIES 4000                 /* a guard for walking a folder */
#define BUF         128

enum { ADDED, ALREADY, FAILED, REMOVED, ABSENT };
enum { PICK_BACK = -1, PICK_PASS = -2, PICK_EMPTY = -3 };

static inline __attribute__((always_inline)) int is_m3u(u32 ext)
{
    u32 last = ext >> 24, a = ext & 0xff, c = (ext >> 16) & 0xff;
    return (a == 'M' || a == 'm') && ((ext >> 8) & 0xff) == '3' && (c == 'U' || c == 'u') && (last == 0 || last == ' ');
}

typedef struct list_s {                  /* a list screen (list_run) */
    u32 title;                           /* text id */
    int total, sel;                      /* rows; the chosen one, from 0 */
    int moving;                          /* Previous and Next move the chosen row, without going round */
    int extra, from;                     /* for the page function */
    /* fills rows top .. top+count-1: their text into rows[], or another descriptor into items[] */
    void (*page)(struct list_s *l, int top, u8 rows[ROWS][ROW_NAME + 2], strdesc_t *items, int count);
} list_t;

int entry_name(u8 *buf, int room, int whole);
int playlist_name(u8 *buf, int room);
int song_path_at(u8 *line, const void *layer, const void *offset);
int find_playlist(int index, int *count);
int find_new(int number);                /* the index of "New playlist <number>" (and stops on it), or -1 */
int list_run(list_t *l, u32 *result);
int pick(u32 *result, int extra);
int append(int index, int *number, u8 *line, int start);
int remove_line(int index, const u8 *path, int len);
void library_add(int index, int number, const u8 *name, const u8 *line, int start, const u8 *loc);
void choice_name(u8 *name, int choice, int number, int extra);
void to_wide(u16 *wide, const u8 *name);
u32 say(u32 text, const u8 *first, const u8 *second, int ask, int yes_first);
int pause_playing(void);

#endif
