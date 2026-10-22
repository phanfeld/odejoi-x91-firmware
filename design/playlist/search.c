/* "Search" in the options of the music lists, with a T9 keypad (Graphite stage 25).
 *
 * Menu -> Search in Playlists, All songs, Artists, Albums or Genres, at any level (an artist's albums, an album, a
 * playlist), opens a keypad over that level's rows. Each key stands for its letters and its digit (2 abc, 3 def ...
 * 9 wxyz), one press per letter, as T9 did: 2-3-2 finds "Beatles" and "Abba". A row matches when the keys spell the
 * beginning of one of its words; spaces and signs in the name are skipped, so 8-4-3-2-3-2 finds "The Beatles" too.
 * Accented Latin letters count as their base letter (é as e, ł as l), digits as themselves.
 *
 * The screen (128 x 160, rows of 16 pixels): the status bar with "Search"; the query line, with the letters the
 * first match spells there (the digits typed while nothing is found yet) and the number of matches; four result
 * lines; at the bottom the keypad, 1, 2 abc, 3 def / 4 ghi, 5 jkl, 6 mno / 7 pqrs, 8 tuv, 9 wxyz / Del, 0, OK.
 *
 * Keys: Up, Down, Previous and Next move on the keypad, Play types the key. Up from its top row, OK or Menu go to
 * the results; there Up and Down move (Previous and Next by four), Play opens the row, Down from the last one goes
 * back to the keypad's top row, and so do Return and Menu (to the key it was on). Return deletes the last key, held
 * it deletes them all, and with nothing typed it leaves the search. Other keys (volume) work as in a menu.
 *
 * A chosen row is opened the way Select opens it in the list: an artist, album, genre or playlist shows its rows, a
 * song plays. The list itself stands on that row, so Back (or leaving the playing screen) comes back to it.
 *
 * How the level is searched: the rows' names come from the list's own browser, as the list reads them, a few rows
 * per call. A bit per row (4000 rows at most, the library's limit) marks the rows that may still match: a further
 * key tests only those again, deleting a key marks all of them. The search runs between key presses, so typing
 * never waits for it: a key restarts it with the new query, and matches show as they are found.
 *
 * While the screen shows, the app timers of the list (the scrolling of its chosen row) are held by a timer tag of
 * the search's own, and the display's colours are given back afterwards.
 */
#include "fw.h"
#include "util.h"
#include "search.h"

#define QMAX      16                     /* keys a query holds */
#define MAXROWS   4000                   /* rows searched: the library holds 4000 songs at most */
#define WORDS     ((MAXROWS + 31) / 32)
#define BATCH     3                      /* rows read from the browser at a time (it opens the library each time) */
#define SCAN_ROWS 12                     /* rows tested before the search looks for keys again */
#define NAMELEN   ROW_NAME               /* a row's name: the browser writes at most ROW_NAME - 2 bytes and two zeros */
#define PRED      16                     /* characters of the spelled letters shown */
#define SHOWN     4                      /* result lines */

#define KEYS      12                     /* keys 0 to 8 are 1 to 9; then Del, 0, OK */
#define K_DEL     9
#define K_ZERO    10
#define K_OK      11

#define Y_QUERY   16                     /* the screen: status bar, query line, 4 result lines, 4 rows of keys */
#define Y_LIST    32
#define Y_KEYS    96
#define LINE      16
#define KEY_W     41                     /* a key, 41 x 15, one pixel apart */
#define KEY_H     15
#define DIGIT_W   12                     /* a key's digit centred in its first 12 pixels, its letters in the rest */
#define TITLE_X   22                     /* the status bar's title, where the menus have theirs (stage 24) */
#define TITLE_W   76
#define COUNT_X   80                     /* the number of matches, right-aligned up to x = 123 */

/* The theme's colours as RGB565; build_stage25.py passes the theme's own, these are Amber's. */
#ifndef COL_BG
#define COL_BG        0x0000
#define COL_SURFACE   0x18e4
#define COL_LINE      0x2987
#define COL_TEXT      0xf7be
#define COL_TEXT2     0x8cb4
#define COL_ACCENT    0xfd80
#define COL_ON_ACCENT 0x0862
#endif

#define TAG_SEARCH 0x8e                  /* the app timer tag while the search shows (the SDK's tags end at 0x8d) */

