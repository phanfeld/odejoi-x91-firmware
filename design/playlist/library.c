/* M3U.LIB, the library of the .m3u playlists that the Playlists list shows, brought up to date in place when the
 * player's own playlist actions change a playlist (Graphite stage 20).
 *
 * The library builder (PLAYLIST.AP) writes the whole file at "Update list?", after USB mode and at power-up, in
 * the SDK's layout (enhanced.h, plist_m3u_deal*.c; checked against the player's copy of 2026-10-21):
 *   sector 0   head: "M3U", the number of playlists (+8), the sector of the first playlist record (+10, 1), the
 *              item "ALLFILE" with the sectors of the playlists' sorted order and of its inverse (+0x24, +0x26);
 *              from +0xa0 the number of songs, the songs per playlist (u16[50]), the Audible files per playlist
 *   sector 1   playlist records of 256 bytes in folder order: name (UTF-16, no ".m3u"), "M3U", the directory
 *              entry of the .m3u (cluster +0x9c, offset +0xa0) and its folder chain (+0xa8)
 *   then       the sorted order (u16 record numbers) and its inverse, one sector each, right behind the records
 *   0x4a00     per playlist 0x2000 bytes: its songs as u16 song numbers, in the order of the .m3u
 *   0x68a00    song records of 256 bytes: the file name (one-byte text, at most 54 bytes), the playlists that
 *              use the song (+0x38, 50 bytes, 0xff = free), extension, directory entry, folder chain
 *   0x162a00   per song 8 bytes: cluster and offset of its directory entry, to find a song by its place
 * The music program reads the head again whenever it opens the library (MUSIC.AP 0x1c0c2164), so a change made
 * here shows the next time the Playlists list is opened.
 *
 * Writes are ordered so that the file stays readable after each one: new data first, the counts that make it
 * visible last. A playlist added here goes to the end of the sorted order, so that list positions the music
 * program keeps stay right; the next full build sorts it in.
 */
#include "fw.h"
#include "util.h"
#include "library.h"

#define SECTOR        512
#define REC           256
#define H_LISTS       8
#define H_FIRST       10
#define H_ORDER       0x24
#define H_INVERSE     0x26
#define H_SONGS       0xa0
#define H_COUNT       0xa2
#define H_AUDIBLE     0x106
#define INDEX         0x4a00
#define INDEX_SIZE    0x2000
#define SONGS         0x68a00
#define SONGS_MAX     4000
#define POS           0x162a00
#define LIB_SIZE      0x16aa00
#define R_USERS       0x38
#define R_EXT         0x94
#define R_ID3         0x98
#define R_FLAG        0x99
#define R_TRACK       0x9a
#define R_CLUSTER     0x9c
#define R_ENTRY       0xa0
#define R_PREV        0xa4
#define R_NEXT        0xa6
#define R_LAYER       0xa8
#define TITLE_MAX     54                 /* bytes of a song record's name, as the builder cuts it */
#define LIST_NAME_MAX 26                 /* characters of a playlist record's name */
#define CHUNK         64                 /* u16 values per read */
#define HALF          (REC / 2)          /* records are written in two halves, to keep the stack small */
#define ERROR         0xffffffffu

/* rd and wr are written into every caller: the loops that use them must not call into another code bank. */
static inline __attribute__((always_inline)) int rd(uptr h, u32 off, void *buf, u32 n)
{
    vfs(off, SEEK_FROM_SET, h, VFS_SEEK);
    return (u32)vfs((uptr)buf, n, h, VFS_READ) == n;
}

static inline __attribute__((always_inline)) int wr(uptr h, u32 off, const void *buf, u32 n)
{
    vfs(off, SEEK_FROM_SET, h, VFS_SEEK);
    return (u32)vfs((uptr)buf, n, h, VFS_WRITE) == n;
}

static u32 rd16(uptr h, u32 off)
{
    u16 v;
    return rd(h, off, &v, 2) ? v : ERROR;
}

static int wr16(uptr h, u32 off, u32 v)
{
    u16 x = (u16)v;
    return wr(h, off, &x, 2);
}

