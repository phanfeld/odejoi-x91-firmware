/* Runs "Add to playlist" (playlist.c) against the simulated player of mock.c.
 *
 *   cc -DHOST -I.. -o test test.c mock.c ../playlist.c && ./test
 */
#include <stdio.h>
#include <string.h>
#include "../fw.h"
#include "mock.h"

static int failures;

#define CHECK(cond, ...) do { if (!(cond)) { failures++; printf("FAIL %s:%d: ", __FILE__, __LINE__); printf(__VA_ARGS__); printf("\n"); } } while (0)

static int song, focus, nothing, music;

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

static void disk(void)
{
    int artist, album;
    reset_disk();
    music = add_node(0, "Music", 1, NULL);
    add_node(0, "E-Book", 1, NULL);
    focus = add_node(0, "Focus.m3u", 0, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n");
    add_node(0, "readme.txt", 0, "hello");
    nothing = add_node(0, "NothingMuch.m3u", 0, "Music\\A\\B\\x.mp3");     /* no line end at the end */
    artist = add_node(music, "16 Bit Lolitas", 1, NULL);
    album = add_node(artist, "Stardust EP", 1, NULL);
    add_node(album, "02 - Love Left (original mix).mp3", 0, NULL);
    song = add_node(album, "01 - Stardust (original mix).mp3", 0, NULL);
    play(song);
    set_title("Stardust");
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

int main(void)
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
    CHECK(dir == dir2 && entry == entry2, "position not restored after Back");

    /* add to Focus */
    keys(2, EV_NEXT, EV_SELECT);
    r = add_playing_to_playlist(0);
    snprintf(want, sizeof want, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n%s", LINE);
    content_is(focus, want, __LINE__);
    CHECK(r == RESULT_TO_PLAYING, "adding gives %#x", r);
    CHECK(!strcmp(last_message, "text 12: \"Stardust\" added to Focus!"), "message: %s", last_message);
    CHECK(paused == 0 && resumed > 0, "playback not paused and resumed around the write (%d, %d)", paused, resumed);
    position(&dir2, &entry2);
    CHECK(dir == dir2 && entry == entry2, "position not restored after adding");

    /* again: nothing is added */
    keys(2, EV_NEXT, EV_SELECT);
    dialogs = 0;
    r = add_playing_to_playlist(0);
    content_is(focus, want, __LINE__);
    CHECK(r == RESULT_REDRAW && dialogs == 1 && last_dialog_text == S_ALREADY_ADDED, "second add: %#x, text %d", r, last_dialog_text);

    /* the same line in other letter case counts as there */
    strcpy(nodes[focus].data, "music\\16 BIT LOLITAS\\stardust ep\\01 - stardust (original mix).MP3");
    nodes[focus].size = (u32)strlen(nodes[focus].data);
    keys(2, EV_NEXT, EV_SELECT);
    r = add_playing_to_playlist(0);
    CHECK(last_dialog_text == S_ALREADY_ADDED && nodes[focus].size == strlen("music\\16 BIT LOLITAS\\stardust ep\\01 - stardust (original mix).MP3"),
          "case: text %d, size %u", last_dialog_text, nodes[focus].size);

    /* a playlist without a line end at its end gets one first */
    keys(3, EV_NEXT, EV_NEXT, EV_SELECT);
    r = add_playing_to_playlist(0);
    snprintf(want, sizeof want, "Music\\A\\B\\x.mp3\r\n%s", LINE);
    content_is(nothing, want, __LINE__);

    /* Previous from the top wraps to the last row */
    keys(2, EV_PREV, EV_BACK);
    add_playing_to_playlist(0);
    CHECK(last_active == 2 && last_total == 3, "wrap: active %d of %d", last_active, last_total);

    /* new playlists */
    keys(1, EV_SELECT);
    r = add_playing_to_playlist(0);
    n = find("New playlist 1.m3u");
    CHECK(n >= 0 && r == RESULT_TO_PLAYING, "no New playlist 1 (%#x)", r);
    if (n >= 0)
        content_is(n, LINE, __LINE__);
    CHECK(!strcmp(last_message, "text 12: \"Stardust\" added to New playlist 1!"), "message: %s", last_message);
    keys(1, EV_SELECT);
    add_playing_to_playlist(0);
    CHECK(find("New playlist 2.m3u") >= 0, "no New playlist 2");

    /* many playlists: the page follows the selection */
    {
        int i;
        char name[32];
        for (i = 0; i < 8; i++) {
            snprintf(name, sizeof name, "List %d.m3u", i);
            add_node(0, name, 0, "");
        }
        keys(9, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_BACK);
        add_playing_to_playlist(0);
        CHECK(last_total == 13 && last_active == 5 && !strcmp(shown[5], "List 3") && !strcmp(shown[0], "New playlist 1"),
              "paging: total %d active %d rows '%s'..'%s'", last_total, last_active, shown[0], shown[5]);
        keys(10, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_NEXT, EV_SELECT);
        add_playing_to_playlist(0);
        content_is(find("List 4.m3u"), LINE, __LINE__);
    }

    /* a name that is not one-byte text: nothing is written, the message says so */
    disk();
    nodes[song].wide_char = 1;
    keys(2, EV_NEXT, EV_SELECT);
    r = add_playing_to_playlist(0);
    content_is(focus, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\n", __LINE__);
    CHECK(r == RESULT_REDRAW && last_dialog_text == S_OPEN_FAILED, "wide name: %#x text %d", r, last_dialog_text);

    /* the deepest path the sync makes */
    disk();
    {
        int a = add_node(music, "Godspeed You Black Emperor", 1, NULL);   /* artists are cut at 18, this is longer */
        int b = add_node(a, "Lift Your Skinny Fists Like Antennas to Heaven xyz", 1, NULL);                   /* 50 */
        int s = add_node(b, "01 - Storm - Lift Yr. Skinny Fists, Like Antennas to Heaven!.mp3", 0, NULL);    /* 64 */
        play(s);
        keys(2, EV_NEXT, EV_SELECT);
        r = add_playing_to_playlist(0);
        snprintf(want, sizeof want, "Music\\Danger\\0917 2007\\01 - 4-30.mp3\r\nMusic\\%s\\%s\\%s\r\n",
                 nodes[a].name, nodes[b].name, nodes[s].name);
        content_is(focus, want, __LINE__);
    }

    printf("%s (%d failure%s)\n", failures ? "FAILED" : "all passed", failures, failures == 1 ? "" : "s");
    return failures != 0;
}
