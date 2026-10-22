@ Shared status-bar code, the routine that switches the status bar on or off (stage 24; replaces the stage 14
@ routine, music_headbar.S, in every program that has it). r0 = mode (1 = on), r1 = program icon, r2 = background
@ picture (0xffff = the default one).
@
@ Stage 14 draws the bar at once when it is switched on. A list draws its full-screen background after that call
@ (list styles of COMMON.STY: picture 185 at 0, 0), so in every menu and list the bar was gone until the bar's
@ 500 ms timer drew it again (owner, 2026-10-22: about a second in every sub-menu). New: when the timer has been
@ restarted, its next firing time is moved back by one period, to now. The program looks at its timers again
@ when it waits for keys, which is after the caller has drawn its screen; the bar is drawn then, and from there
@ on every 500 ms as before. Timer entries (the SDK's app timers, MUSIC.AP 0x18a21b80): 16 bytes each, period
@ (ms) at +2, next firing time at +8; the table's address is kept at the word lit_table points to.
@
@ The source is laid out from the timer bank (0x18a21a00) so that both banks' routines can be named.

        .syntax unified
        .cpu cortex-m3
        .thumb
        .equ    BANK, 0x18c21a00 - 0x18a21a00

        .org    0x0cc
        .thumb_func
timer_stop:     nop
        .org    0x180
        .thumb_func
timer_restart:  nop                     @ returns 0 when there is no such timer
        .org    BANK + 0x020
        .thumb_func
draw_bar:       nop                     @ r0 = 0: draw every part

        .org    BANK + 0x474
start:  push    {r4, lr}
        ldr     r3, lit_mode
        strb    r0, [r3]
        ldr     r3, lit_icon
        strb    r1, [r3]
        ldr     r4, lit_timer
        ldrsb.w r4, [r4]
        cmp     r0, #1
        bne     off
        ldr     r1, lit_parts           @ which layout record draws which part; 0xffff = part not shown
        movw    r3, #0xffff
        strh    r3, [r1, #0]
        strh    r3, [r1, #2]            @ program icon: not shown
        strh    r3, [r1, #8]
        strh    r0, [r1, #4]
        movw    r0, #0x1001             @ battery
        strh    r0, [r1, #6]
        adds    r0, #1                  @ card
        strh    r0, [r1, #10]
        adds    r0, #1                  @ Bluetooth
        strh    r0, [r1, #12]
        ldr     r1, lit_flag
        movs    r0, #0
        strb    r0, [r1]
        cmp     r2, r3
        bne     1f
        movw    r2, #0x80f9
1:      ldr     r1, lit_back
        strh    r2, [r1]
        mov     r0, r4
        bl      timer_restart
        cbz     r0, 2f
        ldr     r1, lit_table
        ldr     r1, [r1]
        add.w   r1, r1, r4, lsl #4      @ this timer's entry
        ldrh    r2, [r1, #2]
        ldr     r0, [r1, #8]
        subs    r0, r0, r2
        str     r0, [r1, #8]            @ next firing: now
2:      movs    r0, #0
        bl      draw_bar
        pop     {r4, pc}
off:    mov     r0, r4
        bl      timer_stop
        pop     {r4, pc}

        .org    BANK + 0x4e4
lit_table:      .word 0                 @ the program's timer table pointer (filled in per program)
lit_mode:       .word 0                 @ the stock literal pool from here on (kept as it is in each program)
lit_icon:       .word 0
lit_parts:      .word 0
lit_flag:       .word 0
lit_back:       .word 0
lit_timer:      .word 0
