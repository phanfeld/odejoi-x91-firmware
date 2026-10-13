@ EBOOK.AP, the reading screen, bank at 0x180e1000. Three stretches are rewritten:
@
@   0x0dc to 0x18e   the routine that paints the page (stock, written compactly), now bracketed by the display
@                    driver's "turn the screen" call: landscape while the page is drawn, portrait again
@                    afterwards, so everything else the firmware shows (menus, notices, screensaver) is untouched.
@   0x48c to 0x50a   the top strip with "page/pages" becomes a bottom strip: strip picture and page number.
@                    Stock redrew the number on every step of the running page count; now the strip is
@                    drawn when the page changes or the screen is repainted, and once when the count is done.
@   0x3c0 to 0x406   stock: the "pages turn by themselves" mark. Not shown any more; the room holds the
@                    progress bar: BAR_LEN * page / pages, drawn as 8-pixel pieces and single columns in the
@                    accent colour over the track that is part of the strip picture. Empty while the
@                    pages are still being counted.
@
@ Flags, as bytes from the "full repaint" flag: +7 page needs drawing, +8 page number needs drawing,
@ +10 page count running. The builder checks that the program's variables are laid out that way.

        .syntax unified
        .cpu cortex-m3
        .thumb
        .equ    BAR_X, 6
        .equ    BAR_LEN, 104
        .equ    BAR_Y, 119
        .equ    PIECE, 43               @ pictures of EBOOK.STY: 8 x 3 and 1 x 3 in the accent colour
        .equ    COLUMN, 44

        .org    0x0dc
paint:  push    {r4, r5, r6, lr}
        sub     sp, #12
        ldr     r4, lit_page
        ldr     r5, lit_cfg
        movs    r0, #1
        bl      turn                    @ landscape
        ldrb    r0, [r4, #1]
        cmp     r0, #1
        beq     1f
        ldrb    r0, [r4]
        cmp     r0, #1
        bne     2f
1:      ldr     r0, lit_sys
        ldrb    r0, [r0, #9]
        cbnz    r0, 2f
        bl      strip
        movs    r0, #0
        strb    r0, [r4, #1]
2:      ldrb    r0, [r4]
        cmp     r0, #1
        bne     3f
        mov     r1, sp                  @ page background: picture box 0, frame = page colour
        mov.w   r0, #0x1000
        strh    r0, [r1, #4]
        movs    r0, #0
        strb    r0, [r1, #6]
        subs    r0, #1
        strh    r0, [r1, #0]
        ldrb.w  r6, [r5, #170]
        strb    r6, [r1, #2]
        movs    r3, #2
        movs    r2, #0
        add     r0, sp, #4
        bl      ui_call
        ldr     r0, lit_offset
        ldr     r0, [r0]
        ldr     r1, lit_file
        str     r0, [r1, #12]
        movs    r0, #0                  @ text colour: black, white on the two dark pages
        cmp     r6, #4
        beq     4f
        cmp     r6, #1
        bne     5f
4:      movw    r0, #0xffff
5:      movs    r3, #19
        movs    r2, #0
        movs    r1, #0
        bl      ui_call
        add     r2, sp, #8
        ldr     r1, lit_file
        ldr     r0, lit_decode
        bl      decode_page             @ lays the page out and draws its lines
        ldr     r1, lit_offset
        ldr     r0, [r1]
        ldr     r2, [sp, #8]
        adds    r0, r0, r2
        str     r0, [r1]
        movs    r0, #0
        strb    r0, [r4]
3:      movs    r0, #0
        bl      turn                    @ portrait again
        add     sp, #12
        pop     {r4, r5, r6, pc}
turn:   movs    r3, #30
        movs    r2, #0
        movs    r1, #0
        b       ui_call

        .org    0x18e
        nop
lit_flag2:      .word 0                 @ 0x190: page number flag (not used by name: it is lit_page + 1)
lit_page:       .word 0
lit_sys:        .word 0
lit_cfg:        .word 0
lit_offset:     .word 0
lit_file:       .word 0
lit_decode:     .word 0

        .org    0x1f4
        .thumb_func
decode_page:    nop

        .org    0x3c0
bar:    cbnz    r6, 9f                  @ pages still being counted
        cbz     r7, 9f
        movs    r0, #BAR_LEN
        muls    r5, r0
        udiv    r5, r5, r7
        cmp     r5, r0
        bls     1f
        mov     r5, r0
1:      adds    r5, #BAR_X              @ r5 = where the filled part ends
        movs    r7, #BAR_X
2:      add.w   r0, r7, #8
        cmp     r0, r5
        bhi     3f
        movs    r0, #PIECE
        bl      draw
        adds    r7, #8
        b       2b
3:      cmp     r7, r5
        bcs     9f
        movs    r0, #COLUMN
        bl      draw
        adds    r7, #1
        b       3b
9:      add     sp, #20
        pop     {r4, r5, r6, r7, pc}
draw:   mov     r1, r7                  @ picture r0 at x = r7 on the bar's row
        movs    r2, #BAR_Y
        movs    r3, #31
        b       ui_call

        .org    0x410
        nop

        .org    0x48c
        .thumb_func
strip:  push    {r4, r5, r6, r7, lr}
        sub     sp, #20
        ldr     r7, lit_full
        ldrb    r0, [r7]
        movs    r1, #0
        strb    r1, [r7]
        ldrb    r6, [r7, #10]           @ r6: page count still running
        cbnz    r0, 1f
        ldrb    r0, [r7, #7]
        cmp     r0, #1
        beq     1f
        cbnz    r6, 8f                  @ only the running count ticked: nothing new to show
1:      ldr     r0, lit_cfg2
        ldrb.w  r4, [r0, #170]          @ page colour
        mov     r1, sp
        movw    r0, #0x1002             @ the strip: picture box 2
        strh    r0, [r1, #4]
        movs    r0, #0
        strb    r0, [r1, #6]
        strb    r0, [r1, #18]
        subs    r0, #1
        strh    r0, [r1, #0]
        strb    r4, [r1, #2]
        add.w   r0, r4, #0x3000         @ the page number: number box of that colour
        strh    r0, [r1, #16]
        ldr     r0, lit_cur
        ldr     r5, [r0]
        adds    r5, #1
        str     r5, [r1, #8]
        ldr     r0, lit_total
        ldr     r7, [r0]
        str     r7, [r1, #12]
        movs    r3, #2
        movs    r2, #0
        add     r0, sp, #4
        bl      ui_call
        movs    r3, #5
        movs    r2, #2
        add     r1, sp, #8
        add     r0, sp, #16
        bl      ui_call
        b       bar
8:      add     sp, #20
        pop     {r4, r5, r6, r7, pc}

        .org    0x50a
        nop
lit_cfg2:       .word 0
lit_cur:        .word 0
lit_total:      .word 0
lit_full:       .word 0

        .org    0x648
        .thumb_func
ui_call:        nop
