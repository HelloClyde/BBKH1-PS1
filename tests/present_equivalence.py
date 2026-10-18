"""Compiled fused LCD rows vs independent full-frame pixel/alias oracle."""
from pathlib import Path
import argparse,json,random,struct
from unicorn.mips_const import *
from smoke import PS1Machine

W,H,STRIDE=362,272,480
def reference(memory,source,target,x,y,w,h,depth):
    previous=-1;row=None
    for dy in range(H):
        sy=(y+dy*h//H)%512
        if sy!=previous:
            colors=[]
            for dx in range(W):
                sx=dx*w//W
                if depth:
                    off=(2*x+3*sx)%2048;p=source+2048*sy
                    c=memory[p+off]*65536+memory[p+(off+1)%2048]*256+memory[p+(off+2)%2048]
                else:
                    p=source+2048*sy+2*((x+sx)%1024)
                    c=memory[p]+256*memory[p+1]
                    c=((c%32)*8)*65536+(((c//32)%32)*8)*256+((c//1024)%32)*8
                colors.append(c)
            row=struct.pack('<362I',*colors)
        off=target+(dy*STRIDE+59)*4;memory[off:off+len(row)]=row;previous=sy

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    m=PS1Machine(args.bda,b'');fn=m.symbols['h1_ps1_present_fused'];rng=random.Random(0x4c434446)
    src=0x83000000;dst=0x83200000;out_bytes=480*272*4;cases=0;exhaustive=0
    def call(source,target,x,y,w,h,depth):
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for reg,value in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),(target,source,x,y)):m.uc.reg_write(reg,value)
        m.write(0x83aff010,struct.pack('<3I',w,h,depth));saved=[m.uc.reg_read(r) for r in m.saved_regs]
        m.uc.emu_start(fn,0,count=10_000_000)
        assert m.finished and m.uc.reg_read(UC_MIPS_REG_SP)==0x83aff000
        assert saved==[m.uc.reg_read(r) for r in m.saved_regs]
    image=rng.randbytes(1024*512*2)
    for n in range(48):
        depth=n%2;w=(256,320,368,512,640,1024)[n%6];h=(1,32,128,224,240,256,272,480,512)[n%9]
        x=(0,1,1018,1023)[n%4];y=(0,1,509,511)[(n//4)%4];alignment=(n%4)*4
        target=dst+64+alignment;source=src+(n%2)*2
        m.write(source,image);before=bytes([0xa5])*(out_bytes+128+alignment);m.write(dst,before)
        expected=bytearray(image+before);reference(expected,0,len(image)+64+alignment,x,y,w,h,depth)
        call(source,target,x,y,w,h,depth)
        assert m.read(dst,len(before))==expected[len(image):],(n,'frame/pillar bars/canaries')
        assert m.read(source,len(image))==image,(n,'VRAM changed');cases+=1
    # All 65536 input words, including mask bit, expanded through compiled code.
    # Height 1 also verifies the original row-cache behavior for many duplicates.
    for first in range(0,65536,W):
        row=b''.join(struct.pack('<H',(first+i)&65535) for i in range(W))
        m.write(src,row);before=bytes([0x5a])*(out_bytes+128);m.write(dst,before)
        memory=bytearray(2048);memory[:len(row)]=row;expected=bytearray(memory+before)
        reference(expected,0,len(memory)+64,0,0,W,1,False);call(src,dst+64,0,0,W,1,False)
        assert m.read(dst,len(before))==expected[len(memory):],('all colors',first)
        exhaustive+=min(W,65536-first);cases+=1
    # Full source/output aliases must use the old per-row snapshot order.
    for n in range(8):
        target=64+(n%2)*0x10000;memory=bytearray(image);expected=bytearray(memory)
        x=(1023,7)[n%2];y=(511,3)[n%2];h=(240,1,512,32)[n%4];w=(320,640)[n%2];depth=n%2
        reference(expected,0,target,x,y,w,h,depth)
        m.write(src,bytes(memory));call(src,src+target,x,y,w,h,depth)
        assert m.read(src,len(memory))==expected,(n,'alias row order');cases+=1
    report={'ok':True,'sha256':m.metadata['sha256'],'cases':cases,'exhaustive_16bit_colors':exhaustive,
        'checks':['compiled MIPS vs independent 480x272 oracle','15-bit and packed 24-bit, per-row horizontal and vertical wrap',
        '256/320/368/512/640/1024 widths and 1..512 heights','single/double/many duplicate source rows',
        'all 65536 16-bit words including mask bit','full output, bars and canaries; VRAM unchanged when separate',
        'source/output aliases retain original row snapshot/write order','callee registers and stack preserved']}
    (args.bda.parent/'present-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
