/* What the playlist code uses of the stock MUSIC.AP (X91 firmware 1.101.37 as in the Graphite stage 17 image).
 *
 * Every address was read from the program; how each was found is in reports/X91 write procedure.md, sections
 * "On-device playlist editing: groundwork", "A list drawn by new code", "Stage 20 prepared" and "Stage 21
 * prepared". With -DHOST the
 * same names are declared as plain functions, which host/mock.c implements on a simulated disk, so the logic can
 * be tested on the computer.
 */
#ifndef PLAYLIST_FW_H
#define PLAYLIST_FW_H

typedef unsigned char u8;
typedef signed char s8;
typedef unsigned short u16;
typedef unsigned int u32;
typedef int s32;
#ifdef HOST
#include <stdint.h>
typedef uintptr_t uptr;
#else
typedef u32 uptr;
#endif

/* ------------------------------------------------------------------ file system (svc 17, vfs_op_entry) */

enum {                                   /* command numbers, as in the SDK's vfs_interface.h and seen in PLAYLIST.AP */
    VFS_CD = 0, VFS_DIR = 1, VFS_GET_NAME = 2, VFS_OFFSET = 3, VFS_OPEN = 5, VFS_CREATE = 6, VFS_CLOSE = 7,
    VFS_REMOVE = 8, VFS_SIZE = 9, VFS_SEEK = 11, VFS_READ = 13, VFS_WRITE = 14,
};
#define CD_ROOT       ':'
#define CD_BACK       '|'                /* to the parent; the position stays on the folder just left */
#define DIR_NEXT      0x80
#define DIR_HEAD      0x82
#define EXT_ALL_FILES 0x00000002u        /* EXT_NAME_ALL_FILE */
#define OPEN_MODIFY   2
#define SEEK_FROM_SET 0
#define FS_FILE       1

typedef struct {                         /* where a file is, as VFS_OFFSET reports and takes it */
    u8 layer[76];                        /* pdir_layer_t: (cluster, entry) of each folder level, then the depth (73 bytes) */
    u32 cluster, entry;                  /* the file's directory entry */
} place_t;
#define LAYER_SIZE 73

/* The playing song's location (file_location_t, plist_location_t): the extension at +4, the directory entry's
 * cluster and offset at +8 and +12, the folder chain at +16. */
#define LOC_EXT     4
#define LOC_CLUSTER 8
#define LOC_ENTRY   12
#define LOC_LAYER   16

/* ------------------------------------------------------------------ display driver (svc 6, ui_op_entry) */

#define UI_LISTBOX    8
#define LIST_DRAW_LIST 2                 /* rows only */
#define LIST_DRAW_ALL  3                 /* background, title and rows */
#define STYLE_PICKER  0x6004             /* the list style of the stock "Add to playlist" sub-menu */
#define STYLE_DIR     0x6000             /* the file lists' style (DIRLIST): since stage 24 nothing in the status bar */
#define STYLE_COUNTED 0x6003             /* stage 24: the same look with the counter (stock MENULIST_HEAD, unused) */
#define STYLE_NAMED   0x6005             /* stage 24: the same look with the title (stock MENULIST_TITLE2, unused) */
#define ICON_PLAYLIST 6                  /* row icons of that sub-menu */
#define ICON_ADD      15                 /* the icon of "Add to playlist" in the options */
#define ICON_REMOVE   16                 /* the icon of "Remove from Playlist" */
#define TEXT_ID       0x7e               /* string descriptor types */
#define TEXT_UTF16    0x7d

typedef struct {                         /* string_desc_t, 12 bytes */
    uptr str;                            /* text, or a string id in the low 16 bits */
    s8 lang;
    u8 reserve;
    u16 length;                          /* buffer size */
    u16 argv;                            /* in a list row: icon (low byte), mark (high byte) */
    u16 result;
} strdesc_t;

typedef struct {                         /* listbox_private_t, 100 bytes */
    strdesc_t title;
    strdesc_t items[6];
    u16 head_id, head_act_id;
    u16 valid;                           /* rows filled */
    u16 active, old;                     /* rows on the page, from 0 */
    u16 total, pos;                      /* the whole list, from 0 */
    u16 pad;
} listbox_t;

typedef struct { u16 id; u8 type; u8 reserve; } style_t;        /* type 1: COMMON.STY */

