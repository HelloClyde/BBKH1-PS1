/* Original PS1 workload: R3000 integer/memory loops, GPU tiles and triangles.
 * GPL-2.0-or-later; assembled with GNU binutils, no PS1 SDK required. */
    .set noreorder
    .set noat
    .text
    .globl _start
_start:
    lui $s0,0x1f80
    ori $s0,$s0,0x1810
    lui $s1,0x8000
    /* Self-modified guest code must invalidate previously compiled blocks. */
    lui $t7,0x8001
    ori $t7,$t7,0x2000
    lui $t0,0x2402
    ori $t0,$t0,17
    sw $t0,0($t7)
    lui $t0,0x03e0
    ori $t0,$t0,8
    sw $t0,4($t7)
    sw $zero,8($t7)
    jalr $t7
    nop
    sw $v0,0x108($s1)
    lui $t0,0x2402
    ori $t0,$t0,34
    sw $t0,0($t7)
    jalr $t7
    nop
    sw $v0,0x10c($s1)
    /* GTE NCLIP: twice the signed area of a 64x64 right triangle. */
    mtc2 $zero,$12
    ori $t0,$zero,64
    mtc2 $t0,$13
    lui $t0,64
    mtc2 $t0,$14
    .word 0x4a140006
    mfc2 $t0,$24
    nop
    sw $t0,0x110($s1)
    /* Branch delay slot executes once. */
    ori $t0,$zero,7
    b 1f
    addiu $t0,$t0,5
    addiu $t0,$t0,99
1:
    sw $t0,0x114($s1)
    jal sdk_wait_probe
    nop
    nor $t0,$v0,$zero
    lw $t1,0x114($s1)
    nop
    xor $t0,$t0,$t1
    sw $t0,0x114($s1)
    lui $t0,0x0300
    sw $t0,4($s0)
    lui $t0,0x0800
    ori $t0,$t0,1
    sw $t0,4($s0)
    lui $t0,0x0704
    ori $t0,$t0,0x0010
    sw $t0,4($s0)
    lui $t0,0x0500
    sw $t0,4($s0)
    lui $t0,0xe300
    sw $t0,0($s0)
    lui $t0,0xe403
    ori $t0,$t0,0xbd3f
    sw $t0,0($s0)
    lui $t0,0xe500
    sw $t0,0($s0)
    move $s2,$zero
frame:
    /* Stable checksum 637627500 for 5000 iterations summing i*51. */
    ori $t1,$zero,5000
    move $t2,$zero
arithmetic:
    sll $t3,$t1,5
    sll $t4,$t1,4
    addu $t3,$t3,$t4
    sll $t4,$t1,1
    addu $t3,$t3,$t4
    addu $t3,$t3,$t1
    addu $t2,$t2,$t3
    addiu $t1,$t1,-1
    bnez $t1,arithmetic
    nop
    sw $t2,0x100($s1)
    /* Blue background, red and green tiles. */
    lui $t0,0x02b0
    sw $t0,0($s0)
    sw $zero,0($s0)
    lui $t0,240
    ori $t0,$t0,320
    sw $t0,0($s0)
    lui $t0,0x6000
    ori $t0,$t0,0xff
    sw $t0,0($s0)
    lui $t0,40
    ori $t0,$t0,40
    sw $t0,0($s0)
    lui $t0,80
    ori $t0,$t0,80
    sw $t0,0($s0)
    lui $t0,0x6000
    ori $t0,$t0,0xff00
    sw $t0,0($s0)
    lui $t0,40
    ori $t0,$t0,200
    sw $t0,0($s0)
    lui $t0,80
    ori $t0,$t0,80
    sw $t0,0($s0)
    /* 48 shaded triangles, exercised on every emulated frame. */
    ori $t5,$zero,48
triangles:
    lui $t0,0x30ff
    sw $t0,0($s0)
    lui $t0,130
    ori $t0,$t0,100
    sw $t0,0($s0)
    ori $t0,$zero,0xff
    sw $t0,0($s0)
    lui $t0,210
    ori $t0,$t0,160
    sw $t0,0($s0)
    ori $t0,$zero,0xff00
    sw $t0,0($s0)
    lui $t0,130
    ori $t0,$t0,220
    sw $t0,0($s0)
    addiu $t5,$t5,-1
    bnez $t5,triangles
    nop
    addiu $s2,$s2,1
    sw $s2,0x104($s1)
    /* Consume the hardware VBlank IRQ bit. */
    lui $t6,0x1f80
wait_vblank:
    lw $t0,0x1070($t6)
    nop
    andi $t0,$t0,1
    beqz $t0,wait_vblank
    nop
    ori $t0,$zero,0xfffe
    sh $t0,0x1070($t6)
    b frame
    nop

/* An original SDK-style timeout loop exercises both the batched native path
 * and the unmodified fall-through timeout handler. */
sdk_wait_probe:
    addiu $sp,$sp,-32
    sw $ra,24($sp)
    ori $t0,$zero,3
    lui $t1,0x8001
    sw $t0,0x3000($t1)
    ori $v0,$zero,50
    sw $v0,16($sp)
    ori $a0,$zero,10
    addiu $v1,$zero,-1
    b sdk_head
    nop
sdk_tail:
    lw $v0,16($sp)
    nop
    addiu $v0,$v0,-1
    sw $v0,16($sp)
    lw $v0,16($sp)
    nop
    bne $v0,$v1,sdk_head
    nop
    lw $ra,24($sp)
    addiu $sp,$sp,32
    jr $ra
    nop
sdk_head:
    lui $v0,0x8001
    lw $v0,0x3000($v0)
    nop
    slt $v0,$v0,$a0
    bnez $v0,sdk_tail
    nop
    lw $v0,16($sp)
    lw $ra,24($sp)
    addiu $sp,$sp,32
    jr $ra
    nop