uptr lib_open(void)
{
    u16 name[9];
    u32 magic = 0, size = 0;
    uptr h;

    name[0] = 0xfeff;
    name[1] = 'M'; name[2] = '3'; name[3] = 'U'; name[4] = '.'; name[5] = 'L'; name[6] = 'I'; name[7] = 'B';
    name[8] = 0;
    vfs(CD_ROOT, 0, 0, VFS_CD);
    h = vfs((uptr)name, OPEN_MODIFY, 0, VFS_OPEN);
    if (!h)
        return 0;
    vfs((uptr)&size, h, 0, VFS_SIZE);
    if (size < LIB_SIZE || !rd(h, 0, &magic, 4) || magic != 0x0055334d || rd16(h, 510) != 0xaa55
        || rd16(h, H_FIRST) != 1 || rd16(h, H_LISTS) > LISTS_MAX || rd16(h, H_SONGS) > SONGS_MAX) {
        vfs(h, 0, 0, VFS_CLOSE);
        return 0;
    }
    return h;
}

void lib_close(uptr h)
{
    vfs(h, 0, 0, VFS_CLOSE);
}

int lib_find_list(uptr h, const place_t *p)
{
    u32 lists = rd16(h, H_LISTS), ce[2], k;

    for (k = 0; k < lists && k < LISTS_MAX; k++)
        if (rd(h, SECTOR + k * REC + R_CLUSTER, ce, 8) && ce[0] == p->cluster && ce[1] == p->entry)
            return (int)k;
    return -1;
}

/* The song whose directory entry is (cluster, entry): its number, -1 if the library has none, -2 on an error. */
static int find_song(uptr h, u32 total, u32 cluster, u32 entry)
{
    u32 buf[2 * 8], i, k, n;

    for (i = 0; i < total; i += n) {
        n = total - i < 8 ? total - i : 8;
        if (!rd(h, POS + i * 8, buf, n * 8))
            return -2;
        for (k = 0; k < n; k++)
            if (buf[2 * k] == cluster && buf[2 * k + 1] == entry)
                return (int)(i + k);
    }
    return -1;
}

/* The second half of a record, the same for playlists and songs. */
static void record_tail(u8 *b, const u8 *ext, int id3, u32 track, u32 cluster, u32 entry, u32 number, const u8 *layer)
{
    int k;

    set_bytes(b, 0, HALF);
    for (k = 0; k < 4; k++)
        b[R_EXT - HALF + k] = ext[k];
    b[R_ID3 - HALF] = (u8)id3;
    b[R_FLAG - HALF] = 1;
    put16(b + R_TRACK - HALF, track);
    put32(b + R_CLUSTER - HALF, cluster);
    put32(b + R_ENTRY - HALF, entry);
    put16(b + R_PREV - HALF, number - 1);
    put16(b + R_NEXT - HALF, number + 1);
    for (k = 0; k < LAYER_SIZE; k++)
        b[R_LAYER - HALF + k] = layer[k];
}

/* b: HALF bytes of the caller's */
static int write_song(uptr h, u32 i, int list, const u8 *loc, const u8 *name, int n, u8 *b)
{
    int k;

    set_bytes(b, 0, HALF);
    if (n > TITLE_MAX)
        n = TITLE_MAX;
    for (k = 0; k < n; k++)
        b[k] = name[k];
    set_bytes(b + R_USERS, 0xff, LISTS_MAX);
    b[R_USERS] = (u8)list;
    if (!wr(h, SONGS + i * REC, b, HALF))
        return 0;
    record_tail(b, loc + LOC_EXT, 1, 0xffff, get32(loc + LOC_CLUSTER), get32(loc + LOC_ENTRY), i, loc + LOC_LAYER);
    return wr(h, SONGS + i * REC + HALF, b, HALF);
}

static int write_list(uptr h, u32 k, const place_t *p, const u8 *name, int n)
{
    u8 b[HALF] __attribute__((aligned(4)));
    u8 ext[4];
    int i;

    set_bytes(b, 0, HALF);
    if (n > LIST_NAME_MAX)
        n = LIST_NAME_MAX;
    b[0] = 0xff;
    b[1] = 0xfe;
    for (i = 0; i < n; i++)
        b[2 + 2 * i] = name[i];
    if (!wr(h, SECTOR + k * REC, b, HALF))
        return 0;
    ext[0] = 'M'; ext[1] = '3'; ext[2] = 'U'; ext[3] = 0;
    record_tail(b, ext, 0, 0, p->cluster, p->entry, k, p->layer);
    return wr(h, SECTOR + k * REC + HALF, b, HALF);
}

