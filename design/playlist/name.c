/* Naming a playlist with the keypad (Graphite stage 27): "New playlist" and "Rename" in the Playlists options.
 *
 * The screen is the search's (search.c): the name on the line at the top, the keypad at the bottom. The keys type as a
 * phone's did before T9: each key stands for its letters and then its digit (2 abc 2, ... 9 wxyz 9), 1 for a few signs
 * (- . & ' ( ) ! 1), 0 for the space and 0. Play on a key types its first character; Play again on the same key within
 * a second takes the next one in its place (a, b, c, 2, a ...). Another key, a move on the keypad or a second without
 * a press keeps the character. Held, Play types the key's digit at once.
 *
 * Under the name, the characters of the chosen key in a row, in the case the next letter takes, the one being typed
 * marked, and on the right the letter case: "Abc" (a capital at the start and after a space), "abc" or "ABC"; Menu
 * switches between them. The keys keep their small letters, as a phone's did. Del (or Return) takes out the last
 * character, held all of them; Return on an empty name leaves the screen, and so does a system message. OK takes the
 * name, without spaces at its ends (an empty one is not taken). A name has at most 26 characters, as many as a playlist's record in M3U.LIB holds; of a name
 * longer than the line, its end shows.
 *
 * The keys are read raw, as by the search: Up, Down, Previous and Next move on the keypad. Other keys (volume) work as
 * in a menu. While the screen shows, the list's timers are held by the search's timer tag, and the display's colours
 * are given back afterwards.
 */
#include "fw.h"
#include "util.h"
#include "search.h"
#include "name.h"

#define TAP_MS    1000                   /* a press of the same key within this changes the character being typed */
#define NAME_X    6                      /* the name, from x = 6 */
#define NAME_W    116
#define CARET     3                      /* room behind the name for the caret */
#define CELL_X    2                      /* the chosen key's characters: one per 12 pixels from x = 2 */
#define CELL_W    12
#define CASE_X    98                     /* the letter case, right-aligned up to x = 123 */
#define CASE_W    26
#define KEY1_MORE ('(' | ')' << 8 | '!' << 16)   /* the signs of 1 after KEY1_SIGNS */

enum { CASE_AUTO, CASE_LOWER, CASE_UPPER };
enum { N_STAY = 0, N_LEAVE = -1, N_PASS = -2, N_NONE = -3, N_AGAIN = -4, N_SHOW = -5, N_DONE = 1 };

typedef struct {
    u16 w[NAME_UNITS];                   /* FF FE, the name, 0 */
    int len;                             /* its characters; one being typed is the last */
    int key;                             /* the keypad's key */
    int tap, taps;                       /* the key of the character being typed (-1: none), its place in the key's row */
    int tap_upper;                       /* whether that character is a capital */
    u32 at;                              /* when that key was last pressed (ms) */
    int mode, upper;                     /* the letter case; whether the next letter is a capital */
    int title;                           /* NAME_NEW or NAME_RENAME */
    u32 result;                          /* the result of a system message that ends the screen */
} name_t;

typedef union {                          /* a key message, or another message for the program */
    u8 gui[8];
    u8 app[24];
} name_msg_t;

/* ------------------------------------------------------------------ the keys' characters */

/* The characters of digit d's key, in the order Play takes them: its letters (signs, the space), then its digit. How
   many: 2 8 4 4 4 4 4 5 4 5 for 0 to 9, less one, in 3 bits each (a table would be data). */
#define CYCLES 0x238db6f9u
static int cycle_len(int d) { return (int)(CYCLES >> (3 * d) & 7) + 1; }

static u32 cycle_char(int d, int i, int upper)
{
    if (i >= cycle_len(d) - 1)
        return (u32)('0' + d);
    if (!d)
        return ' ';
    if (d == 1)
        return (i < 4 ? KEY1_SIGNS : KEY1_MORE) >> (8 * (i & 3)) & 0xff;
    return (u32)((upper ? 'A' : 'a') + 3 * (d - 2) + (d > 7) + i);
}

/* Whether a letter at place pos of the name (from 1) is a capital. */
static int upper_at(const name_t *n, int pos)
{
    return n->mode == CASE_UPPER || (n->mode == CASE_AUTO && (pos == 1 || n->w[pos - 1] == ' '));
}

