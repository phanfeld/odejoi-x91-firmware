/* Runs the playlist actions (playlist.c, library.c) and the Previous key (keys.c) against the simulated player of
 * mock.c. After every change the playlist library on the simulated disk is compared with one built from scratch
 * the way the player's library builder builds it (build_reference, after the SDK's plist_m3u_deal*.c). When the
 * player's own M3U.LIB of 2026-10-21 is given as argument, the library functions also run on that file.
 *
 *   cc -DHOST -I.. -o test test.c mock.c ../playlist.c ../library.c ../keys.c ../browse.c && ./test [M3U.LIB]
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <strings.h>
#include "../fw.h"
#include "../library.h"
#include "mock.h"

static int failures;

#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

#define LIB_SIZE 0x16aa00
#define SONGS    0x68a00
#define POS      0x162a00

static int song, focus, nothing, music, lib;

static void keys(int n, ...)
{
    __builtin_va_list ap;
    int i;
    __builtin_va_start(ap, n);
    for (i = 0; i < n; i++)
        events[i] = __builtin_va_arg(ap, int);
    __builtin_va_end(ap);
    event_count = n;
    event_next = 0;
}

/* ------------------------------------------------------------------ the library as the builder makes it */

static u32 rd16(const u8 *d, u32 o) { return d[o] | (u32)d[o + 1] << 8; }
static u32 rd32(const u8 *d, u32 o) { return rd16(d, o) | rd16(d, o + 2) << 16; }
static void w16(u8 *d, u32 o, u32 v) { d[o] = (u8)v; d[o + 1] = (u8)(v >> 8); }
static void w32(u8 *d, u32 o, u32 v) { w16(d, o, v); w16(d, o + 2, v >> 16); }

static int ends_m3u(const char *s)
{
    size_t n = strlen(s);
    return n > 4 && !strcasecmp(s + n - 4, ".m3u");
}

static int root_playlists(int *out)                  /* the .m3u files of the root, in folder order */
{
    int i, n = 0;
    for (i = 1; i < node_count; i++)
        if (nodes[i].parent == 0 && !nodes[i].gone && !nodes[i].is_dir && ends_m3u(nodes[i].name))
            out[n++] = i;
    return n;
}

static int resolve(const char *path)                 /* the node a path from the root names, or -1 */
{
    char part[200];
    int dir = 0, i, n;
    while (*path) {
        for (n = 0; *path && *path != '\\'; path++)
            part[n++] = *path;
        part[n] = 0;
        if (*path)
            path++;
        if (n > 63)                                  /* the builder keeps 63 characters of a name */
            return -1;
        for (i = 1; i < node_count; i++)
            if (nodes[i].parent == dir && !nodes[i].gone && !strcasecmp(nodes[i].name, part))
                break;
        if (i == node_count)
            return -1;
        dir = i;
    }
    return dir;
}

/* the songs of a playlist file as the builder reads them: a line counts when it ends with CR, '#' ends it */
static int playlist_songs(int node, int *out)
{
    char text[256];
    int n = 0, len = 0, skip = 0, s;
    u32 i;
    for (i = 0; i < nodes[node].size; i++) {
        char c = nodes[node].data[i];
        if (skip) {
            if (c == '\n')
                skip = 0, len = 0;
            continue;
        }
        if (c == '#') {
            skip = 1;
        } else if (c == '\r') {
            text[len] = 0;
            s = len > 3 ? resolve(text) : -1;
            if (s > 0 && !nodes[s].is_dir)
                out[n++] = s;
            skip = 1;
        } else if (len < 255) {
            text[len++] = c;
        }
    }
    return n;
}

static void place_of(int node, u32 *cluster, u32 *entry)
{
    *cluster = (u32)nodes[node].parent;
    *entry = (u32)node;
}

static void build_reference(u8 *d)
{
    int lists[64], order[64], used[4000], songs[4096], n, k, i, j, total = 0, c;
    u32 cl, en, r;
    memset(d, 0, LIB_SIZE);
    memcpy(d, "M3U", 4);
    memcpy(d + 0x10, "ALLFILE", 8);
    d[510] = 0x55;
    d[511] = 0xaa;
    n = root_playlists(lists);
    w16(d, 8, (u32)n);
    w16(d, 10, 1);
    for (k = 0; k < n; k++) {
        const char *name = nodes[lists[k]].name;
        r = 0x200 + (u32)k * 256;
        d[r] = 0xff;
        d[r + 1] = 0xfe;
        for (i = 0; i < (int)strlen(name) - 4 && i < 26; i++)
            d[r + 2 + 2 * i] = (u8)name[i];
        memcpy(d + r + 0x94, "M3U", 4);
        d[r + 0x99] = 1;
        place_of(lists[k], &cl, &en);
        w32(d, r + 0x9c, cl);
        w32(d, r + 0xa0, en);
        w16(d, r + 0xa4, (u32)k - 1);
        w16(d, r + 0xa6, (u32)k + 1);
        layer_of((int)cl, (int)en, d + r + 0xa8);
        order[k] = k;
    }
    for (i = 0; i < n; i++)                          /* sorted by name */
        for (j = i + 1; j < n; j++)
            if (strcasecmp(nodes[lists[order[j]]].name, nodes[lists[order[i]]].name) < 0)
                c = order[i], order[i] = order[j], order[j] = c;
    j = 1 + (n + 1) / 2;
    w16(d, 0x24, (u32)j);
    w16(d, 0x26, (u32)j + 1);
    for (k = 0; k < n; k++) {
        w16(d, (u32)j * 512 + 2 * (u32)k, (u32)order[k]);
        w16(d, (u32)(j + 1) * 512 + 2 * (u32)order[k], (u32)k);
    }
    for (k = 0; k < n; k++) {
        int m = playlist_songs(lists[k], songs);
        for (i = 0; i < m; i++) {
            for (j = 0; j < total && used[j] != songs[i]; j++)
                ;
            r = SONGS + (u32)j * 256;
            if (j == total) {
                const char *name = nodes[songs[i]].name;
                used[total++] = songs[i];
                memcpy(d + r, name, strlen(name) > 54 ? 54 : strlen(name));
                memset(d + r + 0x38, 0xff, 50);
                d[r + 0x38] = (u8)k;
                memcpy(d + r + 0x94, "MP3", 4);
                d[r + 0x98] = 1;
                d[r + 0x99] = 1;
                w16(d, r + 0x9a, 0xffff);
                place_of(songs[i], &cl, &en);
                w32(d, r + 0x9c, cl);
                w32(d, r + 0xa0, en);
                w16(d, r + 0xa4, (u32)j - 1);
                w16(d, r + 0xa6, (u32)j + 1);
                layer_of((int)cl, (int)en, d + r + 0xa8);
                w32(d, POS + (u32)j * 8, cl);
                w32(d, POS + (u32)j * 8 + 4, en);
            } else {
                for (c = 1; c < 50 && d[r + 0x38 + c] != 0xff; c++)
                    ;
                if (c < 50 && d[r + 0x38] != (u8)k)
                    d[r + 0x38 + c] = (u8)k;
            }
            w16(d, 0x4a00 + (u32)k * 0x2000 + 2 * rd16(d, 0xa2 + 2 * (u32)k), (u32)j);
            w16(d, 0xa2 + 2 * (u32)k, rd16(d, 0xa2 + 2 * (u32)k) + 1);
        }
    }
    w16(d, 0xa0, (u32)total);
}

