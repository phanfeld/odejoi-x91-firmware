/* The playlist actions in the options of the playing screen (Graphite stages 18 and 20).
 *
 * "Add to playlist" opens a list of the .m3u files in the root folder with "New playlist" on top. Choosing a
 * playlist appends the playing song's path to it in the form the sync writes ("Music\Artist\Album\01 - Title.mp3",
 * CR LF); "New playlist" creates "New playlist N.m3u" with the first free N. A song that is in the playlist
 * already is not added again.
 *
 * "Remove from Playlist" (stage 20) opens the same list without "New playlist"; choosing a playlist takes every
 * line with the playing song's path out of it. The file keeps its size: the lines behind move up, and the bytes
 * left over become one comment line at the end ("#" and spaces), which readers of .m3u files skip. Such a line
 * from an earlier removal is taken into the new one, so there is never more than one.
 *
 * Since stage 20 both also bring the playlist library M3U.LIB up to date (library.c), so the Playlists list shows
 * the change without "Update list?". Messages in the player's language say what happened (MUSIC.STY texts 11,
 * 12, 14 and 27, COMMON.STY 26 and 36).
 *
 * The build (design/graphite/newcode.py) puts this into free room at the end of code banks of MUSIC.AP. Code there has no
 * global or static data and no string constants (constant text is built in code) and calls no library. Its
 * buffers are on the stack (the program's task has about 3 KB): the RAM from 0x101000 on, where the menus keep
 * their scratch data, is also where code banks are loaded, so data put there does not survive a call into
 * another bank. While files are read and written, a playing song is paused and then resumed, as with the Play
 * key; the engine reads the same storage.
 */
#include "fw.h"
#include "util.h"
#include "library.h"
#include "playlist.h"

#define MAX_DEPTH   9                    /* folder levels the file system supports */
#define NEW_MAX     99                   /* "New playlist 1" to "New playlist 99" */
#define MAX_CUTS    8                    /* lines one removal takes out */

/* "New playlist" in one-byte text; returns its length */
static int new_playlist_text(u8 *t)
{
    t[0] = 'N'; t[1] = 'e'; t[2] = 'w'; t[3] = ' '; t[4] = 'p'; t[5] = 'l';
    t[6] = 'a'; t[7] = 'y'; t[8] = 'l'; t[9] = 'i'; t[10] = 's'; t[11] = 't';
    return 12;
}

/* " N" after "New playlist"; returns the new length */
static int append_number(u8 *t, int n, int number)
{
    t[n++] = ' ';
    if (number >= 10)
        t[n++] = (u8)('0' + number / 10);
    t[n++] = (u8)('0' + number % 10);
    return n;
}

/* ------------------------------------------------------------------ names and paths */

/* The name of the entry the file system stands on, as one-byte text: the long name if there is one (the sync
 * writes ASCII; characters up to 0xff pass as code page 1252), else the 8.3 name. buf must be 2-aligned and room
 * at least 24. With whole set, a name that is cut or has a character above 0xff gives 0; otherwise such a name is
 * shown cut or with '?'. Returns the length. */
int entry_name(u8 *buf, int room, int whole)
{
    u16 *w = (u16 *)buf;
    int units = room / 2, n = 0, i;

    set_bytes(buf, 0, units * 2);
    vfs((uptr)buf, units, 0, VFS_GET_NAME);
    if (buf[0] == 0xff && buf[1] == 0xfe) {
        for (i = 1; i < units && w[i]; i++) {           /* byte n is written behind unit i, which is read */
            if (w[i] > 0xff) {
                if (whole)
                    return 0;
                buf[n++] = '?';
            } else {
                buf[n++] = (u8)w[i];
            }
        }
        return i == units && whole ? 0 : n;
    } else {                                            /* "NAME    EXT" */
        u8 e0 = buf[8], e1 = buf[9], e2 = buf[10];
        for (n = 8; n > 0 && (buf[n - 1] == ' ' || buf[n - 1] == 0); n--)
            ;
        if (e0 > ' ') {
            buf[n++] = '.';
            buf[n++] = e0;
            if (e1 > ' ')
                buf[n++] = e1;
            if (e2 > ' ')
                buf[n++] = e2;
        }
        return n;
    }
}