enum { ENC_BYTE, ENC_WIDE, ENC_UTF8 };
enum { ON_KEYS, ON_LIST };
enum { STAY = 0, LEAVE = -1, PASS = -2 };   /* what a key does; a chosen row is above 0 */

typedef struct {
    u32 bits[WORDS];                     /* rows that may match: below pos they do, from pos on they did so far */
    u16 pred[PRED + 2];                  /* FF FE, the letters the first match spells, 0 */
    union {                              /* a key message, or another message for the program */
        u8 gui[8];
        u8 app[24];
    } msg __attribute__((aligned(4)));
    u8 q[QMAX];                          /* the keys typed: digits */
    int qlen, rows, pos, found;          /* found: the matches below pos */
    int focus, key, sel, top;            /* the keypad's key; the chosen result and the first one shown (match numbers) */
    int counted;                         /* what the count shows: found * 2 + still searching */
    u32 result;                          /* the result of a system message that ends the search */
} search_t;

/* ------------------------------------------------------------------ names, letters and keys */

static int start_of(const u8 *s, int *enc)
{
    if (s[0] == 0xff && s[1] == 0xfe) {
        *enc = ENC_WIDE;
        return 2;
    }
    if (s[0] == 0xef && s[1] == 0xbb && s[2] == 0xbf) {
        *enc = ENC_UTF8;
        return 3;
    }
    *enc = ENC_BYTE;
    return 0;
}

/* The next character of a name as a code point (0 at its end); one-byte names are code page 1252 (the player's
   English, German, French or Spanish), whose letters at 0x80 to 0x9f are taken over here. */
static u32 next_cp(const u8 *s, int *at, int enc)
{
    int i = *at, more;
    u32 c;

    if (i >= NAMELEN - 1)
        return 0;
    c = s[i];
    if (enc == ENC_WIDE) {
        *at = i + 2;
        return c | (u32)s[i + 1] << 8;
    }
    if (!c)
        return 0;
    *at = ++i;
    if (enc == ENC_UTF8 && c >= 0xc0) {
        more = c >= 0xe0 ? 2 : 1;
        c &= c >= 0xe0 ? 0x0f : 0x1f;
        while (more-- && i < NAMELEN && (s[i] & 0xc0) == 0x80)
            c = c << 6 | (s[i++] & 0x3f);
        *at = i;
    } else if (enc == ENC_BYTE && c >= 0x8a && c < 0xa0) {   /* S, OE and Z with caron (0x8x, small 0x9x), Y diaeresis */
        u32 big = c & 0xef, small = c >> 4 & 1;
        c = big == 0x8a ? 0x160 + small : big == 0x8c ? 0x152 + small : big == 0x8e ? 0x17d + small : c == 0x9f ? 0x178 : c;
    }
    return c;
}

/* The key of a character: its digit, or the key its letter is on (accented Latin letters as their base letter);
   -1 for anything else (spaces, signs). Latin-1 (U+00C0 to U+00FF, upper case 0x20 below lower case) and Latin
   Extended-A (U+0100 to U+017F) run through the alphabet, so a few stretches per key cover them. */
static int key_of(u32 c)
{
    if (c - '0' < 10)
        return (int)(c - '0');
    if (c - 'A' < 26 || c - 'a' < 26) {
        c = (c | 0x20) - 'a';
        return c < 15 ? 2 + (int)c / 3 : c < 19 ? 7 : c < 22 ? 8 : 9;
    }
    if (c >= 0x100)                                     /* a c / d e / g h i ij / j k l / n o oe / r s / t u / w y z / long s */
        return c >= 0x180 ? -1 : c < 0x10e ? 2 : c < 0x11c ? 3 : c < 0x134 ? 4 : c < 0x143 ? 5 : c < 0x154 ? 6
             : c < 0x162 ? 7 : c < 0x174 ? 8 : c < 0x17f ? 9 : 7;
    if (c < 0xc0)
        return -1;
    if (c == 0xdf)                                      /* sharp s */
        return 7;
    c |= 0x20;                                          /* a ae c / e / i / eth / (times, divided) / n o o-slash / u / y / thorn */
    return c < 0xe8 ? 2 : c < 0xec ? 3 : c < 0xf0 ? 4 : c == 0xf0 ? 3 : c == 0xf7 ? -1 : c < 0xf9 ? 6 : c < 0xfd ? 8
         : c == 0xfe ? 8 : 9;
}

