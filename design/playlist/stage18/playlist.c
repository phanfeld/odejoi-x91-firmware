/* "Add to playlist" writes the .m3u files themselves (Graphite stage 18).
 *
 * In the options of the playing screen, "Add to playlist" opens a list of the .m3u files in the root folder, with
 * "New playlist" on top. Choosing a playlist appends the playing song's path to it in the form the sync writes
 * ("Music\Artist\Album\01 - Title.mp3", CR LF); "New playlist" creates "New playlist N.m3u" with the first free N.
 * A song that is in the playlist already is not added again. A message says what happened, in the player's
 * language (texts 11 and 12 of MUSIC.STY, 26 of COMMON.STY).
 *
 * design/build_stage18.py puts this into free room at the end of code banks of MUSIC.AP. Code there has no
 * global or static data and no string constants (constant text is built in code) and calls no library. Its
 * buffers are on the stack (the program's task has about 3 KB): the RAM from 0x101000 on, where the menus keep
 * their scratch data, is also where code banks are loaded, so data put there does not survive a call into
 * another bank. While the playlist file is read and written, playback is paused: the storage is busy and the
 * engine would run dry (heard as a loud stutter on the first test of stage 18).
 */
#include "fw.h"

#define ROWS        6
#define ROW_CHARS   21                   /* a shown playlist name and its zero */
#define LINE_MAX    192                  /* the song's path; room for the sync's longest names, see song_path */
#define MAX_DEPTH   9                    /* folder levels the file system supports */
#define MAX_ENTRIES 4000                 /* a guard for walking a folder */
#define NEW_MAX     99                   /* "New playlist 1" to "New playlist 99" */

enum { ADDED, ALREADY, FAILED };
enum { PICK_BACK = -1, PICK_PASS = -2 };

static inline __attribute__((always_inline)) void set_bytes(void *p, int v, int n)
{
    u8 *b = p;
    while (n-- > 0)
        *b++ = (u8)v;
}

static inline __attribute__((always_inline)) u32 upper(u32 c)
{
    c &= 0xff;
    return c >= 'a' && c <= 'z' ? c - 32 : c;
}

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
static int entry_name(u8 *buf, int room, int whole)
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
static int playlist_name(u8 *buf, int room)
{
    int n = entry_name(buf, room, 0);
    if (n >= 4 && buf[n - 4] == '.' && upper(buf[n - 3]) == 'M' && buf[n - 2] == '3' && upper(buf[n - 1]) == 'U')
        n -= 4;
    return n;
}

/* The playing song's path from the root, "Music\Artist\Album\01 - Title.mp3", written at the end of
 * line[0 .. LINE_MAX). Returns where it starts, or -1; leaves the file system in the song's folders.
 * Each name is first read into the free front of line[] (as UTF-16 it needs twice its length plus 4 bytes) and then
 * moved behind the rest. With the sync's limits (file names up to 64 characters, album folders up to 50, artist
 * folders up to 18) the worst case needs 64 + 1 + 104 = 169 bytes, and leaves 52 in front for the work of
 * append(). */