/* A playlist's name as the Playlists list shows it, without ".m3u". */
int playlist_name(u8 *buf, int room)
{
    int n = entry_name(buf, room, 0);
    if (n >= 4 && buf[n - 4] == '.' && upper(buf[n - 3]) == 'M' && buf[n - 2] == '3' && upper(buf[n - 1]) == 'U')
        n -= 4;
    return n;
}

/* The path from the root of the song at (layer, offset) as VFS_OFFSET takes them, "Music\Artist\Album\01 -
 * Title.mp3", written at the end of line[0 .. LINE_MAX). Returns where it starts, or -1; leaves the file system in
 * the song's folders.
 * Each name is first read into the free front of line[] (as UTF-16 it needs twice its length plus 4 bytes) and then
 * moved behind the rest. With the sync's limits (file names up to 64 characters, album folders up to 50, artist
 * folders up to 18) the worst case needs 64 + 1 + 104 = 169 bytes, and leaves 52 in front for the work of
 * append(). */
int song_path_at(u8 *line, const void *layer, const void *offset)
{
    int end = LINE_MAX, depth = 0, n, k;

    if (!vfs((uptr)layer, (uptr)offset, 1, VFS_OFFSET))
        return -1;
    for (;;) {
        if (end < 24)
            return -1;
        n = entry_name(line, end & ~1, 1);
        if (n <= 0 || n >= end)
            return -1;
        for (k = n; k-- > 0;)                           /* backwards: the target lies behind the source */
            line[end - n + k] = line[k];
        end -= n;
        if (++depth > MAX_DEPTH)
            return -1;
        if (!vfs(CD_BACK, 0, 0, VFS_CD))
            return end;
        line[--end] = '\\';
    }
}

/* ------------------------------------------------------------------ the playlists in the root folder */

/* Walks the files of the root folder. Stops on the index-th .m3u (from 0) and returns 1; or returns 0 at the end
 * and puts the number of .m3u files into *count. */
int find_playlist(int index, int *count)
{
    int type = DIR_HEAD, n = 0, guard;

    vfs(CD_ROOT, 0, 0, VFS_CD);
    for (guard = 0; guard < MAX_ENTRIES; guard++) {
        u32 ext = (u32)vfs(type, 0, EXT_ALL_FILES, VFS_DIR);
        if (!ext)
            break;
        type = DIR_NEXT;
        if (is_m3u(ext)) {
            if (n == index)
                return 1;
            n++;
        }
    }
    if (count)
        *count = n;
    return 0;
}

/* Stops on "New playlist <number>.m3u" in the root folder and returns its index among the playlists; -1 if it is
 * not there. */
int find_new(int number)
{
    u8 want[24], tmp[64] __attribute__((aligned(4)));
    int type = DIR_HEAD, n, i, k = 0, guard;

    n = append_number(want, new_playlist_text(want), number);
    vfs(CD_ROOT, 0, 0, VFS_CD);
    for (guard = 0; guard < MAX_ENTRIES; guard++) {
        u32 ext = (u32)vfs(type, 0, EXT_ALL_FILES, VFS_DIR);
        if (!ext)
            break;
        type = DIR_NEXT;
        if (!is_m3u(ext))
            continue;
        if (playlist_name(tmp, 64) == n) {
            for (i = 0; i < n && tmp[i] == want[i]; i++)
                ;
            if (i == n)
                return k;
        }
        k++;
    }
    return -1;
}

/* ------------------------------------------------------------------ a list screen */

/* Draws the list the way the stock menu does (shared code at 0x18661316). The names live only while drawing. */
static void list_draw(list_t *l, int top, int mode)
{
    u8 rows[ROWS][ROW_NAME + 2] __attribute__((aligned(4)));
    listbox_t list, *box = &list;
    style_t st;
    int r, flag;

    st.id = STYLE_PICKER;
    st.type = 1;
    st.reserve = 0;
    if (mode == LIST_DRAW_ALL) {                           /* the bar on, its middle empty (stage 24) */
        headbar_all();
        clear_bar();
    }
    list_prepare(&st);
    set_bytes(box, 0, sizeof *box);
    for (r = 0; r < ROWS && top + r < l->total; r++) {
        rows[r][0] = rows[r][1] = rows[r][2] = 0;
        box->items[r].str = (uptr)rows[r];
        box->items[r].lang = language();
        box->items[r].length = ROW_NAME;
        box->items[r].argv = ICON_PLAYLIST;
    }
    l->page(l, top, rows, box->items, r);
    box->title.str = l->title;
    box->title.lang = TEXT_ID;
    box->head_id = box->head_act_id = 0xffff;
    box->valid = (u16)r;
    box->active = box->old = (u16)(l->sel - top);
    box->total = (u16)l->total;
    box->pos = (u16)l->sel;
    flag = back_flag();
    if (flag == 0)
        ui(0x2124, 0, 0, 20);
    else if (flag == 1)
        ui(0x2a14, 0, 0, 20);
    ui((uptr)&st, (uptr)box, mode, UI_LISTBOX);
}

