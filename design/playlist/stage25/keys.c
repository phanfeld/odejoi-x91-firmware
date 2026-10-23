/* The Previous key (Graphite stages 20 and 23).
 *
 * A song that has played for 3 seconds or more starts again from its beginning; within its first 3 seconds the
 * key goes to the previous song, as it always did. So two quick presses go back one song.
 *
 * With the screen on, the playing screen's key code (MUSIC.AP 0x180a1374) calls the stock "previous" (resident
 * 0x1102b5) only for a plain press, after its own cases for A-B repeat and fast winding; design/build_stage20.py
 * points that one call (0x180a13b6) to previous_key. With the screen off, the program's shared key filter
 * (0x18b41a00) handles Previous, Next, Play and the volume itself; its "previous" (0x18da1cec with 0, which sends
 * 0x31b to the engine while the music engine runs) is called at 0x18b41a6e, which stage 23 points to
 * standby_previous. The playing screen does not update its time while the screen is off, so that one asks the
 * engine's RAM for it.
 *
 * The restart works the way the stock "Resume" plays a bookmark (0x183813fc): the engine's seek message with a
 * break point, here time 0. A playing song is paused first and resumed after, so that the engine ends in the
 * state the Play key leaves it in; a paused song stays paused, at its beginning.
 */
#include "fw.h"

#define RESTART_MS 3000

/* written into both callers, so that neither calls into another bank */
static inline __attribute__((always_inline)) void previous_after(u32 ms)
{
    u32 bp[3];
    int st = engine_status();

    if (ms < RESTART_MS || (st != PLAY_PLAYING && st != PLAY_PAUSED)) {
        previous_song();
        return;
    }
    if (st == PLAY_PLAYING)
        engine_pause();
    bp[0] = bp[1] = bp[2] = 0;
    engine_seek(bp);
    if (st == PLAY_PLAYING)
        engine_resume();
    else
        engine_pause();
    *elapsed_ms() = 0;                                  /* a second press right away goes back one song */
}

void previous_key(void)
{
    previous_after(*elapsed_ms());
}

/* Previous with the screen off: as the stock one, only while the music engine runs (a song playing or paused). */
void standby_previous(void)
{
    if (music_playing())
        previous_after(engine_time());
}