typedef struct {                         /* dialog_com_data_t as the stock add routine fills it */
    u8 type;                             /* 2: information */
    u8 buttons;
    u16 icon;
    uptr text;                           /* strdesc_t * */
    u8 active;
    u8 reserve[3];
} dialog_t;

/* ------------------------------------------------------------------ keys and results */

#define EV_NEXT     0x2701               /* from the menu key table at 0x18aa1ac0 */
#define EV_PREV     0x2702
#define EV_STOP     0x2703
#define EV_SELECT   0x2704
#define EV_BACK     0x2705
#define EV_OPTION   0x2706
#define RESULT_REDRAW 0x8014
#define RESULT_DELETE_FILE 0x8019        /* to a list: the entry is gone, take it out and redraw (SDK ui_directory2.c) */
#define RESULT_DELETE_DIRLIST 0x801a     /* the same for an entry that is a list itself */
#define RESULT_DIALOG_YES 0x8306
#define RESULT_TO_PLAYING 0x861b         /* what the stock "Delete" returns when it is done */
#define RESULT_PLAYING_START 0x8601
#define RESULT_ADD_FAVOR1 0x8605         /* what option rows return (MUSIC.AP 0x181613df, 0x18161413, 0x1816140b) */
#define RESULT_DEL_FAVOR  0x8608
#define RESULT_CLR_FAVOR  0x8609

/* ------------------------------------------------------------------ texts of MUSIC.STY and COMMON.STY */

#define S_ADD_TO_PLAYLIST 5              /* "Add to playlist" */
#define S_ALREADY_ADDED   11             /* "Track already added" */
#define S_ADDED           12             /* "\"[%s]\" added to [%s]!" */
#define S_REMOVED         14             /* "Removed \"[%s]\" from [%s]!" */
#define S_NOT_IN_PLAYLIST 27             /* "This song can't be found in the playlist" */
#define S_REMOVE_FROM     34             /* "Remove from Playlist" */
#define S_REMOVE_ASK      35             /* "Remove [%s] from [%s]?" (in English rewritten in stage 21) */
#define S_MOVE            29             /* "Move song" (English; stock "Clear playlist") */
#define S_DELETE_ASK      (0x8000 | 15)  /* "\"[%s]\" delete?" (COMMON.STY) */
#define S_DELETED         (0x8000 | 19)  /* "\"[%s]\" deleted!" */
#define S_WAIT            (0x8000 | 47)  /* "Please wait..." */
#define S_OPEN_FAILED     (0x8000 | 26)  /* "File failed to open" (COMMON.STY) */
#define S_NO_PLAYLISTS    (0x8000 | 36)  /* "No playlists found" (COMMON.STY) */

/* ------------------------------------------------------------------ the list browser (enhanced library) */

/* What the music program's lists (Playlists, All songs, Artists ...) are browsed with: the SDK's fsel_browser_*
 * functions, in MUSIC.AP bank 0x1c0a2000 and 0x1c8b1000; the list option callback hands them a path info whose
 * location (+4) they fill. */
typedef struct {                         /* dir_brow_t */
    u16 dir_total;                       /* lists below this level (albums of an artist, playlists) */
    u16 file_total;                      /* songs at this level */
    u8 name_len, layer_no, reserve[2];
    uptr name_buf;
} dir_brow_t;
typedef struct { u8 option, num; u16 top; } brow_decode_t;      /* top: the row, from 1 */
typedef struct { u8 ext[4]; u8 name_len, reserve[3]; uptr name_buf; } file_brow_t;
enum { BROW_CUR = 0, BROW_SON = 1, BROW_PARENT = 2 };
enum { FSEL_PLAYLIST = 3, FSEL_M3U = 8 };                    /* file sources: the song lists, the .m3u lists */
enum { SCAN_SELF = 0, SCAN_FILE = 1, SCAN_ERROR = 4 };
#define SCAN_DXCH 1
#define ROW_NAME 52                      /* what the stock code takes of a row's name */

/* ------------------------------------------------------------------ the playback engine */

/* MENGINE.AP numbers its messages as the SDK does up to "get file path" (0x302); from "play" on they are the
 * SDK's plus 2 (dispatcher 0x1a051600): 0x313 play, 0x314 stop, 0x315 pause, 0x316 resume, 0x317 seek (the file
 * again from a break point given with the message), 0x31a next, 0x31b previous; 0x32b answers the play mode,
 * 0x32e the status. Pause keeps the break point; resume plays on from it. */
