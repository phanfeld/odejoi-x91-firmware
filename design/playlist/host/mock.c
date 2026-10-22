/* The player's side of fw.h on the computer: a small disk in memory with the file system's position rules, a
 * queue of key events, the engine's states, and records of what was drawn and said. Used by test.c.
 * A file's place is (its folder's node, its own node), standing in for (cluster, entry): like a directory entry
 * on the disk it stays the same when other files go. */
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
int calls_vfs, drawn_rows, last_active, last_total, last_title, dialogs, last_dialog_text;
int questions, last_default, removed_files, stops, stock_calls, source, refused_opens;
u32 answer = RESULT_DIALOG_YES;
int status = PLAY_PLAYING, pauses, resumes, seeks, previous_songs, writes_while_playing;
u32 last_seek[3], elapsed, engine_ms;
int background = 1;                                         /* the music engine runs in the background */
dir_brow_t level;                                           /* the shared list control's browser state */
int last_style, last_mode, last_title_lang;                 /* what the file lists' last draw asked for */
uptr box_result;
int list_test;                                              /* the list style tests: every list style is drawn */
int bar_clears, last_clear_pic, last_clear_x, last_clear_y, cleared_first;   /* clear_bar: pictures drawn, and before the list? */
static int clear_pending;
char shown[6][64];
char last_message[256];
int events[64], event_count, event_next;

void node_room(int node, u32 size)
{
    struct node *n = &nodes[node];
    if (size <= n->cap)
        return;
    n->data = realloc(n->data, size);
    memset(n->data + n->cap, 0, size - n->cap);
    n->cap = size;
}

int add_node(int parent, const char *name, int is_dir, const char *data)
{
    struct node *n = &nodes[node_count];
    free(n->data);
    memset(n, 0, sizeof *n);
    snprintf(n->name, sizeof n->name, "%s", name);
    n->parent = parent;
    n->is_dir = is_dir;
    node_room(node_count, 8192);
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
    status = PLAY_PLAYING;
}

static int child(int dir, int k)                          /* the k-th entry of a folder, or -1 */
{
    int i, n = 0;
    for (i = 1; i < node_count; i++)
        if (nodes[i].parent == dir && !nodes[i].gone && n++ == k)
            return i;
    return -1;
}

int index_in(int dir, int node)
{
    int k;
    for (k = 0; child(dir, k) >= 0; k++)
        if (child(dir, k) == node)
            return k;
    return -1;
}

/* a folder chain that tells places apart, with the depth in byte 72 as the real one has it */
void layer_of(int dir, int entry, u8 *layer)
{
    int k, depth = 0, d;
    for (d = dir; d > 0; d = nodes[d].parent)
        depth++;
    for (k = 0; k < 72; k++)
        layer[k] = (u8)(dir * 7 + entry * 3 + k);
    layer[72] = (u8)depth;
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

/* The player lets a program hold only few files open (stage 21's "Move song" failed with two on the player), so
 * the new code must never hold more than one: a second open is refused. */
static int new_handle(int node)
{
    int i;
    for (i = 1; i < 8; i++)
        if (handles[i].open) {
            refused_opens++;
            return 0;
        }
    handles[1].open = 1;
    handles[1].node = node;
    handles[1].pos = 0;
    return 1;
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
            e = child(cur_dir, cur_entry);
            off[0] = (u32)cur_dir;
            off[1] = (u32)e;
            if (a)
                layer_of(cur_dir, e, (u8 *)a);
            return 1;
        }
        if (off[0] >= (u32)node_count || !nodes[off[0]].is_dir)
            return 0;
        cur_dir = (int)off[0];
        cur_entry = off[1] < (u32)node_count && nodes[off[1]].parent == cur_dir ? index_in(cur_dir, (int)off[1]) : -1;
        return 1;
    }
    case VFS_REMOVE:
        for (k = 0; (e = child(cur_dir, k)) >= 0; k++)
            if (!nodes[e].is_dir && same_name(nodes[e].name, (const u16 *)a) && b == FS_FILE) {
                nodes[e].gone = 1;
                removed_files++;
                cur_entry = -1;
                return 1;
            }
        return 0;
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
        for (k = 1; k < 8; k++)
            if (handles[k].open) {
                refused_opens++;
                return 0;
            }
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
        if (status == PLAY_PLAYING)
            writes_while_playing++;
        node_room(handles[c].node, handles[c].pos + (u32)b);
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

