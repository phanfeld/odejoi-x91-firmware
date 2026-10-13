@ MUSIC.AP, shared status-bar code, bank at 0x18c21a00: the routine that switches the status bar on or off
@ (bank offsets 0x474 to 0x4e8, 116 bytes). r0 = mode (1 = on), r1 = program icon, r2 = background picture
@ (0xffff = the default one).
@
@ Stock: stores its settings and restarts the status bar's 500 ms timer; the bar itself is first drawn when
@ that timer fires, so battery, card and Bluetooth marks appear half a second after every full repaint.
@ New: the same, written compactly, and then the bar is drawn at once. The "draw everything" flag is left
@ as stock sets it, so the timer still redraws the bar half a second later; a caller that paints its
@ background after this call therefore ends up with the same picture as before.
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
timer_restart:  nop
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
        movs    r0, #0
        bl      draw_bar
        pop     {r4, pc}
off:    mov     r0, r4
        bl      timer_stop
        pop     {r4, pc}

        .org    BANK + 0x4e8
lit_mode:       .word 0
lit_icon:       .word 0
lit_parts:      .word 0
lit_flag:       .word 0
lit_back:       .word 0
lit_timer:      .word 0