enum { PLAY_STOPPED = 0, PLAY_PAUSED = 1, PLAY_PLAYING = 2, PLAY_AB = 3, PLAY_FAST = 4 };

#ifdef HOST

uptr vfs(uptr a, uptr b, uptr c, int cmd);
uptr ui(uptr a, uptr b, uptr c, int cmd);
void delay_tick(void);
int get_gui_msg(void *msg);
int get_app_msg(void *msg);
u32 app_dispatch(void *msg);
int key_mapping(void *msg, u16 *event);
u32 message_box(u32 event);
void string_format(strdesc_t *dest, strdesc_t *src);
u32 dialog(u32 style, dialog_t *d);
u32 dialog_text(u32 style, u32 type, u32 text_id);
void refresh_path(void);
void headbar_all(void);
void list_prepare(style_t *st);
int back_flag(void);
s8 language(void);
u8 *song_location(void);                 /* the playing song's location */
u8 *song_title(void);                    /* the playing song's title from its tag */
u8 *temp_buffer(void);                   /* 128 bytes for the dialog text */
int engine_status(void);                 /* PLAY_STOPPED ... PLAY_FAST */
void engine_pause(void);
void engine_resume(void);
void engine_seek(u32 *break_point);      /* 12 bytes: time in ms, file offset, extra */
void previous_song(void);                /* what the Previous key does in the stock firmware */
volatile u32 *elapsed_ms(void);          /* the playing screen's copy of the playing time */
u32 engine_time(void);                   /* the engine's own playing time (ms) */
int music_playing(void);                 /* the music engine runs in the background (playing or paused) */
const dir_brow_t *list_level(void);   /* the shared list control's browser state */
void engine_stop(void);
int playing_source(void);                /* where the playing song was chosen: FSEL_M3U for a playlist */
int browser_enter_dir(int type, int list_no, dir_brow_t *b);
int browser_get_items(brow_decode_t *d, file_brow_t *f);
int browser_select(int list_no);
int browser_get_location(u8 *loc, int type);
int browser_scan_init(dir_brow_t *b);
int browser_scan(u8 *path_info, dir_brow_t *b, int type);
u8 *browse_path(void);                   /* g_browser_filepath, which a scan fills */
int m3u_list(void);                      /* the playlist the browser is in (record number), 0xffff at the top */
u32 stock_list_result(u8 *path_info, u32 check, u32 active);
u32 stock_m3u_result(u8 *path_info, u32 check, u32 active);

#else

#define FAR(addr, type) ((type)(addr))

/* the firmware reads these structures: their sizes must be the stock ones */
_Static_assert(sizeof(strdesc_t) == 12, "string descriptor");
_Static_assert(sizeof(listbox_t) == 100, "list box data");
_Static_assert(sizeof(dialog_t) == 12, "dialog data");
_Static_assert(sizeof(style_t) == 4, "style");
_Static_assert(sizeof(place_t) == 84, "file place");
_Static_assert(sizeof(dir_brow_t) == 12, "browser state");
_Static_assert(sizeof(brow_decode_t) == 4, "browser rows");
_Static_assert(sizeof(file_brow_t) == 12, "browser row");

