/* Exact PCSX4ALL RGB24 conversion, one 16x2 cached-RAM strip per call.
 * a0=8 Cr samples (Cb at +256), a1=left Y block, a2=96 output bytes.
 * All operations wrap at 32 bits before arithmetic rounding. Signed lanes
 * are narrowed only after >>20, then biased and saturated to unsigned bytes.
 * MXU Release-1 only: JZ4740 has no D32ASUM or S8STD (Release-2).
 * No IO/service calls under the IRQ mask. Preserve every used XR and control.
 */
.set mips32
.set noreorder
.set noat
.macro move_xr op,xr,gpr
 .word (0x70000000 | (\gpr << 16) | (\xr << 6) | \op)
.endm
.macro load_xr xr,gpr,offset
 .word (0x70000010 | (\gpr << 21) | ((\offset / 4) << 10) | (\xr << 6))
.endm
.macro op4 op,a,b,c,d,extra=0
 .word (0x70000000 | (\extra << 22) | (\d << 18) | (\c << 14) | (\b << 10) | (\a << 6) | \op)
.endm
.macro pair yoff,outoff
 load_xr 1,5,\yoff
 load_xr 2,5,(\yoff+4)
 op4 0x30,3,1,2,4,10
 op4 0x30,5,1,2,6,10
 op4 0x30,7,1,2,8,10
 op4 0x19,3,11,0,4 /* D32ACC: both Y lanes += R + XR0 */
 op4 0x19,5,12,0,6
 op4 0x19,7,13,0,8
 op4 0x33,3,3,4,4,15
 op4 0x33,5,5,6,6,15
 op4 0x33,7,7,8,8,15
 op4 0x32,3,4,3,0,5 /* R1:R0, signed 12-bit range fits int16 */
 op4 0x32,5,6,5,0,5
 op4 0x32,7,8,7,0,5
 op4 0x0e,3,3,9,10 /* Q16ADD: +128 to both signed lanes */
 op4 0x0e,5,5,9,10
 op4 0x0e,7,7,9,10
 op4 0x3d,5,5,3,6,12 /* S32SFL PTN3: G1:R1 and G0:R0 */
 op4 0x07,5,5,6,6 /* Q16SAT pool02 sub6 */
 op4 0x07,7,0,7,6
 move_xr 0x2e,5,8
 move_xr 0x2e,7,9
 sb $t0,\outoff($a2)
 sb $t1,(\outoff+2)($a2)
 srl $t0,$t0,8
 sb $t0,(\outoff+1)($a2)
 srl $t1,$t1,8
 sb $t1,(\outoff+5)($a2)
 srl $t0,$t0,8
 sb $t0,(\outoff+3)($a2)
 srl $t0,$t0,8
 sb $t0,(\outoff+4)($a2)
.endm
.macro quad yoff,outoff,croff
 lw $t0,\croff($a0)
 lw $t1,(\croff+256)($a0)
 mul $t2,$t0,$t3
 addu $t2,$t2,$t7
 move_xr 0x2f,11,10
 mul $t2,$t0,$t6
 mul $t0,$t1,$t5
 addu $t2,$t2,$t0
 addu $t2,$t2,$t7
 move_xr 0x2f,12,10
 mul $t2,$t1,$t4
 addu $t2,$t2,$t7
 move_xr 0x2f,13,10
 pair \yoff,\outoff
 pair (\yoff+32),(\outoff+48)
.endm
.section .text.h1_mdec_row24_mxu,"ax",@progbits
.word 0x50314d58
.global h1_mdec_row24_mxu
.type h1_mdec_row24_mxu,@function
h1_mdec_row24_mxu:
 addiu $sp,$sp,-64
 mfc0 $t0,$12
 sw $t0,56($sp)
 srl $t1,$t0,1
 sll $t1,$t1,1
 mtc0 $t1,$12
 nop
 nop
 nop
 move_xr 0x2e,16,8
 sw $t0,52($sp)
 ori $t0,$t0,1
 move_xr 0x2f,16,8
 .irp xr,1,2,3,4,5,6,7,8,9,10,11,12,13
  move_xr 0x2e,\xr,8
  sw $t0,((\xr-1)*4)($sp)
 .endr
 li $t0,0x00800080
 move_xr 0x2f,9,8
 li $t3,1434
 li $t4,1807
 li $t5,-351
 li $t6,-728
 lui $t7,8
 quad 0,0,0
 quad 8,6,4
 quad 16,12,8
 quad 24,18,12
 quad 256,24,16
 quad 264,30,20
 quad 272,36,24
 quad 280,42,28
 .irp xr,1,2,3,4,5,6,7,8,9,10,11,12,13
  lw $t0,((\xr-1)*4)($sp)
  move_xr 0x2f,\xr,8
 .endr
 lw $t0,52($sp)
 move_xr 0x2f,16,8
 lw $t0,56($sp)
 mtc0 $t0,$12
 nop
 nop
 nop
 jr $ra
 addiu $sp,$sp,64
.size h1_mdec_row24_mxu,.-h1_mdec_row24_mxu
.word 0x50314d59
