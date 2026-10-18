"""Exact SPU stepping vs the original compiled upstream macro and callbacks."""
from pathlib import Path
import argparse,json,random,struct,subprocess
from elftools.elf.elffile import ELFFile
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);args=ap.parse_args()
    folder=args.bda.parent/'spu-reference';folder.mkdir(exist_ok=True)
    original=(ROOT/'third_party/pcsx4all/src/spu/spu_pcsxrearmed/spu.c').read_text()
    macro=original[original.index('#define make_do_samples('):original.index('#define fmod_recv_check')]
    macro=macro.replace('static noinline int','__attribute__((noinline,used)) int')
    fixture='''
int *ChanBuf=(int*)0x83010020;
int *position_ptr,*index_ptr;
unsigned calls,seed,mutate,trace[512][4];
int callback(void *context,int channel,int *history) {
 unsigned k=calls++;trace[k][0]=*position_ptr;trace[k][1]=*index_ptr;
 trace[k][2]=channel;trace[k][3]=(unsigned)context;
 for(unsigned i=0;i<28;++i){seed^=seed<<13;seed^=seed>>17;seed^=seed<<5;history[i]=(int)seed;}
 if(mutate&&calls%11==0){*position_ptr=calls%33==0?0:(*position_ptr&65535)+65536;*index_ptr=calls%4;}
 return calls%7==0?-1:0;
}
int dummy(void *context,int channel,int *history){return 0;}
'''+macro+'\nmake_do_samples(reference, , fa = SB[29], , ChanBuf[ns] = fa, SB[29] = fa)\n'
    source=folder/'reference.c';source.write_text(fixture)
    tc=Path(__import__('os').environ.get('H1_GNU_BIN',ROOT/'.tools/toolchain/bin'));elf_path=folder/'reference.elf'
    cmd=[tc/'mipsel-none-elf-gcc.exe','-EL','-march=mips32','-mabi=32','-msoft-float','-mno-abicalls','-G0',
        '-fno-pic','-O3','-ffreestanding','-fno-builtin','-fno-strict-aliasing','-nostdlib',
        '-Wl,-Ttext,0x83100000','-Wl,-Tdata,0x83110000','-Wl,--section-start,.bss=0x83120000',
        '-Wl,-e,do_samples_reference','-o',elf_path,source]
    p=subprocess.run(list(map(str,cmd)),capture_output=True,text=True);assert p.returncode==0,p.stdout+p.stderr
    m=PS1Machine(args.bda,b'');symbols={}
    with elf_path.open('rb') as f:
        elf=ELFFile(f)
        for segment in elf.iter_segments():
            if segment['p_type']=='PT_LOAD':
                m.write(segment['p_vaddr'],segment.data()+bytes(segment['p_memsz']-segment['p_filesz']))
        for s in elf.get_section_by_name('.symtab').iter_symbols():symbols[s.name]=s['st_value']
    new=m.symbols['h1_spu_samples_noint'];old=symbols['do_samples_reference']
    history,output,position,index=0x83000020,0x83010020,0x83020000,0x83020004
    rng=random.Random(0x535055);cost=[]
    def run(address,callback,ch,count,step,phase,offset,data,mutate,measure=False):
        m.write(history-32,data);m.write(output-32,b'\xa5'*(1024*4+64));m.word(position,phase);m.word(index,offset)
        for name,value in (('position_ptr',position),('index_ptr',index),('calls',0),('seed',0x12345678),('mutate',mutate)):
            m.word(symbols[name],value)
        m.write(symbols['trace'],bytes(512*16))
        args=[callback,0x1000234,ch,count,history,step,position,index]
        if address==new:args.append(output)
        m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),args):m.uc.reg_write(r,v)
        for i,v in enumerate(args[4:]):m.word(0x83aff000+16+i*4,v)
        steps=[0]
        def tick(*unused):steps[0]+=1
        hook=m.uc.hook_add(UC_HOOK_CODE,tick) if measure else None
        m.uc.emu_start(address,0,count=2_000_000)
        if hook is not None:m.uc.hook_del(hook)
        assert m.finished and m.uc.reg_read(UC_MIPS_REG_SP)==0x83aff000
        result=(m.uc.reg_read(UC_MIPS_REG_V0),m.read(history-32,len(data)),m.read(output-32,1024*4+64),
            m.read(position,8),m.read(symbols['calls'],4),m.read(symbols['seed'],4),m.read(symbols['trace'],512*16))
        return result,steps[0]
    for case in range(512):
        count=([0,1,2,27,28,29,92,184,441,1024][case%10] if case<80 else rng.randrange(1025))
        step=rng.choice([0,1,0x8000,0x10000,0x18000,0x3fff0,rng.randrange(0x40000)])
        phase=rng.randrange(65536)+(0x40000 if case%7==0 else 0);offset=rng.randrange(28)
        edges=(0,1,0xffffffff,0x80000000,0x7fffffff)
        values=struct.pack('<36I',*(edges[i%5] for i in range(36))) if case<8 else rng.randbytes(36*4)
        data=b'\x5a'*32+values+b'\xa5'*32
        values=(symbols['callback'],case%24,count,step,phase,offset,data,case%2)
        a,_=run(old,*values);b,_=run(new,*values);assert a==b,(case,count,step,phase,offset)
    for step in (0x8000,0x10000,0x18000,0x3fff0):
        values=(symbols['dummy'],0,184,step,123,4,bytes(36*4+64),0)
        a,before=run(old,*values,True);b,after=run(new,*values,True);assert a==b
        cost.append({'step':step,'output_samples':184,'before':before,'after':after})
    report={'ok':True,'sha256':m.metadata['sha256'],'cases':512,'native_instruction_counts':cost,
        'checks':['actual upstream C macro compiled for MIPS32','full output/history/canaries and final phase/index',
            'random pitch, zero pitch, first-block phase, 0..1024 samples','callback-visible phase/index and order',
            'callbacks modifying phase/index and returning end-of-sound flags','all source values including int32 limits']}
    (args.bda.parent/'spu-samples-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