/* Whether the keys q[0 .. n) spell the name from byte at on, letter by letter, skipping signs; *to: where they end. */
static inline __attribute__((always_inline)) int spells(const u8 *s, int at, int enc, const u8 *q, int n, int *to)
{
    int j = 0, k;
    u32 c;

    while (j < n) {
        c = next_cp(s, &at, enc);
        if (!c)
            return 0;
        k = key_of(c);
        if (k < 0)
            continue;
        if (k != q[j])
            return 0;
        j++;
    }
    *to = at;
    return 1;
}

/* Whether the keys spell the beginning of a word of the name: the first such place as from | to << 8 (bytes of the
   name, which has at most NAMELEN), or -1. */
static int match(const u8 *s, const u8 *q, int n)
{
    int enc, at = start_of(s, &enc), here, k, prev = -1, to;
    u32 c;

    for (;;) {
        here = at;
        c = next_cp(s, &at, enc);
        if (!c)
            return -1;
        k = key_of(c);
        if (k >= 0 && prev < 0 && spells(s, here, enc, q, n, &to))
            return here | to << 8;
        prev = k;
    }
}

/* The letters of the name a match spans (from | to << 8), as UTF-16 with FF FE, into pred[PRED + 2]. */
static void spelled(u16 *pred, const u8 *s, int span)
{
    int enc, n = 1, from = span & 0xff, to = span >> 8;

    start_of(s, &enc);
    pred[0] = 0xfeff;
    while (from < to && n <= PRED)
        pred[n++] = (u16)next_cp(s, &from, enc);
    pred[n] = 0;
}

/* ------------------------------------------------------------------ the rows that may match */

static inline __attribute__((always_inline)) int marked(const search_t *st, int r) { return (int)(st->bits[r >> 5] >> (r & 31) & 1); }

static void mark_all(search_t *st)
{
    int w, left;

    for (w = 0; w < WORDS; w++) {
        left = st->rows - w * 32;
        st->bits[w] = left <= 0 ? 0 : left >= 32 ? ~0u : (1u << left) - 1;
    }
}

/* The first marked row from r on, or -1. */
static int next_row(const search_t *st, int r)
{
    int w;
    u32 b;

    for (w = r >> 5; w < WORDS && w * 32 < st->rows; w++) {
        b = st->bits[w];
        if (w == r >> 5)
            b &= ~0u << (r & 31);
        if (b) {
            r = w * 32 + __builtin_ctz(b);
            return r < st->rows ? r : -1;
        }
    }
    return -1;
}

/* The row of match m (from 0), or -1. */
static int match_row(const search_t *st, int m)
{
    int w;
    u32 b;

    for (w = 0; w * 32 < st->pos; w++) {
        b = st->bits[w];
        if (st->pos - w * 32 < 32)
            b &= (1u << (st->pos - w * 32)) - 1;
        for (; b; b &= b - 1)
            if (!m--)
                return w * 32 + __builtin_ctz(b);
    }
    return -1;
}

/* Rows row .. row+n-1 (from 0) into names[], as the list reads them. */
static void read_rows(u8 names[][NAMELEN], int row, int n)
{
    brow_decode_t d;
    file_brow_t f[BATCH];
    int k;

    set_bytes(f, 0, sizeof f);
    for (k = 0; k < n; k++) {
        set_bytes(names[k], 0, NAMELEN);
        f[k].name_len = NAMELEN;
        f[k].name_buf = (uptr)names[k];
    }
    d.option = 1;
    d.num = (u8)n;
    d.top = (u16)(row + 1);
    browser_get_items(&d, f);
}

/* ------------------------------------------------------------------ drawing */

static void fill(int x, int y, int w, int h, u32 colour)
{
    region_t r;

    r.x = (u16)x;
    r.y = (u16)y;
    r.w = (u16)w;
    r.h = (u16)h;
    ui(colour, 0, 0, UI_BACKGD);
    ui((uptr)&r, 0, 0, UI_CLEAR);
}

/* a panel with its corners cut, as the design's rounded ones look at this size */
static void panel(int x, int y, int w, int h, u32 colour)
{
    fill(x + 1, y, w - 2, h, colour);
    fill(x, y + 1, w, h - 2, colour);
}

/* A text of one line in a region 16 pixels high: UTF-16 with FF FE, UTF-8 with its mark, or one-byte text in the
   player's language (as the list's names come); only its dots are drawn. */
