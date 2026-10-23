/* The playlist actions in the options of the music program's lists (Graphite stage 21).
 *
 * Song lists (All songs, Artists, Albums, Genres; options in MUSIC.MCG lists 21 to 25): "Add to playlist", for the
 * .m3u playlists. On a song it adds that song; on an album, artist or genre all of its songs, to a playlist
 * chosen from the same list as on the playing screen (playlist.c).
 *
 * Playlists (the options of the .m3u lists, before lists 50 to 54, now 26 to 30, whose rows served the built-in
 * playlists): "Delete" on a playlist deletes its .m3u file after a question; on a song inside a playlist it takes
 * the song out of that playlist, also after a question. "Move song" shows the playlist's songs with that song
 * chosen: Previous and Next move it, Select leaves it there, Back keeps the order. "Add songs" (stage 26), inside a
 * playlist or on one in the list of playlists, finds songs of the library by the search's keypad; each one chosen
 * goes to the end of that playlist, and the search comes back as it was for the next one. "New playlist" (stage 27)
 * asks for a name on the keypad (name.c), makes "<name>.m3u" and its record, and goes on to "Add songs" for it; in the
 * list of playlists the list then stands on it. "Rename" (stage 27) asks for the playlist's new name: the file is
 * copied under that name and the old one removed (the file system's own rename is used by no stock program, so it
 * is not relied on), and its record in M3U.LIB takes the new name and place.
 *
 * How it hooks in: the list option callback (MUSIC.AP 0x18161000) hands the result of the chosen option row, the
 * browser's path info and the list row the options were opened on to a result handler; the build points
 * its two calls (0x1816102e, 0x18161092) to list_option and m3u_option, which pass everything they do not handle
 * to the stock handlers; "Search" (stage 25, 0x8606 in both) goes on to search.c, "Add songs" (stage 26, 0x8607 in
 * Playlists) to add_songs, "New playlist" and "Rename" (stage 27, 0x8605 and 0x860f in Playlists) to new_playlist and
 * rename_playlist. The option rows are the stock ones
 * of the built-in playlists and return their codes (add
 * 0x8605, remove 0x8608, clear 0x8609). After a removal the list is told so (RESULT_DELETE_FILE or
 * RESULT_DELETE_DIRLIST): it takes the row out and reads itself again (SDK ui_directory2.c,
 * directory_option_deal).
 */
#include "fw.h"
#include "util.h"
#include "library.h"
#include "playlist.h"
#include "search.h"
#include "name.h"

#define FNAME_UNITS 66                   /* a playlist file's name for removing it */

/* The name of list row `row` (from 1) as the list shows it, into buf[ROW_NAME + 2]. */
static void row_name(int row, u8 *buf)
{
    brow_decode_t d;
    file_brow_t f;

    set_bytes(buf, 0, ROW_NAME + 2);
    set_bytes(&f, 0, sizeof f);
    d.option = 1;
    d.num = 1;
    d.top = (u16)row;
    f.name_len = ROW_NAME;
    f.name_buf = (uptr)buf;
    browser_get_items(&d, &f);
}

/* The browser's level: its lists below (artists, albums) and its rows. */
static int list_rows(int *lists)
{
    dir_brow_t b;

    set_bytes(&b, 0, sizeof b);
    browser_enter_dir(BROW_CUR, 0, &b);
    if (lists)
        *lists = b.dir_total;
    return b.dir_total + b.file_total;
}

/* The index among the root's .m3u files of the one at p (by its directory entry), standing on it; -1 if none. */
static int find_playlist_at(const place_t *p)
{
    place_t here;
    int type = DIR_HEAD, n = 0, guard;

    vfs(CD_ROOT, 0, 0, VFS_CD);
    for (guard = 0; guard < MAX_ENTRIES; guard++) {
        u32 ext = (u32)vfs(type, 0, EXT_ALL_FILES, VFS_DIR);
        if (!ext)
            break;
        type = DIR_NEXT;
        if (!is_m3u(ext))
            continue;
        vfs((uptr)here.layer, (uptr)&here.cluster, 0, VFS_OFFSET);
        if (here.cluster == p->cluster && here.entry == p->entry)
            return n;
        n++;
    }
    return -1;
}

/* ------------------------------------------------------------------ adding from the song lists */

/* The song at loc to the index-th playlist, or to a new one (index < 0, its number to *number). */
static int add_one(int index, int *number, const u8 *loc)
{
    u8 line[LINE_MAX + 2] __attribute__((aligned(4)));
    u8 name[ROW_CHARS];
    int start = song_path_at(line, loc + LOC_LAYER, loc + LOC_CLUSTER), status;

    if (start < 0)
        return FAILED;
    status = append(index, number, line, start);
    if (status == ADDED) {
        if (index < 0)
            choice_name(name, 0, *number, 1);
        library_add(index, *number, name, line, start, loc);
    }
    return status;
}

