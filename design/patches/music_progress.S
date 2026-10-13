@ MUSIC.AP, code bank at 0x18061000: the end of the routine that draws the playing time and the
@ progress knob (bank offsets 0x3f4 to 0x476, 130 bytes).
@
@ Stock behaviour of the progress part: on every refresh draw the whole track picture (which wipes the knob)
@ and then the knob. With a light knob on a dark track that shows as flicker.
@ New behaviour on a refresh (not on a full repaint of the screen):
@   knob position unchanged      -> draw nothing
@   knob one pixel further right -> restore the one column it leaves behind (picture 66, one pixel wide),
@                                   then draw the knob at its new place; the knob is never absent
@   anything else (seek, new track) and every full repaint -> as stock
@ The last knob position is kept in a byte only the unused "demo" screensaver mode refers to.
@ The time part before it is the stock logic written compactly, which frees the room.

        .syntax unified
        .cpu cortex-m3
        .thumb
        .equ    TRACK, 67
        .equ    KNOB, 68
        .equ    COLUMN, 66
        .equ    BAR_Y, 110
        .equ    STATE, 0x00200191

        .org    0x3f4
time_tail:                              @ r5 = style, r8 = 1 on a full repaint; elapsed and total time are on the stack
        ldrh.w  r0, [sp, #12]           @ total has hours?
        movs    r1, #6
        cbz     r0, 1f
        movs    r1, #4
        ldr     r2, lit_flags
        ldr     r0, [r2]
        bic.w   r0, r0, #0xb00
        str     r0, [r2]
1:      strb.w  r1, [sp, #17]
        movs    r2, #1
        cmp.w   r8, #1
        bne     2f
        movs    r2, #2
2:      movs    r3, #4
        add     r1, sp, #4
        mov     r0, r5
        bl      ui_call
        b       done

        .org    0x422
quick:  movs    r3, #31
        movs    r2, #BAR_Y
        mov     r1, r6                  @ the old position: its left column is all the new knob will not cover
        movs    r0, #COLUMN
        bl      ui_call
        b       knob
full:   movs    r3, #31
        movs    r2, #BAR_Y
        movs    r1, #0
        movs    r0, #TRACK
        bl      ui_call
knob:   movs    r3, #31
        movs    r2, #BAR_Y
        mov     r1, r7
        movs    r0, #KNOB
        bl      ui_call
        b       done

        .org    0x44a
progress:                               @ r4 = total seconds, r6 = elapsed seconds
        movs    r7, #0
        cbz     r4, 3f
        movs    r0, #122
        muls    r0, r6, r0
        udiv    r7, r0, r4
        cmp     r7, #122
        bls     3f
        movs    r7, #122
3:      movw    r4, #:lower16:STATE
        movt    r4, #:upper16:STATE
        ldrb    r6, [r4]                @ where the knob was drawn last
        strb    r7, [r4]
        cmp.w   r8, #1
        beq     full
        subs    r0, r7, r6
        cmp     r0, #1
        beq     quick
        bhi     full
                                        @ unchanged: nothing to draw
        .org    0x476
done:   nop

        .org    0x484
lit_flags:      .word 0

        .org    0x5d6
        .thumb_func
ui_call:        nop