static void text(const void *s, int room, int x, int y, int w, u32 colour, u32 mode)
{
    const u8 *b = s;
    strdesc_t d;
    region_t r;

    set_bytes(&d, 0, sizeof d);
    d.str = (uptr)s;
    d.lang = b[0] == 0xff && b[1] == 0xfe ? TEXT_UTF16 : b[0] == 0xef && b[1] == 0xbb && b[2] == 0xbf ? TEXT_UTF8 : language();
    d.length = (u16)room;
    r.x = (u16)x;
    r.y = (u16)y;
    r.w = (u16)w;
    r.h = LINE;
    ui(colour, 0, 0, UI_PEN);
    ui((uptr)&d, (uptr)&r, DRAW_DOTS | NO_ARABIC | mode, UI_STRING);
}

/* Up to four ASCII characters packed in a word (the first in the low byte) put at w[n]; the new n. */
static int put4(u16 *w, int n, u32 chars)
{
    for (; chars; chars >>= 8)
        w[n++] = (u16)(chars & 0xff);
    w[n] = 0;
    return n;
}

static int put_number(u16 *w, int n, u32 v)
{
    u16 t[6];
    int k = 0;

    do
        t[k++] = (u16)('0' + v % 10);
    while ((v /= 10) && k < 6);
    while (k)
        w[n++] = t[--k];
    w[n] = 0;
    return n;
}

static int digit_of(int k) { return k < K_DEL ? k + 1 : k == K_ZERO ? 0 : -1; }

static void draw_key(const search_t *st, int k)
{
    u16 w[6];
    int x = 1 + k % 3 * (KEY_W + 1), y = Y_KEYS + k / 3 * LINE, d = digit_of(k), on = st->focus == ON_KEYS && st->key == k, i;
    u32 fg = on ? COL_ON_ACCENT : COL_TEXT, fg2 = on ? COL_ON_ACCENT : COL_TEXT2;

    fill(x, y, KEY_W, KEY_H, COL_BG);
    panel(x, y, KEY_W, KEY_H, on ? COL_ACCENT : COL_SURFACE);
    w[0] = 0xfeff;
    if (d < 2) {                                        /* 1, 0, Del, OK: alone in the middle */
        if (d >= 0)
            put4(w, 1, (u32)('0' + d));
        else
            put4(w, 1, k == K_DEL ? 'D' | 'e' << 8 | 'l' << 16 : 'O' | 'K' << 8);
        text(w, sizeof w, x, y - 1, KEY_W, d >= 0 ? fg : fg2, ALIGN_CENTRE | LONG_CUT);
        return;
    }
    put4(w, 1, (u32)('0' + d));
    text(w, sizeof w, x, y - 1, DIGIT_W, fg, ALIGN_CENTRE | LONG_CUT);
    for (i = 0; i < (d == 7 || d == 9 ? 4 : 3); i++)   /* 2 abc ... 7 pqrs, 8 tuv, 9 wxyz */
        w[1 + i] = (u16)('a' + 3 * (d - 2) + (d > 7) + i);
    w[1 + i] = 0;
    text(w, sizeof w, x + DIGIT_W - 1, y - 1, KEY_W - DIGIT_W + 3, fg2, ALIGN_CENTRE | LONG_CUT);
}

static int searching(const search_t *st) { return st->qlen && st->pos < st->rows; }

/* The number of matches (on the results: the chosen one's place too), with an ellipsis while the search goes on. */
static void draw_count(search_t *st)
{
    u16 w[12];                                          /* FF FE, "4000/4000", the ellipsis, 0 */
    int n = 1;

    st->counted = st->found * 2 + searching(st);
    fill(COUNT_X, Y_QUERY, 124 - COUNT_X, LINE - 2, COL_BG);
    if (!st->qlen)
        return;
    w[0] = 0xfeff;
    if (st->focus == ON_LIST && st->found) {
        n = put_number(w, n, (u32)st->sel + 1);
        w[n++] = '/';
    }
    if (st->found || !searching(st))
        n = put_number(w, n, (u32)st->found);
    if (searching(st))
        w[n++] = 0x2026;
    w[n] = 0;
    text(w, sizeof w, COUNT_X, Y_QUERY, 124 - COUNT_X, COL_TEXT2, ALIGN_RIGHT | LONG_CUT);
}

/* The query line: the letters the first match spells, else the digits typed; the line under it, in the accent while
   the keys type into it. The count is drawn by the callers (after the first match the search draws it). */
