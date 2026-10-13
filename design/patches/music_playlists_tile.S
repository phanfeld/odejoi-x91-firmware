@ MUSIC.AP, code bank at 0x18101000: part of the routine that shows the music root menu
@ (bank offsets 0x2dc to 0x35e, 130 bytes).
@
@ Stock behaviour, kept: choose which root menu to show (six variants), then show it.
@ Added: if the program was started with start code TILE (sent by the main menu's Playlists tile),
@ do not show the menu; behave as if "Playlists" had just been chosen in it (result 0x8610),
@ and set the start code back to 1 (started from the main menu) so that Back leads to the menu.
@ The stock code was compiled without optimisation; writing it compactly frees the room for the addition.

        .syntax unified
        .cpu cortex-m3
        .thumb
        .equ    TILE, 0x40

        .org    0x0ec
lit_mode:       .word 0x00200001                @ start code (existing literal)

        .org    0x2dc
patch_start:
        ldr     r1, lit_engine
        ldrb    r1, [r1]                        @ 1 while the playback engine is running
        cbz     r0, no_card                     @ r0 = result of the storage query + 1
        movs    r0, #56
        cmp     r1, #1
        beq     store
        movs    r0, #1
        cbz     r6, store                       @ r6 = "a resume point exists"
        movs    r0, #58
        b       store
no_card:
        movs    r0, #55
        cmp     r1, #1
        beq     store
        movs    r0, #0
        cbz     r6, store
        movs    r0, #57
        ldrb.w  r1, [sp, #64]
        cmp     r1, #16
        bne     store
        movs    r3, #1
        movs    r2, #12
        movs    r1, #0
        add     r0, sp, #216
        bl      libc_call_b
        movs    r3, #19
        movs    r2, #0
        mov.w   r1, #0x1c0000
        add     r0, sp, #8
        bl      libc_call_a
        movs    r0, #0
store:
        strb.w  r0, [sp, #1]                    @ menu variant
        movs    r0, #0
        strb.w  r0, [sp, #2]
        ldr.w   r1, lit_mode
        ldrb    r0, [r1]
        cmp     r0, #TILE
        bne     show_menu
        movs    r0, #1
        strb    r0, [r1]
        movw    r5, #0x8610                     @ "Playlists chosen"
        b       patch_end
show_menu:
        mov     r1, sp
        movw    r0, #0x6002
        bl      menu_list
        mov     r5, r0
        b       patch_end

        .org    0x35e
patch_end:
        nop

        .org    0x42c
lit_engine:     .word 0x00202fbc                @ existing literal

        .org    0x634
        .thumb_func
libc_call_a:    nop
        .org    0x63e
        .thumb_func
libc_call_b:    nop

        .org    0x18601010 - 0x18101000
        .thumb_func
menu_list:      nop