/* ------------------------------------------------------------------ the screen the search draws (stage 25) */

u32 pen = 0xffff, backgd;
struct screen_text texts[MAX_TEXTS];
int text_count, fills, strings, tag_while_drawing = -1;
FILE *draw_log;
static u32 filled[160][128];                            /* the colour each pixel was last filled with */

/* a string as the driver gets it, as plain text: UTF-16 (FF FE) and UTF-8 (EF BB BF) beyond ASCII as '?', and the
   ellipsis U+2026 as "~" */
static void as_plain(char *out, int room, const strdesc_t *d)
{
    const u8 *t = (const u8 *)d->str;
    int i = 0, n = 0;
    if (t[0] == 0xff && t[1] == 0xfe) {
        for (i = 2; i + 1 < d->length && (t[i] || t[i + 1]) && n < room - 1; i += 2)
            out[n++] = t[i + 1] ? (t[i] == 0x26 && t[i + 1] == 0x20 ? '~' : '?') : (char)t[i];
    } else {
        for (i = t[0] == 0xef && t[1] == 0xbb && t[2] == 0xbf ? 3 : 0; i < d->length && t[i] && n < room - 1; i++)
            out[n++] = t[i] < 0x80 ? (char)t[i] : '?';
    }
    out[n] = 0;
}

/* A fill covers what was drawn there: a text whose left edge it covers, and the rows of the glyphs (rows 4 to 15 of
   the 16-row cell: ascenders from row 4, descenders down to row 15). */
static void forget_texts(int x, int y, int w, int h)
{
    int i, k = 0;
    for (i = 0; i < text_count; i++)
        if (!(texts[i].x >= x && texts[i].x < x + w && texts[i].y + 4 < y + h && texts[i].y + 16 > y))
            texts[k++] = texts[i];
    text_count = k;
}

static void search_draw(uptr a, uptr b, uptr c, int cmd)
{
    if (cmd == UI_DC_GET) {
        ((u32 *)a)[0] = pen;
        ((u32 *)a)[1] = backgd;
    } else if (cmd == UI_PEN) {
        pen = (u32)a;
    } else if (cmd == UI_BACKGD) {
        backgd = (u32)a;
    } else if (cmd == UI_CLEAR) {
        const region_t *r = (const region_t *)a;
        if (!r || r->x + r->w > 128 || r->y + r->h > 160 || !r->w || !r->h)
            fprintf(stderr, "a fill outside the screen\n"), exit(2);
        fills++;
        forget_texts(r->x, r->y, r->w, r->h);
        for (int y = r->y; y < r->y + r->h; y++)
            for (int x = r->x; x < r->x + r->w; x++)
                filled[y][x] = backgd;
        if (draw_log)
            fprintf(draw_log, "fill %d %d %d %d %#x\n", r->x, r->y, r->w, r->h, backgd);
    } else if (cmd == UI_STRING) {
        const strdesc_t *d = (const strdesc_t *)a;
        const region_t *r = (const region_t *)b;
        const u8 *t = (const u8 *)d->str;
        int i;
        if (tag_while_drawing < 0)
            tag_while_drawing = *timer_tag();
        if ((c & 3) != DRAW_DOTS || !(c & NO_ARABIC) || r->h != 16 || r->x + r->w > 131 || d->length > 200
            || (d->lang == TEXT_UTF16) != (t[0] == 0xff && t[1] == 0xfe))
            fprintf(stderr, "a string drawn with mode %#x in %d,%d %dx%d\n", (unsigned)c, r->x, r->y, r->w, r->h), exit(2);
        strings++;
        for (i = 0; i < text_count && (texts[i].x != r->x || texts[i].y != r->y); i++)
            ;
        if (i == text_count && text_count < MAX_TEXTS)
            text_count++;
        if (i < MAX_TEXTS) {
            texts[i].x = r->x;
            texts[i].y = r->y;
            texts[i].w = r->w;
            texts[i].colour = pen;
            texts[i].mode = (u32)c;
            as_plain(texts[i].s, sizeof texts[i].s, d);
        }
        if (draw_log) {
            fprintf(draw_log, "text %d %d %d %d %#x %#x %d ", r->x, r->y, r->w, r->h, pen, (unsigned)c, d->lang);
            for (i = 0; i < d->length && (t[i] || (d->lang == TEXT_UTF16 && i + 1 < d->length && t[i + 1])); i += d->lang == TEXT_UTF16 ? 2 : 1)
                fprintf(draw_log, d->lang == TEXT_UTF16 ? "%02x%02x" : "%02x", t[i], d->lang == TEXT_UTF16 ? t[i + 1] : 0);
            fprintf(draw_log, "\n");
        }
    }
}