/* Every song below list row `active` (an album, artist or genre), by the stock scan of the browser (as the stock
 * batch add at MUSIC.AP 0x182e1000 does it); the first one may make the new playlist. */
static int add_all(int active, int index, int *number)
{
    dir_brow_t b;
    int r, s, guard, added = 0, already = 0;

    dialog_text(0x8000, 3, S_WAIT);
    set_bytes(&b, 0, sizeof b);
    browser_enter_dir(BROW_CUR, 0, &b);
    browser_enter_dir(BROW_SON, active, &b);
    browser_scan_init(&b);
    for (guard = 0; guard < MAX_ENTRIES; guard++) {
        r = browser_scan(browse_path(), &b, SCAN_DXCH);
        if (r == SCAN_FILE) {
            s = add_one(index, number, browse_path() + 4);
            added += s == ADDED;
            already += s == ALREADY;
            if (index < 0) {                            /* the rest goes to the playlist just made */
                if (s != ADDED)
                    break;
                index = find_new(*number);
                if (index < 0)
                    break;
            }
        } else if (r == SCAN_SELF || r == SCAN_ERROR || b.layer_no == 0) {
            break;
        }
    }
    browser_enter_dir(BROW_PARENT, 0, &b);
    return added ? ADDED : already ? ALREADY : FAILED;
}

/* "<title> added to <playlist>!" for row `choice` of the list of playlists. */
static void added(const u8 *title, int choice, int number)
{
    u8 name[ROW_CHARS];
    u16 wide[ROW_CHARS + 1];

    choice_name(name, choice, number, 1);
    to_wide(wide, name);
    say(S_ADDED, title, (const u8 *)wide, 0, 0);
}

static u32 add_selected(u8 *path_info, int active)
{
    u8 title[ROW_NAME + 2] __attribute__((aligned(4)));
    place_t keep;
    u32 result = RESULT_REDRAW;
    int choice, number = 0, status = FAILED, paused, batch = 0;

    list_rows(&batch);
    row_name(active, title);
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
    choice = pick(&result, 1);
    if (choice < 0) {
        vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
        return choice == PICK_PASS ? result : RESULT_REDRAW;
    }
    paused = pause_playing();
    if (batch)
        status = add_all(active, choice - 1, &number);
    else if (browser_select(active) && browser_get_location(path_info + 4, FSEL_PLAYLIST))
        status = add_one(choice - 1, &number, path_info + 4);
    if (paused)
        engine_resume();
    if (status == ADDED)
        added(title, choice, number);                   /* (finds the playlist's name) */
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
    if (status != ADDED)
        dialog_text(0x8000, 2, status == ALREADY ? S_ALREADY_ADDED : S_OPEN_FAILED);
    return RESULT_REDRAW;
}

/* ------------------------------------------------------------------ in the Playlists list */

/* The song in list row `active` out of playlist `list`. */
static u32 remove_selected(u8 *path_info, int active, int list)
{
    u8 title[ROW_NAME + 2] __attribute__((aligned(4)));
    u8 line[LINE_MAX + 2] __attribute__((aligned(4)));
    u16 wname[28];
    place_t keep, m3u;
    u8 *loc = path_info + 4;
    int index, start, status = FAILED, paused, ok = 0, gone = 0;
    uptr h;

    row_name(active, title);
    h = lib_open();
    if (h) {
        ok = lib_list(h, list, &m3u, wname);
        lib_close(h);
    }
    if (!ok) {
        dialog_text(0x8000, 2, S_OPEN_FAILED);
        return RESULT_REDRAW;
    }
    if (say(S_REMOVE_ASK, title, (const u8 *)wname, 1, 1) != RESULT_DIALOG_YES)
        return RESULT_REDRAW;
    if (!browser_select(active) || !browser_get_location(loc, FSEL_M3U)) {
        dialog_text(0x8000, 2, S_OPEN_FAILED);
        return RESULT_REDRAW;
    }
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
    paused = pause_playing();
    index = find_playlist_at(&m3u);
    start = song_path_at(line, loc + LOC_LAYER, loc + LOC_CLUSTER);
    if (index >= 0 && start >= 0)
        status = remove_line(index, line + start, LINE_MAX - start);
    if (status == REMOVED || status == ABSENT) {        /* not in the file: the library's entry is old, it goes too */
        h = lib_open();
        if (h) {
            gone = lib_remove_song(h, list, loc);
            lib_close(h);
        }
    }
    if (paused)
        engine_resume();
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
    if (status == REMOVED || gone)
        say(S_REMOVED, title, (const u8 *)wname, 0, 0);
    else
        dialog_text(0x8000, 2, status == ABSENT ? S_NOT_IN_PLAYLIST : S_OPEN_FAILED);
    return gone ? RESULT_DELETE_FILE : RESULT_REDRAW;
}

