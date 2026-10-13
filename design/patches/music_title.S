@ MUSIC.AP, tag reader, bank at 0x1c102000: the step that runs after a file's tags were read
@ (bank offsets 0x1d4 to 0x1f2, 30 bytes, inside the routine at 0x1c1021ce).
@
@ Stock: the title buffer is always overwritten with the file name, so the playing screen shows the file name
@ even when the tag has a title. The same routine fills the other fields only when they are empty.
@ New: the file name is fetched only when the title is empty (first byte 0; a UTF-16 title starts with ff fe).
@ r4 = the tag record: +0 title buffer, +24 its size in bytes.

        .syntax unified
        .cpu cortex-m3
        .thumb

        .org    0x0ee
        .thumb_func
short_name:     nop                     @ turns an 8.3 name ("NAME    EXT") into "NAME.EXT"

        .org    0x1d4
start:  ldr     r1, [r4, #0]            @ title buffer
        ldrb    r0, [r1]
        cbnz    r0, keep                @ the tag had a title
        movs    r0, #2                  @ file-system call 2: name of the current file
        str     r0, [sp, #0]
        ldrb    r2, [r4, #24]
        lsrs    r2, r2, #1              @ room in characters
        movs    r3, #0
        ldr     r0, lit_mount
        ldr     r0, [r0, #0]
        bl      file_call
        ldr     r0, [r4, #0]
        bl      short_name

        .org    0x1f2
keep:   nop

        .org    0x2dc
lit_mount:      .word 0

        .org    0x30a
        .thumb_func
file_call:      nop
