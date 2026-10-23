/* Small helpers shared by the playlist code. The code runs without a C library, so these are written out. */
#ifndef PLAYLIST_UTIL_H
#define PLAYLIST_UTIL_H
#include "fw.h"

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

/* little-endian values at any address */
static inline __attribute__((always_inline)) u32 get32(const u8 *p)
{
    return p[0] | (u32)p[1] << 8 | (u32)p[2] << 16 | (u32)p[3] << 24;
}

static inline __attribute__((always_inline)) void put16(u8 *p, u32 v)
{
    p[0] = (u8)v;
    p[1] = (u8)(v >> 8);
}

static inline __attribute__((always_inline)) void put32(u8 *p, u32 v)
{
    put16(p, v);
    put16(p + 2, v >> 16);
}

#endif
