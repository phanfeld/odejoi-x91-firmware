/* The player's side of fw.h on the computer: a small disk in memory with the file system's position rules, a
 * queue of key events, and records of what was drawn and said. Used by test.c. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../fw.h"
#include "mock.h"

struct node nodes[MAX_NODES];
int node_count;
static int cur_dir, cur_entry = -1;
static struct { int node; u32 pos; int open; } handles[8];

static u8 location[128], title[96], temp[256];
int paused, resumed, calls_vfs, drawn_rows, last_active, last_total, dialogs, last_dialog_text;
char shown[6][64];
char last_message[256];
int events[64], event_count, event_next;

int add_node(int parent, const char *name, int is_dir, const char *data)
{
    struct node *n = &nodes[node_count];
    memset(n, 0, sizeof *n);
    snprintf(n->name, sizeof n->name, "%s", name);
    n->parent = parent;
    n->is_dir = is_dir;
    if (data) {
        n->size = (u32)strlen(data);
        memcpy(n->data, data, n->size);
    }
    return node_count++;
}

void reset_disk(void)
{
    node_count = 0;
    add_node(-1, "", 1, NULL);
    cur_dir = 0;
    cur_entry = -1;
    memset(handles, 0, sizeof handles);
}

static int child(int dir, int k)                          /* the k-th entry of a folder, or -1 */
{
    int i, n = 0;
    for (i = 1; i < node_count; i++)
        if (nodes[i].parent == dir && !nodes[i].gone && n++ == k)
            return i;
    return -1;
}

static int index_in(int dir, int node)
{
    int k;
    for (k = 0; child(dir, k) >= 0; k++)
        if (child(dir, k) == node)
            return k;
    return -1;
}

static int same_name(const char *a, const u16 *w)
{
    int i;
    if (w[0] != 0xfeff)
        return 0;
    for (i = 0; a[i]; i++)
        if (w[i + 1] > 0xff || tolower_ascii(a[i]) != tolower_ascii((char)w[i + 1]))
            return 0;
    return w[i + 1] == 0;
}

int tolower_ascii(int c) { return c >= 'A' && c <= 'Z' ? c + 32 : c; }

static u32 ext_of(const char *name)
{
    const char *d = strrchr(name, '.');
    u32 e = 0;
    int i;
    if (!d)
        return 0x20202020u;                                /* a file without an extension still counts */
    for (i = 0; i < 3 && d[1 + i]; i++)
        e |= (u32)(d[1 + i] >= 'a' && d[1 + i] <= 'z' ? d[1 + i] - 32 : d[1 + i]) << (8 * i);
    return e;
}

static int new_handle(int node)
{
    int i;
    for (i = 1; i < 8; i++)
        if (!handles[i].open) {
            handles[i].open = 1;
            handles[i].node = node;
            handles[i].pos = 0;
            return i;
        }
    fprintf(stderr, "out of handles\n");
    exit(2);
}