/* ------------------------------------------------------------------ drawing */

/* t: FF FE, w[from .. to), 0 */
static void part(u16 *t, const u16 *w, int from, int to)
{
    int i;

    t[0] = 0xfeff;
    for (i = 0; from + i < to; i++)
        t[1 + i] = w[from + i];
    t[1 + i] = 0;
}

/* the width in pixels of a text of NAME_UNITS units (UTF-16 with FF FE), as the display driver measures it */
static int width(const u16 *t)
{
    strdesc_t d;

    set_bytes(&d, 0, sizeof d);
    d.str = (uptr)t;
    d.lang = TEXT_UTF16;
    d.length = NAME_UNITS * 2;
    return (int)(ui((uptr)&d, 0xffff, 0, UI_STR_WIDTH) & 0xffff);
}

/* The name's line: the name (its end, if it is longer than the line) in the text colour, a character being typed in
   the accent behind it, else the caret; then the line under it, which the texts' strips reach. */
static void draw_name(const name_t *n)
{
    u16 t[NAME_UNITS];
    int pend = n->tap >= 0, s, x = NAME_X, cw;

    for (s = 0;; s++) {                                 /* the first character shown */
        part(t, n->w, 1 + s, 1 + n->len);
        if (s >= n->len || width(t) <= NAME_W - CARET)
            break;
    }
    fill(0, Y_QUERY, 128, LINE - 1, COL_BG);
    if (s < n->len - pend) {
        part(t, n->w, 1 + s, 1 + n->len - pend);
        text(t, sizeof t, NAME_X, Y_QUERY, NAME_W, ON(COL_TEXT, COL_BG), ALIGN_LEFT | LONG_CUT);
        x += width(t);
    }
    if (pend) {
        part(t, n->w, n->len, 1 + n->len);
        cw = width(t);
        if (cw < 1)
            cw = 1;
        fill(x, Y_QUERY, cw, LINE - 1, COL_ACCENT);
        text(t, sizeof t, x, Y_QUERY, cw, ON(COL_ON_ACCENT, COL_ACCENT), ALIGN_LEFT | LONG_CUT);
    } else {
        fill(x + 1, Y_QUERY + 3, 1, 10, COL_ACCENT);
    }
    fill(4, Y_QUERY + LINE - 1, 120, 1, COL_ACCENT);
}

/* The line under the name: the chosen key's characters, the one being typed in the accent; the letter case. */
static void draw_cycle(const name_t *n)
{
    u16 t[6];
    int d = digit_of(n->key), i, x, on, any = 0, last, up = n->tap == n->key ? n->tap_upper : n->upper;
    u32 pen;

    fill(0, Y_LIST, 128, LINE, COL_BG);
    for (i = 0; d >= 0 && i < cycle_len(d); i++) {
        on = n->tap == n->key && n->taps == i;
        last = i == cycle_len(d) - 1;
        x = CELL_X + i * CELL_W;
        pen = on ? COL_ON_ACCENT : last ? COL_TEXT2 : COL_TEXT;
        if (on)
            fill(x, Y_LIST, CELL_W, LINE - 1, COL_ACCENT);
        if (!d && !i) {                                 /* the space */
            space_bar(x + 2, Y_LIST + 12, CELL_W - 4, pen);
        } else {
            t[0] = 0xfeff;
            t[1] = (u16)cycle_char(d, i, up);          /* (as further presses give them) */
            t[2] = 0;
            text(t, sizeof t, x, Y_LIST, CELL_W, ON(pen, on ? COL_ACCENT : COL_BG), ALIGN_CENTRE | LONG_CUT);
        }
        any |= on;
    }
    t[0] = 0xfeff;
    put4(t, 1, (n->mode == CASE_LOWER ? 'a' : 'A') | (u32)(n->mode == CASE_UPPER ? 'B' | 'C' << 8 : 'b' | 'c' << 8) << 8);
    text(t, sizeof t, CASE_X, Y_LIST, CASE_W, ON(COL_TEXT2, COL_BG), ALIGN_RIGHT | LONG_CUT);
    if (any)
        fill(0, Y_LIST + LINE - 1, 128, 1, COL_BG);    /* the row below the mark, which its text painted */
}

static void name_keys(const name_t *n)
{
    int k;

    for (k = 0; k < KEYS; k++)
        keypad_key(k, k == n->key, KEYS_NAME);
}