/* The sorted order with record lists (the new one) at its end, in the sectors behind lists + 1 records. */
static int append_to_order(uptr h, u32 lists)
{
    u16 order[LISTS_MAX + 1];
    u32 at = rd16(h, H_ORDER), k, seen[2] = {0, 0};

    if (lists && (at < 2 || at > 36 || !rd(h, at * SECTOR, order, lists * 2)))
        return 0;
    for (k = 0; k < lists; k++) {                       /* the order must be a permutation, else leave it alone */
        if (order[k] >= lists || seen[order[k] >> 5] & 1u << (order[k] & 31))
            return 0;
        seen[order[k] >> 5] |= 1u << (order[k] & 31);
    }
    order[lists] = (u16)lists;
    at = 1 + (lists + 2) / 2;                           /* the first sector behind lists + 1 records */
    if (!wr(h, at * SECTOR, order, (lists + 1) * 2))
        return 0;
    for (k = 0; k <= lists; k++)                        /* the inverse: each record's place in the order */
        if (!wr16(h, (at + 1) * SECTOR + 2 * order[k], k))
            return 0;
    return wr16(h, H_ORDER, at) && wr16(h, H_INVERSE, at + 1);
}

int lib_add_list(uptr h, const place_t *p, const u8 *name, int n)
{
    u32 lists = rd16(h, H_LISTS);

    if (lists >= LISTS_MAX || !append_to_order(h, lists))
        return -1;
    if (!write_list(h, lists, p, name, n) || !wr16(h, H_COUNT + 2 * lists, 0) || !wr16(h, H_AUDIBLE + 2 * lists, 0)
        || !wr16(h, H_LISTS, lists + 1))
        return -1;
    return (int)lists;
}

int lib_add_song(uptr h, int list, const u8 *loc, const u8 *name, int n)
{
    u16 buf[CHUNK];
    u8 *users = (u8 *)buf;                              /* used one after the other */
    u32 total = rd16(h, H_SONGS), count = rd16(h, H_COUNT + 2 * list), base = INDEX + (u32)list * INDEX_SIZE;
    u32 cluster = get32(loc + LOC_CLUSTER), entry = get32(loc + LOC_ENTRY), i, k, m, at;
    int song;

    if (total > SONGS_MAX || count >= INDEX_SIZE / 2)
        return 0;
    song = find_song(h, total, cluster, entry);
    if (song == -2)
        return 0;
    if (song < 0) {                                     /* a song the library does not have yet */
        u32 pos[2];
        pos[0] = cluster;
        pos[1] = entry;
        if (total == SONGS_MAX || !write_song(h, total, list, loc, name, n, (u8 *)buf) || !wr(h, POS + total * 8, pos, 8)
            || !wr16(h, H_SONGS, total + 1))
            return 0;
        song = (int)total;
    } else {
        at = SONGS + (u32)song * REC + R_USERS;
        if (!rd(h, at, users, LISTS_MAX))
            return 0;
        for (k = 0; k < LISTS_MAX && users[k] != 0xff && (users[k] & 0x7f) != (u32)list; k++)
            ;
        if (k < LISTS_MAX && users[k] == 0xff) {
            users[k] = (u8)list;
            if (!wr(h, at + k, users + k, 1))
                return 0;
        }
        for (i = 0; i < count; i += m) {                /* in the playlist already: nothing to add */
            m = count - i < CHUNK ? count - i : CHUNK;
            if (!rd(h, base + i * 2, buf, m * 2))
                return 0;
            for (k = 0; k < m; k++)
                if ((buf[k] & 0x7fffu) == (u32)song)
                    return 1;
        }
    }
    return wr16(h, base + count * 2, (u32)song) && wr16(h, H_COUNT + 2 * list, count + 1);
}

/* In the list of playlists using song: playlist from becomes to; to = 0xff takes it out (the rest moves up). */
static void users_change(uptr h, u32 song, u32 from, u32 to)
{
    u8 users[LISTS_MAX];
    u32 at = SONGS + song * REC + R_USERS, k, kept;

    if (!rd(h, at, users, LISTS_MAX))
        return;
    for (k = kept = 0; k < LISTS_MAX; k++) {
        if (users[k] == 0xff)
            continue;
        if ((users[k] & 0x7f) == from) {
            if (to == 0xff)
                continue;
            users[k] = (u8)((users[k] & 0x80) | to);
        }
        users[kept++] = users[k];
    }
    set_bytes(users + kept, 0xff, (int)(LISTS_MAX - kept));
    wr(h, at, users, LISTS_MAX);
}

