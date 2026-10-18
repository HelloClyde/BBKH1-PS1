"""Native VLC batches vs the compiled R3000 interpreter and original MIPS JIT.

The fixture is a relocatable SDK primary-table coefficient loop, not a movie.
Synthetic tables and streams cover register, bit, output and event semantics.
"""
from pathlib import Path
import argparse,json,random,struct
from unicorn import UC_HOOK_CODE
from unicorn.mips_const import *
from smoke import PS1Machine,ROOT
from elftools.elf.elffile import ELFFile

LOOP=[int(x,16) for x in '''
000244c2 000840c0 01064020 8d090000 00000000 15200011 312100ff
00021200 20630008 30610010 10200005 3063000f 94880000 20840002 00684004 00481025
000245c2 00084080 01074020 8d090000 00005820 04010002 312100ff
8d0b0004 00221004 00611820 30610010 10200005 3063000f
94880000 20840002 00684004 00481025
00094c02 39217c1f 10200015 3921fe00
1020ff93 a4a90000 1160ffd8 20a50002
316affff 39417c1f 1020000d 3941fe00
1020ff8b a4aa0000 000b5402 1140ffcf 20a50002
39417c1f 10200005 3941fe00
1020ff83 a4aa0000 0401ffc8 20a50002
'''.split()]