static void name_draw(name_t *n)
{
    u16 w[14];                                          /* FF FE, "New playlist", 0 */

    headbar_all();                                      /* the status bar on, its middle empty (stage 24) */
    clear_bar();
    w[0] = 0xfeff;
    if (n->title == NAME_RENAME)
        put4(w, put4(w, 1, 'R' | 'e' << 8 | 'n' << 16 | 'a' << 24), 'm' | 'e' << 8);
    else
        put4(w, put4(w, put4(w, 1, 'N' | 'e' << 8 | 'w' << 16 | ' ' << 24), 'p' | 'l' << 8 | 'a' << 16 | 'y' << 24),
             'l' | 'i' << 8 | 's' << 16 | (u32)'t' << 24);
    text(w, sizeof w, TITLE_X, 0, TITLE_W, ON(COL_TEXT2, COL_BG), ALIGN_LEFT | LONG_CUT);   /* the bar's middle: black */
    fill(0, LINE, 128, 160 - LINE, COL_BG);
    draw_name(n);
    draw_cycle(n);
    name_keys(n);
}

/* After the name or the case changed: the name, the row of characters. */
static void name_show(name_t *n)
{
    n->upper = upper_at(n, n->len + 1);
    draw_name(n);
    draw_cycle(n);
}

/* ------------------------------------------------------------------ typing */

/* Play on the key of digit d: its first character at the end, or, pressed again soon, the next one in its place. */
static void tap(name_t *n, int d)
{
    u32 t = now_ms();

    if (n->tap == n->key && t - n->at < TAP_MS) {
        n->taps = (n->taps + 1) % cycle_len(d);
    } else {
        n->tap = -1;                                    /* the one typed before stays */
        if (n->len >= NAME_MAX)
            return;
        n->tap_upper = upper_at(n, n->len + 1);
        n->len++;
        n->tap = n->key;
        n->taps = 0;
    }
    n->w[n->len] = (u16)cycle_char(d, n->taps, n->tap_upper);
    n->w[n->len + 1] = 0;
    n->at = t;
}

/* Play held: the digit. */
static void put_digit(name_t *n, int d)
{
    n->tap = -1;
    if (n->len >= NAME_MAX)
        return;
    n->w[++n->len] = (u16)('0' + d);
    n->w[n->len + 1] = 0;
}

static void name_erase(name_t *n, int all)
{
    n->tap = -1;
    n->len = all || !n->len ? 0 : n->len - 1;
    n->w[n->len + 1] = 0;
}

/* Menu: the next letter case; a letter being typed takes it. */
static void recase(name_t *n)
{
    n->mode = (n->mode + 1) % 3;
    if (n->tap >= 0 && digit_of(n->tap) >= 2) {
        n->tap_upper = upper_at(n, n->len);
        n->w[n->len] = (u16)cycle_char(digit_of(n->tap), n->taps, n->tap_upper);
        n->at = now_ms();
    }
}

/* OK: the name without spaces at its ends; whether anything is left. */
static int name_trim(name_t *n)
{
    int a = 1, i;

    n->tap = -1;
    while (n->len && n->w[n->len] == ' ')
        n->len--;
    while (a <= n->len && n->w[a] == ' ')
        a++;
    for (i = 0; a + i <= n->len; i++)
        n->w[1 + i] = n->w[a + i];
    n->len = i;
    n->w[1 + i] = 0;
    return i;
}

/* ------------------------------------------------------------------ keys */

static void name_move(name_t *n, u32 key)
{
    int old = n->key, k = old, row = k / 3, col = k % 3, was = n->tap >= 0;

    if (key == KEY_UP)
        k = row ? k - 3 : k;
    else if (key == KEY_DOWN)
        k = row < 3 ? k + 3 : k;
    else
        k = row * 3 + (col + (key == KEY_PREV ? 2 : 1)) % 3;
    n->tap = -1;                                        /* a move keeps the character being typed */
    n->key = k;
    if (k != old) {
        keypad_key(old, 0, KEYS_NAME);
        keypad_key(k, 1, KEYS_NAME);
    }
    if (was)
        draw_name(n);
    if (was || k != old)
        draw_cycle(n);
}