int lib_remove_song(uptr h, int list, const u8 *loc)
{
    u16 buf[CHUNK];
    u32 total = rd16(h, H_SONGS), count = rd16(h, H_COUNT + 2 * list), base = INDEX + (u32)list * INDEX_SIZE;
    u32 r, w = 0, m, k, kept;
    int song;

    if (total > SONGS_MAX || count > INDEX_SIZE / 2)
        return 0;
    song = find_song(h, total, get32(loc + LOC_CLUSTER), get32(loc + LOC_ENTRY));
    if (song < 0)
        return 0;
    for (r = 0; r < count; r += m) {                    /* the entries behind move up; w <= r, so nothing unread is overwritten */
        m = count - r < CHUNK ? count - r : CHUNK;
        if (!rd(h, base + r * 2, buf, m * 2))
            return 0;
        for (k = kept = 0; k < m; k++)
            if ((buf[k] & 0x7fffu) != (u32)song)
                buf[kept++] = buf[k];
        if (kept && (w != r || kept != m) && !wr(h, base + w * 2, buf, kept * 2))
            return 0;
        w += kept;
    }
    if (w != count && !wr16(h, H_COUNT + 2 * list, w))
        return 0;
    users_change(h, (u32)song, (u32)list, 0xff);
    return w != count;
}

int lib_lists(uptr h)
{
    return (int)rd16(h, H_LISTS);
}

int lib_order(uptr h, int k)
{
    u32 at = rd16(h, H_ORDER), lists = rd16(h, H_LISTS), r;

    if (k < 0 || (u32)k >= lists || at < 2 || at > 36)
        return -1;
    r = rd16(h, at * SECTOR + 2 * (u32)k);
    return r < lists ? (int)r : -1;
}

int lib_list(uptr h, int list, place_t *p, u16 *name)
{
    u32 at = SECTOR + (u32)list * REC;

    if (list < 0 || (u32)list >= rd16(h, H_LISTS))
        return 0;
    if (name && !rd(h, at, name, 56))
        return 0;
    if (name)
        name[27] = 0;
    return !p || (rd(h, at + R_CLUSTER, &p->cluster, 8) && rd(h, at + R_LAYER, p->layer, LAYER_SIZE));
}

int lib_set_list(uptr h, int list, const place_t *p, const u16 *name)
{
    u16 b[28];
    u32 at = SECTOR + (u32)list * REC, ce[2];
    int i;

    if (list < 0 || (u32)list >= rd16(h, H_LISTS))
        return 0;
    set_bytes(b, 0, sizeof b);
    b[0] = 0xfeff;
    for (i = 0; i < LIST_NAME_MAX && name[1 + i]; i++)
        b[1 + i] = name[1 + i];
    ce[0] = p->cluster;
    ce[1] = p->entry;
    return wr(h, at + R_CLUSTER, ce, 8) && wr(h, at + R_LAYER, p->layer, LAYER_SIZE) && wr(h, at, b, sizeof b);
}

int lib_count(uptr h, int list)
{
    u32 n = rd16(h, H_COUNT + 2 * (u32)list);
    return n <= INDEX_SIZE / 2 ? (int)n : -1;
}

int lib_song(uptr h, int list, int pos, place_t *p)
{
    u32 s = rd16(h, INDEX + (u32)list * INDEX_SIZE + 2 * (u32)pos), at;

    if (s == ERROR || (s & 0x7fff) >= rd16(h, H_SONGS))
        return -1;
    s &= 0x7fff;
    at = SONGS + s * REC;
    if (p && !(rd(h, at + R_CLUSTER, &p->cluster, 8) && rd(h, at + R_LAYER, p->layer, LAYER_SIZE)))
        return -1;
    return (int)s;
}

int lib_has_song(uptr h, int list, const u8 *loc)
{
    u8 users[LISTS_MAX];
    int song = find_song(h, rd16(h, H_SONGS), get32(loc + LOC_CLUSTER), get32(loc + LOC_ENTRY)), k;

    if (song < 0 || !rd(h, SONGS + (u32)song * REC + R_USERS, users, LISTS_MAX))
        return 0;
    for (k = 0; k < LISTS_MAX; k++)
        if (users[k] != 0xff && (users[k] & 0x7f) == (u32)list)
            return 1;
    return 0;
}

/* Copies n u16 entries from src to dst (byte offsets); overlapping ranges are fine either way. */
static int move_entries(uptr h, u32 dst, u32 src, u32 n)
{
    u16 buf[CHUNK];
    u32 i, m;

    if (dst < src) {
        for (i = 0; i < n; i += m) {
            m = n - i < CHUNK ? n - i : CHUNK;
            if (!rd(h, src + 2 * i, buf, m * 2) || !wr(h, dst + 2 * i, buf, m * 2))
                return 0;
        }
    } else if (dst > src) {
        for (i = n; i > 0; i -= m) {
            m = i < CHUNK ? i : CHUNK;
            if (!rd(h, src + 2 * (i - m), buf, m * 2) || !wr(h, dst + 2 * (i - m), buf, m * 2))
                return 0;
        }
    }
    return 1;
}

