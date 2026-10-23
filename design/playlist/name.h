/* Naming a playlist with the keypad (name.c, stage 27). */
#ifndef PLAYLIST_NAME_H
#define PLAYLIST_NAME_H
#include "fw.h"

#define NAME_MAX   26                    /* characters of a name: as many as a playlist's record in M3U.LIB holds */
#define NAME_UNITS (NAME_MAX + 2)        /* FF FE, the name, 0 */
enum { NAME_NEW, NAME_RENAME };          /* the screen's title: "New playlist", "Rename" */
enum { NAME_PASS = -1, NAME_LEFT = 0, NAME_OK = 1 };

/* The name screen, starting with name (UTF-16 with FF FE, NAME_UNITS units; empty for a new playlist): NAME_OK with
   the name typed in name (never empty, no spaces at its ends), NAME_LEFT after Return on an empty name, NAME_PASS
   when a system message ends it (its result in *result). */
int name_entry(u16 *name, int title, u32 *result);

#endif