static void rebuild_library(void)
{
    build_reference((u8 *)nodes[lib].data);
}

static int make_library(void)
{
    int n = add_node(0, "M3U.LIB", 0, NULL);
    node_room(n, LIB_SIZE);
    nodes[n].size = LIB_SIZE;
    build_reference((u8 *)nodes[n].data);
    return n;
}

static int users_has(const u8 *d, u32 song, u32 list)
{
    int k;
    for (k = 0; k < 50; k++)
        if (d[SONGS + song * 256 + 0x38 + k] != 0xff && (d[SONGS + song * 256 + 0x38 + k] & 0x7f) == list)
            return 1;
    return 0;
}

/* The library on the disk says what one built from the playlist files now would say: the same playlists (by
 * place and name), each with the same songs in the same order (by place), the same song records. The numbering
 * of records, the sorted order of new playlists and songs no playlist uses any more may differ. */
static void check_library(int line)
{
    static u8 ref[LIB_SIZE];
    const u8 *d = (const u8 *)nodes[lib].data;
    int n, k, j, i, map[64], seen[64] = {0}, bad = 0;
    u32 total, rtotal, at, o, cnt;
    build_reference(ref);
    n = (int)rd16(d, 8);
    if (memcmp(d, "M3U", 4) || d[510] != 0x55 || d[511] != 0xaa || rd16(d, 10) != 1 || n != (int)rd16(ref, 8)) {
        printf("FAIL line %d: library head (%d playlists, %u wanted)\n", line, n, rd16(ref, 8));
        failures++;
        return;
    }
    at = rd16(d, 0x24);
    if (at != 1 + ((u32)n + 1) / 2 || rd16(d, 0x26) != at + 1)
        printf("FAIL line %d: the order is in sector %u\n", line, at), bad++;
    for (k = 0; k < n; k++) {                        /* the order is a permutation, its inverse beside it */
        o = rd16(d, at * 512 + 2 * (u32)k);
        if (o >= (u32)n || seen[o]++ || rd16(d, (at + 1) * 512 + 2 * o) != (u32)k)
            printf("FAIL line %d: order entry %d\n", line, k), bad++;
    }
    for (k = 0; k < n; k++) {
        u32 r = 0x200 + (u32)k * 256;
        for (j = 0; j < n && memcmp(d + r + 0x9c, ref + 0x200 + (u32)j * 256 + 0x9c, 8); j++)
            ;
        map[k] = j;
        if (j == n || memcmp(d + r, ref + 0x200 + (u32)j * 256, 0x38) || memcmp(d + r + 0x94, ref + 0x200 + (u32)j * 256 + 0x94, 0x10)
            || memcmp(d + r + 0xa8, ref + 0x200 + (u32)j * 256 + 0xa8, 0x58) || rd16(d, r + 0xa4) != (((u32)k - 1) & 0xffff)
            || rd16(d, r + 0xa6) != (u32)k + 1)
            printf("FAIL line %d: playlist record %d\n", line, k), bad++;
    }
    if (bad) {
        failures++;
        return;
    }
    total = rd16(d, 0xa0);
    rtotal = rd16(ref, 0xa0);
    if (total < rtotal || total > 4000)
        printf("FAIL line %d: %u songs, at least %u wanted\n", line, total, rtotal), bad++;
    for (k = 0; k < n && !bad; k++) {               /* each playlist's songs, by place */
        cnt = rd16(d, 0xa2 + 2 * (u32)k);
        if (cnt != rd16(ref, 0xa2 + 2 * (u32)map[k]) || rd16(d, 0x106 + 2 * (u32)k)) {
            printf("FAIL line %d: playlist %d has %u songs, %u wanted\n", line, k, cnt, rd16(ref, 0xa2 + 2 * (u32)map[k]));
            bad++;
            break;
        }
        for (i = 0; i < (int)cnt; i++) {
            u32 s = rd16(d, 0x4a00 + (u32)k * 0x2000 + 2 * (u32)i), t = rd16(ref, 0x4a00 + (u32)map[k] * 0x2000 + 2 * (u32)i);
            if (s >= total || memcmp(d + SONGS + s * 256 + 0x9c, ref + SONGS + t * 256 + 0x9c, 8)) {
                printf("FAIL line %d: playlist %d song %d\n", line, k, i);
                bad++;
                break;
            }
            if (memcmp(d + SONGS + s * 256, ref + SONGS + t * 256, 0x38) || memcmp(d + SONGS + s * 256 + 0x94, ref + SONGS + t * 256 + 0x94, 0x10)
                || memcmp(d + SONGS + s * 256 + 0xa8, ref + SONGS + t * 256 + 0xa8, 0x58)) {
                printf("FAIL line %d: the record of song %u\n", line, s);
                bad++;
                break;
            }
        }
    }
    for (i = 0; i < (int)total && !bad; i++) {      /* every song: its place in the position index, its users */
        if (memcmp(d + POS + (u32)i * 8, d + SONGS + (u32)i * 256 + 0x9c, 8))
            printf("FAIL line %d: position of song %d\n", line, i), bad++;
        for (k = 0; k < n; k++) {
            int in = 0;
            cnt = rd16(d, 0xa2 + 2 * (u32)k);
            for (j = 0; j < (int)cnt; j++)
                in |= rd16(d, 0x4a00 + (u32)k * 0x2000 + 2 * (u32)j) == (u32)i;
            if (in != users_has(d, (u32)i, (u32)k))
                printf("FAIL line %d: song %d %s playlist %d\n", line, i, in ? "is in but not marked for" : "is marked for but not in", k), bad++;
        }
    }
    if (bad)
        failures++;
}

/* ------------------------------------------------------------------ the disk */