/* the text drawn with its left edge at x in the line starting at y ("" if none) */
const char *text_at(int x, int y)
{
    int i;
    for (i = 0; i < text_count; i++)
        if (texts[i].x == x && texts[i].y == y)
            return texts[i].s;
    return "";
}

/* the colour the pixel at x, y was last filled with */
long fill_at(int x, int y) { return (long)filled[y][x]; }

/* the colour the text at x, y was drawn in, or -1 */
long colour_at(int x, int y)
{
    int i;
    for (i = 0; i < text_count; i++)
        if (texts[i].x == x && texts[i].y == y)
            return (long)texts[i].colour;
    return -1;
}

uptr ui(uptr a, uptr b, uptr c, int cmd)
{
    if (cmd >= UI_DC_GET && cmd <= UI_STRING) {
        search_draw(a, b, c, cmd);
        return 1;
    }
    if (cmd == UI_PICTURE) {
        if (draw_log)
            fprintf(draw_log, "picture %#x %d %d\n", (unsigned)a, (int)b, (int)c);
        bar_clears++;
        last_clear_pic = (int)a;
        last_clear_x = (int)b;
        last_clear_y = (int)c;
        clear_pending = 1;
        return 0;
    }
    if (cmd == UI_LISTBOX && list_test) {
        listbox_t *box = (listbox_t *)b;
        if (a && ((style_t *)a)->type != 1)                              /* COMMON.STY */
            fprintf(stderr, "list: style type %d\n", ((style_t *)a)->type), exit(2);
        last_style = a ? ((style_t *)a)->id : -1;
        last_mode = (int)c;
        last_title = box ? (int)(box->title.str & 0xffff) : -1;
        last_title_lang = box ? box->title.lang : -1;
        cleared_first = clear_pending;
        clear_pending = 0;
        return box_result;
    }
    if (cmd == UI_LISTBOX) {
        listbox_t *box = (listbox_t *)b;
        int r;
        /* the list style the new code uses (COMMON.STY list box 4) has 5 lines; the firmware draws a 6th row over
           the first one (seen on the player, stage 22) */
        if (((style_t *)a)->id != STYLE_PICKER || box->valid > PICKER_LINES || (box->valid && box->active >= box->valid))
            fprintf(stderr, "list box: style %#x, %d rows, active %d\n", ((style_t *)a)->id, box->valid, box->active), exit(2);
        if ((int)c == LIST_DRAW_ALL ? !clear_pending || last_clear_pic != BAR_CLEAR || last_clear_x != BAR_CLEAR_X || last_clear_y
                                    : clear_pending)
            fprintf(stderr, "list box: mode %d, the bar's middle %s\n", (int)c, clear_pending ? "cleared" : "not cleared"), exit(2);
        clear_pending = 0;
        drawn_rows = box->valid;
        last_active = box->active;
        last_total = box->total;
        last_title = (int)(box->title.str & 0xffff);
        for (r = 0; r < 6; r++) {
            const u8 *t = r < box->valid ? (const u8 *)box->items[r].str : (const u8 *)"";
            if (t[0] == 0xff && t[1] == 0xfe) {        /* UTF-16 rows: shown as one-byte text */
                int i;
                for (i = 0; i < 63 && (t[2 + 2 * i] || t[3 + 2 * i]); i++)
                    shown[r][i] = (char)t[2 + 2 * i];
                shown[r][i] = 0;
            } else {
                snprintf(shown[r], sizeof shown[r], "%s", (const char *)t);
            }
        }
        if (box->title.lang != TEXT_ID || (last_title != S_ADD_TO_PLAYLIST && last_title != S_REMOVE_FROM && last_title != S_MOVE))
            fprintf(stderr, "wrong list title\n"), exit(2);
    }
    (void)c;
    return 0;
}