static void draw_query(search_t *st)
{
    int i;

    fill(0, Y_QUERY, 128, LINE, COL_BG);
    fill(4, Y_QUERY + LINE - 1, 120, 1, st->focus == ON_KEYS ? COL_ACCENT : COL_LINE);   /* below the descenders */
    if (st->found) {
        text(st->pred, sizeof st->pred, 6, Y_QUERY, COUNT_X - 8, COL_TEXT, ALIGN_LEFT | LONG_CUT);
    } else if (st->qlen) {                              /* nothing spelled yet: the digits, in its place */
        st->pred[0] = 0xfeff;
        for (i = 0; i < st->qlen; i++)
            st->pred[1 + i] = (u16)('0' + st->q[i]);
        st->pred[1 + i] = 0;
        text(st->pred, sizeof st->pred, 6, Y_QUERY, COUNT_X - 8, COL_TEXT2, ALIGN_LEFT | LONG_CUT);
    }
}

/* Result line i with the name of its row (0: an empty line). */
static void draw_line(const search_t *st, int i, const u8 *name)
{
    int y = Y_LIST + i * LINE, on = st->focus == ON_LIST && st->top + i == st->sel;

    fill(0, y, 128, LINE, COL_BG);
    if (on) {
        panel(1, y, 126, LINE - 1, COL_SURFACE);
        fill(3, y + 3, 2, 9, COL_ACCENT);
    }
    if (name)
        text(name, NAMELEN, 8, y, 116, COL_TEXT, ALIGN_LEFT | LONG_DOTS);
}

/* The result line of match m (an empty line past the matches), if it is shown. */
static void draw_match(const search_t *st, int m)
{
    u8 name[1][NAMELEN] __attribute__((aligned(4)));
    int row = m < st->found ? match_row(st, m) : -1;

    if (m < st->top || m >= st->top + SHOWN)
        return;
    if (row >= 0)
        read_rows(name, row, 1);
    draw_line(st, m - st->top, row >= 0 ? name[0] : 0);
}

static void draw_results(search_t *st)
{
    u16 w[12];
    int i;

    for (i = 0; i < SHOWN; i++)
        draw_match(st, st->top + i);
    if (st->qlen && !st->found && !searching(st)) {    /* "No matches" */
        w[0] = 0xfeff;
        put4(w, put4(w, put4(w, 1, 'N' | 'o' << 8 | ' ' << 16 | 'm' << 24), 'a' | 't' << 8 | 'c' << 16 | 'h' << 24),
             'e' | 's' << 8);
        text(w, sizeof w, 8, Y_LIST, 116, COL_TEXT2, ALIGN_LEFT | LONG_CUT);
    }
}

static void draw_all(search_t *st)
{
    u16 w[8];
    int k;

    headbar_all();                                      /* the status bar on, its middle empty (stage 24) */
    clear_bar();
    w[0] = 0xfeff;
    put4(w, put4(w, 1, 'S' | 'e' << 8 | 'a' << 16 | 'r' << 24), 'c' | 'h' << 8);
    text(w, sizeof w, TITLE_X, 0, TITLE_W, COL_TEXT2, ALIGN_LEFT | LONG_CUT);
    fill(0, LINE, 128, 160 - LINE, COL_BG);
    draw_query(st);
    draw_count(st);
    for (k = 0; k < KEYS; k++)
        draw_key(st, k);
    draw_results(st);
}

/* ------------------------------------------------------------------ searching */

/* A match: counted; the first one spells the query line, those on the result lines are drawn at once. */
static void found_one(search_t *st, const u8 *name, int span)
{
    int m = st->found++;

    if (!m) {
        spelled(st->pred, name, span);
        draw_query(st);
    }
    if (m >= st->top && m < st->top + SHOWN)
        draw_line(st, m - st->top, name);
}

/* After a stretch of the search: done when nothing further is marked; the count when it changed. */
static void scanned(search_t *st)
{
    if (next_row(st, st->pos) < 0) {
        st->pos = st->rows;
        if (!st->found)
            draw_results(st);                           /* "No matches" */
    }
    if (st->counted != st->found * 2 + searching(st))
        draw_count(st);
}

/* The marked rows from pos on are tested against the whole query, up to SCAN_ROWS of them, a few per browser call
   (the names are read into this frame). This and what it calls for every row and character share a bank. */