/* Shows the list until a row is chosen (returns it), Back is pressed (PICK_BACK), or a system message asks to
 * leave (PICK_PASS, the result in *result). Previous and Next go round the list; with l->moving they stop at its
 * ends (the chosen row is a song being moved). Keys go through the stock menu's key table; everything else is
 * handled the way the stock menu handles it. */
int list_run(list_t *l, u32 *result)
{
    u8 gui[8], app[24];
    u16 ev = 0;
    int top = l->sel >= ROWS ? l->sel - ROWS + 1 : 0, mode = LIST_DRAW_ALL, n = l->total;
    u32 r;

    for (;;) {
        if (mode) {
            list_draw(l, top, mode);
            mode = 0;
        }
        if (get_gui_msg(gui)) {
            if (key_mapping(gui, &ev)) {
                if (ev == EV_NEXT || ev == EV_PREV) {
                    if (l->moving)
                        l->sel = ev == EV_NEXT ? (l->sel + 1 < n ? l->sel + 1 : l->sel) : (l->sel > 0 ? l->sel - 1 : 0);
                    else
                        l->sel = ev == EV_NEXT ? (l->sel + 1 < n ? l->sel + 1 : 0) : (l->sel > 0 ? l->sel - 1 : n - 1);
                    if (l->sel < top)
                        top = l->sel;
                    if (l->sel >= top + ROWS)
                        top = l->sel - ROWS + 1;
                    mode = l->moving ? LIST_DRAW_ALL : LIST_DRAW_LIST;
                } else if (ev == EV_SELECT) {
                    return l->sel;
                } else if (ev == EV_BACK) {
                    return PICK_BACK;
                } else if (ev != EV_STOP && ev != EV_OPTION) {
                    r = message_box(ev);
                    if (r == RESULT_REDRAW)
                        mode = LIST_DRAW_ALL;
                    else if (r) {
                        *result = r;
                        return PICK_PASS;
                    }
                }
            }
        } else if (get_app_msg(app)) {
            r = app_dispatch(app);
            if (r == RESULT_REDRAW)
                mode = LIST_DRAW_ALL;
            else if (r) {
                *result = r;
                return PICK_PASS;
            }
        }
        delay_tick();
    }
}

/* The names of rows top .. top+n-1 of the list of playlists. With extra = 1 row 0 is "New playlist" and row k
 * the (k-1)-th playlist; with extra = 0 row k is the k-th playlist. */
static void playlist_page(list_t *l, int top, u8 rows[ROWS][ROW_NAME + 2], strdesc_t *items, int count)
{
    u8 tmp[96] __attribute__((aligned(4)));
    int r, i, k, type = DIR_HEAD, n = 0, guard;

    if (top < l->extra) {
        rows[0][new_playlist_text(rows[0])] = 0;
        items[0].argv = ICON_ADD;
    }
    vfs(CD_ROOT, 0, 0, VFS_CD);
    for (guard = 0; guard < MAX_ENTRIES && n + l->extra < top + count; guard++) {
        u32 ext = (u32)vfs(type, 0, EXT_ALL_FILES, VFS_DIR);
        if (!ext)
            break;
        type = DIR_NEXT;
        if (!is_m3u(ext))
            continue;
        r = n++ + l->extra - top;                       /* this playlist's row on the page */
        if (r < 0 || r >= count)
            continue;
        k = playlist_name(tmp, 96);
        if (k > ROW_CHARS - 1)
            k = ROW_CHARS - 1;
        for (i = 0; i < k; i++)
            rows[r][i] = tmp[i];
        rows[r][k] = 0;
    }
}

