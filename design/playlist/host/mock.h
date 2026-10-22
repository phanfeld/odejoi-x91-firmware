/* The simulated player of mock.c */
#ifndef PLAYLIST_MOCK_H
#define PLAYLIST_MOCK_H
#define MAX_NODES 64

struct node {
    char name[80];
    int parent, is_dir, gone, wide_char;
    u32 size, cap;
    char *data;
};

extern struct node nodes[MAX_NODES];
extern int node_count, calls_vfs, drawn_rows, last_active, last_total, last_title, dialogs, last_dialog_text;
extern int status, pauses, resumes, seeks, previous_songs, writes_while_playing;
extern int questions, last_default, removed_files, stops, stock_calls, source, refused_opens;
extern u32 answer;
enum { BROWSE_SONGS, BROWSE_M3U };
extern int browse_mode, m3u_cur, album_level, album, albums[16], album_count, rows_extra;
extern u32 last_seek[3], elapsed, engine_ms;
extern int background;
extern dir_brow_t level;
extern int last_style, last_mode, last_title_lang;
extern uptr box_result;
extern int list_test, bar_clears, last_clear_pic, last_clear_x, last_clear_y, cleared_first;
#define PICKER_LINES 5
extern char shown[6][64], last_message[256];
extern int events[64], event_count, event_next;

int add_node(int parent, const char *name, int is_dir, const char *data);
void node_room(int node, u32 size);
void reset_disk(void);
int tolower_ascii(int c);
int index_in(int dir, int node);
void layer_of(int dir, int entry, u8 *layer);
void play(int node);
void set_title(const char *t);
void position(int *dir, int *entry);
u32 add_playing_to_playlist(void *title_action);
u32 remove_playing_from_playlist(void *title_action);
void previous_key(void);
void standby_previous(void);
uptr list_box(style_t *st, listbox_t *data, u32 mode);
u32 list_option(u8 *path_info, u32 check, u32 active);
u32 m3u_option(u8 *path_info, u32 check, u32 active);
#endif