static void scan(search_t *st)
{
    u8 names[BATCH][NAMELEN] __attribute__((aligned(4)));
    int left = SCAN_ROWS, r, n, k, span;

    while (left > 0 && (r = next_row(st, st->pos)) >= 0) {
        for (n = 1; n < BATCH && r + n < st->rows && marked(st, r + n); n++)
            ;
        read_rows(names, r, n);
        for (k = 0; k < n; k++) {
            span = match(names[k], st->q, st->qlen);
            if (span < 0)
                st->bits[(r + k) >> 5] &= ~(1u << ((r + k) & 31));
            else
                found_one(st, names[k], span);
        }
        st->pos = r + n;
        left -= n;
    }
}

/* The query changed: search again from the first row. */
static void restart(search_t *st)
{
    if (st->focus != ON_KEYS) {                         /* (a held Return on the results) */
        st->focus = ON_KEYS;
        draw_key(st, st->key);
    }
    st->pos = 0;
    st->found = 0;
    st->sel = st->top = 0;
    if (!st->qlen)
        st->pos = st->rows;
    draw_query(st);
    draw_count(st);
    draw_results(st);
}

static void type(search_t *st, int digit)
{
    if (st->qlen >= QMAX)
        return;
    if (!st->qlen)
        mark_all(st);
    st->q[st->qlen++] = (u8)digit;                      /* the marked rows stay: they are all a longer query can match */
    restart(st);
}

static void erase(search_t *st, int all)
{
    if (!st->qlen)
        return;
    st->qlen = all ? 0 : st->qlen - 1;
    mark_all(st);                                       /* a shorter query may match rows the longer one did not */
    restart(st);
}

/* ------------------------------------------------------------------ keys */

static void set_sel(search_t *st, int s)
{
    int old = st->sel, top = st->top;

    st->sel = s;
    if (s < st->top)
        st->top = s;
    if (s >= st->top + SHOWN)
        st->top = s - SHOWN + 1;
    if (st->top != top) {
        draw_results(st);
    } else {
        draw_match(st, old);
        draw_match(st, s);
    }
    draw_count(st);
}

static void focus(search_t *st, int on)
{
    st->focus = on;
    draw_key(st, st->key);
    draw_query(st);
    draw_count(st);
    draw_results(st);
}

static void move(search_t *st, u32 key)
{
    int k = st->key, row = k / 3, col = k % 3, last = st->found - 1;

    if (st->focus == ON_LIST) {                         /* the results lie above the keypad */
        if (key == KEY_DOWN && st->sel >= last) {
            st->key = col;                              /* onto the keypad's top row, below the results */
            focus(st, ON_KEYS);
        } else if (key == KEY_UP || key == KEY_DOWN) {
            set_sel(st, key == KEY_DOWN ? st->sel + 1 : st->sel ? st->sel - 1 : 0);
        } else {
            set_sel(st, key == KEY_PREV ? (st->sel > SHOWN ? st->sel - SHOWN : 0) : st->sel + SHOWN < last ? st->sel + SHOWN : last);
        }
        return;
    }
    if (key == KEY_UP && !row) {
        if (st->found)
            focus(st, ON_LIST);
        return;
    }
    if (key == KEY_UP)
        k -= 3;
    else if (key == KEY_DOWN)
        k = row < 3 ? k + 3 : k;
    else
        k = row * 3 + (col + (key == KEY_PREV ? 2 : 1)) % 3;
    if (k != st->key) {
        row = st->key;
        st->key = k;
        draw_key(st, row);
        draw_key(st, k);
    }
}

/* A key the search does not use: as a menu has it (the volume, the key lock); 1 if the search ends. */
static int other(search_t *st)
{
    u16 ev = 0;
    u32 r;

    if (!key_mapping(st->msg.gui, &ev))
        return 0;
    r = message_box(ev);
    if (r == RESULT_REDRAW)
        draw_all(st);
    else if (r)
        st->result = r;
    return r && r != RESULT_REDRAW;
}