/* The list of playlists, "Add to playlist" with "New playlist" on top (extra = 1) or "Remove from Playlist":
 * the chosen row, PICK_BACK, PICK_PASS, or PICK_EMPTY if there is nothing to show. */
int pick(u32 *result, int extra)
{
    list_t l;
    int count = 0;

    find_playlist(-1, &count);
    set_bytes(&l, 0, sizeof l);
    l.title = extra ? S_ADD_TO_PLAYLIST : S_REMOVE_FROM;
    l.total = count + extra;
    l.extra = extra;
    l.page = playlist_page;
    if (!l.total)
        return PICK_EMPTY;
    return list_run(&l, result);
}

/* ------------------------------------------------------------------ adding */

/* Creates "New playlist N.m3u" in the root with the first free N; the UTF-16 name is built in name[] (42 bytes).
 * Returns the open file, 0 if none could be made. */
static uptr create_new(u8 *name, int *number)
{
    u16 *w = (u16 *)name;
    u8 t[24];
    int n, k, i;
    uptr h;

    for (n = 1; n <= NEW_MAX; n++) {
        k = append_number(t, new_playlist_text(t), n);
        t[k++] = '.';
        t[k++] = 'm';
        t[k++] = '3';
        t[k++] = 'u';
        w[0] = 0xfeff;
        for (i = 0; i < k; i++)
            w[i + 1] = t[i];
        w[k + 1] = 0;
        vfs(CD_ROOT, 0, 0, VFS_CD);
        h = vfs((uptr)name, OPEN_MODIFY, 0, VFS_OPEN);
        if (h) {
            vfs(h, 0, 0, VFS_CLOSE);
            continue;
        }
        *number = n;
        return vfs((uptr)name, 0, 0, VFS_CREATE);
    }
    return 0;
}

/* Appends the path at line[start .. LINE_MAX) to the index-th playlist (from 0), or to a new one when index < 0
 * (its number goes to *number). The bytes of line[] in front of the path serve as buffer for reading the
 * playlist. */
int append(int index, int *number, u8 *line, int start)
{
    int len = LINE_MAX - start, pos = 0, last = '\n';
    u32 size = 0, off, want, got, i;
    uptr h;

    if (start < (index < 0 ? 44 : 16))
        return FAILED;
    if (index < 0) {
        h = create_new(line, number);
    } else {
        if (!find_playlist(index, 0))
            return FAILED;
        h = vfs(0, OPEN_MODIFY, 0, VFS_OPEN);
    }
    if (!h)
        return FAILED;
    vfs((uptr)&size, h, 0, VFS_SIZE);
    for (off = 0; off < size; off += got) {             /* is the song in it already? */
        want = size - off < (u32)start ? size - off : (u32)start;
        got = (u32)vfs((uptr)line, want, h, VFS_READ);
        if (!got || got > want)
            break;
        for (i = 0; i < got; i++) {
            u32 c = line[i];
            if (c == '\r' || c == '\n') {
                if (pos == len)
                    break;
                pos = 0;
            } else if (pos >= 0) {
                pos = pos < len && upper(c) == upper(line[start + pos]) ? pos + 1 : -1;
            }
            last = (int)c;
        }
        if (i < got)
            break;
    }
    if (pos == len) {
        vfs(h, 0, 0, VFS_CLOSE);
        return ALREADY;
    }
    if (off != size || (size == 0 && vfs((uptr)line, 1, h, VFS_READ))) {
        vfs(h, 0, 0, VFS_CLOSE);                        /* the size and the content disagree: leave the file alone */
        return FAILED;
    }
    vfs(size, SEEK_FROM_SET, h, VFS_SEEK);
    got = 1;
    if (size && last != '\n') {
        line[0] = '\r';
        line[1] = '\n';
        got = (u32)vfs((uptr)line, 2, h, VFS_WRITE) == 2;
    }
    line[LINE_MAX] = '\r';
    line[LINE_MAX + 1] = '\n';
    if (got)
        got = (u32)vfs((uptr)(line + start), (u32)len + 2, h, VFS_WRITE) == (u32)len + 2;
    vfs(h, 0, 0, VFS_CLOSE);
    return got ? ADDED : FAILED;
}

/* ------------------------------------------------------------------ removing */

