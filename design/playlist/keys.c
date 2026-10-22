/* The Previous key of the playing screen (Graphite stage 20).
 *
 * A song that has played for 3 seconds or more starts again from its beginning; within its first 3 seconds the
 * key goes to the previous song, as it always did. So two quick presses go back one song.
 *
 * The playing screen's key code (MUSIC.AP 0x180a1374) calls the stock "previous" (resident 0x1102b5) only for a
 * plain press, after its own cases for A-B repeat and fast winding; design/build_stage20.py points that one call
 * (0x180a13b6) here. The restart works the way the stock "Resume" plays a bookmark (0x183813fc): the engine's
 * seek message with a break point, here time 0. A playing song is paused first and resumed after, so that the
 * engine ends in the state the Play key leaves it in; a paused song stays paused, at its beginning.
 */
#include "fw.h"

#define RESTART_MS 3000

void previous_key(void)
{
    u32 bp[3];
    int st = engine_status();

    if (*elapsed_ms() < RESTART_MS || (st != PLAY_PLAYING && st != PLAY_PAUSED)) {
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