/* Removes the file the file system stands on, by its name (UTF-16 with FF FE, or built from the 8.3 name). */
static void remove_here(void)
{
    u16 fname[FNAME_UNITS];
    u8 t[12];
    int i, n;

    set_bytes(fname, 0, sizeof fname);
    vfs((uptr)fname, FNAME_UNITS - 1, 0, VFS_GET_NAME);
    if (fname[0] != 0xfeff) {                           /* "NAME    EXT" */
        for (i = 0; i < 11; i++)
            t[i] = ((u8 *)fname)[i];
        for (n = 8; n > 0 && t[n - 1] == ' '; n--)
            ;
        for (i = 0; i < n; i++)
            fname[1 + i] = t[i];
        fname[1 + n++] = '.';
        for (i = 8; i < 11 && t[i] > ' '; i++)
            fname[1 + n++] = t[i];
        fname[1 + n] = 0;
        fname[0] = 0xfeff;
    }
    vfs((uptr)fname, FS_FILE, 0, VFS_REMOVE);
}

/* The playlist in list row `active`: its file and its record. A playlist the engine plays from stops first, else
 * the engine would go on in the record that takes its number. */
static u32 delete_playlist(int active)
{
    u16 wname[28];
    place_t keep, m3u;
    int list = -1, index, ok = 0, paused, stopped = 0;
    uptr h;

    h = lib_open();
    if (h) {
        list = lib_order(h, active - 1);
        ok = list >= 0 && lib_list(h, list, &m3u, wname);
        lib_close(h);
    }
    if (!ok) {
        dialog_text(0x8000, 2, S_OPEN_FAILED);
        return RESULT_REDRAW;
    }
    if (say(S_DELETE_ASK, (const u8 *)wname, 0, 1, 0) != RESULT_DIALOG_YES)
        return RESULT_REDRAW;
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
    paused = pause_playing();
    index = find_playlist_at(&m3u);
    if (index >= 0)                                     /* the file system stands on it */
        remove_here();
    ok = 0;
    h = lib_open();
    if (h) {
        refresh_path();
        if (playing_source() == FSEL_M3U && lib_has_song(h, list, song_location())) {
            engine_stop();
            stopped = 1;
        }
        ok = lib_delete_list(h, list);
        lib_close(h);
    }
    if (paused && !stopped)
        engine_resume();
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
    if (!ok) {
        dialog_text(0x8000, 2, S_OPEN_FAILED);
        return RESULT_REDRAW;
    }
    say(S_DELETED, (const u8 *)wname, 0, 0, 0);
    return RESULT_DELETE_DIRLIST;
}

/* ------------------------------------------------------------------ moving a song */

/* While the song from row l->from (from 0) stands at row l->sel, the row the list itself has at row r. */
static int source_row(const list_t *l, int r)
{
    if (r == l->sel)
        return l->from;
    if (l->from < l->sel && r >= l->from && r < l->sel)
        return r + 1;
    if (l->sel < l->from && r > l->sel && r <= l->from)
        return r - 1;
    return r;
}

static void move_page(list_t *l, int top, u8 rows[ROWS][ROW_NAME + 2], strdesc_t *items, int count)
{
    int r;

    for (r = 0; r < count; r++) {
        row_name(source_row(l, top + r) + 1, rows[r]);
        items[r].lang = rows[r][0] == 0xff && rows[r][1] == 0xfe ? TEXT_UTF16
                      : rows[r][0] == 0xef && rows[r][1] == 0xbb && rows[r][2] == 0xbf ? 0x7c : language();
    }
}

/* Where in the open playlist file the line with path[0 .. len) is: its start and its end behind the line end. */
static int find_line(uptr h, u32 size, const u8 *path, int len, u32 *start, u32 *end)
{
    u8 buf[BUF] __attribute__((aligned(4)));
    u32 off, got, want, i, ls = 0;
    int match = 0, ended = 0;

    vfs(0, SEEK_FROM_SET, h, VFS_SEEK);
    for (off = 0; off < size; off += got) {
        want = size - off < BUF ? size - off : BUF;
        got = (u32)vfs((uptr)buf, want, h, VFS_READ);
        if (!got || got > want)
            return 0;
        for (i = 0; i < got; i++) {
            u32 c = buf[i];
            if (c == '\n') {
                if (match == len) {
                    *start = ls;
                    *end = off + i + 1;
                    return 1;
                }
                ls = off + i + 1;
                match = ended = 0;
            } else if (c == '\r') {
                ended = 1;
            } else if (ended) {
                match = -1;
            } else {
                match = match >= 0 && match < len && upper(c) == upper(path[match]) ? match + 1 : -1;
            }
        }
    }
    return 0;
}