void delay_tick(void) {}

/* The key queue holds menu events (the menu key table's), or for the search raw key messages (RAW_KEY), stretches
   with no message (IDLE: the search goes on in them), and marks for the draw log (SNAP). */
int raw_keys, idle_left, volume_popups, app_result;
static int app_pending;

int get_gui_msg(void *msg)
{
    u8 *m = msg;
    int e;

    if (idle_left > 0) {
        idle_left--;
        return 0;
    }
    if (event_next >= event_count) {                       /* nothing left: leave the list */
        if (raw_keys)
            fprintf(stderr, "the search ran out of keys\n"), exit(2);
        *(int *)msg = EV_BACK;
        return 1;
    }
    e = events[event_next++];
    if (e & SNAP_EVENT) {
        if (draw_log)
            fprintf(draw_log, "snapshot %d\n", e & 0xffff);
        return get_gui_msg(msg);
    }
    if (e & APP_EVENT) {                                   /* a system message comes instead */
        app_pending = 1;
        app_result = e & 0xffff;
        return 0;
    }
    if (e & IDLE_EVENT) {
        idle_left = (e & 0xffffff) - 1;
        return 0;
    }
    if (e & RAW_EVENT) {
        memset(m, 0, 8);
        m[2] = (u8)(e >> 16);
        m[4] = (u8)e;
        m[5] = (u8)(e >> 8);
        return 1;
    }
    *(int *)msg = e;
    return 1;
}

int get_app_msg(void *msg)
{
    (void)msg;
    if (!app_pending)
        return 0;
    app_pending = 0;
    return 1;
}

u32 app_dispatch(void *msg) { (void)msg; return (u32)app_result; }

int key_mapping(void *msg, u16 *event)
{
    const u8 *m = msg;
    if (raw_keys) {                                        /* the volume key, as the common key table has it */
        if (m[2] == 0x0a && (m[4] | m[5] << 8) & KT_SHORT_UP) {
            *event = 0x2801;
            return 1;
        }
        return 0;
    }
    *event = (u16)*(int *)msg;
    return 1;
}

u32 message_box(u32 event)
{
    if (event == 0x2801) {                                 /* the volume pop-up, drawn over the screen */
        volume_popups++;
        text_count = 0;
        return RESULT_REDRAW;
    }
    return 0;
}

/* a text as one-byte text, whatever its encoding (UTF-16 with FF FE, else bytes) */
static void plain(char *out, int room, const u8 *t)
{
    int i = 0;
    if (!t) {
        out[0] = 0;
        return;
    }
    if (t[0] == 0xff && t[1] == 0xfe) {
        for (; i < room - 1 && (t[2 + 2 * i] || t[3 + 2 * i]); i++)
            out[i] = (char)t[2 + 2 * i];
        out[i] = 0;
    } else {
        snprintf(out, (size_t)room, "%s", (const char *)t);
    }
}

