"""Drive the real SPU register/DMA/ADPCM/ADSR mixer and compare PCM bytes."""
from pathlib import Path
import argparse,hashlib,json,random,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine

class SPU:
    def __init__(self,bda):
        self.m=PS1Machine(bda,b'');self.pcm=[];m=self.m;sy=m.symbols
        self.call('h1_ps1_configure');assert self.call('SPUinit')==0;assert self.call('SPUopen')==0
        driver=struct.unpack('<I',m.read(sy['out_current'],4))[0]
        feed=struct.unpack('<I',m.read(driver+16,4))[0]
        def capture(uc,address,size,data):
            p=uc.reg_read(UC_MIPS_REG_A0);n=uc.reg_read(UC_MIPS_REG_A1)
            assert n<65536 and n%4==0;self.pcm.append(m.read(p,n))
            uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
        m.uc.hook_add(UC_HOOK_CODE,capture,begin=feed,end=feed)
    def call(self,name,*values):
        m=self.m;m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),values):m.uc.reg_write(r,v)
        m.uc.emu_start(m.symbols[name],0,count=4_000_000);assert m.finished,(name,hex(m.uc.reg_read(UC_MIPS_REG_PC)))
        return m.uc.reg_read(UC_MIPS_REG_V0)
    def reg(self,address,value,cycle=0):self.call('SPUwriteRegister',address,value,cycle)
    def finish(self):
        self.call('SPUshutdown');assert not self.m.allocations and not self.m.handles

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('before',type=Path);ap.add_argument('after',type=Path)
    args=ap.parse_args();rng=random.Random(0x50434d);rows=[]
    for case,voices in enumerate((1,2,4,7,11,14,24,11)):
        machines=[SPU(p) for p in (args.before,args.after)]
        wave=bytearray()
        for block in range(32):
            wave.extend(bytes([(block%5)*16+(block%13),4 if block==0 else 3 if block==31 else 0])+rng.randbytes(14))
        for s in machines:
            s.m.write(0x83b00000,bytes(wave));s.reg(0x1f801da6,0x1000)
            s.call('SPUwriteDMAMem',0x83b00000,len(wave)//2,0)
            s.reg(0x1f801daa,0xc000)
            s.reg(0x1f801d80,0x3fff);s.reg(0x1f801d82,0x3fff)
            for channel in range(voices):
                base=0x1f801c00+channel*16
                for off,value in ((0,0x3fff-channel*77),(2,0x1000+channel*91),
                    (4,(0x800,0x1000,0x1800,0x3fff)[(case+channel)%4]),(6,0x1000),
                    (8,0x000f),(10,0),(14,0x1000)):
                    s.reg(base+off,value)
            if case==7:s.reg(0x1f801d90,2) # modulation sender uses the optimized no-interpolation path
            mask=(1<<voices)-1;s.reg(0x1f801d88,mask&65535);s.reg(0x1f801d8a,mask>>16)
            total=0
            for block in range(48):
                total+=((37,92,184,128)[block%4])*768
                if block==24:s.reg(0x1f801c04,0x1500,total)
                if block==36:s.reg(0x1f801d8c,1,total)
                s.call('SPUasync',total,1)
        a,b=(b''.join(s.pcm) for s in machines)
        assert a==b and any(a),(case,voices,len(a),len(b))
        rows.append({'voices':voices,'stereo_frames':len(a)//4,'sha256':hashlib.sha256(a).hexdigest()})
        for s in machines:s.finish()
    report={'ok':True,'before_sha256':machines[0].m.metadata['sha256'],'sha256':machines[1].m.metadata['sha256'],
        'cases':len(rows),'pcm':rows,'checks':['actual SPU register/DMA interfaces and ADPCM blocks',
            '1..24 simultaneous voices, ADSR, pitch changes and key off','ADPCM loop start/end and frequency modulation',
            'bit-identical interleaved stereo PCM with varying update boundaries','all SPU allocations released']}
    (args.after.parent/'spu-audio-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