/* Copies n bytes of the open file from src to dst (any overlap). */
static int move_bytes(uptr h, u32 dst, u32 src, u32 n)
{
    u8 buf[BUF] __attribute__((aligned(4)));
    u32 i, m;

    for (i = 0; i < n; i += m) {                        /* forward when moving down, backward when moving up */
        u32 at;
        m = n - i < BUF ? n - i : BUF;
        at = dst < src ? i : n - i - m;
        vfs(src + at, SEEK_FROM_SET, h, VFS_SEEK);
        if ((u32)vfs((uptr)buf, m, h, VFS_READ) != m)
            return 0;
        vfs(dst + at, SEEK_FROM_SET, h, VFS_SEEK);
        if ((u32)vfs((uptr)buf, m, h, VFS_WRITE) != m)
            return 0;
    }
    return 1;
}

/* In the index-th playlist file, the line of song a goes behind (after) or in front of the line of song b. */
static int move_line(int index, const place_t *a, const place_t *b, int after)
{
    u8 line[LINE_MAX + 2] __attribute__((aligned(4)));
    u32 size = 0, a0, a1, b0, b1, t, n;
    int start, ok = 0;
    uptr h;

    if (!find_playlist(index, 0))
        return 0;
    h = vfs(0, OPEN_MODIFY, 0, VFS_OPEN);
    if (!h)
        return 0;
    vfs((uptr)&size, h, 0, VFS_SIZE);                   /* both lines end (find_line wants the line end), so a */
    start = song_path_at(line, a->layer, &a->cluster);  /* last line without one stays where it is */
    if (start < 0 || !find_line(h, size, line + start, LINE_MAX - start, &a0, &a1))
        goto done;
    start = song_path_at(line, b->layer, &b->cluster);
    if (start < 0 || !find_line(h, size, line + start, LINE_MAX - start, &b0, &b1))
        goto done;
    n = a1 - a0;
    if (n > LINE_MAX + 2)
        goto done;
    t = after ? b1 : b0;
    vfs(a0, SEEK_FROM_SET, h, VFS_SEEK);
    if ((u32)vfs((uptr)line, n, h, VFS_READ) != n)
        goto done;
    if (t > a1) {                                       /* down: what lies between moves up */
        if (!move_bytes(h, a0, a1, t - a1))
            goto done;
        t -= n;
    } else if (t < a0) {                                /* up: what lies between moves down */
        if (!move_bytes(h, t + n, t, a0 - t))
            goto done;
    } else {
        ok = 1;
        goto done;
    }
    vfs(t, SEEK_FROM_SET, h, VFS_SEEK);
    ok = (u32)vfs((uptr)line, n, h, VFS_WRITE) == n;
done:
    vfs(h, 0, 0, VFS_CLOSE);
    return ok;
}

/* The place of the song in list row `row` (from 1), from the browser, as "Delete" gets it. */
static int row_place(u8 *path_info, int row, place_t *p)
{
    u8 *loc = path_info + 4;
    int k;

    if (!browser_select(row) || !browser_get_location(loc, FSEL_M3U))
        return 0;
    for (k = 0; k < LAYER_SIZE; k++)
        p->layer[k] = loc[LOC_LAYER + k];
    p->cluster = get32(loc + LOC_CLUSTER);
    p->entry = get32(loc + LOC_ENTRY);
    return 1;
}

/* "Move song" on list row `active` of playlist `list`. The library and the playlist file are open one after the
 * other, never together: the player lets a program hold only few files open (with both open the move failed). */
static u32 move_song(u8 *path_info, int active, int list)
{
    list_t l;
    place_t keep, m3u, a, b;
    u32 result = RESULT_REDRAW;
    int count = -1, to, paused, ok = 0, index;
    uptr h;

    h = lib_open();
    if (h) {
        count = lib_count(h, list);
        if (!lib_list(h, list, &m3u, 0))
            count = -1;
        lib_close(h);
    }
    if (count <= 1 || active < 1 || active > count)
        return RESULT_REDRAW;
    set_bytes(&l, 0, sizeof l);
    l.title = S_MOVE;
    l.total = count;
    l.sel = l.from = active - 1;
    l.moving = 1;
    l.page = move_page;
    to = list_run(&l, &result);
    if (to < 0)
        return to == PICK_PASS ? result : RESULT_REDRAW;
    if (to == l.from)
        return RESULT_REDRAW;
    if (!row_place(path_info, l.from + 1, &a) || !row_place(path_info, to + 1, &b)) {
        dialog_text(0x8000, 2, S_OPEN_FAILED);
        return RESULT_REDRAW;
    }
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
    paused = pause_playing();
    index = find_playlist_at(&m3u);
    if (index >= 0 && move_line(index, &a, &b, to > l.from)) {
        h = lib_open();
        if (h) {
            ok = lib_move_song(h, list, l.from, to);
            lib_close(h);
        }
    }
    if (paused)
        engine_resume();
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
    if (!ok)
        dialog_text(0x8000, 2, S_OPEN_FAILED);
    return RESULT_REDRAW;
}