void string_format(strdesc_t *dest, strdesc_t *src)
{
    char a[64], b[64];
    plain(a, sizeof a, (const u8 *)src[0].str);
    plain(b, sizeof b, (const u8 *)src[1].str);
    snprintf(last_message, sizeof last_message, "text %u: \"%s\", %s", dest->argv, a, b);
}

u32 dialog(u32 style, dialog_t *d)
{
    dialogs++;
    last_dialog_text = ((strdesc_t *)d->text)->argv;
    if (style == 0x8002) {                             /* a question */
        questions++;
        last_default = d->active;
        return answer;
    }
    return 0;
}
u32 dialog_text(u32 style, u32 type, u32 text_id) { (void)style; (void)type; dialogs++; last_dialog_text = (int)text_id; return 0; }
void refresh_path(void) {}
void headbar_all(void) {}
void list_prepare(style_t *st) { (void)st; }
int back_flag(void) { return 0; }
s8 language(void) { return 1; }
u8 *song_location(void) { return location; }
u8 *song_title(void) { return title; }
u8 *temp_buffer(void) { return temp; }

int engine_status(void) { return status; }
void engine_pause(void)
{
    pauses++;
    if (status == PLAY_PLAYING)
        status = PLAY_PAUSED;
}
void engine_resume(void) { resumes++; status = PLAY_PLAYING; }
void engine_seek(u32 *bp)
{
    seeks++;
    memcpy(last_seek, bp, sizeof last_seek);
    status = PLAY_PLAYING;
    elapsed = engine_ms = bp[0];
}
void previous_song(void) { previous_songs++; }
void engine_stop(void) { stops++; status = PLAY_STOPPED; }
int playing_source(void) { return source; }
volatile u32 *elapsed_ms(void) { return &elapsed; }
u32 engine_time(void) { return engine_ms; }
int music_playing(void) { return background; }
const dir_brow_t *list_level(void) { return &level; }

void play(int node)
{
    int dir = nodes[node].parent;
    u32 *p = (u32 *)(location + LOC_CLUSTER);
    memcpy(location + LOC_EXT, "MP3", 4);
    p[0] = (u32)dir;
    p[1] = (u32)node;
    layer_of(dir, node, location + LOC_LAYER);
    source = 0;
}

void set_title(const char *t) { snprintf((char *)title, sizeof title, "%s", t); }

void position(int *dir, int *entry)
{
    *dir = cur_dir;
    *entry = cur_entry;
}

/* ------------------------------------------------------------------ the list browser */

int browse_mode, m3u_cur = 0xffff, album_level, album, albums[16], album_count, rows_extra;
static int selected = -1, scan_pos;
static u8 path_info[128];

static u32 le16(const u8 *d, u32 o) { return d[o] | (u32)d[o + 1] << 8; }

static const u8 *libdata(void)
{
    int i;
    for (i = 1; i < node_count; i++)
        if (nodes[i].parent == 0 && !nodes[i].gone && !strcmp(nodes[i].name, "M3U.LIB"))
            return (const u8 *)nodes[i].data;
    return 0;
}

static int album_song(int a, int k)                     /* the k-th song (from 0) of album node a */
{
    int i, n = 0;
    for (i = 1; i < node_count; i++)
        if (nodes[i].parent == a && !nodes[i].gone && !nodes[i].is_dir && n++ == k)
            return i;
    return -1;
}

static int album_songs(int a)
{
    int n = 0;
    while (album_song(a, n) >= 0)
        n++;
    return n;
}

