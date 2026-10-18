"""Audit this kernel's emitted MXU Release-1 subset, without emulation deps.

JZ4740 supports Release-1 only. Reference: Ingenic SIMD/DSP Instruction Set,
2007 revision 1.1, release history and instruction-summary *1 annotations.
https://www.sccs.swarthmore.edu/users/16/mmcconv1/jz-simd-docs.pdf
"""
import struct

def audit(payload):
    start=payload.find(struct.pack('<I',0x50314d58))
    if start<0:return None
    end=payload.index(struct.pack('<I',0x50314d59),start+4)
    operations=0
    for offset in range(start+4,end,4):
        word=struct.unpack_from('<I',payload,offset)[0]
        if word>>26!=28:continue
        op=word&63
        assert op in (2,0x10,0x19,0x30,0x32,0x33,0x0e,0x3d,0x07,0x2e,0x2f),hex(word)
        if op==0x19:assert word>>22&15==0,'Release-2 D32ASUM/ACCM on JZ4740'
        if op==0x07:assert word>>18&63==6,'Unexpected MXU pool02 opcode'
        operations+=op!=2
    return {'ISA':'MXU Release-1 (JZ4740)','static_extension_instructions':operations,'kernel_bytes':end-start-4}