/* ------------------------------------------------------------------ adding songs by the search (stage 26) */

/* The playlist "Add songs" adds to: the one the list is in, or the one on list row `active` in the list of playlists;
 * its record to *list and the index of its .m3u among the root's (or -1). The list's rows must agree with the
 * library, as for the other options. */
static int add_target(int active, int *list)
{
    place_t m3u;
    int in = m3u_list(), rows = list_rows(0), l = -1, ok = 0;
    uptr h = lib_open();

    if (!h)
        return -1;
    if (in < LISTS_MAX)
        l = rows == lib_count(h, in) ? in : -1;
    else if (rows == lib_lists(h) && active >= 1 && active <= rows)
        l = lib_order(h, active - 1);
    ok = l >= 0 && lib_list(h, l, &m3u, 0);
    lib_close(h);
    *list = l;
    return ok ? find_playlist_at(&m3u) : -1;
}

/* Row `row` of All songs to the index-th playlist: ADDED, ALREADY or FAILED. */
static int add_found(int index, int row)
{
    u8 loc[LOC_LAYER + LAYER_SIZE + 3] __attribute__((aligned(4)));
    place_t keep;
    int status = FAILED, number = 0, paused;

    if (!songs_get(row, loc, 1))
        return FAILED;
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
    paused = pause_playing();
    status = add_one(index, &number, loc);
    if (paused)
        engine_resume();
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
    return status;
}

/* "<song> added to <playlist>!", or why it was not. */
static void add_said(int list, int row, int status)
{
    u8 title[ROW_NAME + 2] __attribute__((aligned(4)));
    u16 wname[28];
    int ok = 0;
    uptr h;

    if (status == ADDED) {
        h = lib_open();
        if (h) {
            ok = lib_list(h, list, 0, wname);
            lib_close(h);
        }
        if (ok && songs_get(row, title, 0))
            say(S_ADDED, title, (const u8 *)wname, 0, 0);
        return;
    }
    dialog_text(0x8000, 2, status == ALREADY ? S_ALREADY_ADDED : S_OPEN_FAILED);
}

/* The list's number of rows from the browser's level again, its place kept: after a "redraw" the list reads the rows
 * of its page again but keeps its number of rows (the control recounts only when it enters a level, 0x187012bc, which
 * also takes the place from the level's history), so songs added behind its end would not show. */
static void list_grown(void)
{
    dirctl_t *dc = dir_control();
    int total = list_rows(0) + menu_rows(), last = dc->top + dc->page - 1;

    if (total <= dc->total)
        return;
    dc->total = (u16)total;
    dc->bottom = (u16)(last < total ? last : total);
}

/* The list stands on browser row `row` (from 1); on the last line of its page if it was not on the page. */
static void stand_on(int row)
{
    dirctl_t *dc = dir_control();
    int no = row + menu_rows(), page = dc->page, top = dc->top;

    if (row < 1 || no > dc->total || page < 1)
        return;
    if (no < top || no >= top + page)
        top = no - page + 1 > 1 ? no - page + 1 : 1;
    dc->top = (u16)top;
    dc->bottom = (u16)(top + page - 1 < dc->total ? top + page - 1 : dc->total);
    dc->list_no = (u16)no;
    dc->active = dc->old = (u16)(no - top + 1);
}

/* "Add songs" to the index-th playlist (its record list); made: the playlist was just made by "New playlist", and in
 * the list of playlists the list then stands on it (the last row: a record added goes to the end of the order). */
static u32 add_songs(int index, int list, int made)
{
    search_keep_t keep;
    int r, status;

    set_bytes(&keep, 0, sizeof keep);
    made = made ? 2 : 0;                                /* and bit 0: a song was added (one register less) */
    while ((r = search_songs(&keep)) == SONGS_CHOSEN) { /* the song is added after the screen's frame has gone */
        status = add_found(index, keep.row);
        made |= status == ADDED;
        add_said(list, keep.row, status);
    }
    if (made)
        list_grown();
    if (made & 2 && m3u_list() >= LISTS_MAX)
        stand_on(list_rows(0));
    if (r == SONGS_FAILED)
        dialog_text(0x8000, 2, S_OPEN_FAILED);
    return r == SONGS_PASS ? keep.result : RESULT_REDRAW;
}