static inline __attribute__((always_inline)) uptr vfs(uptr a, uptr b, uptr c, int cmd)
{
    return FAR(0x1102e7, uptr (*)(s32, uptr, uptr, uptr, int))(*(volatile s32 *)0x200020, a, b, c, cmd);
}
/* the display driver's entry (svc 6) is resident; other programs have it elsewhere (liststyle.c is compiled with theirs) */
#ifndef UI_ENTRY
#define UI_ENTRY 0x1102e9
#endif
static inline __attribute__((always_inline)) uptr ui(uptr a, uptr b, uptr c, int cmd) { return FAR(UI_ENTRY, uptr (*)(uptr, uptr, uptr, int))(a, b, c, cmd); }
static inline __attribute__((always_inline)) void delay_tick(void) { FAR(0x1102e1, uptr (*)(uptr, uptr, uptr, int))(1, 0, 0, 49); }
static inline __attribute__((always_inline)) int get_gui_msg(void *msg) { return FAR(0x110435, int (*)(void *))(msg); }
static inline __attribute__((always_inline)) int get_app_msg(void *msg) { return FAR(0x11030d, int (*)(void *))(msg); }
static inline __attribute__((always_inline)) u32 app_dispatch(void *msg) { return FAR(*(volatile u32 *)0x200140, u32 (*)(void *))(msg); }
static inline __attribute__((always_inline)) int key_mapping(void *msg, u16 *event)
{
    return FAR(0x18aa1a01, int (*)(void *, u16 *, uptr))(msg, event, 0x18aa1ac0);
}
static inline __attribute__((always_inline)) u32 message_box(u32 event) { return FAR(0x18de1a01, u32 (*)(u32))(event); }
static inline __attribute__((always_inline)) void string_format(strdesc_t *dest, strdesc_t *src) { FAR(0x18b01a01, void (*)(strdesc_t *, strdesc_t *))(dest, src); }
static inline __attribute__((always_inline)) u32 dialog(u32 style, dialog_t *d) { return FAR(0x18d61d89, u32 (*)(u32, dialog_t *))(style, d); }
static inline __attribute__((always_inline)) u32 dialog_text(u32 style, u32 type, u32 text_id) { return FAR(0x18d61d4d, u32 (*)(u32, u32, u32))(style, type, text_id); }
static inline __attribute__((always_inline)) void refresh_path(void) { FAR(0x11025d, void (*)(uptr))(0x200324); }
/* what the menu does before it draws its list (shared code at 0x18661316): status bar on a full redraw, display
   command 35 with the list style, background colour by the flag at [0x202f88]+3 */
static inline __attribute__((always_inline)) void headbar_all(void) { FAR(0x18c21e75, void (*)(u32, u32, u32))(1, *(volatile u8 *)0x200162, 0xffff); }
static inline __attribute__((always_inline)) void list_prepare(style_t *st) { ui((uptr)st, 0x2001a8, 0, 35); }
static inline __attribute__((always_inline)) int back_flag(void) { return (*(u8 *volatile *)0x202f88)[3]; }
static inline __attribute__((always_inline)) s8 language(void) { return *(volatile s8 *)0x20047c; }
static inline __attribute__((always_inline)) u8 *song_location(void) { return (u8 *)0x200328; }
static inline __attribute__((always_inline)) u8 *song_title(void) { return (u8 *)0x2001f4; }
static inline __attribute__((always_inline)) u8 *temp_buffer(void) { return *(u8 *volatile *)0x200054; }
/* The engine, through the music program's message calls (MUSIC.AP 0x11034d: data, reply, message). The status
   (0x110281, message 0x32e) is the engine's play_status byte, as the Play key reads it (0x180a1328). */
static inline __attribute__((always_inline)) int engine_status(void)
{
    u32 st[2] = {0, 0};
    FAR(0x110281, void (*)(void *))(st);
    return (int)(st[0] & 0xf);
}
static inline __attribute__((always_inline)) void engine_pause(void) { FAR(0x11034d, u32 (*)(u32, u32, u32))(0, 0, 0x315); }
static inline __attribute__((always_inline)) void engine_resume(void) { FAR(0x11034d, u32 (*)(u32, u32, u32))(0, 0, 0x316); }
static inline __attribute__((always_inline)) void engine_seek(u32 *bp) { FAR(0x11034d, u32 (*)(u32, u32, u32))((uptr)bp, 0, 0x317); }
static inline __attribute__((always_inline)) void previous_song(void) { FAR(0x1102b5, u32 (*)(void))(); }
static inline __attribute__((always_inline)) volatile u32 *elapsed_ms(void) { return (volatile u32 *)0x200030; }
static inline __attribute__((always_inline)) void engine_stop(void) { FAR(0x11034d, u32 (*)(u32, u32, u32))(0, 0, 0x314); }
/* The engine's playing time, from its own RAM: MENGINE.AP keeps it at 0x200914 (its main loop copies it from the
   decoder, 0x1a0d1600; its RAM starts at 0x200800, the music program's ends below that). Message 0x32f would
   copy it too, but also clears the "song changed" flags the playing screen reads, so the time is read directly.
   The playing screen's own copy (elapsed_ms) is not updated while the screen is off. */
