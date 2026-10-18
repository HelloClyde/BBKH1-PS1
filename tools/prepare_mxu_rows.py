"""Reuse the verified MXU1 strip body four times per saved context."""
def rows_assembly(asm):
    asm=asm.replace('h1_mdec_row24_mxu','h1_mdec_rows24_mxu')
    start=' quad 0,0,0\n';last=' quad 280,42,28\n'
    assert asm.count(start)==asm.count(last)==1
    asm=asm.replace(start,' li $t8,4\n1:\n'+start)
    asm=asm.replace(last,last+''' addiu $a0,$a0,32
 addiu $a1,$a1,64
 addiu $t8,$t8,-1
 bnez $t8,1b
 addiu $a2,$a2,96
''')
    asm=asm.replace('one 16x2 cached-RAM strip per call.','one 16x8 cached-RAM tile per call.')
    asm=asm.replace('a0=8 Cr samples (Cb at +256), a1=left Y block, a2=96 output bytes.',
        'a0=32 Cr samples (Cb at +256), a1=adjacent left/right Y blocks, a2=384 output bytes.')
    return asm

def prepare_mxu_rows(root,build,core):
    asm=rows_assembly((root/'src/mdec_mxu.S').read_text(encoding='utf-8'))
    path=build/'mdec-mxu-rows.S';path.write_text(asm,encoding='utf-8')
    from prepare import replace
    mdec=core/'mdec.cpp'
    text=mdec.read_text(encoding='utf-8');assert text.count('h1_mdec_row24_mxu')==2
    mdec.write_text(text.replace('h1_mdec_row24_mxu','h1_mdec_rows24_mxu'),encoding='utf-8')
    replace(mdec,'for (unsigned row=0;row<8;++row)','for (unsigned row=0;row<8;row+=4)')
    return path