/* ------------------------------------------------------------------ naming playlists (stage 27) */

#define FILE_UNITS (NAME_MAX + 8)        /* FF FE, a name (with a "~" in front), ".m3u", 0 */
#define COPY_BUF   192                   /* bytes copied at a time (the rename's chain of frames stays below the search's) */
enum { ST_DONE = 0, ST_FAILED = -1, ST_TAKEN = -2 };
enum { NEW_LEFT = -1, NEW_PASS = -2 };

/* "<name>.m3u" (UTF-16 with FF FE) for a name of up to NAME_MAX + 1 characters */
static void m3u_file(u16 *f, const u16 *name)
{
    int i;

    f[0] = 0xfeff;
    for (i = 0; i <= NAME_MAX && name[1 + i]; i++)
        f[1 + i] = name[1 + i];
    put4(f, 1 + i, '.' | 'm' << 8 | '3' << 16 | (u32)'u' << 24);
}

/* The index among the root's .m3u files of the one called name (UTF-16 with FF FE, without ".m3u"; the letter case
 * aside, as the file system has it), standing on it, its place in *p; -1 if there is none. */
static int find_named(const u16 *name, place_t *p)
{
    u8 tmp[96] __attribute__((aligned(4)));
    int type = DIR_HEAD, k = 0, n, i, guard;
    u32 c;

    vfs(CD_ROOT, 0, 0, VFS_CD);
    for (guard = 0; guard < MAX_ENTRIES; guard++) {
        u32 ext = (u32)vfs(type, 0, EXT_ALL_FILES, VFS_DIR);
        if (!ext)
            break;
        type = DIR_NEXT;
        if (!is_m3u(ext))
            continue;
        n = playlist_name(tmp, 96);                     /* (one-byte text: other characters as '?') */
        for (i = 0; i < n; i++) {
            c = name[1 + i];
            if (!c || upper(c > 0xff ? '?' : c) != upper(tmp[i]))
                break;
        }
        if (i == n && !name[1 + n]) {
            if (p)
                vfs((uptr)p->layer, (uptr)&p->cluster, 0, VFS_OFFSET);
            return k;
        }
        k++;
    }
    return -1;
}

/* The file at *src (a root .m3u) copied into a new file dst (UTF-16 with FF FE) of the root folder, a piece at a time
 * with one file open, each time standing on the source by walking the folder (as "Delete" finds a playlist): 1, or 0
 * with nothing new left behind. A file of that name already there is left alone. */
static int copy_to(const place_t *src, const u16 *dst)
{
    u8 buf[COPY_BUF] __attribute__((aligned(4)));
    u32 off = 0, size = 0, n, done;
    int ok = 0;
    uptr h;

    vfs(CD_ROOT, 0, 0, VFS_CD);
    h = vfs((uptr)dst, OPEN_MODIFY, 0, VFS_OPEN);
    if (h) {
        vfs(h, 0, 0, VFS_CLOSE);
        return 0;
    }
    h = vfs((uptr)dst, 0, 0, VFS_CREATE);
    if (!h)
        return 0;
    vfs(h, 0, 0, VFS_CLOSE);
    for (;;) {
        if (find_playlist_at(src) < 0)
            break;
        h = vfs(0, OPEN_MODIFY, 0, VFS_OPEN);
        if (!h)
            break;
        vfs((uptr)&size, h, 0, VFS_SIZE);
        n = off >= size ? 0 : size - off < COPY_BUF ? size - off : COPY_BUF;
        vfs(off, SEEK_FROM_SET, h, VFS_SEEK);
        done = n ? (u32)vfs((uptr)buf, n, h, VFS_READ) : 0;
        vfs(h, 0, 0, VFS_CLOSE);
        if (done != n)
            break;
        if (!n) {
            ok = 1;
            break;
        }
        vfs(CD_ROOT, 0, 0, VFS_CD);
        h = vfs((uptr)dst, OPEN_MODIFY, 0, VFS_OPEN);
        if (!h)
            break;
        vfs(off, SEEK_FROM_SET, h, VFS_SEEK);
        done = (u32)vfs((uptr)buf, n, h, VFS_WRITE);
        vfs(h, 0, 0, VFS_CLOSE);
        if (done != n)
            break;
        off += n;
    }
    if (!ok) {
        vfs(CD_ROOT, 0, 0, VFS_CD);
        vfs((uptr)dst, FS_FILE, 0, VFS_REMOVE);
    }
    return ok;
}

