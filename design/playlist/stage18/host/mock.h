/* The simulated player of mock.c */
#ifndef PLAYLIST_MOCK_H
#define PLAYLIST_MOCK_H
#define MAX_NODES 64

struct node {
    char name[80];
    int parent, is_dir, gone, wide_char;
    u32 size;
    char data[8192];
};

extern struct node nodes[MAX_NODES];
extern int paused, resumed, node_count, calls_vfs, drawn_rows, last_active, last_total, dialogs, last_dialog_text;
extern char shown[6][64], last_message[256];
extern int events[64], event_count, event_next;

int add_node(int parent, const char *name, int is_dir, const char *data);
void reset_disk(void);
int tolower_ascii(int c);
void play(int node);
void set_title(const char *t);
void position(int *dir, int *entry);
u32 add_playing_to_playlist(void *title_action);
#endif