static int m3u_song(int row)                            /* the song record of row (from 1) in playlist m3u_cur */
{
    const u8 *d = libdata();
    if (!d || row < 1 || (u32)row > le16(d, 0xa2 + 2 * (u32)m3u_cur))
        return -1;
    return (int)(le16(d, 0x4a00 + (u32)m3u_cur * 0x2000 + 2 * (u32)(row - 1)) & 0x7fff);
}

int browser_enter_dir(int type, int list_no, dir_brow_t *b)
{
    const u8 *d = libdata();
    if (browse_mode == BROWSE_M3U) {
        if (type == BROW_SON && m3u_cur == 0xffff && d)
            m3u_cur = (int)le16(d, le16(d, 0x24) * 512 + 2 * (u32)(list_no - 1));
        else if (type == BROW_PARENT)
            m3u_cur = 0xffff;
        b->dir_total = (u16)(m3u_cur == 0xffff && d ? le16(d, 8) : 0);
        b->file_total = (u16)(m3u_cur != 0xffff && d ? le16(d, 0xa2 + 2 * (u32)m3u_cur) : 0);
        b->layer_no = m3u_cur != 0xffff;
        b->file_total = (u16)(b->file_total + rows_extra);
    } else if (browse_mode == BROWSE_NAMES) {
        b->dir_total = (u16)name_dirs;
        b->file_total = (u16)(name_count - name_dirs);
        b->layer_no = 0;
    } else {
        if (type == BROW_SON && !album_level) {
            album_level = 1;
            album = albums[list_no - 1];
        } else if (type == BROW_PARENT) {
            album_level = 0;
        }
        b->dir_total = (u16)(album_level ? 0 : album_count);
        b->file_total = (u16)(album_level ? album_songs(album) : 0);
        b->layer_no = (u8)album_level;
    }
    return 1;
}

/* BROWSE_NAMES (the search tests): one level of rows given by their names' bytes; rows 1 .. name_dirs have lists
   below them */
struct name_row name_rows[MAX_NAME_ROWS];
int name_count, name_dirs, items_calls, items_rows;

static void row_bytes(int row, u8 *out)                 /* out: 128 zero bytes */
{
    const u8 *d = libdata();
    int s;
    if (browse_mode == BROWSE_NAMES) {
        if (row >= 1 && row <= name_count)
            memcpy(out, name_rows[row - 1].b, (size_t)name_rows[row - 1].n);
    } else if (browse_mode == BROWSE_M3U && m3u_cur == 0xffff && d) {
        u32 rec = le16(d, le16(d, 0x24) * 512 + 2 * (u32)(row - 1));
        memcpy(out, d + 0x200 + rec * 256, 56);
    } else if (browse_mode == BROWSE_M3U) {
        s = m3u_song(row);
        if (s >= 0)
            snprintf((char *)out, 128, "%s", (const char *)d + 0x68a00 + (u32)s * 256);
    } else if (!album_level) {
        snprintf((char *)out, 128, "%s", nodes[albums[row - 1]].name);
    } else {
        s = album_song(album, row - 1);
        if (s >= 0)
            snprintf((char *)out, 128, "%s", nodes[s].name);
    }
}

/* As the library's (MUSIC.AP 0x1c93100c): num rows from row top, each name cut to name_len - 2 bytes and ended by
   two zeros. */
int browser_get_items(brow_decode_t *dd, file_brow_t *f)
{
    u8 tmp[128];
    int k, n;
    if (!dd->num || !dd->top)
        return 0;
    items_calls++;
    for (k = 0; k < dd->num; k++) {
        if (f[k].name_len < 2 || f[k].name_len > 58)
            fprintf(stderr, "a row's name buffer of %d bytes\n", f[k].name_len), exit(2);
        memset(tmp, 0, sizeof tmp);
        row_bytes(dd->top + k, tmp);
        n = f[k].name_len - 2;
        memcpy((u8 *)f[k].name_buf, tmp, (size_t)n);
        ((u8 *)f[k].name_buf)[n] = ((u8 *)f[k].name_buf)[n + 1] = 0;
        items_rows++;
    }
    return 1;
}