class CPU:
    def __init__(self,bda,jit):
        self.m=PS1Machine(bda,(ROOT/'build/test-rom/H1TEST.exe').read_bytes());m=self.m;sy=m.symbols
        self.abi=struct.unpack('<10I',m.read(sy['h1_ps1_abi'],40));self.regs=sy['psxRegs']
        m.write(sy['Config']+self.abi[6],bytes([0 if jit else 1]))
        assert self.call(sy['_Z7psxInitv'])==0
        self.ram=self.word(sy['psxM']);table=sy['psxRec' if jit else 'psxInt']
        self.execute=self.word(table+12);self.clear=self.word(table+16);self.due=[]
        def branch(uc,address,size,data):
            if self.word(self.regs+self.abi[3])>=self.word(self.regs+self.abi[4]):self.due.append(True)
            uc.reg_write(UC_MIPS_REG_PC,uc.reg_read(UC_MIPS_REG_RA))
        m.uc.hook_add(UC_HOOK_CODE,branch,begin=sy['_Z13psxBranchTestv'],end=sy['_Z13psxBranchTestv'])
        self.trace=[]
        if jit and bda.with_suffix('.elf').is_file():
            with bda.with_suffix('.elf').open('rb') as f:
                for symbol in ELFFile(f).get_section_by_name('.symtab').iter_symbols():
                    if 'recExecuteBlock' not in symbol.name or symbol['st_info']['type']!='STT_FUNC':continue
                    for off in range(0,symbol['st_size'],4):
                        address=symbol['st_value']+off
                        if self.word(address) not in (0x01000008,0x0100f809):continue
                        def dispatch(uc,address,size,data):
                            self.trace.append((hex(uc.reg_read(UC_MIPS_REG_V0)),self.word(self.regs+self.abi[3])))
                        m.uc.hook_add(UC_HOOK_CODE,dispatch,begin=address,end=address)
    def word(self,p):return struct.unpack('<I',self.m.read(p,4))[0]
    def call(self,p,*values):
        m=self.m;m.finished=False;m.uc.reg_write(UC_MIPS_REG_SP,0x83aff000);m.uc.reg_write(UC_MIPS_REG_RA,0x80001ff0)
        for r,v in zip((UC_MIPS_REG_A0,UC_MIPS_REG_A1,UC_MIPS_REG_A2,UC_MIPS_REG_A3),values):m.uc.reg_write(r,v)
        m.uc.emu_start(p,0,count=4_000_000);assert m.finished,hex(m.uc.reg_read(UC_MIPS_REG_PC))
        return m.uc.reg_read(UC_MIPS_REG_V0)
    def put(self,p,data):self.m.write(self.ram+(p&0x1fffff),data)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('bda',type=Path);ap.add_argument('--reference',type=Path,required=True)
    args=ap.parse_args();optimized=CPU(args.bda,True);interpreter=CPU(args.reference,False);jit=CPU(args.reference,True)
    assert not jit.m.metadata['options'].get('vlc_hle'),'the original JIT reference must disable VLC HLE'
    cpus=(optimized,interpreter,jit);head,table,source,dest=0x80010000,0x80040000,0x80060000,0x80070000
    code=struct.pack('<57I',*LOOP)
    for cpu in cpus:cpu.put(head,code)
    admit=optimized.m.symbols.get('h1_ps1_vlc_hle_admit')
    token=optimized.call(admit,head) if admit else None
    if admit:assert token
    abi=optimized.abi;size,pc_off,cycle_off,io_off=abi[1:5];gpr_off=abi[8]
    rng=random.Random(0x564c43);batched=declined=stub_checks=groups=0;tested_multipliers=set()
    for case in range(192):
        count=1+case%3;bits=1+case%16
        values=[rng.randrange(1,0x7000) for _ in range(3)]
        extra=(values[1]|((values[2] if count==3 else 0)<<16)) if count>1 else 0
        word=(values[0]<<16)|bits
        mode='' if case<120 or case>=168 else ('secondary','first-EOB','first-escape','second-EOB','third-escape','write-disabled',
              'output-odd','input-odd','table-odd','bad-position','MMIO-table','output-code',
              'bad-bits','output-end','event-due','table-end')[case%16]
        if mode=='secondary':word=0
        if mode=='first-EOB':word=0xfe000000|bits
        if mode=='first-escape':word=0x7c1f0000|bits
        if mode=='second-EOB':extra=0xfe00
        if mode=='third-escape':extra=0x7c1f0001
        if mode=='bad-bits':word&=~255
        table_data=struct.pack('<II',word,extra)*8192
        stream=rng.randbytes(1024);output=b'\xa5'*2048
        state=bytearray(size);gpr=[rng.getrandbits(32) for _ in range(34)];gpr[0]=0
        gpr[2]=rng.getrandbits(32);gpr[3]=case%16;gpr[4]=source;gpr[5]=dest+(case%2)*2;gpr[6]=table
        # All invalid-address cases must decline before touching guest state.
        if mode=='output-odd':gpr[5]|=1
        if mode=='input-odd':gpr[4]|=1;gpr[3]=15
        if mode=='table-odd':gpr[6]|=1
        if mode=='bad-position':gpr[3]=16
        if mode=='MMIO-table':gpr[6]=0x1f801000
        if mode=='output-code':gpr[5]=head
        if mode=='output-end':gpr[5]=0x801fffff
        if mode=='table-end':gpr[6]=0x801ffffc;gpr[2]=0
        if case>=168:
            # An output can overwrite unread stream/table bytes. Match the
            # original load/store order, and stop after this group.
            gpr[5]=source if case%2 else table+((gpr[2]>>19)<<3)
        struct.pack_into('<34I',state,gpr_off,*gpr)
        cycle=rng.randrange(100000);delta=0 if mode=='event-due' else rng.choice([1,41,42,43,64,100,200,600,10000])
        mult=512 if case<64 else rng.choice([256,384,512,600])
        if case<48:delta=600
        if case>=168:mult=512;delta=(51,69,83)[count-1]
        if 'cycle_multiplier' not in optimized.m.symbols:mult=512
        tested_multipliers.add(mult)
        for cpu in cpus:
            # The recompiler embeds the cycle multiplier in each block.
            cpu.call(cpu.clear,head,57)
            s=bytearray(state)
            for off,v in ((pc_off,head),(cycle_off,cycle),(io_off,cycle+delta),(abi[5],mode!='write-disabled'),(abi[7],cpu.ram)):
                struct.pack_into('<I',s,off,v)
            struct.pack_into('<I',s,abi[9]+48,0x10900000)
            cpu.m.write(cpu.regs,bytes(s))
            if 'cycle_multiplier' in cpu.m.symbols:cpu.m.word(cpu.m.symbols['cycle_multiplier'],mult)
            cpu.put(table,table_data);cpu.put(source,stream);cpu.put(dest,output);cpu.due.clear();cpu.trace.clear()
        before=optimized.m.read(optimized.regs,size);memory=optimized.m.read(optimized.ram,0x200000)
        if token is None:
            # LTO inlines admission into the real recompiler. Exercise that
            # path; its first and only admission owns immutable token 1.
            optimized.call(optimized.execute,head);token=1;handled=1
            assert optimized.word(optimized.m.symbols['h1_vlc_hle_stats'])>0
        else:handled=optimized.call(optimized.m.symbols['h1_ps1_vlc_hle_execute'],head,token)
        result=optimized.m.read(optimized.regs,size);after=optimized.m.read(optimized.ram,0x200000)
        if not handled:
            assert result==before and after==memory,(case,mode,'decline changed state');declined+=1;continue
        assert not mode,(case,mode,'unexpected admission')
        spent=struct.unpack_from('<I',result,cycle_off)[0]-cycle;assert 0<spent<delta
        n=0
        for cpu in ((interpreter,jit) if mult==512 else (jit,)):
            n=0
            while cpu.word(cpu.regs+cycle_off)<cycle+spent:
                cpu.call(cpu.execute,head);n+=1;assert n<=128
            reference=cpu.m.read(cpu.regs,size)
            for off,length in ((gpr_off,136),(pc_off,4),(cycle_off,4)):
                assert result[off:off+length]==reference[off:off+length],(case,mult,n,off,
                    result[off:off+length].hex(),reference[off:off+length].hex(),cpu.trace[-30:])
            assert cpu.m.read(cpu.ram,0x200000)==after,(case,'RAM differs')
            assert not cpu.due,(case,'crossed hardware event')
        if case%5==0:
            optimized.m.write(optimized.regs,before);optimized.m.write(optimized.ram,memory)
            optimized.call(optimized.execute,head);stub=optimized.m.read(optimized.regs,size)
            for off,length in ((gpr_off,136),(pc_off,4),(cycle_off,4)):
                assert stub[off:off+length]==result[off:off+length],('JIT stub',case,off)
            assert optimized.m.read(optimized.ram,0x200000)==after and not optimized.due;stub_checks+=1
        batched+=1;groups+=n
    mutations=0
    for i,w in enumerate(LOOP):
        optimized.put(head+4*i,struct.pack('<I',w^1));before=optimized.m.read(optimized.regs,size)
        assert optimized.call(optimized.m.symbols['h1_ps1_vlc_hle_execute'],head,token)==1
        assert optimized.m.read(optimized.regs,size)==before
        optimized.put(head+4*i,struct.pack('<I',w));mutations+=1
    report={'ok':True,'sha256':optimized.m.metadata['sha256'],'reference_sha256':jit.m.metadata['sha256'],
        'reference_vlc_hle_disabled':True,
        'cases':192,'batched':batched,'declined_without_changes':declined,'coefficient_groups_checked':groups,
        'instruction_mutations_rejected':mutations,'actual_JIT_HLE_stub_checks':stub_checks,
        'cycle_multipliers':sorted(tested_multipliers),
        'checks':['all GPR/HI/LO, PC, cycles and entire 2 MiB RAM vs original compiled CPUs',
            'one, two and three tokens per table entry; all bit positions and refills',
            'compiled JIT cycle rounding and strict hardware event boundary',
            'EOB, escape, secondary table, invalid addresses and write-disabled fallback',
            'overlapping output with input stream and lookup-table data',
            'guest lookup tables; relocatable code with no fixed game PC']}
    (args.bda.parent/'vlc-hle-equivalence.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()
