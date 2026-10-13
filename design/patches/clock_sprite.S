@ Shared screensaver code, bank at 0x18ce1a00 (present in every program with a user interface):
@ the first part of the routine that draws the clock (bank offsets 0x034 to 0x0c6, 146 bytes).
@
@ Stock behaviour, kept: on the first call draw the background picture; return at once if the minute has not
@ changed; otherwise prepare the drawing of the digits.
@ Added: on every call (the screensaver timer calls this routine) draw the next frame of a small animation
@ below the clock. The frame number lives in the byte the unused "demo" screensaver mode keeps its picture
@ number in; that byte sits 4 bytes before the "last minute drawn" byte in every program.

        .syntax unified
        .cpu cortex-m3
        .thumb
        .equ    FRAMES, 12
        .equ    FIRST, 0x8000 + 221             @ first frame: picture 221 of COMMON.STY
        .equ    SPRITE_X, 36
        .equ    SPRITE_Y, 72

        .org    0x034
patch_start:
        ldr     r4, lit_table
        ldrh    r4, [r4]
        ldr     r7, lit_settings
        ldr     r7, [r7]                        @ settings block
        ldrb    r0, [r7, #30]
        adds    r4, r4, r0                      @ background picture = first + chosen number
        cmp.w   sl, #1                          @ first call?
        bne     1f
        mov     r0, r4
        movs    r1, #0
        movs    r2, #0
        movs    r3, #31
        bl      show_picture
        mov.w   fp, #1
1:      ldr     r1, lit_last_minute
        subs    r1, #4                          @ frame counter
        ldrb    r0, [r1]
        adds    r0, #1
        cmp     r0, #FRAMES
        bcc     2f
        movs    r0, #0
2:      strb    r0, [r1]
        movw    r2, #FIRST
        adds    r0, r0, r2
        movs    r1, #SPRITE_X
        movs    r2, #SPRITE_Y
        movs    r3, #31
        bl      show_picture
        ldrb.w  r0, [sp, #37]                   @ minute now
        ldr     r1, lit_last_minute
        ldrb    r2, [r1]
        cmp     r0, r2
        bne     3f
        cmp.w   fp, #1
        bne     leave                           @ nothing to redraw
3:      cmp     r2, #59
        bne     4f
        mov.w   fp, #1                          @ hour changed: redraw everything
4:      strb    r0, [r1]
        movs    r3, #62
        movs    r2, #0
        movs    r1, #0
        movs    r0, #30
        bl      system_call
        uxtb    r0, r0
        str     r0, [sp, #0]
        add     r1, sp, #12                     @ text settings for the digits
        movw    r0, #0xb5b6
        strh    r0, [r1, #4]
        strh    r4, [r1, #8]
        movs    r0, #1
        strb    r0, [r1, #2]
        movs    r0, #0
        strb    r0, [r1, #3]
        strh    r0, [r1, #10]
        strh    r0, [r1, #12]
        ldrb    r0, [r7, #10]
        cbnz    r0, patch_end
        subs    r5, #7

        .org    0x0c6
patch_end:
        nop

        .org    0x14a
leave:  nop

        .org    0x3e4
lit_table:              .word 0
lit_settings:           .word 0
lit_last_minute:        .word 0

        .org    0x412
        .thumb_func
system_call:    nop
        .org    0x41c
        .thumb_func
show_picture:   nop
