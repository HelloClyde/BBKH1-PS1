"""Compare actual compiled UNAI spans against scalar pixel order and old BDA."""
from pathlib import Path
import argparse,json,random,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('before',type=Path);ap.add_argument('after',type=Path)
    args=ap.parse_args();machines=[PS1Machine(p,b'') for p in (args.before,args.after)]
    rng=random.Random(0x48315350);base=0x83000000;size=8192;cases=0;cost=[]
    def symbol(m,name,cf):
        prefix=f'_Z{len(name)}{name}ILi{cf}EE'
        return m.symbols[next(k for k in m.symbols if k.startswith(prefix))]
    def call(m,name,cf,values,trace=False):
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),values):m.uc.reg_write(r,v)
        count=[0]
        def step(*unused):count[0]+=1
        hook=m.uc.hook_add(UC_HOOK_CODE,step) if trace else None
        m.uc.emu_start(symbol(m,name,cf),0,count=1_000_000)
        if hook is not None:m.uc.hook_del(hook)
        assert m.finished and m.uc.reg_read(UC_MIPS_REG_SP)==0x83aff000
        return count[0]
    def get(buf,p):return struct.unpack_from('<H',buf,p)[0]
    def put(buf,p,v):struct.pack_into('<H',buf,p,v)
    for name in ('gpuTileSpanFn','gpuPolySpanFn','gpuSpriteSpanFn'):
        for iteration in range(256):
            count=([1,2,7,8,9,15,16,31,128,255,511][iteration%11] if iteration<44 else rng.randrange(1,512))
            offset=256+2*(iteration&1);color=rng.randrange(65536);cf=(0,2,4,6,256,258)[iteration%6]
            original=bytes(rng.randrange(256) for _ in range(size));expected=bytearray(original)
            texture,clut=2048,4096;u=rng.choice((0,1,2,3,254,255,0xffffffff,rng.randrange(65536)))
            mask=rng.choice((0,1,7,15,31,127,255,0xf7,0xe8,0xfe))
            if name=='gpuSpriteSpanFn':
                cf=32
                # Exercise read-after-write texture/CLUT aliases and transparent
                # pixels. The byte image is updated in original pixel order.
                if iteration%7==0:offset=texture-2
                if iteration%11==0:offset=clut-2
                mutable=bytearray(original)
                for index in (0,3,7,12):put(mutable,clut+index*2,0)
                original=bytes(mutable);expected=bytearray(original)
                for n in range(count):
                    index=(expected[texture+((u&mask)>>1)]>>((u&1)*4))&15
                    value=get(expected,clut+2*index)
                    if value:put(expected,offset+2*n,value)
                    u=(u+1)&0xffffffff
                u=(u-count)&0xffffffff
            else:
                for n in range(count):
                    old=get(expected,offset+2*n)
                    if cf&4 and old&0x8000:continue
                    value=(((old&0x7bde)+(color&0x7bde))>>1) if cf&2 else color
                    if cf&256:value|=0x8000
                    put(expected,offset+2*n,value)
            for m in machines:
                m.write(base,original)
                gpu=m.symbols[next(k for k in m.symbols if k.startswith('_ZL8gpu_unai.'))]
                if name=='gpuSpriteSpanFn':
                    m.write(gpu+78,bytes([mask]));m.word(gpu+96,base+clut)
                    values=(base+offset,count,base+texture,u)
                elif name=='gpuPolySpanFn':
                    m.write(gpu+138,struct.pack('<H',color));values=(gpu,base+offset,count)
                else:values=(base+offset,count,color)
                call(m,name,cf,values)
                actual=m.read(base,size)
                assert actual==bytes(expected),(name,iteration,count,cf,offset,mask,m.metadata['sha256'])
            cases+=1
        # Count native instructions on matched long opaque spans, independent
        # of Python wall time. These figures are not physical FPS.
        for cf in ((0,2,32) if name=='gpuPolySpanFn' else ((0,2) if name=='gpuTileSpanFn' else (32,))):
            row={'name':name,'cf':cf,'pixels':128}
            for label,m in zip(('before','after'),machines):
                gpu=m.symbols[next(k for k in m.symbols if k.startswith('_ZL8gpu_unai.'))]
                m.write(base,bytes([0x77])*size);m.write(gpu+78,b'\xff');m.word(gpu+96,base+4096)
                m.write(gpu+138,struct.pack('<H',0x3210))
                m.word(gpu+92,base+2048);m.write(gpu+100,struct.pack('<6I',0,1024,0x3ffff,0x3ffff,1024,0))
                values=(base+256,128,base+2048,0) if name=='gpuSpriteSpanFn' else ((gpu,base+256,128) if name=='gpuPolySpanFn' else (base+256,128,0x3210))
                row[label]=call(m,name,cf,values,trace=True)
            cost.append(row)
    for iteration in range(256):
        count=rng.choice((1,7,8,9,16,31,128,255));offset=256+2*(iteration&1)
        texture,clut=2048,6144
        if iteration%7==0:offset=texture-2
        if iteration%11==0:offset=clut-2
        fixture=bytearray(rng.randrange(256) for _ in range(size))
        for index in (0,3,7,12):put(fixture,clut+index*2,0)
        original=bytes(fixture);expected=bytearray(original)
        u0=rng.randrange(0x40000);v0=rng.randrange(0x2000)
        umask=rng.choice((0x3ffff,0x1ffff,0x1bfff,0x03fff));vmask=0x7ff
        du=rng.choice((0,1,1024,2048,-1024,-7777,12345));dv=0 if iteration%4 else 1024
        u,v=u0&umask,v0&vmask
        for n in range(count):
            byte=expected[texture+(u>>11)+((v<<1)&0x7f800)]
            value=get(expected,clut+2*((byte>>((u>>8)&4))&15))
            if value:put(expected,offset+2*n,value)
            u=(u+du)&umask;v=(v+dv)&vmask
        for m in machines:
            m.write(base,original);gpu=m.symbols[next(k for k in m.symbols if k.startswith('_ZL8gpu_unai.'))]
            m.word(gpu+92,base+texture);m.word(gpu+96,base+clut)
            m.write(gpu+100,struct.pack('<6I',u0,v0,umask,vmask,du&0xffffffff,dv))
            call(m,'gpuPolySpanFn',32,(gpu,base+offset,count))
            assert m.read(base,size)==bytes(expected),('textured polygon',iteration,count,du,dv,m.metadata['sha256'])
        cases+=1
    report={'ok':True,'environment':'compiled MIPS UNAI spans + scalar pixel-order oracle; not physical FPS',
            'before_sha256':machines[0].metadata['sha256'],'sha256':machines[1].metadata['sha256'],
            'cases':cases,'checks':['whole scratch image including canaries','transparent texels','odd/even source and destination',
                'texture-window holes and wrap','texture/CLUT aliases','mask check and mask set','packed average matches existing rounding',
                'constant-V polygons with signed/fractional/wrapped UV and aliases','nonzero V increment fallback'],
            'native_instruction_counts':cost}
    (args.after.parent/'raster-equivalence.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