typedef struct {                         /* the line being read */
    u32 start;                           /* where it starts in the file */
    int match;                           /* characters equal to the path so far, -1 once it differs */
    int pad;                             /* 0 while empty, 1 while "#" and spaces, -1 else */
    int ended;                           /* a CR was seen */
} scan_t;

/* The line ends at end (behind its line end). Notes it as a cut if it is the song's line or a filler line, and
 * returns 1 for the song's. */
static int line_done(scan_t *s, u32 end, int len, u32 cut[][2], int *cuts)
{
    int song = s->match == len;

    if ((song || s->pad == 1) && *cuts < MAX_CUTS) {
        cut[*cuts][0] = s->start;
        cut[*cuts][1] = end;
        ++*cuts;
    } else {
        song = 0;
    }
    s->start = end;
    s->match = s->pad = s->ended = 0;
    return song;
}

/* Takes the lines with the path path[0 .. len) out of the index-th playlist (see the top of the file). */
int remove_line(int index, const u8 *path, int len)
{
    u8 buf[BUF] __attribute__((aligned(4)));
    u32 cut[MAX_CUTS][2], size = 0, off, got, want, i, r, w, end, left, body;
    int cuts = 0, songs = 0, k, last = '\n';
    scan_t s;
    uptr h;

    if (!find_playlist(index, 0))
        return FAILED;
    h = vfs(0, OPEN_MODIFY, 0, VFS_OPEN);
    if (!h)
        return FAILED;
    vfs((uptr)&size, h, 0, VFS_SIZE);
    set_bytes(&s, 0, sizeof s);
    for (off = 0; off < size; off += got) {
        want = size - off < BUF ? size - off : BUF;
        got = (u32)vfs((uptr)buf, want, h, VFS_READ);
        if (!got || got > want)
            break;
        for (i = 0; i < got; i++) {
            u32 c = buf[i];
            if (c == '\n') {
                songs += line_done(&s, off + i + 1, len, cut, &cuts);
            } else if (c == '\r') {
                s.ended = 1;
            } else if (s.ended) {                       /* text behind a CR in the same line */
                s.match = s.pad = -1;
            } else {
                s.match = s.match >= 0 && s.match < len && upper(c) == upper(path[s.match]) ? s.match + 1 : -1;
                s.pad = s.pad == 0 ? (c == '#' ? 1 : -1) : s.pad == 1 && c == ' ' ? 1 : -1;
            }
        }
    }
    if (off != size || (size == 0 && vfs((uptr)buf, 1, h, VFS_READ)))
        goto fail;                                      /* the size and the content disagree: leave the file alone */
    if (s.start < size)                                 /* the last line has no line end */
        songs += line_done(&s, size, len, cut, &cuts);
    if (!songs) {
        vfs(h, 0, 0, VFS_CLOSE);
        return ABSENT;
    }
    w = cut[0][0];
    if (w) {
        vfs(w - 1, SEEK_FROM_SET, h, VFS_SEEK);
        if ((u32)vfs((uptr)buf, 1, h, VFS_READ) != 1)
            goto fail;
        last = buf[0];
    }
    for (k = 0; k < cuts; k++) {                        /* what lies between the cuts moves up; w <= r */
        end = k + 1 < cuts ? cut[k + 1][0] : size;
        for (r = cut[k][1]; r < end; r += want, w += want) {
            want = end - r < BUF ? end - r : BUF;
            vfs(r, SEEK_FROM_SET, h, VFS_SEEK);
            if ((u32)vfs((uptr)buf, want, h, VFS_READ) != want)
                goto fail;
            vfs(w, SEEK_FROM_SET, h, VFS_SEEK);
            if ((u32)vfs((uptr)buf, want, h, VFS_WRITE) != want)
                goto fail;
            last = buf[want - 1];
        }
    }
    left = size - w;                                    /* the bytes left over: a line end if the text before */
    vfs(w, SEEK_FROM_SET, h, VFS_SEEK);                 /* lacks one, then "#", spaces and CR LF */
    if (last != '\n' && left >= 2) {
        buf[0] = '\r';
        buf[1] = '\n';
        if ((u32)vfs((uptr)buf, 2, h, VFS_WRITE) != 2)
            goto fail;
        left -= 2;
    }
    body = left >= 2 ? left - 2 : left;                 /* (one byte left: just the "#") */
    for (i = 0; i < body; i += want) {
        want = body - i < BUF ? body - i : BUF;
        set_bytes(buf, ' ', BUF);
        if (i == 0)
            buf[0] = '#';
        if ((u32)vfs((uptr)buf, want, h, VFS_WRITE) != want)
            goto fail;
    }
    if (left >= 2) {
        buf[0] = '\r';
        buf[1] = '\n';
        if ((u32)vfs((uptr)buf, 2, h, VFS_WRITE) != 2)
            goto fail;
    }
    vfs(h, 0, 0, VFS_CLOSE);
    return REMOVED;
fail:
    vfs(h, 0, 0, VFS_CLOSE);
    return FAILED;
}