uptr vfs(uptr a, uptr b, uptr c, int cmd)
{
    int e, k;
    calls_vfs++;
    switch (cmd) {
    case VFS_CD:
        if (a == CD_ROOT) {
            cur_dir = 0;
            cur_entry = -1;
            return 1;
        }
        if (a == CD_BACK) {
            if (cur_dir == 0)
                return 0;
            cur_entry = index_in(nodes[cur_dir].parent, cur_dir);
            cur_dir = nodes[cur_dir].parent;
            return 1;
        }
        return 0;
    case VFS_DIR:
        for (k = a == DIR_HEAD ? 0 : cur_entry + 1; (e = child(cur_dir, k)) >= 0; k++) {
            if (c == EXT_ALL_FILES && !nodes[e].is_dir) {
                cur_entry = k;
                return ext_of(nodes[e].name);
            }
        }
        return 0;
    case VFS_GET_NAME: {
        u16 *w = (u16 *)a;
        int units = (int)b, i, n;
        e = child(cur_dir, cur_entry);
        if (e < 0)
            return 0;
        n = (int)strlen(nodes[e].name);
        if (units > 0)
            w[0] = 0xfeff;
        for (i = 0; i < n && i + 1 < units; i++)
            w[i + 1] = (u8)nodes[e].name[i];
        if (nodes[e].wide_char && n > 2 && 3 < units)
            w[3] = 0x4e2d;                                 /* a CJK character, for the test of names that are not one-byte text */
        if (n + 1 < units)
            w[n + 1] = 0;
        return (uptr)(n + 2);
    }
    case VFS_OFFSET: {
        u32 *off = (u32 *)b;
        if (c == 0) {
            off[0] = (u32)cur_dir;
            off[1] = (u32)cur_entry;
            if (a)
                memset((void *)a, 0x5a, 74);
            return 1;
        }
        if (off[0] >= (u32)node_count || !nodes[off[0]].is_dir)
            return 0;
        cur_dir = (int)off[0];
        cur_entry = (int)off[1];
        return 1;
    }
    case VFS_OPEN:
        if (!a) {
            e = child(cur_dir, cur_entry);
            return e >= 0 && !nodes[e].is_dir ? (uptr)new_handle(e) : 0;
        }
        for (k = 0; (e = child(cur_dir, k)) >= 0; k++)
            if (!nodes[e].is_dir && same_name(nodes[e].name, (const u16 *)a)) {
                cur_entry = k;
                return (uptr)new_handle(e);
            }
        return 0;
    case VFS_CREATE: {
        const u16 *w = (const u16 *)a;
        char name[80];
        int i;
        for (i = 0; w[i + 1] && i < 79; i++)
            name[i] = (char)w[i + 1];
        name[i] = 0;
        e = add_node(cur_dir, name, 0, NULL);
        cur_entry = index_in(cur_dir, e);
        return (uptr)new_handle(e);
    }
    case VFS_CLOSE:
        handles[a].open = 0;
        return 1;
    case VFS_SIZE:
        *(u32 *)a = nodes[handles[b].node].size;
        return 1;
    case VFS_SEEK:
        handles[c].pos = (u32)a;
        return 1;
    case VFS_READ: {
        struct node *n = &nodes[handles[c].node];
        u32 got = handles[c].pos >= n->size ? 0 : n->size - handles[c].pos;
        if (got > b)
            got = (u32)b;
        memcpy((void *)a, n->data + handles[c].pos, got);
        handles[c].pos += got;
        return got;
    }
    case VFS_WRITE: {
        struct node *n = &nodes[handles[c].node];
        memcpy(n->data + handles[c].pos, (void *)a, b);
        handles[c].pos += (u32)b;
        if (handles[c].pos > n->size)
            n->size = handles[c].pos;
        return b;
    }
    }
    fprintf(stderr, "unexpected file system command %d\n", cmd);
    exit(2);
}

uptr ui(uptr a, uptr b, uptr c, int cmd)
{
    (void)a;
    if (cmd == UI_LISTBOX) {
        listbox_t *box = (listbox_t *)b;
        int r;
        drawn_rows = box->valid;
        last_active = box->active;
        last_total = box->total;
        for (r = 0; r < 6; r++)
            snprintf(shown[r], sizeof shown[r], "%s", r < box->valid ? (char *)box->items[r].str : "");
        if (box->title.lang != TEXT_ID || (box->title.str & 0xffff) != S_ADD_TO_PLAYLIST)
            fprintf(stderr, "wrong list title\n"), exit(2);
    }
    (void)c;
    return 0;
}

void delay_tick(void) {}

int get_gui_msg(void *msg)
{
    if (event_next >= event_count) {                       /* nothing left: leave the list */
        *(int *)msg = EV_BACK;
        return 1;
    }
    *(int *)msg = events[event_next++];
    return 1;
}

int get_app_msg(void *msg) { (void)msg; return 0; }
u32 app_dispatch(void *msg) { (void)msg; return 0; }
int key_mapping(void *msg, u16 *event) { *event = (u16)*(int *)msg; return 1; }
u32 message_box(u32 event) { (void)event; return 0; }

void string_format(strdesc_t *dest, strdesc_t *src)
{
    char a[64] = "", b[64] = "";
    const u16 *w = (const u16 *)src[1].str;
    int i;
    for (i = 0; w[i + 1] && i < 63; i++)
        b[i] = (char)w[i + 1];
    snprintf(a, sizeof a, "%s", (char *)src[0].str);
    snprintf(last_message, sizeof last_message, "text %u: \"%s\" added to %s!", dest->argv, a, b);
}

u32 dialog(u32 style, dialog_t *d) { (void)style; (void)d; dialogs++; last_dialog_text = 12; return 0; }
u32 dialog_text(u32 style, u32 type, u32 text_id) { (void)style; (void)type; dialogs++; last_dialog_text = (int)text_id; return 0; }
void refresh_path(void) {}
void headbar_all(void) {}
void list_prepare(style_t *st) { (void)st; }
int back_flag(void) { return 0; }
s8 language(void) { return 1; }
u8 *song_location(void) { return location; }
u8 *song_title(void) { return title; }
u8 *temp_buffer(void) { return temp; }
int engine_status(void) { return 2; }
void engine_pause(void) { paused++; }
void engine_resume(void) { paused--; resumed++; }

void play(int node)
{
    u32 *p = (u32 *)(location + 8);
    p[0] = (u32)nodes[node].parent;
    p[1] = (u32)index_in(nodes[node].parent, node);
}

void set_title(const char *t) { snprintf((char *)title, sizeof title, "%s", t); }

void position(int *dir, int *entry)
{
    *dir = cur_dir;
    *entry = cur_entry;
}