int browser_select(int list_no)
{
    selected = list_no;
    return list_no >= 1;
}

static void song_loc(u8 *loc, int node)
{
    memset(loc, 0, 100);
    memcpy(loc + LOC_EXT, "MP3", 4);
    *(u32 *)(loc + LOC_CLUSTER) = (u32)nodes[node].parent;
    *(u32 *)(loc + LOC_ENTRY) = (u32)node;
    layer_of(nodes[node].parent, node, loc + LOC_LAYER);
}

int browser_get_location(u8 *loc, int type)
{
    const u8 *d = libdata();
    int s;
    if (type == FSEL_M3U && browse_mode == BROWSE_M3U && m3u_cur != 0xffff) {
        s = m3u_song(selected);
        if (s < 0)
            return 0;
        memset(loc, 0, 100);
        memcpy(loc + LOC_EXT, "MP3", 4);
        memcpy(loc + LOC_CLUSTER, d + 0x68a00 + (u32)s * 256 + 0x9c, 8);
        memcpy(loc + LOC_LAYER, d + 0x68a00 + (u32)s * 256 + 0xa8, 73);
        return 1;
    }
    if (type == FSEL_PLAYLIST && browse_mode == BROWSE_SONGS && album_level) {
        s = album_song(album, selected - 1);
        if (s < 0)
            return 0;
        song_loc(loc, s);
        return 1;
    }
    return 0;
}

int browser_scan_init(dir_brow_t *b)
{
    (void)b;
    scan_pos = 0;
    return 1;
}

int browser_scan(u8 *pi, dir_brow_t *b, int type)
{
    int s = album_level ? album_song(album, scan_pos++) : -1;
    (void)type;
    if (s < 0)
        return SCAN_SELF;
    song_loc(pi + 4, s);
    b->layer_no = 1;
    return SCAN_FILE;
}

u8 *browse_path(void) { return path_info; }
int m3u_list(void) { return m3u_cur; }
u32 last_stock_check, last_stock_active, last_stock_m3u;
u32 stock_list_result(u8 *pi, u32 check, u32 active)
{
    (void)pi;
    stock_calls++;
    last_stock_check = check;
    last_stock_active = active;
    last_stock_m3u = 0;
    return check;
}
u32 stock_m3u_result(u8 *pi, u32 check, u32 active)
{
    (void)pi;
    stock_calls++;
    last_stock_check = check;
    last_stock_active = active;
    last_stock_m3u = 1;
    return check;
}

/* ------------------------------------------------------------------ the list control (stage 25) */

dirctl_t dirctl;
int menu_count, selects, selected_row;
static u8 tag = 0x84;                                   /* the list control's timer tag */

dirctl_t *dir_control(void) { return &dirctl; }
int menu_rows(void) { return menu_count; }
u8 *timer_tag(void) { return &tag; }

/* the control's Select: it reads the chosen row's line on the page, so the state has to agree with itself */
u32 dir_select(u8 *pi, dirctl_t *dc)
{
    (void)pi;
    if (dc != &dirctl || dc->active < 1 || dc->active > dc->page || dc->old != dc->active || dc->top < 1
        || dc->list_no != dc->top + dc->active - 1 || dc->bottom < dc->list_no || dc->bottom > dc->total
        || dc->bottom - dc->top + 1 > dc->page || dc->list_no <= menu_count)
        fprintf(stderr, "Select with a list state that does not agree with itself\n"), exit(2);
    selects++;
    selected_row = dc->list_no - menu_count;
    return 0;
}

/* a fresh screen for the next search test */
void screen_reset(void)
{
    text_count = fills = strings = 0;
    tag_while_drawing = -1;
    clear_pending = 0;
    idle_left = 0;
    items_calls = items_rows = 0;
}