/* One key message: STAY, LEAVE, PASS, or the chosen row (from 1). */
static int on_key(search_t *st)
{
    u32 key = st->msg.gui[2], kind = st->msg.gui[4] | (u32)st->msg.gui[5] << 8, d;
    int press = (kind & (KT_DOWN | KT_LONG | KT_HOLD)) != 0, up = (kind & KT_SHORT_UP) != 0;

    if (st->msg.gui[0] != 0)
        return other(st) ? PASS : STAY;
    if (key == KEY_UP || key == KEY_DOWN || key == KEY_PREV || key == KEY_NEXT) {
        if (press)
            move(st, key);
    } else if (key == KEY_PLAY) {
        if (up && st->focus == ON_LIST)
            return match_row(st, st->sel) + 1;
        d = (u32)digit_of(st->key);
        if (up && st->key == K_DEL)
            erase(st, 0);
        else if (up && st->key == K_OK && st->found)
            focus(st, ON_LIST);
        else if (up && d <= 9)
            type(st, (int)d);
    } else if (key == KEY_RETURN) {
        if (up && st->focus == ON_LIST)
            focus(st, ON_KEYS);
        else if (up && !st->qlen)
            return LEAVE;
        else if (up || kind & KT_LONG)
            erase(st, !up);
    } else if (key == KEY_MENU) {
        if (up && (st->focus == ON_LIST || st->found))
            focus(st, st->focus == ON_LIST ? ON_KEYS : ON_LIST);
    } else if (other(st)) {
        return PASS;
    }
    return STAY;
}

/* The screen until a row is chosen (its number from 1), Return leaves it (LEAVE) or a system message asks to leave
   (PASS, its result in st->result); the search goes on whenever no message waits. */
static int run(search_t *st)
{
    int act;
    u32 r;

    draw_all(st);
    for (;;) {
        if (get_gui_msg(st->msg.gui)) {
            act = on_key(st);
            if (act != STAY)
                return act;
        } else if (get_app_msg(st->msg.app)) {
            r = app_dispatch(st->msg.app);
            if (r == RESULT_REDRAW) {
                draw_all(st);
            } else if (r) {
                st->result = r;
                return PASS;
            }
        } else if (searching(st)) {
            scan(st);                                   /* (its row names are off the stack before more is drawn) */
            scanned(st);
        } else {
            delay_tick();
        }
    }
}

/* ------------------------------------------------------------------ the chosen row */

/* The list stands on browser row `row` (from 1, below the menu rows on top), with that row a little below the top of
   its page if it was not on the page shown; then what Select does there is done. A row with lists below (an artist,
   album, genre, a playlist) goes through the control's own Select, which also keeps this level's place for Back; a
   song plays by the stock "Play" option of that row. */
static u32 open_row(u8 *path_info, int row)
{
    dirctl_t *dc = dir_control();
    int no = row + menu_rows(), page = dc->page, total = dc->total, top = dc->top;
    u32 r;

    if (row < 1 || no > total || page < 1)
        return RESULT_REDRAW;
    if (no < top || no >= top + page) {
        top = no - (page - 1) / 2;
        if (top > total - page + 1)
            top = total - page + 1;
        if (top < 1)
            top = 1;
    }
    dc->top = (u16)top;
    dc->bottom = (u16)(top + page - 1 < total ? top + page - 1 : total);
    dc->list_no = (u16)no;
    dc->active = dc->old = (u16)(no - top + 1);
    if (row <= list_level()->dir_total) {
        r = dir_select(path_info, dc);                  /* the control reads and draws the new level after the options */
        return r ? r : RESULT_REDRAW;
    }
    return path_info[0] == FSEL_M3U ? stock_m3u_result(path_info, RESULT_PLAYING_START, (u32)row)
                                    : stock_list_result(path_info, RESULT_PLAYING_START, (u32)row);
}

u32 search_list(u8 *path_info)
{
    search_t st;
    u32 dc[2];
    u8 *tag = timer_tag(), keep = *tag;
    const dir_brow_t *b = list_level();
    int row;

    set_bytes(&st, 0, sizeof st);
    st.rows = b->dir_total + b->file_total < MAXROWS ? b->dir_total + b->file_total : MAXROWS;
    st.pos = st.rows;
    st.key = 4;                                         /* 5 jkl, in the middle of the keypad */
    ui((uptr)dc, 0, 0, UI_DC_GET);
    *tag = TAG_SEARCH;
    row = run(&st);
    *tag = keep;
    ui(dc[0], 0, 0, UI_PEN);
    ui(dc[1], 0, 0, UI_BACKGD);
    if (row == PASS)
        return st.result;
    return row > 0 ? open_row(path_info, row) : RESULT_REDRAW;
}

#ifdef HOST
int search_matches(const u8 *name, const u8 *keys, int n, u16 *pred)
{
    int span = match(name, keys, n);

    if (span < 0)
        return 0;
    spelled(pred, name, span);
    return 1;
}
#endif