/* The playlist file at *m3u under the name name: copied, the old file removed, then its record (record list) with the
 * new name and place, which go to *m3u. 1 if all of it was done; else the file and the record agree as far as it got. */
static int move_file(int list, place_t *m3u, const u16 *name)
{
    u16 f[FILE_UNITS];
    int ok = 0;
    uptr h;

    m3u_file(f, name);
    if (!copy_to(m3u, f))
        return 0;
    if (find_playlist_at(m3u) >= 0)                     /* (it stands on it) */
        remove_here();
    if (find_named(name, m3u) < 0)                      /* (the old place is of no use now) */
        return 0;
    h = lib_open();
    if (h) {
        ok = lib_set_list(h, list, m3u, name);
        lib_close(h);
    }
    return ok;
}

/* The playlist of record list, its file at *m3u, renamed name: ST_DONE, ST_TAKEN (another playlist has that name) or
 * ST_FAILED. When only the letter case changes, it is renamed twice, by a name with a "~" in front first (into tmp,
 * NAME_UNITS + 1 units): the file system takes the new name for the old one. */
static int rename_file(int list, place_t *m3u, const u16 *name, u16 *tmp)
{
    place_t p;
    int at = find_named(name, &p), status = ST_FAILED, paused, i;

    if (at >= 0 && (p.cluster != m3u->cluster || p.entry != m3u->entry))
        return ST_TAKEN;
    paused = pause_playing();
    if (at >= 0) {
        tmp[0] = 0xfeff;
        tmp[1] = '~';
        for (i = 1; i <= NAME_MAX && name[i]; i++)
            tmp[1 + i] = name[i];
        tmp[1 + i] = 0;
        if (find_named(tmp, 0) < 0 && move_file(list, m3u, tmp) && move_file(list, m3u, name))
            status = ST_DONE;
    } else if (move_file(list, m3u, name)) {
        status = ST_DONE;
    }
    if (paused)
        engine_resume();
    return status;
}

/* "Rename": the playlist the list is in, or the one on list row `active` in the list of playlists. */
static u32 rename_playlist(int active)
{
    u16 name[NAME_UNITS], was[NAME_UNITS + 1];          /* (was: the record's 28 units; then rename_file's) */
    place_t m3u, keep;
    u32 result = RESULT_REDRAW;
    int list, r, status, i, ok = 0;
    uptr h;

    if (add_target(active, &list) >= 0) {
        h = lib_open();
        if (h) {
            ok = lib_list(h, list, &m3u, was);
            lib_close(h);
        }
    }
    if (!ok) {
        dialog_text(0x8000, 2, S_OPEN_FAILED);
        return RESULT_REDRAW;
    }
    for (i = 0; i < NAME_UNITS - 1 && (!i || was[i]); i++)
        name[i] = was[i];
    name[i] = 0;
    for (;;) {
        r = name_entry(name, NAME_RENAME, &result);
        if (r != NAME_OK)
            return r == NAME_PASS ? result : RESULT_REDRAW;
        for (i = 0; name[i] == was[i] && name[i]; i++)
            ;
        if (name[i] == was[i])                          /* the same name */
            return RESULT_REDRAW;
        vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
        status = rename_file(list, &m3u, name, was);
        vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
        if (status != ST_TAKEN)
            break;
        say(S_NAME_TAKEN, (const u8 *)name, 0, 0, 0);  /* (was is still the record's name: only a rename writes it) */
    }
    if (status != ST_DONE)
        dialog_text(0x8000, 2, S_OPEN_FAILED);
    return RESULT_REDRAW;                               /* the list reads its rows again: the new name */
}

/* "<name>.m3u" made in the root folder, empty, with its record in M3U.LIB: its index among the root's .m3u files and
 * the record in *list; ST_TAKEN if a playlist of that name is there; ST_FAILED, and no new file left. */
static int make_playlist(const u16 *name, int *list)
{
    u16 f[FILE_UNITS];
    u8 one[NAME_MAX];
    place_t keep, p;
    int index = ST_TAKEN, paused, n;
    uptr h;

    vfs((uptr)keep.layer, (uptr)&keep.cluster, 0, VFS_OFFSET);
    if (find_named(name, 0) < 0) {
        paused = pause_playing();
        m3u_file(f, name);
        vfs(CD_ROOT, 0, 0, VFS_CD);
        h = vfs((uptr)f, OPEN_MODIFY, 0, VFS_OPEN);    /* any file of that name */
        if (h)
            vfs(h, 0, 0, VFS_CLOSE);
        else if ((h = vfs((uptr)f, 0, 0, VFS_CREATE)) == 0)
            index = ST_FAILED;
        else {
            vfs(h, 0, 0, VFS_CLOSE);
            index = find_named(name, &p);
            *list = -1;
            h = index >= 0 ? lib_open() : 0;
            if (h) {
                for (n = 0; n < NAME_MAX && name[1 + n]; n++)
                    one[n] = (u8)name[1 + n];       /* (a typed name is ASCII) */
                *list = lib_add_list(h, &p, one, n);
                lib_close(h);
            }
            if (*list < 0) {                            /* no record: the file goes again */
                if (index >= 0 && find_playlist_at(&p) >= 0)
                    remove_here();
                index = ST_FAILED;
            }
        }
        if (paused)
            engine_resume();
    }
    vfs((uptr)keep.layer, (uptr)&keep.cluster, 1, VFS_OFFSET);
    return index;
}

