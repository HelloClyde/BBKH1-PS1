"""Compare compiled MDEC color conversion with scalar wrapping/rounding oracle."""
from pathlib import Path
import argparse,json,random,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine

def signed(x):
    x&=0xffffffff
    return x-0x100000000 if x&0x80000000 else x

def reference(block,depth,bw,alpha):
    result=bytearray()
    for y in range(16):
        for x in range(16):
            yv=block[(2+(y//8)*2+x//8)*64+(y%8)*8+x%8]
            limit,bias,shift=(255,128,20) if depth==24 else (31,16,23)
            if bw:rgb=[max(0,min(limit,(yv if depth==24 else yv>>3)+bias))]*3
            else:
                cr,cb=block[(y//2)*8+x//2],block[64+(y//2)*8+x//2]
                chroma=(signed(1434*cr),signed(-351*cb-728*cr),signed(1807*cb))
                rgb=[max(0,min(limit,(signed(signed((yv<<10)+c)+(1<<(shift-1)))>>shift)+bias)) for c in chroma]
            if depth==24:result.extend(rgb)
            else:result.extend(struct.pack('<H',rgb[0]|(rgb[1]<<5)|(rgb[2]<<10)|(0x8000 if alpha else 0)))
    return bytes(result)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('before',type=Path);ap.add_argument('after',type=Path)
    args=ap.parse_args();machines=[PS1Machine(p,b'') for p in (args.before,args.after)]
    rng=random.Random(0x4d444543);src,dst=0x83000000,0x83002000;cost=[];cases=0
    fixtures=[]
    for value in (0,1,-1,-131072,130048,131072,-132096,0x7fffffff,-0x80000000,0x200000,-0x200000):fixtures.append([value]*384)
    for i in range(117):
        bound=(200000,1048576,0x80000000)[i%3]
        fixtures.append([rng.randrange(-bound,bound) for _ in range(384)])
    def call(m,depth,bw,alpha,block,alignment,trace=False):
        sy=m.symbols;abi=struct.unpack('<10I',m.read(sy['h1_ps1_abi'],40))
        m.write(sy['Config']+abi[6]-7,bytes([bw]))
        state=next(v for k,v in sy.items() if k.startswith('_ZL4mdec'))
        m.word(state,0x02000000 if alpha else 0)
        address=next(v for k,v in sy.items() if k.startswith('_ZL9yuv2rgb'+str(depth)))
        data=struct.pack('<384i',*block);m.write(src,data);m.write(dst,bytes([0xa5])*1024)
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        status=0x10000400|(alignment&1)
        m.uc.reg_write(UC_MIPS_REG_CP0_STATUS,status)
        if m.ps1_mxu:m.ps1_mxu['xr'][16]=(alignment&3)|0x40000000
        m.uc.reg_write(UC_MIPS_REG_A0,src);m.uc.reg_write(UC_MIPS_REG_A1,dst+32+alignment)
        saved=[m.uc.reg_read(r) for r in m.saved_regs];count=[0]
        def step(*unused):count[0]+=1
        hook=m.uc.hook_add(UC_HOOK_CODE,step) if trace else None
        m.uc.emu_start(address,0,count=1_000_000)
        if hook is not None:m.uc.hook_del(hook)
        assert m.finished and m.uc.reg_read(UC_MIPS_REG_SP)==0x83aff000
        assert m.uc.reg_read(UC_MIPS_REG_CP0_STATUS)==status
        assert saved==[m.uc.reg_read(r) for r in m.saved_regs]
        assert m.read(src,len(data))==data
        expected=bytes([0xa5])*(32+alignment)+reference(block,depth,bw,alpha)
        expected+=bytes([0xa5])*(1024-len(expected))
        assert m.read(dst,1024)==expected,(depth,bw,alpha,alignment,m.metadata['sha256'])
        return count[0]
    for i,block in enumerate(fixtures):
        for depth in (15,24):
            for bw in (0,1):
                for alpha in (0,1):
                    for m in machines:call(m,depth,bw,alpha,block,(i&3) if depth==24 else 2*(i&1))
                    cases+=1
    for depth in (15,24):
        block=[rng.randrange(-131072,131072) for _ in range(384)]
        cost.append({'depth':depth,'pixels':256,'before':call(machines[0],depth,0,0,block,0,True),
                     'after':call(machines[1],depth,0,0,block,0,True)})
    report={'ok':True,'environment':'compiled MIPS + independent scalar wrapping/rounding oracle; not physical FPS',
            'before_sha256':machines[0].metadata['sha256'],'sha256':machines[1].metadata['sha256'],'cases':cases,
            'checks':['RGB15 and RGB24','grayscale','alpha flag','all valid destination alignments','rounding and saturation',
                      'full signed input range and 32-bit wrap','source unchanged','output canaries','callee registers and stack'],
            'native_instruction_counts':cost}
    if machines[1].ps1_mxu:
        report['mxu']={k:v for k,v in machines[1].ps1_mxu.items() if k in ('calls','operations','max_masked_instructions')}
        report['checks']+=['IRQ enabled/disabled and full used XR/control restoration']
    (args.after.parent/'mdec-color-equivalence.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
if __name__=='__main__':main()