/* ------------------------------------------------------------------ the library */

/* The last part of the path at line[start .. LINE_MAX): the song's file name. */
static const u8 *file_name(const u8 *line, int start, int *n)
{
    int i = LINE_MAX;
    while (i > start && line[i - 1] != '\\')
        i--;
    *n = LINE_MAX - i;
    return line + i;
}

/* M3U.LIB after a song was added to the index-th playlist, or to "New playlist <number>" (index < 0) named
 * name[]: the playlist is found by its directory entry; a new playlist gets a record. A playlist the library
 * does not know otherwise is left to the next "Update list?". */
void library_add(int index, int number, const u8 *name, const u8 *line, int start, const u8 *loc)
{
    place_t m3u;
    const u8 *file;
    int list, n, k;
    uptr h;

    if (!(index >= 0 ? find_playlist(index, 0) : find_new(number) >= 0))
        return;
    vfs((uptr)m3u.layer, (uptr)&m3u.cluster, 0, VFS_OFFSET);
    h = lib_open();
    if (!h)
        return;
    list = lib_find_list(h, &m3u);
    if (list < 0 && index < 0) {
        for (k = 0; name[k]; k++)
            ;
        list = lib_add_list(h, &m3u, name, k);
    }
    if (list >= 0) {
        file = file_name(line, start, &n);
        lib_add_song(h, list, loc, file, n);
    }
    lib_close(h);
}

/* M3U.LIB after the playing song was taken out of the index-th playlist. */
static void library_remove(int index)
{
    place_t m3u;
    int list;
    uptr h;

    if (!find_playlist(index, 0))
        return;
    vfs((uptr)m3u.layer, (uptr)&m3u.cluster, 0, VFS_OFFSET);
    h = lib_open();
    if (!h)
        return;
    list = lib_find_list(h, &m3u);
    if (list >= 0)
        lib_remove_song(h, list, song_location());
    lib_close(h);
}

/* ------------------------------------------------------------------ messages */

/* The name of list row choice for the message (with extra = 1, row 0 is "New playlist N"). */
void choice_name(u8 *name, int choice, int number, int extra)
{
    u8 tmp[96] __attribute__((aligned(4)));
    int i, n;

    if (choice < extra) {
        name[append_number(name, new_playlist_text(name), number)] = 0;
        return;
    }
    n = find_playlist(choice - extra, 0) ? playlist_name(tmp, 96) : 0;
    if (n > ROW_CHARS - 1)
        n = ROW_CHARS - 1;
    for (i = 0; i < n; i++)
        name[i] = tmp[i];
    name[n] = 0;
}

/* A one-byte name as UTF-16 with FF FE, for wide[ROW_CHARS + 1]. */
void to_wide(u16 *wide, const u8 *name)
{
    int i;

    wide[0] = 0xfeff;
    for (i = 0; i < ROW_CHARS - 1 && name[i]; i++)
        wide[i + 1] = name[i];
    wide[i + 1] = 0;
}

/* The descriptor of a text as the stock dialogs read one: UTF-16 with FF FE, UTF-8 with its mark, else one-byte
 * text in the player's language. */
static void text_desc(strdesc_t *d, const u8 *text)
{
    d->str = (uptr)text;
    d->lang = text[0] == 0xff && text[1] == 0xfe ? TEXT_UTF16
            : text[0] == 0xef && text[1] == 0xbb && text[2] == 0xbf ? 0x7c : language();
    d->length = 32;
}

/* Text text of the player's resources with first (and second, if not 0) put into its [%s], shown as a message
 * (style 0x8000) or as a question with Yes and No (0x8002, Yes on yes_first); returns the dialog's result. A
 * title, a name from a list or a playlist name (UTF-16) may be given, as text_desc says. */
