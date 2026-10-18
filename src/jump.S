    .set noreorder
    .text
    .globl h1_ps1_setjmp
h1_ps1_setjmp:
    sw $s0,0($a0)
    sw $s1,4($a0)
    sw $s2,8($a0)
    sw $s3,12($a0)
    sw $s4,16($a0)
    sw $s5,20($a0)
    sw $s6,24($a0)
    sw $s7,28($a0)
    sw $fp,32($a0)
    sw $sp,36($a0)
    sw $ra,40($a0)
    sw $gp,44($a0)
    jr $ra
    move $v0,$zero
    .globl h1_ps1_longjmp
h1_ps1_longjmp:
    lw $s0,0($a0)
    lw $s1,4($a0)
    lw $s2,8($a0)
    lw $s3,12($a0)
    lw $s4,16($a0)
    lw $s5,20($a0)
    lw $s6,24($a0)
    lw $s7,28($a0)
    lw $fp,32($a0)
    lw $sp,36($a0)
    lw $ra,40($a0)
    lw $gp,44($a0)
    jr $ra
    li $v0,1