/* A key the screen does not use: as a menu has it (the volume, the key lock). */
static int name_other(name_t *n, name_msg_t *msg)
{
    u16 ev = 0;
    u32 r;

    if (!key_mapping(msg->gui, &ev))
        return N_STAY;
    r = message_box(ev);
    if (r == RESULT_REDRAW)
        return N_AGAIN;
    n->result = r;
    return r ? N_PASS : N_STAY;
}

/* One key message: N_STAY, N_SHOW (the name changed), N_DONE, N_LEAVE, N_AGAIN or N_PASS. */
static int name_key(name_t *n, name_msg_t *msg)
{
    u32 key = msg->gui[2], kind = msg->gui[4] | (u32)msg->gui[5] << 8;
    int press = (kind & (KT_DOWN | KT_LONG | KT_HOLD)) != 0, up = (kind & KT_SHORT_UP) != 0, held = (kind & KT_LONG) != 0;

    if (msg->gui[0] != 0)
        return name_other(n, msg);
    if (key == KEY_UP || key == KEY_DOWN || key == KEY_PREV || key == KEY_NEXT) {
        if (press)
            name_move(n, key);
        return N_STAY;
    }
    if (key == KEY_PLAY) {
        if (!up && !held)
            return N_STAY;
        if (n->key == K_OK)
            return !up ? N_STAY : name_trim(n) ? N_DONE : N_SHOW;
        if (n->key == K_DEL)
            name_erase(n, held);
        else if (up)
            tap(n, digit_of(n->key));
        else
            put_digit(n, digit_of(n->key));
        return N_SHOW;
    }
    if (key == KEY_RETURN) {
        if (up && !n->len)
            return N_LEAVE;
        if (!up && !held)
            return N_STAY;
        name_erase(n, held);
        return N_SHOW;
    }
    if (key == KEY_MENU) {
        if (up)
            recase(n);
        return up ? N_SHOW : N_STAY;
    }
    return name_other(n, msg);
}

/* A key or another message for the program, if one waits: what it does; N_NONE when none came. */
static int name_poll(name_t *n)
{
    name_msg_t msg __attribute__((aligned(4)));
    u32 r;

    if (get_gui_msg(msg.gui))
        return name_key(n, &msg);
    if (!get_app_msg(msg.app))
        return N_NONE;
    r = app_dispatch(msg.app);
    if (r == RESULT_REDRAW)
        return N_AGAIN;
    n->result = r;
    return r ? N_PASS : N_STAY;
}

/* The screen until OK takes the name (N_DONE), Return leaves (N_LEAVE) or a system message asks to leave (N_PASS). */
static int name_run(name_t *n)
{
    int act;

    for (act = N_AGAIN;; act = name_poll(n)) {
        if (act == N_AGAIN) {                           /* the first time, and after a pop-up */
            name_draw(n);
        } else if (act == N_SHOW) {
            name_show(n);
        } else if (act == N_NONE) {
            if (n->tap >= 0 && now_ms() - n->at >= TAP_MS) {
                n->tap = -1;                            /* a second without a press keeps the character */
                name_show(n);
            } else {
                delay_tick();
            }
        } else if (act != N_STAY) {
            return act;
        }
    }
}

int name_entry(u16 *name, int title, u32 *result)
{
    name_t n;
    u32 dc[2];
    u8 *tag = timer_tag(), keep = *tag;
    int r, i;

    set_bytes(&n, 0, sizeof n);
    n.w[0] = 0xfeff;
    for (i = 0; i < NAME_MAX && name[0] == 0xfeff && name[1 + i]; i++)
        n.w[1 + i] = name[1 + i];
    n.len = i;
    n.tap = -1;
    n.key = 4;                                          /* 5 jkl, in the middle of the keypad */
    n.title = title;
    n.upper = upper_at(&n, n.len + 1);
    ui((uptr)dc, 0, 0, UI_DC_GET);
    *tag = TAG_SEARCH;
    r = name_run(&n);
    *tag = keep;
    ui(dc[0], 0, 0, UI_PEN);
    ui(dc[1], 0, 0, UI_BACKGD);
    *result = n.result;
    if (r != N_DONE)
        return r == N_PASS ? NAME_PASS : NAME_LEFT;
    for (i = 0; i <= n.len + 1; i++)
        name[i] = n.w[i];
    return NAME_OK;
}