static int song_path(u8 *line)
{
    u8 *loc = song_location();
    int end = LINE_MAX, depth = 0, n, k;

    if (!vfs((uptr)(loc + 16), (uptr)(loc + 8), 1, VFS_OFFSET))
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

static inline __attribute__((always_inline)) int is_m3u(u32 ext)
{
    u32 last = ext >> 24;
    return upper(ext) == 'M' && ((ext >> 8) & 0xff) == '3' && upper(ext >> 16) == 'U' && (last == 0 || last == ' ');
}

/* Walks the files of the root folder. Stops on the index-th .m3u (from 0) and returns 1; or returns 0 at the end
 * and puts the number of .m3u files into *count. */
static int find_playlist(int index, int *count)
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

/* ------------------------------------------------------------------ the list */

/* The names of list rows top .. top+5 (row 0 is "New playlist", row k the (k-1)-th playlist). */
static void fill_rows(u8 rows[ROWS][ROW_CHARS], int top)
{
    u8 tmp[96] __attribute__((aligned(4)));
    int r, i, k, type = DIR_HEAD, n = 0, guard;

    for (r = 0; r < ROWS; r++)
        rows[r][0] = 0;
    if (top == 0)
        rows[0][new_playlist_text(rows[0])] = 0;
    vfs(CD_ROOT, 0, 0, VFS_CD);
    for (guard = 0; guard < MAX_ENTRIES && n + 1 < top + ROWS; guard++) {
        u32 ext = (u32)vfs(type, 0, EXT_ALL_FILES, VFS_DIR);
        if (!ext)
            break;
        type = DIR_NEXT;
        if (!is_m3u(ext))
            continue;
        r = ++n - top;                                  /* this playlist's row on the page */
        if (r < 0 || r >= ROWS)
            continue;
        k = playlist_name(tmp, 96);
        if (k > ROW_CHARS - 1)
            k = ROW_CHARS - 1;
        for (i = 0; i < k; i++)
            rows[r][i] = tmp[i];
        rows[r][k] = 0;
    }
}

/* Draws the list the way the stock menu does (shared code at 0x18661316). The names live only while drawing. */
static void draw(int top, int sel, int total, int mode)
{
    u8 rows[ROWS][ROW_CHARS];
    listbox_t list, *box = &list;
    style_t st;
    int r, flag;

    st.id = STYLE_PICKER;
    st.type = 1;
    st.reserve = 0;
    if (mode == LIST_DRAW_ALL)
        headbar_all();
    list_prepare(&st);
    fill_rows(rows, top);
    set_bytes(box, 0, sizeof *box);
    box->title.str = S_ADD_TO_PLAYLIST;
    box->title.lang = TEXT_ID;
    for (r = 0; r < ROWS && top + r < total; r++) {
        box->items[r].str = (uptr)rows[r];
        box->items[r].lang = language();
        box->items[r].length = ROW_CHARS;
        box->items[r].argv = top + r == 0 ? ICON_ADD : ICON_PLAYLIST;
    }
    box->head_id = box->head_act_id = 0xffff;
    box->valid = (u16)r;
    box->active = box->old = (u16)(sel - top);
    box->total = (u16)total;
    box->pos = (u16)sel;
    flag = back_flag();
    if (flag == 0)
        ui(0x2124, 0, 0, 20);
    else if (flag == 1)
        ui(0x2a14, 0, 0, 20);
    ui((uptr)&st, (uptr)box, mode, UI_LISTBOX);
}

/* Shows the list until a row is chosen (returns it), Back is pressed (PICK_BACK), or a system message asks to
 * leave (PICK_PASS, the result in *result). Keys go through the stock menu's key table; everything else is handled
 * the way the stock menu handles it. */
static int pick(u32 *result)
{
    u8 gui[8], app[24];
    u16 ev = 0;
    int total, count = 0, sel = 0, top = 0, mode = LIST_DRAW_ALL;
    u32 r;

    find_playlist(-1, &count);
    total = count + 1;
    for (;;) {
        if (mode) {
            draw(top, sel, total, mode);
            mode = 0;
        }
        if (get_gui_msg(gui)) {
            if (key_mapping(gui, &ev)) {
                if (ev == EV_NEXT || ev == EV_PREV) {
                    sel = ev == EV_NEXT ? (sel + 1 < total ? sel + 1 : 0) : (sel > 0 ? sel - 1 : total - 1);
                    if (sel < top)
                        top = sel;
                    if (sel >= top + ROWS)
                        top = sel - ROWS + 1;
                    mode = LIST_DRAW_LIST;
                } else if (ev == EV_SELECT) {
                    return sel;
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

/* ------------------------------------------------------------------ writing */

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

/* Appends the playing song to the index-th playlist (from 0), or to a new one when index < 0 (its number goes to
 * *number). The bytes of line[] in front of the path serve as buffer for reading the playlist. */
static int append(int index, int *number)
{
    u8 line[LINE_MAX + 2] __attribute__((aligned(4)));
    int start, len, pos = 0, last = '\n';
    u32 size = 0, off, want, got, i;
    uptr h;

    start = song_path(line);
    if (start < (index < 0 ? 44 : 16))
        return FAILED;
    len = LINE_MAX - start;
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

/* The name of list row choice for the message (row 0: "New playlist N"). */
static void choice_name(u8 *name, int choice, int number)
{
    u8 tmp[96] __attribute__((aligned(4)));
    int i, n;

    if (choice == 0) {
        name[append_number(name, new_playlist_text(name), number)] = 0;
        return;
    }
    n = find_playlist(choice - 1, 0) ? playlist_name(tmp, 96) : 0;
    if (n > ROW_CHARS - 1)
        n = ROW_CHARS - 1;
    for (i = 0; i < n; i++)
        name[i] = tmp[i];
    name[n] = 0;
}

/* "<title> added to <playlist>!" with the song's title from its tag, as the stock message does it. */
static void report_added(u8 *name)
{
    strdesc_t dest, src[2];
    dialog_t d;
    u16 wide[ROW_CHARS + 1];
    u8 *title = song_title();
    int i;

    wide[0] = 0xfeff;
    for (i = 0; i < ROW_CHARS - 1 && name[i]; i++)
        wide[i + 1] = name[i];
    wide[i + 1] = 0;
    set_bytes(src, 0, sizeof src);
    src[0].str = (uptr)title;
    src[0].lang = title[0] == 0xff && title[1] == 0xfe ? TEXT_UTF16
                : title[0] == 0xef && title[1] == 0xbb && title[2] == 0xbf ? 0x7c : language();
    src[0].length = 32;
    src[1].str = (uptr)wide;
    src[1].lang = TEXT_UTF16;
    src[1].length = 32;
    set_bytes(&dest, 0, sizeof dest);
    dest.str = (uptr)temp_buffer();
    dest.lang = TEXT_UTF16;
    dest.length = 0x80;
    dest.argv = S_ADDED;
    string_format(&dest, src);
    set_bytes(&d, 0, sizeof d);
    d.type = 2;
    d.icon = 0xffff;
    d.text = (uptr)&dest;
    dialog(0x8000, &d);
}

/* ------------------------------------------------------------------ the menu item */

/* "Add to playlist" in the options of the playing screen (MUSIC.MCG lists 42 and 59). */
u32 add_playing_to_playlist(void *title_action)
{
    u8 keep[84] __attribute__((aligned(4)));            /* where the file system stood: folder chain, entry */
    u8 name[ROW_CHARS];
    u32 result = RESULT_REDRAW;
    int choice, number = 0, status, playing;

    (void)title_action;
    vfs((uptr)keep, (uptr)(keep + 76), 0, VFS_OFFSET);
    choice = pick(&result);
    if (choice < 0) {
        vfs((uptr)keep, (uptr)(keep + 76), 1, VFS_OFFSET);
        return choice == PICK_PASS ? result : RESULT_REDRAW;
    }
    refresh_path();
    playing = engine_status();
    playing = playing != 0 && playing != 3;
    if (playing)
        engine_pause();
    status = append(choice - 1, &number);
    if (playing)
        engine_resume();
    if (status == ADDED)
        choice_name(name, choice, number);
    vfs((uptr)keep, (uptr)(keep + 76), 1, VFS_OFFSET);
    if (status == ADDED) {
        report_added(name);
        return RESULT_TO_PLAYING;
    }
    dialog_text(0x8000, 2, status == ALREADY ? S_ALREADY_ADDED : S_OPEN_FAILED);
    return RESULT_REDRAW;
}
