@ MUSIC.AP, code bank at 0x18061000: the whole routine that draws the playing time and the progress bar
@ (bank offsets 0x390 to 0x476, 230 bytes). The knob moves column by column, without flicker.
@
@ Called with r0 = 1 on a full repaint of the screen (else 0), r1 = control block, r2 = 0 for the time, 1 for the bar.
@ Time: the stock logic, written compactly. The room gained goes to the bar.
@ Bar: an inset bar with the played part in the accent colour.
@   position = BAR_X + BAR_LEN * elapsed / total
@   full repaint, seek or new track: track picture, played part in 6-pixel pieces, knob
@   knob one pixel further right:    one accent column where the knob's left edge was, knob at its new place
@   knob unchanged:                  nothing
@ The last position is kept in a byte only the unused "demo" screensaver refers to (0x200191).

        .syntax unified
        .cpu cortex-m3
        .thumb
        .equ    TRACK, 67               @ pictures of MUSIC.STY
        .equ    KNOB, 68
        .equ    COLUMN, 65              @ one accent column of the bar
        .equ    SEGMENT, 70             @ six accent columns
        .equ    BAR_Y, 132
        .equ    BAR_X, 8
        .equ    BAR_LEN, 106
        .equ    STATE_OFF, 0x200191 - 0x20002c  @ from the "total time" variable to the state byte

        .org    0x364
        .thumb_func
hms:    nop                             @ seconds -> hours, minutes, seconds

        .org    0x390
start:  push    {r4, r5, r6, r7, r8, r9, lr}
        sub     sp, #44
        mov     r8, r0
        mov     r5, r1
        mov     r9, r2
        ldr     r4, lit_total
        ldr     r0, [r4]                @ total time in ms, 0 if not asked for yet
        cbnz    r0, 1f
        add     r0, sp, #20
        bl      get_total
        ldr     r0, [sp, #20]
        str     r0, [r4]
1:      ldr     r1, lit_elapsed
        ldr     r1, [r1]
        mov.w   r2, #1000
        udiv    r6, r1, r2              @ r6 = elapsed seconds
        udiv    r7, r0, r2              @ r7 = total seconds
        cmp.w   r9, #0
        bne     progress

        add     r1, sp, #4              @ ---- the time
        mov     r0, r6
        bl      hms
        add     r1, sp, #12
        mov     r0, r7
        bl      hms
        movw    r0, #0x4001
        strh    r0, [r5]
        movs    r0, #6
        ldrh.w  r1, [sp, #4]            @ elapsed has hours?
        cbz     r1, 2f
        movs    r0, #4
2:      strb.w  r0, [sp, #9]
        movs    r1, #6
        ldrh.w  r0, [sp, #12]           @ total has hours?
        cbz     r0, 3f
        movs    r1, #4
        ldr     r2, lit_flags
        ldr     r0, [r2]
        bic.w   r0, r0, #0xb00
        str     r0, [r2]
3:      strb.w  r1, [sp, #17]
        movs    r2, #1
        cmp.w   r8, #1
        bne     4f
        movs    r2, #2
4:      movs    r3, #4
        add     r1, sp, #4
        mov     r0, r5
        bl      ui_call
        b       done

draw:   movs    r3, #31                 @ picture r0 at x = r1 on the bar's row
        movs    r2, #BAR_Y
        b.w     ui_call

        .org    0x420
progress:                               @ ---- the bar
        movs    r5, #0
        cbz     r7, 5f
        movs    r5, #BAR_LEN
        muls    r5, r6, r5
        udiv    r5, r5, r7
        cmp     r5, #BAR_LEN
        bls     5f
        movs    r5, #BAR_LEN
5:      adds    r5, #BAR_X              @ r5 = knob position
        ldrb.w  r6, [r4, #STATE_OFF]    @ r6 = where it was drawn last
        strb.w  r5, [r4, #STATE_OFF]
        cmp.w   r8, #1
        beq     full
        subs    r0, r5, r6
        cmp     r0, #1
        beq     quick
        bcc     done                    @ unchanged
full:   movs    r0, #TRACK
        movs    r1, #0
        bl      draw
        movs    r7, #BAR_X
6:      cmp     r7, r5
        bcs     knob
        movs    r0, #SEGMENT
        mov     r1, r7
        bl      draw
        adds    r7, #6
        b       6b
quick:  movs    r0, #COLUMN
        mov     r1, r6
        bl      draw
knob:   movs    r0, #KNOB
        mov     r1, r5
        bl      draw

        .org    0x476
done:   nop

        .org    0x47c
lit_total:      .word 0
lit_elapsed:    .word 0
lit_flags:      .word 0

        .org    0x5d6
        .thumb_func
ui_call:        nop
        .org    0x61c
        .thumb_func
get_total:      nop
