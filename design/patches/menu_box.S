@ menu_box (stage 24): every list box call of a program that is not the file lists' control comes here (r0 = list
@ style or 0, r1 = list data, r2 = draw mode, r3 = 8). On a full redraw (mode 3) of a style drawn with the status bar
@ on (0x6000 + n for n in BAR_STYLES: 0, 2 the menus, 3 the counter, 4 the sub-menus with a title line, 5 the name)
@ it first draws picture BAR_CLEAR at (BAR_X, 0): black over the bar's middle, which these styles' background no
@ longer covers (the bar's marks cover the rest of it). Then the list, as the
@ caller asked. Both through the bank's own veneer to the display driver, so the code needs no literal; it sits at
@ the end of the bank it is called from (the menu routines keep their list data inside their bank).
@
@ design/graphite/lists.py assembles this per bank: BANK, VENEER_OFF and TAIL_OFF are set with --defsym.

        .syntax unified
        .cpu cortex-m3
        .thumb
        .equ    BAR_CLEAR, 0x8000 | 127
        .equ    BAR_X, 17
        .equ    BAR_STYLES, 0x3d
        .equ    PICTURE, 31
        .equ    LISTBOX, 8

        .org    VENEER_OFF
        .thumb_func
veneer: nop                             @ movw ip, #entry; movt ip, #0x11; bx ip (the bank's own)

        .org    TAIL_OFF
        .thumb_func
menu_box:
        cmp     r2, #3
        bne     go
        cbz     r0, go
        ldrh    r3, [r0]
        sub.w   r3, r3, #0x6000
        cmp     r3, #7
        bhi     go
        push    {r0, r1, r2, lr}
        movs    r0, #BAR_STYLES
        lsrs    r0, r3
        lsls    r0, r0, #31
        cmp     r0, #0
        beq     1f
        movw    r0, #BAR_CLEAR
        movs    r1, #BAR_X
        movs    r2, #0
        movs    r3, #PICTURE
        bl      veneer
1:      pop.w   {r0, r1, r2, lr}
go:     movs    r3, #LISTBOX
        b.w     veneer