/* "New playlist": a name on the keypad, then the playlist (make_playlist). The new file's index among the root's .m3u
 * files (its record to *list); NEW_LEFT when there is none (Return, or a message said why), NEW_PASS with a system
 * message's result in *list. */
static int new_playlist(int *list)
{
    u16 name[NAME_UNITS];
    u32 result = 0;
    int r, index;

    name[0] = 0xfeff;
    name[1] = 0;
    for (;;) {
        r = name_entry(name, NAME_NEW, &result);
        if (r != NAME_OK) {
            *list = (int)result;
            return r == NAME_PASS ? NEW_PASS : NEW_LEFT;
        }
        index = make_playlist(name, list);
        if (index != ST_TAKEN)
            break;
        say(S_NAME_TAKEN, (const u8 *)name, 0, 0, 0);  /* and the name again, to change it */
    }
    if (index < 0)
        dialog_text(0x8000, 2, S_OPEN_FAILED);
    return index < 0 ? NEW_LEFT : index;
}

/* ------------------------------------------------------------------ the result handlers */

/* The song lists' options (MUSIC.AP 0x1816102e). "Search" (stage 25) works on whatever level the list shows. */
u32 list_option(u8 *path_info, u32 check, u32 active)
{
    if (check == RESULT_SEARCH)
        return search_list(path_info);
    if (check != RESULT_ADD_FAVOR1)
        return stock_list_result(path_info, check, active);
    if ((s32)(short)active <= 0)                        /* rows put on top of a list: no song there */
        return RESULT_REDRAW;
    return add_selected(path_info, (int)active);
}

/* The Playlists list's options other than "Search". Which level the list is at: the browser keeps the playlist it
 * is in at 0x200116 (0xffff at the top, MUSIC.AP 0x1c0c22d2); its number of rows must agree with the library. */
static u32 m3u_edit(u8 *path_info, u32 check, u32 active)
{
    int list = m3u_list(), rows = list_rows(0), lists = -1, songs = -1;
    uptr h;

    if (check != RESULT_DEL_FAVOR && check != RESULT_CLR_FAVOR)
        return stock_m3u_result(path_info, check, active);
    if ((s32)(short)active <= 0)
        return RESULT_REDRAW;
    h = lib_open();
    if (h) {
        lists = lib_lists(h);
        if (list < LISTS_MAX)
            songs = lib_count(h, list);
        lib_close(h);
    }
    if (list < LISTS_MAX && rows == songs && (int)active <= songs)
        return check == RESULT_DEL_FAVOR ? remove_selected(path_info, (int)active, list) : move_song(path_info, (int)active, list);
    if (rows == lists && (int)active <= lists)
        return check == RESULT_DEL_FAVOR ? delete_playlist((int)active) : RESULT_REDRAW;
    dialog_text(0x8000, 2, S_OPEN_FAILED);                /* the library and the list disagree: "Update list?" */
    return RESULT_REDRAW;
}

/* The Playlists list's options (MUSIC.AP 0x18161092). "Search" (stage 25), "Add songs" (stage 26) and "New playlist"
 * (stage 27, which goes on to "Add songs") go on from here with the least stack. */
u32 m3u_option(u8 *path_info, u32 check, u32 active)
{
    int list = -1, index;

    if (check == RESULT_SEARCH)
        return search_list(path_info);
    if (check == RESULT_RENAME)
        return rename_playlist((int)active);
    if (check == RESULT_ADD_SONGS) {
        index = add_target((int)active, &list);
        if (index < 0) {
            dialog_text(0x8000, 2, S_OPEN_FAILED);
            return RESULT_REDRAW;
        }
    } else if (check == RESULT_NEW_LIST) {
        index = new_playlist(&list);                    /* (its frame is gone before the search's comes) */
        if (index < 0)
            return index == NEW_PASS ? (u32)list : RESULT_REDRAW;
    } else {
        return m3u_edit(path_info, check, active);
    }
    return add_songs(index, list, check == RESULT_NEW_LIST);
}