int lib_move_song(uptr h, int list, int from, int to)
{
    u32 count = rd16(h, H_COUNT + 2 * (u32)list), base = INDEX + (u32)list * INDEX_SIZE, v;

    if (count > INDEX_SIZE / 2 || from < 0 || to < 0 || (u32)from >= count || (u32)to >= count)
        return 0;
    v = rd16(h, base + 2 * (u32)from);
    if (v == ERROR)
        return 0;
    if (from < to && !move_entries(h, base + 2 * (u32)from, base + 2 * (u32)from + 2, (u32)(to - from)))
        return 0;
    if (from > to && !move_entries(h, base + 2 * (u32)to + 2, base + 2 * (u32)to, (u32)(from - to)))
        return 0;
    return wr16(h, base + 2 * (u32)to, v);
}

/* The users of the songs of a playlist: from becomes to (0xff: out). */
static int list_users(uptr h, u32 list, u32 from, u32 to)
{
    u16 buf[CHUNK];
    u32 count = rd16(h, H_COUNT + 2 * list), base = INDEX + list * INDEX_SIZE, i, k, m;

    if (count > INDEX_SIZE / 2)
        return 0;
    for (i = 0; i < count; i += m) {
        m = count - i < CHUNK ? count - i : CHUNK;
        if (!rd(h, base + 2 * i, buf, m * 2))
            return 0;
        for (k = 0; k < m; k++)
            users_change(h, buf[k] & 0x7fffu, from, to);
    }
    return 1;
}

/* Playlist record from becomes record to, its previous and next numbers to's. */
static int copy_record(uptr h, u32 from, u32 to)
{
    u8 b[HALF] __attribute__((aligned(4)));
    u32 half;

    for (half = 0; half < REC; half += HALF) {
        if (!rd(h, SECTOR + from * REC + half, b, HALF))
            return 0;
        if (half) {
            put16(b + R_PREV - HALF, to - 1);
            put16(b + R_NEXT - HALF, to + 1);
        }
        if (!wr(h, SECTOR + to * REC + half, b, HALF))
            return 0;
    }
    return 1;
}

/* The sorted order without playlist list, the last record renumbered to list. */
static int drop_from_order(uptr h, u32 list, u32 lists)
{
    u16 order[LISTS_MAX];
    u32 last = lists - 1, at = rd16(h, H_ORDER), k, n;

    if (at < 2 || at > 36 || !rd(h, at * SECTOR, order, lists * 2))
        return 0;
    for (k = n = 0; k < lists; k++)
        if (order[k] != (u32)list)
            order[n++] = (u16)(order[k] == last ? list : order[k]);
    at = 1 + (n + 1) / 2;                               /* the first sector behind n records */
    if (!wr(h, at * SECTOR, order, n * 2))
        return 0;
    for (k = 0; k < n; k++)
        if (!wr16(h, (at + 1) * SECTOR + 2 * order[k], k))
            return 0;
    return wr16(h, H_ORDER, at) && wr16(h, H_INVERSE, at + 1);
}

int lib_delete_list(uptr h, int list)
{
    u32 lists = rd16(h, H_LISTS), last, count;

    if (list < 0 || (u32)list >= lists || lists > LISTS_MAX)
        return 0;
    last = lists - 1;
    if (rd16(h, H_ORDER) < 2 || !list_users(h, (u32)list, (u32)list, 0xff))
        return 0;
    if ((u32)list != last) {                            /* the last playlist moves into the freed record */
        count = rd16(h, H_COUNT + 2 * last);
        if (!list_users(h, last, last, (u32)list)
            || !move_entries(h, INDEX + (u32)list * INDEX_SIZE, INDEX + last * INDEX_SIZE, count)
            || !wr16(h, H_COUNT + 2 * (u32)list, count) || !wr16(h, H_AUDIBLE + 2 * (u32)list, rd16(h, H_AUDIBLE + 2 * last))
            || !copy_record(h, last, (u32)list))
            return 0;
    }
    return drop_from_order(h, (u32)list, lists) && wr16(h, H_COUNT + 2 * last, 0) && wr16(h, H_AUDIBLE + 2 * last, 0)
        && wr16(h, H_LISTS, last);
}