u32 say(u32 text, const u8 *first, const u8 *second, int ask, int yes_first)
{
    strdesc_t dest, src[2];
    dialog_t d;

    set_bytes(src, 0, sizeof src);
    text_desc(&src[0], first);
    if (second)
        text_desc(&src[1], second);
    set_bytes(&dest, 0, sizeof dest);
    dest.str = (uptr)temp_buffer();
    dest.lang = TEXT_UTF16;
    dest.length = 0x80;
    dest.argv = (u16)text;
    string_format(&dest, src);
    set_bytes(&d, 0, sizeof d);
    d.type = ask ? 0 : 2;                               /* with buttons, or a message that waits */
    d.buttons = ask ? 3 : 0;                            /* Yes and No */
    d.icon = 0xffff;
    d.text = (uptr)&dest;
    d.active = (u8)(ask && !yes_first);
    return dialog(ask ? 0x8002 : 0x8000, &d);
}

/* "<title> added to <playlist>!" (text 12) or "<title> removed from <playlist>!" (text 14), with the playing
 * song's title from its tag, as the stock message does it. */
static void report(u32 text, const u8 *name)
{
    u16 wide[ROW_CHARS + 1];

    to_wide(wide, name);
    say(text, song_title(), (const u8 *)wide, 0, 0);
}

/* ------------------------------------------------------------------ the menu items */

/* Pauses a playing song; returns whether it did. */
int pause_playing(void)
{
    if (engine_status() != PLAY_PLAYING)
        return 0;
    engine_pause();
    return 1;
}

/* "Add to playlist" in the options of the playing screen (MUSIC.MCG lists 42 and 59). */
u32 add_playing_to_playlist(void *title_action)
{
    u8 line[LINE_MAX + 2] __attribute__((aligned(4)));
    place_t keep;                                       /* where the file system stood */
    u8 name[ROW_CHARS];
    u32 result = RESULT_REDRAW;
    int choice, number = 0, status, paused, start;

    (void)title_action;
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
    choice = pick(&result, 1);
    if (choice < 0) {
        vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
        return choice == PICK_PASS ? result : RESULT_REDRAW;
    }
    refresh_path();
    paused = pause_playing();
    start = song_path_at(line, song_location() + LOC_LAYER, song_location() + LOC_CLUSTER);
    status = start < 0 ? FAILED : append(choice - 1, &number, line, start);
    if (status == ADDED) {
        choice_name(name, choice, number, 1);
        library_add(choice - 1, number, name, line, start, song_location());
    }
    if (paused)
        engine_resume();
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
    if (status == ADDED) {
        report(S_ADDED, name);
        return RESULT_TO_PLAYING;
    }
    dialog_text(0x8000, 2, status == ALREADY ? S_ALREADY_ADDED : S_OPEN_FAILED);
    return RESULT_REDRAW;
}

/* "Remove from Playlist" in the options of the playing screen (MUSIC.MCG lists 42 and 59). */
u32 remove_playing_from_playlist(void *title_action)
{
    u8 line[LINE_MAX + 2] __attribute__((aligned(4)));
    place_t keep;
    u8 name[ROW_CHARS];
    u32 result = RESULT_REDRAW;
    int choice, status, paused, start;

    (void)title_action;
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
    choice = pick(&result, 0);
    if (choice < 0) {
        vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
        if (choice == PICK_EMPTY)
            dialog_text(0x8000, 2, S_NO_PLAYLISTS);
        return choice == PICK_PASS ? result : RESULT_REDRAW;
    }
    refresh_path();
    paused = pause_playing();
    start = song_path_at(line, song_location() + LOC_LAYER, song_location() + LOC_CLUSTER);
    status = start < 0 ? FAILED : remove_line(choice, line + start, LINE_MAX - start);
    if (status == REMOVED) {
        library_remove(choice);
        choice_name(name, choice, 0, 0);
    }
    if (paused)
        engine_resume();
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
    if (status == REMOVED) {
        report(S_REMOVED, name);
        return RESULT_TO_PLAYING;
    }
    dialog_text(0x8000, 2, status == ABSENT ? S_NOT_IN_PLAYLIST : S_OPEN_FAILED);
    return RESULT_REDRAW;
}