static inline __attribute__((always_inline)) u32 engine_time(void) { return *(volatile u32 *)0x200914; }
/* The two bytes of the shared state at 0x202fbc that the stock screen-off "previous" and "next" check (0x18da1cec):
   the background engine is the music engine, and it runs (a song is playing or paused). */
static inline __attribute__((always_inline)) int music_playing(void)
{
    return ((volatile u8 *)0x202fbc)[1] == 1 && ((volatile u8 *)0x202fbc)[0] == 1;
}
static inline __attribute__((always_inline)) int playing_source(void) { return *(volatile u8 *)0x200324; }
/* The shared list control's browser state (g_dir_browser): MUSIC.AP 0x2006fc, which the control reads at 0x18661280
   (layer, lists, songs) and refreshes through browser_enter_dir at 0x18661490. The other programs with the control
   have it elsewhere (the literal at 0x18661400 of their copy); liststyle.c is compiled with theirs. Not volatile:
   list_box reads each field once, which keeps it inside the room at the end of the control's bank. */
#ifndef LIST_LEVEL_AT
#define LIST_LEVEL_AT 0x2006fc
#endif
static inline __attribute__((always_inline)) const dir_brow_t *list_level(void) { return (const dir_brow_t *)LIST_LEVEL_AT; }

/* the browser (veneers in MUSIC.AP 0x18161422, 0x1816142c, 0x18161436, 0x1830150a, 0x182e11d0, 0x182e11da) */
static inline __attribute__((always_inline)) int browser_enter_dir(int type, int list_no, dir_brow_t *b)
{
    return FAR(0x1c0a2001, int (*)(int, int, dir_brow_t *))(type, list_no, b);
}
static inline __attribute__((always_inline)) int browser_get_items(brow_decode_t *d, file_brow_t *f)
{
    return FAR(0x1c0a2023, int (*)(brow_decode_t *, file_brow_t *))(d, f);
}
static inline __attribute__((always_inline)) int browser_select(int list_no) { return FAR(0x1c0a2077, int (*)(int))(list_no); }
static inline __attribute__((always_inline)) int browser_get_location(u8 *loc, int type)
{
    return FAR(0x1c0a20cb, int (*)(u8 *, int))(loc, type);
}
static inline __attribute__((always_inline)) int browser_scan_init(dir_brow_t *b) { return FAR(0x1c8b1293, int (*)(dir_brow_t *))(b); }
static inline __attribute__((always_inline)) int browser_scan(u8 *path_info, dir_brow_t *b, int type)
{
    return FAR(0x1c8b117f, int (*)(u8 *, dir_brow_t *, int))(path_info, b, type);
}
static inline __attribute__((always_inline)) u8 *browse_path(void) { return (u8 *)0x2003c0; }
static inline __attribute__((always_inline)) int m3u_list(void) { return *(volatile u16 *)0x200116; }
/* the stock result handlers of the list options (playlist_option_result_proc, m3ulist_option_result_proc) */
static inline __attribute__((always_inline)) u32 stock_list_result(u8 *path_info, u32 check, u32 active)
{
    return FAR(0x181612ef, u32 (*)(u8 *, u32, u32))(path_info, check, active);
}
static inline __attribute__((always_inline)) u32 stock_m3u_result(u8 *path_info, u32 check, u32 active)
{
    return FAR(0x18161291, u32 (*)(u8 *, u32, u32))(path_info, check, active);
}

#endif

/* Stage 24: the background of the list styles drawn with the status bar on (0x6000, 0x6002 to 0x6005) starts at row
   16, so a full redraw of a list no longer wipes the bar's marks; the code that draws them first clears the bar's
   middle, x 17 to 97 (between the card mark and the Bluetooth mark), and the marks, bordered in black out to the
   bar's edges, paint the rest of rows 0 to 15: liststyle.c and the picker (playlist.c) here, patches/menu_box.S
   (same picture and place) for every other list. */
#define UI_PICTURE   31                  /* display command: a picture at x, y */
#define BAR_CLEAR    (0x8000 | 127)      /* COMMON.STY picture 127: 81 x 16, black (a view into picture 185) */
#define BAR_CLEAR_X  17
static inline __attribute__((always_inline)) void clear_bar(void) { ui(BAR_CLEAR, BAR_CLEAR_X, 0, UI_PICTURE); }

#endif