static void disk(void)
{
    int artist, album;
    reset_disk();
    music = add_node(0, "Music", 1, NULL);
    add_node(0, "E-Book", 1, NULL);
    artist = add_node(music, "Danger", 1, NULL);
    album = add_node(artist, "0917 2007", 1, NULL);
    add_node(album, "01 - 4-30.mp3", 0, NULL);
    artist = add_node(music, "A", 1, NULL);
    album = add_node(artist, "B", 1, NULL);
    add_node(album, "x.mp3", 0, NULL);
    focus = add_node(0, "Focus.m3u", 0, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n");
    add_node(0, "readme.txt", 0, "hello");
    nothing = add_node(0, "NothingMuch.m3u", 0, "Music\\A\\B\\x.mp3\r\n");
    artist = add_node(music, "16 Bit Lolitas", 1, NULL);
    album = add_node(artist, "Stardust EP", 1, NULL);
    add_node(album, "02 - Love Left (original mix).mp3", 0, NULL);
    song = add_node(album, "01 - Stardust (original mix).mp3", 0, NULL);
    lib = make_library();
    play(song);
    set_title("Stardust");
    status = PLAY_PLAYING;
    writes_while_playing = 0;
}

static const char *LINE = "Music\\16 Bit Lolitas\\Stardust EP\\01 - Stardust (original mix).mp3\r\n";

static int find(const char *name)
{
    int i;
    for (i = 0; i < node_count; i++)
        if (!strcmp(nodes[i].name, name))
            return i;
    return -1;
}

static void content_is(int node, const char *want, int line)
{
    nodes[node].data[nodes[node].size] = 0;
    if (strcmp(nodes[node].data, want)) {
        failures++;
        printf("FAIL line %d: %s holds\n---\n%s\n--- instead of\n%s\n---\n", line, nodes[node].name, nodes[node].data, want);
    }
}

/* "#", spaces, CR LF: n bytes */
static const char *filler(int n)
{
    static char f[600];
    memset(f, ' ', (size_t)n);
    f[0] = '#';
    f[n - 2] = '\r';
    f[n - 1] = '\n';
    f[n] = 0;
    return f;
}

/* ------------------------------------------------------------------ the tests */

static void test_add(void)
{
    char want[1024];
    int dir, entry, dir2, entry2, n;
    u32 r;

    /* the list: "New playlist", then the playlists in folder order */
    disk();
    keys(1, EV_BACK);
    position(&dir, &entry);
    r = add_playing_to_playlist(0);
    position(&dir2, &entry2);
    CHECK(r == RESULT_REDRAW, "Back gives %#x", r);
    CHECK(drawn_rows == 3 && !strcmp(shown[0], "New playlist") && !strcmp(shown[1], "Focus") && !strcmp(shown[2], "NothingMuch"),
          "rows %d: '%s' '%s' '%s'", drawn_rows, shown[0], shown[1], shown[2]);
    CHECK(last_title == S_ADD_TO_PLAYLIST, "title %d", last_title);
    CHECK(dir == dir2 && entry == entry2, "position not restored after Back");
    CHECK(pauses == 0, "paused without a choice");

    /* add to Focus: the file, the library, the pause */
    keys(2, EV_NEXT, EV_SELECT);
    pauses = resumes = 0;
    r = add_playing_to_playlist(0);
    snprintf(want, sizeof want, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n%s", LINE);
    content_is(focus, want, __LINE__);
    check_library(__LINE__);
    CHECK(r == RESULT_TO_PLAYING, "adding gives %#x", r);
    CHECK(!strcmp(last_message, "text 12: \"Stardust\", Focus") && last_dialog_text == S_ADDED, "message: %s", last_message);
    CHECK(pauses == 1 && resumes == 1 && status == PLAY_PLAYING && writes_while_playing == 0,
          "pause %d, resume %d, status %d, %d writes while playing", pauses, resumes, status, writes_while_playing);
    position(&dir2, &entry2);
    CHECK(dir == dir2 && entry == entry2, "position not restored after adding");

    /* again: nothing is added */
    keys(2, EV_NEXT, EV_SELECT);
    dialogs = 0;
    r = add_playing_to_playlist(0);
    content_is(focus, want, __LINE__);
    check_library(__LINE__);
    CHECK(r == RESULT_REDRAW && dialogs == 1 && last_dialog_text == S_ALREADY_ADDED, "second add: %#x, text %d", r, last_dialog_text);

    /* a paused song stays paused */
    status = PLAY_PAUSED;
    pauses = resumes = 0;
    keys(3, EV_NEXT, EV_NEXT, EV_SELECT);
    add_playing_to_playlist(0);
    CHECK(pauses == 0 && resumes == 0 && status == PLAY_PAUSED, "paused song: pause %d resume %d", pauses, resumes);
    status = PLAY_PLAYING;

    snprintf(want, sizeof want, "Music\\A\\B\\x.mp3\r\n%s", LINE);
    content_is(nothing, want, __LINE__);
    check_library(__LINE__);

    /* a playlist without a line end at its end gets one first (the library learns only the added song: the
       builder skipped the line before, as it skips every line without CR) */
    disk();
    strcpy(nodes[nothing].data, "Music\\A\\B\\x.mp3");
    nodes[nothing].size = (u32)strlen(nodes[nothing].data);
    keys(3, EV_NEXT, EV_NEXT, EV_SELECT);
    add_playing_to_playlist(0);
    content_is(nothing, want, __LINE__);

    /* the same line in other letter case counts as there */
    disk();
    strcpy(nodes[focus].data, "music\\16 BIT LOLITAS\\stardust ep\\01 - stardust (original mix).MP3");
    nodes[focus].size = (u32)strlen(nodes[focus].data);
    keys(2, EV_NEXT, EV_SELECT);
    add_playing_to_playlist(0);
    CHECK(last_dialog_text == S_ALREADY_ADDED && nodes[focus].size == strlen("music\\16 BIT LOLITAS\\stardust ep\\01 - stardust (original mix).MP3"),
          "case: text %d, size %u", last_dialog_text, nodes[focus].size);

    /* Previous from the top wraps to the last row */
    keys(2, EV_PREV, EV_BACK);
    add_playing_to_playlist(0);
    CHECK(last_active == 2 && last_total == 3, "wrap: active %d of %d", last_active, last_total);

    /* new playlists: the file and a new record in the library, at the end of the order */
    disk();
    keys(1, EV_SELECT);
    r = add_playing_to_playlist(0);
    n = find("New playlist 1.m3u");
    CHECK(n >= 0 && r == RESULT_TO_PLAYING, "no New playlist 1 (%#x)", r);
    if (n >= 0)
        content_is(n, LINE, __LINE__);
    CHECK(!strcmp(last_message, "text 12: \"Stardust\", New playlist 1"), "message: %s", last_message);
    {
        const u8 *d = (const u8 *)nodes[lib].data;
        CHECK(rd16(d, 8) == 3 && rd16(d, rd16(d, 0x24) * 512 + 4) == 2, "the new playlist is not last in the order");
    }
    keys(1, EV_SELECT);
    add_playing_to_playlist(0);
    CHECK(find("New playlist 2.m3u") >= 0, "no New playlist 2");
    check_library(__LINE__);
    keys(2, EV_NEXT, EV_SELECT);                       /* and then to Focus: the song is in three playlists */
    add_playing_to_playlist(0);
    check_library(__LINE__);

    /* many playlists: the page follows the selection; seven new ones move the order to later sectors */
    {
        int i;
        for (i = 0; i < 7; i++) {
            keys(1, EV_SELECT);
            add_playing_to_playlist(0);
            check_library(__LINE__);
        }
        keys(9, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_BACK);
        add_playing_to_playlist(0);
        CHECK(last_total == 12 && last_active == 4 && drawn_rows == 5 && !strcmp(shown[4], "New playlist 6")
              && !strcmp(shown[0], "New playlist 2"),
              "paging: total %d active %d rows '%s'..'%s'", last_total, last_active, shown[0], shown[4]);
        keys(2, EV_PREV, EV_BACK);                     /* from the top round to the last row */
        add_playing_to_playlist(0);
        CHECK(last_active == 4 && drawn_rows == 5 && !strcmp(shown[0], "New playlist 5") && !strcmp(shown[4], "New playlist 9"),
              "round to the end: active %d rows '%s'..'%s'", last_active, shown[0], shown[4]);
        keys(3, EV_PREV, EV_NEXT, EV_BACK);            /* and on to the top again */
        add_playing_to_playlist(0);
        CHECK(last_active == 0 && drawn_rows == 5 && !strcmp(shown[0], "New playlist") && !strcmp(shown[1], "Focus"),
              "round to the top: active %d rows '%s', '%s'", last_active, shown[0], shown[1]);
    }

    /* a playlist the library does not know: the file is written, the library left to "Update list?" */
    disk();
    add_node(0, "Later.m3u", 0, "");
    keys(4, EV_NEXT, EV_NEXT, EV_NEXT, EV_SELECT);
    r = add_playing_to_playlist(0);
    content_is(find("Later.m3u"), LINE, __LINE__);
    CHECK(r == RESULT_TO_PLAYING && rd16((const u8 *)nodes[lib].data, 8) == 2, "unknown playlist: %#x", r);

    /* no library at all: the file is still written */
    disk();
    nodes[lib].gone = 1;
    keys(2, EV_NEXT, EV_SELECT);
    r = add_playing_to_playlist(0);
    CHECK(r == RESULT_TO_PLAYING, "no library: %#x", r);

    /* a name that is not one-byte text: nothing is written, the message says so */
    disk();
    nodes[song].wide_char = 1;
    keys(2, EV_NEXT, EV_SELECT);
    r = add_playing_to_playlist(0);
    content_is(focus, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n", __LINE__);
    CHECK(r == RESULT_REDRAW && last_dialog_text == S_OPEN_FAILED, "wide name: %#x text %d", r, last_dialog_text);
    CHECK(status == PLAY_PLAYING, "not resumed after a failure");

    /* the deepest path the sync makes */
    disk();
    {
        int a = add_node(music, "Godspeed You Black Emperor", 1, NULL);   /* artists are cut at 18, this is longer */
        int b = add_node(a, "Lift Your Skinny Fists Like Antennas to Heaven xyz", 1, NULL);                   /* 50 */
        int s = add_node(b, "01 - Storm - Lift Yr. Skinny Fists, Like Antennas to Heaven!.mp3", 0, NULL);    /* 64 */
        play(s);
        keys(2, EV_NEXT, EV_SELECT);
        add_playing_to_playlist(0);
        snprintf(want, sizeof want, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\nMusic\\%s\\%s\\%s\r\n",
                 nodes[a].name, nodes[b].name, nodes[s].name);
        content_is(focus, want, __LINE__);
    }
}

static void test_remove(void)
{
    char want[1024];
    int dir, entry, dir2, entry2, n;
    u32 r, size;

    /* the list: the playlists only, titled "Remove from Playlist" */
    disk();
    keys(1, EV_BACK);
    r = remove_playing_from_playlist(0);
    CHECK(r == RESULT_REDRAW && drawn_rows == 2 && !strcmp(shown[0], "Focus") && !strcmp(shown[1], "NothingMuch") && last_title == S_REMOVE_FROM,
          "rows %d: '%s' '%s', title %d", drawn_rows, shown[0], shown[1], last_title);

    /* a song that is not in the playlist */
    keys(1, EV_SELECT);
    r = remove_playing_from_playlist(0);
    CHECK(r == RESULT_REDRAW && last_dialog_text == S_NOT_IN_PLAYLIST, "absent: %#x text %d", r, last_dialog_text);
    content_is(focus, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n", __LINE__);

    /* added, then removed: the file keeps its size, the rest is one comment line; the library follows */
    keys(2, EV_NEXT, EV_SELECT);
    add_playing_to_playlist(0);
    size = nodes[focus].size;
    keys(1, EV_SELECT);
    position(&dir, &entry);
    pauses = resumes = 0;
    writes_while_playing = 0;
    r = remove_playing_from_playlist(0);
    position(&dir2, &entry2);
    snprintf(want, sizeof want, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n%s", filler((int)strlen(LINE)));
    content_is(focus, want, __LINE__);
    CHECK(nodes[focus].size == size, "size %u, was %u", nodes[focus].size, size);
    check_library(__LINE__);
    CHECK(r == RESULT_TO_PLAYING && !strcmp(last_message, "text 14: \"Stardust\", Focus") && last_dialog_text == S_REMOVED,
          "removed: %#x %s", r, last_message);
    CHECK(pauses == 1 && resumes == 1 && writes_while_playing == 0, "pause %d resume %d, %d writes while playing", pauses, resumes, writes_while_playing);
    CHECK(dir == dir2 && entry == entry2, "position not restored after removing");

    /* added again: behind the comment line; removed again: one comment line, at the end */
    keys(2, EV_NEXT, EV_SELECT);
    add_playing_to_playlist(0);
    check_library(__LINE__);
    keys(1, EV_SELECT);
    remove_playing_from_playlist(0);
    snprintf(want, sizeof want, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n%s", filler(2 * (int)strlen(LINE)));
    content_is(focus, want, __LINE__);
    check_library(__LINE__);

    /* twice in the file, the last line without a line end, other letter case */
    disk();
    snprintf(want, sizeof want, "#EXTM3U\r\n%sMusic\\A\\B\\x.mp3\r\nmusic\\16 bit lolitas\\stardust ep\\01 - STARDUST (original mix).mp3", LINE);
    strcpy(nodes[nothing].data, want);
    nodes[nothing].size = (u32)strlen(want);
    size = nodes[nothing].size;
    keys(2, EV_NEXT, EV_SELECT);
    remove_playing_from_playlist(0);
    snprintf(want, sizeof want, "#EXTM3U\r\nMusic\\A\\B\\x.mp3\r\n%s", filler((int)(size - strlen("#EXTM3U\r\nMusic\\A\\B\\x.mp3\r\n"))));
    content_is(nothing, want, __LINE__);
    CHECK(nodes[nothing].size == size, "size %u, was %u", nodes[nothing].size, size);

    /* the song in the middle, the last line without a line end: the kept text gets one */
    disk();
    snprintf(want, sizeof want, "Music\\A\\B\\x.mp3\r\n%sMusic\\Danger\\0917 2007\\01 - 4-30.mp3", LINE);
    strcpy(nodes[nothing].data, want);
    nodes[nothing].size = (u32)strlen(want);
    keys(2, EV_NEXT, EV_SELECT);
    remove_playing_from_playlist(0);
    snprintf(want, sizeof want, "Music\\A\\B\\x.mp3\r\nMusic\\Danger\\0917 2007\\01 - 4-30.mp3\r\n%s", filler((int)strlen(LINE) - 2));
    content_is(nothing, want, __LINE__);

    /* the only line */
    disk();
    strcpy(nodes[focus].data, LINE);
    nodes[focus].size = (u32)strlen(LINE);
    rebuild_library();
    keys(1, EV_SELECT);
    remove_playing_from_playlist(0);
    content_is(focus, filler((int)strlen(LINE)), __LINE__);
    check_library(__LINE__);

    /* no playlists */
    disk();
    nodes[focus].gone = nodes[nothing].gone = 1;
    dialogs = 0;
    r = remove_playing_from_playlist(0);
    CHECK(r == RESULT_REDRAW && dialogs == 1 && last_dialog_text == S_NO_PLAYLISTS, "no playlists: %#x text %d", r, last_dialog_text);

    /* a long playlist: the lines behind move up in pieces */
    disk();
    {
        static char big[8000];
        int i, k = 0;
        for (i = 0; i < 40; i++)
            k += snprintf(big + k, sizeof big - (size_t)k, "%s", i == 20 ? LINE : "Music\\A\\B\\x.mp3\r\n");
        strcpy(nodes[focus].data, big);
        nodes[focus].size = (u32)k;
        rebuild_library();
        keys(1, EV_SELECT);
        remove_playing_from_playlist(0);
        for (i = 0, k = 0; i < 39; i++)
            k += snprintf(big + k, sizeof big - (size_t)k, "Music\\A\\B\\x.mp3\r\n");
        strcat(big, filler((int)strlen(LINE)));
        content_is(focus, big, __LINE__);
        check_library(__LINE__);
    }
    (void)n;
}

static void test_previous(void)
{
    disk();
    elapsed = 5000;
    pauses = resumes = seeks = previous_songs = 0;
    previous_key();
    CHECK(pauses == 1 && seeks == 1 && resumes == 1 && previous_songs == 0 && last_seek[0] == 0 && last_seek[1] == 0
          && status == PLAY_PLAYING && elapsed == 0, "restart: pause %d seek %d resume %d previous %d, status %d",
          pauses, seeks, resumes, previous_songs, status);
    previous_key();                                  /* right after: back one song */
    CHECK(previous_songs == 1 && seeks == 1, "second press: previous %d seek %d", previous_songs, seeks);

    elapsed = 2999;
    previous_key();
    CHECK(previous_songs == 2 && seeks == 1, "early press: previous %d seek %d", previous_songs, seeks);

    status = PLAY_PAUSED;                            /* a paused song starts again, paused */
    elapsed = 60000;
    pauses = resumes = 0;
    previous_key();
    CHECK(seeks == 2 && status == PLAY_PAUSED && resumes == 0 && pauses == 1 && previous_songs == 2,
          "paused: seek %d status %d resume %d pause %d", seeks, status, resumes, pauses);

    status = PLAY_STOPPED;
    elapsed = 60000;
    previous_key();
    CHECK(previous_songs == 3 && seeks == 2, "stopped: previous %d seek %d", previous_songs, seeks);

    /* screen off: the engine's time counts, the playing screen's copy is old */
    status = PLAY_PLAYING;
    background = 1;
    elapsed = 500;
    engine_ms = 8000;
    pauses = resumes = seeks = previous_songs = 0;
    standby_previous();
    CHECK(pauses == 1 && seeks == 1 && resumes == 1 && previous_songs == 0 && last_seek[0] == 0 && status == PLAY_PLAYING,
          "screen off, restart: pause %d seek %d resume %d previous %d", pauses, seeks, resumes, previous_songs);
    engine_ms = 1200;
    standby_previous();
    CHECK(previous_songs == 1 && seeks == 1, "screen off, second press: previous %d seek %d", previous_songs, seeks);
    elapsed = 60000;
    engine_ms = 900;
    standby_previous();
    CHECK(previous_songs == 2 && seeks == 1, "screen off, early press: previous %d seek %d", previous_songs, seeks);
    background = 0;                                  /* no music engine running: nothing, as stock */
    engine_ms = 8000;
    standby_previous();
    CHECK(previous_songs == 2 && seeks == 1 && pauses == 1, "screen off, no music engine: previous %d seek %d", previous_songs, seeks);
    background = 1;
}

/* The library functions on the player's own M3U.LIB (2026-10-21: NothingMuch, Focus, New playlist 1 to 3). */
static void test_real_library(const char *path)
{
    static u8 before[LIB_SIZE];
    FILE *f = fopen(path, "rb");
    u8 loc[128], *d;
    place_t p;
    uptr h;
    int k;
    u32 o;

    if (!f) {
        printf("(no M3U.LIB at %s: the test on the player's library is skipped)\n", path);
        return;
    }
    reset_disk();
    lib = add_node(0, "M3U.LIB", 0, NULL);
    node_room(lib, LIB_SIZE);
    nodes[lib].size = (u32)fread(nodes[lib].data, 1, LIB_SIZE, f);
    fclose(f);
    d = (u8 *)nodes[lib].data;
    memcpy(before, d, LIB_SIZE);

    h = lib_open();
    CHECK(h != 0, "the player's library does not open");
    if (!h)
        return;
    memset(&p, 0, sizeof p);
    p.cluster = 2;
    p.entry = 0x580;
    CHECK(lib_find_list(h, &p) == 1, "Focus is not record 1");

    /* a new song to Focus: record 21, position 21, Focus's 11th */
    memset(loc, 0, sizeof loc);
    memcpy(loc + LOC_EXT, "MP3", 4);
    w32(loc, LOC_CLUSTER, 0x123456);
    w32(loc, LOC_ENTRY, 0x40);
    memset(loc + LOC_LAYER, 0x33, LAYER_SIZE);
    CHECK(lib_add_song(h, 1, loc, (const u8 *)"01 - New.mp3", 12), "adding a new song");
    CHECK(rd16(d, 0xa0) == 22 && rd16(d, 0xa4) == 11 && rd16(d, 0x4a00 + 0x2000 + 20) == 21, "new song: %u songs, Focus %u",
          rd16(d, 0xa0), rd16(d, 0xa4));
    o = SONGS + 21 * 256;
    CHECK(!memcmp(d + o, "01 - New.mp3\0\0", 14) && d[o + 0x38] == 1 && d[o + 0x39] == 0xff && d[o + 0x69] == 0xff && d[o + 0x6a] == 0
          && !memcmp(d + o + 0x94, "MP3\0\1\1\xff\xff", 8) && rd32(d, o + 0x9c) == 0x123456 && rd32(d, o + 0xa0) == 0x40
          && rd16(d, o + 0xa4) == 20 && rd16(d, o + 0xa6) == 22 && d[o + 0xa8] == 0x33 && d[o + 0xa8 + 72] == 0x33 && d[o + 0xa8 + 73] == 0,
          "the new song's record");
    CHECK(rd32(d, POS + 21 * 8) == 0x123456 && rd32(d, POS + 21 * 8 + 4) == 0x40, "the new song's position");
    CHECK(lib_add_song(h, 1, loc, (const u8 *)"01 - New.mp3", 12) && rd16(d, 0xa4) == 11 && rd16(d, 0xa0) == 22, "added twice");

    /* "01 - Biome" (song 8, in NothingMuch and New playlist 1) to Focus */
    w32(loc, LOC_CLUSTER, 0xe1683);
    w32(loc, LOC_ENTRY, 0xe0);
    CHECK(lib_add_song(h, 1, loc, (const u8 *)"x", 1) && rd16(d, 0xa0) == 22 && rd16(d, 0xa4) == 12 && rd16(d, 0x4a00 + 0x2000 + 22) == 8
          && d[SONGS + 8 * 256 + 0x38] == 0 && d[SONGS + 8 * 256 + 0x39] == 2 && d[SONGS + 8 * 256 + 0x3a] == 1, "a known song");

    /* two new playlists: the order moves from sector 4 to 4 and then 5 */
    p.entry = 0x960;
    memset(p.layer, 0x44, LAYER_SIZE);
    k = lib_add_list(h, &p, (const u8 *)"New playlist 4", 14);
    CHECK(k == 5 && rd16(d, 8) == 6 && rd16(d, 0x24) == 4 && rd16(d, 0x26) == 5, "playlist 6: %d, order in %u", k, rd16(d, 0x24));
    CHECK(rd16(d, 4 * 512) == 1 && rd16(d, 4 * 512 + 8) == 0 && rd16(d, 4 * 512 + 10) == 5 && rd16(d, 5 * 512) == 4 && rd16(d, 5 * 512 + 10) == 5,
          "order and inverse with playlist 6");
    o = 0x200 + 5 * 256;
    CHECK(d[o] == 0xff && d[o + 1] == 0xfe && d[o + 2] == 'N' && d[o + 3] == 0 && d[o + 28] == '4' && d[o + 30] == 0
          && !memcmp(d + o + 0x94, "M3U\0\0\1\0\0", 8) && rd32(d, o + 0x9c) == 2 && rd32(d, o + 0xa0) == 0x960
          && rd16(d, o + 0xa4) == 4 && rd16(d, o + 0xa6) == 6 && d[o + 0xa8] == 0x44, "the new playlist's record");
    p.entry = 0x9c0;
    k = lib_add_list(h, &p, (const u8 *)"New playlist 5", 14);
    CHECK(k == 6 && rd16(d, 8) == 7 && rd16(d, 0x24) == 5 && rd16(d, 0x26) == 6 && rd16(d, 5 * 512 + 12) == 6 && rd16(d, 6 * 512 + 12) == 6,
          "playlist 7: %d, order in %u", k, rd16(d, 0x24));
    CHECK(rd32(d, 0x200 + 6 * 256 + 0xa0) == 0x9c0, "playlist 7's record is where the order was");
    w32(loc, LOC_CLUSTER, 0x123456);
    w32(loc, LOC_ENTRY, 0x40);
    CHECK(lib_add_song(h, 6, loc, (const u8 *)"01 - New.mp3", 12) && rd16(d, 0xa2 + 12) == 1 && rd16(d, 0x4a00 + 6 * 0x2000) == 21
          && d[SONGS + 21 * 256 + 0x39] == 6, "a song in playlist 7");

    /* "01 - Biome" out of Focus again, and "01 - 4-30" (song 9, in Focus and New playlist 3) too */
    w32(loc, LOC_CLUSTER, 0xe1683);
    w32(loc, LOC_ENTRY, 0xe0);
    CHECK(lib_remove_song(h, 1, loc) && rd16(d, 0xa4) == 11 && d[SONGS + 8 * 256 + 0x3a] == 0xff && d[SONGS + 8 * 256 + 0x39] == 2,
          "removing a song");
    w32(loc, LOC_CLUSTER, 0xa8e09);
    w32(loc, LOC_ENTRY, 0xc0);
    CHECK(lib_remove_song(h, 1, loc) && rd16(d, 0xa4) == 10 && rd16(d, 0x4a00 + 0x2000) == 10 && d[SONGS + 9 * 256 + 0x38] == 4
          && d[SONGS + 9 * 256 + 0x39] == 0xff, "removing the first song of Focus");
    CHECK(!lib_remove_song(h, 1, loc), "removing it twice");
    lib_close(h);

    /* nothing else changed: compare outside what was written */
    for (o = 0; o < LIB_SIZE; o++) {
        int written = o == 8 || o == 9 || o == 0x24 || o == 0x25 || o == 0x26 || o == 0x27 || (o >= 0xa0 && o < 0xa2)
                   || (o >= 0xa2 && o < 0xa2 + 14) || (o >= 0x106 && o < 0x106 + 14) || (o >= 0x700 && o < 0x900)
                   || (o >= 4 * 512 && o < 7 * 512) || (o >= 0x4a00 + 0x2000 && o < 0x4a00 + 0x2000 + 24)
                   || (o >= 0x4a00 + 6 * 0x2000 && o < 0x4a00 + 6 * 0x2000 + 2) || (o >= SONGS + 8 * 256 + 0x38 && o < SONGS + 8 * 256 + 0x6a)
                   || (o >= SONGS + 9 * 256 + 0x38 && o < SONGS + 9 * 256 + 0x6a) || (o >= SONGS + 21 * 256 && o < SONGS + 22 * 256)
                   || (o >= POS + 21 * 8 && o < POS + 22 * 8);
        if (!written && d[o] != before[o]) {
            CHECK(0, "byte %#x changed", o);
            break;
        }
    }
}

/* ------------------------------------------------------------------ stage 21: the lists' options */

static const char *LOVE = "Music\\16 Bit Lolitas\\Stardust EP\\02 - Love Left (original mix).mp3\r\n";
static const char *DANGER = "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n";
static const char *X = "Music\\A\\B\\x.mp3\r\n";

static void set_file(int node, const char *text)
{
    snprintf(nodes[node].data, nodes[node].cap, "%s", text);
    nodes[node].size = (u32)strlen(text);
}

static void test_song_lists(void)
{
    u8 pi[128];
    char want[1024];
    dir_brow_t b;
    u32 r;
    int n;

    disk();
    browse_mode = BROWSE_SONGS;
    album_level = 0;
    album_count = 0;
    albums[album_count++] = nodes[song].parent;      /* Stardust EP: 02 - Love Left, 01 - Stardust */
    albums[album_count++] = find("B");

    /* a song: row 1 of the album, to Focus */
    browser_enter_dir(BROW_SON, 1, &b);
    keys(2, EV_NEXT, EV_SELECT);
    r = list_option(pi, RESULT_ADD_FAVOR1, 1);
    snprintf(want, sizeof want, "%s%s", DANGER, LOVE);
    content_is(focus, want, __LINE__);
    check_library(__LINE__);
    CHECK(r == RESULT_REDRAW && !strcmp(last_message, "text 12: \"02 - Love Left (original mix).mp3\", Focus"),
          "song: %#x %s", r, last_message);
    CHECK(writes_while_playing == 0 && status == PLAY_PLAYING, "song: %d writes while playing", writes_while_playing);

    /* an album: all its songs, to a new playlist */
    browser_enter_dir(BROW_PARENT, 0, &b);
    keys(1, EV_SELECT);
    r = list_option(pi, RESULT_ADD_FAVOR1, 1);
    n = find("New playlist 1.m3u");
    CHECK(n >= 0 && r == RESULT_REDRAW && album_level == 0 && find("New playlist 2.m3u") < 0, "album: %d %#x level %d", n, r, album_level);
    if (n >= 0) {
        snprintf(want, sizeof want, "%s%s", LOVE, LINE);
        content_is(n, want, __LINE__);
    }
    check_library(__LINE__);
    CHECK(!strcmp(last_message, "text 12: \"Stardust EP\", New playlist 1"), "album message: %s", last_message);

    /* the album again, to the same playlist: nothing new */
    keys(4, EV_NEXT, EV_NEXT, EV_NEXT, EV_SELECT);
    r = list_option(pi, RESULT_ADD_FAVOR1, 1);
    CHECK(last_dialog_text == S_ALREADY_ADDED, "album again: text %d", last_dialog_text);
    check_library(__LINE__);

    /* a second album to Focus */
    keys(2, EV_NEXT, EV_SELECT);
    list_option(pi, RESULT_ADD_FAVOR1, 2);
    snprintf(want, sizeof want, "%s%s%s", DANGER, LOVE, X);
    content_is(focus, want, __LINE__);
    check_library(__LINE__);

    /* other results and rows on top of the list go elsewhere */
    stock_calls = 0;
    r = list_option(pi, RESULT_PLAYING_START, 1);
    CHECK(stock_calls == 1 && r == RESULT_PLAYING_START, "play: %d %#x", stock_calls, r);
    r = list_option(pi, RESULT_ADD_FAVOR1, 0);
    CHECK(stock_calls == 1 && r == RESULT_REDRAW, "row 0: %d %#x", stock_calls, r);
}

static int m3u_row(const char *name)                 /* the row (from 1) of a playlist in the Playlists list */
{
    const u8 *d = (const u8 *)nodes[lib].data;
    u32 n = rd16(d, 8), at = rd16(d, 0x24), k, rec;
    int i;
    for (k = 0; k < n; k++) {
        rec = rd16(d, at * 512 + 2 * k);
        for (i = 0; name[i] && d[0x200 + rec * 256 + 2 + 2 * i] == (u8)name[i]; i++)
            ;
        if (!name[i] && !d[0x200 + rec * 256 + 2 + 2 * i])
            return (int)k + 1;
    }
    return -1;
}

static void test_playlists(void)
{
    u8 pi[128];
    char want[2048];
    dir_brow_t b;
    u32 r;
    int c, i, songs[6];

    disk();
    c = add_node(find("B"), "y.mp3", 0, NULL);
    (void)c;
    snprintf(want, sizeof want, "%s%s%s", DANGER, X, LINE);
    set_file(focus, want);
    rebuild_library();
    browse_mode = BROWSE_M3U;
    m3u_cur = 0xffff;
    browser_enter_dir(BROW_SON, m3u_row("Focus"), &b);

    /* "Delete" on a song: a question (Yes first), then the song is out of the file and the library */
    questions = 0;
    answer = RESULT_DIALOG_YES;
    r = m3u_option(pi, RESULT_DEL_FAVOR, 2);
    CHECK(r == RESULT_DELETE_FILE && questions == 1 && last_default == 0, "remove: %#x, %d questions", r, questions);
    snprintf(want, sizeof want, "%s%s%s", DANGER, LINE, filler((int)strlen(X)));
    content_is(focus, want, __LINE__);
    check_library(__LINE__);
    CHECK(!strcmp(last_message, "text 14: \"x.mp3\", Focus"), "remove message: %s", last_message);

    /* No: nothing */
    answer = 0x8307;
    r = m3u_option(pi, RESULT_DEL_FAVOR, 1);
    CHECK(r == RESULT_REDRAW, "no: %#x", r);
    content_is(focus, want, __LINE__);
    answer = RESULT_DIALOG_YES;

    /* "Move song": the first one down by one */
    keys(2, EV_NEXT, EV_SELECT);
    r = m3u_option(pi, RESULT_CLR_FAVOR, 1);
    snprintf(want, sizeof want, "%s%s%s", LINE, DANGER, filler((int)strlen(X)));
    content_is(focus, want, __LINE__);
    check_library(__LINE__);
    CHECK(r == RESULT_REDRAW && last_title == S_MOVE, "move: %#x", r);

    /* Back keeps the order; while moving, the rows show the new order */
    keys(2, EV_PREV, EV_BACK);
    r = m3u_option(pi, RESULT_CLR_FAVOR, 2);
    content_is(focus, want, __LINE__);
    CHECK(r == RESULT_REDRAW && !strcmp(shown[0], "01 - 4-30.mp3") && !strcmp(shown[1], "01 - Stardust (original mix).mp3"),
          "moving rows: '%s' '%s'", shown[0], shown[1]);

    /* a longer playlist, the last one to the top, a file without a line end at its end */
    songs[0] = find("01 - 4-30.mp3");
    songs[1] = find("x.mp3");
    songs[2] = find("y.mp3");
    songs[3] = find("02 - Love Left (original mix).mp3");
    songs[4] = song;
    snprintf(want, sizeof want, "#EXTM3U\r\n%s%sMusic\\A\\B\\y.mp3\r\n%s%s", DANGER, X, LOVE, LINE);
    want[strlen(want) - 2] = 0;
    set_file(focus, want);
    rebuild_library();
    keys(5, EV_PREV, EV_PREV, EV_PREV, EV_PREV, EV_SELECT);   /* the last line has no line end: not in the list */
    m3u_option(pi, RESULT_CLR_FAVOR, 4);
    snprintf(want, sizeof want, "#EXTM3U\r\n%s%s%sMusic\\A\\B\\y.mp3\r\n%s", LOVE, DANGER, X, LINE);
    want[strlen(want) - 2] = 0;
    content_is(focus, want, __LINE__);
    check_library(__LINE__);
    keys(3, EV_NEXT, EV_NEXT, EV_SELECT);            /* and the second one two down */
    m3u_option(pi, RESULT_CLR_FAVOR, 2);
    snprintf(want, sizeof want, "#EXTM3U\r\n%s%sMusic\\A\\B\\y.mp3\r\n%s%s", LOVE, X, DANGER, LINE);
    want[strlen(want) - 2] = 0;
    content_is(focus, want, __LINE__);
    check_library(__LINE__);
    (void)songs;

    /* a playlist longer than the copy's pieces: the last of twelve to the top and back to the end */
    {
        char line[12][128], name[64];
        int k;
        want[0] = 0;
        for (k = 0; k < 12; k++) {
            snprintf(name, sizeof name, "%02d - a song with a rather long name number %d.mp3", k, k);
            add_node(find("B"), name, 0, NULL);
            snprintf(line[k], sizeof line[k], "Music\\A\\B\\%s\r\n", name);
            strcat(want, line[k]);
        }
        set_file(focus, want);
        rebuild_library();
        keys(1, EV_SELECT);
        for (k = 0; k < 11; k++)
            events[k] = EV_PREV;
        events[11] = EV_SELECT;
        event_count = 12;
        event_next = 0;
        m3u_option(pi, RESULT_CLR_FAVOR, 12);
        snprintf(want, sizeof want, "%s", line[11]);
        for (k = 0; k < 11; k++)
            strcat(want, line[k]);
        content_is(focus, want, __LINE__);
        check_library(__LINE__);
        for (k = 0; k < 11; k++)
            events[k] = EV_NEXT;
        event_next = 0;
        m3u_option(pi, RESULT_CLR_FAVOR, 1);
        for (want[0] = 0, k = 0; k < 12; k++)
            strcat(want, line[k]);
        content_is(focus, want, __LINE__);
        check_library(__LINE__);
    }

    /* the library and the list disagree: nothing happens */
    rows_extra = 1;
    r = m3u_option(pi, RESULT_DEL_FAVOR, 1);
    CHECK(r == RESULT_REDRAW && last_dialog_text == S_OPEN_FAILED, "disagree: %#x %d", r, last_dialog_text);
    rows_extra = 0;
    content_is(focus, want, __LINE__);

    /* the top: "Delete" deletes NothingMuch (No first), "Move song" does nothing */
    browser_enter_dir(BROW_PARENT, 0, &b);
    r = m3u_option(pi, RESULT_CLR_FAVOR, 1);
    CHECK(r == RESULT_REDRAW && !nodes[nothing].gone, "move at the top: %#x", r);
    removed_files = 0;
    r = m3u_option(pi, RESULT_DEL_FAVOR, m3u_row("NothingMuch"));
    CHECK(r == RESULT_DELETE_DIRLIST && nodes[nothing].gone && removed_files == 1 && last_default == 1 && stops == 0,
          "delete: %#x gone %d removed %d", r, nodes[nothing].gone, removed_files);
    check_library(__LINE__);
    CHECK(!strcmp(last_message, "text 32787: \"NothingMuch\", "), "delete message: %s", last_message);

    /* deleting the playlist the engine plays from stops the engine */
    for (i = 0; i < 3; i++) {                        /* more playlists, so that the last record moves */
        keys(1, EV_SELECT);
        add_playing_to_playlist(0);
    }
    check_library(__LINE__);
    play(find("00 - a song with a rather long name number 0.mp3"));   /* a song of Focus, chosen in a playlist */
    source = FSEL_M3U;
    r = m3u_option(pi, RESULT_DEL_FAVOR, m3u_row("Focus"));
    CHECK(r == RESULT_DELETE_DIRLIST && nodes[focus].gone && stops == 1 && status == PLAY_STOPPED, "delete playing: %#x stops %d", r, stops);
    check_library(__LINE__);
    status = PLAY_PLAYING;

    /* other results go to the stock handler */
    stock_calls = 0;
    r = m3u_option(pi, RESULT_PLAYING_START, 1);
    CHECK(stock_calls == 1 && r == RESULT_PLAYING_START, "play: %d", stock_calls);
}

/* The music lists' top line per level (stage 24): the counter inside one album or playlist, else the level's name;
   at the top level the name of the list, from the browse path. */
static void test_list_style(void)
{
    static const struct { int source, type, layer, lists, songs, style, title; const char *what; } cases[] = {
        {FSEL_PLAYLIST, 2, 0, 4, 0, STYLE_NAMED, 17, "Artists"},
        {FSEL_PLAYLIST, 0, 0, 0, 186, STYLE_NAMED, 10, "All songs"},
        {FSEL_PLAYLIST, 1, 0, 9, 0, STYLE_NAMED, 8, "Albums"},
        {FSEL_PLAYLIST, 3, 0, 3, 0, STYLE_NAMED, 42, "Genres"},
        {FSEL_M3U, 0, 0, 3, 0, STYLE_NAMED, 72, "Playlists"},
        {0, 0, 0, 2, 5, STYLE_DIR, -1, "the top folder"},
        {FSEL_PLAYLIST, 9, 0, 2, 0, STYLE_DIR, -1, "an unknown list"},
        {FSEL_PLAYLIST, 2, 1, 2, 0, STYLE_NAMED, -1, "an artist's albums"},
        {FSEL_PLAYLIST, 1, 1, 0, 12, STYLE_COUNTED, -1, "an album of the Albums list"},
        {FSEL_M3U, 0, 1, 0, 4, STYLE_COUNTED, -1, "a playlist"},
        {FSEL_PLAYLIST, 2, 2, 0, 9, STYLE_COUNTED, -1, "an album of an artist"},
        {FSEL_PLAYLIST, 3, 3, 0, 1, STYLE_COUNTED, -1, "a genre's album with one song"},
        {0, 0, 1, 2, 3, STYLE_NAMED, -1, "a folder with folders and songs"},
        {0, 0, 3, 0, 11, STYLE_COUNTED, -1, "an album folder"},
        {FSEL_PLAYLIST, 2, 1, 0, 0, STYLE_NAMED, -1, "an empty level"},
    };
    u8 keep[8], *path = browse_path();
    unsigned i;
    style_t st;
    listbox_t box;

    memcpy(keep, path, sizeof keep);
    list_test = 1;
    for (i = 0; i < sizeof cases / sizeof cases[0]; i++) {
        path[0] = (u8)cases[i].source;
        path[6] = (u8)cases[i].type;
        path[7] = 0;
        level.layer_no = (u8)cases[i].layer;
        level.dir_total = (u16)cases[i].lists;
        level.file_total = (u16)cases[i].songs;
        memset(&box, 0, sizeof box);
        box.title.str = 0x1234;                      /* what the control filled in: the browser's name buffer */
        box.title.lang = TEXT_UTF16;
        st.id = STYLE_DIR;
        st.type = 1;
        last_style = 0;
        box_result = 2 + i;                          /* UI_NEED_SCROLL and others go back to the control unchanged */
        bar_clears = 0;
        CHECK(list_box(&st, &box, LIST_DRAW_ALL) == 2 + i && last_style == cases[i].style && last_mode == LIST_DRAW_ALL,
              "%s: style %#x", cases[i].what, last_style);
        CHECK(bar_clears == 1 && cleared_first && last_clear_pic == BAR_CLEAR && last_clear_x == BAR_CLEAR_X && last_clear_y == 0,
              "%s: the bar's middle is not cleared before the list (%d)", cases[i].what, bar_clears);
        if (cases[i].title >= 0)
            CHECK(last_title == cases[i].title && last_title_lang == TEXT_ID, "%s: title %d (type %#x)", cases[i].what,
                  last_title, last_title_lang);
        else
            CHECK(last_title == 0x1234 && last_title_lang == TEXT_UTF16, "%s: the title was changed", cases[i].what);
    }
    path[0] = FSEL_PLAYLIST;
    level.layer_no = 1;
    level.dir_total = 0;
    level.file_total = 5;
    st.id = STYLE_DIR;
    bar_clears = 0;
    list_box(&st, &box, LIST_DRAW_LIST);
    CHECK(last_style == STYLE_COUNTED && last_mode == LIST_DRAW_LIST && bar_clears == 0, "rows only: style %#x mode %d, %d clears",
          last_style, last_mode, bar_clears);

    list_test = 0;
    memcpy(path, keep, sizeof keep);
}

int main(int argc, char **argv)
{
    test_add();
    test_remove();
    test_previous();
    test_song_lists();
    test_playlists();
    test_list_style();
    test_real_library(argc > 1 ? argv[1] : "../../../x91_dump/device_files/2026-10-21/M3U.LIB");
    CHECK(refused_opens == 0, "%d files opened while another was open", refused_opens);
    printf("%s (%d failure%s)\n", failures ? "FAILED" : "all passed", failures, failures == 1 ? "" : "s");
    return failures != 0;
}
